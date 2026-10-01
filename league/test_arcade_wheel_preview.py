from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import ArcadeWheelSpin


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

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Тестовый режим — безопасно для лиги.")
        self.assertContains(response, 'id="test-wheel-disc"')
        self.assertContains(response, 'id="test-wheel-apply"')
        self.assertNotContains(response, "data-spin-url")
        self.assertNotContains(response, "data-activate-url")
        self.assertEqual(ArcadeWheelSpin.objects.count(), 0)

    def test_preview_rejects_post_without_creating_a_spin(self):
        admin = User.objects.create_user("wheel-preview-admin", is_staff=True)
        self.client.force_login(admin)

        response = self.client.post(self.url, {"prize": "pit_wall"})

        self.assertEqual(response.status_code, 405)
        self.assertEqual(ArcadeWheelSpin.objects.count(), 0)
