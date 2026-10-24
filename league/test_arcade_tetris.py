from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .arcade_library import GAMES, PREVIEW_GAMES
from .models import (
    ArcadeAttempt, ArcadeCompetition, ArcadeRecord, ArcadeSettings, ArcadeWheelSpin,
    DoodleAttempt, DoodleRecord, Event, Season,
)


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class TetrisPreviewTests(TestCase):
    def setUp(self):
        self.url = reverse("league:arcade_game", args=["tetris"])
        self.admin = User.objects.create_user("tetris-admin", is_staff=True)
        self.player = User.objects.create_user("tetris-player")
        Season.objects.update_or_create(year=2026, defaults={"is_active": True})

    def test_anonymous_and_player_cannot_open_even_with_preview_flag(self):
        for user in (None, self.player):
            if user:
                self.client.force_login(user)
            for suffix in ("", "?admin_test=1"):
                self.assertEqual(self.client.get(self.url+suffix).status_code, 404)

    def test_admin_gets_playable_preview_without_database_mutations(self):
        self.client.force_login(self.admin)
        tracked = (ArcadeAttempt, DoodleAttempt, ArcadeRecord, DoodleRecord,
                   ArcadeCompetition, ArcadeWheelSpin, ArcadeSettings)
        before = [model.objects.count() for model in tracked]
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "arcade_tetris.html")
        for text in ("Pit Stack", 'id="tetris-canvas"', "tetris-engine.js", "tetris-gestures.js",
                     "tetris-scenery.js", "Лаборатория · закрытый тест"):
            self.assertContains(response, text)
        self.assertEqual([model.objects.count() for model in tracked], before)
        self.assertNotContains(response, 'id="arcade-wheel-panel"')
        for text in ('class="tetris-controls"', 'id="tetris-level"', 'id="tetris-status"',
                     'class="tetris-rules"', 'class="tetris-key-hint"',
                     "Классическая механика. Гоночный ритм.", "Тестовый заезд. Результат не сохраняется."):
            self.assertNotContains(response, text)

    def test_only_control_contains_preview_not_public_library(self):
        self.client.force_login(self.admin)
        control = self.client.get(reverse("league:arcade_control"))
        self.assertContains(control, self.url)
        self.assertContains(control, "Лаборатория · новые игры")
        self.assertNotContains(control, '<option value="tetris"')
        for user in (self.admin, self.player):
            self.client.force_login(user)
            library = self.client.get(reverse("league:arcade"))
            self.assertNotContains(library, self.url)
            self.assertNotContains(library, "Pit Stack")

    def test_unreleased_game_cannot_be_published_by_forged_form(self):
        self.client.force_login(self.admin)
        event = Event.objects.create(name="Tetris GP", round_number=1, season_year=2026,
            deadline=timezone.now()+timedelta(days=1))
        response = self.client.post(reverse("league:arcade_control"), {
            "action": "publish", "active_game": "tetris", "competition_event": event.pk,
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ArcadeCompetition.objects.filter(event=event).exists())
        self.assertNotEqual(ArcadeSettings.objects.get(pk=1).active_game, "tetris")
        self.assertNotIn("tetris", GAMES)
        self.assertIn("tetris", PREVIEW_GAMES)

    def test_preview_is_get_only(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_admin_access_does_not_change_existing_competition(self):
        self.client.force_login(self.admin)
        now = timezone.now()
        event = Event.objects.create(name="Current GP", round_number=1, season_year=2026,
            deadline=now+timedelta(hours=1))
        settings, _ = ArcadeSettings.objects.update_or_create(pk=1, defaults={
            "active_game": "doodle_jump", "competition_event": event,
            "competition_opened_at": now-timedelta(hours=1), "public_enabled": True,
        })
        contest = ArcadeCompetition.objects.create(event=event, game_key="doodle_jump", opened_at=settings.competition_opened_at)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        settings.refresh_from_db(); contest.refresh_from_db()
        self.assertEqual(settings.active_game, "doodle_jump")
        self.assertTrue(settings.public_enabled)
        self.assertIsNone(contest.frozen_at)
