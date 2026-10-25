"""Pure, versioned objective event rules. No league, votes or reward queries."""

RULES_VERSION = 1
PREDICTION_FIELDS = (
    "p1", "p2", "p3", "pole", "sprint_qualifying_winner", "sprint_winner",
    "fastest_lap", "driver_of_day", "safety_car_count", "dnf_count",
)
RESULT_FIELDS = PREDICTION_FIELDS + ("driver_of_day_multiple",)


def _normalize(value):
    return "" if value is None else str(value).strip().lower()


def calculate_base_points(prediction, result, *, rules_version=RULES_VERSION):
    if rules_version != RULES_VERSION:
        raise ValueError("Неизвестная версия правил прогноза.")
    breakdown = {}
    actual = {slot: _normalize(getattr(result, slot)) for slot in ("p1", "p2", "p3")}
    top3 = {driver for driver in actual.values() if driver}
    for slot, label, weight in (("p1", "P1", 10), ("p2", "P2", 6), ("p3", "P3", 4)):
        driver = _normalize(getattr(prediction, slot))
        if driver and driver == actual[slot]:
            breakdown[label] = weight
        elif driver and driver in top3:
            breakdown[f"{label} (Top-3)"] = 3
    sprint = bool(getattr(getattr(result, "event", None), "has_sprint", False))
    for field, label, weight in (
        ("pole", "Pole Position", 4),
        ("sprint_qualifying_winner", "Sprint Qualifying Winner", 3),
        ("sprint_winner", "Sprint Winner", 5),
        ("fastest_lap", "Fastest Lap", 3),
    ):
        if field.startswith("sprint_") and not sprint:
            continue
        value = _normalize(getattr(result, field))
        if value and _normalize(getattr(prediction, field)) == value:
            breakdown[label] = weight
    multiple = getattr(result, "driver_of_day_multiple", None)
    drivers = {_normalize(value) for value in multiple if _normalize(value)} if isinstance(multiple, list) else set()
    legacy_driver = _normalize(getattr(result, "driver_of_day", ""))
    if not drivers and legacy_driver:
        drivers = {legacy_driver}
    if _normalize(prediction.driver_of_day) and _normalize(prediction.driver_of_day) in drivers:
        breakdown["Driver of the Day"] = 3
    for field, label in (("safety_car_count", "Safety Car Count"), ("dnf_count", "DNF Count")):
        if getattr(prediction, field) == getattr(result, field):
            breakdown[label] = 5
    return sum(breakdown.values()), breakdown
