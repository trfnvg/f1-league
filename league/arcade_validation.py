"""Server-owned attempt lifecycle and conservative plausibility checks.

This is NOT authoritative physics replay: a modified client can still simulate
plausible progress. Tokens bind requests, they do not prove a human played.
Never replace these checks with an obfuscated/signing secret in JavaScript.
"""
import hashlib
import json
import logging
import math
import secrets

from django.contrib.auth.models import User
from django.utils import timezone

from .models import ArcadeAttempt, DoodleAttempt

logger = logging.getLogger(__name__)
MAX_RUN_SECONDS = 12 * 60 * 60
MAX_IDLE_SECONDS = 180
MAX_PAYLOAD_BYTES = 4096


class InvalidRun(ValueError):
    def __init__(self, message, status=400):
        self.status = status
        super().__init__(message)


def payload(request):
    try:
        if int(request.META.get("CONTENT_LENGTH") or 0) > MAX_PAYLOAD_BYTES:
            raise ValueError
        raw = request.body
        if len(raw) > MAX_PAYLOAD_BYTES:
            raise ValueError
        data = json.loads(raw or b"{}")
        if not isinstance(data, dict) or set(data) != {"attempt_id", "run_token", "score"}:
            raise ValueError
        if type(data.get("attempt_id")) is not int or not 0 < data["attempt_id"] <= 2**63-1:
            raise ValueError
        if type(data.get("score")) is not int or not 0 <= data["score"] <= 2_147_483_647:
            raise ValueError
        token = data.get("run_token")
        if not isinstance(token, str) or not 20 <= len(token) <= 128:
            raise ValueError
        return data
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise InvalidRun("Некорректные данные заезда. Обнови страницу и начни новый заезд.")


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def lock_player(user):
    # All game mutations use this lock BEFORE contest/attempt/record locks.
    # Serializes concurrent starts/finishes, including across the two games.
    User.objects.select_for_update().only("pk").get(pk=user.pk)


def start(request, attempt):
    now = timezone.now()
    for model in (ArcadeAttempt, DoodleAttempt):
        # Do not erase scores/history: abandoned runs are simply unranked.
        model.objects.filter(user=request.user, finished_at__isnull=True).exclude(
            pk=attempt.pk if model is type(attempt) else None).update(finished_at=now)
    token = secrets.token_urlsafe(32)
    attempt.verification = {"version": 1, "token": digest(token),
        "session": digest(request.session.session_key or ""),
        "seen": now.timestamp(), "score": 0}
    attempt.save(update_fields=["verification"])
    return token


def reject(attempt, reason, now):
    attempt.finished_at = now
    attempt.verification = {**attempt.verification, "rejected": reason}
    attempt.save(update_fields=["finished_at", "verification"])
    # No request bodies, cookies, tokens, names or email addresses in logs.
    logger.warning("arcade_rejected game=%s attempt=%s user=%s reason=%s",
        attempt._meta.model_name, attempt.pk, attempt.user_id, reason)


def check(request, attempt, data, game, *, final=False):
    now = timezone.now()
    state = attempt.verification
    if not state or state.get("version") != 1:
        raise InvalidRun("Этот заезд начат в старой версии игры. Обнови страницу и начни новый.", 409)
    if not secrets.compare_digest(state.get("token", ""), digest(data["run_token"])) or not secrets.compare_digest(
            state.get("session", ""), digest(request.session.session_key or "")):
        raise InvalidRun("Заезд относится к другой игровой сессии. Начни новый заезд.", 403)
    if attempt.finished_at:
        raise InvalidRun("Заезд уже завершён или заменён новым.", 409)
    duration = (now-attempt.started_at).total_seconds()
    delta = now.timestamp()-state["seen"]
    score = data["score"]
    reason = None
    if duration < 0 or delta < 0 or duration > MAX_RUN_SECONDS or delta > MAX_IDLE_SECONDS:
        reason = "expired"
    elif score < state["score"]:
        reason = "score_decreased"
    elif game == "flappy":
        if score > 500 or (score > 0 and duration < 3+(score-1)*.95):
            reason = "impossible_flappy_progress"
        elif score > state["score"] + math.ceil(delta/0.95) + 3:
            reason = "flappy_progress_jump"
    else:
        # Fastest launch is 1400 world px/s / 11 px/point. Leave room for
        # normal lag, enemies (+30), marshals (+50) and boss bonuses (+800).
        if score > 120 + math.ceil(duration*180):
            reason = "impossible_doodle_progress"
        elif score > state["score"] + 1000 + math.ceil(delta*180):
            reason = "doodle_progress_jump"
    if reason:
        reject(attempt, reason, now)
        raise InvalidRun("Результат не прошёл проверку сервера. Начни новый заезд.")
    attempt.verification = {**state, "seen": now.timestamp(), "score": score}
    if not final:
        attempt.save(update_fields=["verification"])
    return now
