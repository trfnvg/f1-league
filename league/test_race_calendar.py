from datetime import datetime, timedelta, timezone as dt_timezone
import hashlib
import importlib
import json
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse

from .calendar_assets import calendar_photos
from .calendar_globe import COORDINATES, globe_rounds
from .models import Event, EventPhoto, Prediction, RaceCalendarRound, Season
from .race_calendar import calendar_rows


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class RaceCalendarTests(TestCase):
    now = datetime(2026, 10, 28, 12, tzinfo=dt_timezone.utc)

    def get_page(self, **query):
        with patch("league.race_calendar.timezone.now", return_value=self.now):
            return self.client.get(reverse("league:calendar"), query)

    def test_frozen_snapshot_contains_actual_2026_calendar(self):
        rounds = list(RaceCalendarRound.objects.filter(season_year=2026))
        self.assertEqual(len(rounds), 23)
        self.assertEqual([r.round_number for r in rounds], list(range(1, 24)))
        self.assertEqual(sum(r.has_sprint for r in rounds), 6)
        self.assertEqual(rounds[15].circuit, "sepang")
        for race in rounds:
            with self.subTest(circuit=race.circuit):
                race.full_clean()
                self.assertIsNotNone(race.practice1_at)
                self.assertIsNotNone(race.race_at)
                self.assertEqual(race.checked_on.isoformat(), "2026-10-29")

    def test_calendar_is_public_with_links_in_navigation(self):
        response = self.get_page()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["calendar_rounds"]), 23)
        self.assertContains(response, "Гоночный календарь")
        self.assertContains(response, 'href="/calendar/"', count=4)
        self.assertContains(response, 'data-calendar-round', count=23)
        self.assertContains(response, 'nightshift-mobile-nav')

    def test_dates_are_moscow_time_on_server_without_javascript(self):
        response = self.get_page()
        self.assertContains(response, "30.10 · 21:30")  # Mexico FP1 = 18:30 UTC.
        self.assertContains(response, "01.11 · 23:00")  # Mexico GP = 20:00 UTC.
        self.assertContains(response, "22.11 · 07:00")  # Vegas: Sunday MSK, Saturday at the circuit.
        self.assertContains(response, "МСК")

    def test_timezone_setting_does_not_change_the_server_default(self):
        with override_settings(TIME_ZONE="America/Los_Angeles"):
            self.assertContains(self.get_page(), "01.11 · 23:00")

    def test_race_remains_current_for_two_hours(self):
        mexico = RaceCalendarRound.objects.get(circuit="mexico", season_year=2026)
        for offset, expected in ((-1, "mexico"), (0, "interlagos"), (1, "interlagos")):
            with self.subTest(offset=offset):
                _, next_race = calendar_rows(2026, mexico.race_at + timedelta(hours=2, seconds=offset))
                self.assertEqual(next_race.circuit, expected)

    def test_unknown_hours_are_not_replaced_by_fake_midnight(self):
        RaceCalendarRound.objects.filter(circuit="mexico").update(practice1_at=None, race_at=None)
        response = self.get_page()
        self.assertContains(response, "Время уточняется")
        self.assertEqual(response.context["calendar_next"].circuit, "mexico")
        vegas = RaceCalendarRound.objects.get(circuit="las-vegas")
        RaceCalendarRound.objects.filter(pk=vegas.pk).update(race_at=None)
        _, next_race = calendar_rows(2026, datetime(2026, 11, 22, 7, tzinfo=dt_timezone.utc))
        self.assertEqual(next_race.circuit, "las-vegas")  # Still Nov 21 at the venue.

    def test_predictions_link_by_circuit_not_round_number(self):
        misleading = Event.objects.create(name="Monaco", circuit="monaco", season_year=2026,
            round_number=19, deadline=self.now + timedelta(days=2))
        correct = Event.objects.create(name="Mexico", circuit="mexico", season_year=2026,
            round_number=99, deadline=self.now + timedelta(days=3))
        Event.objects.create(name="Mexico next season", circuit="mexico", season_year=2027,
            round_number=1, deadline=self.now + timedelta(days=100))
        response = self.get_page()
        self.assertEqual(response.context["calendar_next"].linked_event.pk, correct.pk)
        self.assertContains(response, reverse("league:event_detail", args=[correct.pk]))
        self.assertNotEqual(response.context["calendar_next"].linked_event.pk, misleading.pk)

    def test_ambiguous_prediction_event_requires_explicit_link(self):
        for i in (1, 2):
            Event.objects.create(name=f"Mexico {i}", circuit="mexico", season_year=2026,
                round_number=i, deadline=self.now + timedelta(days=3))
        self.assertIsNone(self.get_page().context["calendar_next"].linked_event)
        event = Event.objects.first()
        RaceCalendarRound.objects.filter(circuit="mexico").update(prediction_event=event)
        self.assertEqual(self.get_page().context["calendar_next"].linked_event.pk, event.pk)

    def test_page_does_not_create_prediction_events_or_change_deadlines(self):
        before = (Event.objects.count(), Prediction.objects.count(), Season.objects.count())
        self.get_page()
        self.assertEqual((Event.objects.count(), Prediction.objects.count()), before[:2])
        event = Event.objects.create(name="Existing GP", circuit="mexico", season_year=2026,
            round_number=19, deadline=self.now + timedelta(minutes=19))
        deadline = event.deadline
        self.get_page()
        event.refresh_from_db()
        self.assertEqual(event.deadline, deadline)

    def test_year_input_is_bounded_and_falls_back(self):
        for value in ("abc", "1 OR 1=1", "9999999999999999999999999", "2027"):
            with self.subTest(value=value):
                response = self.get_page(season=value)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["calendar_year"], 2026)

    def test_empty_and_finished_seasons_have_clear_state(self):
        self.now = datetime(2026, 12, 20, tzinfo=dt_timezone.utc)
        self.assertContains(self.get_page(), "Сезон завершён")
        RaceCalendarRound.objects.all().delete()
        self.assertContains(self.get_page(), "Календарь готовится")

    def test_calendar_data_queries_are_constant(self):
        with self.assertNumQueries(2):
            rounds, next_race = calendar_rows(2026, self.now)
        self.assertEqual(len(rounds), 23)
        self.assertEqual(next_race.circuit, "mexico")

    def test_images_are_local_and_have_valid_attribution(self):
        photos = calendar_photos()
        circuits = set(RaceCalendarRound.objects.values_list("circuit", flat=True))
        self.assertEqual(set(photos), circuits)
        root = Path(__file__).parent / "static"
        for circuit, photo in photos.items():
            with self.subTest(circuit=circuit):
                image = (root / photo["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(image).hexdigest(), photo["sha256"])
                self.assertTrue(image.startswith(b"\xff\xd8"))
                self.assertTrue(photo["author"])
                self.assertTrue(photo["license"].startswith("CC BY") or photo["license"] in ("CC0", "Public domain"))
                self.assertTrue(photo["license_url"].startswith(("https://creativecommons.org/", "http://creativecommons.org/")))
                self.assertTrue(photo["source_url"].startswith("https://commons.wikimedia.org/wiki/File:"))
        self.assertContains(self.get_page(), "Фотографии и источники")

    def test_admin_checks_timezone_dates_and_cross_season_links(self):
        race = RaceCalendarRound.objects.get(circuit="mexico")
        race.venue_timezone = "wrong/zone"
        with self.assertRaises(ValidationError):
            race.full_clean()
        race.venue_timezone = "America/Mexico_City"
        race.prediction_event = Event.objects.create(name="Future GP", season_year=2027,
            round_number=1, deadline=self.now + timedelta(days=100))
        with self.assertRaises(ValidationError):
            race.full_clean()
        race.prediction_event = None
        race.race_at = self.now - timedelta(days=200)
        with self.assertRaises(ValidationError):
            race.full_clean()

    def test_seed_is_idempotent_and_keeps_manual_schedule_edits(self):
        from django.apps import apps
        module = importlib.import_module("league.migrations.0059_seed_race_calendar")
        race = RaceCalendarRound.objects.get(circuit="mexico")
        race.race_at += timedelta(minutes=30)
        race.save(update_fields=["race_at"])
        # Only the connection alias is used; no schema operation is needed.
        from types import SimpleNamespace
        module.seed_calendar(apps, SimpleNamespace(connection=connection))
        self.assertEqual(RaceCalendarRound.objects.count(), 23)
        race.refresh_from_db()
        self.assertEqual(race.race_at.hour, 20)
        self.assertEqual(race.race_at.minute, 30)

    def test_calendar_is_read_only_for_public_users_and_admin_can_edit(self):
        self.assertEqual(self.client.post(reverse("league:calendar")).status_code, 405)
        admin = User.objects.create_superuser("calendaradmin", password="test")
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse("admin:league_racecalendarround_changelist")).status_code, 200)

    def test_full_official_weekends_have_exactly_five_real_sessions(self):
        rounds, _ = calendar_rows(2026, self.now)
        for race in rounds:
            with self.subTest(circuit=race.circuit):
                race.full_clean()
                expected = ["FP1", "SQ", "SPR", "Q", "GP"] if race.has_sprint else ["FP1", "FP2", "FP3", "Q", "GP"]
                self.assertEqual([row["code"] for row in race.session_rows], expected)
                times = [row["at"] for row in race.session_rows]
                self.assertTrue(all(times))
                self.assertEqual(times, sorted(times))
        self.assertContains(self.get_page(), 'data-calendar-session=', count=120)  # 23 cards + hero, five each.

    def test_qualifying_and_sprint_times_are_displayed_in_moscow(self):
        response = self.get_page()
        self.assertContains(response, "Практика 2")
        self.assertContains(response, "Практика 3")
        self.assertContains(response, "Квалификация к спринту")
        self.assertContains(response, "31.10 · 01:00")  # Mexico FP2 crosses midnight in MSK.
        self.assertContains(response, "31.10 · 20:30")  # Mexico FP3.
        self.assertContains(response, "01.11 · 00:00")  # Mexico qualifying.

    def test_uploaded_event_cover_used_in_card_and_feature_without_copy(self):
        event = Event.objects.create(name="Мехико", circuit="mexico", season_year=2026, round_number=19,
            deadline=self.now + timedelta(days=2), cover_image="event_covers/my-mexico.png")
        response = self.get_page()
        self.assertEqual(response.context["calendar_next"].cover_url, event.cover_image.url)
        self.assertContains(response, event.cover_image.url, count=3)  # Hero, card and globe JSON.
        self.assertFalse(response.context["calendar_next"].uses_stock_photo)
        self.assertEqual(len(list(response.context["calendar_credits"])), 22)
        RaceCalendarRound.objects.filter(circuit="mexico").update(cover_image="calendar_covers/override.png")
        response = self.get_page()
        self.assertContains(response, "/calendar_covers/override.png", count=3)

    def test_globe_covers_every_round_without_extra_database_queries(self):
        rounds, _ = calendar_rows(2026, self.now)
        with self.assertNumQueries(0):
            globe = globe_rounds(rounds)
        self.assertEqual(len(globe), 23)
        self.assertEqual(len({race['key'] for race in globe}), 23)
        self.assertEqual([race['round'] for race in globe], list(range(1, 24)))
        self.assertEqual([race['key'] for race in globe if race['next']], ['mexico'])
        for race in globe:
            with self.subTest(circuit=race['key']):
                self.assertTrue(-90 <= race['lat'] <= 90)
                self.assertTrue(-180 <= race['lon'] <= 180)
                self.assertEqual(len(race['sessions']), 5)
                self.assertTrue(race['cover'].startswith('/static/'))
                self.assertTrue(race['url'].startswith('https://www.formula1.com/'))
                self.assertTrue(race['external'])

    def test_globe_uses_existing_event_links_covers_and_session_data(self):
        event = Event.objects.create(name='Mexico', circuit='mexico', season_year=2026,
            round_number=19, deadline=self.now + timedelta(days=3), cover_image='event_covers/existing.jpg')
        response = self.get_page()
        mexico = next(race for race in response.context['globe_rounds'] if race['key'] == 'mexico')
        self.assertEqual(mexico['cover'], event.cover_image.url)
        self.assertEqual(mexico['url'], reverse('league:event_detail', args=[event.pk]))
        self.assertFalse(mexico['external'])
        self.assertTrue(mexico['track'])
        self.assertEqual([s['code'] for s in mexico['sessions']], ['FP1', 'FP2', 'FP3', 'Q', 'GP'])
        self.assertEqual(mexico['raceAt'], response.context['calendar_next'].race_at.isoformat())

    def test_globe_handles_unknown_coordinates_hours_and_escaped_names(self):
        malicious = '</script><script>alert(1)</script>'
        RaceCalendarRound.objects.filter(circuit='mexico').update(location=malicious, race_at=None)
        response = self.get_page()
        payload = response.content.decode().split('id="calendar-globe-data" type="application/json">')[1].split('</script>')[0]
        parsed = json.loads(payload)
        mexico = next(race for race in parsed if race['key'] == 'mexico')
        self.assertEqual(mexico['location'], malicious)
        self.assertIsNone(mexico['raceAt'])
        self.assertNotIn('<script>', payload)
        rounds, _ = calendar_rows(2026, self.now)
        with patch.dict(COORDINATES, {}, clear=True):
            self.assertEqual(globe_rounds(rounds), [])

    def test_globe_textures_are_small_local_jpegs_with_attribution(self):
        from PIL import Image
        folder = Path(__file__).parent / 'static/league/images/globe'
        for filename in ('earth-day.jpg', 'earth-night.jpg'):
            with Image.open(folder / filename) as image:
                self.assertEqual(image.format, 'JPEG')
                self.assertEqual(image.width, image.height * 2)
            self.assertLess((folder / filename).stat().st_size, 500_000)
        self.assertIn('CC BY 4.0', (folder / 'ATTRIBUTION.md').read_text())

    def test_old_uploaded_gallery_photo_is_used_if_cover_missing(self):
        event = Event.objects.create(name="Мехико", circuit="mexico", season_year=2026, round_number=19,
            deadline=self.now + timedelta(days=2))
        photo = EventPhoto.objects.create(event=event, image="event_photos/my-old-cover.jpg")
        self.assertEqual(self.get_page().context["calendar_next"].cover_url, photo.image.url)

    def test_uploaded_covers_never_leak_from_different_seasons(self):
        Event.objects.create(name="Мехико 2027", circuit="mexico", season_year=2027, round_number=19,
            deadline=self.now + timedelta(days=400), cover_image="event_covers/future.png")
        self.assertTrue(self.get_page().context["calendar_next"].uses_stock_photo)

    def test_gallery_cover_queries_do_not_grow_per_card(self):
        for number, circuit in enumerate(("mexico", "monaco", "shanghai"), 1):
            event = Event.objects.create(name=circuit, circuit=circuit, season_year=2026,
                round_number=number, deadline=self.now + timedelta(days=2))
            EventPhoto.objects.create(event=event, image=f"event_photos/{circuit}.jpg")
        with self.assertNumQueries(3):
            rounds, _ = calendar_rows(2026, self.now)
        self.assertEqual(sum(bool(race.cover_url) for race in rounds), 3)

    def test_session_seed_does_not_overwrite_manually_edited_hours(self):
        from django.apps import apps
        from types import SimpleNamespace
        seed = importlib.import_module("league.migrations.0061_seed_calendar_weekend_sessions").seed_sessions
        race = RaceCalendarRound.objects.get(circuit="mexico")
        custom = race.qualifying_at + timedelta(minutes=30)
        race.qualifying_at = custom
        race.save(update_fields=["qualifying_at"])
        seed(apps, SimpleNamespace(connection=connection))
        race.refresh_from_db()
        self.assertEqual(race.qualifying_at, custom)

    def test_session_validation_rejects_wrong_order_and_wrong_format(self):
        race = RaceCalendarRound.objects.get(circuit="mexico")
        race.qualifying_at = race.practice1_at - timedelta(minutes=30)
        with self.assertRaises(ValidationError):
            race.full_clean()
        race.refresh_from_db()
        race.sprint_at = race.practice3_at
        with self.assertRaises(ValidationError):
            race.full_clean()
