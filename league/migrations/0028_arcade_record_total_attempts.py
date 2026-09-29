from django.db import migrations, models
from django.db.models import Count


def backfill_attempt_counts(apps, schema_editor):
    ArcadeAttempt = apps.get_model("league", "ArcadeAttempt")
    ArcadeRecord = apps.get_model("league", "ArcadeRecord")
    database = schema_editor.connection.alias

    attempts_by_user = (
        ArcadeAttempt.objects.using(database)
        .values("user_id")
        .annotate(total=Count("id"))
        .iterator()
    )
    for item in attempts_by_user:
        records = ArcadeRecord.objects.using(database)
        updated = records.filter(user_id=item["user_id"]).update(total_attempts=item["total"])
        if not updated:
            records.create(user_id=item["user_id"], total_attempts=item["total"])


class Migration(migrations.Migration):
    dependencies = [
        ("league", "0027_event_qualifying_datetime_arcadewheelspin"),
    ]

    operations = [
        migrations.AddField(
            model_name="arcaderecord",
            name="total_attempts",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(backfill_attempt_counts, migrations.RunPython.noop),
    ]
