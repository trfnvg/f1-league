import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("league", "0035_arcade_settings_and_minesweeper"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DoodleAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("score", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="doodle_attempts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-started_at",),
                "verbose_name": "Попытка Doodle GP",
                "verbose_name_plural": "Попытки Doodle GP",
                "indexes": [models.Index(fields=["user", "started_at"], name="doodle_attempt_user_idx")],
            },
        ),
        migrations.CreateModel(
            name="DoodleRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("best_score", models.PositiveIntegerField(default=0)),
                ("total_attempts", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="doodle_record",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-best_score", "updated_at", "user__username"),
                "verbose_name": "Рекорд Doodle GP",
                "verbose_name_plural": "Рекорды Doodle GP",
            },
        ),
    ]
