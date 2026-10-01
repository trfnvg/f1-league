import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("league", "0028_arcade_record_total_attempts"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CrazyPredictionVote",
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
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="crazy_prediction_votes",
                        to="league.event",
                    ),
                ),
                (
                    "target_prediction",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="crazy_prediction_votes_received",
                        to="league.prediction",
                    ),
                ),
                (
                    "voter",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="crazy_prediction_votes_cast",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Голос за Crazy Prediction",
                "verbose_name_plural": "Голоса за Crazy Prediction",
            },
        ),
        migrations.AddConstraint(
            model_name="crazypredictionvote",
            constraint=models.UniqueConstraint(
                fields=("event", "voter"),
                name="crazy_vote_event_user_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="crazypredictionvote",
            index=models.Index(
                fields=["event", "target_prediction"],
                name="crazy_vote_ev_target_idx",
            ),
        ),
    ]
