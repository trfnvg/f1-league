import json
from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import ArcadeCompetition, ArcadeRecord, ArcadeSettings, DoodleAttempt, DoodleRecord, Event, Season
from .arcade_library import freeze


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class ArcadeLibraryTests(TestCase):
    def finish_run(self, started, score):
        """Simulate real wall-clock play/checkpoints, never instant forged scores."""
        attempt = DoodleAttempt.objects.get(pk=started["attempt_id"])
        total_seconds = max(10, score / 150)
        passed = 0
        while passed + 150 < total_seconds:
            passed += 150
            with patch("league.arcade_validation.timezone.now", return_value=attempt.started_at+timedelta(seconds=passed)):
                response = self.client.post(reverse("league:doodle_attempt_progress"),
                    data=json.dumps({"attempt_id": attempt.pk, "run_token": started["run_token"],
                                     "score": min(score, int(passed*150))}), content_type="application/json")
            self.assertEqual(response.status_code, 200, response.content)
        with patch("league.arcade_validation.timezone.now", return_value=attempt.started_at+timedelta(seconds=total_seconds)):
            return self.client.post(reverse("league:doodle_attempt_finish"), data=json.dumps({
                "attempt_id": attempt.pk, "run_token": started["run_token"], "score": score}), content_type="application/json")

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
        response=self.client.get(reverse("league:arcade"))
        self.assertEqual([card["key"] for card in response.context["games"]],["doodle_jump","flappy"])
        flappy=self.client.get(reverse("league:arcade_game",args=["flappy"]))
        self.assertContains(flappy,'id="arcade-enter-fullscreen"')
        self.assertNotContains(flappy,"Играть на весь экран")

    def test_new_attempt_binds_only_current_game(self):
        for name, Model, competitive in [("doodle_attempt_start", DoodleAttempt, True)]:
            data = self.client.post(reverse("league:"+name)).json()
            self.assertEqual(Model.objects.get(pk=data["attempt_id"]).competition_id, self.contest.pk)
        response = self.client.post(reverse("league:arcade_run_start"))
        self.assertIsNone(response.json().get("error"))
        from .models import ArcadeAttempt
        self.assertIsNone(ArcadeAttempt.objects.get(pk=response.json()["attempt_id"]).competition_id)

    def test_library_feature_disappears_exactly_at_deadline_but_games_remain(self):
        url = reverse("league:arcade")
        for offset, active in ((-1, True), (0, False), (1, False)):
            with self.subTest(offset=offset), patch("league.arcade_library.timezone.now",
                    return_value=self.event.deadline+timedelta(seconds=offset)):
                page = self.client.get(url)
                self.assertEqual(page.context["contest_open"], active)
                if active:
                    self.assertContains(page, 'class="library-featured"', count=1)
                    self.assertContains(page, 'data-contest-deadline=')
                else:
                    self.assertIsNone(page.context["current_game"])
                    self.assertNotContains(page, 'class="library-featured"')
                    self.assertNotContains(page, 'class="library-notice"')
                    self.assertNotContains(page, "ЗАЧЁТ ЗАВЕРШЁН")
                self.assertContains(page, "Библиотека игр")
                for game in ("flappy", "doodle_jump"):
                    self.assertContains(page, reverse("league:arcade_game", args=[game]))
        self.contest.refresh_from_db()
        self.assertIsNotNone(self.contest.frozen_at)

    def test_paused_competition_does_not_get_a_library_feature(self):
        self.settings.public_enabled = False
        self.settings.save(update_fields=["public_enabled"])
        page = self.client.get(reverse("league:arcade"))
        self.assertNotContains(page, 'class="library-featured"')
        self.assertContains(page, "Библиотека игр")

    def test_all_public_results_use_shared_component_for_players_and_guests(self):
        ArcadeRecord.objects.create(user=self.user, best_score=50, total_attempts=2)
        DoodleRecord.objects.create(user=self.user, best_score=500, total_attempts=2)
        for guest in (False, True):
            if guest:
                self.client.logout()
            for key, prefix in (("flappy", "arcade"), ("doodle_jump", "doodle")):
                page = self.client.get(reverse("league:arcade_game", args=[key]))
                self.assertContains(page, "league/arcade-results.css")
                self.assertContains(page, f'class="{prefix}-leaderboard arcade-results"')
                self.assertContains(page, f'class="{prefix}-leaderboard-list arcade-results-list"', count=1)
                self.assertContains(page, 'class="arcade-table-labels"', count=1)
                self.assertContains(page, f'id="{prefix}-leaderboard-list"', count=1)
                self.assertContains(page, 'class="arcade-results-total"', count=1)
                self.assertContains(page, 'Всего попыток')
                self.assertContains(page, '<span>Результат</span>')
                self.assertNotContains(page, 'онлайн-обновление')
                self.assertNotContains(page, 'ВСЕГО ПОПЫТОК')

    def test_global_place_is_available_below_top_ten(self):
        ArcadeRecord.objects.create(user=self.user, best_score=5, total_attempts=3)
        for i in range(11):
            rival = User.objects.create_user(f"ranked-{i}")
            ArcadeRecord.objects.create(user=rival, best_score=10+i, total_attempts=1)
        data = self.client.get(reverse("league:arcade_leaderboard")).json()
        self.assertEqual(len(data["records"]), 10)
        self.assertEqual(data["rank"], 12)
        self.assertEqual(data["board_record"], 5)
        page = self.client.get(reverse("league:arcade_game", args=["flappy"]))
        self.assertContains(page, 'id="arcade-own-rank">12</strong>')

    def test_single_board_switches_at_deadline_and_when_paused(self):
        DoodleRecord.objects.create(user=self.user, best_score=900, total_attempts=20)
        attempt = DoodleAttempt.objects.create(user=self.user, competition=self.contest, score=200)
        DoodleAttempt.objects.filter(pk=attempt.pk).update(
            started_at=self.now-timedelta(minutes=5), finished_at=self.now-timedelta(minutes=4))
        page = reverse("league:arcade_game", args=["doodle_jump"])
        endpoint = reverse("league:doodle_leaderboard")
        response = self.client.get(page)
        self.assertContains(response, "Зачёт этапа · R1 · Library GP")
        self.assertNotContains(response, 'class="arcade-history"')
        data = self.client.get(endpoint).json()
        self.assertEqual(data["records"][0]["score"], 200)
        self.assertEqual(data["total_attempts"], 1)
        self.assertEqual(data["record"], 900)  # Personal all-time best remains intact.
        self.settings.public_enabled = False
        self.settings.save(update_fields=["public_enabled"])
        self.assertEqual(self.client.get(endpoint).json()["board_scope"], "global")
        self.settings.public_enabled = True
        self.settings.save(update_fields=["public_enabled"])
        self.event.deadline = self.now-timedelta(minutes=1)
        self.event.save(update_fields=["deadline"])
        data = self.client.get(endpoint).json()
        self.assertEqual(data["board_title"], "Глобальный рейтинг")
        self.assertEqual(data["records"][0]["score"], 900)
        self.assertEqual(data["total_attempts"], 20)
        self.assertNotContains(self.client.get(page), 'class="arcade-history"')

    def test_flappy_board_uses_competition_only_for_selected_game(self):
        from .models import ArcadeAttempt
        self.settings.active_game = "flappy"
        self.settings.save(update_fields=["active_game"])
        self.contest.game_key = "flappy"
        self.contest.save(update_fields=["game_key"])
        ArcadeRecord.objects.create(user=self.user, best_score=80, total_attempts=12)
        attempt = ArcadeAttempt.objects.create(user=self.user, competition=self.contest, score=15)
        ArcadeAttempt.objects.filter(pk=attempt.pk).update(finished_at=self.now)
        response = self.client.get(reverse("league:arcade_game", args=["flappy"]))
        self.assertContains(response, "Зачёт этапа · R1 · Library GP")
        self.assertNotContains(response, 'class="arcade-history"')
        self.assertEqual(self.client.get(reverse("league:arcade_leaderboard")).json()["records"][0]["score"], 15)
        self.assertEqual(self.client.get(reverse("league:doodle_leaderboard")).json()["board_scope"], "global")

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
        finish = self.finish_run(start, 900)
        self.assertEqual(finish.status_code,200)
        self.assertEqual(finish.json()["record"],900)
        self.assertEqual(freeze(self.contest).standings,frozen.standings)
        self.assertEqual(freeze(self.contest).total_attempts,1)

    def test_late_finish_excluded_from_event_but_saved_globally(self):
        start=self.client.post(reverse("league:doodle_attempt_start")).json()
        self.event.deadline=timezone.now()-timedelta(seconds=1)
        self.event.save(update_fields=["deadline"])
        response=self.finish_run(start, 500)
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
            response=self.client.post(url,data=json.dumps({"attempt_id":start["attempt_id"],"run_token":start["run_token"],"score":score}),content_type="application/json")
            self.assertEqual(response.status_code,status)
        self.assertEqual(DoodleRecord.objects.get(user=self.user).best_score,100)

    def test_endless_scores_share_the_same_attempt_and_record(self):
        for score in [50000,100000,1000001]:
            with self.subTest(score=score):
                start=self.client.post(reverse("league:doodle_attempt_start")).json()
                url=reverse("league:doodle_attempt_finish")
                payload={"attempt_id":start["attempt_id"],"run_token":start["run_token"],"score":score}
                finish=self.finish_run(start, score)
                self.assertEqual(finish.status_code,200)
                self.assertEqual(DoodleRecord.objects.get(user=self.user).best_score,score)
                self.assertEqual(DoodleAttempt.objects.get(pk=start["attempt_id"]).score,score)
                self.assertEqual(self.client.post(url,data=json.dumps(payload),content_type="application/json").status_code,409)
        self.assertEqual(DoodleRecord.objects.get(user=self.user).total_attempts,3)
        invalid=self.client.post(reverse("league:doodle_attempt_finish"),
            data=json.dumps({"attempt_id":1,"score":2147483648}),content_type="application/json")
        self.assertEqual(invalid.status_code,400)

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
