"""Read-only presentation of a player's saved forecast, using the event roster."""
from .models import DRIVER_CHOICES


def forecast_summary(prediction, event, profiles):
    summary = {"podium": [], "weekend": [], "counts": [], "crazy": ""}
    if prediction is None:
        return summary
    roster = {profile["key"]: profile for profile in profiles}
    choices = dict(DRIVER_CHOICES)
    categories = (
        ("p1", "P1", "Победитель", "podium"),
        ("p2", "P2", "Второе место", "podium"),
        ("p3", "P3", "Третье место", "podium"),
        ("pole", "POLE", "Поул", "weekend"),
        ("fastest_lap", "FL", "Быстрый круг", "weekend"),
        ("driver_of_day", "DOTD", "Гонщик дня", "weekend"),
        ("sprint_qualifying_winner", "SQ", "Поул спринта", "weekend"),
        ("sprint_winner", "SPR", "Победитель спринта", "weekend"),
    )
    for field, marker, title, group in categories:
        if field.startswith("sprint_") and not event.has_sprint:
            continue
        key = getattr(prediction, field, "")
        driver = roster.get(key)
        if key and driver is None:
            surname, _, team = choices.get(key, key).partition(" (")
            driver = {"key": key, "surname": surname, "team": team.rstrip(")"),
                      "photo": "", "number": None, "team_color": "#b5c0ce"}
        summary[group].append({"field": field, "marker": marker, "title": title, "driver": driver})
    for field, marker, title in (("safety_car_count", "SC", "Выезды Safety Car"),
                                  ("dnf_count", "DNF", "Количество сходов")):
        value = getattr(prediction, field, None)
        summary["counts"].append({"field": field, "marker": marker, "title": title,
                                  "value": "—" if value is None else value})
    summary["crazy"] = prediction.crazy_prediction or ""
    return summary
