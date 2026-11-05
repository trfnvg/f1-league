"""Explicit, audited administrator corrections; original attempts are never deleted."""
from datetime import timedelta
from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from . import arcade_library as library
from .models import (ArcadeAttempt, ArcadeCompetition, ArcadeGameClosure, ArcadeTrophyAward,
    ArcadeWheelSpin, DoodleAttempt, Event, MinesweeperAttempt, TetrisAttempt)

GAME_MODELS = {ArcadeAttempt: "flappy", DoodleAttempt: "doodle_jump", TetrisAttempt: "tetris", MinesweeperAttempt: "minesweeper"}


def require_permission(actor, model, *, manual=False):
    if model not in GAME_MODELS or not actor.is_active or not actor.is_staff:
        raise PermissionDenied
    actions = ("change", "add") if manual else ("change",)
    if not all(actor.has_perm(f"league.{action}_{model._meta.model_name}") for action in actions):
        raise PermissionDenied


def clean_reason(reason):
    reason = (reason or "").strip()
    if not reason or len(reason) > 2000:
        raise ValidationError("Укажи причину изменения (до 2000 символов).")
    return reason


def lock_contest(competition_id):
    if not competition_id:
        return None
    stub = ArcadeCompetition.objects.get(pk=competition_id)
    Event.objects.select_for_update().get(pk=stub.event_id)
    return ArcadeCompetition.objects.select_for_update().select_related("event").get(pk=competition_id)


def record_before(model, user):
    if model is MinesweeperAttempt:
        return None
    _, Record = library.models_for(GAME_MODELS[model])
    record, _ = Record.objects.select_for_update().get_or_create(user=user)
    if record.moderation_baseline_score is None:
        attempts = model.objects.filter(user=user)
        represented = attempts.filter(score=record.best_score, finished_at__isnull=False, is_excluded=False).exists()
        record.moderation_baseline_score = 0 if represented else record.best_score
        record.moderation_baseline_attempts = max(0, record.total_attempts-attempts.filter(is_excluded=False).count())
        record.moderation_baseline_at = record.updated_at
        record.save(update_fields=("moderation_baseline_score", "moderation_baseline_attempts", "moderation_baseline_at"))
    return record


def refresh_record(model, user, record):
    if record is None:
        return
    attempts = model.objects.filter(user=user, is_excluded=False)
    best = attempts.filter(score__isnull=False, finished_at__isnull=False).order_by("-score", "finished_at", "pk").first()
    score = max(record.moderation_baseline_score, best.score if best else 0)
    fields = ["total_attempts", "best_score"]
    if record.best_score != score:
        if score == record.moderation_baseline_score and record.moderation_baseline_at:
            record.updated_at = record.moderation_baseline_at
            fields.append("updated_at")
        elif best and best.score == score:
            record.updated_at = best.finished_at
            fields.append("updated_at")
    record.best_score = score
    record.total_attempts = record.moderation_baseline_attempts + attempts.count()
    # QuerySet.update preserves the achievement time used to break ties.
    type(record).objects.filter(pk=record.pk).update(**{field: getattr(record, field) for field in fields})


def refresh_contest(contest):
    if not contest:
        return
    # Do not silently change a winner whose wheel effects/trophy have already
    # affected predictions. That requires a separate, deliberate reward correction.
    protected = set(ArcadeWheelSpin.objects.filter(event=contest.event).values_list("winner_id", flat=True))
    protected.update(ArcadeTrophyAward.objects.filter(event=contest.event).values_list("player_id", flat=True))
    protected.update(ArcadeGameClosure.objects.filter(event=contest.event, winner__isnull=False).values_list("winner_id", flat=True))
    if protected:
        leader = library.rewards.best_event_arcade_attempt(contest.event, through=contest.event.deadline,
            game_key=contest.game_key, opened_at=contest.opened_at)
        if not leader or protected != {leader.user_id}:
            raise ValidationError("Нельзя сменить победителя этапа: колесо или трофей уже выданы. Сначала нужна отдельная корректировка наград.")
    if contest.frozen_at:
        contest.standings, contest.total_attempts = library.contest_rows(contest)
        contest.save(update_fields=("standings", "total_attempts"))


def audit(actor, attempt, message, *, added=False):
    LogEntry.objects.create(user=actor, content_type=ContentType.objects.get_for_model(attempt),
        object_id=str(attempt.pk), object_repr=str(attempt)[:200],
        action_flag=ADDITION if added else CHANGE, change_message=message)


@transaction.atomic
def set_excluded(*, actor, model, attempt_id, excluded, reason):
    require_permission(actor, model)
    if type(excluded) is not bool:
        raise ValidationError("Укажи корректное действие с попыткой.")
    reason = clean_reason(reason)
    stub = model.objects.get(pk=attempt_id)
    contest = lock_contest(getattr(stub, "competition_id", None))
    attempt = model.objects.select_for_update().select_related("user").get(pk=attempt_id)
    if attempt.is_excluded == excluded:
        return attempt
    record = record_before(model, attempt.user)
    attempt.is_excluded, attempt.moderation_note = excluded, reason
    attempt.moderated_by, attempt.moderated_at = actor, timezone.now()
    attempt.save(update_fields=("is_excluded", "moderation_note", "moderated_by", "moderated_at"))
    refresh_record(model, attempt.user, record)
    refresh_contest(contest)
    audit(actor, attempt, ("Исключена из зачёта. " if excluded else "Возвращена в зачёт. ") + reason)
    return attempt


@transaction.atomic
def create_manual(*, actor, model, user, started_at, finished_at, reason, competition=None,
                  score=None, elapsed_ms=None, week_start=None):
    require_permission(actor, model, manual=True)
    reason = clean_reason(reason)
    if user.is_staff or not user.is_active:
        raise ValidationError("Выбери активного игрока, не администратора.")
    if not started_at or not finished_at or started_at > finished_at or finished_at > timezone.now():
        raise ValidationError("Начало должно быть не позже завершения; завершение не может быть в будущем.")
    contest = lock_contest(competition.pk if competition else None)
    if contest and (contest.game_key != GAME_MODELS[model] or not contest.opened_at
            or started_at < contest.opened_at or started_at >= contest.event.deadline or finished_at > contest.event.deadline):
        raise ValidationError("Игра и время попытки должны соответствовать выбранному зачёту этапа.")
    data = dict(user=user, finished_at=finished_at, is_manual=True, moderation_note=reason,
        moderated_by=actor, moderated_at=timezone.now())
    if model is MinesweeperAttempt:
        if contest or type(elapsed_ms) is not int or not 0 < elapsed_ms <= (finished_at-started_at).total_seconds()*1000:
            raise ValidationError("Время сапёра должно быть положительным и не превышать длительность попытки.")
        day = timezone.localdate(started_at)
        monday = day-timedelta(days=day.weekday())
        if week_start is not None and week_start != monday:
            raise ValidationError("Игровая неделя должна соответствовать дате начала попытки.")
        data.update(completed=True, elapsed_ms=elapsed_ms, week_start=monday)
    else:
        if type(score) is not int or not 0 <= score <= (500 if model is ArcadeAttempt else 2_147_483_647):
            raise ValidationError("Укажи корректное неотрицательное количество очков (для Pit Lane Flight — до 500).")
        data.update(score=score, competition=contest)
        if model is TetrisAttempt:
            data.update(seed=0)
    record = record_before(model, user)
    attempt = model.objects.create(**data)
    model.objects.filter(pk=attempt.pk).update(started_at=started_at)
    attempt.started_at = started_at
    refresh_record(model, user, record)
    refresh_contest(contest)
    audit(actor, attempt, "Добавлена вручную администратором. " + reason, added=True)
    return attempt
