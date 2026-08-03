import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Q, Sum
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
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
    DuelChallenge,
    Event,
    HomeResultImage,
    Prediction,
    Score,
    SeasonPrediction,
    SeasonResult,
    SeasonScore,
    UserProfile,
)
from .services import (
    build_achievements,
    build_activity_feed,
    build_duel,
    build_leaderboard,
    build_player_statistics,
    get_selected_season,
)
from .telegram_bot import TelegramAPIError, bot_is_configured, get_bot_username, notify_prediction_saved


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


def _community_prediction_correctness(prediction, result):
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
        and (prediction.crazy_prediction or "").strip()
        and prediction.crazy_prediction_approved
    )
    return correct


def home(request):
    now = timezone.now()
    season = get_selected_season(request)
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
            "leaderboard_top": leaderboard_data["rows"][:3],
            "activity_feed": build_activity_feed(leaderboard_data),
        },
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


@login_required(login_url="login")
def connect_telegram(request):
    bot_username = get_bot_username()
    if not bot_username:
        messages.error(request, "Telegram-бот ещё не настроен администрацией сайта.")
        return redirect("league:player_profile", user_id=request.user.id)

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    connect_url = (
        f"https://t.me/{bot_username}"
        f"?start={profile.telegram_link_token}"
    )
    return redirect(connect_url)


def event_detail(request, event_id: int):
    event = get_object_or_404(Event, id=event_id)
    photos = event.photos.all()
    result_obj = getattr(event, "result", None)
    event_time = event.race_datetime or event.deadline
    is_past_event = event.status == Event.Status.SCORED or (event_time and event_time < timezone.now())

    prediction = None
    if request.user.is_authenticated:
        prediction = Prediction.objects.filter(event=event, user=request.user).first()

    state = event.voting_state()
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
            try:
                notify_prediction_saved(new_prediction)
            except TelegramAPIError:
                # Telegram must never prevent the prediction itself from being saved.
                logger.exception("Could not send prediction confirmation for prediction %s", new_prediction.pk)
            messages.success(request, "Прогноз сохранен.")
            return redirect("league:event_detail", event_id=event.id)
    else:
        state = event.voting_state()
        is_locked = state != "open"
        form = PredictionForm(instance=prediction, event=event)

    score = None
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
        add_row(
            label="Crazy Prediction",
            predicted=prediction.crazy_prediction or "—",
            actual="Засчитано судьей" if prediction.crazy_prediction_approved else "Не засчитано судьей",
            points=5 if prediction.crazy_prediction_approved else 0,
            max_points=5,
            status="hit" if prediction.crazy_prediction_approved else "miss",
        )

    can_view_community = state in ("closed", "scored")
    community_predictions = []
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
        best_public_score = max(
            (item.points for item in public_scores.values()),
            default=None,
        )
        community_predictions = [
            {
                "prediction": item,
                "profile": getattr(item.user, "league_profile", None),
                "score": public_scores.get(item.user_id),
                "correct": _community_prediction_correctness(item, result_obj),
                "is_winner": (
                    best_public_score is not None
                    and public_scores.get(item.user_id) is not None
                    and public_scores[item.user_id].points == best_public_score
                ),
            }
            for item in public_predictions
        ]

    own_duel = get_user_event_duel(event, request.user)
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
            "own_duel": own_duel,
            "duel_form": duel_form,
            "event_duels": event_duels,
            "duel_history": duel_history,
        },
    )


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
        respond_to_duel(duel, request.user, accept=action == "accept")
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
                "score": score_map.get(event.id),
            }
        )

    season_deadline = season.predictions_deadline or datetime(
        season.year, 3, 5, 23, 59, tzinfo=ZoneInfo("Europe/Moscow")
    )
    can_view_season_prediction = can_edit_avatar or timezone.now() > season_deadline
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
            "telegram_bot_configured": bot_is_configured(),
            "season": season,
            "player_statistics": player_statistics,
            "achievements": achievements,
        },
    )


def participants(request):
    season = get_selected_season(request)
    event_totals_qs = Score.objects.filter(event__season_year=season.year).values("user_id").annotate(total=Sum("points"))
    season_totals_qs = SeasonScore.objects.filter(season_year=season.year).values("user_id").annotate(total=Sum("points"))
    event_totals = {item["user_id"]: int(item["total"] or 0) for item in event_totals_qs}
    season_totals = {item["user_id"]: int(item["total"] or 0) for item in season_totals_qs}

    event_submissions_qs = Prediction.objects.filter(event__season_year=season.year).values("user_id").annotate(total=Count("id"))
    season_submissions_qs = SeasonPrediction.objects.filter(season_year=season.year).values("user_id").annotate(total=Count("id"))
    event_submissions = {item["user_id"]: int(item["total"] or 0) for item in event_submissions_qs}
    season_submissions = {item["user_id"]: int(item["total"] or 0) for item in season_submissions_qs}

    users = list(User.objects.filter(is_staff=False, is_active=True).order_by("username"))
    user_ids = [user.id for user in users]
    profile_map = {
        profile.user_id: profile for profile in UserProfile.objects.filter(user_id__in=user_ids)
    }
    leaderboard_data = build_leaderboard(season.year)
    leaderboard_rows = {row["user"].id: row for row in leaderboard_data["rows"]}

    rows = []
    for user in users:
        event_count = event_submissions.get(user.id, 0)
        season_count = season_submissions.get(user.id, 0)
        if event_count == 0 and season_count == 0:
            continue

        profile_obj = profile_map.get(user.id)
        avatar_url = profile_obj.avatar.url if profile_obj and profile_obj.avatar else None
        total_points = event_totals.get(user.id, 0) + season_totals.get(user.id, 0)
        statistics = build_player_statistics(user, season.year, leaderboard=leaderboard_data)
        rows.append(
            {
                "user": user,
                "avatar_url": avatar_url,
                "event_count": event_count,
                "season_count": season_count,
                "total_points": total_points,
                "is_wpc": bool(profile_obj and profile_obj.is_world_predict_champion),
                "rank": leaderboard_rows.get(user.id, {}).get("rank"),
                "movement": leaderboard_rows.get(user.id, {}).get("movement", 0),
                "achievement_count": len(build_achievements(user, statistics)),
            }
        )

    rows.sort(key=lambda item: (-item["total_points"], item["user"].username.lower()))

    return render(request, "participants.html", {"rows": rows, "season": season})


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
