import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("league", "0025_shared_wildcard_decks_and_new_cards"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ArcadeAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("score", models.PositiveIntegerField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="arcade_attempts", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-started_at",)},
        ),
        migrations.CreateModel(
            name="ArcadeRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("best_score", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="arcade_record", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-best_score", "updated_at", "user__username")},
        ),
        migrations.AddIndex(
            model_name="arcadeattempt",
            index=models.Index(fields=["user", "started_at"], name="arcade_attempt_user_idx"),
        ),
    ]
