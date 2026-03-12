from .models import Prediction, Score, SeasonPrediction, SeasonResult, SeasonScore

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
    if _normalize(pred.pole) == _normalize(res.pole):
        add("Pole Position", 4)
    if is_sprint_weekend and _normalize(pred.sprint_qualifying_winner) == _normalize(res.sprint_qualifying_winner):
        add("Sprint Qualifying Winner", 3)
    if is_sprint_weekend and _normalize(pred.sprint_winner) == _normalize(res.sprint_winner):
        add("Sprint Winner", 5)
    if _normalize(pred.fastest_lap) == _normalize(res.fastest_lap):
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

        if isinstance(predicted_value, str) or isinstance(actual_value, str):
            is_match = _normalize(predicted_value) == _normalize(actual_value)
        else:
            is_match = predicted_value == actual_value

        if is_match:
            points += weight
            breakdown[label] = weight

    return points, breakdown


def calculate_event_scores(event):
    if not hasattr(event, "result"):
        return 0

    res = event.result
    preds = Prediction.objects.filter(event=event)

    total_updates = 0

    for pred in preds:
        pts, breakdown = calculate_points(pred, res)

        Score.objects.update_or_create(
            event=event,
            user=pred.user,
            defaults={
                "points": pts,
                "breakdown": breakdown,
            },
        )
        total_updates += 1

    return total_updates


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
