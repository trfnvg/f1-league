from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import ArcadeAttempt, ArcadeRecord


class ArcadeAttemptStatsTests(TestCase):
    def setUp(self):
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
        self.assertEqual(second.json()["records"][0]["attempts"], 2)

    def test_leaderboard_api_includes_attempt_counts(self):
        ArcadeAttempt.objects.create(user=self.user)
        self.record.total_attempts = 1
        self.record.save(update_fields=("total_attempts",))

        response = self.client.get(reverse("league:arcade_leaderboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["records"][0]["attempts"], 1)
