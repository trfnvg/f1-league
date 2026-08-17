import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_wildcard_library(apps, schema_editor):
    CardTemplate = apps.get_model("league", "WildcardCardTemplate")
    EventQuestion = apps.get_model("league", "EventWildcardQuestion")

    for question in EventQuestion.objects.select_related("event").order_by("id"):
        template = CardTemplate.objects.filter(
            question=question.question,
            option_a=question.option_a,
            option_b=question.option_b,
        ).first()
        if template and EventQuestion.objects.filter(
            event_id=question.event_id,
            source_card_id=template.id,
        ).exists():
            template = None
        if template is None:
            template = CardTemplate.objects.create(
                title=question.question[:120],
                question=question.question,
                option_a=question.option_a,
                option_b=question.option_b,
            )
        question.source_card_id = template.id
        question.points = 3
        question.save(update_fields=("source_card", "points"))


def clear_wildcard_library_links(apps, schema_editor):
    EventQuestion = apps.get_model("league", "EventWildcardQuestion")
    CardTemplate = apps.get_model("league", "WildcardCardTemplate")
    EventQuestion.objects.update(source_card=None)
    CardTemplate.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("league", "0022_wildcardsettings_eventwildcardquestion_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WildcardCardTemplate",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "title",
                    models.CharField(
                        help_text="Короткое название только для удобного поиска в админке.",
                        max_length=120,
                        verbose_name="Название в библиотеке",
                    ),
                ),
                ("question", models.CharField(max_length=240, verbose_name="Вопрос")),
                ("option_a", models.CharField(max_length=120, verbose_name="Вариант A")),
                ("option_b", models.CharField(max_length=120, verbose_name="Вариант B")),
                ("is_active", models.BooleanField(default=True, verbose_name="Можно добавлять в этапы")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Шаблон личной карты",
                "verbose_name_plural": "Библиотека личных карт",
                "ordering": ("title", "id"),
            },
        ),
        migrations.AddField(
            model_name="eventwildcardquestion",
            name="source_card",
            field=models.ForeignKey(
                blank=True,
                help_text="Текст и варианты копируются в этап, чтобы история не менялась при редактировании шаблона.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="event_assignments",
                to="league.wildcardcardtemplate",
                verbose_name="Карта из библиотеки",
            ),
        ),
        migrations.AlterField(
            model_name="eventwildcardquestion",
            name="points",
            field=models.PositiveSmallIntegerField(
                default=3,
                editable=False,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(10),
                ],
                verbose_name="Очки",
            ),
        ),
        migrations.AlterModelOptions(
            name="eventwildcardquestion",
            options={
                "ordering": ("sort_order", "id"),
                "verbose_name": "Карта этапа",
                "verbose_name_plural": "Карты этапов и правильные ответы",
            },
        ),
        migrations.RunPython(backfill_wildcard_library, clear_wildcard_library_links),
        migrations.AddConstraint(
            model_name="eventwildcardquestion",
            constraint=models.UniqueConstraint(
                fields=("event", "source_card"),
                name="unique_wildcard_template_per_event",
            ),
        ),
        migrations.CreateModel(
            name="PlayerWildcardOffer",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="wildcard_offers",
                        to="league.event",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="wildcard_offers",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Персональная тройка карт",
                "verbose_name_plural": "Персональные тройки карт",
                "ordering": ("event", "user__username"),
            },
        ),
        migrations.AddConstraint(
            model_name="playerwildcardoffer",
            constraint=models.UniqueConstraint(
                fields=("event", "user"),
                name="unique_wildcard_offer_per_event_user",
            ),
        ),
        migrations.CreateModel(
            name="PlayerWildcardOfferCard",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "slot",
                    models.PositiveSmallIntegerField(
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(3),
                        ],
                        verbose_name="Позиция карты",
                    ),
                ),
                (
                    "offer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cards",
                        to="league.playerwildcardoffer",
                    ),
                ),
                (
                    "question",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.RESTRICT,
                        related_name="offer_cards",
                        to="league.eventwildcardquestion",
                    ),
                ),
            ],
            options={
                "verbose_name": "Карта в персональной тройке",
                "verbose_name_plural": "Карты в персональной тройке",
                "ordering": ("slot",),
            },
        ),
        migrations.AddConstraint(
            model_name="playerwildcardoffercard",
            constraint=models.UniqueConstraint(
                fields=("offer", "slot"),
                name="unique_wildcard_offer_slot",
            ),
        ),
        migrations.AddConstraint(
            model_name="playerwildcardoffercard",
            constraint=models.UniqueConstraint(
                fields=("offer", "question"),
                name="unique_wildcard_offer_question",
            ),
        ),
    ]
