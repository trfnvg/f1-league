"""Minimal first-party JS fault reports, not analytics or session recording."""
import json
import logging
import re

from django.conf import settings
from django.db import DatabaseError
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .auth_limits import client_address, consume

logger = logging.getLogger("fastlap.operations")
ASSET = re.compile(r"[a-zA-Z0-9_.-]{1,100}\.js\Z")
TYPES = {"Error", "TypeError", "ReferenceError", "SyntaxError", "RangeError", "URIError", "EvalError"}


def monitoring_context(request):
    if not settings.BROWSER_ERROR_REPORTING:
        return {}
    return {"browser_monitoring": {"endpoint": reverse("browser_error"), "csrf": get_token(request)}}


@never_cache
@require_POST
def report(request):
    if not settings.BROWSER_ERROR_REPORTING:
        return HttpResponse(status=204)
    try:
        if int(request.META.get("CONTENT_LENGTH") or 0) > 1024:
            raise ValueError
        body = request.body
        if len(body) > 1024:
            raise ValueError
        data = json.loads(body)
        if not isinstance(data, dict) or set(data) != {"asset", "line", "column", "kind", "error_type", "viewport"}:
            raise ValueError
        if not isinstance(data["asset"], str) or not ASSET.fullmatch(data["asset"]):
            raise ValueError
        if data["kind"] not in ("error", "unhandledrejection") or data["error_type"] not in TYPES:
            raise ValueError
        if data["viewport"] not in ("mobile", "desktop"):
            raise ValueError
        for field in ("line", "column"):
            if type(data[field]) is not int or not 0 <= data[field] <= 1_000_000:
                raise ValueError
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return JsonResponse({"error": "invalid_report"}, status=400)
    try:
        wait = consume("browser-error-ip", client_address(request), 30, 300)
    except DatabaseError:
        # Monitoring must not create another 500/error-report loop during a DB outage.
        return HttpResponse(status=503)
    if wait:
        response = HttpResponse(status=429)
        response["Retry-After"] = str(wait)
        return response
    logger.error("browser_runtime_error", extra=data)
    return HttpResponse(status=204)
