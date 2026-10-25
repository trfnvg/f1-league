import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("league", "0040_private_league_foundation"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CompetitionScoreAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("global_projected", "Общий пересчёт"), ("league_projected", "Локальный пересчёт"), ("crazy_decided", "Решение по крейзи"), ("podium_applied", "Локальный апдейт подиума")], max_length=20)),
                ("before", models.JSONField(blank=True, null=True)),
                ("after", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="competition_score_actions", to=settings.AUTH_USER_MODEL)),
                ("entry", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="score_audits", to="league.leagueseasonentry")),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="competition_score_audits", to="league.event")),
                ("league_season", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="score_audits", to="league.leagueseason")),
            ],
            options={"constraints": [models.CheckConstraint(
                condition=(models.Q(action="global_projected", entry__isnull=True, league_season__isnull=True)
                           | models.Q(action__in=("league_projected", "crazy_decided", "podium_applied"), entry__isnull=False, league_season__isnull=False)),
                name="competition_audit_scope_valid",
            )]},
        ),
        migrations.CreateModel(
            name="GlobalEventScore",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("points", models.PositiveIntegerField(default=0)),
                ("breakdown", models.JSONField(blank=True, default=dict)),
                ("rules_version", models.PositiveSmallIntegerField(default=1)),
                ("input_data", models.JSONField(blank=True, default=dict)),
                ("input_digest", models.CharField(max_length=64)),
                ("calculated_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="global_scores", to="league.event")),
                ("prediction", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="global_event_score", to="league.prediction")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="global_event_scores", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "indexes": [models.Index(fields=["event", "-points", "user"], name="global_score_event_rank_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=("event", "user"), name="global_score_event_user_uniq"),
                    models.CheckConstraint(condition=models.Q(rules_version__gte=1), name="global_score_version_positive"),
                ],
            },
        ),
        migrations.CreateModel(
            name="LeagueCrazyDecision",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("approved", models.BooleanField(default=False)),
                ("text_digest", models.CharField(max_length=64)),
                ("reviewed_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("entry", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(class)s_records", to="league.leagueseasonentry")),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(class)s_records", to="league.event")),
                ("prediction", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="local_crazy_decisions", to="league.prediction")),
                ("reviewed_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="local_crazy_reviews", to=settings.AUTH_USER_MODEL)),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("entry", "event"), name="local_crazy_entry_event_uniq")]},
        ),
        migrations.CreateModel(
            name="LeagueEventScore",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("base_points", models.PositiveIntegerField(default=0)),
                ("podium_adjustment", models.IntegerField(default=0)),
                ("crazy_points", models.PositiveSmallIntegerField(default=0)),
                ("other_adjustment", models.IntegerField(default=0)),
                ("points", models.IntegerField(default=0)),
                ("breakdown", models.JSONField(blank=True, default=dict)),
                ("rules_version", models.PositiveSmallIntegerField(default=1)),
                ("input_data", models.JSONField(blank=True, default=dict)),
                ("input_digest", models.CharField(max_length=64)),
                ("calculated_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("entry", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(class)s_records", to="league.leagueseasonentry")),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(class)s_records", to="league.event")),
                ("prediction", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="local_event_scores", to="league.prediction")),
            ],
            options={
                "indexes": [models.Index(fields=["event", "-points", "entry"], name="local_score_event_rank_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=("entry", "event"), name="local_score_entry_event_uniq"),
                    models.CheckConstraint(condition=models.Q(rules_version__gte=1), name="local_score_version_positive"),
                    models.CheckConstraint(condition=models.Q(crazy_points__in=(0, 5)), name="local_score_crazy_points_valid"),
                    models.CheckConstraint(condition=models.Q(points=models.F("base_points")+models.F("podium_adjustment")+models.F("crazy_points")+models.F("other_adjustment")), name="local_score_total_consistent"),
                ],
            },
        ),
        migrations.CreateModel(
            name="LeaguePodiumBonus",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_key", models.CharField(max_length=160)),
                ("granted_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("slot", models.CharField(blank=True, choices=[("p1", "P1"), ("p2", "P2"), ("p3", "P3")], max_length=2)),
                ("driver", models.CharField(blank=True, choices=[
                    ("norris", "Норрис (McLaren)"), ("piastri", "Пиастри (McLaren)"), ("russell", "Рассел (Mercedes)"),
                    ("antonelli", "Антонелли (Mercedes)"), ("verstappen", "Ферстаппен (Red Bull)"), ("hadjar", "Хаджар (Red Bull)"),
                    ("leclerc", "Леклер (Ferrari)"), ("hamilton", "Хэмильтон (Ferrari)"), ("albon", "Албон (Williams)"),
                    ("sainz", "Сайнс (Williams)"), ("lindblad", "Линдблад (Racing Bulls)"), ("lawson", "Лоусон (Racing Bulls)"),
                    ("stroll", "Стролл (Aston Martin)"), ("alonso", "Алонсо (Aston Martin)"), ("ocon", "Окон (Haas)"),
                    ("bearman", "Берман (Haas)"), ("hulkenberg", "Хюлкенберг (Audi)"), ("bortoleto", "Бортолето (Audi)"),
                    ("gasly", "Гасли (Alpine)"), ("colapinto", "Колапинто (Alpine)"), ("perez", "Перес (Cadillac)"), ("bottas", "Боттас (Cadillac)"),
                ], max_length=50)),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("entry", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(class)s_records", to="league.leagueseasonentry")),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(class)s_records", to="league.event")),
            ],
            options={"constraints": [
                models.UniqueConstraint(fields=("entry", "event"), name="local_podium_entry_event_uniq"),
                models.CheckConstraint(condition=(models.Q(used_at__isnull=True, slot="", driver="")
                    | (models.Q(used_at__isnull=False, slot__in=("p1", "p2", "p3")) & ~models.Q(driver=""))), name="local_podium_used_consistent"),
            ]},
        ),
        migrations.CreateModel(
            name="LeagueScoreAdjustment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("duel", "Дуэль"), ("arcade", "Аркада"), ("wildcard", "Личная карта")], max_length=12)),
                ("source_key", models.CharField(max_length=160)),
                ("points", models.IntegerField()),
                ("reason", models.CharField(max_length=200)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("entry", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(class)s_records", to="league.leagueseasonentry")),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(class)s_records", to="league.event")),
            ],
            options={"constraints": [
                models.UniqueConstraint(fields=("entry", "event", "kind", "source_key"), name="local_adjustment_source_uniq"),
                models.CheckConstraint(condition=models.Q(kind__in=("duel", "arcade", "wildcard")), name="local_adjustment_kind_valid"),
            ]},
        ),
    ]
