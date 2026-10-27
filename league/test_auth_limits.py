from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from .auth_limits import bucket_key, client_address, consume
from .models import AuthRateBucket


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
              "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
)
class AuthLimitTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="legacy-name", email="driver@example.com", password="safe-password-63")
        self.user.league_profile.handle = "driver63"
        self.user.league_profile.save()

    def attempt(self, username="@driver63", **extra):
        return self.client.post("/accounts/login/", {"username": username, "password": "wrong"}, **extra)

    def test_five_attempts_then_block_before_password_hashing(self):
        for _ in range(5):
            self.assertEqual(self.attempt().status_code, 200)
        with patch("django.contrib.auth.models.User.check_password") as check:
            response = self.attempt()
        check.assert_not_called()
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)
        self.assertContains(response, "Слишком много попыток", status_code=429)

    def test_aliases_and_admin_share_limits(self):
        for username in ["@driver63", "DRIVER63", "legacy-name", "@DRIVER63", "driver63"]:
            self.attempt(username)
        response = self.client.post("/admin/login/", {"username": "legacy-name", "password": "wrong"})
        self.assertEqual(response.status_code, 429)

    def test_expiry_and_blocked_requests_do_not_extend_lock(self):
        self.assertEqual(consume("test", "secret", 1, 60), 0)
        key = bucket_key("test", "secret")
        expiry = AuthRateBucket.objects.get(pk=key).expires_at
        self.assertGreater(consume("test", "secret", 1, 60), 0)
        self.assertEqual(AuthRateBucket.objects.get(pk=key).expires_at, expiry)
        AuthRateBucket.objects.filter(pk=key).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(consume("test", "secret", 1, 60), 0)
        self.assertEqual(AuthRateBucket.objects.get(pk=key).hits, 1)

    def test_success_clears_account_and_pair_not_ip(self):
        self.attempt()
        response = self.client.post("/accounts/login/", {"username": "@driver63", "password": "safe-password-63"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(AuthRateBucket.objects.filter(pk=bucket_key("login-account", f"user:{self.user.pk}")).exists())
        self.assertEqual(AuthRateBucket.objects.get(pk=bucket_key("login-ip", "127.0.0.1")).hits, 2)

    def test_account_limit_across_addresses(self):
        for number in range(20):
            self.assertEqual(self.attempt(REMOTE_ADDR=f"192.0.2.{number + 1}").status_code, 200)
        self.assertEqual(self.attempt(REMOTE_ADDR="192.0.2.100").status_code, 429)

    def test_shared_wifi_other_user_not_locked(self):
        for _ in range(6):
            self.attempt()
        self.assertEqual(self.attempt("another-user").status_code, 200)

    def test_ip_limit_and_cache_restart_cannot_bypass(self):
        from django.core.cache import cache
        consume("login-ip", "127.0.0.1", 1, 900)
        AuthRateBucket.objects.filter(pk=bucket_key("login-ip", "127.0.0.1")).update(hits=120)
        cache.clear()
        with patch("django.contrib.auth.models.User.check_password") as check:
            self.assertEqual(self.attempt("a-new-account").status_code, 429)
        check.assert_not_called()
        self.assertEqual(self.attempt("a-new-account", REMOTE_ADDR="192.0.2.10").status_code, 200)

    def test_ipv6_privacy_addresses_share_a_network(self):
        factory = RequestFactory()
        first = client_address(factory.get("/", REMOTE_ADDR="2001:db8:1:2::1"))
        second = client_address(factory.get("/", REMOTE_ADDR="2001:db8:1:2::9999"))
        self.assertEqual(first, second)

    def test_recovery_known_and_unknown_have_same_response_and_limits(self):
        for email in ["driver@example.com", "absent@example.com"]:
            for _ in range(3):
                response = self.client.post("/accounts/password_reset/", {"email": email})
                self.assertRedirects(response, "/accounts/password_reset/done/", fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        # Clear cooldowns only, simulating separate minutes within the same hour.
        for _ in range(4):
            AuthRateBucket.objects.filter(pk=bucket_key("reset-email-minute", "driver@example.com")).delete()
            self.client.post("/accounts/password_reset/", {"email": "DRIVER@example.com"})
        self.assertEqual(len(mail.outbox), 3)

    def test_recovery_ip_limit_counts_invalid_and_unknown_emails(self):
        for _ in range(20):
            self.client.post("/accounts/password_reset/", {"email": "invalid"})
        response = self.client.post("/accounts/password_reset/", {"email": "driver@example.com"})
        self.assertEqual(response.status_code, 429)
        self.assertFalse(hasattr(mail, "outbox") and mail.outbox)

    def test_forwarded_headers_cannot_bypass_default(self):
        request = RequestFactory().get("/", REMOTE_ADDR="192.0.2.1", HTTP_X_FORWARDED_FOR="198.51.100.1")
        self.assertEqual(client_address(request), "192.0.2.1")
        with override_settings(AUTH_TRUSTED_PROXIES=["192.0.2.0/24"]):
            self.assertEqual(client_address(request), "198.51.100.1")
            request.META["HTTP_X_FORWARDED_FOR"] = "spoofed, 198.51.100.1"
            self.assertEqual(client_address(request), "198.51.100.1")

    def test_csrf_still_required_and_get_not_limited(self):
        from django.test import Client
        self.assertEqual(Client(enforce_csrf_checks=True).post("/accounts/login/", {}).status_code, 403)
        for _ in range(25):
            self.assertEqual(self.client.get("/accounts/login/").status_code, 200)
        self.assertEqual(AuthRateBucket.objects.count(), 0)
