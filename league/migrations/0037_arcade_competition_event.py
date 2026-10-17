import django.db.models.deletion
from django.db import migrations, models


def close_unbound_public_arcade(apps, schema_editor):
    ArcadeSettings = apps.get_model("league", "ArcadeSettings")
    ArcadeSettings.objects.filter(pk=1).update(public_enabled=False)


class Migration(migrations.Migration):

    dependencies = [
        ("league", "0036_doodle_records"),
    ]

    operations = [
        migrations.AddField(
            model_name="arcadesettings",
            name="competition_event",
            field=models.ForeignKey(
                blank=True,
                help_text="Игра и её победитель привязаны только к этому выбранному этапу.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="league.event",
                verbose_name="Этап зачёта",
            ),
        ),
        migrations.AddField(
            model_name="arcadesettings",
            name="competition_opened_at",
            field=models.DateTimeField(
                blank=True,
                help_text="С этой даты и до дедлайна выбранного этапа попытки идут в зачёт.",
                null=True,
                verbose_name="Открыто участникам с",
            ),
        ),
        migrations.RunPython(close_unbound_public_arcade, migrations.RunPython.noop),
    ]
