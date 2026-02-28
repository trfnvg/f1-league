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


def calculate_points(pred, res):
    points = 0
    breakdown = {}

    def add(label, pts):
        nonlocal points
        points += pts
        breakdown[label] = pts

    if _normalize(pred.p1) == _normalize(res.p1):
        add("P1", 10)
    if _normalize(pred.p2) == _normalize(res.p2):
        add("P2", 6)
    if _normalize(pred.p3) == _normalize(res.p3):
        add("P3", 4)
    if _normalize(pred.pole) == _normalize(res.pole):
        add("Pole Position", 4)
    if _normalize(pred.fastest_lap) == _normalize(res.fastest_lap):
        add("Fastest Lap", 3)
    if _normalize(pred.driver_of_day) == _normalize(res.driver_of_day):
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
