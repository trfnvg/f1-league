from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("league", "0020_duel_challenge"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="event",
            name="duel_cover_image",
        ),
        migrations.CreateModel(
            name="DuelSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(default="default", editable=False, max_length=32, unique=True)),
                (
                    "cover_image",
                    models.ImageField(
                        blank=True,
                        help_text="Загружается один раз и используется на всех этапах.",
                        max_length=255,
                        null=True,
                        upload_to="duel_theme/",
                        verbose_name="Общая обложка дуэлей",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Оформление дуэлей",
                "verbose_name_plural": "Оформление дуэлей",
            },
        ),
    ]
