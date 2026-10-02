import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_arcade_settings(apps, schema_editor):
    ArcadeSettings = apps.get_model("league", "ArcadeSettings")
    ArcadeSettings.objects.get_or_create(
        pk=1,
        defaults={"active_game": "minesweeper", "public_enabled": False},
    )


class Migration(migrations.Migration):

    dependencies = [
        ("league", "0034_event_crazy_vote_closed_at"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ArcadeSettings",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                (
                    "active_game",
                    models.CharField(
                        choices=[
                            ("flappy", "Pit Lane Flight · Flappy Bird"),
                            ("doodle_jump", "Doodle GP · прототип"),
                            ("minesweeper", "Сапёр · Pitwall Sweep"),
                        ],
                        default="minesweeper",
                        help_text="Выбор меняет игру на вкладке «Аркада», но не удаляет результаты других игр.",
                        max_length=24,
                        verbose_name="Активная аркада недели",
                    ),
                ),
                (
                    "public_enabled",
                    models.BooleanField(
                        default=False,
                        help_text="Если выключено, страницу и игру видят только администраторы. Можно включить позже без удаления результатов.",
                        verbose_name="Открыть участникам",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
            ],
            options={
                "verbose_name": "Настройки аркады",
                "verbose_name_plural": "Настройки аркады",
            },
        ),
        migrations.CreateModel(
            name="MinesweeperAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("week_start", models.DateField(db_index=True, verbose_name="Начало игровой недели")),
                ("started_at", models.DateTimeField(auto_now_add=True, verbose_name="Начало попытки")),
                ("finished_at", models.DateTimeField(blank=True, null=True, verbose_name="Завершено")),
                ("completed", models.BooleanField(default=False, verbose_name="Поле пройдено")),
                ("elapsed_ms", models.PositiveIntegerField(blank=True, null=True, verbose_name="Время прохождения, мс")),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="minesweeper_attempts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Попытка Сапёра",
                "verbose_name_plural": "Попытки Сапёра",
                "ordering": ("week_start", "elapsed_ms", "started_at"),
                "indexes": [
                    models.Index(fields=["week_start", "user"], name="mine_week_user_idx"),
                    models.Index(fields=["week_start", "completed", "elapsed_ms"], name="mine_week_result_idx"),
                ],
            },
        ),
        migrations.RunPython(seed_arcade_settings, migrations.RunPython.noop),
    ]
