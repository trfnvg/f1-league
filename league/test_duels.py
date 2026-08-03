from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .duels import DuelActionError, create_duel_challenge, respond_to_duel
from .models import DuelChallenge, Event, Prediction, Result, Score
from .scoring import publish_event_scores
from .services import build_leaderboard


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=TEST_STORAGES)
class DuelChallengeTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.event = Event.objects.create(
            season_year=2026,
            name="Desert Grand Prix",
            round_number=1,
            deadline=now + timedelta(days=2),
            race_datetime=now + timedelta(days=3),
        )
        self.challenger = User.objects.create_user(username="Cowboy", password="test-pass")
        self.opponent = User.objects.create_user(username="Ranger", password="test-pass")
        self.third = User.objects.create_user(username="Sheriff", password="test-pass")

    def _prediction(self, user, *, strong):
        if strong:
            values = {
                "p1": "norris",
                "p2": "piastri",
                "p3": "russell",
                "pole": "norris",
                "fastest_lap": "norris",
                "driver_of_day": "norris",
                "safety_car_count": 1,
                "dnf_count": 2,
            }
        else:
            values = {
                "p1": "verstappen",
                "p2": "leclerc",
                "p3": "hamilton",
                "pole": "verstappen",
                "fastest_lap": "verstappen",
                "driver_of_day": "verstappen",
                "safety_car_count": 0,
                "dnf_count": 0,
            }
        return Prediction.objects.create(event=self.event, user=user, **values)

    def _result(self, *, strong=True):
        if strong:
            values = {
                "p1": "norris",
                "p2": "piastri",
                "p3": "russell",
                "pole": "norris",
                "fastest_lap": "norris",
                "driver_of_day": "norris",
                "safety_car_count": 1,
                "dnf_count": 2,
            }
        else:
            values = {
                "p1": "verstappen",
                "p2": "leclerc",
                "p3": "hamilton",
                "pole": "verstappen",
                "fastest_lap": "verstappen",
                "driver_of_day": "verstappen",
                "safety_car_count": 0,
                "dnf_count": 0,
            }
        result, _ = Result.objects.update_or_create(event=self.event, defaults=values)
        return result

    def test_player_can_challenge_and_opponent_can_accept(self):
        self.client.force_login(self.challenger)
        response = self.client.post(
            reverse("league:create_event_duel", args=(self.event.id,)),
            {"opponent": self.opponent.id, "stake": 10},
        )
        self.assertRedirects(
            response,
            f"{reverse('league:event_detail', args=(self.event.id,))}#event-duel",
            fetch_redirect_response=False,
        )
        duel = DuelChallenge.objects.get()
        self.assertEqual(duel.status, DuelChallenge.Status.PENDING)
        self.assertEqual(duel.stake, 10)

        self.client.force_login(self.opponent)
        event_page = self.client.get(reverse("league:event_detail", args=(self.event.id,)))
        self.assertContains(event_page, "Тебе бросили вызов")
        self.assertContains(
            event_page,
            reverse("league:respond_event_duel", kwargs={"duel_id": duel.id, "action": "accept"}),
        )
        home_page = self.client.get(reverse("league:home"))
        self.assertContains(home_page, "Тебе бросили вызов")
        response = self.client.post(
            reverse("league:respond_event_duel", kwargs={"duel_id": duel.id, "action": "accept"})
        )
        self.assertEqual(response.status_code, 302)
        duel.refresh_from_db()
        self.assertEqual(duel.status, DuelChallenge.Status.ACCEPTED)
        self.assertIsNotNone(duel.responded_at)
        self.assertContains(
            self.client.get(reverse("league:event_detail", args=(self.event.id,))),
            "Ставка зафиксирована",
        )

    def test_declined_player_can_send_counter_challenge(self):
        duel = create_duel_challenge(self.event, self.challenger, self.opponent, 8)
        self.client.force_login(self.opponent)
        response = self.client.post(
            reverse("league:respond_event_duel", kwargs={"duel_id": duel.id, "action": "decline"})
        )
        self.assertIn(f"counter={self.challenger.id}", response["Location"])
        duel.refresh_from_db()
        self.assertEqual(duel.status, DuelChallenge.Status.DECLINED)

        response = self.client.post(
            reverse("league:create_event_duel", args=(self.event.id,)),
            {"opponent": self.challenger.id, "stake": 4},
        )
        self.assertEqual(response.status_code, 302)
        counter = DuelChallenge.objects.exclude(pk=duel.pk).get()
        self.assertEqual(counter.challenger, self.opponent)
        self.assertEqual(counter.opponent, self.challenger)
        self.assertEqual(counter.stake, 4)

    def test_only_one_active_duel_and_stake_limit(self):
        create_duel_challenge(self.event, self.challenger, self.opponent, 5)
        with self.assertRaisesMessage(DuelActionError, "уже есть активная дуэль"):
            create_duel_challenge(self.event, self.third, self.opponent, 6)
        with self.assertRaisesMessage(DuelActionError, "от 1 до 10"):
            create_duel_challenge(self.event, self.third, self.challenger, 11)

    def test_challenges_close_at_prediction_deadline(self):
        self.event.deadline = timezone.now() - timedelta(minutes=1)
        self.event.save(update_fields=("deadline",))
        with self.assertRaisesMessage(DuelActionError, "закрываются одновременно"):
            create_duel_challenge(self.event, self.challenger, self.opponent, 5)

    def test_settlement_adds_and_subtracts_stake_and_republishes(self):
        duel = create_duel_challenge(self.event, self.challenger, self.opponent, 7)
        respond_to_duel(duel, self.opponent, accept=True)
        self._prediction(self.challenger, strong=True)
        self._prediction(self.opponent, strong=False)
        result = self._result(strong=True)

        publish_event_scores(self.event)
        duel.refresh_from_db()
        winner_score = Score.objects.get(event=self.event, user=self.challenger)
        loser_score = Score.objects.get(event=self.event, user=self.opponent)
        self.assertEqual(duel.status, DuelChallenge.Status.SETTLED)
        self.assertEqual(duel.winner, self.challenger)
        self.assertEqual(winner_score.prediction_points, 40)
        self.assertEqual(winner_score.duel_adjustment, 7)
        self.assertEqual(winner_score.points, 47)
        self.assertEqual(loser_score.prediction_points, 0)
        self.assertEqual(loser_score.duel_adjustment, -7)
        self.assertEqual(loser_score.points, -7)
        self.assertEqual(loser_score.breakdown["Дуэль"], -7)
        leaderboard = build_leaderboard(2026)
        totals = {row["user"].id: row["total"] for row in leaderboard["rows"]}
        self.assertEqual(totals[self.challenger.id], 47)
        self.assertEqual(totals[self.opponent.id], -7)
        public_page = self.client.get(reverse("league:event_detail", args=(self.event.id,)))
        self.assertContains(public_page, "40 : 0")
        self.assertContains(public_page, "Cowboy · +7")

        result.p1 = "verstappen"
        result.p2 = "leclerc"
        result.p3 = "hamilton"
        result.pole = "verstappen"
        result.fastest_lap = "verstappen"
        result.driver_of_day = "verstappen"
        result.safety_car_count = 0
        result.dnf_count = 0
        result.save()
        publish_event_scores(self.event)

        duel.refresh_from_db()
        self.assertEqual(duel.winner, self.opponent)
        self.assertEqual(Score.objects.get(event=self.event, user=self.challenger).points, -7)
        self.assertEqual(Score.objects.get(event=self.event, user=self.opponent).points, 47)

    def test_tie_does_not_transfer_points_and_pending_duel_expires(self):
        duel = create_duel_challenge(self.event, self.challenger, self.opponent, 10)
        respond_to_duel(duel, self.opponent, accept=True)
        pending = DuelChallenge.objects.create(
            event=self.event,
            challenger=self.third,
            opponent=User.objects.create_user(username="Bandit", password="test-pass"),
            stake=3,
        )
        self._prediction(self.challenger, strong=True)
        self._prediction(self.opponent, strong=True)
        self._result(strong=True)

        publish_event_scores(self.event)
        duel.refresh_from_db()
        pending.refresh_from_db()
        self.assertIsNone(duel.winner)
        self.assertEqual(Score.objects.get(event=self.event, user=self.challenger).duel_adjustment, 0)
        self.assertEqual(Score.objects.get(event=self.event, user=self.opponent).duel_adjustment, 0)
        self.assertEqual(pending.status, DuelChallenge.Status.EXPIRED)

    def test_event_page_renders_western_duel_form(self):
        self.client.force_login(self.challenger)
        response = self.client.get(reverse("league:event_detail", args=(self.event.id,)))
        self.assertContains(response, "Вызов на дуэль")
        self.assertContains(response, "F1 · Wild West")
        self.assertContains(response, reverse("league:create_event_duel", args=(self.event.id,)))
