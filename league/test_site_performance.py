"""Performance invariants without flaky wall-clock thresholds or live data."""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, User
from django.db import connection
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .arcade_library import contest_rows
from .context_processors import league_context
from .competition_scoring import _text_digest
from .league_standings import standings
from .leagues import import_legacy_league
from .models import (ArcadeAttempt, ArcadeCompetition, DoodleAttempt, Event,
                     LeagueCrazyDecision, LeagueDayDecision, Prediction, Result, Score, Season)
from .services import build_activity_feed, build_leaderboard, get_selected_season


class RequestSeasonReuseTests(TestCase):
    def setUp(self):
        self.active, _ = Season.objects.update_or_create(year=2026, defaults={"is_active": True})
        self.archive = Season.objects.create(year=2025)

    def test_reuses_selection_only_within_one_request(self):
        request = RequestFactory().get("/", {"season": 2025})
        with self.assertNumQueries(2):
            self.assertEqual(get_selected_season(request), self.archive)
        with self.assertNumQueries(0):
            self.assertEqual(get_selected_season(request), self.archive)
        self.archive.is_active = True
        self.archive.save()
        self.assertEqual(get_selected_season(RequestFactory().get("/")), self.archive)

    def test_active_year_needs_no_second_season_lookup(self):
        for query in ({}, {"season": "2026"}, {"season": "invalid"}):
            with self.subTest(query=query), self.assertNumQueries(1):
                self.assertEqual(get_selected_season(RequestFactory().get("/", query)), self.active)
        self.assertEqual(get_selected_season(RequestFactory().get("/", {"season": "2024"})), self.active)

    def test_navigation_reuses_view_season_without_cross_request_cache(self):
        request = RequestFactory().get("/", {"season": "2025"})
        request.user = AnonymousUser()
        get_selected_season(request)
        with CaptureQueriesContext(connection) as queries:
            context = league_context(request)
        self.assertEqual(context["current_season"], self.archive)
        self.assertFalse(any('"league_season"' in query["sql"] for query in queries))


class BoundedStandingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.now = timezone.now()
        cls.users = [User.objects.create_user(f"perf{i}") for i in range(3)]
        cls.events = [Event.objects.create(
            name=f"Performance GP {i}", round_number=i + 1, season_year=2026,
            deadline=cls.now - timedelta(days=12 - i), status=Event.Status.SCORED,
        ) for i in range(6)]
        Score.objects.bulk_create([
            Score(user=user, event=event, points=10 + i + j)
            for i, event in enumerate(cls.events) for j, user in enumerate(cls.users)
        ])
        Prediction.objects.bulk_create([
            Prediction(user=user, event=event, p1="norris", p2="russell", p3="leclerc",
                       crazy_prediction="Do not load this body for the news feed")
            for user in cls.users for event in cls.events
        ])
        Result.objects.bulk_create([
            Result(event=event, p1="norris", p2="russell", p3="leclerc", published_at=event.deadline)
            for event in cls.events
        ])

    def test_leaderboard_does_not_hydrate_user_and_event_for_every_score(self):
        with patch.object(User, "from_db", wraps=User.from_db) as users:
            with patch.object(Event, "from_db", wraps=Event.from_db) as events:
                board = build_leaderboard(2026)
        self.assertEqual(users.call_count, len(self.users))
        self.assertEqual(events.call_count, len(self.events))
        self.assertEqual(len(board["scores"]), len(self.users) * len(self.events))
        self.assertEqual(board["rows"][0]["user"], self.users[-1])

    def test_home_can_reuse_calendar_without_changing_order_or_ranks(self):
        expected = build_leaderboard(2026)
        with CaptureQueriesContext(connection) as queries:
            actual = build_leaderboard(2026, events=list(reversed(self.events)))
        self.assertEqual(actual["events"], expected["events"])
        self.assertEqual(actual["rows"], expected["rows"])
        self.assertEqual(len(queries), 4)

    def test_feed_loads_only_latest_published_podium_and_keeps_records(self):
        # A newer unpublished score must not hide the previous GP's news.
        Result.objects.filter(event=self.events[-1]).update(published_at=None)
        board = build_leaderboard(2026)
        with CaptureQueriesContext(connection) as queries:
            with patch.object(Prediction, "from_db", wraps=Prediction.from_db) as predictions:
                feed = build_activity_feed(board, limit=30)
        self.assertEqual(predictions.call_count, len(self.users))
        self.assertEqual({item["source_event_id"] for item in feed}, {self.events[-2].pk})
        self.assertTrue({"record", "perfect-podium", "winner"} <= {item["type"] for item in feed})
        prediction_sql = [query["sql"] for query in queries if 'FROM "league_prediction"' in query["sql"]]
        self.assertEqual(len(prediction_sql), 1)
        self.assertNotIn('"crazy_prediction"', prediction_sql[0])

    def test_unpublished_season_never_loads_prediction_bodies(self):
        Result.objects.all().update(published_at=None)
        with patch.object(Prediction, "from_db", wraps=Prediction.from_db) as predictions:
            self.assertEqual(build_activity_feed(build_leaderboard(2026)), [])
        self.assertEqual(predictions.call_count, 0)

    def legacy_league(self):
        Season.objects.update_or_create(year=2026, defaults={"is_active": True})
        Prediction.objects.all().update(created_at=self.now - timedelta(days=30))
        return import_legacy_league(owner=self.users[0], season_year=2026, name="Performance League")[0]

    def test_legacy_standings_need_no_predictions_without_overrides(self):
        league = self.legacy_league()
        with patch.object(Prediction, "from_db", wraps=Prediction.from_db) as predictions:
            board = standings(league)
        self.assertEqual(predictions.call_count, 0)
        self.assertEqual(len(board["rows"]), len(self.users))
        for row in board["rows"]:
            self.assertEqual(row["total"], sum(s.points for s in Score.objects.filter(user=row["user"])))

    def test_legacy_overrides_load_only_relevant_predictions(self):
        league = self.legacy_league()
        event = self.events[-1]
        previous = self.events[-2]
        entry = league.entries.get(membership__user=self.users[0])
        prediction = Prediction.objects.get(user=self.users[0], event=event)
        LeagueCrazyDecision.objects.create(entry=entry, event=event, prediction=prediction,
            approved=True, text_digest=_text_digest(prediction), reviewed_by=self.users[0])
        Prediction.objects.filter(event=previous).update(driver_of_day="russell")
        LeagueDayDecision.objects.create(league_season=league, event=previous,
            drivers=["russell"], reviewed_by=self.users[0])
        with patch.object(Prediction, "from_db", wraps=Prediction.from_db) as predictions:
            board = standings(league)
        self.assertEqual(predictions.call_count, len(self.users) + 1)
        for row in board["rows"]:
            original = sum(s.points for s in Score.objects.filter(user=row["user"]))
            self.assertEqual(row["total"], original + 3 + (5 if row["user"] == self.users[0] else 0))
        # Editing the judged text invalidates the decision just as before.
        prediction.crazy_prediction = "Changed text"
        prediction.save(update_fields=["crazy_prediction"])
        board = standings(league)
        own = next(row for row in board["rows"] if row["user"] == self.users[0])
        self.assertEqual(own["total"], sum(s.points for s in Score.objects.filter(user=self.users[0])) + 3)

    @override_settings(STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    })
    def test_polled_fragment_matches_html_without_loading_page_context(self):
        season, _ = Season.objects.update_or_create(year=2026, defaults={"is_active": True})
        expected = render_to_string("activity_feed_items.html", {
            "season": season, "activity_feed": build_activity_feed(build_leaderboard(2026)),
        })
        with patch("league.context_processors.league_context", side_effect=AssertionError("unneeded page context")):
            response = self.client.get(reverse("league:activity_feed"), {"season": 2026})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["html"], expected)
        self.assertIn("no-store", response["Cache-Control"])

    def test_contest_query_selects_one_run_per_player_for_both_games(self):
        event = self.events[-1]
        event.deadline = self.now + timedelta(hours=1)
        event.save(update_fields=["deadline"])
        staff = User.objects.create_user("perfstaff", is_staff=True)
        inactive = User.objects.create_user("perfinactive", is_active=False)
        all_users = self.users + [staff, inactive]
        for key, model in (("flappy", ArcadeAttempt), ("doodle_jump", DoodleAttempt)):
            with self.subTest(game=key):
                contest = ArcadeCompetition.objects.create(
                    event=event, game_key=key, opened_at=self.now - timedelta(hours=1))
                attempts = model.objects.bulk_create([
                    model(user=user, competition=contest, score=score,
                          finished_at=self.now - timedelta(minutes=score), verification={"large": "x" * 1000})
                    for user in all_users for score in (10, 20, 20)
                ])
                model.objects.filter(pk__in=[a.pk for a in attempts]).update(started_at=self.now - timedelta(minutes=30))
                model.objects.create(user=self.users[0], competition=contest)  # Unfinished starts still count.
                model.objects.create(user=self.users[0], competition=contest, score=999,
                                     finished_at=event.deadline + timedelta(seconds=1))
                before = model.objects.create(user=self.users[0], competition=contest, score=1000,
                                              finished_at=self.now)
                model.objects.filter(pk=before.pk).update(started_at=contest.opened_at - timedelta(seconds=1))
                at_deadline = model.objects.create(user=self.users[0], competition=contest, score=2000,
                                                   finished_at=event.deadline)
                model.objects.filter(pk=at_deadline.pk).update(started_at=event.deadline)
                with self.assertNumQueries(2):
                    with patch.object(model, "from_db", wraps=model.from_db) as hydration:
                        rows, total = contest_rows(contest)
                self.assertEqual(hydration.call_count, 0)
                self.assertEqual([row["user_id"] for row in rows], [u.pk for u in self.users])
                self.assertEqual([row["score"] for row in rows], [20] * 3)
                self.assertEqual([row["rank"] for row in rows], [1, 2, 3])
                self.assertEqual(rows[0]["attempts"], 5)  # Finished late counts as a start, not a result.
                self.assertEqual(total, 14)  # Includes inactive starts; never staff starts.
                contest.delete()  # The event is one-to-one with a competition.
