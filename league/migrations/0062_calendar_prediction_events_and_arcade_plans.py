from django.db import migrations, models


def backfill_prediction_events(apps, schema_editor):
    from league.calendar_event_sync import sync_calendar_events_v1
    Event = apps.get_model("league", "Event")
    alias = schema_editor.connection.alias
    # Only seasons already used for predictions are published automatically.
    # A clean installation may contain the public calendar but no configured league.
    years = list(Event.objects.using(alias).order_by().values_list("season_year", flat=True).distinct())
    for year in years:
        report = sync_calendar_events_v1(year, model_registry=apps, using=alias)
        if report["created"] or report["linked"]:
            print(f'Calendar {year}: created {report["created"]}, linked {report["linked"]}.')
        for conflict in report["conflicts"]:
            print(f'Calendar {year}: manual review required: {conflict}')


class Migration(migrations.Migration):
    dependencies = [("league", "0061_seed_calendar_weekend_sessions")]
    operations = [
        migrations.AlterField(model_name="arcadecompetition", name="opened_at",
            field=models.DateTimeField(blank=True, null=True,
                help_text="Пусто — игра назначена этапу, но зачёт ещё не открыт.")),
        migrations.RunPython(backfill_prediction_events, migrations.RunPython.noop),
    ]
