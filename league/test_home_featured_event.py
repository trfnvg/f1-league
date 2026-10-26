from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .home_events import select_featured_event
from .models import Event, Season

MSK = ZoneInfo("Europe/Moscow")


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class HomeFeaturedEventTests(TestCase):
    def setUp(self):
        Season.objects.update_or_create(year=2026, defaults={"is_active": True})
        self.race = datetime(2026, 10, 25, 22, tzinfo=MSK)
        self.current = Event.objects.create(name="Current GP", round_number=19,
            season_year=2026, deadline=self.race-timedelta(days=2), race_datetime=self.race)
        self.next = Event.objects.create(name="Already created next GP", round_number=20,
            season_year=2026, deadline=self.race+timedelta(days=5), race_datetime=self.race+timedelta(days=7))

    def home_at(self, now):
        with patch("league.views.timezone.now", return_value=now):
            response = self.client.get(reverse("league:home"))
        self.assertEqual(response.status_code, 200)
        return response

    def test_league_creation_ctas_only_appear_for_guests_with_or_without_events(self):
        player = User.objects.create_user("home-player")
        for empty_calendar in (False, True):
            if empty_calendar:
                Event.objects.all().delete()
            self.client.logout()
            self.assertContains(self.home_at(self.race), "Создать лигу")
            self.client.force_login(player)
            self.assertNotContains(self.home_at(self.race), "Создать лигу")

    def test_closed_deadline_keeps_current_gp_and_prediction_deadline_is_not_reopened(self):
        now = self.race-timedelta(days=1)
        response = self.home_at(now)
        self.assertEqual(response.context["featured_event"], self.current)
        self.assertFalse(response.context["featured_is_upcoming"])
        self.assertEqual(select_featured_event([self.next, self.current], now), self.current)

    def test_scored_race_stays_until_the_two_hour_boundary(self):
        self.current.status = Event.Status.SCORED
        self.current.save(update_fields=["status"])
        self.assertEqual(self.home_at(self.race+timedelta(hours=2)-timedelta(seconds=1)).context["featured_event"], self.current)
        self.assertEqual(self.home_at(self.race+timedelta(hours=2)).context["featured_event"], self.next)

    def test_race_start_plus_two_hours_switches_to_next_gp(self):
        self.assertEqual(self.home_at(self.race).context["featured_event"], self.current)
        self.assertEqual(self.home_at(self.race+timedelta(hours=2)-timedelta(microseconds=1)).context["featured_event"], self.current)
        self.assertEqual(self.home_at(self.race+timedelta(hours=2)).context["featured_event"], self.next)

    def test_sidebar_and_mobile_navigation_keep_the_same_gp_after_predictions_close(self):
        for now in (self.race-timedelta(hours=1), self.race+timedelta(hours=1)):
            response = self.home_at(now)
            self.assertEqual(response.context["current_event"], self.current)
            self.assertEqual(response.context["featured_event"], self.current)
        self.assertEqual(self.home_at(self.race+timedelta(hours=2)).context["current_event"], self.next)

    def test_missing_race_uses_prediction_deadline_as_fallback(self):
        self.current.race_datetime = None
        self.current.save(update_fields=["race_datetime"])
        self.assertEqual(select_featured_event([self.next, self.current], self.current.deadline-timedelta(seconds=1)), self.current)
        self.assertEqual(select_featured_event([self.next, self.current], self.race), self.next)

    def test_locked_predictions_do_not_hide_upcoming_race(self):
        self.current.status = Event.Status.LOCKED
        self.current.save(update_fields=["status"])
        response = self.home_at(self.race-timedelta(hours=2))
        self.assertEqual(response.context["featured_event"], self.current)
        self.assertTrue(response.context["featured_race_upcoming"])
        self.assertFalse(response.context["featured_is_upcoming"])
        self.assertContains(response, "До старта гонки")

    def test_empty_archive_and_upcoming_fallbacks(self):
        self.assertIsNone(select_featured_event([], self.race))
        self.assertEqual(select_featured_event([self.next, self.current], self.race-timedelta(days=20)), self.current)
        self.assertEqual(select_featured_event([self.current, self.next], self.race+timedelta(days=60)), self.next)

    def test_home_respects_selected_season(self):
        Season.objects.update_or_create(year=2025, defaults={"is_active": False})
        old = Event.objects.create(name="Archive final", round_number=24, season_year=2025,
            deadline=datetime(2025, 12, 5, tzinfo=MSK))
        with patch("league.views.timezone.now", return_value=self.race):
            response = self.client.get(reverse("league:home"), {"season": 2025})
        self.assertEqual(response.context["featured_event"], old)
