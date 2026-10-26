import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .admin import EventAdminForm
from .circuits import CIRCUITS, resolve_circuit
from .leagues import create_league
from .models import Event, Season

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


class CircuitCatalogueTests(SimpleTestCase):
    def test_all_current_circuits_have_distinct_closed_finite_paths(self):
        self.assertEqual(len(CIRCUITS), 27)
        self.assertEqual(len({c["path"] for c in CIRCUITS.values()}), len(CIRCUITS))
        for key, circuit in CIRCUITS.items():
            with self.subTest(key=key):
                self.assertRegex(circuit["path"], r"^M[\d., L]+ Z$")
                points = re.findall(r"([\d.]+),([\d.]+)", circuit["path"])
                self.assertGreater(len(points), 15)
                self.assertTrue(all(0 <= float(x) <= 620 and 0 <= float(y) <= 370 for x, y in points))
                self.assertEqual((float(points[0][0]), float(points[0][1])), (circuit["start_x"], circuit["start_y"]))
                self.assertEqual([label["text"] for label in circuit["sector_labels"]], ["S1", "S2", "S3"])
                for label in [circuit["start_label"], *circuit["sector_labels"]]:
                    self.assertTrue(20 <= label["x"] <= 600 and 15 <= label["y"] <= 355)

    def test_existing_russian_and_english_cards_resolve_without_round_guesses(self):
        cases = {
            "Гран-при США": "austin", "Гран-при Мексики": "mexico",
            "FORMULA 1 LAS VEGAS GRAND PRIX": "las-vegas", "Гран-при Бразилии": "interlagos",
            "Гран-при Катара": "lusail", "Гран-при Абу-Даби": "yas-marina",
            "Гран-при Барселоны-Каталуньи": "barcelona", "Гран-при Испании": "madrid",
            "Гран-при Италии (Имола)": "imola", "Гран-при Бельгии": "spa",
            "Spanish Grand Prix": "madrid", "São Paulo Grand Prix": "interlagos",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(resolve_circuit(event_name=name, season_year=2026)["key"], expected)
        self.assertEqual(resolve_circuit(event_name="Spanish Grand Prix", season_year=2025)["key"], "barcelona")
        self.assertEqual(resolve_circuit("monaco", "Гран-при США")["key"], "monaco")
        self.assertIsNone(resolve_circuit(event_name="Наш особенный этап"))


@override_settings(STORAGES=STORAGES)
class CircuitEventTests(TestCase):
    def test_every_circuit_renders_full_roster_without_draw_animation(self):
        from django.template.loader import render_to_string
        for key, circuit in CIRCUITS.items():
            html = render_to_string("circuit_track.html", {"circuit":circuit, "track_id":key, "animated":True})
            self.assertEqual(html.count('class="circuit-car"'), 22)
            self.assertIn('data-racer="russell"', html)
            self.assertIn('data-racer="bottas"', html)
            self.assertNotIn('animateMotion', html)

    def setUp(self):
        self.now = timezone.now()
        self.season, _ = Season.objects.update_or_create(year=2026, defaults={"is_active": True})
        self.current = Event.objects.create(season_year=2026, name="Гран-при США", round_number=19,
            deadline=self.now-timedelta(hours=12), race_datetime=self.now+timedelta(hours=4))
        self.future = Event.objects.create(season_year=2026, name="Гран-при Мехико", round_number=20,
            deadline=self.now+timedelta(days=5), race_datetime=self.now+timedelta(days=7))

    def test_home_uses_current_race_track_after_prediction_deadline(self):
        with patch("league.views.timezone.now", return_value=self.now):
            response = self.client.get(reverse("league:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="circuit-path-home"')
        self.assertContains(response, 'data-circuit="austin"')
        self.assertContains(response, "До старта гонки")
        self.assertContains(response, 'class="circuit-car"', count=22)
        self.assertContains(response, 'league/circuit-peloton.js')
        self.assertNotContains(response, 'class="home-command')

    def test_admin_select_saves_circuit_and_fills_empty_name(self):
        form = EventAdminForm(data={"season_year": 2026, "round_number": 21,
            "name": "", "circuit": "interlagos", "deadline": self.now+timedelta(days=10),
            "status": Event.Status.OPEN})
        self.assertTrue(form.is_valid(), form.errors)
        event = form.save()
        self.assertEqual(event.name, "Гран-при Сан-Паулу")
        self.assertEqual(event.circuit_visual["key"], "interlagos")

    def test_custom_name_is_preserved_and_unknown_circuit_is_rejected(self):
        data = {"season_year": 2026, "round_number": 21, "name": "Наш бразильский этап",
            "circuit": "interlagos", "deadline": self.now+timedelta(days=10), "status": Event.Status.OPEN}
        form = EventAdminForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().name, data["name"])
        data["round_number"] = 22
        data["circuit"] = "invalid"
        self.assertIn("circuit", EventAdminForm(data=data).errors)

    def test_home_league_is_membership_scoped(self):
        owner = User.objects.create_user("owner")
        outsider = User.objects.create_user("outsider")
        create_league(owner=owner, name="Own league", season=self.season, start_event=self.future)
        create_league(owner=outsider, name="Private outsider league", season=self.season, start_event=self.future)
        self.client.force_login(owner)
        response = self.client.get(reverse("league:home"))
        self.assertContains(response, "Own league")
        self.assertNotContains(response, "Private outsider league")

    def test_admin_editor_contains_all_track_options_and_preview(self):
        admin = User.objects.create_superuser("track-admin", "admin@example.com", "test")
        self.client.force_login(admin)
        response = self.client.get(reverse("admin:league_event_add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-circuit-path", count=len(CIRCUITS))
        self.assertContains(response, "data-circuit-preview")
        self.assertContains(response, "admin-circuits.js")

    def test_global_ranking_remains_accessible_to_a_league_member(self):
        player = User.objects.create_user("ranked-player")
        create_league(owner=player, name="My league", season=self.season, start_event=self.future)
        self.client.force_login(player)
        response = self.client.get(reverse("league:global_leaderboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "leaderboard.html")

    def test_existing_card_editor_preselects_its_inferred_circuit(self):
        form = EventAdminForm(instance=self.current)
        self.assertEqual(form["circuit"].value(), "austin")
