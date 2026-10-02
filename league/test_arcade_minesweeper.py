from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import ArcadeSettings, MinesweeperAttempt


class MinesweeperArcadeTests(TestCase):
    def setUp(self):
        ArcadeSettings.objects.update_or_create(
            pk=1,
            defaults={
                "active_game": ArcadeSettings.Game.MINESWEEPER,
                "public_enabled": False,
            },
        )
        self.player = User.objects.create_user("mine-player", password="test-password")

    def test_private_arcade_is_only_visible_to_staff(self):
        self.client.force_login(self.player)
        self.assertEqual(self.client.get(reverse("league:arcade")).status_code, 403)
        self.assertEqual(self.client.get(reverse("league:minesweeper_leaderboard")).status_code, 403)
        self.assertEqual(
            self.client.post(reverse("league:minesweeper_attempt_start")).status_code,
            403,
        )

        admin = User.objects.create_superuser("mine-admin", "mine-admin@example.com", "test-password")
        self.client.force_login(admin)
        response = self.client.get(reverse("league:arcade"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PITWALL")
        self.assertContains(response, "ТОЛЬКО ДЛЯ АДМИНА")
        self.assertContains(response, reverse("admin:league_arcadesettings_change", args=(1,)))

    def test_admin_setting_page_is_available_for_toggling_public_access(self):
        admin = User.objects.create_superuser("mine-superuser", "admin@example.com", "test-password")
        self.client.force_login(admin)

        response = self.client.get(reverse("admin:league_arcadesettings_change", args=(1,)))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "active_game")
        self.assertContains(response, "public_enabled")

    def test_public_setting_exposes_game_to_players_but_not_admin_tools(self):
        ArcadeSettings.objects.filter(pk=1).update(public_enabled=True)
        self.client.force_login(self.player)

        response = self.client.get(reverse("league:arcade"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PITWALL")
        self.assertNotContains(response, "Управление аркадой")

    def test_attempt_count_and_best_completed_time_update_leaderboard(self):
        ArcadeSettings.objects.filter(pk=1).update(public_enabled=True)
        self.client.force_login(self.player)

        first = self.client.post(reverse("league:minesweeper_attempt_start"))
        self.assertEqual(first.status_code, 200)
        attempt_id = first.json()["attempt_id"]
        MinesweeperAttempt.objects.filter(pk=attempt_id).update(
            started_at=timezone.now() - timedelta(seconds=12),
        )
        finished = self.client.post(
            reverse("league:minesweeper_attempt_finish"),
            data={"attempt_id": attempt_id, "completed": True, "elapsed_ms": 10_000},
            content_type="application/json",
        )

        self.assertEqual(finished.status_code, 200)
        self.assertEqual(finished.json()["attempts"], 1)
        self.assertEqual(finished.json()["wins"], 1)
        self.assertEqual(finished.json()["best_time_ms"], 10_000)
        self.assertEqual(finished.json()["records"][0]["username"], self.player.username)

        second = self.client.post(reverse("league:minesweeper_attempt_start"))
        second_id = second.json()["attempt_id"]
        MinesweeperAttempt.objects.filter(pk=second_id).update(
            started_at=timezone.now() - timedelta(seconds=7),
        )
        failed = self.client.post(
            reverse("league:minesweeper_attempt_finish"),
            data={"attempt_id": second_id, "completed": False},
            content_type="application/json",
        )

        self.assertEqual(failed.status_code, 200)
        self.assertEqual(failed.json()["attempts"], 2)
        self.assertEqual(failed.json()["wins"], 1)
        self.assertEqual(failed.json()["total_attempts"], 2)

    def test_each_attempt_is_single_use_and_only_own_attempt_can_be_finished(self):
        ArcadeSettings.objects.filter(pk=1).update(public_enabled=True)
        self.client.force_login(self.player)
        started = self.client.post(reverse("league:minesweeper_attempt_start"))
        attempt_id = started.json()["attempt_id"]
        other = User.objects.create_user("other-mine-player", password="test-password")
        self.client.force_login(other)

        rejected = self.client.post(
            reverse("league:minesweeper_attempt_finish"),
            data={"attempt_id": attempt_id, "completed": False},
            content_type="application/json",
        )

        self.assertEqual(rejected.status_code, 409)
        self.assertIsNone(MinesweeperAttempt.objects.get(pk=attempt_id).finished_at)
