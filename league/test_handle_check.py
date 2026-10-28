from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .auth_limits import bucket_key, consume
from .models import AuthRateBucket


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class HandleCheckTests(TestCase):
    def setUp(self):
        self.url = reverse("league:handle_check")

    def check(self, value, **extra):
        return self.client.post(self.url, {"handle": value}, **extra)

    def test_available_is_normalized_private_and_does_not_reserve_or_create_accounts(self):
        for value in ("racer63", "RACER63", " racer63 "):
            response = self.check(value)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {
                "available": True, "code": "available", "message": "Логин доступен."})
            self.assertIn("no-store", response["Cache-Control"])
            self.assertIn("private", response["Cache-Control"])
        self.assertFalse(User.objects.exists())

    def test_format_and_moderation_use_same_server_validator(self):
        for value, code in (("", "invalid_format"), ("ab", "invalid_format"),
                            ("a"*31, "invalid_format"), ("a"*2000, "invalid_format"),
                            ("ra_cer", "invalid_format"), ("@racer", "invalid_format"),
                            ("гонщик", "invalid_format"), ("putin63", "name_not_allowed"),
                            ("m0th3rfuck3r", "name_not_allowed")):
            with self.subTest(value=value):
                response = self.check(value)
                self.assertEqual(response.status_code, 200)
                self.assertIs(response.json()["available"], False)
                self.assertEqual(response.json()["code"], code)

    def test_taken_includes_legacy_names_and_handles_without_account_details(self):
        user = User.objects.create_user("Legacy63", email="private@example.com", first_name="Гриша")
        user.league_profile.handle = "current63"
        user.league_profile.save(update_fields=["handle"])
        for value in ("LEGACY63", "CURRENT63"):
            response = self.check(value)
            self.assertEqual(response.json()["code"], "handle_taken")
            self.assertIs(response.json()["available"], False)
            self.assertNotContains(response, "private@example.com")
            self.assertEqual(set(response.json()), {"available", "code", "message"})

    def test_settings_allow_own_unchanged_handle_but_not_somebody_elses(self):
        user = User.objects.create_user("putin63")  # Grandfathered account.
        User.objects.create_user("racer64")
        self.client.force_login(user)
        self.assertTrue(self.check("PUTIN63").json()["available"])
        self.assertEqual(self.check("putin64").json()["code"], "name_not_allowed")
        self.assertEqual(self.check("racer64").json()["code"], "handle_taken")
        self.assertTrue(self.check("racer65").json()["available"])
        self.assertEqual(User.objects.get(pk=user.pk).league_profile.handle, "putin63")

    def test_post_only_and_real_csrf_protection(self):
        self.assertEqual(self.client.get(self.url, {"handle": "racer63"}).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        self.assertEqual(strict.post(self.url, {"handle": "racer63"}).status_code, 403)
        strict.get(reverse("league:register"))
        token = strict.cookies["csrftoken"].value
        self.assertEqual(strict.post(self.url, {"handle": "racer63"}, HTTP_X_CSRFTOKEN=token).status_code, 200)
        self.assertEqual(strict.post(self.url, {"handle": "racer63"}, HTTP_X_CSRFTOKEN=token,
            HTTP_ORIGIN="https://evil.example").status_code, 403)

    @override_settings(AUTH_TRUSTED_PROXIES=[])
    def test_rate_limit_shared_across_handles_and_not_bypassed_by_forwarded_header(self):
        for number in range(60):
            self.assertEqual(self.check(f"racer{number}").status_code, 200)
        with patch("league.auth_views.clean_handle") as validate:
            response = self.check("other63", HTTP_X_FORWARDED_FOR="192.0.2.2")
        validate.assert_not_called()
        self.assertEqual(response.status_code, 429)
        self.assertIsNone(response.json()["available"])
        self.assertEqual(response.json()["code"], "rate_limited")
        self.assertGreater(int(response["Retry-After"]), 0)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(self.check("other63", REMOTE_ADDR="192.0.2.2").status_code, 200)
        # Buckets store a keyed hash, not the IP address or typed handle.
        self.assertTrue(all(len(key) == 64 for key in AuthRateBucket.objects.values_list("key", flat=True)))

    def test_hourly_limit_and_expiry(self):
        consume("handle-check-hour", "127.0.0.1", 600, 3600)
        key = bucket_key("handle-check-hour", "127.0.0.1")
        AuthRateBucket.objects.filter(pk=key).update(hits=600)
        self.assertEqual(self.check("racer63").status_code, 429)
        AuthRateBucket.objects.filter(pk=key).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.check("racer63").status_code, 200)

    def test_final_registration_rechecks_availability_without_relying_on_preview(self):
        self.assertTrue(self.check("racer63").json()["available"])
        User.objects.create_user("racer63")
        response = self.client.post(reverse("league:register"), {
            "first_name": "Гриша", "username": "racer63", "email": "new@example.com",
            "password1": "RaceStart!63", "password2": "RaceStart!63"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("username", response.context["form"].errors)
        self.assertEqual(User.objects.count(), 1)

    def test_final_registration_works_without_javascript_even_if_live_checks_are_limited(self):
        consume("handle-check-minute", "127.0.0.1", 60, 60)
        AuthRateBucket.objects.filter(pk=bucket_key("handle-check-minute", "127.0.0.1")).update(hits=60)
        self.assertEqual(self.check("racer63").status_code, 429)
        response = self.client.post(reverse("league:register"), {
            "first_name": "Гриша", "username": "racer63", "email": "new@example.com",
            "password1": "RaceStart!63", "password2": "RaceStart!63"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="racer63").exists())

    def test_only_registration_and_settings_opt_in_not_login(self):
        self.assertContains(self.client.get(reverse("league:register")), 'data-handle-check-url=')
        self.assertNotContains(self.client.get(reverse("login")), 'data-handle-check-url=')
        self.client.force_login(User.objects.create_user("racer63"))
        self.assertContains(self.client.get(reverse("league:account_settings")), 'data-handle-check-url=')
