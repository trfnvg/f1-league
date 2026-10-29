"""Frozen, reviewed F1 session starts; no network I/O or prediction changes."""
from datetime import date, datetime
import json
from pathlib import Path

from django.db import migrations


FIELDS = ("practice2_at", "practice3_at", "qualifying_at", "sprint_at", "sprint_qualifying_at")


def seed_sessions(apps, schema_editor):
    Round = apps.get_model("league", "RaceCalendarRound")
    snapshot = json.loads((Path(__file__).resolve().parents[1] / "data" /
                           "race_calendar_sessions_20261029.json").read_text(encoding="utf-8"))
    for row in snapshot["rounds"]:
        race = Round.objects.using(schema_editor.connection.alias).filter(
            season_year=row["season_year"], circuit=row["circuit"]).first()
        if race is None:
            continue
        if race.has_sprint != ("sprint_at" in row):
            continue  # Respect a manually configured weekend format.
        updates = {}
        for field in FIELDS:
            if row.get(field) and getattr(race, field) is None:
                updates[field] = datetime.fromisoformat(row[field])
        # Do not mark a manually changed schedule as externally verified.
        if (race.practice1_at == datetime.fromisoformat(row["practice1_at"])
                and race.race_at == datetime.fromisoformat(row["race_at"])
                and race.checked_on == date(2026, 10, 28)):
            updates["checked_on"] = date.fromisoformat(snapshot["checked_on"])
        if updates:
            Round.objects.using(schema_editor.connection.alias).filter(pk=race.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [("league", "0060_calendar_weekend_sessions")]
    operations = [migrations.RunPython(seed_sessions, migrations.RunPython.noop)]
