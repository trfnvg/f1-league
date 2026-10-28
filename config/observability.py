"""Small, privacy-conscious operational signals; no credentials or request bodies."""
import json
import logging
import time
import traceback
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

from django.conf import settings


request_id_context = ContextVar("request_id", default="-")
logger = logging.getLogger("fastlap.operations")
FIELDS = ("route", "method", "status", "duration_ms", "asset", "line", "column",
          "kind", "error_type", "viewport")
LOG_FIELDS = FIELDS + ("game", "attempt_id", "user_id", "reason")


class OperationalFormatter(logging.Formatter):
    """Deliberately omit raw messages/URLs, SQL, cookies and exception values."""

    def format(self, record):
        request = getattr(record, "request", None)
        data = {
            "time": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.msg if record.name == "fastlap.operations" or (
                record.name == "league.arcade_validation" and record.msg == "arcade_rejected") else "application_log",
            "request_id": getattr(record, "request_id", getattr(request, "request_id", request_id_context.get())),
        }
        for key in LOG_FIELDS:
            if hasattr(record, key):
                data[key] = getattr(record, key)
        if record.exc_info and record.exc_info[0]:
            data["error_type"] = record.exc_info[0].__name__
            data["frames"] = [
                {"file": frame.filename.rsplit("/", 1)[-1], "line": frame.lineno, "function": frame.name}
                for frame in traceback.extract_tb(record.exc_info[2])[-12:]
            ]
        return json.dumps(data, ensure_ascii=True)


class RequestMonitoringMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Do not accept an attacker-controlled request ID or log forwarded headers.
        request.request_id = uuid.uuid4().hex
        token = request_id_context.set(request.request_id)
        started = time.monotonic()
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request.request_id
            elapsed = round((time.monotonic() - started) * 1000, 1)
            match = getattr(request, "resolver_match", None)
            route = match.view_name if match else "unresolved"
            if not request.path.startswith("/health/") or response.status_code >= 500:
                level = logging.ERROR if response.status_code >= 500 else (
                    logging.WARNING if elapsed >= settings.SLOW_REQUEST_MS else logging.INFO)
                logger.log(level, "http_request", extra={"route": route, "method": request.method,
                    "status": response.status_code, "duration_ms": elapsed})
            return response
        finally:
            request_id_context.reset(token)


def scrub_error_event(event, hint):
    """Strict allowlist, including removal of Django's request/session and locals.

    Exception types and stack locations remain useful for grouping/debugging;
    exception messages may contain a DB URL or email and are not transmitted.
    """
    clean = {key: event[key] for key in ("event_id", "timestamp", "level", "platform", "release",
             "environment", "sdk", "logger") if key in event}
    clean["message"] = "Fastlap application error"
    clean["tags"] = {"request_id": request_id_context.get()}
    record = hint.get("log_record") if hint else None
    if record:
        request = getattr(record, "request", None)
        clean["tags"]["request_id"] = getattr(request, "request_id", request_id_context.get())
        if record.name == "fastlap.operations":
            clean["tags"]["event"] = record.msg
        for key in FIELDS:
            if hasattr(record, key):
                clean["tags"][key] = getattr(record, key)
    exceptions = []
    for value in event.get("exception", {}).get("values", []):
        frames = []
        for frame in value.get("stacktrace", {}).get("frames", []):
            frames.append({key: frame[key] for key in ("filename", "module", "function", "lineno", "colno", "in_app")
                           if key in frame})
        exceptions.append({"type": value.get("type", "Error"), "value": "[redacted]",
                           "stacktrace": {"frames": frames}})
    if exceptions:
        clean["exception"] = {"values": exceptions}
    return clean


def configure_error_monitoring(dsn, *, environment, release):
    if not dsn:
        return  # No external requests or third-party monitoring unless configured.
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=dsn, environment=environment, release=release or None,
        integrations=[DjangoIntegration(), LoggingIntegration(level=None, event_level=logging.ERROR)],
        send_default_pii=False, include_local_variables=False, include_source_context=False,
        max_request_body_size="never", traces_sample_rate=0,
        before_send=scrub_error_event,
    )
