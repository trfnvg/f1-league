from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("league", "0047_league_deletion_audit")]

    operations = [
        migrations.AddField(
            model_name="event",
            name="circuit",
            field=models.CharField(
                blank=True, default="", max_length=24,
                verbose_name="Гран-при / трасса",
                help_text="Выберите этап: схема трассы и её анимация появятся автоматически. Для старых карточек трасса определяется по названию.",
                choices=[('melbourne', 'Гран-при Австралии — Albert Park Circuit'), ('shanghai', 'Гран-при Китая — Shanghai International Circuit'), ('suzuka', 'Гран-при Японии — Suzuka International Racing Course'), ('bahrain', 'Гран-при Бахрейна — Bahrain International Circuit'), ('jeddah', 'Гран-при Саудовской Аравии — Jeddah Corniche Circuit'), ('miami', 'Гран-при Майами — Miami International Autodrome'), ('montreal', 'Гран-при Канады — Circuit Gilles-Villeneuve'), ('monaco', 'Гран-при Монако — Circuit de Monaco'), ('barcelona', 'Гран-при Барселоны-Каталуньи — Circuit de Barcelona-Catalunya'), ('spielberg', 'Гран-при Австрии — Red Bull Ring'), ('silverstone', 'Гран-при Великобритании — Silverstone Circuit'), ('spa', 'Гран-при Бельгии — Circuit de Spa-Francorchamps'), ('hungaroring', 'Гран-при Венгрии — Hungaroring'), ('zandvoort', 'Гран-при Нидерландов — Circuit Zandvoort'), ('monza', 'Гран-при Италии — Autodromo Nazionale Monza'), ('madrid', 'Гран-при Испании — Circuito de Madring'), ('baku', 'Гран-при Азербайджана — Baku City Circuit'), ('singapore', 'Гран-при Сингапура — Marina Bay Street Circuit'), ('austin', 'Гран-при США — Circuit of the Americas'), ('mexico', 'Гран-при Мехико — Autódromo Hermanos Rodríguez'), ('interlagos', 'Гран-при Сан-Паулу — Autódromo José Carlos Pace - Interlagos'), ('las-vegas', 'Гран-при Лас-Вегаса — Las Vegas Street Circuit'), ('lusail', 'Гран-при Катара — Losail International Circuit'), ('yas-marina', 'Гран-при Абу-Даби — Yas Marina Circuit'), ('imola', 'Гран-при Эмилии-Романьи — Autodromo Enzo e Dino Ferrari'), ('portimao', 'Гран-при Португалии — Autódromo Internacional do Algarve'), ('istanbul', 'Гран-при Турции — Intercity Istanbul Park')],
            ),
        ),
    ]
