from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .crazy_jury import (
    CrazyVoteError, cancel_crazy_exclusion, cast_crazy_prediction_vote,
    crazy_jury_context, crazy_vote_is_open, vetoed_crazy_prediction_id,
)
from .models import (
    ArcadeWheelSpin, CrazyPredictionVote, DuelChallenge, Event, Prediction,
    Result, Score, ScoreRevision, Season,
)
from .scoring import publish_event_scores
from .services import build_activity_feed, build_leaderboard


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class CrazyJuryControlTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.season = Season.get_active()
        self.event = Event.objects.create(season_year=self.season.year, name="Jury controls GP", round_number=1,
            deadline=self.now-timedelta(minutes=30), race_datetime=self.now+timedelta(hours=2))
        self.admin = User.objects.create_user("jury-control-admin", is_staff=True)
        self.a = User.objects.create_user("jury-a")
        self.b = User.objects.create_user("jury-b")
        self.voter = User.objects.create_user("jury-voter")
        self.pa = self.prediction(self.a, "Alpha crazy")
        self.pb = self.prediction(self.b, "Bravo crazy")

    def prediction(self, user, text, event=None):
        return Prediction.objects.create(event=event or self.event, user=user,
            p1="norris", p2="piastri", p3="russell", pole="norris", safety_car_count=1, dnf_count=1,
            crazy_prediction=text, crazy_prediction_approved=True)

    def close_event(self):
        self.event.deadline = self.now-timedelta(hours=13)
        self.event.race_datetime = self.now-timedelta(hours=1)
        self.event.save(update_fields=("deadline", "race_datetime"))

    def result(self):
        return Result.objects.create(event=self.event, p1="verstappen", p2="leclerc", p3="hamilton",
            pole="sainz", safety_car_count=0, dnf_count=0)

    def test_revote_updates_one_ballot_and_preserves_original_time(self):
        first = cast_crazy_prediction_vote(self.event, self.voter, self.pa.pk, now=self.now)
        later = self.now+timedelta(minutes=1)
        second = cast_crazy_prediction_vote(self.event, self.voter, self.pb.pk, now=later)
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(second.created_at, first.created_at)
        self.assertEqual(second.updated_at, later)
        self.assertEqual(CrazyPredictionVote.objects.filter(event=self.event, voter=self.voter).count(), 1)
        context = crazy_jury_context(self.event, self.voter, now=later)
        self.assertTrue(context["can_vote"])
        self.assertEqual([r["id"] for r in context["candidates"] if r["is_selected"]], [self.pb.pk])
        self.client.force_login(self.voter)
        response = self.client.get(reverse("league:home"))
        self.assertContains(response, "Изменить голос")
        self.assertNotContains(response, 'class="crazy-jury-candidates" disabled')

    def test_invalid_or_closed_revote_cannot_replace_previous_choice(self):
        first = cast_crazy_prediction_vote(self.event, self.a, self.pb.pk, now=self.now)
        with self.assertRaises(CrazyVoteError):
            cast_crazy_prediction_vote(self.event, self.a, self.pa.pk, now=self.now)
        with self.assertRaises(CrazyVoteError):
            cast_crazy_prediction_vote(self.event, self.a, 999999, now=self.now)
        with self.assertRaises(CrazyVoteError):
            cast_crazy_prediction_vote(self.event, self.admin, self.pa.pk, now=self.now)
        self.close_event()
        with self.assertRaises(CrazyVoteError):
            cast_crazy_prediction_vote(self.event, self.a, self.pa.pk, now=self.now)
        first.refresh_from_db()
        self.assertEqual(first.target_prediction_id, self.pb.pk)

    def test_cancel_is_staff_post_only_and_csrf_protected(self):
        url = reverse("league:cancel_crazy_exclusion", args=[self.event.pk])
        self.client.force_login(self.voter)
        self.assertEqual(self.client.post(url).status_code, 403)
        with self.assertRaises(CrazyVoteError):
            cancel_crazy_exclusion(self.event, self.voter)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        self.assertEqual(csrf_client.post(url).status_code, 403)
        self.event.refresh_from_db()
        self.assertIsNone(self.event.crazy_vote_veto_cancelled_at)

    def test_cancel_keeps_votes_audit_and_other_event_intact(self):
        vote = cast_crazy_prediction_vote(self.event, self.voter, self.pa.pk)
        self.close_event()
        self.assertEqual(vetoed_crazy_prediction_id(self.event), self.pa.pk)
        other = Event.objects.create(season_year=self.season.year, name="Another GP", round_number=2,
            deadline=self.event.deadline, race_datetime=self.event.race_datetime)
        other_prediction = self.prediction(self.a, "Another crazy", other)
        CrazyPredictionVote.objects.create(event=other, voter=self.voter, target_prediction=other_prediction)
        self.client.force_login(self.admin)
        url = reverse("league:cancel_crazy_exclusion", args=[self.event.pk])
        self.assertEqual(self.client.post(url).status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.crazy_vote_veto_cancelled_by, self.admin)
        self.assertIsNotNone(self.event.crazy_vote_veto_cancelled_at)
        self.assertIsNone(vetoed_crazy_prediction_id(self.event))
        self.assertFalse(crazy_vote_is_open(self.event))
        self.assertTrue(CrazyPredictionVote.objects.filter(pk=vote.pk).exists())
        self.assertEqual(vetoed_crazy_prediction_id(other), other_prediction.pk)
        with self.assertRaises(CrazyVoteError):
            cast_crazy_prediction_vote(self.event, self.voter, self.pb.pk)
        audit = self.client.get(reverse("league:paddock_jury_admin"), {"event":self.event.pk})
        self.assertContains(audit, "Исключение отменено администратором")
        self.assertContains(audit, self.voter.username)
        page = self.client.get(reverse("league:event_detail", args=[self.event.pk]))
        self.assertContains(page, "Исключение отменено")
        self.assertNotContains(page, "Снят Paddock Jury")

    def test_cancel_recalculates_published_scores_duels_and_revision_once(self):
        cast_crazy_prediction_vote(self.event, self.voter, self.pa.pk)
        self.close_event()
        self.result()
        duel = DuelChallenge.objects.create(event=self.event, challenger=self.a, opponent=self.b,
            stake=10, status=DuelChallenge.Status.ACCEPTED)
        publish_event_scores(self.event, self.admin)
        duel.refresh_from_db()
        self.assertEqual(duel.winner_id, self.b.pk)
        self.assertEqual(Score.objects.get(event=self.event, user=self.a).points, -10)
        self.assertTrue(cancel_crazy_exclusion(self.event, self.admin))
        self.assertEqual(Score.objects.get(event=self.event, user=self.a).points, 5)
        duel.refresh_from_db()
        self.assertIsNone(duel.winner_id)
        self.assertEqual(ScoreRevision.objects.filter(event=self.event).count(), 2)
        self.assertFalse(cancel_crazy_exclusion(self.event, self.admin))
        self.assertEqual(ScoreRevision.objects.filter(event=self.event).count(), 2)

    def test_failed_recalculation_rolls_back_cancellation(self):
        self.close_event()
        self.result()
        publish_event_scores(self.event, self.admin)
        with patch("league.scoring.publish_event_scores", side_effect=ValueError("Cannot publish")):
            with self.assertRaisesMessage(ValueError, "Cannot publish"):
                cancel_crazy_exclusion(self.event, self.admin)
        self.event.refresh_from_db()
        self.assertIsNone(self.event.crazy_vote_veto_cancelled_at)
        self.assertEqual(ScoreRevision.objects.filter(event=self.event).count(), 1)

    def test_cancel_does_not_mark_an_unapproved_prediction_correct(self):
        cast_crazy_prediction_vote(self.event, self.voter, self.pa.pk)
        self.pa.crazy_prediction_approved = False
        self.pa.save(update_fields=("crazy_prediction_approved",))
        self.close_event()
        self.result()
        publish_event_scores(self.event, self.admin)
        cancel_crazy_exclusion(self.event, self.admin)
        self.pa.refresh_from_db()
        self.assertFalse(self.pa.crazy_prediction_approved)
        self.assertEqual(Score.objects.get(event=self.event, user=self.a).points, 0)

    def test_cancel_preserves_separate_wheel_block(self):
        cast_crazy_prediction_vote(self.event, self.voter, self.pa.pk)
        self.close_event()
        self.result()
        ArcadeWheelSpin.objects.create(event=self.event, winner=self.b, winner_score=100,
            prize=ArcadeWheelSpin.Prize.CRAZY_BLOCK, target_user=self.a, activated_at=self.now)
        publish_event_scores(self.event, self.admin)
        cancel_crazy_exclusion(self.event, self.admin)
        self.assertEqual(Score.objects.get(event=self.event, user=self.a).points, 0)
        self.assertIn("Crazy Prediction · заблокирован", Score.objects.get(event=self.event, user=self.a).breakdown)

    def test_cancel_notice_replaces_exclusion_in_live_feed(self):
        cast_crazy_prediction_vote(self.event, self.voter, self.pa.pk)
        self.close_event()
        cancel_crazy_exclusion(self.event, self.admin)
        feed = build_activity_feed(build_leaderboard(self.season.year))
        news = next(row for row in feed if row["type"] == "crazy-veto")
        self.assertIn("отменено", news["text"])
        self.assertEqual(news["event_id"], self.event.pk)

    def test_future_stage_cannot_be_cancelled(self):
        self.event.deadline = self.now+timedelta(hours=1)
        self.event.save(update_fields=("deadline",))
        with self.assertRaises(CrazyVoteError):
            cancel_crazy_exclusion(self.event, self.admin)
