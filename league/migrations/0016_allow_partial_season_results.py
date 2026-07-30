from django.db import migrations, models


DRIVER_CHOICES = [
    ("norris", "Норрис (McLaren)"),
    ("piastri", "Пиастри (McLaren)"),
    ("russell", "Рассел (Mercedes)"),
    ("antonelli", "Антонелли (Mercedes)"),
    ("verstappen", "Ферстаппен (Red Bull)"),
    ("hadjar", "Хаджар (Red Bull)"),
    ("leclerc", "Леклер (Ferrari)"),
    ("hamilton", "Хэмильтон (Ferrari)"),
    ("albon", "Албон (Williams)"),
    ("sainz", "Сайнс (Williams)"),
    ("lindblad", "Линдблад (Racing Bulls)"),
    ("lawson", "Лоусон (Racing Bulls)"),
    ("stroll", "Стролл (Aston Martin)"),
    ("alonso", "Алонсо (Aston Martin)"),
    ("ocon", "Окон (Haas)"),
    ("bearman", "Берман (Haas)"),
    ("hulkenberg", "Хюлкенберг (Audi)"),
    ("bortoleto", "Бортолето (Audi)"),
    ("gasly", "Гасли (Alpine)"),
    ("colapinto", "Колапинто (Alpine)"),
    ("perez", "Перес (Cadillac)"),
    ("bottas", "Боттас (Cadillac)"),
]

CONSTRUCTOR_CHOICES = [
    ("mclaren", "McLaren"),
    ("mercedes", "Mercedes"),
    ("red_bull", "Red Bull"),
    ("ferrari", "Ferrari"),
    ("williams", "Williams"),
    ("racing_bulls", "Racing Bulls"),
    ("aston_martin", "Aston Martin"),
    ("haas", "Haas"),
    ("audi", "Audi"),
    ("alpine", "Alpine"),
    ("cadillac", "Cadillac"),
]

YES_NO_CHOICES = [
    ("yes", "Да"),
    ("no", "Нет"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("league", "0015_alter_event_has_sprint_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="seasonresult",
            name="world_drivers_champion",
            field=models.CharField(
                blank=True,
                choices=DRIVER_CHOICES,
                default="",
                max_length=50,
                verbose_name="Чемпион мира среди пилотов (факт)",
            ),
        ),
        migrations.AlterField(
            model_name="seasonresult",
            name="constructors_champion",
            field=models.CharField(
                blank=True,
                choices=CONSTRUCTOR_CHOICES,
                default="",
                max_length=50,
                verbose_name="Чемпион Кубка конструкторов (факт)",
            ),
        ),
        migrations.AlterField(
            model_name="seasonresult",
            name="constructors_second",
            field=models.CharField(
                blank=True,
                choices=CONSTRUCTOR_CHOICES,
                default="",
                max_length=50,
                verbose_name="2 место Кубка конструкторов (факт)",
            ),
        ),
        migrations.AlterField(
            model_name="seasonresult",
            name="constructors_third",
            field=models.CharField(
                blank=True,
                choices=CONSTRUCTOR_CHOICES,
                default="",
                max_length=50,
                verbose_name="3 место Кубка конструкторов (факт)",
            ),
        ),
        migrations.AlterField(
            model_name="seasonresult",
            name="last_race_winner",
            field=models.CharField(
                blank=True,
                choices=DRIVER_CHOICES,
                default="",
                max_length=50,
                verbose_name="Победитель последней гонки сезона (факт)",
            ),
        ),
        migrations.AlterField(
            model_name="seasonresult",
            name="season_pole_sitter",
            field=models.CharField(
                blank=True,
                choices=DRIVER_CHOICES,
                default="",
                max_length=50,
                verbose_name="Pole-sitter сезона (факт)",
            ),
        ),
        migrations.AlterField(
            model_name="seasonresult",
            name="driver_change_happened",
            field=models.CharField(
                blank=True,
                choices=YES_NO_CHOICES,
                default="",
                max_length=3,
                verbose_name="Была ли смена пилота в сезоне (факт)",
            ),
        ),
        migrations.AlterField(
            model_name="seasonresult",
            name="team_most_dnf",
            field=models.CharField(
                blank=True,
                choices=CONSTRUCTOR_CHOICES,
                default="",
                max_length=50,
                verbose_name="Команда-лидер по количеству DNF (факт)",
            ),
        ),
    ]
