"""Published arcade library, durable event standings and all-time play."""
import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, F, Sum
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import (DRIVER_CHOICES, ArcadeAttempt, ArcadeCompetition, ArcadeRecord, ArcadeSettings,
                     ArcadeWheelSpin, DoodleAttempt, DoodleRecord, Event, Prediction)
from .services import get_selected_season
from . import arcade_rewards as rewards

GAMES = {
    "flappy": {"title": "Pit Lane Flight", "subtitle": "Банан Леклер · Flappy Bird", "cover": "league/images/arcade-flappy-cover-v1.png", "description": "Пролетай между воротами солнечного паддока и держи ритм."},
    "doodle_jump": {"title": "Cowboy GP", "subtitle": "Рассел на Диком Западе · Doodle Jump", "cover": "league/images/arcade-doodle-cover-v1.png", "description": "Прыгай через каньоны, облака и космос. Каждый забег — новая высота."},
}


def models_for(game):
    return (DoodleAttempt, DoodleRecord) if game == "doodle_jump" else (ArcadeAttempt, ArcadeRecord)


def selected_contest():
    settings = ArcadeSettings.objects.select_related("competition_event").filter(pk=1).first()
    if not settings or not settings.competition_event_id or not settings.competition_opened_at:
        return settings, None
    contest, created = ArcadeCompetition.objects.get_or_create(
        event=settings.competition_event,
        defaults={"game_key": settings.active_game, "opened_at": settings.competition_opened_at},
    )
    return settings, contest


def contest_rows(contest):
    Attempt, _ = models_for(contest.game_key)
    attempts = Attempt.objects.filter(competition=contest, user__is_staff=False,
        started_at__gte=contest.opened_at, started_at__lt=contest.event.deadline)
    counts = dict(attempts.values("user_id").annotate(count=Count("pk")).values_list("user_id", "count"))
    rows, seen = [], set()
    finished = attempts.filter(score__isnull=False, finished_at__lte=contest.event.deadline,
                              user__is_active=True).select_related("user").order_by("-score", "finished_at", "user_id")
    for attempt in finished:
        if attempt.user_id in seen:
            continue
        seen.add(attempt.user_id)
        rows.append({"user_id": attempt.user_id, "username": attempt.user.get_full_name().strip() or attempt.user.username,
                     "score": attempt.score, "attempts": counts[attempt.user_id], "rank": len(rows) + 1})
    return rows, sum(counts.values())


@transaction.atomic
def freeze(contest):
    if contest.frozen_at:
        return contest
    contest = ArcadeCompetition.objects.select_for_update().select_related("event").get(pk=contest.pk)
    if not contest.frozen_at and timezone.now() >= contest.event.deadline and contest.game_key in GAMES:
        contest.standings, contest.total_attempts = contest_rows(contest)
        contest.frozen_at = timezone.now()
        contest.save(update_fields=("standings", "total_attempts", "frozen_at"))
    return contest


def board(user, game):
    _, Record = models_for(game)
    records = Record.objects.filter(user__is_staff=False, best_score__gt=0).select_related("user").order_by("-best_score", "updated_at", "user_id")
    own = Record.objects.filter(user=user).first() if user.is_authenticated else None
    rows = [{"username": r.user.get_full_name().strip() or r.user.username, "score": r.best_score,
             "attempts": r.total_attempts, "rank": i, "is_current_user": user.is_authenticated and r.user_id == user.pk}
            for i, r in enumerate(records[:10], 1)]
    data = {"records": rows, "record": own.best_score if own else 0, "attempts": own.total_attempts if own else 0,
            "rank": next((r["rank"] for r in rows if r["is_current_user"]), None),
            "total_attempts": Record.objects.filter(user__is_staff=False).aggregate(total=Sum("total_attempts"))["total"] or 0}
    data.update(board_title="Глобальный рейтинг", board_scope="global",
                board_record=data["record"], board_attempts=data["attempts"])
    settings, contest = selected_contest()
    now = timezone.now()
    if (contest and contest.game_key == game and settings.public_enabled
            and not contest.frozen_at and contest.opened_at <= now < contest.event.deadline):
        rows, total = contest_rows(contest)
        own_row = next((row for row in rows if user.is_authenticated and row["user_id"] == user.pk), None)
        data.update(records=[{**row, "is_current_user": user.is_authenticated and row["user_id"] == user.pk}
                             for row in rows[:10]], total_attempts=total,
                    rank=own_row["rank"] if own_row else None,
                    board_record=own_row["score"] if own_row else 0,
                    board_attempts=own_row["attempts"] if own_row else 0,
                    board_scope="competition",
                    board_title=f"Зачёт этапа · R{contest.event.round_number} · {contest.event.name}")
    return data


def history(game, user):
    result = []
    for item in ArcadeCompetition.objects.filter(game_key=game).select_related("event"):
        item = freeze(item)
        rows, total = (item.standings, item.total_attempts) if item.frozen_at else contest_rows(item)
        result.append({"event": item.event, "frozen": bool(item.frozen_at), "total": total,
                       "rows": [{**r, "is_current_user": user.is_authenticated and r["user_id"] == user.pk} for r in rows[:20]]})
    return result


@require_GET
def library(request):
    settings, contest = selected_contest()
    if contest:
        contest = freeze(contest)
    # New releases lead the library; the selected competition has its own hero card.
    newest_first = ("doodle_jump", "flappy")
    cards = [{**GAMES[key], "key": key, "url": reverse("league:arcade_game", args=[key])} for key in newest_first]
    current = next((card for card in cards if contest and card["key"] == contest.game_key), None)
    return render(request, "arcade_library.html", {"games": cards, "current_game": current,
        "contest": contest, "contest_open": bool(contest and settings.public_enabled and timezone.now() < contest.event.deadline),
        "arcade_settings_admin_url": reverse("league:arcade_control")})


@require_GET
def game(request, game_key):
    if game_key not in GAMES:
        raise Http404
    settings, contest = selected_contest()
    is_current = bool(contest and contest.game_key == game_key)
    if contest:
        contest = freeze(contest)
    data = board(request.user, game_key)
    admin_test = request.user.is_staff and request.GET.get("admin_test") == "1"
    context = {"game": GAMES[game_key], "arcade_game_key": game_key, "arcade_scoring_open": True,
        "arcade_admin_preview": admin_test, "arcade_test_mode": admin_test, "arcade_library_mode": True,
        "arcade_settings_admin_url": reverse("league:arcade_control"), "leaderboard_title": data["board_title"],
        "competitive_now": bool(is_current and settings.public_enabled and timezone.now() < contest.event.deadline),
        "arcade_records": data["records"], "arcade_total_attempts": data["total_attempts"],
        "arcade_own_record": {"best_score": data["record"], "total_attempts": data["attempts"]}, "arcade_own_rank": data["rank"],
        "board_own_score": data["board_record"], "board_own_attempts": data["board_attempts"],
        "doodle_records": data["records"], "doodle_total_attempts": data["total_attempts"]}
    suffix = "?admin_test=1" if admin_test else ""
    for key, name in [("doodle_attempt_start_url", "doodle_attempt_start"), ("doodle_attempt_finish_url", "doodle_attempt_finish"), ("doodle_leaderboard_url", "doodle_leaderboard")]:
        context[key] = reverse("league:" + name) + suffix
    wheel_period = bool(contest and (not contest.event.race_datetime or timezone.now() < contest.event.race_datetime)
                        and contest.event.status != Event.Status.SCORED)
    if is_current and not admin_test and wheel_period:
        # Keep the current winner's wheel accessible through the race start.
        context.update(wheel_context(request, contest))
    return render(request, "arcade_doodle_jump.html" if game_key == "doodle_jump" else "arcade_flappy.html", context)


def doodle_page(request):
    return game(request, "doodle_jump")


@require_GET
def leaderboard(request, game_key="flappy"):
    return JsonResponse(board(request.user, game_key))


@login_required
@require_POST
@transaction.atomic
def attempt_start(request, game_key="flappy"):
    if game_key not in GAMES:
        raise Http404
    if request.user.is_staff and request.GET.get("admin_test") == "1":
        return JsonResponse({"attempt_id": None, **board(request.user, game_key)})
    settings, contest = selected_contest()
    now = timezone.now()
    if contest:
        contest = freeze(contest)  # Same lock order as finish; deadline freezes before free play.
    eligible = bool(contest and contest.game_key == game_key and settings.public_enabled
        and contest.opened_at <= now < contest.event.deadline and not request.user.is_staff)
    Attempt, Record = models_for(game_key)
    attempt = Attempt.objects.create(user=request.user, competition=contest if eligible else None)
    record, _ = Record.objects.select_for_update().get_or_create(user=request.user)
    Record.objects.filter(pk=record.pk).update(total_attempts=F("total_attempts") + 1)
    return JsonResponse({"attempt_id": attempt.pk, **board(request.user, game_key)})


@login_required
@require_POST
@transaction.atomic
def attempt_finish(request, game_key="flappy"):
    try:
        payload = json.loads(request.body or b"{}")
        attempt_id, score = payload.get("attempt_id"), payload.get("score")
        if type(attempt_id) is not int or type(score) is not int or not 0 <= score <= (500 if game_key == "flappy" else 1000000):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({"error": "Некорректный результат."}, status=400)
    Attempt, Record = models_for(game_key)
    stub = Attempt.objects.filter(pk=attempt_id, user=request.user).first()
    if not stub:
        return JsonResponse({"error": "Заезд не найден."}, status=409)
    if stub.competition_id:
        freeze(ArcadeCompetition.objects.get(pk=stub.competition_id))
    attempt = Attempt.objects.select_for_update().get(pk=stub.pk)
    if attempt.finished_at:
        return JsonResponse({"error": "Заезд уже сохранён."}, status=409)
    now = timezone.now()
    duration = (now - attempt.started_at).total_seconds()
    if game_key == "flappy" and score > 0 and not 3 + (score - 1) * 1.15 <= duration <= 12 + (score - 1) * 2.6:
        attempt.finished_at = now
        attempt.save(update_fields=("finished_at",))
        return JsonResponse({"error": "Время заезда не соответствует результату."}, status=400)
    attempt.finished_at, attempt.score = now, score
    attempt.save(update_fields=("finished_at", "score"))
    record, _ = Record.objects.select_for_update().get_or_create(user=request.user)
    if score > record.best_score:
        record.best_score = score
        record.save(update_fields=("best_score", "updated_at"))
    return JsonResponse(board(request.user, game_key))


@login_required
def control(request):
    if not request.user.is_staff:
        return HttpResponseForbidden()
    settings, previous = selected_contest()
    settings = settings or ArcadeSettings.objects.create(pk=1)
    if previous:
        freeze(previous)
    now = timezone.now()
    events = Event.objects.filter(season_year=get_selected_season(request).year, deadline__gt=now).exclude(status=Event.Status.SCORED).order_by("round_number")
    if request.method == "POST":
        with transaction.atomic():
            settings = ArcadeSettings.objects.select_for_update().get(pk=1)
            key = request.POST.get("active_game")
            try:
                event_id = int(request.POST.get("competition_event", ""))
            except (TypeError, ValueError):
                event_id = None
            event = events.filter(pk=event_id).first()
            locked = previous and (not previous.event.race_datetime or now < previous.event.race_datetime)
            if request.POST.get("action") == "close":
                settings.public_enabled = False
                settings.save(update_fields=("public_enabled", "updated_at"))
                messages.success(request, "Соревновательный зачёт приостановлен. Глобальные рекорды продолжают сохраняться.")
            elif key not in GAMES or not event:
                messages.error(request, "Выбери игру и этап с будущим дедлайном.")
            elif locked and (previous.game_key != key or previous.event_id != event.pk):
                messages.error(request, "Сменить текущий зачёт можно после старта его гонки: победителю нужен доступ к колесу.")
            elif ArcadeCompetition.objects.filter(event=event).exclude(game_key=key).exists():
                messages.error(request, "К этому этапу уже привязана другая игра.")
            else:
                contest, _ = ArcadeCompetition.objects.get_or_create(event=event, defaults={"game_key": key, "opened_at": now})
                settings.active_game, settings.competition_event = key, event
                settings.competition_opened_at = contest.opened_at
                settings.public_enabled = True
                settings.save()
                messages.success(request, "Соревнование открыто до дедлайна выбранного этапа.")
        return redirect("league:arcade_control")
    return render(request, "arcade_library_control.html", {"settings": settings, "events": events, "games": GAMES.items(),
        "arcade_wheel_sectors": list(rewards.WHEEL_SECTORS), "driver_choices": DRIVER_CHOICES})


def wheel_context(request, contest):
    now, event = timezone.now(), contest.event
    leader = rewards.best_event_arcade_attempt(event, through=now, game_key=contest.game_key, opened_at=contest.opened_at)
    spin = ArcadeWheelSpin.objects.filter(event=event).select_related("winner", "target_user").first()
    targets = list(Prediction.objects.filter(event=event, user__is_staff=False, user__is_active=True).exclude(user=request.user).select_related("user")) if request.user.is_authenticated else []
    opened = rewards.wheel_window_is_open(event, now)
    return {"wheel_event": event, "wheel_leader": leader, "wheel_spin": spin,
        "wheel_prize": rewards.WHEEL_PRIZE_BY_KEY.get(spin.prize) if spin else None,
        "wheel_sectors": list(rewards.WHEEL_SECTORS), "wheel_targets": targets,
        "crazy_targets": [t for t in targets if (t.crazy_prediction or "").strip()],
        "wheel_prediction_fields": rewards.available_va_bank_fields(event, request.user, now=now) if request.user.is_authenticated else [],
        "wheel_open": opened, "now": now, "driver_choices": DRIVER_CHOICES,
        "can_spin_wheel": bool(opened and leader and leader.user_id == request.user.pk and not spin),
        "can_activate_wheel": bool(opened and spin and spin.winner_id == request.user.pk and not spin.activated_at),
        "podium_edit_open": rewards.podium_edit_is_open(event, now)}
