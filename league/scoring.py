from .models import Prediction, Score


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
