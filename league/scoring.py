from django.db import transaction
from collections import defaultdict

from django.db.models import Max
from django.utils import timezone

from .models import (
    DuelChallenge,
    Event,
    PlayerWildcard,
    Prediction,
    Score,
    ScoreRevision,
    SeasonPrediction,
    SeasonResult,
    SeasonScore,
)
from .wildcards import unresolved_wildcard_questions

SEASON_SCORING_WEIGHTS = {
    "hungary_driver_championship_leader": ("Лидер пилотского зачета после Венгрии", 12),
    "hungary_constructor_championship_leader": ("Лидер Кубка конструкторов после Венгрии", 10),
    "hadjar_best_finish": ("Лучший финиш Хаджара", 8),
    "world_drivers_champion": ("Чемпион мира среди пилотов", 25),
    "constructors_champion": ("Чемпион Кубка конструкторов", 20),
    "constructors_second": ("2 место Кубка конструкторов", 12),
    "constructors_third": ("3 место Кубка конструкторов", 10),
    "last_race_winner": ("Победитель последней гонки", 10),
    "season_pole_sitter": ("Pole-sitter сезона", 12),
    "driver_change_happened": ("Смена пилота в сезоне", 8),
    "team_most_dnf": ("Команда-лидер по DNF", 12),
}


def _normalize(value):
    if value is None:
        return ""
    return str(value).strip().lower()


def _driver_of_day_actual_values(result):
    values = getattr(result, "driver_of_day_multiple", None)
    if isinstance(values, list):
        normalized = {_normalize(v) for v in values if _normalize(v)}
        if normalized:
            return normalized

    legacy_value = _normalize(getattr(result, "driver_of_day", ""))
    if legacy_value:
        return {legacy_value}
    return set()


def calculate_points(pred, res):
    points = 0
    breakdown = {}
    is_sprint_weekend = bool(getattr(getattr(res, "event", None), "has_sprint", False))

    def add(label, pts):
        nonlocal points
        points += pts
        breakdown[label] = pts

    actual_podium = {
        "p1": _normalize(res.p1),
        "p2": _normalize(res.p2),
        "p3": _normalize(res.p3),
    }
    actual_top3 = {value for value in actual_podium.values() if value}

    for field_name, label, exact_points in (("p1", "P1", 10), ("p2", "P2", 6), ("p3", "P3", 4)):
        predicted_value = _normalize(getattr(pred, field_name))
        if not predicted_value:
            continue

        if predicted_value == actual_podium[field_name]:
            add(label, exact_points)
        elif predicted_value in actual_top3:
            add(f"{label} (Top-3)", 3)
    if _normalize(res.pole) and _normalize(pred.pole) == _normalize(res.pole):
        add("Pole Position", 4)
    if (
        is_sprint_weekend
        and _normalize(res.sprint_qualifying_winner)
        and _normalize(pred.sprint_qualifying_winner) == _normalize(res.sprint_qualifying_winner)
    ):
        add("Sprint Qualifying Winner", 3)
    if (
        is_sprint_weekend
        and _normalize(res.sprint_winner)
        and _normalize(pred.sprint_winner) == _normalize(res.sprint_winner)
    ):
        add("Sprint Winner", 5)
    if _normalize(res.fastest_lap) and _normalize(pred.fastest_lap) == _normalize(res.fastest_lap):
        add("Fastest Lap", 3)
    predicted_driver_of_day = _normalize(pred.driver_of_day)
    if predicted_driver_of_day and predicted_driver_of_day in _driver_of_day_actual_values(res):
        add("Driver of the Day", 3)
    if pred.crazy_prediction_approved:
        add("Crazy Prediction", 5)
    if pred.safety_car_count == res.safety_car_count:
        add("Safety Car Count", 5)
    if pred.dnf_count == res.dnf_count:
        add("DNF Count", 5)

    return points, breakdown


def calculate_season_points(prediction, result):
    points = 0
    breakdown = {}

    for field_name, (label, weight) in SEASON_SCORING_WEIGHTS.items():
        predicted_value = getattr(prediction, field_name)
        actual_value = getattr(result, field_name)

        # Итоги сезона заполняются по мере появления фактических данных.
        # Незавершенная категория не должна ни давать очки, ни считаться ошибкой.
        if actual_value is None or (isinstance(actual_value, str) and not _normalize(actual_value)):
            continue

        if isinstance(predicted_value, str) or isinstance(actual_value, str):
            is_match = _normalize(predicted_value) == _normalize(actual_value)
        else:
            is_match = predicted_value == actual_value

        if is_match:
            points += weight
            breakdown[label] = weight

    return points, breakdown


def _build_event_score_rows(event):
    predictions = list(
        Prediction.objects.filter(event=event).select_related("user").order_by("user__username")
    )
    standard_prediction_points = {}
    breakdowns = {}
    users = {}
    for prediction in predictions:
        points, breakdown = calculate_points(prediction, event.result)
        standard_prediction_points[prediction.user_id] = points
        breakdowns[prediction.user_id] = breakdown
        users[prediction.user_id] = prediction.user

    wildcard_points = {}
    wildcard_answers = list(
        PlayerWildcard.objects.filter(event=event)
        .exclude(selected_option="")
        .select_related("user", "question")
        .order_by("user__username")
    )
    for assignment in wildcard_answers:
        points = assignment.awarded_points
        wildcard_points[assignment.user_id] = points
        users[assignment.user_id] = assignment.user
        breakdowns.setdefault(assignment.user_id, {})["Личная карта этапа"] = points

    duels = list(
        DuelChallenge.objects.filter(
            event=event,
            status__in=(DuelChallenge.Status.ACCEPTED, DuelChallenge.Status.SETTLED),
        ).select_related("challenger", "opponent")
    )
    adjustments = defaultdict(int)
    duel_participant_ids = set()
    outcomes = []
    for duel in duels:
        # Случайная личная карта не влияет на дуэль: соперники сравнивают
        # только одинаковый для всех основной прогноз.
        challenger_points = standard_prediction_points.get(duel.challenger_id, 0)
        opponent_points = standard_prediction_points.get(duel.opponent_id, 0)
        users[duel.challenger_id] = duel.challenger
        users[duel.opponent_id] = duel.opponent
        duel_participant_ids.update((duel.challenger_id, duel.opponent_id))

        winner_id = None
        if challenger_points > opponent_points:
            winner_id = duel.challenger_id
            adjustments[duel.challenger_id] += duel.stake
            adjustments[duel.opponent_id] -= duel.stake
        elif opponent_points > challenger_points:
            winner_id = duel.opponent_id
            adjustments[duel.opponent_id] += duel.stake
            adjustments[duel.challenger_id] -= duel.stake

        outcomes.append(
            {
                "duel_id": duel.id,
                "winner_id": winner_id,
                "challenger_points": challenger_points,
                "opponent_points": opponent_points,
            }
        )

    rows = []
    for user_id, player in sorted(users.items(), key=lambda item: item[1].username.lower()):
        duel_prediction_points = standard_prediction_points.get(user_id, 0)
        personal_points = wildcard_points.get(user_id, 0)
        base_points = duel_prediction_points + personal_points
        duel_adjustment = adjustments[user_id]
        breakdown = dict(breakdowns.get(user_id, {}))
        if user_id in duel_participant_ids:
            breakdown["Дуэль"] = duel_adjustment
        rows.append(
            {
                "user_id": user_id,
                "username": player.username,
                "prediction_points": base_points,
                "duel_prediction_points": duel_prediction_points,
                "wildcard_points": personal_points,
                "duel_adjustment": duel_adjustment,
                "points": base_points + duel_adjustment,
                "breakdown": breakdown,
            }
        )
    return rows, outcomes


def _apply_duel_outcomes(event, outcomes):
    now = timezone.now()
    DuelChallenge.objects.filter(
        event=event,
        status=DuelChallenge.Status.PENDING,
    ).update(status=DuelChallenge.Status.EXPIRED, responded_at=now, updated_at=now)

    for outcome in outcomes:
        DuelChallenge.objects.filter(pk=outcome["duel_id"]).update(
            status=DuelChallenge.Status.SETTLED,
            winner_id=outcome["winner_id"],
            challenger_prediction_points=outcome["challenger_points"],
            opponent_prediction_points=outcome["opponent_points"],
            settled_at=now,
            updated_at=now,
        )


def calculate_event_scores(event):
    if not hasattr(event, "result"):
        return 0
    if unresolved_wildcard_questions(event).exists():
        raise ValueError("Укажи правильные ответы для всех разыгранных личных карт этапа.")

    rows, outcomes = _build_event_score_rows(event)
    for row in rows:
        Score.objects.update_or_create(
            event=event,
            user_id=row["user_id"],
            defaults={
                "points": row["points"],
                "prediction_points": row["prediction_points"],
                "duel_adjustment": row["duel_adjustment"],
                "breakdown": row["breakdown"],
            },
        )
    user_ids = [row["user_id"] for row in rows]
    Score.objects.filter(event=event).exclude(user_id__in=user_ids).delete()
    _apply_duel_outcomes(event, outcomes)
    return len(rows)


def preview_event_scores(event):
    if not hasattr(event, "result"):
        return []

    previous_scores = {score.user_id: score for score in Score.objects.filter(event=event)}
    rows, _ = _build_event_score_rows(event)
    for row in rows:
        previous = previous_scores.get(row["user_id"])
        row["previous_points"] = previous.points if previous else None
        row["delta"] = row["points"] - (previous.points if previous else 0)
    return rows


@transaction.atomic
def publish_event_scores(event, user=None):
    if not hasattr(event, "result"):
        raise ValueError("Сначала внеси фактический результат этапа.")
    if unresolved_wildcard_questions(event).exists():
        raise ValueError("Укажи правильные ответы для всех разыгранных личных карт этапа.")

    rows, outcomes = _build_event_score_rows(event)
    previous_scores = {score.user_id: score for score in Score.objects.filter(event=event)}
    for row in rows:
        previous = previous_scores.get(row["user_id"])
        row["previous_points"] = previous.points if previous else None
        row["delta"] = row["points"] - (previous.points if previous else 0)

    Score.objects.filter(event=event).delete()
    Score.objects.bulk_create(
        [
            Score(
                event=event,
                user_id=row["user_id"],
                points=row["points"],
                prediction_points=row["prediction_points"],
                duel_adjustment=row["duel_adjustment"],
                breakdown=row["breakdown"],
            )
            for row in rows
        ]
    )

    latest_revision = (
        ScoreRevision.objects.filter(event=event).aggregate(value=Max("revision"))["value"] or 0
    )
    revision = ScoreRevision.objects.create(
        event=event,
        revision=latest_revision + 1,
        scores=[
            {
                "user_id": row["user_id"],
                "points": row["points"],
                "prediction_points": row["prediction_points"],
                "duel_prediction_points": row["duel_prediction_points"],
                "wildcard_points": row["wildcard_points"],
                "duel_adjustment": row["duel_adjustment"],
                "breakdown": row["breakdown"],
            }
            for row in rows
        ],
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    _apply_duel_outcomes(event, outcomes)

    event.status = Event.Status.SCORED
    event.save(update_fields=("status",))
    result = event.result
    result.published_at = timezone.now()
    result.published_by = user if getattr(user, "is_authenticated", False) else None
    result.save(update_fields=("published_at", "published_by"))
    return revision, rows


@transaction.atomic
def restore_score_revision(revision, user=None):
    event = revision.event
    Score.objects.filter(event=event).delete()
    Score.objects.bulk_create(
        [
            Score(
                event=event,
                user_id=row["user_id"],
                points=row["points"],
                prediction_points=row.get("prediction_points", row["points"]),
                duel_adjustment=row.get("duel_adjustment", 0),
                breakdown=row.get("breakdown", {}),
            )
            for row in revision.scores
        ]
    )

    latest_revision = (
        ScoreRevision.objects.filter(event=event).aggregate(value=Max("revision"))["value"] or 0
    )
    restored = ScoreRevision.objects.create(
        event=event,
        revision=latest_revision + 1,
        scores=revision.scores,
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )

    restored_base_points = {
        row["user_id"]: row.get(
            "duel_prediction_points",
            row.get("prediction_points", row["points"]),
        )
        for row in revision.scores
    }
    outcomes = []
    for duel in DuelChallenge.objects.filter(
        event=event,
        status__in=(DuelChallenge.Status.ACCEPTED, DuelChallenge.Status.SETTLED),
    ):
        challenger_points = restored_base_points.get(duel.challenger_id, 0)
        opponent_points = restored_base_points.get(duel.opponent_id, 0)
        winner_id = None
        if challenger_points > opponent_points:
            winner_id = duel.challenger_id
        elif opponent_points > challenger_points:
            winner_id = duel.opponent_id
        outcomes.append(
            {
                "duel_id": duel.id,
                "winner_id": winner_id,
                "challenger_points": challenger_points,
                "opponent_points": opponent_points,
            }
        )
    _apply_duel_outcomes(event, outcomes)

    event.status = Event.Status.SCORED
    event.save(update_fields=("status",))
    return restored


def calculate_season_scores(season_year):
    result = SeasonResult.objects.filter(season_year=season_year).first()
    if not result:
        return 0

    predictions = SeasonPrediction.objects.filter(season_year=season_year).select_related("user")
    total_updates = 0

    for prediction in predictions:
        points, breakdown = calculate_season_points(prediction, result)
        SeasonScore.objects.update_or_create(
            season_year=season_year,
            user=prediction.user,
            defaults={
                "points": points,
                "breakdown": breakdown,
            },
        )
        total_updates += 1

    return total_updates
