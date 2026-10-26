from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .driver_profiles import picker_profiles
from .models import DRIVER_CHOICES, DriverProfile


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class DriverProfilesTests(TestCase):
    def test_season_roster_covers_all_prediction_choices(self):
        profiles = picker_profiles(2026)
        self.assertEqual({driver["key"] for driver in profiles}, {key for key, _ in DRIVER_CHOICES})
        self.assertEqual(len({driver["number"] for driver in profiles}), 22)
        self.assertTrue(all('/2026/' in driver['photo'] for driver in profiles))
        self.assertTrue(all('g_face,w_440,h_440' in driver['photo'] for driver in profiles))

    def test_profiles_are_public_and_season_specific(self):
        driver = DriverProfile.objects.get(season_year=2026, key="russell")
        DriverProfile.objects.create(season_year=2027, key="russell", name=driver.name,
                                     surname=driver.surname, number=63, team="Другая команда")
        response = self.client.get(reverse("league:driver_profile", args=(2026, "russell")))
        self.assertContains(response, "Mercedes")
        self.assertNotContains(response, "Другая команда")
        self.assertEqual(self.client.get(reverse("league:driver_profile", args=(2025, "russell"))).status_code, 404)
        self.assertContains(self.client.get(reverse("league:drivers")+'?season=2026'), "Джордж Рассел")

    def test_uploaded_portrait_takes_precedence(self):
        driver = DriverProfile.objects.get(season_year=2026, key="russell")
        driver.portrait = "driver_portraits/russell.webp"
        self.assertEqual(driver.photo_url, "/media/driver_portraits/russell.webp")

    def test_picker_team_accents_follow_profile_team_not_driver(self):
        profiles = {driver["key"]: driver for driver in picker_profiles(2026)}
        self.assertEqual(profiles["russell"]["team_color"], "#62dfcd")
        self.assertEqual(profiles["leclerc"]["team_color"], "#ff8585")
        self.assertEqual(profiles["norris"]["team_color"], "#ffad61")
        for driver in profiles.values():
            self.assertRegex(driver["team_color"], r"^#[0-9a-f]{6}$")
            self.assertNotEqual(driver["team_color"], "#b5c0ce")
        DriverProfile.objects.filter(season_year=2026, key="russell").update(team=" McLaren ")
        self.assertEqual(next(d for d in picker_profiles(2026) if d["key"] == "russell")["team_color"], "#ffad61")
        DriverProfile.objects.filter(season_year=2026, key="russell").update(team="Новая команда")
        self.assertEqual(next(d for d in picker_profiles(2026) if d["key"] == "russell")["team_color"], "#b5c0ce")

    def test_staff_can_manage_driver_profiles(self):
        admin = User.objects.create_superuser("drivers-admin", "drivers@example.com", "test")
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse("admin:league_driverprofile_changelist")).status_code, 200)
