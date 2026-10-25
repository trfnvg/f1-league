import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("league", "0041_isolated_competition_scores"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(name="LeagueInvite", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("token_digest", models.CharField(editable=False, max_length=64, unique=True)),
            ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
            ("expires_at", models.DateTimeField()),
            ("revoked_at", models.DateTimeField(blank=True, null=True)),
            ("uses", models.PositiveIntegerField(default=0)),
            ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="league_invites", to=settings.AUTH_USER_MODEL)),
            ("league_season", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="invites", to="league.leagueseason")),
        ]),
        migrations.CreateModel(name="LeagueActivity", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("action", models.CharField(choices=[("created", "Создание лиги"), ("joined", "Вступление"), ("invite_created", "Создание приглашения"), ("invite_revoked", "Отзыв приглашения"), ("role_changed", "Изменение роли")], max_length=24)),
            ("details", models.JSONField(blank=True, default=dict)),
            ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
            ("actor", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="league_actions", to=settings.AUTH_USER_MODEL)),
            ("league", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="activity", to="league.league")),
        ]),
    ]
