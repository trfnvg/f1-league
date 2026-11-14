from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("league", "0072_vegasdailygrant")]
    operations = [migrations.AlterField(
        model_name="vegasdailygrant", name="amount",
        field=models.PositiveIntegerField(default=200000),
    )]
