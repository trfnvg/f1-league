"""These tests MUST execute on PostgreSQL in CI; SQLite cannot prove row locks."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from threading import Barrier

from django.contrib.auth.models import User
from django.db import close_old_connections, connections
from django.test import Client, TransactionTestCase, skipUnlessDBFeature, override_settings
from django.urls import reverse
from django.utils import timezone

from .auth_limits import bucket_key, consume
from .models import AuthRateBucket, DoodleAttempt, DoodleRecord


@skipUnlessDBFeature("has_select_for_update")
@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class PostgreSQLConcurrencyTests(TransactionTestCase):
    def parallel(self, actions):
        barrier = Barrier(len(actions))

        def worker(action):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return action()
            finally:
                # CONN_MAX_AGE=600 otherwise keeps fresh thread-local connections
                # alive and makes Django's DROP of the test DB flaky.
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(actions)) as pool:
            return list(pool.map(worker, actions))

    def test_rate_limit_cannot_be_exceeded_by_parallel_requests(self):
        key = bucket_key("concurrent-test", "synthetic")
        AuthRateBucket.objects.create(key=key, hits=0, expires_at=timezone.now()+timedelta(minutes=1))
        results = self.parallel([lambda: consume("concurrent-test", "synthetic", 3, 60) for _ in range(8)])
        self.assertEqual(results.count(0), 3)
        self.assertEqual(AuthRateBucket.objects.get(pk=key).hits, 3)

    def clients(self):
        user = User.objects.create_user("concurrency63")
        first = Client()
        first.force_login(user)
        # Identical session, just like concurrent requests from one browser.
        second = Client()
        second.cookies = first.cookies.copy()
        return user, first, second

    def test_parallel_finishes_save_exactly_one_result(self):
        user, first, second = self.clients()
        run = first.post(reverse("league:doodle_attempt_start")).json()
        body = json.dumps({"attempt_id": run["attempt_id"], "run_token": run["run_token"], "score": 10})
        def finish(client):
            return client.post(reverse("league:doodle_attempt_finish"), data=body,
                               content_type="application/json").status_code
        results = self.parallel([lambda: finish(first), lambda: finish(second)])
        self.assertEqual(sorted(results), [200, 409])
        self.assertEqual(DoodleAttempt.objects.filter(user=user, score=10).count(), 1)
        self.assertEqual(DoodleRecord.objects.get(user=user).best_score, 10)
        self.assertEqual(DoodleRecord.objects.get(user=user).total_attempts, 1)

    def test_parallel_starts_leave_only_one_active_attempt(self):
        user, first, second = self.clients()
        url = reverse("league:doodle_attempt_start")
        results = self.parallel([lambda: first.post(url).status_code, lambda: second.post(url).status_code])
        self.assertEqual(results, [200, 200])
        self.assertEqual(DoodleAttempt.objects.filter(user=user, finished_at__isnull=True).count(), 1)
        self.assertEqual(DoodleRecord.objects.get(user=user).total_attempts, 2)
