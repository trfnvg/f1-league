from datetime import timedelta
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Event, Season


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.items = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.items.append(dict(attrs))


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class PredictionNavigationTests(TestCase):
    def setUp(self):
        Season.objects.update_or_create(year=2026, defaults={"is_active": True})
        self.event = Event.objects.create(name="Navigation GP", season_year=2026, round_number=1,
            deadline=timezone.now() + timedelta(days=2), race_datetime=timezone.now() + timedelta(days=3))
        self.target = reverse("league:event_detail", args=[self.event.pk])
        self.user = User.objects.create_user("navigation-racer", password="TestRacePassword!63")

    def forecast_links(self, response):
        links = [item["href"] for item in Links(response.content.decode()).items if "data-prediction-nav" in item]
        self.assertEqual(len(links), 3)  # Desktop sidebar, mobile drawer, bottom navigation.
        return links

    def test_guest_forecast_navigation_opens_login_with_return_destination(self):
        response = self.client.get(reverse("league:home"))
        for href in self.forecast_links(response):
            parsed = urlsplit(href)
            self.assertEqual(parsed.path, reverse("login"))
            self.assertEqual(parse_qs(parsed.query), {"next": [self.target]})
        login = self.client.get(self.forecast_links(response)[0])
        self.assertContains(login, "Вход в аккаунт")
        self.assertContains(login, f'name="next" value="{self.target}"')

    def test_authenticated_forecast_navigation_goes_directly_to_event(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("league:home"))
        self.assertEqual(self.forecast_links(response), [self.target] * 3)

    def test_login_returns_to_forecast_and_registration_preserves_destination(self):
        home = self.client.get(reverse("league:home"))
        login_url = self.forecast_links(home)[0]
        response = self.client.get(login_url)
        register_links = [item["href"] for item in Links(response.content.decode()).items
                          if item.get("href", "").startswith(reverse("league:register") + "?")]
        self.assertEqual(len(register_links), 1)
        self.assertEqual(parse_qs(urlsplit(register_links[0]).query), {"next": [self.target]})
        response = self.client.post(login_url, {"username": self.user.username,
            "password": "TestRacePassword!63", "next": self.target})
        self.assertRedirects(response, self.target, fetch_redirect_response=False)

    def test_mobile_drawer_starts_with_home_for_guests_and_players(self):
        for authenticated in (False, True):
            if authenticated:
                self.client.force_login(self.user)
            html = self.client.get(reverse("league:calendar")).content.decode()
            drawer = html.split('<div class="offcanvas-body">', 1)[1].split('<div class="menu-divider">', 1)[0]
            links = Links(drawer).items
            self.assertEqual(links[0]["href"], reverse("league:home"))
            self.assertIn("Главная", drawer[:drawer.index("</a>")])
            self.assertIn("data-prediction-nav", links[1])

    def test_no_current_event_has_a_safe_login_fallback(self):
        self.event.delete()
        response = self.client.get(reverse("league:home"))
        for href in self.forecast_links(response):
            self.assertEqual(urlsplit(href).path, reverse("login"))
            self.assertEqual(parse_qs(urlsplit(href).query), {"next": [reverse("league:home") + "#calendar"]})

    def test_calendar_and_direct_event_preview_remain_public(self):
        self.assertEqual(self.client.get(reverse("league:calendar")).status_code, 200)
        self.assertEqual(self.client.get(self.target).status_code, 200)
