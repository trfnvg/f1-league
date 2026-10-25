from django.db import migrations


# Official 2026 roster and portraits: https://www.formula1.com/en/drivers
# Race numbers cross-checked against the official driver profiles and Red Bull's
# 2026 number guide. Kept in this migration so later seasons cannot change it.
ROSTER = [
    ("norris", "Ландо Норрис", "Норрис", "McLaren", 1, "mclaren", "lannor01", "lando-norris"),
    ("piastri", "Оскар Пиастри", "Пиастри", "McLaren", 81, "mclaren", "oscpia01", "oscar-piastri"),
    ("russell", "Джордж Рассел", "Рассел", "Mercedes", 63, "mercedes", "georus01", "george-russell"),
    ("antonelli", "Кими Антонелли", "Антонелли", "Mercedes", 12, "mercedes", "andant01", "kimi-antonelli"),
    ("verstappen", "Макс Ферстаппен", "Ферстаппен", "Red Bull", 3, "redbullracing", "maxver01", "max-verstappen"),
    ("hadjar", "Исак Хаджар", "Хаджар", "Red Bull", 6, "redbullracing", "isahad01", "isack-hadjar"),
    ("leclerc", "Шарль Леклер", "Леклер", "Ferrari", 16, "ferrari", "chalec01", "charles-leclerc"),
    ("hamilton", "Льюис Хэмильтон", "Хэмильтон", "Ferrari", 44, "ferrari", "lewham01", "lewis-hamilton"),
    ("albon", "Алекс Албон", "Албон", "Williams", 23, "williams", "alealb01", "alexander-albon"),
    ("sainz", "Карлос Сайнс", "Сайнс", "Williams", 55, "williams", "carsai01", "carlos-sainz"),
    ("lindblad", "Арвид Линдблад", "Линдблад", "Racing Bulls", 41, "racingbulls", "arvlin01", "arvid-lindblad"),
    ("lawson", "Лиам Лоусон", "Лоусон", "Racing Bulls", 30, "racingbulls", "lialaw01", "liam-lawson"),
    ("stroll", "Лэнс Стролл", "Стролл", "Aston Martin", 18, "astonmartin", "lanstr01", "lance-stroll"),
    ("alonso", "Фернандо Алонсо", "Алонсо", "Aston Martin", 14, "astonmartin", "feralo01", "fernando-alonso"),
    ("ocon", "Эстебан Окон", "Окон", "Haas", 31, "haasf1team", "estoco01", "esteban-ocon"),
    ("bearman", "Оливер Берман", "Берман", "Haas", 87, "haasf1team", "olibea01", "oliver-bearman"),
    ("hulkenberg", "Нико Хюлкенберг", "Хюлкенберг", "Audi", 27, "audi", "nichul01", "nico-hulkenberg"),
    ("bortoleto", "Габриэл Бортолето", "Бортолето", "Audi", 5, "audi", "gabbor01", "gabriel-bortoleto"),
    ("gasly", "Пьер Гасли", "Гасли", "Alpine", 10, "alpine", "piegas01", "pierre-gasly"),
    ("colapinto", "Франко Колапинто", "Колапинто", "Alpine", 43, "alpine", "fracol01", "franco-colapinto"),
    ("perez", "Серхио Перес", "Перес", "Cadillac", 11, "cadillac", "serper01", "sergio-perez"),
    ("bottas", "Валттери Боттас", "Боттас", "Cadillac", 77, "cadillac", "valbot01", "valtteri-bottas"),
]


def seed(apps, schema_editor):
    Driver = apps.get_model("league", "DriverProfile")
    prefix = "https://media.formula1.com/image/upload/c_lfill,w_440/q_auto/d_common:f1:2026:fallback:driver:2026fallbackdriverright.webp/v1740000001/common/f1/2026"
    for key, name, surname, team, number, folder, code, slug in ROSTER:
        Driver.objects.using(schema_editor.connection.alias).get_or_create(
            season_year=2026, key=key,
            defaults={"name": name, "surname": surname, "team": team, "number": number,
                      "portrait_url": f"{prefix}/{folder}/{code}/2026{folder}{code}right.webp",
                      "source_url": f"https://www.formula1.com/en/drivers/{slug}"},
        )


class Migration(migrations.Migration):
    dependencies = [("league", "0049_driver_profiles")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
