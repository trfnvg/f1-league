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
        self.assertContains(response, '<details class="lab-disclosure" id="lab-competition">')
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
        self.assertContains(response, f'value="{self.event.pk}" selected disabled')
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
