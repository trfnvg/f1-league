import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def copy_existing_score_points(apps, schema_editor):
    Score = apps.get_model("league", "Score")
    for score in Score.objects.all().only("id", "points").iterator():
        Score.objects.filter(pk=score.pk).update(prediction_points=score.points)


class Migration(migrations.Migration):
    dependencies = [
        ("league", "0019_homeresultimage_season_year"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="duel_cover_image",
            field=models.ImageField(
                blank=True,
                help_text="Необязательная иллюстрация F1 × Wild West для блока дуэлей.",
                max_length=255,
                null=True,
                upload_to="event_duels/",
                verbose_name="Обложка дуэлей",
            ),
        ),
        migrations.AddField(
            model_name="score",
            name="duel_adjustment",
            field=models.IntegerField(default=0, verbose_name="Поправка за дуэль"),
        ),
        migrations.AddField(
            model_name="score",
            name="prediction_points",
            field=models.IntegerField(default=0, verbose_name="Очки прогноза"),
        ),
        migrations.RunPython(copy_existing_score_points, migrations.RunPython.noop),
        migrations.CreateModel(
            name="DuelChallenge",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "stake",
                    models.PositiveSmallIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(10),
                        ],
                        verbose_name="Ставка",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Ожидает ответа"),
                            ("accepted", "Принята"),
                            ("declined", "Отклонена"),
                            ("cancelled", "Отменена"),
                            ("expired", "Истекла"),
                            ("settled", "Рассчитана"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=10,
                        verbose_name="Статус",
                    ),
                ),
                ("challenger_prediction_points", models.IntegerField(blank=True, null=True, verbose_name="Очки инициатора")),
                ("opponent_prediction_points", models.IntegerField(blank=True, null=True, verbose_name="Очки соперника")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("responded_at", models.DateTimeField(blank=True, null=True, verbose_name="Ответ получен")),
                ("settled_at", models.DateTimeField(blank=True, null=True, verbose_name="Рассчитана")),
                (
                    "challenger",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="duel_challenges_sent",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Инициатор",
                    ),
                ),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="duel_challenges",
                        to="league.event",
                    ),
                ),
                (
                    "opponent",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="duel_challenges_received",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Соперник",
                    ),
                ),
                (
                    "winner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="duel_challenges_won",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Победитель",
                    ),
                ),
            ],
            options={
                "verbose_name": "Дуэль",
                "verbose_name_plural": "Дуэли",
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddConstraint(
            model_name="duelchallenge",
            constraint=models.CheckConstraint(
                condition=models.Q(("stake__gte", 1), ("stake__lte", 10)),
                name="duel_stake_between_1_and_10",
            ),
        ),
        migrations.AddConstraint(
            model_name="duelchallenge",
            constraint=models.CheckConstraint(
                condition=models.Q(("challenger", models.F("opponent")), _negated=True),
                name="duel_players_must_differ",
            ),
        ),
        migrations.AddIndex(
            model_name="duelchallenge",
            index=models.Index(fields=["event", "status"], name="duel_event_status_idx"),
        ),
    ]
