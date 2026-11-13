import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("league", "0067_vegas_lab_wallet"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(
        name="VegasTopupClaim",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("task", models.CharField(choices=[("ban", "Получить бан в паблике «Симпли Формула 1»"), ("meme", "Повторить знаменитый формульный мем или сцену")], max_length=8)),
            ("status", models.CharField(choices=[("active", "Задание активно"), ("review", "На проверке"), ("approved", "Засчитано · +5 000"), ("rejected", "Не засчитано"), ("cancelled", "Отменено игроком"), ("expired", "Дедлайн прошёл")], default="active", max_length=10)),
            ("expires_at", models.DateTimeField()),
            ("activated_at", models.DateTimeField(default=django.utils.timezone.now)),
            ("submitted_at", models.DateTimeField(blank=True, null=True)),
            ("reviewed_at", models.DateTimeField(blank=True, null=True)),
            ("credited_at", models.DateTimeField(blank=True, null=True)),
            ("note", models.CharField(blank=True, max_length=300)),
            ("event", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="vegas_topups", to="league.event")),
            ("league_season", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="vegas_topups", to="league.leagueseason")),
            ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_vegas_topups", to=settings.AUTH_USER_MODEL)),
            ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="vegas_topups", to=settings.AUTH_USER_MODEL)),
        ],
        options={"ordering": ("-activated_at", "-pk"), "constraints": [
            models.UniqueConstraint(fields=("user", "event", "task"), name="vegas_topup_task_once"),
            models.UniqueConstraint(condition=models.Q(status__in=("active", "review")), fields=("user",), name="vegas_topup_one_open"),
            models.CheckConstraint(condition=models.Q(task__in=("ban", "meme")), name="vegas_topup_task_valid"),
            models.CheckConstraint(condition=models.Q(status__in=("active", "review", "approved", "rejected", "cancelled", "expired")), name="vegas_topup_status_valid"),
            models.CheckConstraint(condition=(models.Q(status="approved", credited_at__isnull=False) | (~models.Q(status="approved") & models.Q(credited_at__isnull=True))), name="vegas_topup_credit_valid"),
        ]},
    )]
