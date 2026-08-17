import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


CARD_SPECS = (
    {
        "title": "Гонка · Победа с поула",
        "question": "Станет ли победителем гонки пилот, стартовавший с поула?",
        "option_a": "Да",
        "option_b": "Нет",
        "option_c": "",
        "draw_weight": 10,
    },
    {
        "title": "Гонка · Разные команды в топ-6",
        "question": "Сколько разных команд окажется в топ-6 официального протокола гонки?",
        "option_a": "3 команды",
        "option_b": "4 команды",
        "option_c": "5 и более",
        "draw_weight": 10,
    },
    {
        "title": "Редкая · Красный флаг",
        "question": "Будет ли во время гонки показан красный флаг?",
        "option_a": "Да",
        "option_b": "Нет",
        "option_c": "",
        "draw_weight": 2,
    },
    {
        "title": "Гонка · Стартовая топ-3 на подиуме",
        "question": "Финишируют ли все три пилота из стартовой топ-3 на подиуме в любом порядке?",
        "option_a": "Да",
        "option_b": "Нет",
        "option_c": "",
        "draw_weight": 10,
    },
    {
        "title": "Гонка · Три команды на подиуме",
        "question": "Будут ли на подиуме представлены три разные команды?",
        "option_a": "Да",
        "option_b": "Нет",
        "option_c": "",
        "draw_weight": 10,
    },
)


def seed_new_cards(apps, schema_editor):
    CardTemplate = apps.get_model("league", "WildcardCardTemplate")
    for spec in CARD_SPECS:
        CardTemplate.objects.update_or_create(
            title=spec["title"],
            defaults={
                "question": spec["question"],
                "option_a": spec["option_a"],
                "option_b": spec["option_b"],
                "option_c": spec["option_c"],
                "draw_weight": spec["draw_weight"],
                "is_active": True,
            },
        )


def remove_new_cards(apps, schema_editor):
    CardTemplate = apps.get_model("league", "WildcardCardTemplate")
    CardTemplate.objects.filter(title__in=[spec["title"] for spec in CARD_SPECS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("league", "0024_seed_balanced_2026_wildcard_cards"),
    ]

    operations = [
        migrations.AddField(
            model_name="wildcardcardtemplate",
            name="draw_weight",
            field=models.PositiveSmallIntegerField(
                default=10,
                help_text="10 — обычная карта. Чем меньше число, тем реже карта попадает в общую тройку этапа.",
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(100),
                ],
                verbose_name="Частота выпадения",
            ),
        ),
        migrations.AddField(
            model_name="wildcardcardtemplate",
            name="option_c",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Необязательно. Оставь пустым для обычной карты с двумя ответами.",
                max_length=120,
                verbose_name="Вариант C",
            ),
        ),
        migrations.AddField(
            model_name="eventwildcardquestion",
            name="draw_weight",
            field=models.PositiveSmallIntegerField(
                default=10,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(100),
                ],
                verbose_name="Частота выпадения",
            ),
        ),
        migrations.AddField(
            model_name="eventwildcardquestion",
            name="option_c",
            field=models.CharField(blank=True, default="", max_length=120, verbose_name="Вариант C"),
        ),
        migrations.AlterField(
            model_name="eventwildcardquestion",
            name="correct_option",
            field=models.CharField(
                blank=True,
                choices=[("a", "Вариант A"), ("b", "Вариант B"), ("c", "Вариант C")],
                default="",
                help_text="Заполни после завершения этапа перед публикацией очков.",
                max_length=1,
                verbose_name="Правильный вариант",
            ),
        ),
        migrations.AlterField(
            model_name="playerwildcard",
            name="selected_option",
            field=models.CharField(
                blank=True,
                choices=[("a", "Вариант A"), ("b", "Вариант B"), ("c", "Вариант C")],
                default="",
                max_length=1,
                verbose_name="Ответ игрока",
            ),
        ),
        migrations.CreateModel(
            name="EventWildcardDeck",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "event",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="wildcard_deck",
                        to="league.event",
                        verbose_name="Этап",
                    ),
                ),
            ],
            options={
                "verbose_name": "Общая тройка карт этапа",
                "verbose_name_plural": "Общие тройки карт этапов",
                "ordering": ("-event__season_year", "event__round_number"),
            },
        ),
        migrations.CreateModel(
            name="EventWildcardDeckCard",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
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
                    "deck",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cards",
                        to="league.eventwildcarddeck",
                    ),
                ),
                (
                    "question",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.RESTRICT,
                        related_name="shared_deck_cards",
                        to="league.eventwildcardquestion",
                    ),
                ),
            ],
            options={
                "verbose_name": "Карта в общей тройке",
                "verbose_name_plural": "Карты в общей тройке",
                "ordering": ("slot",),
                "constraints": [
                    models.UniqueConstraint(fields=("deck", "slot"), name="unique_wildcard_deck_slot"),
                    models.UniqueConstraint(fields=("deck", "question"), name="unique_wildcard_deck_question"),
                ],
            },
        ),
        migrations.RunPython(seed_new_cards, remove_new_cards),
    ]
