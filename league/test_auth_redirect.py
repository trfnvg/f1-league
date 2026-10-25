from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class LoginRedirectTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("login-test", password="test-password")

    def test_authenticated_visitors_go_home_even_with_next(self):
        self.client.force_login(self.user)
        for suffix in ("", "?next=/accounts/login/", "?next=/ranking/"):
            with self.subTest(suffix=suffix):
                response = self.client.get(reverse("login") + suffix)
                self.assertRedirects(response, reverse("league:home"), fetch_redirect_response=False)

    def test_anonymous_visitors_can_still_log_in_and_return_to_destination(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse("login"), {
            "username": self.user.username,
            "password": "test-password",
            "next": "/ranking/",
        })
        self.assertRedirects(response, "/ranking/", fetch_redirect_response=False)
