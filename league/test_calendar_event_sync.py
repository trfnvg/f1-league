from datetime import date, datetime, timedelta, timezone as dt_timezone
from importlib import import_module
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse

from .calendar_event_sync import sync_calendar_events_v1, thursday_deadline
from .models import Event, Prediction, RaceCalendarRound
from .prediction_submission import save_shared_prediction


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class CalendarEventSyncTests(TestCase):
    def test_all_calendar_rounds_get_cards_and_links_idempotently(self):
        report = sync_calendar_events_v1(2026)
        self.assertEqual(report["created"], 23)
        self.assertEqual(report["linked"], 23)
        self.assertEqual(report["conflicts"], [])
        self.assertEqual(Event.objects.filter(season_year=2026).count(), 23)
        for race in RaceCalendarRound.objects.select_related("prediction_event"):
            event = race.prediction_event
            self.assertEqual(event.season_year, race.season_year)
            self.assertEqual(event.round_number, race.round_number)
            self.assertEqual(event.race_datetime, race.race_at)
            self.assertEqual(event.has_sprint, race.has_sprint)
            self.assertEqual(event.deadline, thursday_deadline(race.starts_on))
            self.assertEqual(event.qualifying_datetime, race.qualifying_at + timedelta(hours=1))
            event.full_clean()
        self.assertEqual(sync_calendar_events_v1(2026)["created"], 0)
        self.assertEqual(Event.objects.count(), 23)

    def test_thursday_deadlines_are_moscow_time_including_vegas(self):
        for weekend, expected in ((date(2026, 10, 30), date(2026, 10, 29)),
                                  (date(2026, 11, 19), date(2026, 11, 19))):
            value = thursday_deadline(weekend)
            self.assertEqual(value.date(), expected)
            self.assertEqual((value.hour, value.minute), (23, 59))
            self.assertEqual(value.utcoffset(), timedelta(hours=3))
        sync_calendar_events_v1(2026)
        vegas = RaceCalendarRound.objects.get(circuit="las-vegas")
        self.assertLess(vegas.prediction_event.deadline, vegas.practice1_at)

    def test_existing_cards_photos_deadlines_and_predictions_are_untouched(self):
        user = User.objects.create_user("existing-predictor")
        event = Event.objects.create(season_year=2026, round_number=19, name="Мой Мехико", circuit="mexico",
            deadline=datetime(2026, 10, 29, 19, tzinfo=dt_timezone.utc), status="locked",
            race_datetime=datetime(2026, 11, 1, 21, tzinfo=dt_timezone.utc),
            cover_image="event_covers/my-mexico.png", has_sprint=True)
        prediction = Prediction.objects.create(user=user, event=event, p1="russell")
        before = Event.objects.values().get(pk=event.pk)
        report = sync_calendar_events_v1(2026)
        self.assertEqual(report["created"], 22)
        self.assertEqual(Event.objects.values().get(pk=event.pk), before)
        self.assertEqual(RaceCalendarRound.objects.get(circuit="mexico").prediction_event_id, event.pk)
        self.assertEqual(Prediction.objects.get(pk=prediction.pk).p1, "russell")

    def test_identity_uses_circuit_never_overwrites_an_unrelated_round(self):
        event = Event.objects.create(season_year=2026, round_number=1, name="Monaco", circuit="monaco",
            deadline=datetime(2026, 6, 4, tzinfo=dt_timezone.utc))
        report = sync_calendar_events_v1(2026)
        event.refresh_from_db()
        self.assertEqual(event.round_number, 1)
        self.assertEqual(RaceCalendarRound.objects.get(circuit="monaco").prediction_event_id, event.pk)
        self.assertIsNone(RaceCalendarRound.objects.get(circuit="melbourne").prediction_event_id)
        self.assertEqual(len(report["conflicts"]), 1)

    def test_deployment_backfills_an_existing_prediction_season(self):
        first = Event.objects.create(season_year=2026, round_number=1, name="Мельбурн, Австралия",
            deadline=datetime(2026, 3, 5, tzinfo=dt_timezone.utc))
        migration = import_module("league.migrations.0062_calendar_prediction_events_and_arcade_plans")
        migration.backfill_prediction_events(apps, SimpleNamespace(connection=connection))
        self.assertEqual(Event.objects.count(), 23)
        self.assertEqual(RaceCalendarRound.objects.get(circuit="melbourne").prediction_event_id, first.pk)

    def test_future_cards_accept_predictions_immediately_and_lock_at_deadline(self):
        sync_calendar_events_v1(2026)
        user = User.objects.create_user("whole-season-predictor")
        self.client.force_login(user)
        early = datetime(2026, 1, 1, tzinfo=dt_timezone.utc)
        data = dict(p1="russell", p2="leclerc", p3="norris", pole="russell",
            fastest_lap="russell", driver_of_day="russell", safety_car_count=0, dnf_count=0)
        with patch("django.utils.timezone.now", return_value=early):
            for race in RaceCalendarRound.objects.select_related("prediction_event"):
                event = race.prediction_event
                self.assertEqual(event.voting_state(), "open")
                response = self.client.get(reverse("league:event_detail", args=[event.pk]))
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.context["is_locked"])
            abu_dhabi = Event.objects.get(circuit="yas-marina")
            form, saved = save_shared_prediction(user=user, event=abu_dhabi, data=data)
            self.assertIsNotNone(saved, form.errors)
        with patch("django.utils.timezone.now", return_value=abu_dhabi.deadline):
            self.assertEqual(abu_dhabi.voting_state(), "closed")

    def test_command_is_explicit_and_only_affects_requested_season(self):
        output = StringIO()
        call_command("sync_calendar_events", season=2026, stdout=output)
        self.assertIn("Создано: 23", output.getvalue())
        self.assertFalse(Event.objects.exclude(season_year=2026).exists())
        self.assertNotContains(self.client.get(reverse("league:home")), 'id="calendar"')
        page = self.client.get(reverse("league:calendar"))
        self.assertEqual(sum(bool(row.linked_event) for row in page.context["calendar_rounds"]), 23)
