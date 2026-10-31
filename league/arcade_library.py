"""Published arcade library, durable event standings and all-time play."""
import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, F, Q, Sum
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

# Unreleased games are deliberately outside GAMES: they cannot be published,
# acquire attempts via models_for(), or affect an existing competition/wheel.
PREVIEW_GAMES = {
    "tetris": {"title": "Pit Stack", "subtitle": "F1-тетрис · закрытый тест", "cover": "league/images/tetris-pit-garage-v1.png"},
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
    if not contest.opened_at or contest.game_key != settings.active_game:
        # Legacy settings must not turn a saved plan into a live competition.
        return settings, None
    return settings, contest


def contest_rows(contest):
    if not contest.opened_at:
        return [], 0
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
    if contest.frozen_at or not contest.opened_at:
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


def history(game, user):
    result = []
    for item in ArcadeCompetition.objects.filter(game_key=game, opened_at__isnull=False).select_related("event"):
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
    now = timezone.now()
    contest_open = bool(contest and settings.public_enabled and not contest.frozen_at
                        and contest.opened_at <= now < contest.event.deadline)
    current = next((card for card in cards if contest_open and card["key"] == contest.game_key), None)
    return render(request, "arcade_library.html", {"games": cards, "current_game": current,
        "contest": contest, "contest_open": contest_open, "library_server_time": now,
        "arcade_settings_admin_url": reverse("league:arcade_control")})


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


@login_required
@require_GET
def minesweeper_preview(request):
    """Keep the old prototype in the lab, never publish it accidentally."""
    if not request.user.is_active or not request.user.is_staff:
        return HttpResponseForbidden()
    from .views import arcade
    request.GET = request.GET.copy()
    request.GET["admin_test"] = ArcadeSettings.Game.MINESWEEPER
    return arcade(request)


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
        if type(attempt_id) is not int or type(score) is not int or not 0 <= score <= (500 if game_key == "flappy" else 2_147_483_647):
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
    season = get_selected_season(request)
    events = Event.objects.filter(season_year=season.year).order_by("round_number")
    if request.method == "POST":
        with transaction.atomic():
            settings = ArcadeSettings.objects.select_for_update().get(pk=1)
            previous = (ArcadeCompetition.objects.select_for_update().select_related("event")
                        .filter(event_id=settings.competition_event_id, opened_at__isnull=False).first()
                        if settings.competition_opened_at else None)
            key = request.POST.get("active_game")
            action = request.POST.get("action")
            try:
                event_id = int(request.POST.get("competition_event", ""))
            except (TypeError, ValueError):
                event_id = settings.competition_event_id if action == "close" else None
            event = events.filter(pk=event_id).first()
            locked = previous and (not previous.event.race_datetime or now < previous.event.race_datetime)
            assignment = (ArcadeCompetition.objects.select_for_update().filter(event=event).first() if event else None)
            if action == "close" and previous and event and previous.event_id == event.pk:
                settings.public_enabled = False
                settings.save(update_fields=("public_enabled", "updated_at"))
                messages.success(request, "Соревновательный зачёт приостановлен. Глобальные рекорды продолжают сохраняться.")
            elif action not in {"select", "publish"}:
                messages.error(request, "Для выбранного этапа нет открытого зачёта, который можно приостановить.")
            elif key not in GAMES or not event or event.deadline <= now or event.status == Event.Status.SCORED:
                messages.error(request, "Выбери игру и этап с будущим дедлайном.")
            elif assignment and assignment.opened_at and assignment.game_key != key:
                messages.error(request, "Игра этого этапа уже опубликована. Менять её нельзя: результаты должны сохраниться.")
            elif assignment and assignment.frozen_at:
                messages.error(request, "Зачёт этого этапа уже зафиксирован.")
            elif action == "publish" and locked and previous.event_id != event.pk:
                messages.error(request, f"Сначала дождись старта гонки «{previous.event.name}»: победителю нужен доступ к колесу. Привязку следующего этапа можно сохранить заранее.")
            else:
                assignment = assignment or ArcadeCompetition.objects.create(event=event, game_key=key)
                if not assignment.opened_at:
                    assignment.game_key = key
                    if action == "publish":
                        assignment.opened_at = now
                    assignment.save(update_fields=("game_key", "opened_at"))
                if action == "publish":
                    settings.active_game, settings.competition_event = key, event
                    settings.competition_opened_at = assignment.opened_at
                    settings.public_enabled = True
                    settings.save()
                    messages.success(request, f"{GAMES[key]['title']} открыт для этапа «{event.name}» до его дедлайна прогнозов.")
                else:
                    # Drafts belong to individual events, not the global current
                    # competition. Planning another GP must never pause live play.
                    if not previous:
                        settings.active_game, settings.competition_event = key, event
                        settings.competition_opened_at = None
                        settings.public_enabled = False
                        settings.save()
                    messages.success(request, f"{GAMES[key]['title']} назначен этапу «{event.name}». Зачёт ещё не запускался; текущая аркада не изменена." if not assignment.opened_at else "Привязка опубликованного зачёта сохранена без изменений.")
        target = reverse("league:arcade_control") + f"?season={season.year}"
        if event:
            target += f"&event={event.pk}"
        return redirect(target + "#lab-competition")
    event_list = list(events)
    selected_event = next((event for event in event_list if str(event.pk) == request.GET.get("event")), None)
    selected_event = selected_event or next((event for event in event_list if event.pk == settings.competition_event_id), None)
    selected_event = selected_event or next((event for event in event_list if event.deadline > now), None) or (event_list[-1] if event_list else None)
    assignments = list(ArcadeCompetition.objects.filter(event__season_year=season.year).select_related("event").order_by("event__round_number"))
    selected_assignment = next((item for item in assignments if selected_event and item.event_id == selected_event.pk), None)
    def plan_state(item):
        if not item.opened_at:
            return "Назначена" if item.event.deadline > now else "Не запускалась"
        if item.frozen_at or item.event.deadline <= now:
            return "Зачёт завершён"
        if settings.competition_event_id == item.event_id and settings.public_enabled:
            return "Зачёт открыт"
        return "Приостановлен"
    plans = [{"event": item.event, "game_title": GAMES.get(item.game_key, {}).get("title", item.get_game_key_display()),
              "state": plan_state(item)} for item in assignments]
    selected_expired = bool(selected_event and (selected_event.deadline <= now or selected_event.status == Event.Status.SCORED))
    blocked_by_previous = bool(previous and selected_event and previous.event_id != selected_event.pk
        and (not previous.event.race_datetime or previous.event.race_datetime > now))
    selected_key = (selected_assignment.game_key if selected_assignment else
                    settings.active_game if selected_event and settings.competition_event_id == selected_event.pk and not settings.competition_opened_at else "")
    test_games = [
        {**GAMES["doodle_jump"], "key": "doodle_jump", "genre": "Doodle Jump", "status": "В библиотеке",
         "url": reverse("league:arcade_game", args=["doodle_jump"]) + "?admin_test=1"},
        {**GAMES["flappy"], "key": "flappy", "genre": "Flappy Bird", "status": "В библиотеке",
         "url": reverse("league:arcade_game", args=["flappy"]) + "?admin_test=1"},
        {"key": "minesweeper", "title": "Pitwall Sweep", "genre": "Сапёр", "status": "Закрытый тест",
         "description": "Расчисти пит-лейн: находи безопасные клетки и отмечай скрытые опасности.",
         "cover": "league/images/arcade-minesweeper-pitlane.png", "url": reverse("league:arcade_minesweeper_preview")},
        {**PREVIEW_GAMES["tetris"], "key": "tetris", "genre": "Тетрис", "status": "Закрытый тест",
         "description": "Собирай ряды под гоночный саундтрек и проверяй темп на трассах Гран-при.",
         "url": reverse("league:arcade_game", args=["tetris"])},
    ]
    contest_open = bool(previous and settings.public_enabled and previous.opened_at <= now < previous.event.deadline)
    return render(request, "arcade_library_control.html", {"settings": settings, "events": event_list, "games": GAMES.items(),
        "season": season, "plans": plans, "selected_event": selected_event,
        "selected_assignment": selected_assignment, "selected_game_key": selected_key,
        "selected_assignment_state": plan_state(selected_assignment) if selected_assignment else "Аркада не назначена",
        "selected_event_expired": selected_expired, "blocked_by_previous": blocked_by_previous,
        "can_pause_selected": bool(selected_event and selected_event.pk == settings.competition_event_id and settings.public_enabled),
        "current_contest": previous,
        "test_games": test_games, "contest_open": contest_open,
        "selected_game_public": selected_key in GAMES,
        "active_game_title": GAMES.get(settings.active_game, {}).get("title", settings.get_active_game_display()),
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
