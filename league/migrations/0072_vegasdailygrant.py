import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("league", "0071_vegaspurchase"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [migrations.CreateModel(
        name="VegasDailyGrant",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("day", models.DateField()),
            ("amount", models.PositiveIntegerField(default=300000)),
            ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
            ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="vegas_daily_grants", to=settings.AUTH_USER_MODEL)),
            ("wallet", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="daily_grants", to="league.vegaswallet")),
        ],
        options={
            "verbose_name": "Ежедневное пополнение Vegas Pit",
            "verbose_name_plural": "Ежедневные пополнения Vegas Pit",
            "constraints": [models.UniqueConstraint(fields=("user", "day"), name="vegas_daily_grant_once")],
        },
    )]
