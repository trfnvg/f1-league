import io
import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from .auth_limits import bucket_key, consume
from .forms import AvatarUploadForm
from .models import ArcadeAttempt, ArcadeRecord, AuthRateBucket, DoodleAttempt, DoodleRecord


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class ArcadeSecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("secure63", password="RaceStart!63")
        self.other = User.objects.create_user("other63", password="RaceStart!63")
        self.client.force_login(self.user)

    def start(self, game="doodle"):
        return self.client.post(reverse("league:doodle_attempt_start" if game == "doodle" else "league:arcade_run_start")).json()

    def send(self, run, score_value, *, progress=False, game="doodle", client=None, **changes):
        name = ("doodle_attempt_" if game == "doodle" else "arcade_run_") + ("progress" if progress else "finish")
        return (client or self.client).post(reverse("league:"+name), data=json.dumps({
            "attempt_id": run["attempt_id"], "run_token": run["run_token"], "score": score_value, **changes}),
            content_type="application/json")

    def test_immediate_forged_huge_score_is_rejected_and_cannot_win_anything(self):
        run = self.start()
        self.assertEqual(self.send(run, 2_147_483_647).status_code, 400)
        attempt = DoodleAttempt.objects.get(pk=run["attempt_id"])
        self.assertIsNone(attempt.score)
        self.assertIsNotNone(attempt.finished_at)
        self.assertIn("rejected", attempt.verification)
        self.assertEqual(DoodleRecord.objects.get(user=self.user).best_score, 0)
        self.assertEqual(self.send(run, 10).status_code, 409)

    def test_normal_checkpoints_and_single_finish_update_server_record(self):
        run = self.start()
        start = DoodleAttempt.objects.get(pk=run["attempt_id"]).started_at
        for second, score in ((10, 300), (20, 600), (30, 700)):
            with patch("league.arcade_validation.timezone.now", return_value=start+timedelta(seconds=second)):
                self.assertEqual(self.send(run, score, progress=True).status_code, 200)
        self.assertEqual(DoodleRecord.objects.get(user=self.user).best_score, 0)
        with patch("league.arcade_validation.timezone.now", return_value=start+timedelta(seconds=31)):
            self.assertEqual(self.send(run, 700).status_code, 200)
            self.assertEqual(self.send(run, 701).status_code, 409)
        self.assertEqual(DoodleRecord.objects.get(user=self.user).best_score, 700)

    def test_other_user_other_session_wrong_token_and_cross_game_cannot_submit(self):
        run = self.start()
        stranger = Client()
        stranger.force_login(self.other)
        self.assertEqual(self.send(run, 10, client=stranger).status_code, 409)
        second_session = Client()
        second_session.force_login(self.user)
        self.assertEqual(self.send(run, 10, client=second_session).status_code, 403)
        self.assertEqual(self.send(run, 10, run_token="a"*43).status_code, 403)
        self.assertEqual(self.send(run, 10, game="flappy").status_code, 409)
        self.assertIsNone(DoodleAttempt.objects.get(pk=run["attempt_id"]).finished_at)
        self.assertEqual(self.send(run, 10).status_code, 200)

    def test_starting_any_new_game_closes_old_attempt_but_preserves_records(self):
        run = self.start()
        self.start("flappy")
        self.assertIsNotNone(DoodleAttempt.objects.get(pk=run["attempt_id"]).finished_at)
        self.assertEqual(self.send(run, 10).status_code, 409)
        self.assertEqual(ArcadeAttempt.objects.filter(user=self.user, finished_at__isnull=True).count(), 1)

    def test_idle_or_expired_attempt_cannot_bank_time_and_finish_later(self):
        for seconds in (181, 12*3600+1):
            run = self.start()
            attempt = DoodleAttempt.objects.get(pk=run["attempt_id"])
            with patch("league.arcade_validation.timezone.now", return_value=attempt.started_at+timedelta(seconds=seconds)):
                self.assertEqual(self.send(run, 10).status_code, 400)
            self.assertIsNone(DoodleAttempt.objects.get(pk=attempt.pk).score)

    def test_monotonic_progress_and_time_jumps_are_checked(self):
        run = self.start()
        self.assertEqual(self.send(run, 50, progress=True).status_code, 200)
        self.assertEqual(self.send(run, 49, progress=True).status_code, 400)
        run = self.start()
        self.assertEqual(self.send(run, 100000, progress=True).status_code, 400)

    def test_flappy_has_server_time_checks_and_checkpoints(self):
        run = self.start("flappy")
        self.assertEqual(self.send(run, 500, game="flappy").status_code, 400)
        run = self.start("flappy")
        start = ArcadeAttempt.objects.get(pk=run["attempt_id"]).started_at
        with patch("league.arcade_validation.timezone.now", return_value=start+timedelta(seconds=10)):
            self.assertEqual(self.send(run, 3, game="flappy", progress=True).status_code, 200)
        with patch("league.arcade_validation.timezone.now", return_value=start+timedelta(seconds=20)):
            self.assertEqual(self.send(run, 10, game="flappy").status_code, 200)
        self.assertEqual(ArcadeRecord.objects.get(user=self.user).best_score, 10)

    def test_payload_types_lengths_encoding_and_nested_json_fail_closed(self):
        run = self.start()
        for changes in ({"score": True}, {"score": -1}, {"score": 1.2}, {"score": "100"},
                        {"attempt_id": True}, {"attempt_id": 2**64}, {"run_token": ""}):
            self.assertEqual(self.send(run, 10, **changes).status_code, 400)
        for body in (b"\xff", b"["*1200+b"]"*1200, b"{}"+b" "*4096, b"[]", b"null"):
            response = self.client.post(reverse("league:doodle_attempt_finish"), body, content_type="application/json")
            self.assertEqual(response.status_code, 400)
        self.assertIsNone(DoodleAttempt.objects.get(pk=run["attempt_id"]).finished_at)

    def test_old_or_missing_token_cannot_use_new_endpoints(self):
        old = DoodleAttempt.objects.create(user=self.user)
        response = self.send({"attempt_id": old.pk, "run_token": "a"*43}, 10)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.post(reverse("league:doodle_attempt_finish"),
            data=json.dumps({"attempt_id": old.pk, "score": 999}), content_type="application/json").status_code, 400)

    def test_database_default_keeps_old_workers_compatible_during_rolling_deploy(self):
        # Simulate an old worker's INSERT without the newly added column.
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO league_doodleattempt (user_id, started_at) VALUES (%s, %s)",
                [self.user.pk, connection.ops.adapt_datetimefield_value(timezone.now())])
        self.assertEqual(DoodleAttempt.objects.get(user=self.user).verification, {})

    def test_staff_test_flags_cannot_write_scores_and_players_cannot_use_lab(self):
        self.assertEqual(self.client.post(reverse("league:minesweeper_attempt_start")+"?admin_test=1").status_code, 403)
        self.assertEqual(self.client.post(reverse("league:minesweeper_attempt_finish")+"?admin_test=1").status_code, 403)
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        run = self.start()
        self.assertIsNone(run["attempt_id"])
        self.assertFalse(DoodleAttempt.objects.exists())
        self.assertEqual(self.send({"attempt_id": 1, "run_token": "a"*43}, 999).status_code, 403)

    def test_csrf_authentication_no_cache_and_methods(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        for name in ("doodle_attempt_start", "doodle_attempt_progress", "doodle_attempt_finish",
                     "arcade_run_start", "arcade_run_progress", "arcade_run_finish"):
            self.assertEqual(strict.post(reverse("league:"+name)).status_code, 403)
            self.assertEqual(self.client.get(reverse("league:"+name)).status_code, 405)
        self.client.logout()
        response = self.client.post(reverse("league:doodle_attempt_start"))
        self.assertEqual(response.status_code, 401)
        self.assertIn("error", response.json())
        self.assertIn("no-store", self.client.get(reverse("league:doodle_leaderboard"))["Cache-Control"])

    def test_request_limits_block_before_creating_more_attempts(self):
        consume("arcade-start-user", str(self.user.pk), 120, 60)
        AuthRateBucket.objects.filter(pk=bucket_key("arcade-start-user", str(self.user.pk))).update(hits=120)
        response = self.client.post(reverse("league:doodle_attempt_start"))
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)
        self.assertFalse(DoodleAttempt.objects.exists())

    def test_signup_and_current_password_are_rate_limited_separately(self):
        for scope, value, limit, path in (
            ("register-ip", "127.0.0.1", 20, "league:register"),
            ("account-settings-user", str(self.user.pk), 10, "league:account_settings")):
            consume(scope, value, limit, 900)
            AuthRateBucket.objects.filter(pk=bucket_key(scope, value)).update(hits=limit)
            if scope == "register-ip":
                self.client.logout()
            else:
                self.client.force_login(self.user)
            response = self.client.post(reverse(path), {})
            self.assertEqual(response.status_code, 429)

    def test_avatar_is_bounded_and_reencoded_without_appended_payload(self):
        output = io.BytesIO()
        Image.new("RGBA", (40, 20), (255, 0, 0, 128)).save(output, "PNG")
        raw = output.getvalue()+b"<script>alert(1)</script>"
        upload = SimpleUploadedFile("portrait.png", raw, "image/png")
        form = AvatarUploadForm({}, {"avatar": upload}, instance=self.user.league_profile)
        self.assertTrue(form.is_valid(), form.errors)
        clean = form.cleaned_data["avatar"]
        self.assertTrue(clean.name.endswith(".webp"))
        self.assertNotIn(b"<script>", clean.read())
        huge = SimpleUploadedFile("portrait.png", raw+b" "*(5*1024*1024), "image/png")
        form = AvatarUploadForm({}, {"avatar": huge}, instance=self.user.league_profile)
        self.assertIn("avatar", form.errors)

    @override_settings(SECRET_KEY="should-never-appear-in-report", ALLOWED_HOSTS=["*"], DEBUG=False)
    def test_config_diagnostic_does_not_print_secrets(self):
        output = io.StringIO()
        call_command("security_audit", stdout=output)
        report = json.loads(output.getvalue())
        self.assertFalse(report["secret_key_strong"])
        self.assertFalse(report["allowed_hosts_explicit"])
        self.assertNotIn("should-never-appear-in-report", output.getvalue())
        with self.assertRaises(CommandError):
            call_command("security_audit", strict=True, stdout=io.StringIO())

    @override_settings(SECRET_KEY="test-only-key-0123456789abcdefghijklmnopqrstuvwxyz-security-checks",
        ALLOWED_HOSTS=["testserver"], DEBUG=False, SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True,
        DATABASE_URL="sqlite:///:memory:")
    def test_strict_diagnostic_accepts_configured_deploy_and_rejects_missing_database(self):
        call_command("security_audit", strict=True, stdout=io.StringIO())
        with override_settings(DATABASE_URL=""), self.assertRaises(CommandError):
            call_command("security_audit", strict=True, stdout=io.StringIO())
