from datetime import timedelta
from importlib import import_module
from io import BytesIO
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from PIL import Image
from django.apps import apps
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .competition_scoring import recalculate_global_event, recalculate_league_event
from .league_management import decide_crazy, decide_day, delete_league
from .league_standings import standings
from .leagues import create_league, enroll_member
from .models import (Event, GlobalEventScore, League, LeagueActivity, LeagueCrazyDecision, LeagueDayDecision,
    LeagueMembership, Prediction, Result, Score, Season)


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class LeagueManagementTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.owner = User.objects.create_user("league-manager")
        self.other = User.objects.create_user("other-owner")
        self.player = User.objects.create_user("friend")
        self.operator = User.objects.create_user("platform", is_staff=True)
        self.season = Season.objects.create(year=2027, is_active=True)
        self.event = Event.objects.create(name="Monaco", season_year=2027, round_number=1,
            deadline=self.now+timedelta(days=1), race_datetime=self.now+timedelta(days=2))
        self.a = create_league(owner=self.owner, name="Alpha", season=self.season, start_event=self.event, ruleset="paddock")
        self.b = create_league(owner=self.other, name="Bravo", season=self.season, start_event=self.event, ruleset="paddock")
        self.entry = enroll_member(actor=self.owner, league_season=self.a, user=self.player)
        enroll_member(actor=self.other, league_season=self.b, user=self.player)
        self.client.force_login(self.owner)

    def url(self, name="friend_league_settings", league=None, **kwargs):
        return reverse("league:"+name, kwargs={"league_id": (league or self.a).league_id, **kwargs})

    def publish(self):
        self.prediction = Prediction.objects.create(event=self.event, user=self.player,
            p1="russell", p2="norris", p3="leclerc", pole="russell", driver_of_day="russell", crazy_prediction="A crazy result")
        Prediction.objects.filter(pk=self.prediction.pk).update(created_at=self.now-timedelta(days=4))
        self.prediction.refresh_from_db()
        self.event.deadline=self.now-timedelta(days=2);self.event.race_datetime=self.now-timedelta(days=1)
        self.event.status=Event.Status.SCORED
        self.event.save()
        # Enrollment preceded the original deadline; changing test dates must
        # not create a corrupt persisted eligibility boundary.
        for ls in (self.a, self.b):
            ls.entries.update(entered_at=self.now-timedelta(days=5))
        self.result = Result.objects.create(event=self.event, p1="russell", p2="norris", p3="leclerc",
            pole="russell", driver_of_day="russell", published_at=self.now-timedelta(hours=1))
        recalculate_global_event(actor=self.operator, event=self.event)
        recalculate_league_event(actor=self.owner, league_season=self.a, event=self.event)
        recalculate_league_event(actor=self.other, league_season=self.b, event=self.event)

    def test_creator_has_manager_status_without_platform_permissions(self):
        member=LeagueMembership.objects.get(league=self.a.league, user=self.owner)
        self.assertEqual(member.role, "manager")
        self.owner.refresh_from_db();self.assertFalse(self.owner.is_staff)
        self.assertContains(self.client.get(self.url("friend_league")), "Управляющий лигой")
        self.assertContains(self.client.get(self.url()), "Название и аватар")

    def test_direct_entry_remembers_only_accessible_league_and_catalog_is_explicit(self):
        self.assertRedirects(self.client.get(reverse("league:friend_leagues")), self.url("friend_league"), fetch_redirect_response=False)
        response=self.client.get(self.url("friend_league"))
        self.assertContains(response, "Очки по этапам");self.assertNotContains(response, "Динамика очков")
        self.assertContains(response, 'class="classification-table"')
        self.assertContains(response, f'href="/leagues/{self.a.league_id}/events/{self.event.pk}/"')
        self.assertEqual(response.context['result_events'], [])
        self.assertNotContains(response, 'league/leaderboard-chart.js')
        self.assertContains(response, "Сменить лигу");self.assertNotContains(response, "Назначить модератором")
        self.assertNotContains(response, '>Таблица</a>')
        self.assertContains(self.client.get(reverse("league:friend_leagues"), {"all":"1"}), "Создать лигу")
        self.assertRedirects(self.client.get(reverse("league:leaderboard")), reverse("league:friend_leagues"), fetch_redirect_response=False)
        session=self.client.session;session["active_friend_league"]=str(self.b.league_id);session.save()
        self.assertRedirects(self.client.get(reverse("league:friend_leagues")), self.url("friend_league"), fetch_redirect_response=False)

    def test_profile_update_is_scoped_and_does_not_accept_role_or_owner_changes(self):
        response=self.client.post(self.url(), {"name":"Renamed Alpha", "owner":self.other.pk, "is_staff":"true"})
        self.assertEqual(response.status_code,302)
        self.a.league.refresh_from_db();self.assertEqual(self.a.league.name,"Renamed Alpha")
        self.assertEqual(self.a.league.owner,self.owner)
        self.assertEqual(self.client.post(self.url(league=self.b),{"name":"Hijacked"}).status_code,404)
        self.client.force_login(self.player)
        self.assertEqual(self.client.post(self.url(),{"name":"Hijacked"}).status_code,403)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(self.url()).status_code,404)

    def test_manager_can_configure_but_moderator_cannot_rename(self):
        member=self.entry.membership
        member.role="moderator";member.save(update_fields=("role",))
        self.client.force_login(self.player)
        self.assertEqual(self.client.get(self.url()).status_code,403)
        member.role="manager";member.save(update_fields=("role",))
        self.assertEqual(self.client.post(self.url(),{"name":"Managed Alpha"}).status_code,302)

    def test_avatar_is_normalized_and_svg_or_invalid_upload_is_rejected(self):
        with TemporaryDirectory(prefix="fastlap-avatar-test-") as directory, override_settings(MEDIA_ROOT=directory):
            buffer=BytesIO();Image.new("RGB",(90,120),"red").save(buffer,"PNG")
            upload=SimpleUploadedFile("avatar.png",buffer.getvalue(),content_type="image/png")
            self.assertEqual(self.client.post(self.url(),{"name":"Alpha","avatar":upload}).status_code,302)
            self.a.league.refresh_from_db()
            with self.a.league.avatar.open("rb") as content, Image.open(content) as image:
                self.assertEqual((image.format,image.size),("WEBP",(512,512)))
            old=self.a.league.avatar.name
            invalid=SimpleUploadedFile("evil.svg",b'<svg onload="alert(1)"></svg>',content_type="image/svg+xml")
            self.assertEqual(self.client.post(self.url(),{"name":"Bad","avatar":invalid}).status_code,200)
            self.a.league.refresh_from_db();self.assertEqual(self.a.league.avatar.name,old)
            self.assertEqual(self.a.league.name,"Alpha")

    def test_transparent_league_logo_keeps_alpha_and_all_edges(self):
        with TemporaryDirectory(prefix="fastlap-avatar-test-") as directory, override_settings(MEDIA_ROOT=directory):
            source = Image.new("RGBA", (512, 256), (0, 0, 0, 0))
            # Opposite edges detect accidental centre cropping; a semitransparent
            # centre detects RGB conversion or compositing onto a solid colour.
            source.putpixel((0, 128), (255, 0, 0, 255))
            source.putpixel((511, 128), (0, 255, 0, 255))
            source.putpixel((256, 128), (0, 0, 255, 128))
            buffer = BytesIO();source.save(buffer, "PNG")
            upload = SimpleUploadedFile("logo.png", buffer.getvalue(), content_type="image/png")
            self.assertEqual(self.client.post(self.url(), {"name": "Alpha", "avatar": upload}).status_code, 302)
            self.a.league.refresh_from_db()
            with self.a.league.avatar.open("rb") as content, Image.open(content) as stored:
                image = stored.convert("RGBA")
                self.assertEqual(image.size, (512, 512))
                self.assertEqual(image.getpixel((0, 0))[3], 0)
                self.assertEqual(image.getpixel((0, 256)), (255, 0, 0, 255))
                self.assertEqual(image.getpixel((511, 256)), (0, 255, 0, 255))
                self.assertEqual(image.getpixel((256, 256)), (0, 0, 255, 128))

    def test_driver_day_changes_only_this_league_and_can_restore_official(self):
        self.publish()
        before_a=standings(self.a)["rows"][0]["total"]
        before_b=standings(self.b)["rows"][0]["total"]
        global_before=GlobalEventScore.objects.get(user=self.player,event=self.event).points
        url=self.url("friend_league_day",event_id=self.event.pk)
        self.assertEqual(self.client.post(url,{"drivers":["norris"]}).status_code,302)
        self.assertEqual(standings(self.a)["rows"][0]["total"],before_a-3)
        self.assertEqual(standings(self.b)["rows"][0]["total"],before_b)
        self.assertEqual(GlobalEventScore.objects.get(user=self.player,event=self.event).points,global_before)
        self.result.refresh_from_db();self.assertEqual(self.result.driver_of_day,"russell")
        self.assertEqual(self.client.post(url,{"drivers":["norris","russell"]}).status_code,302)
        self.assertEqual(standings(self.a)["rows"][0]["total"],before_a)
        self.client.post(url,{"use_official":"on"})
        self.assertFalse(LeagueDayDecision.objects.filter(league_season=self.a).exists())
        self.assertEqual(standings(self.a)["rows"][0]["total"],before_a)

    def test_early_or_foreign_day_decision_is_rejected_and_csrf_required(self):
        url=self.url("friend_league_day",event_id=self.event.pk)
        self.assertEqual(self.client.get(url).status_code,405)
        self.client.post(url,{"drivers":["russell"]})
        self.assertFalse(LeagueDayDecision.objects.exists())
        self.assertEqual(self.client.post(self.url("friend_league_day",league=self.b,event_id=self.event.pk),{}).status_code,404)
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.owner)
        self.assertEqual(strict.post(url,{}).status_code,403)
        self.assertEqual(strict.post(self.url(),{"name":"X"}).status_code,403)

    def test_legacy_moderation_preserves_raw_scores_and_is_immediately_visible(self):
        self.publish()
        self.a.league.legacy_key="original-friends";self.a.league.save(update_fields=("legacy_key",))
        self.a.is_legacy=True;self.a.save(update_fields=("is_legacy",))
        score=Score.objects.create(user=self.player,event=self.event,points=35,prediction_points=30,duel_adjustment=5,
            breakdown={"Crazy Prediction":5,"Driver of the Day":3,"Дуэль":5})
        decide_crazy(actor=self.owner,season=self.a,entry=self.entry,event=self.event,approved=False)
        decide_day(actor=self.owner,season=self.a,event=self.event,drivers=["norris"])
        self.assertEqual(standings(self.a)["rows"][0]["total"],27)
        score.refresh_from_db();self.assertEqual(score.points,35)
        self.prediction.refresh_from_db();self.assertFalse(self.prediction.crazy_prediction_approved)
        url=self.url("friend_league_event",event_id=self.event.pk)
        response=self.client.get(url,{"manage":"1"})
        self.assertContains(response,"Гонщик дня");self.assertContains(response,"A crazy result")
        self.assertRedirects(self.client.get(reverse("league:leaderboard")),
            self.url("friend_league")+"?year=2027",fetch_redirect_response=False)

    def test_migration_gives_grisha_local_manager_rights_only(self):
        grisha=User.objects.create_user("Гриша")
        entry=enroll_member(actor=self.owner,league_season=self.a,user=grisha)
        self.a.league.legacy_key="original-friends";self.a.league.save(update_fields=("legacy_key",))
        import_module("league.migrations.0046_assign_league_managers").assign(apps,SimpleNamespace(connection=connection))
        entry.membership.refresh_from_db();self.assertEqual(entry.membership.role,"manager")
        grisha.refresh_from_db();self.assertFalse(grisha.is_staff);self.assertFalse(grisha.is_superuser)
        self.client.force_login(grisha)
        self.assertEqual(self.client.get(self.url()).status_code,200)

    def test_unknown_rules_and_other_season_cannot_receive_a_day_decision(self):
        self.publish()
        self.a.rules_version=99;self.a.save(update_fields=("rules_version",))
        url=self.url("friend_league_day",event_id=self.event.pk)
        self.assertEqual(self.client.post(url,{"drivers":["norris"]}).status_code,302)
        self.assertFalse(LeagueDayDecision.objects.exists())
        foreign=Event.objects.create(name="Other season",season_year=2028,round_number=1,
            deadline=self.now-timedelta(days=2),race_datetime=self.now-timedelta(days=1))
        self.assertEqual(self.client.post(self.url("friend_league_day",event_id=foreign.pk),{"drivers":["russell"]}).status_code,404)

    def test_creator_deletion_requires_confirmation_and_keeps_shared_history(self):
        self.publish()
        before=(list(Prediction.objects.values()),list(GlobalEventScore.objects.values()))
        url=self.url("friend_league_delete")
        self.assertEqual(self.client.get(url).status_code,200)
        self.a.league.refresh_from_db();self.assertIsNone(self.a.league.archived_at)
        self.assertContains(self.client.post(url,{"confirmation":"wrong"}),"Введите точное название")
        self.assertEqual(self.client.post(url,{"confirmation":"Alpha"}).status_code,302)
        self.a.league.refresh_from_db();self.assertIsNotNone(self.a.league.archived_at)
        self.assertEqual(before,(list(Prediction.objects.values()),list(GlobalEventScore.objects.values())))
        self.assertEqual(self.client.get(self.url("friend_league")).status_code,404)
        self.assertNotContains(self.client.get(reverse("league:friend_leagues"),{"all":"1"}),"Alpha")
        self.client.force_login(self.player)
        self.assertEqual(self.client.get(self.url("friend_league")).status_code,404)
        self.assertContains(self.client.get(self.url("friend_league",league=self.b)),"Bravo")
        delete_league(actor=self.owner,league=self.a.league,confirmation="Alpha")
        self.assertEqual(LeagueActivity.objects.filter(league=self.a.league,action="archived").count(),1)

    def test_manager_cannot_delete_and_delete_post_requires_csrf(self):
        member=self.entry.membership;member.role="manager";member.save(update_fields=("role",))
        self.client.force_login(self.player)
        self.assertNotContains(self.client.get(self.url()),"Удалить лигу")
        self.assertEqual(self.client.get(self.url("friend_league_delete")).status_code,403)
        self.assertEqual(self.client.post(self.url("friend_league_delete"),{"confirmation":"Alpha"}).status_code,403)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.post(self.url("friend_league_delete"),{"confirmation":"Alpha"}).status_code,404)
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.owner)
        self.assertEqual(strict.post(self.url("friend_league_delete"),{"confirmation":"Alpha"}).status_code,403)

    def test_deletion_revokes_existing_invite_and_leaves_other_league_intact(self):
        from .leagues import create_invite,invite_for_token
        from django.core.exceptions import ValidationError
        invite,token=create_invite(actor=self.owner,league_season=self.a)
        self.client.post(self.url("friend_league_delete"),{"confirmation":"Alpha"})
        invite.refresh_from_db();self.assertIsNotNone(invite.revoked_at)
        with self.assertRaises(ValidationError):invite_for_token(token)
        self.b.league.refresh_from_db();self.assertIsNone(self.b.league.archived_at)

    def test_current_gp_remains_after_predictions_close_until_two_hours_after_race_start(self):
        from unittest.mock import patch
        later=Event.objects.create(name="Later GP",season_year=2027,round_number=2,
            deadline=self.now+timedelta(days=8),race_datetime=self.now+timedelta(days=9))
        self.event.deadline=self.now-timedelta(minutes=1)
        self.event.status=Event.Status.LOCKED;self.event.save()
        response=self.client.get(self.url("friend_league"))
        self.assertEqual(response.context["next_event"],self.event)
        self.assertContains(response,"Прогнозы закрыты");self.assertContains(response,"Смотреть прогнозы")
        with patch("django.utils.timezone.now",return_value=self.event.race_datetime):
            response=self.client.get(self.url("friend_league"))
        self.assertEqual(response.context["next_event"],self.event)
        with patch("django.utils.timezone.now",return_value=self.event.race_datetime+timedelta(hours=2)):
            response=self.client.get(self.url("friend_league"))
        self.assertEqual(response.context["next_event"],later)

    def test_current_gp_without_race_time_falls_back_to_prediction_deadline(self):
        self.event.race_datetime=None;self.event.save(update_fields=("race_datetime",))
        response=self.client.get(self.url("friend_league"))
        self.assertEqual(response.context["next_event"],self.event)
        self.assertContains(response,"Время уточняется")
        self.event.deadline=self.now-timedelta(seconds=1);self.event.save(update_fields=("deadline",))
        self.assertEqual(self.client.get(self.url("friend_league")).context["next_event"],self.event)
        self.event.deadline=self.now-timedelta(hours=2);self.event.save(update_fields=("deadline",))
        self.assertIsNone(self.client.get(self.url("friend_league")).context["next_event"])

    def test_duel_is_removed_from_desktop_and_mobile_navigation(self):
        response=self.client.get(self.url("friend_league"))
        self.assertNotContains(response,'href="'+reverse("league:duel")+'"')
