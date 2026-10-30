from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from .leagues import create_league, enroll_member
from .models import Event, Prediction, Season
from .prediction_presence import prediction_presence
from .prediction_submission import save_shared_prediction


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class PredictionPresenceTests(TestCase):
    def setUp(self):
        self.now = datetime(2027, 3, 1, 12, tzinfo=dt_timezone.utc)
        self.clock = patch('django.utils.timezone.now', return_value=self.now)
        self.clock_mock = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.season = Season.objects.create(year=2027, is_active=True)
        self.owner = User.objects.create_user('owner')
        self.player = User.objects.create_user('player')
        self.outsider = User.objects.create_user('outsider')
        self.event = Event.objects.create(name='Monaco', season_year=2027, round_number=6,
            deadline=self.now+timedelta(days=1), race_datetime=self.now+timedelta(days=2))
        self.next = Event.objects.create(name='Canada', season_year=2027, round_number=7,
            deadline=self.now+timedelta(days=8), race_datetime=self.now+timedelta(days=9))
        self.ls = create_league(owner=self.owner, name='Friends', season=self.season,
            start_event=self.event, ruleset='paddock')
        self.entry = enroll_member(actor=self.owner, league_season=self.ls, user=self.player)
        self.url = reverse('league:friend_league_prediction_status', args=[self.ls.league_id])
        self.detail = reverse('league:friend_league', args=[self.ls.league_id])
        self.client.force_login(self.owner)
        self.values = dict(p1='russell', p2='leclerc', p3='norris', pole='russell',
            fastest_lap='russell', driver_of_day='russell', safety_car_count=0, dnf_count=0,
            crazy_prediction='Private words must never leave this endpoint')

    def save_prediction(self, user=None):
        form, prediction = save_shared_prediction(user=user or self.player,
            event=self.event, data=self.values)
        self.assertTrue(form.is_valid(), form.errors)
        return prediction

    def test_saved_status_comes_from_server_and_never_returns_answers(self):
        self.assertEqual(self.client.get(self.url).json()['saved'], 0)
        self.save_prediction()
        response = self.client.get(self.url)
        data = response.json()
        self.assertEqual(data['event']['id'], self.event.pk)
        self.assertEqual(data['statuses'], {str(self.owner.pk): 'missing', str(self.player.pk): 'saved'})
        self.assertEqual((data['saved'], data['eligible']), (1, 2))
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(set(data), {'event', 'statuses', 'saved', 'eligible'})
        for secret in ('Private words', 'russell', 'leclerc', 'crazy_prediction', 'submitted_at'):
            self.assertNotIn(secret, response.content.decode())
        page = self.client.get(self.detail)
        self.assertContains(page, 'data-presence-state="saved"')
        self.assertContains(page, 'data-presence-state="missing"')
        self.assertContains(page, 'data-presence-count>1 / 2')
        self.assertNotContains(page, self.values['crazy_prediction'])

    def test_empty_placeholder_and_invalid_submission_are_not_saved(self):
        prediction = Prediction.objects.create(user=self.player, event=self.event)
        self.assertEqual(self.client.get(self.url).json()['statuses'][str(self.player.pk)], 'missing')
        for key, value in self.values.items():
            setattr(prediction, key, value)
        prediction.p2 = prediction.p1
        prediction.save()
        self.assertEqual(self.client.get(self.url).json()['saved'], 0)
        prediction.p2 = 'leclerc'
        prediction.save()
        # Complete legacy forecasts did not have a submitted_at timestamp.
        self.assertEqual(self.client.get(self.url).json()['saved'], 1)

    def test_sprint_requires_both_extra_answers(self):
        self.event.has_sprint = True
        self.event.save(update_fields=['has_sprint'])
        Prediction.objects.create(user=self.player, event=self.event, **self.values)
        self.assertEqual(self.client.get(self.url).json()['saved'], 0)
        Prediction.objects.filter(user=self.player).update(sprint_winner='russell', sprint_qualifying_winner='norris')
        self.assertEqual(self.client.get(self.url).json()['saved'], 1)

    def test_membership_and_season_scope(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.assertEqual(self.client.get(self.url, {'year': 2028}).status_code, 404)
        Prediction.objects.create(user=self.outsider, event=self.event, **self.values)
        self.assertNotIn(str(self.outsider.pk), self.client.get(self.url).json()['statuses'])
        self.entry.membership.is_active = False
        self.entry.membership.save(update_fields=['is_active'])
        self.client.force_login(self.player)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_future_entry_is_neutral_and_not_in_denominator(self):
        self.entry.first_event = self.next
        self.entry.save(update_fields=['first_event'])
        self.save_prediction()
        data = self.client.get(self.url).json()
        self.assertEqual(data['statuses'][str(self.player.pk)], 'ineligible')
        self.assertEqual((data['saved'], data['eligible']), (0, 1))

    def test_deadline_and_current_stage_rollover(self):
        self.save_prediction()
        self.clock_mock.return_value = self.event.deadline+timedelta(seconds=1)
        data = self.client.get(self.url).json()
        self.assertTrue(data['event']['closed'])
        self.assertEqual(data['saved'], 1)
        self.clock_mock.return_value = self.event.race_datetime+timedelta(hours=2, seconds=1)
        data = self.client.get(self.url).json()
        self.assertEqual(data['event']['id'], self.next.pk)
        self.assertEqual(data['saved'], 0)
        self.clock_mock.return_value = self.next.race_datetime+timedelta(hours=2, seconds=1)
        self.assertIsNone(self.client.get(self.url).json()['event'])

    def test_other_events_and_late_predictions_do_not_count(self):
        Prediction.objects.create(user=self.player, event=self.next, **self.values)
        late = Prediction.objects.create(user=self.owner, event=self.event, **self.values)
        Prediction.objects.filter(pk=late.pk).update(created_at=self.event.deadline+timedelta(seconds=1))
        self.assertEqual(self.client.get(self.url).json()['saved'], 0)

    def test_presence_queries_do_not_grow_per_member(self):
        for index in range(15):
            user = User.objects.create_user(f'friend{index}')
            enroll_member(actor=self.owner, league_season=self.ls, user=user)
        with self.assertNumQueries(3):
            data = prediction_presence(self.ls)
        self.assertEqual(data['eligible'], 17)
