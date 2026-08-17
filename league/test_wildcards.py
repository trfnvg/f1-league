from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .admin import EventAdminForm
from .duels import create_duel_challenge, respond_to_duel
from .models import (
    DuelChallenge,
    Event,
    EventWildcardDeck,
    EventWildcardDeckCard,
    EventWildcardQuestion,
    PlayerWildcard,
    PlayerWildcardOffer,
    Prediction,
    Result,
    Score,
    WildcardCardTemplate,
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
        self.question_two = EventWildcardQuestion.objects.create(
            event=self.event,
            question="Какая команда наберёт больше очков?",
            option_a="Ferrari",
            option_b="Mercedes",
        )
        self.question_three = EventWildcardQuestion.objects.create(
            event=self.event,
            question="Кто окажется выше в квалификации?",
            option_a="Норрис",
            option_b="Пиастри",
        )
        self.deck = EventWildcardDeck.objects.create(event=self.event)
        EventWildcardDeckCard.objects.bulk_create(
            [
                EventWildcardDeckCard(deck=self.deck, question=question, slot=slot)
                for slot, question in enumerate(
                    (self.question, self.question_two, self.question_three),
                    start=1,
                )
            ]
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

        self.assertContains(response, "Карты этапа")
        self.assertContains(response, 'name="slot"', count=3)
        self.assertContains(response, "Нажми на каждую карту")
        self.assertContains(response, "±3 PTS", count=3)
        self.assertContains(response, "/media/wildcard_theme/back.webp")
        self.assertContains(response, "league/wildcard.js")

        offer = PlayerWildcardOffer.objects.get(event=self.event, user=self.user)
        self.assertEqual(offer.cards.count(), 3)
        self.assertEqual(PlayerWildcard.objects.filter(event=self.event, user=self.user).count(), 0)

    def test_event_page_waits_for_manual_admin_deck(self):
        self.deck.delete()
        self.client.force_login(self.user)

        response = self.client.get(reverse("league:event_detail", args=(self.event.id,)))

        self.assertContains(response, "Администратор ещё не выбрал три карты для этого этапа.")
        self.assertFalse(PlayerWildcardOffer.objects.filter(event=self.event, user=self.user).exists())

    def test_every_player_gets_the_same_three_cards_in_the_same_order(self):
        for index in range(4, 7):
            EventWildcardQuestion.objects.create(
                event=self.event,
                question=f"Дополнительный вопрос {index}?",
                option_a=f"A{index}",
                option_b=f"B{index}",
            )

        self.client.force_login(self.user)
        self.client.get(reverse("league:event_detail", args=(self.event.id,)))
        first_offer = PlayerWildcardOffer.objects.get(event=self.event, user=self.user)
        first_cards = list(first_offer.cards.values_list("slot", "question_id"))

        self.client.force_login(self.opponent)
        self.client.get(reverse("league:event_detail", args=(self.event.id,)))
        second_offer = PlayerWildcardOffer.objects.get(event=self.event, user=self.opponent)
        second_cards = list(second_offer.cards.values_list("slot", "question_id"))

        self.assertEqual(EventWildcardDeck.objects.filter(event=self.event).count(), 1)
        self.assertEqual(first_cards, second_cards)
        self.assertEqual(
            first_cards,
            [(1, self.question.id), (2, self.question_two.id), (3, self.question_three.id)],
        )

    def test_requested_race_cards_are_available_in_library(self):
        expected_titles = {
            "Гонка · Победа с поула",
            "Гонка · Разные команды в топ-6",
            "Редкая · Красный флаг",
            "Гонка · Стартовая топ-3 на подиуме",
            "Гонка · Три команды на подиуме",
        }

        self.assertEqual(
            set(WildcardCardTemplate.objects.filter(title__in=expected_titles).values_list("title", flat=True)),
            expected_titles,
        )
        self.assertEqual(
            WildcardCardTemplate.objects.get(title="Гонка · Разные команды в топ-6").option_c,
            "5 и более",
        )
        self.assertLess(
            WildcardCardTemplate.objects.get(title="Редкая · Красный флаг").draw_weight,
            WildcardCardTemplate.objects.get(title="Гонка · Победа с поула").draw_weight,
        )

    def test_card_is_drawn_only_once_even_after_second_request(self):
        self.client.force_login(self.user)
        first = self._ajax_post("league:draw_event_wildcard", {"slot": 1})
        assignment = PlayerWildcard.objects.get(event=self.event, user=self.user)
        first_question_id = assignment.question_id

        EventWildcardQuestion.objects.create(
            event=self.event,
            question="Будет ли красный флаг?",
            option_a="Да",
            option_b="Нет",
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
        assignment = PlayerWildcard.objects.get(event=self.event, user=self.user)

        response = self.client.get(reverse("league:event_detail", args=(self.event.id,)))

        self.assertContains(response, 'class="wildcard-face-options"')
        self.assertContains(response, assignment.question.option_a)
        self.assertContains(response, assignment.question.option_b)

    def test_optional_third_answer_can_be_selected_and_rendered(self):
        self.question.option_c = "Поровну"
        self.question.save(update_fields=("option_c",))
        PlayerWildcard.objects.create(
            event=self.event,
            user=self.user,
            question=self.question,
        )
        self.client.force_login(self.user)

        answer = self._ajax_post("league:answer_event_wildcard", {"choice": "c"})
        response = self.client.get(reverse("league:event_detail", args=(self.event.id,)))
        assignment = PlayerWildcard.objects.get(event=self.event, user=self.user)

        self.assertEqual(answer.status_code, 200)
        self.assertEqual(assignment.selected_option, EventWildcardQuestion.Option.C)
        self.assertContains(response, "Поровну")
        self.assertContains(response, 'value="c"')

    def test_library_card_is_copied_to_event_as_a_snapshot(self):
        template = WildcardCardTemplate.objects.create(
            title="Сравнение пилотов",
            question="Кто финиширует выше?",
            option_a="Албон",
            option_b="Сайнс",
            option_c="Одинаковая позиция",
            draw_weight=4,
        )

        event_card = EventWildcardQuestion.objects.create(
            event=self.event,
            source_card=template,
            question="",
            option_a="",
            option_b="",
        )

        self.assertEqual(event_card.question, template.question)
        self.assertEqual(event_card.option_a, template.option_a)
        self.assertEqual(event_card.option_b, template.option_b)
        self.assertEqual(event_card.option_c, template.option_c)
        self.assertEqual(event_card.draw_weight, template.draw_weight)
        self.assertEqual(event_card.points, 3)

    def test_event_admin_selects_cards_from_library(self):
        templates = [
            WildcardCardTemplate.objects.create(
                title=f"Библиотечная карта {index}",
                question=f"Вопрос {index}?",
                option_a=f"A{index}",
                option_b=f"B{index}",
            )
            for index in range(1, 4)
        ]
        form = EventAdminForm(
            data={
                "season_year": self.event.season_year,
                "name": self.event.name,
                "round_number": self.event.round_number,
                "status": self.event.status,
                "deadline": self.event.deadline.strftime("%Y-%m-%d %H:%M:%S"),
                "race_datetime": self.event.race_datetime.strftime("%Y-%m-%d %H:%M:%S"),
                "wildcard_card_1": templates[0].id,
                "wildcard_card_2": templates[1].id,
                "wildcard_card_3": templates[2].id,
            },
            instance=self.event,
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        form.sync_wildcard_cards()

        selected = self.event.wildcard_questions.filter(source_card__in=templates)
        self.assertEqual(selected.count(), 3)
        self.assertTrue(all(item.points == 3 for item in selected))
        self.assertEqual(
            list(
                self.event.wildcard_deck.cards.order_by("slot").values_list(
                    "slot",
                    "question__source_card_id",
                )
            ),
            [(1, templates[0].id), (2, templates[1].id), (3, templates[2].id)],
        )

    def test_event_admin_card_select_renders_live_preview_data(self):
        template = WildcardCardTemplate.objects.create(
            title="Карта с предпросмотром",
            question="Кто попадёт на подиум?",
            option_a="Албон",
            option_b="Сайнс",
        )

        rendered = str(EventAdminForm(instance=self.event)["wildcard_card_1"])

        self.assertIn(f'value="{template.id}"', rendered)
        self.assertIn('data-card-question="Кто попадёт на подиум?"', rendered)
        self.assertIn('data-card-option-a="Албон"', rendered)

    def test_admin_deck_change_replaces_unpicked_offers_for_every_player(self):
        self.client.force_login(self.user)
        self.client.get(reverse("league:event_detail", args=(self.event.id,)))
        old_offer_id = PlayerWildcardOffer.objects.get(event=self.event, user=self.user).id
        templates = [
            WildcardCardTemplate.objects.create(
                title=f"Ручная карта {index}",
                question=f"Ручной вопрос {index}?",
                option_a=f"A{index}",
                option_b=f"B{index}",
            )
            for index in range(1, 4)
        ]
        form = EventAdminForm(
            data={
                "season_year": self.event.season_year,
                "name": self.event.name,
                "round_number": self.event.round_number,
                "status": self.event.status,
                "deadline": self.event.deadline.strftime("%Y-%m-%d %H:%M:%S"),
                "race_datetime": self.event.race_datetime.strftime("%Y-%m-%d %H:%M:%S"),
                "wildcard_card_1": templates[0].id,
                "wildcard_card_2": templates[1].id,
                "wildcard_card_3": templates[2].id,
            },
            instance=self.event,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        form.sync_wildcard_cards()

        self.assertFalse(PlayerWildcardOffer.objects.filter(pk=old_offer_id).exists())

        self.client.force_login(self.user)
        self.client.get(reverse("league:event_detail", args=(self.event.id,)))
        first_cards = list(
            PlayerWildcardOffer.objects.get(event=self.event, user=self.user)
            .cards.order_by("slot")
            .values_list("question__source_card_id", flat=True)
        )
        self.client.force_login(self.opponent)
        self.client.get(reverse("league:event_detail", args=(self.event.id,)))
        second_cards = list(
            PlayerWildcardOffer.objects.get(event=self.event, user=self.opponent)
            .cards.order_by("slot")
            .values_list("question__source_card_id", flat=True)
        )

        self.assertEqual(first_cards, [card.id for card in templates])
        self.assertEqual(second_cards, first_cards)

    def test_event_admin_requires_three_different_cards(self):
        template = WildcardCardTemplate.objects.create(
            title="Одна карта",
            question="Будет ли сейфти-кар?",
            option_a="Да",
            option_b="Нет",
        )
        base_data = {
            "season_year": self.event.season_year,
            "name": self.event.name,
            "round_number": self.event.round_number,
            "status": self.event.status,
            "deadline": self.event.deadline.strftime("%Y-%m-%d %H:%M:%S"),
            "race_datetime": self.event.race_datetime.strftime("%Y-%m-%d %H:%M:%S"),
        }

        partial_form = EventAdminForm(
            data={**base_data, "wildcard_card_1": template.id},
            instance=self.event,
        )
        duplicate_form = EventAdminForm(
            data={
                **base_data,
                "wildcard_card_1": template.id,
                "wildcard_card_2": template.id,
                "wildcard_card_3": template.id,
            },
            instance=self.event,
        )

        self.assertFalse(partial_form.is_valid())
        self.assertIn("Выбери все три карты", partial_form.non_field_errors()[0])
        self.assertFalse(duplicate_form.is_valid())
        self.assertIn("не должно быть одинаковых", duplicate_form.non_field_errors()[0])

    def test_event_admin_cannot_replace_deck_after_player_choice(self):
        templates = [
            WildcardCardTemplate.objects.create(
                title=f"Новая карта {index}",
                question=f"Новый вопрос {index}?",
                option_a=f"A{index}",
                option_b=f"B{index}",
            )
            for index in range(1, 4)
        ]
        PlayerWildcard.objects.create(
            event=self.event,
            user=self.user,
            question=self.question,
            card_slot=1,
        )
        form = EventAdminForm(
            data={
                "season_year": self.event.season_year,
                "name": self.event.name,
                "round_number": self.event.round_number,
                "status": self.event.status,
                "deadline": self.event.deadline.strftime("%Y-%m-%d %H:%M:%S"),
                "race_datetime": self.event.race_datetime.strftime("%Y-%m-%d %H:%M:%S"),
                "wildcard_card_1": templates[0].id,
                "wildcard_card_2": templates[1].id,
                "wildcard_card_3": templates[2].id,
            },
            instance=self.event,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("уже нельзя изменить", form.non_field_errors()[0])

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
        self.assertEqual(score.prediction_points, 3)
        self.assertEqual(score.points, 3)
        self.assertEqual(score.breakdown["Личная карта этапа"], 3)
        self.assertEqual(row["wildcard_points"], 3)
        self.assertEqual(row["duel_prediction_points"], 0)
        self.assertEqual(duel.status, DuelChallenge.Status.SETTLED)
        self.assertIsNone(duel.winner)
        self.assertEqual(duel.challenger_prediction_points, 0)
        self.assertEqual(duel.opponent_prediction_points, 0)

    def test_wrong_card_subtracts_three_points(self):
        self.question.correct_option = EventWildcardQuestion.Option.B
        self.question.save(update_fields=("correct_option",))
        PlayerWildcard.objects.create(
            event=self.event,
            user=self.user,
            question=self.question,
            selected_option=EventWildcardQuestion.Option.A,
            answered_at=timezone.now(),
        )
        self._prediction(self.user)
        self._result()

        _, rows = publish_event_scores(self.event)
        score = Score.objects.get(event=self.event, user=self.user)

        self.assertEqual(score.prediction_points, -3)
        self.assertEqual(score.points, -3)
        self.assertEqual(score.breakdown["Личная карта этапа"], -3)
        self.assertEqual(rows[0]["wildcard_points"], -3)

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
        self.assertContains(response, "+3 очка")
