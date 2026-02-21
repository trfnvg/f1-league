def _normalize(s):
    """Нормализация для сравнения (пробелы, регистр)."""
    if s is None:
        return ""
    return str(s).strip().lower()


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
        add("Pole", 3)

    return points, breakdown

from .models import Prediction, Score

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
                "breakdown": breakdown
            }
        )
        total_updates += 1

    return total_updates