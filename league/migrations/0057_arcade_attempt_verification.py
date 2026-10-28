from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("league", "0056_crazy_reactions")]

    operations = [
        migrations.AddField(model_name=model, name="verification",
            field=models.JSONField(default=dict, db_default={}, blank=True, editable=False))
        for model in ("arcadeattempt", "doodleattempt")
    ]
