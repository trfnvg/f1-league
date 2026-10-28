import json
import logging
from types import SimpleNamespace
from unittest.mock import patch

from django.db import OperationalError
from django.http import HttpResponse
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings

from config.observability import (OperationalFormatter, RequestMonitoringMiddleware,
    configure_error_monitoring, request_id_context, scrub_error_event)
from .models import AuthRateBucket


class ProbeTests(SimpleTestCase):
    def test_liveness_needs_no_database_or_context_processor(self):
        with patch("league.context_processors.league_context", side_effect=AssertionError):
            for method in (self.client.get, self.client.head):
                response = method("/health/live/")
                self.assertEqual(response.status_code, 200)
                self.assertIn("no-store", response["Cache-Control"])
                self.assertRegex(response["X-Request-ID"], r"^[0-9a-f]{32}$")
        self.assertEqual(self.client.post("/health/live/").status_code, 405)

    def test_failed_database_returns_generic_503_without_leaking_details(self):
        with patch("league.health.connections") as connections:
            connections.__getitem__.return_value.cursor.side_effect = OperationalError("secret-db-password")
            response = self.client.get("/health/ready/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})
        self.assertNotIn(b"secret-db-password", response.content)
        self.assertIn("no-store", response["Cache-Control"])


class OperationalLogTests(SimpleTestCase):
    def test_request_id_is_generated_not_trusted_and_context_is_reset(self):
        request = RequestFactory().get("/private-token/?password=secret", HTTP_X_REQUEST_ID="attacker")
        request.resolver_match = SimpleNamespace(view_name="test_route")
        with self.assertLogs("fastlap.operations", level="INFO") as logs:
            response = RequestMonitoringMiddleware(lambda request: HttpResponse())(request)
        self.assertNotEqual(response["X-Request-ID"], "attacker")
        self.assertEqual(request_id_context.get(), "-")
        self.assertEqual(logs.records[0].route, "test_route")
        rendered = OperationalFormatter().format(logs.records[0])
        self.assertNotIn("private-token", rendered)
        self.assertNotIn("password", rendered)

    @override_settings(SLOW_REQUEST_MS=100)
    def test_slow_response_is_warning(self):
        with patch("config.observability.time.monotonic", side_effect=[1, 1.5]):
            with self.assertLogs("fastlap.operations", level="WARNING") as logs:
                RequestMonitoringMiddleware(lambda request: HttpResponse())(RequestFactory().get("/"))
        self.assertEqual(logs.records[0].duration_ms, 500)

    def test_exception_context_is_reset(self):
        def broken(request):
            raise RuntimeError("secret")
        with self.assertRaises(RuntimeError):
            RequestMonitoringMiddleware(broken)(RequestFactory().get("/"))
        self.assertEqual(request_id_context.get(), "-")

    def test_formatter_does_not_include_raw_exception_or_log_parameters(self):
        try:
            raise RuntimeError("password=secret")
        except RuntimeError:
            import sys
            record = logging.LogRecord("django.request", logging.ERROR, __file__, 1,
                "private-reset-token %s", ("secret",), sys.exc_info())
        output = OperationalFormatter().format(record)
        self.assertNotIn("secret", output)
        self.assertNotIn("private-reset-token", output)
        self.assertEqual(json.loads(output)["error_type"], "RuntimeError")

    def test_existing_arcade_security_signals_keep_safe_fields(self):
        record = logging.LogRecord("league.arcade_validation", logging.WARNING, __file__, 1,
            "arcade_rejected", (), None)
        record.game, record.attempt_id, record.user_id, record.reason = "doodleattempt", 1, 2, "expired"
        output = json.loads(OperationalFormatter().format(record))
        self.assertEqual(output["event"], "arcade_rejected")
        self.assertEqual(output["reason"], "expired")

    def test_server_error_page_includes_support_id_without_needing_database(self):
        from league.error_views import server_error
        request = RequestFactory().get("/")
        request.request_id = "a" * 32
        response = server_error(request)
        self.assertContains(response, request.request_id, status_code=500)

    def test_sentry_is_optional_and_does_not_send_personal_data(self):
        with patch("sentry_sdk.init") as init:
            configure_error_monitoring("", environment="test", release="test-sha")
            init.assert_not_called()
            configure_error_monitoring("https://public@example.invalid/1", environment="test", release="test-sha")
            self.assertFalse(init.call_args.kwargs["send_default_pii"])
            self.assertFalse(init.call_args.kwargs["include_local_variables"])
            self.assertEqual(init.call_args.kwargs["traces_sample_rate"], 0)
        event = {"event_id": "123", "request": {"headers": {"cookie": "secret"}},
            "user": {"email": "secret"}, "breadcrumbs": [{"message": "secret"}],
            "extra": {"password": "secret"}, "transaction": "secret", "message": "secret",
            "exception": {"values": [{"type": "ValueError", "value": "secret", "stacktrace": {
                "frames": [{"filename": "views.py", "lineno": 10, "vars": {"password": "secret"},
                            "context_line": "secret"}]}}]}}
        cleaned = scrub_error_event(event, {})
        self.assertNotIn("secret", json.dumps(cleaned))
        self.assertEqual(cleaned["exception"]["values"][0]["stacktrace"]["frames"][0]["lineno"], 10)


@override_settings(BROWSER_ERROR_REPORTING=True)
class BrowserReportTests(TestCase):
    report = {"asset": "doodle-jump.js", "line": 42, "column": 2, "kind": "error",
              "error_type": "TypeError", "viewport": "mobile"}

    def post(self, data=None, client=None, **kwargs):
        return (client or self.client).post("/diagnostics/browser-error/",
            data=json.dumps(data if data is not None else self.report), content_type="application/json", **kwargs)

    def test_ready_on_real_test_database_and_no_user_data_in_probes(self):
        response = self.client.get("/health/ready/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_report_is_csrf_protected_and_does_not_require_login(self):
        self.assertEqual(self.post(client=Client(enforce_csrf_checks=True)).status_code, 403)
        with self.assertLogs("fastlap.operations", level="ERROR") as logs:
            self.assertEqual(self.post().status_code, 204)
        self.assertEqual(logs.records[0].asset, "doodle-jump.js")
        self.assertEqual(logs.records[0].line, 42)

    def test_invalid_or_sensitive_payloads_are_rejected_before_rate_limit_database_work(self):
        for updates in ({"asset": "https://example.com/secret.js"}, {"line": True}, {"line": -1},
                        {"message": "secret"}, {"error_type": []}, {"viewport": "secret"}):
            self.assertEqual(self.post({**self.report, **updates}).status_code, 400)
        self.assertEqual(AuthRateBucket.objects.count(), 0)
        response = self.client.post("/diagnostics/browser-error/", data=b"x"*1025, content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_shared_rate_limit_and_retry_after(self):
        with patch("league.browser_errors.logger.error"):
            for _ in range(30):
                self.assertEqual(self.post().status_code, 204)
        response = self.post()
        self.assertEqual(response.status_code, 429)
        self.assertIn("Retry-After", response)
        self.assertIn("no-store", response["Cache-Control"])

    def test_database_outage_and_disabled_reporting_do_not_raise(self):
        with patch("league.browser_errors.consume", side_effect=OperationalError("secret")):
            self.assertEqual(self.post().status_code, 503)
        with override_settings(BROWSER_ERROR_REPORTING=False):
            with patch("league.browser_errors.consume") as consume:
                self.assertEqual(self.post().status_code, 204)
                consume.assert_not_called()
