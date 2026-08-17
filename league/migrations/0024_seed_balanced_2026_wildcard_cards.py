from django.db import migrations


TEAMMATE_PAIRS = (
    ("Норрис", "Пиастри"),
    ("Рассел", "Антонелли"),
    ("Леклер", "Хэмильтон"),
    ("Албон", "Сайнс"),
    ("Линдблад", "Лоусон"),
    ("Окон", "Берман"),
    ("Хюлкенберг", "Бортолето"),
    ("Перес", "Боттас"),
)

RIVAL_PAIRS = (
    ("Сайнс", "Алонсо"),
    ("Окон", "Гасли"),
    ("Берман", "Бортолето"),
    ("Лоусон", "Хаджар"),
)


def card_specs():
    for driver_a, driver_b in TEAMMATE_PAIRS:
        yield {
            "title": f"2026 · Гонка · {driver_a} / {driver_b}",
            "question": "Кто окажется выше в официальном протоколе гонки, включая DNF и NC?",
            "option_a": driver_a,
            "option_b": driver_b,
        }
        # Меняем стороны местами, чтобы в библиотеке вариант A не был постоянно
        # закреплён за первым пилотом пары.
        yield {
            "title": f"2026 · Квалификация · {driver_b} / {driver_a}",
            "question": "Кто займёт более высокую позицию в итоговом протоколе квалификации?",
            "option_a": driver_b,
            "option_b": driver_a,
        }

    for driver_a, driver_b in RIVAL_PAIRS:
        yield {
            "title": f"2026 · Гонка · {driver_a} / {driver_b}",
            "question": "Кто окажется выше в официальном протоколе гонки, включая DNF и NC?",
            "option_a": driver_a,
            "option_b": driver_b,
        }
        yield {
            "title": f"2026 · Квалификация · {driver_b} / {driver_a}",
            "question": "Кто займёт более высокую позицию в итоговом протоколе квалификации?",
            "option_a": driver_b,
            "option_b": driver_a,
        }


def seed_balanced_cards(apps, schema_editor):
    CardTemplate = apps.get_model("league", "WildcardCardTemplate")
    for spec in card_specs():
        CardTemplate.objects.get_or_create(
            title=spec["title"],
            defaults={
                "question": spec["question"],
                "option_a": spec["option_a"],
                "option_b": spec["option_b"],
                "is_active": True,
            },
        )


def remove_seeded_cards(apps, schema_editor):
    CardTemplate = apps.get_model("league", "WildcardCardTemplate")
    CardTemplate.objects.filter(
        title__in=[spec["title"] for spec in card_specs()],
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("league", "0023_wildcard_card_library_and_offers"),
    ]

    operations = [
        migrations.RunPython(seed_balanced_cards, remove_seeded_cards),
    ]
