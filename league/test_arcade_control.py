from datetime import timedelta

from django.contrib import admin
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    ArcadeAttempt, ArcadeCompetition, ArcadeRecord, ArcadeSettings, ArcadeWheelSpin,
    DoodleAttempt, DoodleRecord, DuelSettings, Event, MinesweeperAttempt, Season,
)


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class ArcadeControlTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("lab-admin", is_staff=True, is_superuser=True)
        self.player = User.objects.create_user("lab-player")
        self.client.force_login(self.staff)
        self.url = reverse("league:arcade_control")
        season = Season.get_active()
        now = timezone.now()
        self.event = Event.objects.create(name="Lab GP", round_number=1, season_year=season.year,
            deadline=now + timedelta(days=1), race_datetime=now + timedelta(days=2))
        self.settings, _ = ArcadeSettings.objects.update_or_create(pk=1, defaults={
            "active_game": "doodle_jump", "competition_event": self.event,
            "competition_opened_at": now - timedelta(hours=1), "public_enabled": True,
        })
        self.contest = ArcadeCompetition.objects.create(event=self.event, game_key="doodle_jump",
            opened_at=self.settings.competition_opened_at)

    def test_four_games_share_one_lab_with_separate_publishing_settings(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "arcade-control.css")
        self.assertContains(response, 'class="lab-game-card"', count=4)
        cards = response.context["test_games"]
        self.assertEqual([card["key"] for card in cards], ["doodle_jump", "flappy", "minesweeper", "tetris"])
        for card in cards:
            self.assertContains(response, f'href="{card["url"]}"')
        self.assertNotContains(response, "flight=1")
        self.assertNotContains(response, '<option value="tetris"')
        self.assertNotContains(response, '<option value="minesweeper"')
        self.assertContains(response, '<details class="lab-disclosure" id="lab-competition" open>')
        self.assertContains(response, '<details class="lab-disclosure" id="lab-wheel">')
        self.assertTrue(response.context["contest_open"])

    def test_every_card_opens_without_results_or_competition_changes(self):
        response = self.client.get(self.url)
        tracked = (ArcadeAttempt, DoodleAttempt, MinesweeperAttempt, ArcadeRecord, DoodleRecord, ArcadeWheelSpin)
        before = [model.objects.count() for model in tracked]
        for card in response.context["test_games"]:
            with self.subTest(game=card["key"]):
                game = self.client.get(card["url"])
                self.assertEqual(game.status_code, 200)
                if card["key"] != "tetris":
                    self.assertTrue(game.context["arcade_test_mode"])
                self.assertNotContains(game, 'id="arcade-wheel-panel"')
                self.assertEqual([model.objects.count() for model in tracked], before)
        self.settings.refresh_from_db()
        self.contest.refresh_from_db()
        self.assertEqual(self.settings.active_game, "doodle_jump")
        self.assertEqual(self.settings.competition_event_id, self.event.pk)
        self.assertTrue(self.settings.public_enabled)
        self.assertIsNone(self.contest.frozen_at)

    def test_test_attempt_endpoints_do_not_record_results(self):
        for name in ("doodle_attempt_start", "arcade_run_start", "minesweeper_attempt_start"):
            response = self.client.post(reverse("league:" + name) + "?admin_test=1")
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(response.json()["attempt_id"])
        for model in (DoodleAttempt, ArcadeAttempt, MinesweeperAttempt, ArcadeRecord, DoodleRecord):
            self.assertFalse(model.objects.exists())

    def test_minesweeper_preview_cannot_finish_even_a_real_attempt(self):
        attempt = MinesweeperAttempt.objects.create(user=self.staff, week_start=timezone.localdate())
        response = self.client.post(reverse("league:minesweeper_attempt_finish") + "?admin_test=1",
            {"attempt_id": attempt.pk, "completed": True, "elapsed_ms": 5000}, content_type="application/json")
        self.assertEqual(response.status_code, 403)
        attempt.refresh_from_db()
        self.assertIsNone(attempt.finished_at)
        self.assertFalse(attempt.completed)

    def test_player_cannot_use_lab_or_bypass_minesweeper_access_with_test_flag(self):
        self.client.force_login(self.player)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.get(reverse("league:arcade_minesweeper_preview")).status_code, 403)
        response = self.client.post(reverse("league:minesweeper_attempt_start") + "?admin_test=1")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(MinesweeperAttempt.objects.exists())
        self.client.logout()
        self.assertRedirects(self.client.get(self.url), reverse("login") + "?next=" + self.url)

    def test_expired_selection_is_visible_and_can_be_paused_without_new_event(self):
        self.event.deadline = timezone.now() - timedelta(hours=1)
        self.event.save(update_fields=["deadline"])
        response = self.client.get(self.url)
        self.assertFalse(response.context["contest_open"])
        self.assertContains(response, "Дедлайн прошёл")
        self.assertEqual(response.context["selected_event"], self.event)
        self.assertTrue(response.context["selected_event_expired"])
        self.assertContains(response, 'value="close" formnovalidate')
        response = self.client.post(self.url, {"action": "close"})
        self.assertEqual(response.status_code, 302)
        self.settings.refresh_from_db()
        self.assertFalse(self.settings.public_enabled)

    def test_requested_sections_removed_from_admin_not_from_database(self):
        record = DoodleRecord.objects.create(user=self.player, best_score=700)
        for model in (DoodleRecord, MinesweeperAttempt, DuelSettings, ArcadeRecord):
            with self.subTest(model=model.__name__):
                self.assertFalse(admin.site.is_registered(model))
                self.assertEqual(self.client.get(f'/admin/league/{model._meta.model_name}/').status_code, 404)
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '/admin/league/doodlerecord/')
        self.assertTrue(DoodleRecord.objects.filter(pk=record.pk, best_score=700).exists())
        self.assertTrue(admin.site.is_registered(DoodleAttempt))

    def test_future_stage_can_be_assigned_without_switching_or_pausing_live_game(self):
        future = Event.objects.create(name="Future GP", round_number=2, season_year=self.event.season_year,
            deadline=timezone.now()+timedelta(days=8), race_datetime=timezone.now()+timedelta(days=10))
        payload = {"action": "select", "active_game": "flappy", "competition_event": future.pk}
        self.assertEqual(self.client.post(self.url, payload).status_code, 302)
        draft = ArcadeCompetition.objects.get(event=future)
        self.assertEqual(draft.game_key, "flappy")
        self.assertIsNone(draft.opened_at)
        self.settings.refresh_from_db()
        self.assertTrue(self.settings.public_enabled)
        self.assertEqual(self.settings.competition_event_id, self.event.pk)
        self.assertEqual(self.settings.active_game, "doodle_jump")
        self.client.post(self.url, {**payload, "active_game": "doodle_jump"})
        draft.refresh_from_db()
        self.assertEqual(draft.game_key, "doodle_jump")
        self.assertIsNone(draft.opened_at)
        page = self.client.get(self.url, {"event": future.pk})
        self.assertEqual(page.context["selected_game_key"], "doodle_jump")
        self.assertEqual(page.context["selected_assignment_state"], "Назначена")
        self.assertTrue(page.context["blocked_by_previous"])
        self.client.force_login(self.player)
        self.assertFalse(self.client.get(reverse("league:arcade_game", args=["flappy"])).context["competitive_now"])

    def test_opening_next_stage_waits_for_previous_race_and_then_keeps_history(self):
        future = Event.objects.create(name="Next GP", round_number=2, season_year=self.event.season_year,
            deadline=timezone.now()+timedelta(days=8))
        draft = ArcadeCompetition.objects.create(event=future, game_key="flappy")
        payload = {"action": "publish", "active_game": "flappy", "competition_event": future.pk}
        self.client.post(self.url, payload)
        draft.refresh_from_db()
        self.assertIsNone(draft.opened_at)
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.competition_event_id, self.event.pk)
        self.event.race_datetime = timezone.now()-timedelta(hours=1)
        self.event.deadline = timezone.now()-timedelta(hours=4)
        self.event.save()
        self.client.post(self.url, payload)
        draft.refresh_from_db()
        self.settings.refresh_from_db()
        self.contest.refresh_from_db()
        self.assertIsNotNone(draft.opened_at)
        self.assertEqual(self.settings.competition_event_id, future.pk)
        self.assertEqual(self.settings.active_game, "flappy")
        self.assertTrue(self.settings.public_enabled)
        self.assertIsNotNone(self.contest.frozen_at)

    def test_published_game_is_immutable_and_pause_resume_preserves_attempts(self):
        attempt = DoodleAttempt.objects.create(user=self.player, competition=self.contest, score=123)
        opened_at = self.contest.opened_at
        for action in ("select", "publish"):
            self.client.post(self.url, {"action": action, "active_game": "flappy", "competition_event": self.event.pk})
            self.contest.refresh_from_db()
            self.assertEqual(self.contest.game_key, "doodle_jump")
        self.client.post(self.url, {"action": "close", "competition_event": self.event.pk})
        self.settings.refresh_from_db()
        self.assertFalse(self.settings.public_enabled)
        self.client.post(self.url, {"action": "publish", "active_game": "doodle_jump", "competition_event": self.event.pk})
        self.settings.refresh_from_db()
        self.contest.refresh_from_db()
        self.assertTrue(self.settings.public_enabled)
        self.assertEqual(self.contest.opened_at, opened_at)
        self.assertTrue(DoodleAttempt.objects.filter(pk=attempt.pk, score=123).exists())

    def test_pausing_a_future_draft_does_not_pause_another_stage(self):
        future = Event.objects.create(name="Draft GP", round_number=2, season_year=self.event.season_year,
            deadline=timezone.now()+timedelta(days=8))
        ArcadeCompetition.objects.create(event=future, game_key="flappy")
        self.client.post(self.url, {"action": "close", "competition_event": future.pk})
        self.settings.refresh_from_db()
        self.assertTrue(self.settings.public_enabled)

    def test_drafts_never_freeze_or_appear_as_competition_on_public_pages(self):
        from .arcade_library import contest_rows, freeze, history
        future = Event.objects.create(name="Draft GP", round_number=2, season_year=self.event.season_year,
            deadline=timezone.now()-timedelta(days=1))
        draft = ArcadeCompetition.objects.create(event=future, game_key="flappy")
        self.assertEqual(contest_rows(draft), ([], 0))
        self.assertIsNone(freeze(draft).frozen_at)
        self.assertEqual(history("flappy", self.player), [])
        self.client.force_login(self.player)
        self.assertNotContains(self.client.get(reverse("league:arcade")), "Draft GP")

    def test_stale_global_settings_cannot_publish_a_draft_implicitly(self):
        future = Event.objects.create(name="Planned GP", round_number=2, season_year=self.event.season_year,
            deadline=timezone.now()+timedelta(days=8))
        draft = ArcadeCompetition.objects.create(event=future, game_key="flappy")
        self.settings.competition_event = future
        self.settings.active_game = "flappy"
        # Simulate stale legacy settings pointing at an unopened assignment.
        self.settings.save()
        self.client.force_login(self.player)
        page = self.client.get(reverse("league:arcade"))
        self.assertFalse(page.context["contest_open"])
        result = self.client.post(reverse("league:arcade_run_start")).json()
        self.assertIsNone(ArcadeAttempt.objects.get(pk=result["attempt_id"]).competition_id)
        draft.refresh_from_db()
        self.assertIsNone(draft.opened_at)
