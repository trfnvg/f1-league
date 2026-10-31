from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .leagues import create_league
from .models import Event, Prediction, Season, SeasonPrediction, UserProfile
from .prediction_submission import save_shared_prediction


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class RaceNavigationTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.season, _ = Season.objects.update_or_create(year=2026, defaults={"is_active": True})
        self.player = User.objects.create_user("driver")
        self.current = Event.objects.create(name="Гран-при США", round_number=19, season_year=2026,
            deadline=self.now-timedelta(hours=12), race_datetime=self.now-timedelta(hours=1))
        self.future = Event.objects.create(name="Гран-при Мехико", round_number=20, season_year=2026,
            deadline=self.now+timedelta(days=50), race_datetime=self.now+timedelta(days=51))
        self.client.force_login(self.player)
        self.data = dict(p1="russell", p2="leclerc", p3="norris", pole="russell",
            fastest_lap="russell", driver_of_day="russell", safety_car_count=1, dnf_count=2)

    def test_card_opens_immediately_even_months_before_the_race(self):
        self.assertEqual(self.future.voting_state(), "open")
        response = self.client.get(reverse("league:event_detail", args=[self.future.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="card event-hero-card event-stage-hero')
        self.assertContains(response, 'name="p1"')
        self.assertNotContains(response, "за 7 дней")
        form, saved = save_shared_prediction(user=self.player, event=self.future, data=self.data)
        self.assertIsNotNone(saved, form.errors)
        self.assertEqual(saved.p1, "russell")

    def test_templates_do_not_emit_bom_before_document_doctype(self):
        # A BOM in both the child and base templates becomes rendered text before
        # <!doctype>, moving <head> into <body> and enabling quirks layout.
        templates = Path(__file__).parent / "templates"
        for template in templates.rglob("*.html"):
            with self.subTest(template=template.relative_to(templates)):
                self.assertFalse(template.read_bytes().startswith(b"\xef\xbb\xbf"))
        for url in (reverse("league:home"), reverse("league:event_detail", args=[self.current.pk]),
                    reverse("league:event_detail", args=[self.future.pk]), reverse("league:global_leaderboard")):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertTrue(response.content.lstrip().lower().startswith(b"<!doctype html>"))

    def test_league_forecast_is_editable_immediately_and_remains_closed_after_deadline(self):
        league = create_league(owner=self.player, name="Future league", season=self.season, start_event=self.future)
        url = reverse("league:friend_league_event", args=[league.league_id, self.future.pk])
        response = self.client.get(url)
        self.assertTrue(response.context["editable"])
        response = self.client.post(url, self.data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Prediction.objects.filter(user=self.player, event=self.future).exists())
        with patch("django.utils.timezone.now", return_value=self.future.deadline):
            self.assertEqual(self.future.voting_state(), "closed")
            response = self.client.post(url, {**self.data, "p1": "hamilton"})
        self.assertEqual(Prediction.objects.get(user=self.player, event=self.future).p1, "russell")

    def test_current_race_is_shared_by_home_navigation_and_league(self):
        # Start the league from the current race while it is still open, then
        # inspect it one hour into the race.
        with patch("django.utils.timezone.now", return_value=self.current.deadline-timedelta(hours=1)):
            league = create_league(owner=self.player, name="Current league", season=self.season, start_event=self.current)
        for delta, expected in ((timedelta(), self.current), (timedelta(hours=1, seconds=1), self.future)):
            with patch("django.utils.timezone.now", return_value=self.now+delta):
                home = self.client.get(reverse("league:home"))
                detail = self.client.get(reverse("league:friend_league", args=[league.league_id]))
            self.assertEqual(home.context["featured_event"], expected)
            self.assertEqual(home.context["current_event"], expected)
            self.assertEqual(detail.context["next_event"], expected)
            self.assertEqual(detail.context["current_event"], expected)

    def test_sidebar_renders_real_avatar_and_navigation_has_no_season_tab(self):
        profile, _ = UserProfile.objects.get_or_create(user=self.player)
        profile.avatar = "avatars/driver.png"
        profile.save(update_fields=["avatar"])
        response = self.client.get(reverse("league:home"))
        self.assertContains(response, 'src="/media/avatars/driver.png"')
        self.assertContains(response, 'class="fl-wordmark"')
        self.assertNotContains(response, "fastlap<span>.</span>")
        self.assertNotContains(response, 'href="'+reverse("league:season_predictions")+'"')
        self.assertNotContains(response, 'class="ns-mini-bars"')
        self.assertNotContains(response, 'class="ns-progress"')

    def test_profile_keeps_season_prediction_privacy(self):
        self.season.predictions_deadline = self.now+timedelta(days=1)
        self.season.save(update_fields=["predictions_deadline"])
        SeasonPrediction.objects.create(user=self.player, season_year=2026, world_drivers_champion="russell", hadjar_best_finish=4)
        url = reverse("league:player_profile", args=[self.player.pk])
        own = self.client.get(url)
        self.assertContains(own, 'id="season-predictions"')
        self.assertEqual(len(own.context["season_cards"]), 1)
        self.client.force_login(User.objects.create_user("visitor"))
        other = self.client.get(url)
        self.assertTrue(other.context["season_prediction_hidden"])
        self.assertEqual(other.context["season_cards"], [])
