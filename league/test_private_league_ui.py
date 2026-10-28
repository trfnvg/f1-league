from datetime import datetime, timedelta, timezone as dt_timezone
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .competition_scoring import recalculate_league_event
from .leagues import accept_invite, create_invite, create_league, current_invite, invite_for_token, revoke_invite
from .models import (
    Event, GlobalEventScore, League, LeagueActivity, LeagueCrazyDecision, LeagueEventScore,
    LeagueInvite, LeagueMembership, LeagueSeason, Prediction, Result, Score, Season, SeasonScore,
)
from .scoring import publish_event_scores

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=STORAGES)
class PrivateLeagueUITests(TestCase):
    def setUp(self):
        self.now = datetime(2027, 3, 1, 12, tzinfo=dt_timezone.utc)
        patcher = patch("django.utils.timezone.now", return_value=self.now)
        self.clock = patcher.start();self.addCleanup(patcher.stop)
        self.season = Season.objects.create(year=2027, is_active=True)
        self.owner = User.objects.create_user("owner")
        self.other = User.objects.create_user("other")
        self.player = User.objects.create_user("friend")
        self.staff = User.objects.create_user("staff", is_staff=True)
        self.event = Event.objects.create(name="Monaco", season_year=2027, round_number=6,
            deadline=self.now+timedelta(days=1), race_datetime=self.now+timedelta(days=2))
        self.next_event = Event.objects.create(name="Canada", season_year=2027, round_number=7,
            deadline=self.now+timedelta(days=8), race_datetime=self.now+timedelta(days=9))
        self.a = create_league(owner=self.owner, name="Private Alpha", season=self.season, start_event=self.event, ruleset="paddock")
        self.b = create_league(owner=self.other, name="Secret Bravo", season=self.season, start_event=self.event, ruleset="paddock")
        self.client.force_login(self.owner)
        self.values = dict(p1="russell", p2="leclerc", p3="norris", pole="russell",
            fastest_lap="russell", driver_of_day="russell", safety_car_count=1, dnf_count=2,
            crazy_prediction="Private crazy text <script>alert(1)</script>")

    def url(self, name="friend_league", league=None, **kwargs):
        return reverse(f"league:{name}", kwargs={"league_id": (league or self.a).league_id, **kwargs})

    def enter(self, league=None):
        ls = league or self.a
        _, token = create_invite(actor=self.owner if ls == self.a else self.other, league_season=ls)
        return accept_invite(user=self.player, token=token)

    def result(self):
        self.clock.return_value = self.event.race_datetime+timedelta(hours=1)
        return Result.objects.create(event=self.event, **{k: v for k, v in self.values.items() if k != "crazy_prediction"})

    def test_index_detail_create_and_navigation_render_without_private_league_leak(self):
        response = self.client.get(reverse("league:friend_leagues"), {"all": "1"})
        self.assertContains(response, "Private Alpha");self.assertNotContains(response, "Secret Bravo")
        self.assertContains(response, "Мои лиги")
        self.assertNotContains(response, '<h2>Мои лиги</h2>')
        self.assertNotContains(response, 'class="leagues-breadcrumb"')
        self.assertEqual(self.client.get(self.url()).status_code, 200)
        self.assertEqual(self.client.get(reverse("league:friend_league_create")).status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])

    def test_create_ignores_forged_owner_and_grants_no_staff_access(self):
        response = self.client.post(reverse("league:friend_league_create"), {
            "name": "My fresh league", "start_event": self.next_event.pk, "ruleset": "classic",
            "owner": self.other.pk, "is_staff": "true", "legacy_key": "original-friends",
        })
        self.assertEqual(response.status_code, 302)
        league = League.objects.get(name="My fresh league")
        self.assertEqual(league.owner, self.owner);self.assertIsNone(league.legacy_key)
        self.owner.refresh_from_db();self.assertFalse(self.owner.is_staff)
        self.assertEqual(league.seasons.get().start_event, self.next_event)

    def test_first_future_card_is_selected_after_current_deadline(self):
        self.clock.return_value = self.event.deadline
        response = self.client.get(reverse("league:friend_league_create"))
        form = response.context["form"]
        self.assertEqual(form.initial["start_event"], self.next_event.pk)
        self.assertNotIn(self.event, form.fields["start_event"].queryset)
        self.assertEqual(self.next_event.voting_state(), "open")
        response = self.client.post(reverse("league:friend_league_create"), {
            "name": "Next race league", "start_event": self.next_event.pk, "ruleset": "classic"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(League.objects.get(name="Next race league").seasons.get().entries.get().first_event, self.next_event)

    def test_new_calendar_card_without_season_settings_can_start_a_league(self):
        event = Event.objects.create(name="New calendar", season_year=2028, round_number=1,
            deadline=self.now+timedelta(days=400), race_datetime=self.now+timedelta(days=401))
        self.assertFalse(Season.objects.filter(year=2028).exists())
        response = self.client.get(reverse("league:friend_league_create"))
        self.assertIn(event, response.context["form"].fields["start_event"].queryset)
        self.assertFalse(Season.objects.filter(year=2028).exists(), "GET never creates calendar settings")
        response = self.client.post(reverse("league:friend_league_create"), {
            "name": "Fresh calendar", "start_event": event.pk, "ruleset": "classic"})
        self.assertEqual(response.status_code, 302)
        ls = League.objects.get(name="Fresh calendar").seasons.get()
        self.assertEqual(ls.season.year, 2028)
        self.assertEqual(ls.entries.get().first_event, event)
        self.season.refresh_from_db();self.assertTrue(self.season.is_active)

    def register_main(self):
        import_module("league.migrations.0043_register_fastlap_main").register_main(apps, SimpleNamespace(connection=connection))

    def test_main_registration_is_idempotent_and_preserves_original_scores(self):
        primary = User.objects.create_user("trfnvg", is_staff=True, is_superuser=True)
        self.enter()
        Prediction.objects.create(user=self.player, event=self.event, p1="russell")
        Score.objects.create(user=self.player, event=self.event, points=29, prediction_points=26, duel_adjustment=3)
        Score.objects.create(user=self.player, event=self.next_event, points=7, prediction_points=10, duel_adjustment=-3)
        SeasonScore.objects.create(user=self.player, season_year=2027, points=12)
        before = (list(Prediction.objects.values()), list(Score.objects.values()), list(SeasonScore.objects.values()))
        self.register_main();self.register_main()
        main = League.objects.get(legacy_key="original-friends")
        self.assertEqual(main.name, "Fastlap Main");self.assertEqual(main.owner, primary)
        ls = main.seasons.get();self.assertTrue(ls.is_legacy)
        self.assertEqual(set(ls.entries.values_list("membership__user_id", flat=True)), {primary.pk, self.player.pk})
        self.assertEqual(before, (list(Prediction.objects.values()), list(Score.objects.values()), list(SeasonScore.objects.values())))
        self.assertFalse(LeagueEventScore.objects.exists())
        self.client.force_login(self.player)
        index = self.client.get(reverse("league:friend_leagues"), {"all": "1"})
        self.assertEqual(index.context["page"][0].league_id, main.pk)
        self.assertEqual(index.context["page"][0].member_count, 1)
        self.assertNotContains(index, "Ваша прежняя компания")
        detail = self.client.get(reverse("league:friend_league", args=[main.pk]))
        self.assertEqual(detail.status_code, 200)
        entry = detail.context["page"][0]
        self.assertEqual((entry.total, entry.rounds), (48, 2))
        self.assertContains(detail, "Fastlap Main")
        self.assertNotContains(detail, "История этой лиги ещё переносится")
        response = self.client.get(reverse("league:friend_league_event", args=[main.pk, self.event.pk]))
        self.assertRedirects(response, reverse("league:event_detail", args=[self.event.pk]), fetch_redirect_response=False)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("league:friend_league", args=[main.pk])).status_code, 404)

    def test_main_registration_never_guesses_owner_from_another_staff_account(self):
        Prediction.objects.create(user=self.player, event=self.event, p1="russell")
        self.register_main()
        self.assertFalse(League.objects.filter(legacy_key="original-friends").exists())

    def test_main_registration_reuses_previous_explicit_import_owner(self):
        from .leagues import import_legacy_league
        Prediction.objects.create(user=self.player, event=self.event, p1="russell")
        original, _ = import_legacy_league(owner=self.owner, season_year=2027)
        self.register_main()
        original.league.refresh_from_db()
        self.assertEqual(original.league.name, "Fastlap Main")
        self.assertEqual(original.league.owner, self.owner)
        self.assertEqual(League.objects.filter(legacy_key="original-friends").count(), 1)

    def repair_main(self):
        import_module("league.migrations.0044_link_main_to_grisha").link_main(apps, SimpleNamespace(connection=connection))

    def test_main_repair_uses_confirmed_production_login_without_staff_upgrade(self):
        grisha = User.objects.create_user("Гриша")
        Prediction.objects.create(user=grisha, event=self.event, p1="russell")
        Score.objects.create(user=grisha, event=self.event, points=31, prediction_points=26, duel_adjustment=5)
        before = (list(Prediction.objects.values()), list(Score.objects.values()))
        self.register_main()
        self.assertFalse(League.objects.filter(legacy_key="original-friends").exists())
        self.repair_main();self.repair_main()
        main = League.objects.get(legacy_key="original-friends")
        self.assertEqual(main.name, "Fastlap Main")
        self.assertEqual(main.owner, grisha)
        self.assertEqual(main.memberships.filter(user=grisha).count(), 1)
        self.assertEqual(main.seasons.get().entries.filter(membership__user=grisha).count(), 1)
        self.assertEqual(before, (list(Prediction.objects.values()), list(Score.objects.values())))
        grisha.refresh_from_db();self.assertFalse(grisha.is_staff);self.assertFalse(grisha.is_superuser)
        self.client.force_login(grisha)
        response = self.client.get(reverse("league:friend_leagues"), {"all": "1"})
        self.assertEqual(response.context["page"][0].league_id, main.pk)
        response = self.client.get(reverse("league:friend_league", args=[main.pk]))
        self.assertEqual(response.context["page"][0].total, 31)

    def test_main_repair_preserves_existing_owner_and_explicitly_links_grisha(self):
        grisha = User.objects.create_user("Гриша")
        primary = User.objects.create_user("trfnvg", is_staff=True)
        Prediction.objects.create(user=self.player, event=self.event, p1="russell")
        self.register_main()
        main = League.objects.get(legacy_key="original-friends")
        self.assertFalse(main.memberships.filter(user=grisha).exists())
        self.repair_main();self.repair_main()
        main.refresh_from_db();self.assertEqual(main.owner, primary)
        self.assertEqual(main.memberships.filter(user=grisha).count(), 1)
        self.assertEqual(League.objects.filter(legacy_key="original-friends").count(), 1)
        self.client.force_login(grisha)
        self.assertContains(self.client.get(reverse("league:friend_leagues"), {"all": "1"}), "Fastlap Main")

    def test_main_repair_does_not_guess_accounts_or_restore_disabled_membership(self):
        Prediction.objects.create(user=self.player, event=self.event, p1="russell")
        self.repair_main()
        self.assertFalse(League.objects.filter(legacy_key="original-friends").exists())
        grisha = User.objects.create_user("Гриша")
        self.repair_main()
        membership = LeagueMembership.objects.get(league__legacy_key="original-friends", user=grisha)
        membership.is_active = False;membership.save(update_fields=("is_active",))
        self.repair_main();membership.refresh_from_db();self.assertFalse(membership.is_active)

    def test_foreign_uuid_event_year_and_membership_ids_are_rejected(self):
        for url in [self.url(league=self.b), self.url("friend_league_invites", league=self.b),
                    self.url("friend_league_event", league=self.b, event_id=self.event.pk)]:
            self.assertEqual(self.client.get(url).status_code, 404)
        for year in ["garbage", "999999999999999999999999", "2028"]:
            self.assertEqual(self.client.get(self.url(), {"year": year}).status_code, 404)
        foreign = self.b.entries.get().membership
        self.assertEqual(self.client.post(self.url("friend_league_role", membership_id=foreign.pk), {"role": "moderator"}).status_code, 404)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_invite_get_has_no_membership_side_effect_and_post_is_idempotent(self):
        invite, token = create_invite(actor=self.owner, league_season=self.a)
        self.assertNotEqual(invite.token_digest, token)
        self.client.force_login(self.player)
        url = reverse("league:friend_league_join", args=[token])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertFalse(LeagueMembership.objects.filter(league=self.a.league, user=self.player).exists())
        for _ in range(2):
            self.assertEqual(self.client.post(url).status_code, 302)
        invite.refresh_from_db();self.assertEqual(invite.uses, 1)
        self.assertEqual(self.a.entries.filter(membership__user=self.player).count(), 1)
        self.assertEqual(LeagueActivity.objects.filter(action="joined").count(), 1)

    def test_invites_expire_at_boundary_and_revoke_blocks_get_and_post(self):
        invite, token = create_invite(actor=self.owner, league_season=self.a)
        # Old seven-day links remain supported until expired or explicitly rotated.
        invite.permanent_league = None
        invite.token_seed = None
        invite.expires_at = self.now+timedelta(days=7)
        invite.save()
        url = reverse("league:friend_league_join", args=[token])
        self.client.force_login(self.player)
        self.clock.return_value = invite.expires_at
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.clock.return_value = self.now
        revoke_invite(actor=self.owner, invite=invite)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertEqual(self.client.get(reverse("league:friend_league_join", args=["forged"])).status_code, 404)

    def test_expired_deadline_join_starts_next_round(self):
        invite, token = create_invite(actor=self.owner, league_season=self.a)
        self.clock.return_value = self.event.deadline
        entry = accept_invite(user=self.player, token=token)
        self.assertEqual(entry.first_event, self.next_event)

    def test_invite_management_requires_own_moderator_and_rotates_single_link(self):
        entry = self.enter()
        self.client.force_login(self.player)
        self.assertEqual(self.client.get(self.url("friend_league_invites")).status_code, 403)
        self.assertEqual(self.client.post(self.url("friend_league_role", membership_id=entry.membership_id), {"role": "moderator"}).status_code, 403)
        self.client.force_login(self.owner)
        response = self.client.post(self.url("friend_league_role", membership_id=entry.membership_id), {"role": "moderator"})
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.player)
        response = self.client.post(self.url("friend_league_invites"), follow=True)
        self.assertEqual(response.status_code, 200);self.assertTrue(response.context["invite_link"])
        invite = self.a.invites.latest("pk")
        self.assertNotIn(invite.token_digest, response.content.decode())
        for _ in range(3):
            create_invite(actor=self.owner, league_season=self.a)
        invite, token = create_invite(actor=self.owner, league_season=self.a)
        self.assertEqual(self.a.invites.filter(revoked_at__isnull=True).count(), 1)
        self.assertEqual(current_invite(actor=self.owner, league=self.a.league), token)

    def test_permanent_link_survives_refresh_time_and_rotation_preserves_members(self):
        first, old_token = create_invite(actor=self.owner, league_season=self.a)
        self.assertIsNone(first.expires_at)
        entry = accept_invite(user=self.player, token=old_token)
        self.clock.return_value = self.now+timedelta(days=365)
        self.assertEqual(invite_for_token(old_token).pk, first.pk)
        self.client.force_login(self.owner)
        page = self.client.get(self.url("friend_league_settings"))
        self.assertTrue(page.context["invite_link"].endswith(old_token+"/"))
        self.assertContains(page, "Обновить ссылку")
        second, token = create_invite(actor=self.owner, league_season=self.a)
        self.assertNotEqual(old_token, token)
        first.refresh_from_db()
        self.assertIsNotNone(first.revoked_at)
        with self.assertRaises(ValidationError):
            invite_for_token(old_token)
        self.assertEqual(invite_for_token(token).pk, second.pk)
        self.assertEqual(accept_invite(user=self.player, token=token).pk, entry.pk)
        self.assertEqual(self.a.entries.filter(membership__user=self.player).count(), 1)
        revoke_invite(actor=self.owner, invite=second)
        self.assertIsNone(current_invite(actor=self.owner, league=self.a.league))
        third, token = create_invite(actor=self.owner, league_season=self.a)
        self.assertEqual(invite_for_token(token).pk, third.pk)

    def test_one_link_for_entire_league_across_seasons(self):
        first, token = create_invite(actor=self.owner, league_season=self.a)
        self.season.is_active = False
        self.season.save(update_fields=["is_active"])
        calendar = Season.objects.create(year=2028, is_active=True)
        event = Event.objects.create(name="New season", round_number=1, season_year=2028,
            deadline=self.now+timedelta(days=365))
        season = LeagueSeason.objects.create(league=self.a.league, season=calendar, start_event=event)
        self.assertEqual(invite_for_token(token).league_season, season)
        entry = accept_invite(user=self.player, token=token)
        self.assertEqual(entry.league_season, season)
        self.assertEqual(entry.first_event, event)
        self.assertEqual(current_invite(actor=self.owner, league=self.a.league), token)
        second, new_token = create_invite(actor=self.owner, league_season=season)
        first.refresh_from_db()
        self.assertIsNotNone(first.revoked_at)
        with self.assertRaises(ValidationError):
            invite_for_token(token)
        self.assertEqual(current_invite(actor=self.owner, league=self.a.league), new_token)

    def test_rotation_retires_existing_seven_day_links(self):
        old, token = create_invite(actor=self.owner, league_season=self.a)
        old.permanent_league = None
        old.token_seed = None
        old.expires_at = self.now+timedelta(days=7)
        old.save()
        self.assertEqual(invite_for_token(token).pk, old.pk)
        self.assertIsNone(current_invite(actor=self.owner, league=self.a.league))
        new, new_token = create_invite(actor=self.owner, league_season=self.a)
        self.assertEqual(invite_for_token(new_token).pk, new.pk)
        with self.assertRaises(ValidationError):
            invite_for_token(token)

    @override_settings(PRIVATE_LEAGUE_MAX_MEMBERS=1, PRIVATE_LEAGUE_MAX_OWNED=1)
    def test_limits_reject_without_orphan_memberships(self):
        _, token = create_invite(actor=self.owner, league_season=self.a)
        with self.assertRaises(ValidationError):
            accept_invite(user=self.player, token=token)
        self.assertFalse(LeagueMembership.objects.filter(league=self.a.league, user=self.player).exists())
        with self.assertRaises(ValidationError):
            create_league(owner=self.owner, name="Spam", season=self.season, start_event=self.event)

    def test_shared_forecast_updates_one_row_and_preserves_classic_crazy_field(self):
        self.enter();self.enter(self.b)
        self.client.force_login(self.player)
        a = self.url("friend_league_event", event_id=self.event.pk)
        b = self.url("friend_league_event", league=self.b, event_id=self.event.pk)
        self.assertEqual(self.client.post(a, {**self.values, "user": self.owner.pk, "crazy_prediction_approved": "true"}).status_code, 302)
        self.assertEqual(Prediction.objects.count(), 1)
        forecast = Prediction.objects.get()
        self.assertEqual(forecast.user, self.player);self.assertFalse(forecast.crazy_prediction_approved)
        response = self.client.get(b)
        self.assertEqual(response.context["prediction"].pk, forecast.pk)
        self.assertEqual(self.client.post(b, {**self.values, "pole": "norris"}).status_code, 302)
        self.assertEqual(Prediction.objects.get().pole, "norris")
        classic = create_league(owner=self.player, name="Classic", season=self.season, start_event=self.event)
        url = self.url("friend_league_event", league=classic, event_id=self.event.pk)
        self.assertEqual(self.client.post(url, {**self.values, "crazy_prediction": "forged"}).status_code, 302)
        self.assertEqual(Prediction.objects.get().crazy_prediction, self.values["crazy_prediction"])

    def test_deadline_blocks_new_and_legacy_submission_routes(self):
        self.enter();self.client.force_login(self.player)
        self.clock.return_value = self.event.deadline
        for url in [self.url("friend_league_event", event_id=self.event.pk), reverse("league:event_detail", args=[self.event.pk])]:
            self.assertEqual(self.client.post(url, self.values).status_code, 302)
        self.assertFalse(Prediction.objects.exists())

    def test_predictions_and_crazy_are_not_exposed_to_other_players_before_deadline(self):
        self.enter()
        Prediction.objects.create(user=self.player, event=self.event, **self.values)
        url = self.url("friend_league_event", event_id=self.event.pk)
        response = self.client.get(url)
        self.assertNotContains(response, "Private crazy text")
        self.assertEqual(response.context["rows"], [])
        self.clock.return_value = self.event.deadline
        response = self.client.get(url)
        self.assertContains(response, "Private crazy text")
        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_publication_automatically_projects_private_standings_and_judge_is_scoped(self):
        entry = self.enter();other_entry = self.enter(self.b)
        Prediction.objects.create(user=self.player, event=self.event, **self.values)
        self.result()
        with self.captureOnCommitCallbacks(execute=True):
            publish_event_scores(self.event, self.staff)
        self.assertEqual(GlobalEventScore.objects.get(user=self.player).points, 40)
        self.assertEqual(LeagueEventScore.objects.get(entry=entry).points, 40)
        url = self.url("friend_league_judge", event_id=self.event.pk, entry_id=entry.pk)
        self.assertEqual(self.client.post(url, {"approved": "yes"}).status_code, 302)
        self.assertEqual(LeagueEventScore.objects.get(entry=entry).points, 45)
        self.assertEqual(LeagueEventScore.objects.get(entry=other_entry).points, 40)
        self.assertEqual(GlobalEventScore.objects.get(user=self.player).points, 40)
        response = self.client.get(self.url())
        self.assertEqual(response.context["page"].object_list[0].total, 45)
        foreign = self.url("friend_league_judge", event_id=self.event.pk, entry_id=other_entry.pk)
        self.assertEqual(self.client.post(foreign, {"approved": "yes"}).status_code, 404)
        self.client.force_login(self.player)
        self.assertEqual(self.client.post(url, {"approved": "no"}).status_code, 403)

    def test_all_mutations_are_post_only_and_csrf_protected(self):
        entry = self.enter()
        invite = self.a.invites.first()
        urls = [self.url("friend_league_revoke", invite_id=invite.pk),
                self.url("friend_league_role", membership_id=entry.membership_id),
                self.url("friend_league_judge", event_id=self.event.pk, entry_id=entry.pk),
                self.url("friend_league_recalculate", event_id=self.event.pk)]
        strict = Client(enforce_csrf_checks=True);strict.force_login(self.owner)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 405)
            self.assertEqual(strict.post(url, {}).status_code, 403)
        for url in [reverse("league:friend_league_create"), self.url("friend_league_invites"), self.url("friend_league_event", event_id=self.event.pk)]:
            self.assertEqual(strict.post(url, {}).status_code, 403)

    def test_standings_are_paginated_and_do_not_query_per_player(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertLess(len(queries), 22)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("league:friend_leagues"), {"all": "1"}).status_code, 302)
