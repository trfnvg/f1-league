import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count, F, Min, Q, Sum
from django.http import HttpResponseForbidden, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .duels import (
    DuelActionError,
    cancel_duel_challenge,
    create_duel_challenge,
    get_user_event_duel,
    respond_to_duel,
)
from .forms import AvatarUploadForm, DuelChallengeForm, PredictionForm, RegisterForm, SeasonPredictionForm
from .models import (
    DRIVER_CHOICES,
    ArcadeAttempt,
    ArcadeLeadChange,
    ArcadeRecord,
    ArcadeSettings,
    ArcadeTrophyAward,
    ArcadeWheelSpin,
    CrazyPredictionVote,
    DuelChallenge,
    DuelSettings,
    Event,
    HomeResultImage,
    MinesweeperAttempt,
    PlayerWildcard,
    Prediction,
    Score,
    SeasonPrediction,
    SeasonResult,
    SeasonScore,
    UserProfile,
    WildcardSettings,
)
from .services import (
    build_achievements,
    build_activity_feed,
    build_duel,
    build_leaderboard,
    build_player_statistics,
    get_selected_season,
    _russian_plural,
)
from .wildcards import (
    WildcardActionError,
    answer_wildcard,
    draw_wildcard,
    get_or_create_wildcard_offer,
)
from .arcade_rewards import (
    WHEEL_PRIZE_BY_KEY,
    WHEEL_SECTORS,
    activate_event_wheel_prize,
    arcade_wheel_event,
    available_va_bank_fields,
    best_event_arcade_attempt,
    award_due_arcade_trophies,
    closed_event_arcade_leaderboard,
    get_or_create_arcade_game_closure,
    podium_edit_is_open,
    spin_event_wheel,
    va_bank_answer_is_correct,
    wheel_window_is_open,
    ArcadeWheelError,
)
from .crazy_jury import (
    CrazyVoteError,
    cast_crazy_prediction_vote,
    crazy_vote_candidates,
    crazy_jury_context,
    crazy_vote_is_finished,
    crazy_vote_is_open,
    vetoed_crazy_prediction_id,
)


DRIVER_LABELS = dict(DRIVER_CHOICES)
logger = logging.getLogger(__name__)


def _normalize(value):
    if value is None:
        return ""
    return str(value).strip().lower()


def _driver_label(value):
    if not value:
        return "—"
    return DRIVER_LABELS.get(value, value)


def _driver_of_day_values(result):
    values = result.driver_of_day_multiple or ([result.driver_of_day] if result.driver_of_day else [])
    return [value for value in values if value]


def _community_prediction_correctness(prediction, result, *, crazy_blocked=False, crazy_vetoed=False):
    driver_fields = ("p1", "p2", "p3", "pole", "fastest_lap")
    correct = {
        field_name: bool(
            result
            and _normalize(getattr(prediction, field_name))
            and _normalize(getattr(prediction, field_name))
            == _normalize(getattr(result, field_name))
        )
        for field_name in driver_fields
    }
    correct["crazy_prediction"] = bool(
        result
        and not crazy_blocked
        and not crazy_vetoed
        and (prediction.crazy_prediction or "").strip()
        and prediction.crazy_prediction_approved
    )
    return correct


def _is_async_request(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _get_arcade_settings():
    return ArcadeSettings.objects.filter(pk=1).first() or ArcadeSettings()


def _arcade_is_visible_to_user(request, arcade_settings):
    return bool(arcade_settings.public_enabled or request.user.is_staff)


def _current_arcade_week_start():
    today = timezone.localdate()
    return today - timedelta(days=today.weekday())


def _minesweeper_leaderboard_data(user, week_start=None):
    week_start = week_start or _current_arcade_week_start()
    attempts = MinesweeperAttempt.objects.filter(week_start=week_start)
    records = list(
        attempts.values("user_id", "user__username")
        .annotate(
            attempts=Count("id"),
            wins=Count("id", filter=Q(completed=True)),
            best_time_ms=Min("elapsed_ms"),
        )
        .filter(best_time_ms__isnull=False)
        .order_by("best_time_ms", "user__username")[:10]
    )
    rows = []
    previous_time = None
    previous_rank = None
    for index, record in enumerate(records, start=1):
        rank = previous_rank if record["best_time_ms"] == previous_time else index
        rows.append({
            "username": record["user__username"],
            "attempts": record["attempts"],
            "wins": record["wins"],
            "best_time_ms": record["best_time_ms"],
            "rank": rank,
            "is_current_user": bool(user.is_authenticated and record["user_id"] == user.id),
        })
        previous_time = record["best_time_ms"]
        previous_rank = rank
    own_attempts = attempts.filter(user=user) if user.is_authenticated else attempts.none()
    return {
        "records": rows,
        "attempts": own_attempts.count(),
        "wins": own_attempts.filter(completed=True).count(),
        "best_time_ms": own_attempts.aggregate(best=Min("elapsed_ms"))["best"],
        "total_attempts": attempts.count(),
        "week_start": week_start.isoformat(),
    }


def minesweeper_leaderboard(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    arcade_settings = _get_arcade_settings()
    if not _arcade_is_visible_to_user(request, arcade_settings):
        return HttpResponseForbidden("Аркада сейчас доступна только администраторам.")
    if arcade_settings.active_game != ArcadeSettings.Game.MINESWEEPER:
        return JsonResponse({"error": "Сапёр сейчас не выбран как активная аркада."}, status=410)
    return JsonResponse(_minesweeper_leaderboard_data(request.user))


def arcade(request):
    arcade_settings = _get_arcade_settings()
    if not _arcade_is_visible_to_user(request, arcade_settings):
        return HttpResponseForbidden("Аркада сейчас доступна только администраторам.")

    if arcade_settings.active_game == ArcadeSettings.Game.MINESWEEPER:
        board_data = _minesweeper_leaderboard_data(request.user)
        return render(request, "arcade_minesweeper.html", {
            "minesweeper_attempts": board_data["attempts"],
            "minesweeper_records": board_data["records"],
            "minesweeper_total_attempts": board_data["total_attempts"],
            "minesweeper_week_start": board_data["week_start"],
            "arcade_admin_preview": not arcade_settings.public_enabled,
            "arcade_settings_admin_url": reverse("admin:league_arcadesettings_change", args=(1,)),
            "minesweeper_attempt_start_url": reverse("league:minesweeper_attempt_start"),
            "minesweeper_attempt_finish_url": reverse("league:minesweeper_attempt_finish"),
            "minesweeper_leaderboard_url": reverse("league:minesweeper_leaderboard"),
        })

    if arcade_settings.active_game == ArcadeSettings.Game.DOODLE_JUMP:
        return render(request, "arcade_doodle_jump.html", {
            "arcade_admin_preview": not arcade_settings.public_enabled,
            "arcade_settings_admin_url": reverse("admin:league_arcadesettings_change", args=(1,)),
        })

    season = get_selected_season(request)
    now = timezone.now()
    award_due_arcade_trophies(season.year, now=now)
    board_data = _arcade_leaderboard_data(request.user)
    arcade_closure, _ = get_or_create_arcade_game_closure(season.year, now=now)
    arcade_closed_event = arcade_closure.event if arcade_closure else None
    arcade_own_closed_record = None
    if arcade_closed_event:
        board_data = closed_event_arcade_leaderboard(arcade_closed_event, request.user)
        arcade_own_closed_record = board_data["own_record"]
    wheel_event = arcade_closed_event or arcade_wheel_event(season.year, now)
    wheel_leader = best_event_arcade_attempt(wheel_event, through=now) if wheel_event else None
    wheel_spin = (
        ArcadeWheelSpin.objects.select_related("winner", "target_user")
        .filter(event=wheel_event)
        .first()
        if wheel_event
        else None
    )
    wheel_targets = []
    crazy_targets = []
    wheel_prediction_fields = []
    if wheel_event and request.user.is_authenticated:
        wheel_targets = list(
            Prediction.objects.filter(
                event=wheel_event,
                user__is_active=True,
                user__is_staff=False,
            )
            .exclude(user=request.user)
            .select_related("user")
            .order_by("user__username")
        )
        crazy_targets = [
            prediction
            for prediction in wheel_targets
            if (prediction.crazy_prediction or "").strip()
        ]
        wheel_prediction_fields = available_va_bank_fields(wheel_event, request.user, now=now)
    wheel_open = wheel_window_is_open(wheel_event, now)
    can_spin_wheel = bool(
        wheel_open
        and wheel_event.deadline <= now
        and wheel_leader
        and request.user.is_authenticated
        and wheel_leader.user_id == request.user.id
        and wheel_spin is None
    )
    if wheel_spin:
        current_prize = WHEEL_PRIZE_BY_KEY.get(wheel_spin.prize)
    else:
        current_prize = None
    if request.user.is_authenticated:
        own_record = ArcadeRecord.objects.filter(user=request.user).first()
    else:
        own_record = None
    return render(request, "arcade.html", {
        "arcade_records": board_data["records"],
        "arcade_own_record": own_record,
        "arcade_own_rank": board_data["rank"],
        "arcade_total_attempts": board_data["total_attempts"],
        "arcade_closure": arcade_closure,
        "arcade_closed_event": arcade_closed_event,
        "arcade_own_closed_record": arcade_own_closed_record,
        "now": now,
        "driver_choices": DRIVER_CHOICES,
        "wheel_event": wheel_event,
        "arcade_next_deadline": (
            wheel_event
            if not arcade_closed_event and wheel_event and wheel_event.deadline > now
            else None
        ),
        "wheel_leader": wheel_leader,
        "wheel_spin": wheel_spin,
        "wheel_prize": current_prize,
        "wheel_sectors": list(WHEEL_SECTORS),
        "wheel_targets": wheel_targets,
        "crazy_targets": crazy_targets,
        "wheel_prediction_fields": wheel_prediction_fields,
        "wheel_open": wheel_open,
        "can_spin_wheel": can_spin_wheel,
        "can_activate_wheel": bool(
            wheel_spin
            and request.user.is_authenticated
            and wheel_spin.winner_id == request.user.id
            and not wheel_spin.activated_at
            and wheel_open
        ),
        "podium_edit_open": bool(wheel_event and podium_edit_is_open(wheel_event, now)),
        "arcade_settings_admin_url": reverse("admin:league_arcadesettings_change", args=(1,)),
    })


@login_required
def arcade_doodle_jump(request):
    arcade_settings = _get_arcade_settings()
    if not request.user.is_staff and not (
        arcade_settings.public_enabled
        and arcade_settings.active_game == ArcadeSettings.Game.DOODLE_JUMP
    ):
        return HttpResponseForbidden("Эта страница доступна только администраторам.")
    return render(request, "arcade_doodle_jump.html", {
        "arcade_admin_preview": not (
            arcade_settings.public_enabled
            and arcade_settings.active_game == ArcadeSettings.Game.DOODLE_JUMP
        ),
        "arcade_settings_admin_url": reverse("admin:league_arcadesettings_change", args=(1,)),
    })


@login_required
def arcade_wheel_test(request):
    if not request.user.is_staff:
        return HttpResponseForbidden("Тест колеса доступен только администраторам.")
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    return render(request, "arcade_wheel_test.html", {
        "wheel_sectors": list(WHEEL_SECTORS),
        "driver_choices": DRIVER_CHOICES,
    })


@login_required
def arcade_wheel_spin(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    try:
        event_id = int(request.POST.get("event_id", ""))
        event = get_object_or_404(Event, pk=event_id)
        spin, created = spin_event_wheel(event, request.user)
    except (ValueError, TypeError, ArcadeWheelError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse({
        "created": created,
        "prize": spin.prize,
        "label": WHEEL_PRIZE_BY_KEY[spin.prize]["label"],
    })


@login_required
def arcade_wheel_activate(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    try:
        event_id = int(request.POST.get("event_id", ""))
        event = get_object_or_404(Event, pk=event_id)
        spin = activate_event_wheel_prize(event, request.user, request.POST)
    except (ValueError, TypeError, ArcadeWheelError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse({"activated": True, "prize": spin.prize})


def arcade_leaderboard(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    arcade_settings = _get_arcade_settings()
    if not _arcade_is_visible_to_user(request, arcade_settings):
        return HttpResponseForbidden("Аркада сейчас доступна только администраторам.")
    if arcade_settings.active_game == ArcadeSettings.Game.MINESWEEPER:
        return JsonResponse(_minesweeper_leaderboard_data(request.user))
    if arcade_settings.active_game != ArcadeSettings.Game.FLAPPY:
        return JsonResponse({"records": [], "attempts": 0, "wins": 0, "best_time_ms": None})
    season = get_selected_season(request)
    now = timezone.now()
    award_due_arcade_trophies(season.year, now=now)
    closure, _ = get_or_create_arcade_game_closure(season.year, now=now)
    if closure:
        return JsonResponse(closed_event_arcade_leaderboard(closure.event, request.user))
    return JsonResponse(_arcade_leaderboard_data(request.user))


def _arcade_leaderboard_data(user):
    records = list(
        ArcadeRecord.objects.select_related("user").filter(best_score__gt=0)
        .order_by("-best_score", "updated_at", "user__username")[:10]
    )
    rows = [{
        "username": row.user.get_full_name().strip() or row.user.username,
        "score": row.best_score,
        "attempts": row.total_attempts,
        "rank": index,
        "is_current_user": bool(user.is_authenticated and row.user_id == user.id),
    } for index, row in enumerate(records, start=1)]
    own_record = ArcadeRecord.objects.filter(user=user).first() if user.is_authenticated else None
    return {
        "records": rows,
        "record": own_record.best_score if own_record else 0,
        "attempts": own_record.total_attempts if own_record else 0,
        "total_attempts": ArcadeRecord.objects.aggregate(total=Sum("total_attempts"))["total"] or 0,
        "rank": _arcade_rank(own_record) if own_record and own_record.best_score else None,
    }


def arcade_run_start(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Войдите, чтобы сохранить рекорд в таблице."}, status=401)
    arcade_settings = _get_arcade_settings()
    if not _arcade_is_visible_to_user(request, arcade_settings):
        return JsonResponse({"error": "Аркада сейчас доступна только администраторам."}, status=403)
    if arcade_settings.active_game != ArcadeSettings.Game.FLAPPY:
        return JsonResponse({"error": "Pit Lane Flight сейчас не выбрана как активная аркада."}, status=410)
    now = timezone.now()
    closure, _ = get_or_create_arcade_game_closure(get_selected_season(request).year, now=now)
    if closure:
        return JsonResponse(
            {"error": "Pit Lane Flight закрыта после дедлайна — результаты зафиксированы."},
            status=410,
        )
    with transaction.atomic():
        ArcadeAttempt.objects.filter(
            user=request.user,
            started_at__lt=timezone.now() - timedelta(days=30),
        ).delete()
        attempt = ArcadeAttempt.objects.create(user=request.user)
        record, _ = ArcadeRecord.objects.select_for_update().get_or_create(user=request.user)
        ArcadeRecord.objects.filter(pk=record.pk).update(total_attempts=F("total_attempts") + 1)
        board_data = _arcade_leaderboard_data(request.user)
    return JsonResponse({"attempt_id": attempt.pk, **board_data})


def arcade_run_finish(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Войдите, чтобы сохранить рекорд в таблице."}, status=401)
    arcade_settings = _get_arcade_settings()
    if not _arcade_is_visible_to_user(request, arcade_settings):
        return JsonResponse({"error": "Аркада сейчас доступна только администраторам."}, status=403)
    if arcade_settings.active_game != ArcadeSettings.Game.FLAPPY:
        return JsonResponse({"error": "Pit Lane Flight сейчас не выбрана как активная аркада."}, status=410)
    now = timezone.now()
    closure, _ = get_or_create_arcade_game_closure(get_selected_season(request).year, now=now)
    if closure:
        return JsonResponse(
            {"error": "Pit Lane Flight закрыта после дедлайна — результаты зафиксированы."},
            status=410,
        )
    try:
        payload = json.loads(request.body or b"{}")
        attempt_id = int(payload.get("attempt_id"))
        score = int(payload.get("score"))
        if isinstance(payload.get("score"), bool) or score < 1 or score > 500:
            raise ValueError
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "Некорректный результат заезда."}, status=400)

    with transaction.atomic():
        attempt = ArcadeAttempt.objects.select_for_update().filter(pk=attempt_id, user=request.user).first()
        if not attempt or attempt.finished_at:
            return JsonResponse({"error": "Этот заезд уже сохранён или не найден."}, status=409)
        now = timezone.now()
        elapsed_seconds = (now - attempt.started_at).total_seconds()
        minimum_seconds = 3.0 + (score - 1) * 1.15
        maximum_seconds = 12.0 + (score - 1) * 2.6
        if elapsed_seconds < minimum_seconds or elapsed_seconds > maximum_seconds:
            attempt.finished_at = now
            attempt.save(update_fields=("finished_at",))
            return JsonResponse({"error": "Время заезда не соответствует указанному результату."}, status=400)
        attempt.finished_at = now
        attempt.score = score
        attempt.save(update_fields=("finished_at", "score"))

        # Lock the small leaderboard consistently so concurrent finishes cannot
        # both announce themselves as the arcade leader.
        list(
            ArcadeRecord.objects.select_for_update()
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        leader_before_id = (
            ArcadeRecord.objects.filter(best_score__gt=0)
            .order_by("-best_score", "updated_at", "user__username")
            .values_list("user_id", flat=True)
            .first()
        )
        record, _ = ArcadeRecord.objects.select_for_update().get_or_create(user=request.user)
        is_record = score > record.best_score
        if is_record:
            record.best_score = score
            record.save(update_fields=("best_score", "updated_at"))
        leader_after_id = (
            ArcadeRecord.objects.filter(best_score__gt=0)
            .order_by("-best_score", "updated_at", "user__username")
            .values_list("user_id", flat=True)
            .first()
        )
        if leader_after_id == request.user.id and leader_before_id != leader_after_id:
            ArcadeLeadChange.objects.create(
                player=request.user,
                best_score=record.best_score,
                attempts=record.total_attempts,
            )
        board_data = _arcade_leaderboard_data(request.user)
    return JsonResponse({**board_data, "is_record": is_record})


@login_required
def minesweeper_attempt_start(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    arcade_settings = _get_arcade_settings()
    if not _arcade_is_visible_to_user(request, arcade_settings):
        return JsonResponse({"error": "Аркада сейчас доступна только администраторам."}, status=403)
    if arcade_settings.active_game != ArcadeSettings.Game.MINESWEEPER:
        return JsonResponse({"error": "Сапёр сейчас не выбран как активная аркада."}, status=410)

    attempt = MinesweeperAttempt.objects.create(
        user=request.user,
        week_start=_current_arcade_week_start(),
    )
    return JsonResponse({
        "attempt_id": attempt.pk,
        **_minesweeper_leaderboard_data(request.user, attempt.week_start),
    })


@login_required
def minesweeper_attempt_finish(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    arcade_settings = _get_arcade_settings()
    if not _arcade_is_visible_to_user(request, arcade_settings):
        return JsonResponse({"error": "Аркада сейчас доступна только администраторам."}, status=403)
    if arcade_settings.active_game != ArcadeSettings.Game.MINESWEEPER:
        return JsonResponse({"error": "Сапёр сейчас не выбран как активная аркада."}, status=410)
    try:
        payload = json.loads(request.body or b"{}")
        attempt_id = int(payload.get("attempt_id"))
        completed = payload.get("completed")
        elapsed_ms = payload.get("elapsed_ms")
        if not isinstance(completed, bool):
            raise ValueError
        if completed and (
            isinstance(elapsed_ms, bool)
            or not isinstance(elapsed_ms, int)
            or elapsed_ms < 3000
            or elapsed_ms > 24 * 60 * 60 * 1000
        ):
            raise ValueError
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "Некорректный результат попытки."}, status=400)

    with transaction.atomic():
        attempt = MinesweeperAttempt.objects.select_for_update().filter(
            pk=attempt_id,
            user=request.user,
        ).first()
        if not attempt or attempt.finished_at:
            return JsonResponse({"error": "Попытка уже сохранена или не найдена."}, status=409)
        now = timezone.now()
        elapsed_server_ms = int((now - attempt.started_at).total_seconds() * 1000)
        if completed and elapsed_ms > elapsed_server_ms + 2500:
            return JsonResponse({"error": "Время прохождения не совпадает с началом попытки."}, status=400)
        attempt.finished_at = now
        attempt.completed = completed
        attempt.elapsed_ms = elapsed_ms if completed else None
        attempt.save(update_fields=("finished_at", "completed", "elapsed_ms"))
        data = _minesweeper_leaderboard_data(request.user, attempt.week_start)
    return JsonResponse(data)


def _arcade_rank(record):
    ahead = Q(best_score__gt=record.best_score)
    ahead |= Q(best_score=record.best_score, updated_at__lt=record.updated_at)
    ahead |= Q(
        best_score=record.best_score,
        updated_at=record.updated_at,
        user__username__lt=record.user.username,
    )
    return ArcadeRecord.objects.filter(best_score__gt=0).filter(ahead).count() + 1


def _wildcard_payload(assignment):
    question = assignment.question
    return {
        "assignment_id": assignment.id,
        "card_slot": assignment.card_slot,
        "question": question.question,
        "option_a": question.option_a,
        "option_b": question.option_b,
        "option_c": question.option_c,
        "points": question.points,
        "selected_option": assignment.selected_option,
    }


def home(request):
    now = timezone.now()
    season = get_selected_season(request)
    award_due_arcade_trophies(season.year, now=now)
    events = list(Event.objects.filter(season_year=season.year).order_by("-round_number"))
    upcoming_events = []
    past_events = []

    for event in events:
        event_time = event.race_datetime or event.deadline
        is_past = event.status == Event.Status.SCORED or (event_time and event_time < now)
        if is_past:
            past_events.append(event)
        else:
            upcoming_events.append(event)

    result_images = list(
        HomeResultImage.objects.filter(is_active=True, season_year=season.year)
    )
    leaderboard_data = build_leaderboard(season.year)
    saved_event_ids = set()
    if request.user.is_authenticated:
        saved_event_ids = set(
            Prediction.objects.filter(user=request.user, event__in=events).values_list("event_id", flat=True)
        )
    for event in events:
        voting_state = event.voting_state()
        if voting_state == "scored":
            event.ui_state = "scored"
        elif voting_state == "open" and event.id in saved_event_ids:
            event.ui_state = "saved"
        elif voting_state == "open":
            event.ui_state = "open"
        elif voting_state == "soon":
            event.ui_state = "soon"
        else:
            event.ui_state = "locked"
    personal_dashboard = None
    next_event = min(
        (event for event in events if event.deadline > now and event.status != Event.Status.SCORED),
        key=lambda event: event.deadline,
        default=None,
    )
    featured_event = next_event or (events[0] if events else None)
    featured_is_upcoming = bool(
        featured_event
        and featured_event.status != Event.Status.SCORED
        and featured_event.deadline > now
    )
    featured_prediction = (
        Prediction.objects.filter(event=featured_event, user=request.user).first()
        if request.user.is_authenticated and featured_event
        else None
    )
    jury_event = min(
        (event for event in events if crazy_vote_is_open(event, now)),
        key=lambda event: event.race_datetime,
        default=None,
    )
    if request.user.is_authenticated:
        user_row = next(
            (row for row in leaderboard_data["rows"] if row["user"].id == request.user.id),
            None,
        )
        latest_event = leaderboard_data["latest_event"]
        personal_dashboard = {
            "next_event": next_event,
            "next_prediction": (
                Prediction.objects.filter(event=next_event, user=request.user).first()
                if next_event
                else None
            ),
            "rank": user_row["rank"] if user_row else None,
            "movement": user_row["movement"] if user_row else 0,
            "total": user_row["total"] if user_row else 0,
            "latest_event": latest_event,
            "latest_score": (
                Score.objects.filter(event=latest_event, user=request.user).first()
                if latest_event
                else None
            ),
            "next_duel": get_user_event_duel(next_event, request.user) if next_event else None,
        }

    return render(
        request,
        "home.html",
        {
            "events": events,
            "upcoming_events": upcoming_events,
            "past_events": past_events,
            "total_events": len(events),
            "result_images": result_images,
            "season": season,
            "personal_dashboard": personal_dashboard,
            "featured_event": featured_event,
            "featured_prediction": featured_prediction,
            "featured_is_upcoming": featured_is_upcoming,
            "leaderboard_top": leaderboard_data["rows"][:3],
            "activity_feed": build_activity_feed(leaderboard_data),
            "crazy_jury": crazy_jury_context(jury_event, request.user, now) if jury_event else None,
        },
    )


def activity_feed_updates(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    season = get_selected_season(request)
    award_due_arcade_trophies(season.year, now=timezone.now())
    activity_feed = build_activity_feed(build_leaderboard(season.year))
    html = render_to_string(
        "activity_feed_items.html",
        {"activity_feed": activity_feed, "season": season},
        request=request,
    )
    response = JsonResponse({"html": html})
    response["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response


@login_required
def cast_crazy_vote(request, event_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    event = get_object_or_404(Event, pk=event_id)
    try:
        cast_crazy_prediction_vote(
            event,
            request.user,
            request.POST.get("target_prediction"),
        )
    except CrazyVoteError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Голос принят. Итоги останутся скрыты до старта гонки.")
    return redirect(f"{reverse('league:home')}?season={event.season_year}#crazy-jury")


@login_required
def paddock_jury_admin(request):
    if not request.user.is_staff:
        return HttpResponseForbidden("Эта страница доступна только администраторам.")
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    season = get_selected_season(request)
    now = timezone.now()
    events = list(
        Event.objects.filter(season_year=season.year)
        .filter(
            Q(crazy_prediction_votes__isnull=False)
            | Q(deadline__lte=now, race_datetime__gt=now)
            | Q(crazy_vote_closed_at__isnull=False)
        )
        .distinct()
        .order_by("-round_number")
    )
    requested_event_id = request.GET.get("event")
    event = next(
        (item for item in events if str(item.pk) == requested_event_id),
        events[0] if events else None,
    )

    candidate_rows = []
    votes = []
    vetoed_prediction_id = None
    vote_is_open = False
    vote_is_final = False
    if event:
        candidates = crazy_vote_candidates(event)
        votes = list(
            CrazyPredictionVote.objects.filter(event=event)
            .select_related("voter", "target_prediction", "target_prediction__user")
            .order_by("created_at", "id")
        )
        votes_by_prediction = {}
        for vote in votes:
            votes_by_prediction.setdefault(vote.target_prediction_id, []).append(vote)

        candidate_rows = [
            {
                "number": index,
                "prediction": candidate,
                "votes": votes_by_prediction.get(candidate.pk, []),
            }
            for index, candidate in enumerate(candidates, start=1)
        ]
        vote_is_open = crazy_vote_is_open(event, now)
        vote_is_final = crazy_vote_is_finished(event, now)
        if vote_is_final:
            vetoed_prediction_id = vetoed_crazy_prediction_id(event, now)

    return render(
        request,
        "paddock_jury_admin.html",
        {
            "season": season,
            "events": events,
            "jury_event": event,
            "candidate_rows": candidate_rows,
            "vote_total": len(votes),
            "vote_is_open": vote_is_open,
            "vote_is_final": vote_is_final,
            "vetoed_prediction_id": vetoed_prediction_id,
        },
    )


@login_required
def close_crazy_vote(request, event_id):
    if not request.user.is_staff:
        return HttpResponseForbidden("Эта операция доступна только администраторам.")
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    with transaction.atomic():
        event = get_object_or_404(Event.objects.select_for_update(), pk=event_id)
        now = timezone.now()
        if not crazy_vote_is_open(event, now):
            messages.warning(request, "Голосование уже закрыто или ещё не началось.")
        else:
            event.crazy_vote_closed_at = now
            event.save(update_fields=("crazy_vote_closed_at",))
            vetoed_id = vetoed_crazy_prediction_id(event, now)
            if vetoed_id:
                target = Prediction.objects.select_related("user").get(pk=vetoed_id)
                messages.success(
                    request,
                    f"Paddock Jury закрыт. Исключён предикт участника {target.user.username}.",
                )
            else:
                messages.success(
                    request,
                    "Paddock Jury закрыт. Из-за ничьей или отсутствия голосов предикт не исключён.",
                )

    return redirect(
        f"{reverse('league:paddock_jury_admin')}?season={event.season_year}&event={event.pk}"
    )


def season_predictions(request):
    season = get_selected_season(request)
    season_year = season.year
    deadline = season.predictions_deadline or datetime(
        season.year,
        3,
        5,
        23,
        59,
        tzinfo=ZoneInfo("Europe/Moscow"),
    )
    now = timezone.now()
    is_locked = now > deadline

    category_groups = [
        {
            "title": "Промежуточные сезонные предикты",
            "items": [
                ("Лидер чемпионата пилотов после этапа Венгрии", 12),
                ("Лидер Кубка конструкторов после этапа Венгрии", 10),
                ("Самый высокий финиш Хаджара", 8),
            ],
        },
        {
            "title": "Итоги сезона",
            "items": [
                ("Чемпион мира среди пилотов", 25),
                ("Чемпион Кубка конструкторов", 20),
                ("2 место Кубка конструкторов", 12),
                ("3 место Кубка конструкторов", 10),
            ],
        },
        {
            "title": "Дополнительные сезонные категории",
            "items": [
                ("Победитель последней гонки сезона", 10),
                ("Pole-sitter сезона (наибольшее число поулов)", 12),
                ("Была ли смена пилота в сезоне", 8),
                ("Команда-лидер по количеству DNF", 12),
            ],
        },
    ]

    prediction = None
    form = None

    if request.user.is_authenticated:
        prediction = SeasonPrediction.objects.filter(user=request.user, season_year=season_year).first()

        if request.method == "POST":
            if is_locked:
                messages.error(request, "Дедлайн сезонных предиктов уже прошел.")
                return redirect("league:season_predictions")

            form = SeasonPredictionForm(request.POST, instance=prediction)
            if form.is_valid():
                prediction_obj = form.save(commit=False)
                prediction_obj.user = request.user
                prediction_obj.season_year = season_year
                prediction_obj.save()
                messages.success(request, "Сезонные предикты сохранены.")
                return redirect("league:season_predictions")
        else:
            form = SeasonPredictionForm(instance=prediction)
    else:
        if request.method == "POST":
            messages.error(request, "Нужно войти в аккаунт для отправки сезонных предиктов.")
            return redirect("login")

    return render(
        request,
        "season_predictions.html",
        {
            "season_year": season_year,
            "season": season,
            "deadline": deadline,
            "is_locked": is_locked,
            "form": form,
            "prediction": prediction,
            "category_groups": category_groups,
        },
    )


def register(request):
    next_url = request.GET.get("next") or request.POST.get("next") or "league:home"

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            if next_url.startswith("/"):
                return redirect(next_url)
            return redirect("league:home")
    else:
        form = RegisterForm()

    return render(request, "registration/register.html", {"form": form, "next": next_url})


def event_detail(request, event_id: int):
    event = get_object_or_404(Event, id=event_id)
    now = timezone.now()
    crazy_vote_open = crazy_vote_is_open(event, now)
    crazy_vote_finished = crazy_vote_is_finished(event, now)
    vetoed_crazy_id = vetoed_crazy_prediction_id(event, now)
    photos = event.photos.all()
    result_obj = getattr(event, "result", None)
    event_time = event.race_datetime or event.deadline
    is_past_event = event.status == Event.Status.SCORED or (event_time and event_time < now)

    state = event.voting_state()
    prediction = None
    wildcard_assignment = None
    wildcard_offer_cards = []
    wildcard_offer_error = ""
    if request.user.is_authenticated:
        prediction = Prediction.objects.filter(event=event, user=request.user).first()
        wildcard_assignment = (
            PlayerWildcard.objects.filter(event=event, user=request.user)
            .select_related("question")
            .first()
        )

        if state == "open" and wildcard_assignment is None:
            try:
                wildcard_offer, _ = get_or_create_wildcard_offer(event, request.user)
            except WildcardActionError as exc:
                wildcard_offer_error = str(exc)
            else:
                wildcard_offer_cards = list(wildcard_offer.cards.all())

    wildcard_settings = WildcardSettings.objects.first()

    is_locked = state != "open"

    if request.method == "POST":
        if not request.user.is_authenticated:
            messages.error(request, "Нужно войти в аккаунт.")
            return redirect("league:event_detail", event_id=event.id)

        state = event.voting_state()
        is_locked = state != "open"

        if is_locked:
            if state == "soon":
                messages.error(request, "Голосование еще не началось. Оно откроется за 7 дней до гонки.")
            elif state == "scored":
                messages.error(request, "Очки уже посчитаны, прогнозы зафиксированы.")
            else:
                messages.error(request, "Дедлайн прошел, прогнозы закрыты.")
            return redirect("league:event_detail", event_id=event.id)

        form = PredictionForm(request.POST, instance=prediction, event=event)
        if form.is_valid():
            new_prediction = form.save(commit=False)
            new_prediction.user = request.user
            new_prediction.event = event
            new_prediction.save()
            messages.success(request, "Прогноз сохранен.")
            return redirect("league:event_detail", event_id=event.id)
    else:
        state = event.voting_state()
        is_locked = state != "open"
        form = PredictionForm(instance=prediction, event=event)

    score = None
    wheel_spin = (
        ArcadeWheelSpin.objects.filter(event=event, activated_at__isnull=False)
        .select_related("winner", "target_user")
        .first()
    )
    if request.user.is_authenticated:
        score = Score.objects.filter(event=event, user=request.user).first()

    factual_rows = []
    if result_obj:
        driver_of_day_values = _driver_of_day_values(result_obj)
        factual_rows = [
            {"label": "P1", "value": _driver_label(result_obj.p1)},
            {"label": "P2", "value": _driver_label(result_obj.p2)},
            {"label": "P3", "value": _driver_label(result_obj.p3)},
            {"label": "Поул", "value": _driver_label(result_obj.pole)},
            {"label": "Fastest Lap", "value": _driver_label(result_obj.fastest_lap)},
            {
                "label": "Driver of the Day",
                "value": ", ".join(_driver_label(value) for value in driver_of_day_values) or "—",
            },
            {"label": "Safety Car", "value": result_obj.safety_car_count},
            {"label": "DNF", "value": result_obj.dnf_count},
        ]
        if event.has_sprint:
            factual_rows.extend(
                [
                    {"label": "Квалификация к спринту", "value": _driver_label(result_obj.sprint_qualifying_winner)},
                    {"label": "Спринт", "value": _driver_label(result_obj.sprint_winner)},
                ]
            )

    comparison_rows = []
    comparison_total = 0
    crazy_vetoed = bool(prediction and vetoed_crazy_id == prediction.id)
    if prediction and result_obj:
        actual_podium = {
            "p1": _normalize(result_obj.p1),
            "p2": _normalize(result_obj.p2),
            "p3": _normalize(result_obj.p3),
        }
        actual_top3 = {value for value in actual_podium.values() if value}
        actual_driver_of_day = {_normalize(value) for value in _driver_of_day_values(result_obj)}

        def add_row(label, predicted, actual, points, max_points, status, note=""):
            nonlocal comparison_total
            comparison_total += points
            comparison_rows.append(
                {
                    "label": label,
                    "predicted": predicted,
                    "actual": actual,
                    "points": points,
                    "max_points": max_points,
                    "status": status,
                    "note": note,
                }
            )

        for field_name, label, exact_points in (("p1", "P1", 10), ("p2", "P2", 6), ("p3", "P3", 4)):
            predicted_code = getattr(prediction, field_name)
            predicted_norm = _normalize(predicted_code)
            actual_norm = actual_podium[field_name]
            points = 0
            status = "miss"
            note = ""

            if predicted_norm and predicted_norm == actual_norm:
                points = exact_points
                status = "hit"
            elif predicted_norm and predicted_norm in actual_top3:
                points = 3
                status = "partial"
                note = "Угадан пилот в топ-3, но не точная позиция."

            add_row(
                label=label,
                predicted=_driver_label(predicted_code),
                actual=_driver_label(getattr(result_obj, field_name)),
                points=points,
                max_points=exact_points,
                status=status,
                note=note,
            )

        def add_exact_driver_row(label, predicted_code, actual_code, max_points):
            predicted_norm = _normalize(predicted_code)
            actual_norm = _normalize(actual_code)
            points = max_points if predicted_norm and actual_norm and predicted_norm == actual_norm else 0
            add_row(
                label=label,
                predicted=_driver_label(predicted_code),
                actual=_driver_label(actual_code),
                points=points,
                max_points=max_points,
                status="hit" if points else "miss",
            )

        add_exact_driver_row("Поул", prediction.pole, result_obj.pole, 4)
        if event.has_sprint:
            add_exact_driver_row(
                "Квалификация к спринту",
                prediction.sprint_qualifying_winner,
                result_obj.sprint_qualifying_winner,
                3,
            )
            add_exact_driver_row("Спринт", prediction.sprint_winner, result_obj.sprint_winner, 5)
        add_exact_driver_row("Fastest Lap", prediction.fastest_lap, result_obj.fastest_lap, 3)

        predicted_dod = _normalize(prediction.driver_of_day)
        dod_points = 3 if predicted_dod and predicted_dod in actual_driver_of_day else 0
        add_row(
            label="Driver of the Day",
            predicted=_driver_label(prediction.driver_of_day),
            actual=", ".join(_driver_label(value) for value in _driver_of_day_values(result_obj)) or "—",
            points=dod_points,
            max_points=3,
            status="hit" if dod_points else "miss",
        )

        add_row(
            label="Safety Car",
            predicted=prediction.safety_car_count,
            actual=result_obj.safety_car_count,
            points=5 if prediction.safety_car_count == result_obj.safety_car_count else 0,
            max_points=5,
            status="hit" if prediction.safety_car_count == result_obj.safety_car_count else "miss",
        )
        add_row(
            label="DNF",
            predicted=prediction.dnf_count,
            actual=result_obj.dnf_count,
            points=5 if prediction.dnf_count == result_obj.dnf_count else 0,
            max_points=5,
            status="hit" if prediction.dnf_count == result_obj.dnf_count else "miss",
        )
        crazy_blocked = bool(
            wheel_spin
            and wheel_spin.prize == ArcadeWheelSpin.Prize.CRAZY_BLOCK
            and wheel_spin.target_user_id == prediction.user_id
        )
        add_row(
            label=(
                "Crazy Prediction · вето паддока и блок колеса" if crazy_vetoed and crazy_blocked
                else "Crazy Prediction · вето паддока" if crazy_vetoed
                else "Crazy Prediction · заблокирован" if crazy_blocked
                else "Crazy Prediction"
            ),
            predicted=prediction.crazy_prediction or "—",
            actual=(
                "Снят анонимным голосованием и заблокирован колесом"
                if crazy_vetoed and crazy_blocked
                else "Снят анонимным голосованием"
                if crazy_vetoed
                else "Заблокировано колесом"
                if crazy_blocked
                else "Засчитано судьей" if prediction.crazy_prediction_approved else "Не засчитано судьей"
            ),
            points=5 if prediction.crazy_prediction_approved and not crazy_blocked and not crazy_vetoed else 0,
            max_points=5,
            status="hit" if prediction.crazy_prediction_approved and not crazy_blocked and not crazy_vetoed else "miss",
        )

    if (
        wildcard_assignment
        and wildcard_assignment.selected_option
        and state == "scored"
        and wildcard_assignment.question.correct_option
    ):
        wildcard_points = wildcard_assignment.awarded_points
        comparison_total += wildcard_points
        comparison_rows.append(
            {
                "label": "Личная карта этапа",
                "predicted": wildcard_assignment.selected_answer,
                "actual": wildcard_assignment.correct_answer,
                "points": wildcard_points,
                "max_points": wildcard_assignment.question.points,
                "status": "hit" if wildcard_points > 0 else "miss",
                "note": wildcard_assignment.question.question,
            }
        )

    if state == "scored" and result_obj and wheel_spin:
        if wheel_spin.winner_id == request.user.id:
            if wheel_spin.prize == ArcadeWheelSpin.Prize.PIT_WALL:
                add_wheel_row = {
                    "label": "Бонус пит-уолла",
                    "predicted": "Активирован",
                    "actual": "+2 очка",
                    "points": 2,
                    "max_points": 2,
                    "status": "hit",
                }
                comparison_rows.append(add_wheel_row)
                comparison_total += 2
            elif wheel_spin.prize == ArcadeWheelSpin.Prize.CARD_BOOST:
                card_hit = bool(wildcard_assignment and wildcard_assignment.is_correct)
                card_bonus = 3 if card_hit else 0
                comparison_rows.append(
                    {
                        "label": "ДРС личной карты",
                        "predicted": wildcard_assignment.selected_answer if wildcard_assignment else "—",
                        "actual": "+3 за верную карту" if card_hit else "Карта не угадана",
                        "points": card_bonus,
                        "max_points": 3,
                        "status": "hit" if card_hit else "miss",
                    }
                )
                comparison_total += card_bonus
            elif wheel_spin.prize == ArcadeWheelSpin.Prize.VA_BANK:
                field_key = (wheel_spin.activation_data or {}).get("field", "")
                field_label = next(
                    (item["label"] for item in available_va_bank_fields(event, request.user, now=now) if item["key"] == field_key),
                    "выбранный прогноз",
                )
                bank_neutralized = field_key == "crazy_prediction" and crazy_vetoed
                bank_hit = False if bank_neutralized else va_bank_answer_is_correct(
                    prediction,
                    result_obj,
                    field_key,
                    wildcard_assignment,
                )
                bank_points = 0 if bank_neutralized else 4 if bank_hit else -1
                comparison_rows.append(
                    {
                        "label": "Ва-банк",
                        "predicted": field_label,
                        "actual": (
                            "Ставка отменена: прогноз снят голосованием"
                            if bank_neutralized
                            else "+4" if bank_hit else "−1"
                        ),
                        "points": bank_points,
                        "max_points": 4,
                        "status": "hit" if bank_hit else "miss",
                    }
                )
                comparison_total += bank_points

        if (
            wheel_spin.prize == ArcadeWheelSpin.Prize.RUEL_V_GOVNE
            and wheel_spin.target_user_id == request.user.id
        ):
            comparison_rows.append(
                {
                    "label": "Руль в говне",
                    "predicted": "Эффект соперника",
                    "actual": "−3 очка",
                    "points": -3,
                    "max_points": 0,
                    "status": "miss",
                }
            )
            comparison_total -= 3

    can_view_community = state in ("closed", "scored")
    community_predictions = []
    crazy_vote_results = []
    crazy_vote_total = 0
    if can_view_community:
        public_predictions = list(
            Prediction.objects.filter(event=event, user__is_active=True, user__is_staff=False)
            .select_related("user", "user__league_profile")
            .order_by("user__username")
        )
        public_scores = {
            item.user_id: item
            for item in Score.objects.filter(event=event)
        }
        public_wildcards = {
            item.user_id: item
            for item in PlayerWildcard.objects.filter(
                event=event,
                user__is_active=True,
                user__is_staff=False,
            ).select_related("question")
        }
        best_public_score = max(
            (item.points for item in public_scores.values()),
            default=None,
        )
        if crazy_vote_finished:
            ballots = list(
                CrazyPredictionVote.objects.filter(event=event)
                .select_related("voter")
                .order_by("created_at", "id")
            )
            crazy_vote_total = len(ballots)
            voters_by_target = {}
            for ballot in ballots:
                voters_by_target.setdefault(ballot.target_prediction_id, []).append(ballot.voter)
            crazy_vote_results = [
                {
                    "number": index,
                    "prediction": candidate,
                    "voters": voters_by_target[candidate.id],
                    "vote_count": len(voters_by_target[candidate.id]),
                    "vote_word": _russian_plural(
                        len(voters_by_target[candidate.id]),
                        ("голос", "голоса", "голосов"),
                    ),
                    "is_excluded": candidate.id == vetoed_crazy_id,
                }
                for index, candidate in enumerate(crazy_vote_candidates(event), start=1)
                if candidate.id in voters_by_target
            ]
        community_predictions = [
            {
                "prediction": item,
                "profile": getattr(item.user, "league_profile", None),
                "score": public_scores.get(item.user_id),
                "correct": _community_prediction_correctness(
                    item,
                    result_obj,
                    crazy_blocked=bool(
                        wheel_spin
                        and wheel_spin.prize == ArcadeWheelSpin.Prize.CRAZY_BLOCK
                        and wheel_spin.target_user_id == item.user_id
                    ),
                    crazy_vetoed=vetoed_crazy_id == item.id,
                ),
                "crazy_vetoed": vetoed_crazy_id == item.id,
                "wildcard": public_wildcards.get(item.user_id),
                "wildcard_correct": bool(
                    state == "scored"
                    and public_wildcards.get(item.user_id)
                    and public_wildcards[item.user_id].is_correct
                ),
                "wildcard_wrong": bool(
                    state == "scored"
                    and public_wildcards.get(item.user_id)
                    and public_wildcards[item.user_id].selected_option
                    and public_wildcards[item.user_id].question.correct_option
                    and not public_wildcards[item.user_id].is_correct
                ),
                "is_winner": (
                    best_public_score is not None
                    and public_scores.get(item.user_id) is not None
                    and public_scores[item.user_id].points == best_public_score
                ),
            }
            for item in public_predictions
        ]

    own_duel = get_user_event_duel(event, request.user)
    duel_settings = DuelSettings.objects.first()
    duel_form = None
    if request.user.is_authenticated and state == "open" and own_duel is None:
        initial = {}
        try:
            counter_id = int(request.GET.get("counter", ""))
            counter_stake = int(request.GET.get("stake", ""))
        except (TypeError, ValueError):
            counter_id = None
            counter_stake = None
        if counter_id:
            initial["opponent"] = counter_id
        if counter_stake and 1 <= counter_stake <= 10:
            initial["stake"] = counter_stake
        duel_form = DuelChallengeForm(event=event, user=request.user, initial=initial)

    event_duels = list(
        DuelChallenge.objects.filter(
            event=event,
            status__in=(DuelChallenge.Status.ACCEPTED, DuelChallenge.Status.SETTLED),
        ).select_related(
            "challenger",
            "opponent",
            "winner",
            "challenger__league_profile",
            "opponent__league_profile",
        )
    )
    duel_history = []
    if request.user.is_authenticated:
        duel_history = list(
            DuelChallenge.objects.filter(event=event)
            .filter(Q(challenger=request.user) | Q(opponent=request.user))
            .filter(
                status__in=(
                    DuelChallenge.Status.DECLINED,
                    DuelChallenge.Status.CANCELLED,
                    DuelChallenge.Status.EXPIRED,
                )
            )
            .select_related("challenger", "opponent")[:3]
        )

    return render(
        request,
        "event_detail_v2.html",
        {
            "event": event,
            "photos": photos,
            "form": form,
            "prediction": prediction,
            "result_obj": result_obj,
            "factual_rows": factual_rows,
            "state": state,
            "is_past_event": is_past_event,
            "is_locked": is_locked,
            "score": score,
            "comparison_rows": comparison_rows,
            "comparison_total": comparison_total,
            "can_view_community": can_view_community,
            "community_predictions": community_predictions,
            "crazy_vote_open": crazy_vote_open,
            "crazy_vote_finished": crazy_vote_finished,
            "crazy_vote_results": crazy_vote_results,
            "crazy_vote_total": crazy_vote_total,
            "crazy_vote_event": event if crazy_vote_open else None,
            "vetoed_crazy_prediction_id": vetoed_crazy_id,
            "own_duel": own_duel,
            "duel_settings": duel_settings,
            "duel_form": duel_form,
            "event_duels": event_duels,
            "duel_history": duel_history,
            "wildcard_assignment": wildcard_assignment,
            "wildcard_settings": wildcard_settings,
            "wildcard_offer_cards": wildcard_offer_cards,
            "wildcard_offer_error": wildcard_offer_error,
        },
    )


@login_required(login_url="login")
def draw_event_wildcard(request, event_id: int):
    if request.method != "POST":
        return HttpResponseNotAllowed(("POST",))
    event = get_object_or_404(Event, id=event_id)
    try:
        assignment, created = draw_wildcard(event, request.user, request.POST.get("slot", 2))
    except WildcardActionError as exc:
        if _is_async_request(request):
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        messages.error(request, str(exc))
    else:
        if _is_async_request(request):
            return JsonResponse({"ok": True, "created": created, **_wildcard_payload(assignment)})
        if created:
            messages.success(request, "Личная карта открыта. Теперь выбери свой ответ.")
        else:
            messages.info(request, "Твоя личная карта уже была открыта.")
    return redirect(f"{reverse('league:event_detail', args=(event.id,))}#personal-wildcard")


@login_required(login_url="login")
def answer_event_wildcard(request, event_id: int):
    if request.method != "POST":
        return HttpResponseNotAllowed(("POST",))
    event = get_object_or_404(Event, id=event_id)
    try:
        assignment = answer_wildcard(event, request.user, request.POST.get("choice", ""))
    except WildcardActionError as exc:
        if _is_async_request(request):
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        messages.error(request, str(exc))
    else:
        if _is_async_request(request):
            return JsonResponse(
                {
                    "ok": True,
                    "selected_option": assignment.selected_option,
                    "selected_answer": assignment.selected_answer,
                }
            )
        messages.success(request, "Ответ на личную карту сохранён.")
    return redirect(f"{reverse('league:event_detail', args=(event.id,))}#personal-wildcard")


@login_required(login_url="login")
def create_event_duel(request, event_id: int):
    if request.method != "POST":
        return HttpResponseNotAllowed(("POST",))
    event = get_object_or_404(Event, id=event_id)
    form = DuelChallengeForm(request.POST, event=event, user=request.user)
    if not form.is_valid():
        error = next(iter(form.errors.values()))[0] if form.errors else "Проверь данные вызова."
        messages.error(request, str(error))
        return redirect("league:event_detail", event_id=event.id)
    try:
        duel = create_duel_challenge(
            event,
            request.user,
            form.cleaned_data["opponent"],
            form.cleaned_data["stake"],
        )
    except DuelActionError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            f"Вызов отправлен игроку {duel.opponent.username}. Ставка — {duel.stake} очков.",
        )
    return redirect(f"{reverse('league:event_detail', args=(event.id,))}#event-duel")


@login_required(login_url="login")
def respond_event_duel(request, duel_id: int, action: str):
    if request.method != "POST":
        return HttpResponseNotAllowed(("POST",))
    duel = get_object_or_404(DuelChallenge.objects.select_related("event", "challenger"), id=duel_id)
    if action not in ("accept", "decline"):
        messages.error(request, "Неизвестное действие с дуэлью.")
        return redirect("league:event_detail", event_id=duel.event_id)
    try:
        duel = respond_to_duel(duel, request.user, accept=action == "accept")
    except DuelActionError as exc:
        messages.error(request, str(exc))
        return redirect(f"{reverse('league:event_detail', args=(duel.event_id,))}#event-duel")

    if action == "accept":
        messages.success(request, f"Дуэль принята. На кону {duel.stake} очков.")
        target = reverse("league:event_detail", args=(duel.event_id,))
    else:
        messages.info(request, "Вызов отклонён. Можешь сразу предложить свою ставку.")
        target = (
            f"{reverse('league:event_detail', args=(duel.event_id,))}"
            f"?counter={duel.challenger_id}&stake={duel.stake}#event-duel"
        )
    return redirect(target)


@login_required(login_url="login")
def cancel_event_duel(request, duel_id: int):
    if request.method != "POST":
        return HttpResponseNotAllowed(("POST",))
    duel = get_object_or_404(DuelChallenge.objects.select_related("event"), id=duel_id)
    try:
        cancel_duel_challenge(duel, request.user)
    except DuelActionError as exc:
        messages.error(request, str(exc))
    else:
        messages.info(request, "Вызов отменён.")
    return redirect(f"{reverse('league:event_detail', args=(duel.event_id,))}#event-duel")


def player_profile(request, user_id: int):
    player = get_object_or_404(User, id=user_id, is_active=True)
    profile_obj, _ = UserProfile.objects.get_or_create(user=player)
    can_edit_avatar = request.user.is_authenticated and request.user.id == player.id
    season = get_selected_season(request)
    now = timezone.now()
    award_due_arcade_trophies(season.year, now=now)

    avatar_form = None
    if request.method == "POST":
        if not can_edit_avatar:
            messages.error(request, "Можно менять только свой аватар.")
            return redirect("league:player_profile", user_id=player.id)

        avatar_form = AvatarUploadForm(request.POST, request.FILES, instance=profile_obj)
        if avatar_form.is_valid():
            avatar_form.save()
            messages.success(request, "Аватар обновлен.")
            return redirect("league:player_profile", user_id=player.id)
        messages.error(request, "Не удалось сохранить аватар. Проверь файл и попробуй еще раз.")
    elif can_edit_avatar:
        avatar_form = AvatarUploadForm(instance=profile_obj)

    events = list(Event.objects.filter(season_year=season.year).order_by("-round_number"))
    predictions = list(
        Prediction.objects.filter(user=player, event__season_year=season.year).select_related("event")
    )
    scores = list(Score.objects.filter(user=player, event__season_year=season.year).select_related("event"))

    prediction_map = {p.event_id: p for p in predictions}
    score_map = {s.event_id: s for s in scores}

    event_cards = []
    for event in events:
        can_view_prediction = can_edit_avatar or event.voting_state() in ("closed", "scored")
        event_cards.append(
            {
                "event": event,
                "prediction": prediction_map.get(event.id) if can_view_prediction else None,
                "prediction_hidden": bool(prediction_map.get(event.id)) and not can_view_prediction,
                "crazy_prediction_hidden": bool(
                    prediction_map.get(event.id) and crazy_vote_is_open(event, now)
                ),
                "score": score_map.get(event.id),
            }
        )

    season_deadline = season.predictions_deadline or datetime(
        season.year, 3, 5, 23, 59, tzinfo=ZoneInfo("Europe/Moscow")
    )
    can_view_season_prediction = can_edit_avatar or now > season_deadline
    season_predictions = list(
        SeasonPrediction.objects.filter(user=player, season_year=season.year)
        if can_view_season_prediction
        else SeasonPrediction.objects.none()
    )
    season_years = [item.season_year for item in season_predictions]
    season_score_map = {
        s.season_year: s for s in SeasonScore.objects.filter(user=player, season_year__in=season_years)
    }
    season_result_map = {
        r.season_year: r for r in SeasonResult.objects.filter(season_year__in=season_years)
    }

    season_cards = []
    for prediction in season_predictions:
        season_cards.append(
            {
                "prediction": prediction,
                "score": season_score_map.get(prediction.season_year),
                "result": season_result_map.get(prediction.season_year),
            }
        )

    event_points_total = sum(item.points for item in scores)
    season_points_total = sum(item.points for item in season_score_map.values())
    total_points = event_points_total + season_points_total
    leaderboard_data = build_leaderboard(season.year)
    player_statistics = build_player_statistics(player, season.year, leaderboard=leaderboard_data)
    achievements = build_achievements(player, player_statistics)
    arcade_record = ArcadeRecord.objects.filter(user=player).first()
    arcade_trophies = [
        {
            "trophy_name": award.trophy_name,
            "game_name": award.game_name,
            "image_url": award.image.url if award.image else "",
            "awarded_at": award.awarded_at,
            "attempts": award.attempts,
            "is_test": False,
        }
        for award in ArcadeTrophyAward.objects.filter(player=player).order_by("awarded_at", "pk")
    ]

    if not arcade_trophies and player.is_staff:
        arcade_trophies.append(
            {
                "trophy_name": "Банана Леклер",
                "game_name": "Pit Lane Flight",
                "image_url": "",
                "awarded_at": arcade_record.updated_at if arcade_record and not player.is_staff else None,
                "attempts": arcade_record.total_attempts if arcade_record else 0,
                "is_test": player.is_staff,
            }
        )

    return render(
        request,
        "player_profile.html",
        {
            "player": player,
            "event_cards": event_cards,
            "season_cards": season_cards,
            "season_prediction_hidden": (
                not can_view_season_prediction
                and SeasonPrediction.objects.filter(user=player, season_year=season.year).exists()
            ),
            "event_points_total": event_points_total,
            "season_points_total": season_points_total,
            "total_points": total_points,
            "events_count": len(events),
            "submitted_events_count": len(prediction_map),
            "profile_obj": profile_obj,
            "can_edit_avatar": can_edit_avatar,
            "avatar_form": avatar_form,
            "season": season,
            "player_statistics": player_statistics,
            "achievements": achievements,
            "arcade_trophies": arcade_trophies,
        },
    )


def leaderboard(request):
    season = get_selected_season(request)
    data = build_leaderboard(season.year)

    return render(
        request,
        "leaderboard.html",
        {
            "events": data["events"],
            "rows": data["rows"],
            "scores_map": data["scores_map"],
            "leaderboard_chart": data["chart"],
            "latest_event": data["latest_event"],
            "round_winners": [row for row in data["rows"] if row["is_round_winner"]],
            "season": season,
        },
    )


def duel(request):
    season = get_selected_season(request)
    leaderboard_data = build_leaderboard(season.year)
    candidates = [row["user"] for row in leaderboard_data["rows"]]

    def selected_id(parameter, fallback=None):
        try:
            value = int(request.GET.get(parameter, ""))
        except (TypeError, ValueError):
            return fallback
        return value if any(user.id == value for user in candidates) else fallback

    default_a = candidates[0].id if candidates else None
    default_b = candidates[1].id if len(candidates) > 1 else None
    player_a_id = selected_id("player_a", default_a)
    player_b_id = selected_id("player_b", default_b)
    player_a = next((user for user in candidates if user.id == player_a_id), None)
    player_b = next((user for user in candidates if user.id == player_b_id), None)

    duel_data = None
    duel_error = ""
    if player_a and player_b and player_a.id == player_b.id:
        duel_error = "Выбери двух разных участников."
    elif player_a and player_b:
        duel_data = build_duel(
            player_a,
            player_b,
            season.year,
            leaderboard=leaderboard_data,
        )
    elif len(candidates) < 2:
        duel_error = "Для дуэли нужны как минимум два участника."

    return render(
        request,
        "duel.html",
        {
            "season": season,
            "candidates": candidates,
            "player_a_id": player_a_id,
            "player_b_id": player_b_id,
            "duel": duel_data,
            "duel_error": duel_error,
        },
    )
