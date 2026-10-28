"""Frozen official calendar snapshot; never performs network I/O or edits Events."""
from datetime import date, datetime
import json
from pathlib import Path

from django.db import migrations


def seed_calendar(apps, schema_editor):
    Round = apps.get_model("league", "RaceCalendarRound")
    path = Path(__file__).resolve().parents[1] / "data" / "race_calendar_20261028.json"
    rows = json.loads(path.read_text(encoding="utf-8"))["rounds"]
    for original in rows:
        values = dict(original)
        for field in ("starts_on", "ends_on", "checked_on"):
            values[field] = date.fromisoformat(values[field])
        for field in ("practice1_at", "race_at"):
            values[field] = datetime.fromisoformat(values[field]) if values[field] else None
        year, circuit = values.pop("season_year"), values.pop("circuit")
        Round.objects.using(schema_editor.connection.alias).get_or_create(
            season_year=year, circuit=circuit, defaults=values)


class Migration(migrations.Migration):
    dependencies = [("league", "0058_race_calendar")]
    operations = [migrations.RunPython(seed_calendar, migrations.RunPython.noop)]
