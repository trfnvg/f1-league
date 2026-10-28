"""Repeatable synthetic benchmark; never opens the site's real database.

Run with the project's Python: python tests/profile_site.py
Times are local medians, not production latency or a concurrent load test.
"""
import os
from pathlib import Path
import statistics
import sys
from time import perf_counter
from datetime import timedelta
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from league.arcade_library import contest_rows
from league.leagues import import_legacy_league
from league.league_standings import standings
from league.models import ArcadeCompetition, DoodleAttempt, Event, Prediction, Result, Score, Season
from league.services import build_activity_feed, build_leaderboard


def measure(label, action):
    action()  # Warm up template/module caches outside the measured runs.
    elapsed = []
    for _ in range(5):
        start = perf_counter()
        action()
        elapsed.append((perf_counter() - start) * 1000)
    with CaptureQueriesContext(connection) as queries:
        with patch.object(Prediction, "from_db", wraps=Prediction.from_db) as predictions:
            with patch.object(DoodleAttempt, "from_db", wraps=DoodleAttempt.from_db) as attempts:
                action()
    print(f"{label}: median_ms={statistics.median(elapsed):.1f}, queries={len(queries)}, "
          f"prediction_models={predictions.call_count}, attempt_models={attempts.call_count}")


def main():
    call_command("migrate", verbosity=0, interactive=False)
    now = timezone.now()
    Season.objects.update_or_create(year=2026, defaults={"is_active": True})
    users = User.objects.bulk_create([User(username=f"perf{i:03}") for i in range(250)])
    events = Event.objects.bulk_create([
        Event(name=f"Synthetic GP {i + 1}", round_number=i + 1, season_year=2026,
              deadline=now - timedelta(days=24 - i), status=Event.Status.SCORED)
        for i in range(24)
    ])
    Score.objects.bulk_create([
        Score(user=user, event=event, points=(i * 7 + j) % 41)
        for i, user in enumerate(users) for j, event in enumerate(events)
    ])
    Prediction.objects.bulk_create([
        Prediction(user=user, event=event, p1="norris", p2="russell", p3="leclerc",
                   crazy_prediction="Synthetic prediction " * 20)
        for user in users for event in events
    ])
    Result.objects.bulk_create([
        Result(event=event, p1="norris", p2="russell", p3="leclerc", published_at=event.deadline)
        for event in events
    ])
    Prediction.objects.all().update(created_at=now - timedelta(days=30))
    league, _ = import_legacy_league(owner=users[0], season_year=2026, name="Synthetic League")
    contest = ArcadeCompetition.objects.create(
        event=events[-1], game_key="doodle_jump", opened_at=now - timedelta(days=2))
    DoodleAttempt.objects.bulk_create([
        DoodleAttempt(user=user, competition=contest, score=i * 100 + j,
                      finished_at=now - timedelta(days=1, minutes=1),
                      verification={"synthetic": "x" * 300})
        for i, user in enumerate(users) for j in range(40)
    ])
    DoodleAttempt.objects.all().update(started_at=now - timedelta(days=1, minutes=5))
    leaderboard = build_leaderboard(2026)
    client = Client()
    with override_settings(ALLOWED_HOSTS=["testserver"], STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }):
        measure("leaderboard_250_players_24_events", lambda: build_leaderboard(2026))
        measure("feed_6000_predictions", lambda: build_activity_feed(leaderboard))
        measure("contest_10000_attempts", lambda: contest_rows(contest))
        for label, url in (("home_guest", reverse("league:home")),
                           ("feed_poll_guest", reverse("league:activity_feed"))):
            def request(url=url):
                response = client.get(url)
                assert response.status_code == 200, response.status_code
            measure(label, request)
        client.force_login(users[0])
        measure("legacy_standings_6000_predictions", lambda: standings(league))
        for label, url in (("home_member", reverse("league:home")),
                           ("global_results", reverse("league:global_leaderboard")),
                           ("league_results", reverse("league:friend_league", args=[league.league_id]))):
            def request(url=url):
                response = client.get(url)
                assert response.status_code == 200, response.status_code
            measure(label, request)


if __name__ == "__main__":
    main()
