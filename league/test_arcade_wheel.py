from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .arcade_rewards import (
    ArcadeWheelError,
    activate_event_wheel_prize,
    best_event_arcade_attempt,
    podium_edit_is_open,
    spin_event_wheel,
)
from .models import (
    ArcadeAttempt,
    ArcadeGameClosure,
    ArcadeRecord,
    ArcadeTrophyAward,
    ArcadeWheelSpin,
    DuelChallenge,
    Event,
    EventWildcardQuestion,
    PlayerWildcard,
    Prediction,
    Result,
    Season,
)
from .scoring import _build_event_score_rows


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=TEST_STORAGES)
class ArcadeWheelTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.event = Event.objects.create(
            season_year=2026,
            name="Monaco GP",
            round_number=8,
            deadline=self.now - timedelta(hours=1),
            qualifying_datetime=self.now - timedelta(minutes=30),
            race_datetime=self.now + timedelta(hours=2),
        )
        self.winner = User.objects.create_user("arcade-winner")
        self.challenger = User.objects.create_user("challenger")
        self.opponent = User.objects.create_user("opponent")
        self._prediction(self.winner)
        self._prediction(self.challenger)
        self._prediction(self.opponent)

    def _prediction(self, user, **overrides):
        values = {
            "p1": "albon",
            "p2": "sainz",
            "p3": "lawson",
            "pole": "albon",
            "fastest_lap": "albon",
            "driver_of_day": "albon",
            "safety_car_count": 3,
            "dnf_count": 3,
            "crazy_prediction": "",
            "crazy_prediction_approved": False,
        }
        values.update(overrides)
        return Prediction.objects.create(event=self.event, user=user, **values)

    def _attempt(self, user, score, finished_at):
        return ArcadeAttempt.objects.create(
            user=user,
            score=score,
            finished_at=finished_at,
        )

    def _result(self):
        return Result.objects.create(
            event=self.event,
            p1="norris",
            p2="piastri",
            p3="russell",
            pole="norris",
            safety_car_count=0,
            dnf_count=0,
        )

    def test_weekly_leader_uses_only_recent_completed_runs_from_event_players(self):
        self._attempt(self.winner, 12, self.event.deadline - timedelta(days=2))
        self._attempt(self.winner, 10, self.event.deadline - timedelta(days=1))
        outsider = User.objects.create_user("outsider")
        self._attempt(outsider, 99, self.event.deadline - timedelta(hours=2))
        self._attempt(self.challenger, 100, self.event.deadline - timedelta(days=8))
        unfinished = ArcadeAttempt.objects.create(user=self.opponent, score=None)

        leader = best_event_arcade_attempt(self.event, through=self.now)

        self.assertEqual(leader.user, self.winner)
        self.assertEqual(leader.score, 12)
        self.assertNotEqual(leader, unfinished)

    def test_arcade_page_renders_wheel_configuration_and_entry(self):
        response = self.client.get(reverse("league:arcade"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="arcade-canvas"')
        self.assertContains(response, "Заезды завершены")
        self.assertContains(response, "Pit Lane")
        self.assertContains(response, "Сектора колеса")
        self.assertContains(response, "25% шанс")
        self.assertContains(response, "arcade-wheel-config")
        self.assertEqual(len(response.context["wheel_sectors"]), 6)
        self.assertEqual(response.context["wheel_sectors"][4]["title"], "Руль в говне")

    def test_game_accepts_runs_before_deadline_and_closes_after_it(self):
        self.event.deadline = self.now + timedelta(days=1)
        self.event.save(update_fields=("deadline",))
        self.client.force_login(self.winner)

        response = self.client.get(reverse("league:arcade"))
        self.assertContains(response, 'id="arcade-canvas"')
        started = self.client.post(reverse("league:arcade_run_start"))
        self.assertEqual(started.status_code, 200)

        self.event.deadline = self.now - timedelta(seconds=1)
        self.event.save(update_fields=("deadline",))
        response = self.client.get(reverse("league:arcade"))
        self.assertContains(response, "Заезды завершены")
        self.assertNotContains(response, 'id="arcade-canvas"')

        rejected = self.client.post(reverse("league:arcade_run_start"))
        self.assertEqual(rejected.status_code, 410)
        self.assertEqual(ArcadeAttempt.objects.count(), 1)

    def test_old_deadline_does_not_close_game_before_next_event_deadline(self):
        self.event.race_datetime = self.now - timedelta(minutes=10)
        self.event.save(update_fields=("race_datetime",))
        next_event = Event.objects.create(
            season_year=2026,
            name="Next GP",
            round_number=9,
            deadline=self.now + timedelta(hours=1),
            qualifying_datetime=self.now + timedelta(hours=2),
            race_datetime=self.now + timedelta(hours=3),
        )
        self.client.force_login(self.winner)

        response = self.client.get(reverse("league:arcade"))

        self.assertContains(response, 'id="arcade-canvas"')
        self.assertFalse(ArcadeGameClosure.objects.exists())

        next_event.deadline = self.now - timedelta(seconds=1)
        next_event.save(update_fields=("deadline",))
        response = self.client.get(reverse("league:arcade"))

        self.assertNotContains(response, 'id="arcade-canvas"')
        self.assertEqual(response.context["arcade_closed_event"], next_event)

    def test_closure_fixes_deadline_winner_and_rejects_late_result(self):
        valid_run = self._attempt(self.winner, 12, self.event.deadline - timedelta(minutes=5))
        ArcadeAttempt.objects.filter(pk=valid_run.pk).update(
            started_at=self.event.deadline - timedelta(minutes=8),
        )
        late_run = self._attempt(self.challenger, 99, self.event.deadline + timedelta(minutes=1))
        ArcadeAttempt.objects.filter(pk=late_run.pk).update(
            started_at=self.event.deadline - timedelta(minutes=2),
        )
        unfinished = ArcadeAttempt.objects.create(user=self.winner)
        ArcadeAttempt.objects.filter(pk=unfinished.pk).update(
            started_at=self.event.deadline - timedelta(seconds=20),
        )
        ArcadeRecord.objects.create(user=self.winner, total_attempts=2006)
        self.client.force_login(self.winner)

        response = self.client.get(reverse("league:arcade"))

        self.assertContains(response, "Заезды завершены")
        self.assertContains(response, "ПОБЕДИТЕЛЬ")
        self.assertContains(response, "arcade-winner")
        self.assertContains(response, ">12 ворот")
        self.assertContains(response, "Лучшие заезды до дедлайна")
        self.assertEqual(
            [row["username"] for row in response.context["arcade_records"]],
            ["arcade-winner"],
        )
        self.assertEqual(response.context["arcade_records"][0]["attempts"], 2006)
        self.assertEqual(response.context["arcade_total_attempts"], 2006)
        award = ArcadeTrophyAward.objects.get(event=self.event, game_key="pit_lane_flight")
        self.assertEqual(award.player, self.winner)
        self.assertEqual(award.attempts, 2006)

        rejected = self.client.post(
            reverse("league:arcade_run_finish"),
            data='{"attempt_id": %d, "score": 20}' % unfinished.pk,
            content_type="application/json",
        )
        self.assertEqual(rejected.status_code, 410)
        unfinished.refresh_from_db()
        self.assertIsNone(unfinished.score)

    def test_closed_game_does_not_reopen_for_a_later_event(self):
        self._attempt(self.winner, 12, self.event.deadline - timedelta(minutes=5))
        ArcadeAttempt.objects.filter(user=self.winner).update(
            started_at=self.event.deadline - timedelta(minutes=8),
        )
        self.client.force_login(self.winner)
        self.client.get(reverse("league:arcade"))

        next_event = Event.objects.create(
            season_year=2026,
            name="Next GP",
            round_number=9,
            deadline=self.now - timedelta(minutes=30),
            qualifying_datetime=self.now - timedelta(minutes=10),
            race_datetime=self.now + timedelta(hours=3),
        )
        Prediction.objects.create(
            event=next_event,
            user=self.challenger,
            p1="albon",
            p2="sainz",
            p3="lawson",
            pole="albon",
            fastest_lap="albon",
            driver_of_day="albon",
            safety_car_count=3,
            dnf_count=3,
        )
        next_run = ArcadeAttempt.objects.create(
            user=self.challenger,
            score=99,
            finished_at=next_event.deadline - timedelta(minutes=1),
        )
        ArcadeAttempt.objects.filter(pk=next_run.pk).update(
            started_at=next_event.deadline - timedelta(minutes=2),
        )

        response = self.client.get(reverse("league:arcade"))

        self.assertEqual(response.context["arcade_closed_event"], self.event)
        closure = ArcadeGameClosure.objects.get(game_key="pit_lane_flight", season_year=2026)
        self.assertEqual(closure.event, self.event)
        self.assertEqual(closure.winner, self.winner)
        self.assertEqual(ArcadeGameClosure.objects.count(), 1)
        self.assertFalse(ArcadeTrophyAward.objects.filter(event=next_event).exists())
        self.assertEqual(
            [row["username"] for row in response.context["arcade_records"]],
            ["arcade-winner"],
        )

    def test_live_paddock_poll_closes_arcade_and_publishes_final_winner(self):
        Season.objects.update_or_create(
            year=2026,
            defaults={"title": "Season 2026", "is_active": True},
        )
        self._attempt(self.winner, 17, self.event.deadline - timedelta(minutes=5))
        ArcadeRecord.objects.create(user=self.winner, best_score=17, total_attempts=2006)

        response = self.client.get(reverse("league:activity_feed"), {"season": 2026})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "arcade-winner", html=False)
        self.assertIn("arcade-winner выиграл аркаду", response.json()["html"])
        self.assertIn("2006 попытками", response.json()["html"])
        self.assertEqual(
            ArcadeGameClosure.objects.get(game_key="pit_lane_flight", season_year=2026).winner,
            self.winner,
        )

    def test_only_weekly_leader_can_spin_and_event_has_one_spin(self):
        self._attempt(self.winner, 12, self.event.deadline - timedelta(minutes=10))
        self._attempt(self.challenger, 8, self.event.deadline - timedelta(minutes=10))

        with patch("league.arcade_rewards._draw_prize", return_value=ArcadeWheelSpin.Prize.PIT_WALL):
            spin, created = spin_event_wheel(self.event, self.winner, now=self.now)
            same_spin, created_again = spin_event_wheel(self.event, self.winner, now=self.now)

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(spin.pk, same_spin.pk)
        self.assertEqual(ArcadeWheelSpin.objects.filter(event=self.event).count(), 1)
        with self.assertRaises(ArcadeWheelError):
            spin_event_wheel(self.event, self.challenger, now=self.now)

    def test_spin_and_activation_respect_event_window(self):
        self._attempt(self.winner, 12, self.event.deadline - timedelta(minutes=10))
        with self.assertRaises(ArcadeWheelError):
            spin_event_wheel(self.event, self.winner, now=self.event.deadline - timedelta(seconds=1))

        self.assertFalse(podium_edit_is_open(self.event, self.event.qualifying_datetime - timedelta(seconds=1)))
        self.assertTrue(podium_edit_is_open(self.event, self.now))

        self.event.race_datetime = self.now - timedelta(seconds=1)
        self.event.save(update_fields=("race_datetime",))
        with self.assertRaises(ArcadeWheelError):
            spin_event_wheel(self.event, self.winner, now=self.now)

    def test_va_bank_can_be_selected_after_deadline_before_race(self):
        self._attempt(self.winner, 12, self.event.deadline - timedelta(minutes=10))
        Prediction.objects.filter(event=self.event, user=self.winner).update(p1="norris")
        spin = ArcadeWheelSpin.objects.create(
            event=self.event,
            winner=self.winner,
            winner_score=12,
            prize=ArcadeWheelSpin.Prize.VA_BANK,
        )

        activated = activate_event_wheel_prize(self.event, self.winner, {"field": "p1"}, now=self.now)

        self.assertEqual(activated.pk, spin.pk)
        self.assertEqual(activated.activation_data, {"field": "p1"})
        self.assertIsNotNone(activated.activated_at)

    def test_podium_edit_requires_qualifying_time_and_changes_only_one_slot(self):
        self._attempt(self.winner, 12, self.event.deadline - timedelta(minutes=10))
        spin = ArcadeWheelSpin.objects.create(
            event=self.event,
            winner=self.winner,
            winner_score=12,
            prize=ArcadeWheelSpin.Prize.PODIUM_EDIT,
        )
        self.event.qualifying_datetime = None
        self.event.save(update_fields=("qualifying_datetime",))
        with self.assertRaises(ArcadeWheelError):
            activate_event_wheel_prize(
                self.event,
                self.winner,
                {"slot": "p1", "driver": "norris"},
                now=self.now,
            )

        self.event.qualifying_datetime = self.now - timedelta(minutes=1)
        self.event.save(update_fields=("qualifying_datetime",))
        activate_event_wheel_prize(
            self.event,
            self.winner,
            {"slot": "p1", "driver": "norris"},
            now=self.now,
        )
        spin.refresh_from_db()
        self.assertEqual(spin.activation_data, {"slot": "p1", "old_driver": "albon", "new_driver": "norris"})
        self.assertEqual(Prediction.objects.get(event=self.event, user=self.winner).p1, "norris")

    def test_personal_card_boost_adds_three_without_double_counting_breakdown(self):
        self._result()
        question = EventWildcardQuestion.objects.create(
            event=self.event,
            question="Поднимется ли пилот на подиум?",
            option_a="Да",
            option_b="Нет",
            correct_option=EventWildcardQuestion.Option.A,
        )
        PlayerWildcard.objects.create(
            event=self.event,
            user=self.winner,
            question=question,
            selected_option=EventWildcardQuestion.Option.A,
        )
        ArcadeWheelSpin.objects.create(
            event=self.event,
            winner=self.winner,
            winner_score=12,
            prize=ArcadeWheelSpin.Prize.CARD_BOOST,
            activated_at=self.now,
        )

        rows, _ = _build_event_score_rows(self.event)
        winner_row = next(row for row in rows if row["user_id"] == self.winner.id)

        self.assertEqual(winner_row["wildcard_points"], 6)
        self.assertEqual(winner_row["breakdown"]["Личная карта этапа"], 3)
        self.assertEqual(winner_row["breakdown"]["ДРС личной карты"], 3)

    def test_crazy_block_removes_points_even_when_prediction_was_approved(self):
        self._result()
        Prediction.objects.filter(event=self.event, user=self.opponent).update(
            crazy_prediction="Будет Safety Car",
            crazy_prediction_approved=True,
        )
        ArcadeWheelSpin.objects.create(
            event=self.event,
            winner=self.winner,
            winner_score=12,
            prize=ArcadeWheelSpin.Prize.CRAZY_BLOCK,
            target_user=self.opponent,
            activated_at=self.now,
        )

        rows, _ = _build_event_score_rows(self.event)
        opponent_row = next(row for row in rows if row["user_id"] == self.opponent.id)

        self.assertEqual(opponent_row["breakdown"]["Crazy Prediction · заблокирован"], 0)
        self.assertNotIn("Crazy Prediction", opponent_row["breakdown"])

    def test_ruel_v_govne_changes_full_score_used_to_settle_duel(self):
        self._result()
        duel = DuelChallenge.objects.create(
            event=self.event,
            challenger=self.challenger,
            opponent=self.opponent,
            stake=2,
            status=DuelChallenge.Status.ACCEPTED,
        )
        ArcadeWheelSpin.objects.create(
            event=self.event,
            winner=self.winner,
            winner_score=12,
            prize=ArcadeWheelSpin.Prize.RUEL_V_GOVNE,
            target_user=self.opponent,
            activated_at=self.now,
        )

        rows, outcomes = _build_event_score_rows(self.event)
        by_user = {row["user_id"]: row for row in rows}
        duel_result = outcomes[0]

        self.assertEqual(duel_result["duel_id"], duel.pk)
        self.assertEqual(duel_result["challenger_points"], 0)
        self.assertEqual(duel_result["opponent_points"], -3)
        self.assertEqual(duel_result["winner_id"], self.challenger.id)
        self.assertEqual(by_user[self.opponent.id]["points"], -5)
