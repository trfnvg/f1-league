import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("league", "0039_crazy_jury_cancellation_and_revote"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="League",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=80, verbose_name="Название лиги")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("archived_at", models.DateTimeField(blank=True, null=True)),
                ("legacy_key", models.CharField(blank=True, editable=False, max_length=40, null=True, unique=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="owned_leagues", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "Лига друзей", "verbose_name_plural": "Лиги друзей", "ordering": ("created_at", "id")},
        ),
        migrations.CreateModel(
            name="LeagueMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("player", "Игрок"), ("moderator", "Модератор")], default="player", max_length=12)),
                ("is_active", models.BooleanField(default=True)),
                ("joined_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("league", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="memberships", to="league.league")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="friend_league_memberships", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="LeagueSeason",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ruleset", models.CharField(choices=[("classic", "Классика"), ("paddock", "Паддок")], default="classic", max_length=12)),
                ("rules_version", models.PositiveSmallIntegerField(default=1, editable=False)),
                ("is_legacy", models.BooleanField(default=False, editable=False)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("league", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="seasons", to="league.league")),
                ("season", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="friend_league_seasons", to="league.season")),
                ("start_event", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="starting_league_seasons", to="league.event")),
            ],
        ),
        migrations.CreateModel(
            name="LeagueSeasonEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("entered_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("first_event", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="first_league_entries", to="league.event")),
                ("league_season", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="entries", to="league.leagueseason")),
                ("membership", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="season_entries", to="league.leaguemembership")),
            ],
        ),
        migrations.AddConstraint(model_name="leaguemembership", constraint=models.UniqueConstraint(fields=("league", "user"), name="league_member_unique")),
        migrations.AddConstraint(model_name="leaguemembership", constraint=models.CheckConstraint(condition=models.Q(role__in=("player", "moderator")), name="league_member_role_valid")),
        migrations.AddConstraint(model_name="leagueseason", constraint=models.UniqueConstraint(fields=("league", "season"), name="league_season_unique")),
        migrations.AddConstraint(model_name="leagueseason", constraint=models.CheckConstraint(condition=models.Q(ruleset__in=("classic", "paddock")), name="league_ruleset_valid")),
        migrations.AddConstraint(model_name="leagueseason", constraint=models.CheckConstraint(condition=models.Q(rules_version__gte=1), name="league_rules_version_positive")),
        migrations.AddConstraint(model_name="leagueseasonentry", constraint=models.UniqueConstraint(fields=("league_season", "membership"), name="league_entry_unique")),
    ]
