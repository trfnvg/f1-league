"""Published arcade library, durable event standings and all-time play."""
import json
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, F, Q, Sum, Window
from django.db.models.functions import RowNumber
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.cache import never_cache

from .models import (DRIVER_CHOICES, ArcadeAttempt, ArcadeCompetition, ArcadeRecord, ArcadeSettings,
                     ArcadeWheelSpin, DoodleAttempt, DoodleRecord, Event, Prediction)
from .services import get_selected_season
from . import arcade_rewards as rewards
from . import arcade_validation as validation

GAMES = {
    "flappy": {"title": "Pit Lane Flight", "subtitle": "Банан Леклер · Flappy Bird", "cover": "league/images/arcade-flappy-cover-v1.png", "description": "Пролетай между воротами солнечного паддока и держи ритм."},
    "doodle_jump": {"title": "Cowboy GP", "subtitle": "Рассел на Диком Западе · Doodle Jump", "cover": "league/images/arcade-doodle-cover-v1.png", "description": "Прыгай через каньоны, облака и космос. Каждый забег — новая высота."},
}

# Unreleased games are deliberately outside GAMES: they cannot be published,
# acquire attempts via models_for(), or affect an existing competition/wheel.
PREVIEW_GAMES = {
    "tetris": {"title": "Pit Stack", "subtitle": "F1-тетрис · закрытый тест", "cover": "league/images/tetris-pit-garage-v1.png"},
}


def require_game_user(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_active:
            # Never return a login-page redirect as a successful JSON save.
            return JsonResponse({"error": "Войди в аккаунт и начни новый заезд, чтобы сохранить результат."}, status=401)
        return view(request, *args, **kwargs)
    return wrapped


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
    rows = []
    finished = attempts.filter(score__isnull=False, finished_at__lte=contest.event.deadline,
                              user__is_active=True)
    # Pick one best run per player in SQL rather than transferring every run
    # (including its verification payload) to Python on each leaderboard poll.
    finished = finished.annotate(best_position=Window(
        expression=RowNumber(), partition_by=[F("user_id")],
        order_by=[F("score").desc(), F("finished_at").asc(), F("pk").asc()],
    )).filter(best_position=1).order_by("-score", "finished_at", "user_id").values(
        "user_id", "score", "user__first_name", "user__last_name", "user__username",
    )
    for attempt in finished:
        name = f"{attempt['user__first_name']} {attempt['user__last_name']}".strip()
        rows.append({"user_id": attempt["user_id"], "username": name or attempt["user__username"],
                     "score": attempt["score"], "attempts": counts[attempt["user_id"]], "rank": len(rows) + 1})
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
    own_rank = None
    if own and own.best_score > 0 and not user.is_staff:
        own_rank = records.filter(
            Q(best_score__gt=own.best_score)
            | Q(best_score=own.best_score, updated_at__lt=own.updated_at)
            | Q(best_score=own.best_score, updated_at=own.updated_at, user_id__lt=user.pk)
        ).count() + 1
    rows = [{"username": r.user.get_full_name().strip() or r.user.username, "score": r.best_score,
             "attempts": r.total_attempts, "rank": i, "is_current_user": user.is_authenticated and r.user_id == user.pk}
            for i, r in enumerate(records[:10], 1)]
    data = {"records": rows, "record": own.best_score if own else 0, "attempts": own.total_attempts if own else 0,
            "rank": own_rank,
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




@require_GET
def library(request):
    settings, contest = selected_contest()
    if contest:
        contest = freeze(contest)
    # New releases lead the library; the selected competition has its own hero card.
    newest_first = ("doodle_jump", "flappy")
    cards = [{**GAMES[key], "key": key, "url": reverse("league:arcade_game", args=[key])} for key in newest_first]
    now = timezone.now()
    contest_open = bool(contest and settings.public_enabled and not contest.frozen_at
                        and contest.opened_at <= now < contest.event.deadline)
    current = next((card for card in cards if contest_open and card["key"] == contest.game_key), None)
    return render(request, "arcade_library.html", {"games": cards, "current_game": current,
        "contest": contest, "contest_open": contest_open, "library_server_time": now,
        "arcade_settings_admin_url": reverse("league:arcade_control")})


@never_cache
@require_GET
def game(request, game_key):
    if game_key in PREVIEW_GAMES:
        if not request.user.is_authenticated or not request.user.is_active or not request.user.is_staff:
            raise Http404
        return render(request, "arcade_tetris.html", {"game": PREVIEW_GAMES[game_key]})
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
    for key, name in [("doodle_attempt_start_url", "doodle_attempt_start"), ("doodle_attempt_finish_url", "doodle_attempt_finish"), ("doodle_attempt_progress_url", "doodle_attempt_progress"), ("doodle_leaderboard_url", "doodle_leaderboard")]:
        context[key] = reverse("league:" + name) + suffix
    wheel_period = bool(contest and (not contest.event.race_datetime or timezone.now() < contest.event.race_datetime)
                        and contest.event.status != Event.Status.SCORED)
    if is_current and not admin_test and wheel_period:
        # Keep the current winner's wheel accessible through the race start.
        context.update(wheel_context(request, contest))
    return render(request, "arcade_doodle_jump.html" if game_key == "doodle_jump" else "arcade_flappy.html", context)


def doodle_page(request):
    return game(request, "doodle_jump")


@login_required
@require_GET
def minesweeper_preview(request):
    """Keep the old prototype in the lab, never publish it accidentally."""
    if not request.user.is_active or not request.user.is_staff:
        return HttpResponseForbidden()
    from .views import _minesweeper_leaderboard_data
    data = _minesweeper_leaderboard_data(request.user)
    return render(request, "arcade_minesweeper.html", {
        "minesweeper_attempts": data["attempts"],
        "minesweeper_records": data["records"],
        "minesweeper_total_attempts": data["total_attempts"],
        "minesweeper_week_start": data["week_start"],
        "arcade_admin_preview": True, "arcade_test_mode": True,
        "arcade_scoring_open": True, "arcade_game_key": ArcadeSettings.Game.MINESWEEPER,
        "arcade_settings_admin_url": reverse("league:arcade_control"),
        "minesweeper_attempt_start_url": reverse("league:minesweeper_attempt_start") + "?admin_test=1",
        "minesweeper_attempt_finish_url": reverse("league:minesweeper_attempt_finish") + "?admin_test=1",
        "minesweeper_leaderboard_url": reverse("league:minesweeper_leaderboard") + "?admin_test=1",
    })


@never_cache
@require_GET
def leaderboard(request, game_key="flappy"):
    if game_key not in GAMES:
        raise Http404
    return JsonResponse(board(request.user, game_key))


@never_cache
@require_game_user
@require_POST
@transaction.atomic
def attempt_start(request, game_key="flappy"):
    if game_key not in GAMES:
        raise Http404
    if request.user.is_staff:
        return JsonResponse({"attempt_id": None, "run_token": None, **board(request.user, game_key)})
    validation.lock_player(request.user)
    settings, contest = selected_contest()
    now = timezone.now()
    if contest:
        contest = freeze(contest)  # Same lock order as finish; deadline freezes before free play.
    eligible = bool(contest and contest.game_key == game_key and settings.public_enabled
        and contest.opened_at <= now < contest.event.deadline and not request.user.is_staff)
    Attempt, Record = models_for(game_key)
    attempt = Attempt.objects.create(user=request.user, competition=contest if eligible else None)
    token = validation.start(request, attempt)
    record, _ = Record.objects.select_for_update().get_or_create(user=request.user)
    Record.objects.filter(pk=record.pk).update(total_attempts=F("total_attempts") + 1)
    return JsonResponse({"attempt_id": attempt.pk, "run_token": token, **board(request.user, game_key)})


@never_cache
@require_game_user
@require_POST
@transaction.atomic
def attempt_finish(request, game_key="flappy"):
    return _attempt_update(request, game_key, final=True)


@never_cache
@require_game_user
@require_POST
@transaction.atomic
def attempt_progress(request, game_key="flappy"):
    return _attempt_update(request, game_key, final=False)


def _attempt_update(request, game_key, *, final):
    if game_key not in GAMES:
        raise Http404
    if request.user.is_staff:
        return JsonResponse({"error": "Тестовые заезды не записываются в рейтинг."}, status=403)
    try:
        payload = validation.payload(request)
    except validation.InvalidRun as error:
        return JsonResponse({"error": str(error)}, status=error.status)
    attempt_id, score = payload["attempt_id"], payload["score"]
    validation.lock_player(request.user)
    Attempt, Record = models_for(game_key)
    stub = Attempt.objects.filter(pk=attempt_id, user=request.user).first()
    if not stub:
        return JsonResponse({"error": "Заезд не найден."}, status=409)
    if final and stub.competition_id:
        freeze(ArcadeCompetition.objects.get(pk=stub.competition_id))
    attempt = Attempt.objects.select_for_update().get(pk=stub.pk)
    try:
        now = validation.check(request, attempt, payload, game_key, final=final)
    except validation.InvalidRun as error:
        return JsonResponse({"error": str(error)}, status=error.status)
    if not final:
        return JsonResponse({"ok": True})
    attempt.finished_at, attempt.score = now, score
    attempt.save(update_fields=("finished_at", "score", "verification"))
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
            elif request.POST.get("action") not in {"select", "publish"}:
                messages.error(request, "Неизвестное действие.")
            elif key not in GAMES or not event:
                messages.error(request, "Выбери игру и этап с будущим дедлайном.")
            elif locked and (previous.game_key != key or previous.event_id != event.pk):
                messages.error(request, "Сменить текущий зачёт можно после старта его гонки: победителю нужен доступ к колесу.")
            elif ArcadeCompetition.objects.filter(event=event).exclude(game_key=key).exists():
                messages.error(request, "К этому этапу уже привязана другая игра.")
            elif request.POST.get("action") == "select":
                changed = settings.active_game != key or settings.competition_event_id != event.pk
                settings.active_game, settings.competition_event = key, event
                if changed or not previous:
                    settings.competition_opened_at = None
                    settings.public_enabled = False
                settings.save()
                messages.success(request, "Выбор сохранён. Нажми «Открыть участникам», когда будешь готов.")
            else:
                contest, _ = ArcadeCompetition.objects.get_or_create(event=event, defaults={"game_key": key, "opened_at": now})
                settings.active_game, settings.competition_event = key, event
                settings.competition_opened_at = contest.opened_at
                settings.public_enabled = True
                settings.save()
                messages.success(request, "Соревнование открыто до дедлайна выбранного этапа.")
        return redirect("league:arcade_control")
    return render(request, "arcade_library_control.html", {"settings": settings, "events": events, "games": GAMES.items(),
        "preview_games": PREVIEW_GAMES.items(),
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
