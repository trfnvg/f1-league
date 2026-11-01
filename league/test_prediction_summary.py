from datetime import timedelta
from types import SimpleNamespace

from django.test import TestCase, override_settings
from django.urls import reverse

from . import test_private_league_ui as fixtures
from .driver_profiles import picker_profiles
from .models import DriverProfile, Prediction
from .prediction_summary import forecast_summary


@override_settings(STORAGES=fixtures.STORAGES)
class PredictionSummaryTests(TestCase):
    setUp = fixtures.PrivateLeagueUITests.setUp

    def test_summary_uses_event_roster_without_extra_queries_and_keeps_zero(self):
        DriverProfile.objects.create(season_year=self.event.season_year, key="russell",
            name="Джордж Рассел", surname="Рассел", number=63, team="Mercedes",
            portrait_url="https://example.invalid/current-season.webp")
        profiles = picker_profiles(self.event.season_year)
        prediction = Prediction(**{**self.values, "safety_car_count": 0, "dnf_count": 0})
        with self.assertNumQueries(0):
            summary = forecast_summary(prediction, self.event, profiles)
        self.assertEqual(summary["podium"][0]["driver"]["photo"], "https://example.invalid/current-season.webp")
        self.assertEqual([row["value"] for row in summary["counts"]], [0, 0])
        self.assertEqual(len(summary["weekend"]), 3)
        # A missing season profile must not borrow a different season's photo.
        self.assertEqual(summary["podium"][1]["driver"]["photo"], "")
        self.assertEqual(summary["podium"][1]["driver"]["surname"], "Леклер")

    def test_sprint_and_empty_answers_are_not_invented(self):
        event = SimpleNamespace(has_sprint=True)
        prediction = Prediction(p1="russell", safety_car_count=None, dnf_count=0)
        summary = forecast_summary(prediction, event, [])
        self.assertEqual(len(summary["weekend"]), 5)
        self.assertIsNone(summary["podium"][1]["driver"])
        self.assertEqual(summary["counts"][0]["value"], "—")
        self.assertEqual(summary["counts"][1]["value"], 0)
        self.assertFalse(forecast_summary(None, event, [])["podium"])

    def test_locked_forecast_has_portraits_and_escaped_text_without_changing_answers(self):
        DriverProfile.objects.create(season_year=self.event.season_year, key="russell",
            name="Джордж Рассел", surname="Рассел", number=63, team="Mercedes",
            portrait_url="https://example.invalid/russell.webp")
        prediction = Prediction.objects.create(user=self.owner, event=self.event, **self.values)
        self.clock.return_value = self.event.deadline + timedelta(minutes=1)
        before = Prediction.objects.filter(pk=prediction.pk).values().get()
        response = self.client.get(reverse("league:event_detail", args=[self.event.pk]))
        self.assertContains(response, 'class="stage-forecast"')
        self.assertContains(response, 'data-forecast-answer="p1"')
        self.assertContains(response, "data-driver-photo")
        self.assertContains(response, "https://example.invalid/russell.webp")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertEqual(Prediction.objects.filter(pk=prediction.pk).values().get(), before)

    def test_forecast_is_not_exposed_to_another_player_or_guest_before_deadline(self):
        Prediction.objects.create(user=self.owner, event=self.event,
            **{**self.values, "crazy_prediction": "PRIVATE-SUMMARY-ANSWER"})
        url = reverse("league:event_detail", args=[self.event.pk])
        self.client.force_login(self.player)
        page = self.client.get(url)
        self.assertIsNone(page.context["prediction"])
        self.assertFalse(page.context["prediction_summary"]["podium"])
        self.assertNotContains(page, "PRIVATE-SUMMARY-ANSWER")
        self.client.logout()
        self.assertNotContains(self.client.get(url), "PRIVATE-SUMMARY-ANSWER")
