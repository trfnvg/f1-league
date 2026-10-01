import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


def backfill_arcade_trophies(apps, schema_editor):
    ArcadeLeadChange = apps.get_model("league", "ArcadeLeadChange")
    ArcadeTrophyAward = apps.get_model("league", "ArcadeTrophyAward")
    database = schema_editor.connection.alias

    for lead_change in ArcadeLeadChange.objects.using(database).all().iterator():
        ArcadeTrophyAward.objects.using(database).create(
            player_id=lead_change.player_id,
            game_name="Pit Lane Flight",
            trophy_name="Банана Леклер",
            attempts=lead_change.attempts,
            awarded_at=lead_change.created_at,
            source_lead_change_id=lead_change.pk,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("league", "0030_arcade_lead_change"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ArcadeTrophyAward",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "game_name",
                    models.CharField(default="Pit Lane Flight", max_length=120, verbose_name="Игра"),
                ),
                (
                    "trophy_name",
                    models.CharField(default="Банана Леклер", max_length=120, verbose_name="Название трофея"),
                ),
                (
                    "image",
                    models.ImageField(
                        blank=True,
                        help_text="Загрузи отдельную фигурку для этой игры. Для старых наград без картинки используется Банана Леклер.",
                        upload_to="arcade/trophies/",
                        verbose_name="Изображение трофея",
                    ),
                ),
                (
                    "attempts",
                    models.PositiveIntegerField(default=0, verbose_name="Попытки к моменту победы"),
                ),
                (
                    "awarded_at",
                    models.DateTimeField(default=timezone.now, verbose_name="Дата получения"),
                ),
                (
                    "player",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="arcade_trophies",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Игрок",
                    ),
                ),
                (
                    "source_lead_change",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="trophy_award",
                        to="league.arcadeleadchange",
                        verbose_name="Смена лидера",
                    ),
                ),
            ],
            options={
                "verbose_name": "Трофей аркады",
                "verbose_name_plural": "Трофеи аркады",
                "ordering": ("awarded_at", "pk"),
            },
        ),
        migrations.RunPython(backfill_arcade_trophies, migrations.RunPython.noop),
    ]
