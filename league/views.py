from datetime import datetime
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import AvatarUploadForm, PredictionForm, RegisterForm, SeasonPredictionForm
from .models import (
    DRIVER_CHOICES,
    Event,
    HomeResultImage,
    Prediction,
    Score,
    SeasonPrediction,
    SeasonResult,
    SeasonScore,
    UserProfile,
)


DRIVER_LABELS = dict(DRIVER_CHOICES)


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


def home(request):
    now = timezone.now()
    events = list(Event.objects.all())
    upcoming_events = []
    past_events = []

    for event in events:
        event_time = event.race_datetime or event.deadline
        is_past = event.status == Event.Status.SCORED or (event_time and event_time < now)
        if is_past:
            past_events.append(event)
        else:
            upcoming_events.append(event)

    result_images = list(HomeResultImage.objects.filter(is_active=True))
    return render(
        request,
        "home.html",
        {
            "upcoming_events": upcoming_events,
            "past_events": past_events,
            "total_events": len(events),
            "result_images": result_images,
        },
    )


def season_predictions(request):
    season_year = 2026
    deadline = datetime(2026, 3, 5, 23, 59, tzinfo=ZoneInfo("Europe/Moscow"))
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
        },
    )


def player_profile(request, user_id: int):
    player = get_object_or_404(User, id=user_id, is_active=True)
    profile_obj, _ = UserProfile.objects.get_or_create(user=player)
    can_edit_avatar = request.user.is_authenticated and request.user.id == player.id

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

    events = list(Event.objects.all().order_by("round_number"))
    predictions = Prediction.objects.filter(user=player).select_related("event")
    scores = Score.objects.filter(user=player).select_related("event")

    prediction_map = {p.event_id: p for p in predictions}
    score_map = {s.event_id: s for s in scores}

    event_cards = []
    for event in events:
        event_cards.append(
            {
                "event": event,
                "prediction": prediction_map.get(event.id),
                "score": score_map.get(event.id),
            }
        )

    season_predictions = list(SeasonPrediction.objects.filter(user=player).order_by("-season_year"))
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

    return render(
        request,
        "player_profile.html",
        {
            "player": player,
            "event_cards": event_cards,
            "season_cards": season_cards,
            "event_points_total": event_points_total,
            "season_points_total": season_points_total,
            "total_points": total_points,
            "events_count": len(events),
            "submitted_events_count": len(prediction_map),
            "profile_obj": profile_obj,
            "can_edit_avatar": can_edit_avatar,
            "avatar_form": avatar_form,
        },
    )


def participants(request):
    event_totals_qs = Score.objects.values("user_id").annotate(total=Sum("points"))
    season_totals_qs = SeasonScore.objects.values("user_id").annotate(total=Sum("points"))
    event_totals = {item["user_id"]: int(item["total"] or 0) for item in event_totals_qs}
    season_totals = {item["user_id"]: int(item["total"] or 0) for item in season_totals_qs}

    event_submissions_qs = Prediction.objects.values("user_id").annotate(total=Count("id"))
    season_submissions_qs = SeasonPrediction.objects.values("user_id").annotate(total=Count("id"))
    event_submissions = {item["user_id"]: int(item["total"] or 0) for item in event_submissions_qs}
    season_submissions = {item["user_id"]: int(item["total"] or 0) for item in season_submissions_qs}

    users = list(User.objects.filter(is_staff=False, is_active=True).order_by("username"))
    user_ids = [user.id for user in users]
    profile_map = {
        profile.user_id: profile for profile in UserProfile.objects.filter(user_id__in=user_ids)
    }

    rows = []
    for user in users:
        event_count = event_submissions.get(user.id, 0)
        season_count = season_submissions.get(user.id, 0)
        if event_count == 0 and season_count == 0:
            continue

        profile_obj = profile_map.get(user.id)
        avatar_url = profile_obj.avatar.url if profile_obj and profile_obj.avatar else None
        total_points = event_totals.get(user.id, 0) + season_totals.get(user.id, 0)
        rows.append(
            {
                "user": user,
                "avatar_url": avatar_url,
                "event_count": event_count,
                "season_count": season_count,
                "total_points": total_points,
                "is_wpc": bool(profile_obj and profile_obj.is_world_predict_champion),
            }
        )

    rows.sort(key=lambda item: (-item["total_points"], item["user"].username.lower()))

    return render(request, "participants.html", {"rows": rows})


def leaderboard(request):
    events = Event.objects.all()

    scores = Score.objects.select_related("user", "event").all()
    scores_map = {(s.user_id, s.event_id): s for s in scores}

    totals_qs = Score.objects.values("user_id").annotate(total=Sum("points"))
    totals_map = {x["user_id"]: int(x["total"] or 0) for x in totals_qs}

    users = list(User.objects.filter(is_staff=False, is_active=True))
    users_sorted = sorted(users, key=lambda u: (-totals_map.get(u.id, 0), u.username.lower()))
    user_ids = [user.id for user in users_sorted]
    profile_map = {
        profile.user_id: profile for profile in UserProfile.objects.filter(user_id__in=user_ids)
    }

    rows = []
    for idx, user in enumerate(users_sorted, start=1):
        profile_obj = profile_map.get(user.id)
        rows.append(
            {
                "user": user,
                "rank": idx,
                "total": totals_map.get(user.id, 0),
                "is_leader": idx == 1,
                "avatar_url": profile_obj.avatar.url if profile_obj and profile_obj.avatar else None,
                "is_wpc": bool(profile_obj and profile_obj.is_world_predict_champion),
            }
        )

    return render(
        request,
        "leaderboard.html",
        {
            "events": events,
            "rows": rows,
            "scores_map": scores_map,
        },
    )
