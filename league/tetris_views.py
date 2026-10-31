"""Public Pit Stack runs; practice mode is isolated from persisted standings."""
import json
import secrets
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import arcade_library as library
from . import tetris_rules as rules
from .models import TetrisAttempt, TetrisRecord


@login_required
@require_POST
@transaction.atomic
def start(request):
    if request.user.is_staff and request.GET.get("admin_test") == "1":
        return JsonResponse({"attempt_id": None})
    settings, contest = library.selected_contest()
    library.require_game_access(request, "tetris", settings, contest)
    now = timezone.now()
    if contest:
        contest = library.freeze(contest)
    record, _ = TetrisRecord.objects.select_for_update().get_or_create(user=request.user)
    if TetrisAttempt.objects.filter(user=request.user, started_at__gte=now-timedelta(minutes=1)).count() >= 30:
        return JsonResponse({"error": "Слишком много стартов. Подожди минуту."}, status=429)
    eligible = bool(contest and contest.game_key == "tetris" and settings.public_enabled
        and not contest.frozen_at and contest.opened_at <= now < contest.event.deadline and not request.user.is_staff)
    attempt = TetrisAttempt.objects.create(user=request.user, seed=secrets.randbits(32),
        competition=contest if eligible else None, rules_version=rules.VERSION)
    TetrisRecord.objects.filter(pk=record.pk).update(total_attempts=F("total_attempts")+1)
    return JsonResponse({"attempt_id": attempt.pk, "seed": attempt.seed, "rules_version": rules.VERSION,
        "max_ticks": rules.MAX_TICKS, "max_inputs": rules.MAX_INPUTS})


@login_required
@require_POST
@transaction.atomic
def finish(request):
    if request.user.is_staff and request.GET.get("admin_test") == "1":
        return JsonResponse({"error": "Тестовые результаты не сохраняются."}, status=403)
    try:
        if len(request.body) > 800_000:
            raise ValueError
        payload = json.loads(request.body)
        if not isinstance(payload, dict) or type(payload.get("attempt_id")) is not int or "score" in payload:
            raise ValueError
    except (ValueError, TypeError, UnicodeDecodeError, RecursionError):
        return JsonResponse({"error": "Некорректный повтор игры."}, status=400)
    stub = TetrisAttempt.objects.filter(pk=payload["attempt_id"], user=request.user).first()
    if not stub:
        return JsonResponse({"error": "Попытка не найдена."}, status=409)
    if stub.competition_id:
        library.freeze(stub.competition)
    attempt = TetrisAttempt.objects.select_for_update().get(pk=stub.pk)
    if attempt.finished_at:
        if attempt.score is not None:
            return JsonResponse(library.board(request.user, "tetris"))  # Safe retry after a lost response.
        return JsonResponse({"error": "Повтор этой попытки уже отклонён."}, status=409)
    attempt.finished_at = timezone.now()
    # Consume invalid attempts as well, so an expensive replay cannot be retried indefinitely.
    attempt.save(update_fields=("finished_at",))
    try:
        if (type(payload.get("rules_version")) is not int or payload["rules_version"] != attempt.rules_version
                or attempt.rules_version != rules.VERSION):
            raise rules.ReplayError("Версия игры обновилась. Начни новый заезд.")
        score = rules.verify(attempt.seed, payload.get("ticks"), payload.get("inputs"),
            (attempt.finished_at-attempt.started_at).total_seconds())
    except rules.ReplayError as error:
        return JsonResponse({"error": str(error)}, status=400)
    attempt.score, attempt.ticks, attempt.replay = score, payload["ticks"], payload["inputs"]
    attempt.finished_at = timezone.now()
    attempt.save(update_fields=("score", "ticks", "replay", "finished_at"))
    record = TetrisRecord.objects.select_for_update().get(user=request.user)
    if score > record.best_score:
        record.best_score = score
        record.save(update_fields=("best_score", "updated_at"))
    return JsonResponse(library.board(request.user, "tetris"))
