from datetime import timedelta

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import arcade_library as library
from .arcade_moderation import create_manual, set_excluded
from .models import (ArcadeAttempt, ArcadeCompetition, ArcadeRecord, ArcadeWheelSpin, DoodleAttempt,
    Event, MinesweeperAttempt, Prediction, TetrisAttempt)
from .views import _minesweeper_leaderboard_data


@override_settings(STORAGES={
    'default': {'BACKEND':'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class ArcadeModerationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('audit-admin', 'admin@example.com', 'test')
        self.player = User.objects.create_user('driver-one')
        self.other = User.objects.create_user('driver-two')
        self.end = timezone.now()-timedelta(minutes=1)
        self.start = self.end-timedelta(minutes=5)
        self.client.force_login(self.admin)

    def manual(self, model=ArcadeAttempt, **kwargs):
        data = dict(actor=self.admin, model=model, user=self.player, started_at=self.start,
            finished_at=self.end, reason='Восстановлен потерянный результат', score=20)
        if model is MinesweeperAttempt:
            data.pop('score')
            data['elapsed_ms'] = 12000
        return create_manual(**{**data, **kwargs})

    def toggle(self, attempt, excluded=True, actor=None):
        return set_excluded(actor=actor or self.admin, model=type(attempt), attempt_id=attempt.pk,
            excluded=excluded, reason='Проверка администратором')

    def contest(self, key='flappy', frozen=False):
        event = Event.objects.create(name='Moderation GP', season_year=2099, round_number=1,
            deadline=self.end+timedelta(seconds=30), race_datetime=self.end+timedelta(days=2))
        return ArcadeCompetition.objects.create(event=event, game_key=key,
            opened_at=self.start-timedelta(minutes=1), frozen_at=timezone.now() if frozen else None)

    def test_manual_add_exclude_restore_updates_all_point_games_without_deletion(self):
        for model, key in ((ArcadeAttempt,'flappy'),(DoodleAttempt,'doodle_jump'),(TetrisAttempt,'tetris')):
            with self.subTest(game=key):
                low = self.manual(model, score=10)
                high = self.manual(model, score=30)
                _, Record = library.models_for(key)
                record = Record.objects.get(user=self.player)
                self.assertEqual((record.best_score,record.total_attempts),(30,2))
                self.assertTrue(high.is_manual)
                self.assertEqual(high.started_at,self.start)
                excluded = self.toggle(high)
                record.refresh_from_db()
                self.assertEqual((record.best_score,record.total_attempts),(10,1))
                self.assertEqual(excluded.score,30)
                self.assertTrue(model.objects.filter(pk=high.pk).exists())
                self.toggle(high,False)
                record.refresh_from_db()
                self.assertEqual((record.best_score,record.total_attempts),(30,2))
                # Repeated clicks must not double-count or rewrite audit history.
                count = LogEntry.objects.count()
                self.toggle(high,False)
                self.assertEqual(LogEntry.objects.count(),count)
        self.assertEqual(LogEntry.objects.filter(user=self.admin).count(),12)

    def test_cached_legacy_record_and_attempt_count_survive_later_corrections(self):
        original = ArcadeRecord.objects.create(user=self.player,best_score=100,total_attempts=50)
        attempt = self.manual(score=200)
        self.toggle(attempt)
        record = ArcadeRecord.objects.get(user=self.player)
        self.assertEqual((record.best_score,record.total_attempts),(100,50))
        self.assertEqual(record.updated_at,original.updated_at)
        self.toggle(attempt,False)
        record.refresh_from_db()
        self.assertEqual((record.best_score,record.total_attempts),(200,51))

    def test_contest_and_frozen_snapshot_are_rebuilt(self):
        contest = self.contest(frozen=True)
        a = self.manual(competition=contest,score=15)
        b = self.manual(competition=contest,score=25,user=self.other)
        contest.refresh_from_db()
        frozen_at = contest.frozen_at
        self.assertEqual(contest.standings[0]['user_id'],self.other.pk)
        self.toggle(b)
        contest.refresh_from_db()
        self.assertEqual(contest.standings[0]['user_id'],self.player.pk)
        self.assertEqual(contest.total_attempts,1)
        self.assertEqual(contest.frozen_at,frozen_at)
        self.assertEqual(library.contest_rows(contest)[1],1)
        self.toggle(b,False)
        contest.refresh_from_db()
        self.assertEqual(contest.standings[0]['user_id'],self.other.pk)

    def test_wheel_winner_changes_roll_back_everything(self):
        contest = self.contest(frozen=True)
        a = self.manual(competition=contest,score=15)
        b = self.manual(competition=contest,score=25,user=self.other)
        Prediction.objects.create(user=self.other,event=contest.event)
        ArcadeWheelSpin.objects.create(event=contest.event,winner=self.other,winner_score=25,prize='pit_wall')
        before = LogEntry.objects.count()
        with self.assertRaises(ValidationError):
            self.toggle(b)
        b.refresh_from_db()
        self.assertFalse(b.is_excluded)
        self.assertEqual(ArcadeRecord.objects.get(user=self.other).best_score,25)
        self.assertEqual(LogEntry.objects.count(),before)
        self.assertEqual(ArcadeWheelSpin.objects.get().winner_id,self.other.pk)

    def test_minesweeper_counts_and_best_time_follow_moderation(self):
        attempt = self.manual(MinesweeperAttempt)
        data = _minesweeper_leaderboard_data(self.player,attempt.week_start)
        self.assertEqual((data['best_time_ms'],data['attempts']),(12000,1))
        self.toggle(attempt)
        data = _minesweeper_leaderboard_data(self.player,attempt.week_start)
        self.assertEqual((data['best_time_ms'],data['attempts']),(None,0))
        self.toggle(attempt,False)
        self.assertEqual(_minesweeper_leaderboard_data(self.player,attempt.week_start)['best_time_ms'],12000)

    def test_invalid_times_scores_wrong_contest_and_missing_reason_do_not_create_rows(self):
        contest = self.contest('tetris')
        for values in ({'score':-1},{'score':501},{'score':True},{'reason':' '},
                {'finished_at':self.start-timedelta(seconds=1)}, {'finished_at':timezone.now()+timedelta(days=1)},
                {'competition':contest}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self.manual(**values)
        self.assertFalse(ArcadeAttempt.objects.exists())
        self.assertFalse(ArcadeRecord.objects.exists())
        self.assertFalse(LogEntry.objects.exists())

    def test_public_permissions_get_and_csrf_cannot_moderate(self):
        attempt = self.manual()
        url = reverse('admin:league_arcadeattempt_moderate',args=[attempt.pk])
        manual_url = reverse('admin:league_arcadeattempt_manual')
        page = self.client.get(url)
        self.assertContains(page,'Причина изменения')
        self.assertFalse(ArcadeAttempt.objects.get().is_excluded)
        self.assertContains(self.client.get(manual_url),'Глобальный рейтинг')
        self.assertContains(self.client.get(reverse('admin:league_arcadeattempt_changelist')),manual_url)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.admin)
        self.assertEqual(csrf.post(url,{'excluded':'1','reason':'test'}).status_code,403)
        viewer = User.objects.create_user('audit-viewer',is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename='view_arcadeattempt'))
        self.client.force_login(viewer)
        self.assertEqual(self.client.post(url,{'excluded':'1','reason':'test'}).status_code,403)
        self.assertEqual(self.client.post(manual_url,{}).status_code,403)
        with self.assertRaises(PermissionDenied):
            self.toggle(attempt,actor=viewer)

    def test_admin_forms_create_and_toggle_and_show_history(self):
        url = reverse('admin:league_tetrisattempt_manual')
        data = {'user':self.player.pk,'started_at':self.start.isoformat(),'finished_at':self.end.isoformat(),
            'score':1234,'competition':'','reason':'Ручная корректировка'}
        page = self.client.post(url,data,follow=True)
        self.assertEqual(page.status_code,200)
        attempt = TetrisAttempt.objects.get()
        self.assertContains(page,'Добавлена администратором')
        self.assertContains(page,'Исключить из зачёта')
        url = reverse('admin:league_tetrisattempt_moderate',args=[attempt.pk])
        page = self.client.post(url,{'excluded':'1','reason':'Сверено с видео'},follow=True)
        self.assertContains(page,'Вернуть в зачёт')
        attempt.refresh_from_db()
        self.assertTrue(attempt.is_excluded)
        history = self.client.get(reverse('admin:league_tetrisattempt_history',args=[attempt.pk]))
        self.assertContains(history,'Сверено с видео')
        self.assertContains(history,'Ручная корректировка')

    def test_excluded_unfinished_run_cannot_reappear_in_global_record_on_finish(self):
        for model, key, url_name in ((ArcadeAttempt,'flappy','arcade_run_finish'),
                (DoodleAttempt,'doodle_jump','doodle_attempt_finish'),(TetrisAttempt,'tetris','tetris_attempt_finish')):
            with self.subTest(game=key):
                options = {'seed':19} if model is TetrisAttempt else {}
                attempt = model.objects.create(user=self.player,**options)
                model.objects.filter(pk=attempt.pk).update(started_at=timezone.now()-timedelta(seconds=25))
                self.toggle(attempt)
                payload = {'attempt_id':attempt.pk,'score':10}
                if model is TetrisAttempt:
                    from .test_arcade_tetris import finished_replay
                    proof, score = finished_replay(19)
                    payload = {**proof,'attempt_id':attempt.pk}
                self.client.force_login(self.player)
                page = self.client.post(reverse('league:'+url_name),payload,content_type='application/json')
                self.assertEqual(page.status_code,200,page.content)
                _, Record = library.models_for(key)
                record = Record.objects.get(user=self.player)
                self.assertEqual((record.best_score,record.total_attempts),(0,0))
                attempt.refresh_from_db()
                self.assertTrue(attempt.is_excluded)
                self.assertIsNotNone(attempt.finished_at)
                self.assertIsNotNone(attempt.score)
                self.toggle(attempt,False)
                record.refresh_from_db()
                self.assertEqual(record.best_score,attempt.score)
                self.assertEqual(record.total_attempts,1)
                self.client.force_login(self.admin)
