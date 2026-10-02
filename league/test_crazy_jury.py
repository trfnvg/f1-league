from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .crazy_jury import (
    CrazyVoteError,
    cast_crazy_prediction_vote,
    crazy_vote_is_open,
    vetoed_crazy_prediction_id,
)
from .models import CrazyPredictionVote, DuelChallenge, Event, Prediction, Result, Season
from .scoring import _build_event_score_rows
from .services import build_activity_feed, build_leaderboard


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def make_prediction(user, event, crazy_text):
    return Prediction.objects.create(
        user=user,
        event=event,
        p1="norris",
        p2="piastri",
        p3="russell",
        pole="norris",
        safety_car_count=1,
        dnf_count=1,
        crazy_prediction=crazy_text,
    )


@override_settings(STORAGES=TEST_STORAGES)
class CrazyJuryTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.season = Season.get_active()
        self.event = Event.objects.create(
            season_year=self.season.year,
            name="Test Grand Prix",
            round_number=1,
            deadline=self.now - timedelta(minutes=30),
            race_datetime=self.now + timedelta(hours=2),
        )
        self.owner_a = User.objects.create_user("owner-a", password="test")
        self.owner_b = User.objects.create_user("owner-b", password="test")
        self.voter = User.objects.create_user("voter", password="test")
        self.prediction_a = make_prediction(self.owner_a, self.event, "Test crazy idea Alpha")
        self.prediction_b = make_prediction(self.owner_b, self.event, "Test crazy idea Bravo")

    def test_vote_window_is_only_after_deadline_before_race(self):
        self.assertTrue(crazy_vote_is_open(self.event, self.now))
        self.assertFalse(crazy_vote_is_open(self.event, self.event.deadline - timedelta(seconds=1)))
        self.assertFalse(crazy_vote_is_open(self.event, self.event.race_datetime))

    def test_home_vote_is_anonymous_and_author_mapping_is_hidden_during_vote(self):
        self.client.force_login(self.voter)
        home = self.client.get(reverse("league:home"))
        self.assertContains(home, "Test crazy idea Alpha")
        self.assertContains(home, "Test crazy idea Bravo")
        self.assertNotIn("user_id", str(home.context["crazy_jury"]["candidates"]))
        self.assertNotIn(self.owner_a.username, str(home.context["crazy_jury"]["candidates"]))
        self.assertNotIn(self.owner_b.username, str(home.context["crazy_jury"]["candidates"]))

        event_page = self.client.get(reverse("league:event_detail", args=(self.event.id,)))
        self.assertTrue(event_page.context["crazy_vote_open"])
        self.assertNotContains(event_page, "Test crazy idea Alpha")
        self.assertNotContains(event_page, "Test crazy idea Bravo")
        self.assertNotContains(event_page, "Голоса за Crazy Prediction")

        profile = self.client.get(reverse("league:player_profile", args=(self.owner_a.id,)))
        self.assertContains(profile, "Скрыто до завершения анонимного голосования")
        self.assertNotContains(profile, "Test crazy idea Alpha")

    def test_admin_audit_shows_voter_and_target_but_is_forbidden_to_players(self):
        CrazyPredictionVote.objects.create(
            event=self.event,
            voter=self.voter,
            target_prediction=self.prediction_a,
        )
        url = reverse("league:paddock_jury_admin")

        self.client.force_login(self.voter)
        denied = self.client.get(url)
        self.assertEqual(denied.status_code, 403)

        admin = User.objects.create_superuser("jury-admin", "admin@example.com", "test")
        self.client.force_login(admin)
        response = self.client.get(url, {"event": self.event.id})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test crazy idea Alpha")
        self.assertContains(response, "Автор прогноза: ")
        self.assertContains(response, self.owner_a.username)
        self.assertContains(response, self.voter.username)

    def test_admin_can_close_vote_and_freeze_veto_before_race(self):
        admin = User.objects.create_superuser("jury-admin", "admin@example.com", "test")
        CrazyPredictionVote.objects.create(
            event=self.event,
            voter=self.voter,
            target_prediction=self.prediction_a,
        )
        self.client.force_login(admin)

        response = self.client.post(
            reverse("league:close_crazy_vote", args=(self.event.id,)),
        )

        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertIsNotNone(self.event.crazy_vote_closed_at)
        self.assertFalse(crazy_vote_is_open(self.event, self.now))
        self.assertEqual(
            vetoed_crazy_prediction_id(self.event, now=self.now),
            self.prediction_a.id,
        )

        feed = build_activity_feed(build_leaderboard(self.season.year))
        jury_news = next(item for item in feed if item["type"] == "crazy-veto")
        self.assertIn(self.owner_a.username, jury_news["text"])
        self.assertEqual(jury_news["event_id"], self.event.id)

        home = self.client.get(reverse("league:home"))
        self.assertContains(home, f"Crazy Prediction игрока {self.owner_a.username} исключён")
        self.assertContains(home, "Paddock Jury")

        event_page = self.client.get(reverse("league:event_detail", args=(self.event.id,)))
        self.assertContains(event_page, "Голоса за Crazy Prediction")
        self.assertContains(event_page, "Снят Paddock Jury")
        self.assertContains(event_page, self.owner_a.username)
        self.assertContains(event_page, self.voter.username)

        audit = self.client.get(reverse("league:paddock_jury_admin"), {"event": self.event.id})
        self.assertContains(audit, "Завершено")
        self.assertContains(audit, "Исключён предикт")

    def test_one_vote_only_and_voter_cannot_vote_for_own_prediction(self):
        with self.assertRaisesMessage(CrazyVoteError, "Нельзя голосовать за свой"):
            cast_crazy_prediction_vote(self.event, self.owner_a, self.prediction_a.id, now=self.now)

        self.client.force_login(self.voter)
        vote_url = reverse("league:crazy_prediction_vote", args=(self.event.id,))
        first_response = self.client.post(vote_url, {"target_prediction": self.prediction_a.id})
        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(CrazyPredictionVote.objects.filter(event=self.event, voter=self.voter).count(), 1)

        second_response = self.client.post(vote_url, {"target_prediction": self.prediction_b.id})
        self.assertEqual(second_response.status_code, 302)
        vote = CrazyPredictionVote.objects.get(event=self.event, voter=self.voter)
        self.assertEqual(vote.target_prediction_id, self.prediction_a.id)

    def test_tied_vote_does_not_veto_but_unique_leader_does(self):
        voter_b = User.objects.create_user("voter-b", password="test")
        voter_c = User.objects.create_user("voter-c", password="test")
        CrazyPredictionVote.objects.create(event=self.event, voter=self.voter, target_prediction=self.prediction_a)
        CrazyPredictionVote.objects.create(event=self.event, voter=voter_b, target_prediction=self.prediction_b)

        closed_at = self.event.race_datetime
        self.assertIsNone(vetoed_crazy_prediction_id(self.event, now=closed_at))

        CrazyPredictionVote.objects.create(event=self.event, voter=voter_c, target_prediction=self.prediction_a)
        self.assertEqual(vetoed_crazy_prediction_id(self.event, now=closed_at), self.prediction_a.id)

    def test_veto_removes_crazy_points_before_duel_is_settled(self):
        voter_b = User.objects.create_user("voter-b", password="test")
        voter_c = User.objects.create_user("voter-c", password="test")
        self.prediction_a.crazy_prediction_approved = True
        self.prediction_a.save(update_fields=("crazy_prediction_approved",))
        Result.objects.create(
            event=self.event,
            p1="verstappen",
            p2="leclerc",
            p3="hamilton",
            pole="sainz",
            safety_car_count=0,
            dnf_count=0,
        )
        CrazyPredictionVote.objects.create(event=self.event, voter=self.voter, target_prediction=self.prediction_a)
        CrazyPredictionVote.objects.create(event=self.event, voter=voter_b, target_prediction=self.prediction_a)
        CrazyPredictionVote.objects.create(event=self.event, voter=voter_c, target_prediction=self.prediction_b)
        duel = DuelChallenge.objects.create(
            event=self.event,
            challenger=self.owner_a,
            opponent=self.owner_b,
            stake=5,
            status=DuelChallenge.Status.ACCEPTED,
        )

        self.event.status = Event.Status.LOCKED
        self.event.race_datetime = self.now - timedelta(seconds=1)
        self.event.save(update_fields=("status", "race_datetime"))
        rows, outcomes = _build_event_score_rows(self.event)
        row_a = next(row for row in rows if row["user_id"] == self.owner_a.id)
        self.assertEqual(row_a["breakdown"]["Crazy Prediction · вето паддока"], 0)
        self.assertEqual(row_a["points"], 0)
        self.assertEqual(outcomes[0]["winner_id"], None)
        self.assertEqual(outcomes[0]["challenger_points"], outcomes[0]["opponent_points"])
        self.assertEqual(duel.status, DuelChallenge.Status.ACCEPTED)
