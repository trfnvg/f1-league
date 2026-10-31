from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from .models import ArcadeSettings, ArcadeWheelSpin, Event, Season


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=TEST_STORAGES)
class ArcadeWheelPreviewTests(TestCase):
    def setUp(self):
        self.url = reverse("league:arcade_wheel_test")

    def test_preview_is_staff_only(self):
        player = User.objects.create_user("wheel-preview-player")
        self.client.force_login(player)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(ArcadeWheelSpin.objects.count(), 0)

    def test_staff_preview_has_no_live_wheel_endpoints_or_database_changes(self):
        admin = User.objects.create_user("wheel-preview-admin", is_staff=True)
        self.client.force_login(admin)

        response = self.client.get(self.url, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Управление аркадами")
        self.assertContains(response, "Изолированный режим")
        self.assertContains(response, 'id="test-wheel-disc"')
        self.assertContains(response, 'id="test-wheel-apply"')
        self.assertNotContains(response, "data-spin-url")
        self.assertNotContains(response, "data-activate-url")
        self.assertEqual(ArcadeWheelSpin.objects.count(), 0)

    def test_admin_control_contains_game_selector_and_isolated_wheel_demo(self):
        admin = User.objects.create_user("arcade-control-admin", is_staff=True)
        self.client.force_login(admin)
        Event.objects.create(name="Selectable GP", round_number=1, season_year=Season.get_active().year,
            deadline=timezone.now() + timedelta(days=2))

        response = self.client.get(reverse("league:arcade_control"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="arcade-game-select"')
        self.assertContains(response, "Открыть участникам")
        self.assertContains(response, 'id="test-wheel-disc"')
        self.assertContains(response, 'id="test-wheel-apply"')
        self.assertEqual(ArcadeWheelSpin.objects.count(), 0)

    def test_admin_can_select_and_publish_game_from_control_page(self):
        admin = User.objects.create_user("arcade-control-admin", is_staff=True)
        self.client.force_login(admin)
        url = reverse("league:arcade_control")
        season = Season.get_active()
        event = Event.objects.create(
            season_year=season.year,
            name="Selected GP",
            round_number=1,
            deadline=timezone.now() + timedelta(days=2),
            race_datetime=timezone.now() + timedelta(days=3),
        )

        selected = self.client.post(url, {
            "action": "select",
            "active_game": ArcadeSettings.Game.DOODLE_JUMP,
            "competition_event": event.pk,
        })
        self.assertEqual(selected.status_code, 302)
        settings = ArcadeSettings.objects.get(pk=1)
        self.assertEqual(settings.active_game, ArcadeSettings.Game.DOODLE_JUMP)
        self.assertEqual(settings.competition_event, event)
        self.assertFalse(settings.public_enabled)

        published = self.client.post(url, {
            "action": "publish",
            "active_game": ArcadeSettings.Game.DOODLE_JUMP,
            "competition_event": event.pk,
        })
        self.assertEqual(published.status_code, 302)
        settings.refresh_from_db()
        self.assertTrue(settings.public_enabled)
        self.assertIsNotNone(settings.competition_opened_at)

    def test_regular_player_cannot_use_admin_control_or_admin_game_preview(self):
        player = User.objects.create_user("arcade-control-player")
        self.client.force_login(player)

        self.assertEqual(self.client.get(reverse("league:arcade_control")).status_code, 403)
        response = self.client.get(reverse("league:arcade_game", args=["doodle_jump"]), {"admin_test": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["arcade_test_mode"])
        self.assertNotContains(response, 'id="doodle-admin-controls"')

    def test_preview_rejects_post_without_creating_a_spin(self):
        admin = User.objects.create_user("wheel-preview-admin", is_staff=True)
        self.client.force_login(admin)

        response = self.client.post(self.url, {"prize": "pit_wall"})

        self.assertEqual(response.status_code, 405)
        self.assertEqual(ArcadeWheelSpin.objects.count(), 0)
