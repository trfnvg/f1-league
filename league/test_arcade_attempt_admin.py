from datetime import timedelta

from django.contrib import admin
from django.contrib.auth.models import Permission, User
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .admin import attempt_duration
from .models import ArcadeAttempt, ArcadeCompetition, DoodleAttempt, Event, MinesweeperAttempt, TetrisAttempt


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class ArcadeAttemptAdminTests(TestCase):
    models = (ArcadeAttempt, DoodleAttempt, TetrisAttempt, MinesweeperAttempt)

    def setUp(self):
        self.staff = User.objects.create_superuser('logs-admin', 'admin@example.com', 'test')
        self.player = User.objects.create_user('logs-player', first_name='Тестовый игрок')
        self.other = User.objects.create_user('other-player')
        self.client.force_login(self.staff)
        self.end = timezone.now()

    def create_attempt(self, model, **kwargs):
        defaults = {'seed': 123} if model is TetrisAttempt else {}
        if model is MinesweeperAttempt:
            defaults['week_start'] = timezone.localdate()
        attempt = model.objects.create(user=self.player, **{**defaults, **kwargs})
        model.objects.filter(pk=attempt.pk).update(started_at=self.end-timedelta(seconds=65, milliseconds=250))
        attempt.refresh_from_db()
        return attempt

    def url(self, model, action='changelist', obj=None):
        return reverse(f'admin:league_{model._meta.model_name}_{action}', args=[obj.pk] if obj else [])

    def test_all_games_have_read_only_logs_with_search_and_duration(self):
        for model in self.models:
            with self.subTest(game=model.__name__):
                kwargs = {'completed': True, 'elapsed_ms': 5000} if model is MinesweeperAttempt else {'score': 0}
                attempt = self.create_attempt(model, finished_at=self.end, **kwargs)
                page = self.client.get(self.url(model))
                self.assertContains(page, 'Тестовый игрок')
                self.assertContains(page, '00:01:05.250')
                self.assertContains(page, 'Длительность (сервер)')
                self.assertNotContains(page, 'action-checkbox')
                self.assertEqual(list(self.client.get(self.url(model), {'q':'@logs-player'}).context['cl'].queryset), [attempt])
                self.assertEqual(self.client.get(self.url(model), {'q':'unknown-player'}).context['cl'].result_count, 0)
                detail = self.client.get(self.url(model, 'change', attempt))
                self.assertContains(detail, 'Игровое время')
                self.assertNotContains(detail, 'name="_save"')
                self.assertEqual(self.client.post(self.url(model, 'change', attempt), {'score': 99999}).status_code, 403)
                self.assertEqual(self.client.post(self.url(model, 'delete', attempt), {'post':'yes'}).status_code, 403)
                self.assertEqual(self.client.get(self.url(model, 'add')).status_code, 403)
                self.assertTrue(model.objects.filter(pk=attempt.pk).exists())
                if model is not MinesweeperAttempt:
                    attempt.refresh_from_db()
                    self.assertEqual(attempt.score, 0)

    def test_status_filters_and_sorting_include_unfinished_and_rejected(self):
        for model in self.models:
            with self.subTest(game=model.__name__):
                unfinished = self.create_attempt(model)
                rejected = self.create_attempt(model, finished_at=self.end)
                kwargs = {'completed': True, 'elapsed_ms': 3000} if model is MinesweeperAttempt else {'score': 0}
                saved = self.create_attempt(model, finished_at=self.end, **kwargs)
                model.objects.filter(pk=saved.pk).update(started_at=self.end-timedelta(seconds=3))
                for state, attempt in [('unfinished',unfinished), ('no_result',rejected), ('saved',saved)]:
                    response = self.client.get(self.url(model), {'run_status':state})
                    self.assertEqual(list(response.context['cl'].queryset.values_list('pk',flat=True)), [attempt.pk])
                response = self.client.get(self.url(model), {'o':'6', 'finished_at__isnull':'False'})
                self.assertEqual(list(response.context['cl'].queryset.values_list('pk',flat=True)), [saved.pk,rejected.pk])
                model_admin = admin.site._registry[model]
                self.assertEqual(model_admin.wall_duration(unfinished), '—')
                self.assertEqual(model_admin.run_status(unfinished), 'Не завершена')

    def test_game_time_is_separate_from_server_duration(self):
        tetris = self.create_attempt(TetrisAttempt, finished_at=self.end, score=100, ticks=150)
        mines = self.create_attempt(MinesweeperAttempt, finished_at=self.end, completed=True, elapsed_ms=4567)
        self.assertEqual(admin.site._registry[TetrisAttempt].active_duration(tetris), '00:00:02.500')
        self.assertEqual(admin.site._registry[MinesweeperAttempt].active_duration(mines), '00:00:04.567')
        self.assertEqual(admin.site._registry[TetrisAttempt].wall_duration(tetris), '00:01:05.250')

    def test_logs_require_model_view_permission(self):
        viewer = User.objects.create_user('log-viewer', is_staff=True)
        for model in self.models:
            self.create_attempt(model)
            self.client.force_login(viewer)
            self.assertEqual(self.client.get(self.url(model)).status_code, 403)
            permission = Permission.objects.get(content_type__app_label='league', codename=f'view_{model._meta.model_name}')
            viewer.user_permissions.add(permission)
            self.assertEqual(self.client.get(self.url(model)).status_code, 200)
        self.client.force_login(self.player)
        self.assertEqual(self.client.get(self.url(ArcadeAttempt)).status_code, 302)
        self.client.logout()
        self.assertEqual(self.client.get(self.url(ArcadeAttempt)).status_code, 302)

    def test_duration_format_does_not_wrap_hours_or_invent_unknown_times(self):
        self.assertEqual(attempt_duration(3600123), '01:00:00.123')
        self.assertEqual(attempt_duration(0), '00:00:00.000')
        self.assertEqual(attempt_duration(-1), '—')
        self.assertEqual(attempt_duration(None), '—')

    def test_stage_and_player_data_are_batched_and_large_replays_are_deferred(self):
        event = Event.objects.create(name='Audit GP', season_year=2099, round_number=1,
            deadline=self.end+timedelta(days=1))
        contest = ArcadeCompetition.objects.create(event=event, game_key='tetris')
        for _ in range(3):
            self.create_attempt(TetrisAttempt, competition=contest, score=10, finished_at=self.end,
                replay=[[1,0],[2,1]])
        model_admin = admin.site._registry[TetrisAttempt]
        request = RequestFactory().get(self.url(TetrisAttempt))
        request.user = self.staff
        with self.assertNumQueries(1):
            for obj in model_admin.get_queryset(request):
                self.assertIn('Тестовый игрок', model_admin.player(obj))
                self.assertIn('Audit GP · 2099', model_admin.competition_label(obj))
                self.assertIn('replay', obj.get_deferred_fields())
                self.assertEqual(model_admin.wall_duration(obj), '00:01:05.250')
