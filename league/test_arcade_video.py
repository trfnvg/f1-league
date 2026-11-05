import json
from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import arcade_video as video
from .models import ArcadeAttempt, ArcadeBestVideo, ArcadeRecord, ArcadeVideoUpload, DoodleAttempt, DoodleRecord, TetrisAttempt, TetrisRecord


@override_settings(USE_S3=True, STORAGES={
    'default': {'BACKEND':'django.core.files.storage.InMemoryStorage'},
    'staticfiles': {'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class ArcadeVideoTests(TestCase):
    def setUp(self):
        self.player=User.objects.create_user('video-player')
        self.other=User.objects.create_user('other-video-player')
        self.client.force_login(self.player)
        self.end=timezone.now()
        self.attempt=ArcadeAttempt.objects.create(user=self.player,score=10,finished_at=self.end)
        ArcadeAttempt.objects.filter(pk=self.attempt.pk).update(started_at=self.end-timedelta(seconds=20))
        self.record=ArcadeRecord.objects.create(user=self.player,best_score=10,total_attempts=1)
        self.body=b'\x1aE\xdf\xa3'+b'video-test'*10
        self.s3=Mock()
        self.s3.create_multipart_upload.return_value={'UploadId':'provider-id'}
        self.s3.upload_part.return_value={'ETag':'etag'}
        self.s3.head_object.return_value={'ContentLength':len(self.body)}
        self.stub=patch('league.arcade_video.s3',return_value=(self.s3,'public-bucket'))
        self.stub.start();self.addCleanup(self.stub.stop)

    def init(self, **changes):
        payload={'game':'flappy','attempt_id':self.attempt.pk,'mime':'video/webm','size':len(self.body),'duration_ms':20000}
        return self.client.post(reverse('league:arcade_video_init'),{**payload,**changes},content_type='application/json')

    def upload(self):
        response=self.init();self.assertEqual(response.status_code,200,response.content)
        data=response.json()
        response=self.client.post(data['part_url'],{'part':1,'chunk':SimpleUploadedFile('part',self.body)})
        self.assertEqual(response.status_code,200,response.content)
        return data

    def test_only_current_owned_nonmanual_nonexcluded_record_is_accepted(self):
        self.assertEqual(self.init().status_code,200)
        self.client.force_login(self.other)
        self.assertEqual(self.init().status_code,409)
        self.client.force_login(self.player)
        for changes in ({'is_excluded':True},{'is_manual':True},{'finished_at':None}):
            ArcadeAttempt.objects.filter(pk=self.attempt.pk).update(**changes)
            self.assertEqual(self.init().status_code,409)
            ArcadeAttempt.objects.filter(pk=self.attempt.pk).update(is_excluded=False,is_manual=False,finished_at=self.end)
        self.record.best_score=20;self.record.save()
        self.assertEqual(self.init().status_code,409)

    def test_complete_replaces_only_after_full_upload_and_deletes_old_on_commit(self):
        old=ArcadeBestVideo.objects.create(user=self.player,game_key='flappy',attempt_id=999,score=5,
            video='arcade-videos/old.webm',duration_ms=1000,size=100)
        data=self.upload()
        with patch('league.arcade_video.default_storage.delete') as delete, self.captureOnCommitCallbacks(execute=True):
            result=self.client.post(data['complete_url'],{},content_type='application/json')
            self.assertEqual(result.status_code,200,result.content)
        delete.assert_called_once_with('arcade-videos/old.webm')
        self.assertEqual(ArcadeBestVideo.objects.count(),1)
        old.refresh_from_db();self.assertEqual((old.attempt_id,old.score),(self.attempt.pk,10))
        self.assertEqual(self.client.post(data['complete_url'],{},content_type='application/json').status_code,200)

    def test_incomplete_failed_and_superseded_uploads_keep_previous_video(self):
        old=ArcadeBestVideo.objects.create(user=self.player,game_key='flappy',attempt_id=999,score=5,
            video='arcade-videos/old.webm',duration_ms=1000,size=100)
        data=self.init().json()
        self.assertEqual(self.client.post(data['complete_url'],{},content_type='application/json').status_code,409)
        data=self.upload()
        self.s3.complete_multipart_upload.side_effect=RuntimeError('storage unavailable')
        with self.assertLogs('league.arcade_video',level='ERROR'):
            self.assertEqual(self.client.post(data['complete_url'],{},content_type='application/json').status_code,503)
        self.s3.complete_multipart_upload.side_effect=None
        self.record.best_score=30;self.record.save()
        self.assertEqual(self.client.post(data['complete_url'],{},content_type='application/json').status_code,409)
        old.refresh_from_db();self.assertEqual(old.video.name,'arcade-videos/old.webm')

    def test_no_arbitrary_files_part_order_or_oversized_claims(self):
        self.assertEqual(self.init(size=video.MAX_SIZE+1).status_code,400)
        self.assertEqual(self.init(mime='text/html').status_code,400)
        data=self.init().json()
        for number,body in ((0,self.body),(2,self.body),(1,b'<script>alert(1)</script>')):
            result=self.client.post(data['part_url'],{'part':number,'chunk':SimpleUploadedFile('bad.html',body)})
            self.assertEqual(result.status_code,400)
        self.assertFalse(self.s3.upload_part.called)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(data['part_url'],{'part':1,'chunk':SimpleUploadedFile('part',self.body)}).status_code,404)

    def test_retried_parts_do_not_duplicate_bytes_and_s3_receives_stream(self):
        data=self.upload()
        response=self.client.post(data['part_url'],{'part':1,'chunk':SimpleUploadedFile('part',self.body)})
        self.assertEqual(response.json()['received'],len(self.body))
        self.assertEqual(self.s3.upload_part.call_count,1)
        self.assertTrue(hasattr(self.s3.upload_part.call_args.kwargs['Body'],'read'))

    def test_csrf_auth_and_preview_config(self):
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.player)
        self.assertEqual(csrf.post(reverse('league:arcade_video_init'),{},content_type='application/json').status_code,403)
        self.client.logout()
        self.assertEqual(self.init().status_code,302)
        request=Mock(user=self.player)
        self.assertIsNone(video.config(request,'flappy',True))
        with override_settings(USE_S3=False):
            self.assertIsNone(video.config(request,'flappy'))

    def test_admin_player_and_attempt_detail_have_video_but_players_cannot_access(self):
        ArcadeBestVideo.objects.create(user=self.player,game_key='flappy',attempt_id=self.attempt.pk,score=10,
            video='arcade-videos/test.webm',duration_ms=20000,size=100)
        admin=User.objects.create_superuser('video-admin','admin@example.com','test')
        self.client.force_login(admin)
        page=self.client.get(reverse('admin:league_arcadebestvideo_changelist'))
        self.assertContains(page,'video-player')
        page=self.client.get(reverse('admin:league_arcadeattempt_change',args=[self.attempt.pk]))
        self.assertContains(page,'<video controls')
        self.assertContains(page,'arcade-videos/test.webm')
        self.client.force_login(self.player)
        self.assertEqual(self.client.get(reverse('admin:league_arcadebestvideo_changelist')).status_code,302)

    def test_cleanup_aborts_expired_sessions_and_retries_old_object_deletion(self):
        data=self.init().json()
        upload=ArcadeVideoUpload.objects.get(pk=data['id'])
        ArcadeVideoUpload.objects.filter(pk=upload.pk).update(created_at=self.end-timedelta(days=2))
        with patch('league.arcade_video.default_storage.delete') as delete:
            video.cleanup()
        self.assertFalse(ArcadeVideoUpload.objects.exists())
        self.assertTrue(self.s3.abort_multipart_upload.called)
        self.assertTrue(delete.called)

    def test_each_published_game_requires_its_own_confirmed_record(self):
        for game, Attempt, Record in [('doodle_jump',DoodleAttempt,DoodleRecord),('tetris',TetrisAttempt,TetrisRecord)]:
            kwargs={'seed':19} if game=='tetris' else {}
            attempt=Attempt.objects.create(user=self.player,score=100,finished_at=self.end,**kwargs)
            Record.objects.create(user=self.player,best_score=100,total_attempts=1)
            self.assertEqual(self.init(game=game,attempt_id=attempt.pk).status_code,200)

    def test_multi_part_file_is_streamed_in_order_and_needs_the_last_part(self):
        first=b'\x1aE\xdf\xa3'+b'\0'*(video.PART_SIZE-4)
        last=b'last-video-bytes'
        self.s3.head_object.return_value={'ContentLength':len(first)+len(last)}
        data=self.init(size=len(first)+len(last)).json()
        result=self.client.post(data['part_url'],{'part':1,'chunk':SimpleUploadedFile('part',first)})
        self.assertEqual(result.status_code,200,result.content)
        self.assertEqual(result.json()['received'],len(first))
        self.assertEqual(self.client.post(data['complete_url'],{},content_type='application/json').status_code,409)
        result=self.client.post(data['part_url'],{'part':2,'chunk':SimpleUploadedFile('part',last)})
        self.assertEqual(result.status_code,200,result.content)
        self.assertEqual(self.client.post(data['complete_url'],{},content_type='application/json').status_code,200)
        self.assertEqual([call.kwargs['ContentLength'] for call in self.s3.upload_part.call_args_list],[len(first),len(last)])
        self.assertEqual(ArcadeBestVideo.objects.get().size,len(first)+len(last))
