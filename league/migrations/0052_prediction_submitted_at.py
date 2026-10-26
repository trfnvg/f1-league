from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("league", "0051_player_handles")]
    operations = [migrations.AddField(
        model_name="prediction", name="submitted_at",
        field=models.DateTimeField("Последнее сохранение игроком", null=True, blank=True, editable=False),
    )]
