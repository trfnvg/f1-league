from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .duels import DuelActionError, available_opponents, create_duel_challenge, respond_to_duel
from .models import DuelChallenge, DuelSettings, Event, Prediction, Result, Score
from .scoring import publish_event_scores
from .services import build_activity_feed, build_leaderboard


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

    def availability(self, opponent=None):
        return self.client.get(reverse('league:duel_opponent_availability', args=[self.event.pk]),
            {'opponent': (opponent or self.challenger).pk})

    def test_pending_challenge_appears_in_live_paddock(self):
        duel = create_duel_challenge(self.event, self.challenger, self.opponent, 5)
        feed = build_activity_feed(build_leaderboard(2026))
        news = next(item for item in feed if item['type'] == 'duel-challenge')
        self.assertIn('Cowboy бросил вызов игроку Ranger', news['text'])
        self.assertEqual(news['occurred_at'], duel.created_at)
        self.assertEqual(news['anchor'], '#event-duel')
        self.assertEqual(news['source_event_id'], self.event.pk)
        self.client.force_login(self.third)
        self.assertContains(self.client.get(reverse('league:home')), 'is-duel-challenge')
        from .duels import cancel_duel_challenge
        cancel_duel_challenge(duel, self.challenger)
        self.assertFalse(any(item['type'] == 'duel-challenge' for item in build_activity_feed(build_leaderboard(2026))))

    def test_busy_opponent_is_visible_but_explained_and_rejected(self):
        create_duel_challenge(self.event, self.challenger, self.opponent, 5)
        self.client.force_login(self.third)
        response = self.availability()
        self.assertFalse(response.json()['available'])
        self.assertIn('Cowboy уже бросил вызов игроку Ranger', response.json()['message'])
        self.assertIn('no-store', response['Cache-Control'])
        page = self.client.get(reverse('league:event_detail', args=[self.event.pk]))
        self.assertContains(page, 'Cowboy · занят')
        self.assertContains(page, 'data-duel-opponent-status')
        response = self.client.post(reverse('league:create_event_duel', args=[self.event.pk]),
            {'opponent': self.challenger.pk, 'stake': 5}, follow=True)
        self.assertContains(response, 'Cowboy уже бросил вызов игроку Ranger')
        self.assertEqual(DuelChallenge.objects.count(), 1)

    def test_availability_tracks_received_accepted_and_declined_challenges(self):
        self.client.force_login(self.third)
        self.assertTrue(self.availability().json()['available'])
        duel = create_duel_challenge(self.event, self.challenger, self.opponent, 5)
        self.assertIn('уже получил вызов', self.availability(self.opponent).json()['message'])
        respond_to_duel(duel, self.opponent, accept=False)
        self.assertTrue(self.availability().json()['available'])
        duel = create_duel_challenge(self.event, self.challenger, self.opponent, 5)
        respond_to_duel(duel, self.opponent, accept=True)
        self.assertIn('уже участвует в дуэли', self.availability().json()['message'])

    def test_availability_requires_login_and_obeys_deadline_and_eligibility(self):
        self.assertEqual(self.availability().status_code, 302)
        self.client.force_login(self.third)
        self.assertFalse(self.availability(self.third).json()['available'])
        url = reverse('league:duel_opponent_availability', args=[self.event.pk])
        self.assertEqual(self.client.post(url).status_code, 405)
        for value in ('not-an-id', '9' * 100, '-1'):
            self.assertFalse(self.client.get(url, {'opponent': value}).json()['available'])
        self.event.deadline = timezone.now() - timedelta(seconds=1)
        self.event.save(update_fields=['deadline'])
        self.assertIn('Приём вызовов закрыт', self.availability().json()['message'])

    def test_stale_opponent_selection_cannot_create_second_challenge(self):
        self.client.force_login(self.third)
        self.assertTrue(self.availability().json()['available'])
        create_duel_challenge(self.event, self.challenger, self.opponent, 5)
        response = self.client.post(reverse('league:create_event_duel', args=[self.event.pk]),
            {'opponent': self.challenger.pk, 'stake': 5}, follow=True)
        self.assertContains(response, 'уже бросил вызов')
        self.assertEqual(DuelChallenge.objects.count(), 1)

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
        feed_url = reverse('league:activity_feed') + '?season=2026'
        self.assertEqual(self.client.get(feed_url).json()['pending_duel_ids'], [duel.pk])
        response = self.client.post(
            reverse("league:respond_event_duel", kwargs={"duel_id": duel.id, "action": "accept"})
        )
        self.assertEqual(response.status_code, 302)
        duel.refresh_from_db()
        self.assertEqual(duel.status, DuelChallenge.Status.ACCEPTED)
        self.assertIsNotNone(duel.responded_at)
        self.assertEqual(self.client.get(feed_url).json()['pending_duel_ids'], [])
        self.assertNotContains(self.client.get(reverse('league:home')), 'class="ns-duel-notice"')
        self.client.force_login(self.challenger)
        self.assertNotContains(self.client.get(reverse('league:home')), 'class="ns-duel-notice"')
        self.client.force_login(self.opponent)
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

    def test_same_opponent_cannot_be_targeted_on_consecutive_events(self):
        next_event = Event.objects.create(
            season_year=2026,
            name="Coastal Grand Prix",
            round_number=2,
            deadline=timezone.now() + timedelta(days=4),
            race_datetime=timezone.now() + timedelta(days=5),
        )
        create_duel_challenge(self.event, self.challenger, self.opponent, 5)

        with self.assertRaisesMessage(DuelActionError, "Нельзя выбирать одного и того же соперника"):
            create_duel_challenge(next_event, self.challenger, self.opponent, 5)

        opponent_ids = set(available_opponents(next_event, self.challenger).values_list("id", flat=True))
        self.assertNotIn(self.opponent.id, opponent_ids)
        self.assertIn(self.third.id, opponent_ids)

    def test_same_opponent_is_available_again_after_an_event_without_that_target(self):
        next_event = Event.objects.create(
            season_year=2026,
            name="Coastal Grand Prix",
            round_number=2,
            deadline=timezone.now() + timedelta(days=4),
            race_datetime=timezone.now() + timedelta(days=5),
        )
        final_event = Event.objects.create(
            season_year=2026,
            name="Night Grand Prix",
            round_number=3,
            deadline=timezone.now() + timedelta(days=6),
            race_datetime=timezone.now() + timedelta(days=7),
        )
        create_duel_challenge(self.event, self.challenger, self.opponent, 5)
        create_duel_challenge(next_event, self.challenger, self.third, 5)

        create_duel_challenge(final_event, self.challenger, self.opponent, 5)

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

    def test_event_page_renders_compact_nightshift_duel_form(self):
        self.client.force_login(self.challenger)
        response = self.client.get(reverse("league:event_detail", args=(self.event.id,)))
        self.assertContains(response, 'class="stage-duel mb-4"')
        self.assertContains(response, "Бросить вызов")
        self.assertContains(response, 'class="stage-duel-form"')
        self.assertNotContains(response, "F1 · Wild West")
        self.assertTemplateUsed(response, "event_duel.html")
        self.assertContains(response, reverse("league:create_event_duel", args=(self.event.id,)))

    def test_legacy_cover_does_not_leak_into_compact_duel_panel(self):
        DuelSettings.objects.create(cover_image="duel_theme/western.webp")
        second_event = Event.objects.create(
            season_year=2026,
            name="Second Desert Grand Prix",
            round_number=2,
            deadline=timezone.now() + timedelta(days=3),
            race_datetime=timezone.now() + timedelta(days=4),
        )
        self.client.force_login(self.challenger)

        first_page = self.client.get(reverse("league:event_detail", args=(self.event.id,)))
        second_page = self.client.get(reverse("league:event_detail", args=(second_event.id,)))
        for page in (first_page, second_page):
            self.assertNotContains(page, "/media/duel_theme/western.webp")
            self.assertContains(page, 'class="stage-duel mb-4"')
        self.assertEqual(DuelSettings.objects.get().cover_image.name, "duel_theme/western.webp")

    @patch("league.telegram_bot.send_message")
    def test_duel_actions_do_not_notify_telegram_while_disabled(self, send_message):
        challenger_profile = self.challenger.league_profile
        challenger_profile.telegram_chat_id = 111
        challenger_profile.telegram_notifications = True
        challenger_profile.save(update_fields=("telegram_chat_id", "telegram_notifications", "updated_at"))
        opponent_profile = self.opponent.league_profile
        opponent_profile.telegram_chat_id = 222
        opponent_profile.telegram_notifications = True
        opponent_profile.save(update_fields=("telegram_chat_id", "telegram_notifications", "updated_at"))

        self.client.force_login(self.challenger)
        self.client.post(
            reverse("league:create_event_duel", args=(self.event.id,)),
            {"opponent": self.opponent.id, "stake": 6},
        )
        duel = DuelChallenge.objects.get()

        self.client.force_login(self.opponent)
        self.client.post(
            reverse("league:respond_event_duel", kwargs={"duel_id": duel.id, "action": "accept"})
        )
        send_message.assert_not_called()
