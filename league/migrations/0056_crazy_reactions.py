import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("league", "0055_remove_league_manager_role"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(
        name="CrazyReaction",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("kind", models.CharField(choices=[("heart", "Сердечко"), ("fire", "Огонёк"), ("poop", "Какашка")], max_length=8)),
            ("league", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="crazy_reactions", to="league.league")),
            ("prediction", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reactions", to="league.prediction")),
            ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="crazy_reactions", to=settings.AUTH_USER_MODEL)),
        ],
        options={"constraints": [
            models.UniqueConstraint(fields=("prediction", "user", "league"), name="crazy_reaction_league_unique"),
            models.UniqueConstraint(fields=("prediction", "user"), condition=models.Q(league__isnull=True), name="crazy_reaction_global_unique"),
            models.CheckConstraint(condition=models.Q(kind__in=("heart", "fire", "poop")), name="crazy_reaction_kind_valid"),
        ]},
    )]
