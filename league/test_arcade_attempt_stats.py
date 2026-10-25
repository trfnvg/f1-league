from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from .models import ArcadeAttempt, ArcadeRecord, ArcadeSettings, Event, Season
from .arcade_library import selected_contest


class ArcadeAttemptStatsTests(TestCase):
    def setUp(self):
        now = timezone.now()
        event = Event.objects.create(
            season_year=Season.get_active().year,
            name="Attempt Stats GP",
            round_number=1,
            deadline=now + timedelta(days=14),
            race_datetime=now + timedelta(days=15),
        )
        ArcadeSettings.objects.update_or_create(
            pk=1,
            defaults={
                "active_game": ArcadeSettings.Game.FLAPPY,
                "public_enabled": True,
                "competition_event": event,
                "competition_opened_at": now - timedelta(minutes=1),
            },
        )
        self.user = User.objects.create_user(username="arcade-player", password="test-password")
        self.record = ArcadeRecord.objects.create(user=self.user, best_score=7)
        self.client.force_login(self.user)

    def test_started_runs_are_counted_and_return_live_leaderboard_data(self):
        start_url = reverse("league:arcade_run_start")

        first = self.client.post(start_url)
        second = self.client.post(start_url)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(ArcadeAttempt.objects.filter(user=self.user).count(), 2)
        self.record.refresh_from_db()
        self.assertEqual(self.record.total_attempts, 2)
        self.assertEqual(first.json()["attempts"], 1)
        self.assertEqual(second.json()["attempts"], 2)
        # A previous global record cannot enter a new contest without a finish.
        self.assertEqual(second.json()["records"], [])
        ArcadeAttempt.objects.filter(pk=first.json()["attempt_id"]).update(score=7, finished_at=timezone.now())
        board = self.client.get(reverse("league:arcade_leaderboard")).json()
        self.assertEqual(board["records"][0]["attempts"], 2)

    def test_leaderboard_api_includes_attempt_counts(self):
        _, contest = selected_contest()
        ArcadeAttempt.objects.create(user=self.user, competition=contest, score=7, finished_at=timezone.now())
        self.record.total_attempts = 1
        self.record.save(update_fields=("total_attempts",))

        response = self.client.get(reverse("league:arcade_leaderboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["records"][0]["attempts"], 1)
