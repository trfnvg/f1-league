import json
from datetime import timedelta
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import ArcadeCompetition, ArcadeRecord, ArcadeSettings, DoodleAttempt, DoodleRecord, Event, Season
from .arcade_library import freeze


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class ArcadeLibraryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("racer", password="pass")
        self.admin = User.objects.create_user("admin", password="pass", is_staff=True)
        self.now = timezone.now()
        Season.objects.update_or_create(year=2026, defaults={"is_active":True})
        self.event = Event.objects.create(name="Library GP", round_number=1, season_year=2026,
            deadline=self.now + timedelta(hours=1), race_datetime=self.now + timedelta(hours=3))
        self.settings, _ = ArcadeSettings.objects.update_or_create(pk=1, defaults={"active_game":"doodle_jump", "public_enabled":True,
            "competition_event":self.event, "competition_opened_at":self.now-timedelta(hours=1)})
        self.contest = ArcadeCompetition.objects.create(game_key="doodle_jump", event=self.event, opened_at=self.settings.competition_opened_at)
        self.client.force_login(self.user)

    def test_library_and_both_game_pages(self):
        for url in [reverse("league:arcade"), reverse("league:arcade_game", args=["flappy"]), reverse("league:arcade_game", args=["doodle_jump"])]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Аркады")
        self.assertContains(self.client.get(reverse("league:arcade")), "Library GP")

    def test_new_attempt_binds_only_current_game(self):
        for name, Model, competitive in [("doodle_attempt_start", DoodleAttempt, True)]:
            data = self.client.post(reverse("league:"+name)).json()
            self.assertEqual(Model.objects.get(pk=data["attempt_id"]).competition_id, self.contest.pk)
        response = self.client.post(reverse("league:arcade_run_start"))
        self.assertIsNone(response.json().get("error"))
        from .models import ArcadeAttempt
        self.assertIsNone(ArcadeAttempt.objects.get(pk=response.json()["attempt_id"]).competition_id)

    def test_deadline_freezes_standings_but_global_play_continues(self):
        attempt = DoodleAttempt.objects.create(user=self.user, competition=self.contest, score=200)
        DoodleAttempt.objects.filter(pk=attempt.pk).update(started_at=self.now-timedelta(minutes=5), finished_at=self.now-timedelta(minutes=4))
        DoodleRecord.objects.create(user=self.user, best_score=200, total_attempts=1)
        self.event.deadline = self.now-timedelta(minutes=1)
        self.event.save(update_fields=["deadline"])
        frozen = freeze(self.contest)
        self.assertEqual(frozen.standings[0]["score"],200)
        self.assertEqual(frozen.standings[0]["attempts"],1)
        start = self.client.post(reverse("league:doodle_attempt_start")).json()
        self.assertIsNone(DoodleAttempt.objects.get(pk=start["attempt_id"]).competition_id)
        finish = self.client.post(reverse("league:doodle_attempt_finish"), data=json.dumps({"attempt_id":start["attempt_id"],"score":900}), content_type="application/json")
        self.assertEqual(finish.status_code,200)
        self.assertEqual(finish.json()["record"],900)
        self.assertEqual(freeze(self.contest).standings,frozen.standings)
        self.assertEqual(freeze(self.contest).total_attempts,1)

    def test_late_finish_excluded_from_event_but_saved_globally(self):
        start=self.client.post(reverse("league:doodle_attempt_start")).json()
        self.event.deadline=timezone.now()-timedelta(seconds=1)
        self.event.save(update_fields=["deadline"])
        response=self.client.post(reverse("league:doodle_attempt_finish"),data=json.dumps({"attempt_id":start["attempt_id"],"score":500}),content_type="application/json")
        self.assertEqual(response.status_code,200)
        self.assertEqual(freeze(self.contest).standings,[])
        self.assertEqual(DoodleRecord.objects.get(user=self.user).best_score,500)

    def test_archive_has_no_wheel(self):
        response=self.client.get(reverse("league:arcade_game",args=["flappy"]))
        self.assertNotContains(response,'id="arcade-wheel-panel"')
        self.assertContains(response,'id="arcade-canvas"')

    def test_admin_test_does_not_write_attempts(self):
        self.client.force_login(self.admin)
        response=self.client.post(reverse("league:doodle_attempt_start")+"?admin_test=1")
        self.assertIsNone(response.json()["attempt_id"])
        self.assertFalse(DoodleAttempt.objects.exists())

    def test_control_permissions_and_publication(self):
        url=reverse("league:arcade_control")
        self.assertEqual(self.client.get(url).status_code,403)
        self.client.force_login(self.admin)
        response=self.client.get(url)
        self.assertEqual(response.status_code,200)
        self.assertContains(response,"Управление аркадами")

    def test_duplicate_finish_cannot_modify_record(self):
        start=self.client.post(reverse("league:doodle_attempt_start")).json()
        url=reverse("league:doodle_attempt_finish")
        for score,status in [(100,200),(900,409)]:
            response=self.client.post(url,data=json.dumps({"attempt_id":start["attempt_id"],"score":score}),content_type="application/json")
            self.assertEqual(response.status_code,status)
        self.assertEqual(DoodleRecord.objects.get(user=self.user).best_score,100)

    def test_free_play_cannot_take_wheel_from_event_winner(self):
        from .models import Prediction
        from .arcade_rewards import spin_event_wheel, ArcadeWheelError
        Prediction.objects.create(user=self.user,event=self.event,p1="norris",p2="piastri",p3="russell",pole="norris",safety_car_count=0,dnf_count=0)
        winner=DoodleAttempt.objects.create(user=self.user,competition=self.contest,score=200)
        DoodleAttempt.objects.filter(pk=winner.pk).update(started_at=self.now-timedelta(minutes=10),finished_at=self.now-timedelta(minutes=9))
        self.event.deadline=self.now-timedelta(minutes=1)
        self.event.save(update_fields=["deadline"])
        late=DoodleAttempt.objects.create(user=self.user,score=900)
        DoodleAttempt.objects.filter(pk=late.pk).update(finished_at=self.now)
        spin,created=spin_event_wheel(self.event,self.user)
        self.assertTrue(created)
        self.assertEqual(spin.winner_score,200)

    def test_wheel_removed_after_race_start(self):
        self.event.deadline=self.now-timedelta(hours=2)
        self.event.race_datetime=self.now-timedelta(hours=1)
        self.event.save()
        response=self.client.get(reverse("league:arcade_game",args=["doodle_jump"]))
        self.assertEqual(response.status_code,200)
        self.assertNotContains(response,'id="arcade-wheel-panel"')

    def test_control_opens_next_event_without_erasing_history(self):
        self.event.deadline=self.now-timedelta(hours=2)
        self.event.race_datetime=self.now-timedelta(hours=1)
        self.event.save()
        next_event=Event.objects.create(name="Next GP",round_number=2,season_year=2026,deadline=self.now+timedelta(days=3))
        self.client.force_login(self.admin)
        response=self.client.post(reverse("league:arcade_control"),{"action":"publish","active_game":"flappy","competition_event":next_event.pk})
        self.assertEqual(response.status_code,302)
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.active_game,"flappy")
        self.assertEqual(ArcadeCompetition.objects.count(),2)
        self.contest.refresh_from_db()
        self.assertIsNotNone(self.contest.frozen_at)
