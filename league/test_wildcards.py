from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .duels import create_duel_challenge, respond_to_duel
from .models import (
    DuelChallenge,
    Event,
    EventWildcardQuestion,
    PlayerWildcard,
    Prediction,
    Result,
    Score,
    WildcardSettings,
)
from .scoring import publish_event_scores


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=TEST_STORAGES)
class PersonalWildcardTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.event = Event.objects.create(
            season_year=2026,
            name="Wildcard Grand Prix",
            round_number=8,
            deadline=now + timedelta(days=2),
            race_datetime=now + timedelta(days=3),
        )
        self.user = User.objects.create_user(username="CardPlayer", password="test-pass")
        self.opponent = User.objects.create_user(username="Opponent", password="test-pass")
        self.question = EventWildcardQuestion.objects.create(
            event=self.event,
            question="Кто финиширует выше?",
            option_a="Леклер",
            option_b="Рассел",
        )

    def _ajax_post(self, name, data=None):
        return self.client.post(
            reverse(name, args=(self.event.id,)),
            data or {},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def _prediction(self, user):
        return Prediction.objects.create(
            event=self.event,
            user=user,
            p1="verstappen",
            p2="leclerc",
            p3="hamilton",
            pole="verstappen",
            fastest_lap="verstappen",
            driver_of_day="verstappen",
            safety_car_count=0,
            dnf_count=0,
        )

    def _result(self):
        return Result.objects.create(
            event=self.event,
            p1="norris",
            p2="piastri",
            p3="russell",
            pole="norris",
            fastest_lap="norris",
            driver_of_day="norris",
            safety_car_count=1,
            dnf_count=2,
        )

    def test_event_page_shows_three_card_draw_and_optional_global_art(self):
        WildcardSettings.objects.create(card_back_image="wildcard_theme/back.webp")
        self.client.force_login(self.user)

        response = self.client.get(reverse("league:event_detail", args=(self.event.id,)))

        self.assertContains(response, "Личная карта этапа")
        self.assertContains(response, 'name="slot"', count=3)
        self.assertContains(response, "/media/wildcard_theme/back.webp")
        self.assertContains(response, "league/wildcard.js")

    def test_card_is_drawn_only_once_even_after_second_request(self):
        self.client.force_login(self.user)
        first = self._ajax_post("league:draw_event_wildcard", {"slot": 1})
        assignment = PlayerWildcard.objects.get(event=self.event, user=self.user)
        first_question_id = assignment.question_id

        EventWildcardQuestion.objects.create(
            event=self.event,
            question="Какая команда наберёт больше очков?",
            option_a="Ferrari",
            option_b="Mercedes",
        )
        second = self._ajax_post("league:draw_event_wildcard", {"slot": 3})
        assignment.refresh_from_db()

        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["created"])
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()["created"])
        self.assertEqual(assignment.question_id, first_question_id)
        self.assertEqual(assignment.card_slot, 1)
        self.assertEqual(PlayerWildcard.objects.filter(event=self.event, user=self.user).count(), 1)

    def test_answer_can_change_before_deadline_and_locks_after_it(self):
        self.client.force_login(self.user)
        self._ajax_post("league:draw_event_wildcard", {"slot": 2})

        first = self._ajax_post("league:answer_event_wildcard", {"choice": "a"})
        second = self._ajax_post("league:answer_event_wildcard", {"choice": "b"})
        assignment = PlayerWildcard.objects.get(event=self.event, user=self.user)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(assignment.selected_option, "b")
        self.assertIsNotNone(assignment.answered_at)

        self.event.deadline = timezone.now() - timedelta(minutes=1)
        self.event.save(update_fields=("deadline",))
        locked = self._ajax_post("league:answer_event_wildcard", {"choice": "a"})
        assignment.refresh_from_db()

        self.assertEqual(locked.status_code, 400)
        self.assertEqual(assignment.selected_option, "b")

    def test_revealed_card_shows_both_answer_labels_on_its_face(self):
        self.client.force_login(self.user)
        self._ajax_post("league:draw_event_wildcard", {"slot": 2})

        response = self.client.get(reverse("league:event_detail", args=(self.event.id,)))

        self.assertContains(response, 'class="wildcard-face-options"')
        self.assertContains(response, "Леклер")
        self.assertContains(response, "Рассел")

    def test_correct_card_adds_points_but_does_not_decide_duel(self):
        self.question.correct_option = EventWildcardQuestion.Option.A
        self.question.save(update_fields=("correct_option",))
        assignment = PlayerWildcard.objects.create(
            event=self.event,
            user=self.user,
            question=self.question,
            selected_option=EventWildcardQuestion.Option.A,
            answered_at=timezone.now(),
        )
        duel = create_duel_challenge(self.event, self.user, self.opponent, 7)
        respond_to_duel(duel, self.opponent, accept=True)
        self._prediction(self.user)
        self._prediction(self.opponent)
        self._result()

        _, rows = publish_event_scores(self.event)
        duel.refresh_from_db()
        score = Score.objects.get(event=self.event, user=self.user)
        row = next(item for item in rows if item["user_id"] == self.user.id)

        self.assertTrue(assignment.is_correct)
        self.assertEqual(score.prediction_points, 5)
        self.assertEqual(score.points, 5)
        self.assertEqual(score.breakdown["Личная карта этапа"], 5)
        self.assertEqual(row["wildcard_points"], 5)
        self.assertEqual(row["duel_prediction_points"], 0)
        self.assertEqual(duel.status, DuelChallenge.Status.SETTLED)
        self.assertIsNone(duel.winner)
        self.assertEqual(duel.challenger_prediction_points, 0)
        self.assertEqual(duel.opponent_prediction_points, 0)

    def test_scoring_requires_result_for_every_answered_card(self):
        PlayerWildcard.objects.create(
            event=self.event,
            user=self.user,
            question=self.question,
            selected_option=EventWildcardQuestion.Option.A,
            answered_at=timezone.now(),
        )
        self._prediction(self.user)
        self._result()

        with self.assertRaisesMessage(ValueError, "правильные ответы"):
            publish_event_scores(self.event)

    def test_scored_page_reveals_card_result(self):
        self.question.correct_option = EventWildcardQuestion.Option.B
        self.question.save(update_fields=("correct_option",))
        PlayerWildcard.objects.create(
            event=self.event,
            user=self.user,
            question=self.question,
            selected_option=EventWildcardQuestion.Option.B,
            answered_at=timezone.now(),
        )
        self._prediction(self.user)
        self._result()
        publish_event_scores(self.event)
        self.client.force_login(self.user)

        response = self.client.get(reverse("league:event_detail", args=(self.event.id,)))

        self.assertContains(response, "Карта сыграла")
        self.assertContains(response, "Правильный ответ: Рассел")
        self.assertContains(response, "+5 очков")
