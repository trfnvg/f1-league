import re
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import RegisterForm
from .identity import display_name


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    SITE_URL="https://fastlap.ru",
    STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
              "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
)
class AccountTests(TestCase):
    def setUp(self):
        cache.clear()
        self.data = dict(first_name="Гриша", username="racer63", email="racer@example.com",
                         password1="RaceStart!63", password2="RaceStart!63")

    def test_registration_keeps_name_separate_and_accepts_same_public_names(self):
        response = self.client.post(reverse("league:register"), self.data)
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="racer63")
        self.assertEqual(display_name(user), "Гриша")
        self.assertEqual(user.league_profile.handle, "racer63")
        self.assertEqual(user.email, "racer@example.com")
        self.assertTrue(user.check_password("RaceStart!63"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.client.logout()
        self.assertEqual(self.client.post(reverse("league:register"),
            {**self.data, "username": "racer64", "email": "other@example.com"}).status_code, 302)

    def test_admin_shows_and_searches_current_handle_separately_from_legacy_username(self):
        admin = User.objects.create_superuser('admin63', 'admin@example.com', 'RaceStart!63')
        player = User.objects.create_user('legacy-player', first_name='Гриша', email='player@example.com')
        profile = player.league_profile
        profile.handle = 'racefan63'
        profile.save(update_fields=['handle'])
        self.client.force_login(admin)
        for term in ('racefan63', '@racefan63'):
            response = self.client.get(reverse('admin:auth_user_changelist'), {'q': term})
            self.assertEqual(response.status_code, 200)
            self.assertEqual([u.pk for u in response.context['cl'].result_list], [player.pk])
            self.assertContains(response, '@racefan63')
            self.assertContains(response, 'Гриша')
        response = self.client.get(reverse('admin:auth_user_change', args=[player.pk]))
        self.assertContains(response, '@racefan63')
        self.assertContains(response, 'legacy-player')
        response = self.client.get(reverse('admin:league_userprofile_changelist'), {'q': '@racefan63'})
        self.assertEqual([p.pk for p in response.context['cl'].result_list], [profile.pk])
        self.assertContains(response, '@racefan63')

    def test_handle_rejects_special_symbols_unicode_spaces_and_bad_lengths(self):
        for handle in ("ra.cer", "ra_cer", "ra-cer", "ra cer", "@racer", "racer🔥", "гонщик", "ab", "a"*31):
            with self.subTest(handle=handle):
                form = RegisterForm({**self.data, "username": handle})
                self.assertFalse(form.is_valid())
                self.assertIn("username", form.errors)

    def test_handle_uniqueness_is_case_insensitive_and_reserves_legacy_names(self):
        user = User.objects.create_user("RACER63")
        user.league_profile.handle = "different63"
        user.league_profile.save(update_fields=["handle"])
        form = RegisterForm(self.data)
        self.assertFalse(form.is_valid())
        self.assertIn("username", form.errors)
        form = RegisterForm({**self.data, "username": "DIFFERENT63"})
        self.assertFalse(form.is_valid())
        self.assertIn("username", form.errors)

    def test_database_prevents_case_variant_handles(self):
        first = User.objects.create_user("first63")
        second = User.objects.create_user("second63")
        with self.assertRaises(IntegrityError), transaction.atomic():
            second.league_profile.handle = first.league_profile.handle.upper()
            second.league_profile.save(update_fields=["handle"])

    def test_password_confirmation_email_and_name_are_required(self):
        for changes, field in [({"password2": "OtherRace!63"}, "password2"),
            ({"password1": "tiny", "password2": "tiny"}, "password1"),
            ({"email": ""}, "email"), ({"first_name": "Гриша<script>"}, "first_name")]:
            with self.subTest(changes=changes):
                form = RegisterForm({**self.data, **changes})
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_email_uniqueness_and_normalization(self):
        User.objects.create_user("existing63", email="RACER@example.com")
        self.assertIn("email", RegisterForm(self.data).errors)
        form = RegisterForm({**self.data, "email": "NEW@Example.com", "username": "NewRacer"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["email"], "new@example.com")
        self.assertEqual(form.cleaned_data["username"], "newracer")

    def test_handle_and_legacy_login_both_work_and_inactive_accounts_do_not(self):
        user = User.objects.create_user("Гриша", password="RaceStart!63")
        handle = user.league_profile.handle
        for value in ("Гриша", handle.upper(), "@"+handle):
            self.assertEqual(authenticate(username=value, password="RaceStart!63"), user)
        self.assertIsNone(authenticate(username="@"+handle, password="wrong"))
        user.is_active = False
        user.save(update_fields=["is_active"])
        self.assertIsNone(authenticate(username="@"+handle, password="RaceStart!63"))

    def test_registration_rejects_external_next_redirect(self):
        response = self.client.post(reverse("league:register"), {**self.data, "next": "//evil.example/"})
        self.assertRedirects(response, reverse("league:home"), fetch_redirect_response=False)

    def test_existing_names_passwords_and_ids_survive_handle_migration(self):
        users = [User.objects.create_user(name, password="RaceStart!63")
                 for name in ("Гриша", "a.b", "ab", "Abc", "ABC")]
        original = [(u.pk, u.username, u.password) for u in users]
        import_module("league.migrations.0051_player_handles").assign_handles(apps, SimpleNamespace(connection=connection))
        handles = []
        for user, before in zip(users, original):
            user.refresh_from_db()
            self.assertEqual((user.pk, user.username, user.password), before)
            self.assertEqual(display_name(user), user.username)
            handles.append(user.league_profile.handle)
        self.assertEqual(len(handles), len(set(handles)))
        self.assertTrue(all(re.fullmatch(r"[a-z0-9]{3,30}", h) for h in handles))

    def test_account_settings_require_password_and_preserve_name(self):
        user = User.objects.create_user("Гриша", password="RaceStart!63")
        self.client.force_login(user)
        url = reverse("league:account_settings")
        response = self.client.post(url, {"handle": "newhandle", "email": "new@example.com", "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.email, "")
        response = self.client.post(url, {"handle": "newhandle", "email": "new@example.com", "password": "RaceStart!63"})
        self.assertRedirects(response, url, fetch_redirect_response=False)
        user.refresh_from_db()
        self.assertEqual(user.email, "new@example.com")
        self.assertEqual(user.league_profile.handle, "newhandle")
        self.assertEqual(display_name(user), "Гриша")
        self.assertEqual(authenticate(username="@newhandle", password="RaceStart!63"), user)

    def test_mail_recovery_complete_token_one_use_and_no_account_enumeration(self):
        user = User.objects.create_user("reset63", email="reset@example.com", password="OldRace!63")
        reset = reverse("password_reset")
        response = self.client.post(reset, {"email": "missing@example.com"})
        self.assertRedirects(response, reverse("password_reset_done"), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 0)
        response = self.client.post(reset, {"email": user.email}, HTTP_HOST="evil.example")
        self.assertRedirects(response, reverse("password_reset_done"), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [user.email])
        link = re.search(r"https://fastlap\.ru(/accounts/reset/\S+)", mail.outbox[0].body).group(1)
        response = self.client.get(link)
        confirm = response.url
        self.assertEqual(self.client.get(confirm).status_code, 200)
        response = self.client.post(confirm, {"new_password1": "NewRace!63", "new_password2": "NewRace!63"})
        self.assertRedirects(response, reverse("password_reset_complete"), fetch_redirect_response=False)
        user.refresh_from_db()
        self.assertTrue(user.check_password("NewRace!63"))
        self.assertIsNone(authenticate(username="reset63", password="OldRace!63"))
        self.assertFalse(self.client.get(link).context["validlink"])

    def test_recovery_repeats_are_throttled_and_missing_smtp_is_explicit(self):
        user = User.objects.create_user("reset63", email="reset@example.com", password="RaceStart!63")
        for _ in range(3):
            self.client.post(reverse("password_reset"), {"email": user.email})
        self.assertEqual(len(mail.outbox), 1)
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST=""):
            response = self.client.post(reverse("password_reset"), {"email": user.email})
            self.assertContains(response, "временно недоступно")

    def test_public_views_show_name_and_profile_shows_handle(self):
        form = RegisterForm(self.data)
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        response = self.client.get(reverse("league:player_profile", args=[user.pk]))
        self.assertContains(response, "<h1>Гриша</h1>", html=True)
        self.assertContains(response, "@racer63")
