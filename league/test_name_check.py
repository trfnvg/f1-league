from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .auth_limits import bucket_key, consume
from .forms import RegisterForm
from .identity import clean_display_name
from .models import AuthRateBucket


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class NameCheckTests(TestCase):
    def setUp(self):
        self.url = reverse("league:name_check")
        self.data = dict(first_name="Гриша", username="racer63", email="new@example.com",
            password1="RaceStart!63", password2="RaceStart!63")

    def check(self, value, **extra):
        return self.client.post(self.url, {"name": value}, **extra)

    def test_ordinary_names_pass_without_reservations_or_changes(self):
        for value in ("Гриша", "Семён", "Esteban Ocon", "  Анна   Мария  ", "Я"):
            response = self.check(value)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"valid": True, "code": "valid",
                "message": "Имя соответствует правилам."})
            self.assertIn("no-store", response["Cache-Control"])
            self.assertIn("private", response["Cache-Control"])
        self.assertEqual(clean_display_name("  Анна   Мария  "), "Анна Мария")
        self.assertFalse(User.objects.exists())

    def test_name_is_not_unique_and_response_exposes_no_account_details(self):
        user = User.objects.create_user("racer64", first_name="Гриша", email="private@example.com")
        response = self.check("Гриша")
        self.assertTrue(response.json()["valid"])
        self.assertEqual(set(response.json()), {"valid", "code", "message"})
        self.assertNotContains(response, "private@example.com")
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Гриша")
        self.assertEqual(user.league_profile.handle, "racer64")

    def test_same_rules_in_preview_and_final_registration(self):
        for value, code in (("", "invalid_format"), ("   ", "invalid_format"),
                            ("Гриша63", "invalid_format"), ("Гриша🔥", "invalid_format"),
                            ("<script>", "invalid_format"), ("А"*151, "name_too_long"),
                            ("Владимир Путин", "name_not_allowed"), ("Адольф Гитлер", "name_not_allowed"),
                            ("Хуесос", "name_not_allowed"), ("f u c k", "name_not_allowed")):
            with self.subTest(value=value):
                response = self.check(value)
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.json()["valid"])
                self.assertEqual(response.json()["code"], code)
                self.assertIn("first_name", RegisterForm({**self.data, "first_name": value}).errors)
        self.assertFalse(User.objects.exists())

    def test_preview_cannot_replace_final_validation_or_create_account(self):
        self.assertTrue(self.check("Гриша").json()["valid"])
        response = self.client.post(reverse("league:register"), {**self.data, "first_name": "Владимир Путин"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("first_name", response.context["form"].errors)
        self.assertFalse(User.objects.exists())

    def test_post_only_and_real_csrf_protection(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        self.assertEqual(strict.post(self.url, {"name": "Гриша"}).status_code, 403)
        strict.get(reverse("league:register"))
        token = strict.cookies["csrftoken"].value
        self.assertEqual(strict.post(self.url, {"name": "Гриша"}, HTTP_X_CSRFTOKEN=token).status_code, 200)
        self.assertEqual(strict.post(self.url, {"name": "Гриша"}, HTTP_X_CSRFTOKEN=token,
            HTTP_ORIGIN="https://evil.example").status_code, 403)

    @override_settings(AUTH_TRUSTED_PROXIES=[])
    def test_rate_limit_and_spoofed_forwarded_address(self):
        for _ in range(60):
            self.assertEqual(self.check("Гриша").status_code, 200)
        with patch("league.auth_views.clean_display_name") as validate:
            response = self.check("Анна", HTTP_X_FORWARDED_FOR="192.0.2.2")
        validate.assert_not_called()
        self.assertEqual(response.status_code, 429)
        self.assertIsNone(response.json()["valid"])
        self.assertGreater(int(response["Retry-After"]), 0)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(self.check("Анна", REMOTE_ADDR="192.0.2.2").status_code, 200)
        # Independent limit: live handle checks and final registration still work.
        self.assertEqual(self.client.post(reverse("league:handle_check"), {"handle": "racer63"}).status_code, 200)
        self.assertEqual(self.client.post(reverse("league:register"), self.data).status_code, 302)

    def test_hourly_limit_and_expiry(self):
        consume("name-check-hour", "127.0.0.1", 600, 3600)
        key = bucket_key("name-check-hour", "127.0.0.1")
        AuthRateBucket.objects.filter(pk=key).update(hits=600)
        self.assertEqual(self.check("Гриша").status_code, 429)
        AuthRateBucket.objects.filter(pk=key).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.check("Гриша").status_code, 200)

    def test_only_registration_has_live_name_check(self):
        response = self.client.get(reverse("league:register"))
        self.assertContains(response, 'data-name-check-url=')
        self.assertContains(response, 'data-name-status')
        self.assertNotContains(self.client.get(reverse("login")), 'data-name-check-url=')
        self.client.force_login(User.objects.create_user("racer63"))
        self.assertNotContains(self.client.get(reverse("league:account_settings")), 'data-name-check-url=')
