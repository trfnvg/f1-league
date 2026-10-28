
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .forms import AccountSettingsForm, RegisterForm
from .identity import clean_handle
from .name_moderation import DATA, _rules, validate_public_name


class NamePolicyTests(SimpleTestCase):
    def test_upstream_words_transliterations_and_disguises_are_rejected(self):
        for value in ("fuck", "FUCK63", "f u c k", "Fúck", "fuuuck", "m0th3rfuck3r", "sh1t",
                      "fuckingracer", "racerfuck", "motherfucker", "bitch63", "asshole", "shithead",
                      "пизда", "ПИЗДЕЦ", "п и з д а", "рizda", "pi3da", "p1zd4", "пиздюк", "долбоеб", "долбоёб",
                      "сука", "блядь", "blyat", "хуй", "хyй", "хyи", "хуесос", "eblan63", "MaxEbetVsehVokrug",
                      "siegheil", "heilhitler", "whitepower", "neonazi", "nazi1488", "зиг хайль",
                      "putin", "Putin63", "realputin", "putinfan63", "Vladimir Putin", "Владимир Путин",
                      "рutin", "trump", "DonaldTrump", "Трамп", "biden", "zelenskyy", "Hitler", "Адольф Гитлер"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validate_public_name(value)

    def test_regular_names_racing_names_and_ambiguous_numbers_are_allowed(self):
        for value in ("Гриша", "Анна", "Аня", "Никита", "Семён", "Семен", "Semen", "Semen63", "Semyon",
                      "Аналитик", "Analyst", "Natalia", "Владимир", "Александр", "Дональд", "Джозеф", "Ким",
                      "Dick", "Лолита", "Lolita", "Fanny", "Willie", "Willy", "Gaylord", "Cummings",
                      "Scunthorpe", "Arsenal", "ScuderiaFerrari", "Esteban", "EstebanOcon31", "Эстебан Окон",
                      "GeorgeRussell63", "Макс Ферстаппен", "MaxEtVsehVokrug", "Тит",
                      "Rasputin", "Trumpeter", "pilot88", "racer1488", "f1fan63", "fastlapfan", "racer63"):
            with self.subTest(value=value):
                validate_public_name(value)

    def test_regex_is_cached_bounded_and_never_fetches_data_at_runtime(self):
        _rules.cache_clear()
        validate_public_name("Гриша")
        with self.assertRaises(ValidationError):
            validate_public_name("a"*151)
        first = _rules()
        for _ in range(100):
            validate_public_name("EstebanOcon31")
        self.assertIs(first, _rules())
        self.assertTrue((DATA/"NOTICE.md").is_file())
        self.assertIn("Attribution 4.0 International", (DATA/"LICENSE-CC-BY-4.0.txt").read_text())


@override_settings(STORAGES={"default":{"BACKEND":"django.core.files.storage.FileSystemStorage"},
    "staticfiles":{"BACKEND":"django.contrib.staticfiles.storage.StaticFilesStorage"}})
class NameModerationAccountTests(TestCase):
    def setUp(self):
        self.data = dict(first_name="Гриша", username="racer63", email="racer@example.com",
            password1="RaceStart!63", password2="RaceStart!63")

    def test_registration_rejects_prohibited_handle_and_name_without_creating_account(self):
        for field, value in (("username","fuck63"),("username","putin63"),("first_name","Владимир Путин"),
                             ("first_name","Хуесос"),("first_name","Адольф Гитлер")):
            with self.subTest(field=field):
                response = self.client.post(reverse("league:register"), {**self.data,field:value})
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)
                self.assertContains(response, "не соответствует правилам Fastlap")
        self.assertFalse(User.objects.exists())

    def test_invalid_new_handle_does_not_update_email_or_handle(self):
        user = User.objects.create_user("racer63", email="old@example.com", password="RaceStart!63")
        self.client.force_login(user)
        response = self.client.post(reverse("league:account_settings"), {
            "handle":"putin63", "email":"new@example.com", "password":"RaceStart!63"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("handle", response.context["form"].errors)
        user.refresh_from_db()
        self.assertEqual(user.email, "old@example.com")
        self.assertEqual(user.league_profile.handle, "racer63")

    def test_profile_clean_rejects_a_new_bad_handle(self):
        user = User.objects.create_user("racer63")
        user.league_profile.handle = "fuck63"
        with self.assertRaises(ValidationError):
            user.league_profile.full_clean()

    def test_existing_login_and_unchanged_handle_are_not_blocked_by_new_policy(self):
        user = User.objects.create_user("putin63", password="RaceStart!63", email="old@example.com")
        self.assertEqual(authenticate(username="@putin63", password="RaceStart!63"), user)
        self.assertEqual(clean_handle("putin63", user), "putin63")
        form = AccountSettingsForm({"handle":"putin63", "email":"new@example.com", "password":"RaceStart!63"}, user=user)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(user.league_profile.handle, "putin63")
        with self.assertRaises(ValidationError):
            clean_handle("putin64", user)

    def test_ordinary_registration_still_succeeds(self):
        form = RegisterForm({**self.data, "username":"estebanocon31", "first_name":"Семён"})
        self.assertTrue(form.is_valid(), form.errors)
