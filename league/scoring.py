def calculate_points(pred, res):
    points = 0
    breakdown = {}

    def add(label, pts):
        nonlocal points
        points += pts
        breakdown[label] = pts

    if pred.p1 == res.p1:
        add("P1", 10)
    if pred.p2 == res.p2:
        add("P2", 6)
    if pred.p3 == res.p3:
        add("P3", 4)
    if pred.pole == res.pole:
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