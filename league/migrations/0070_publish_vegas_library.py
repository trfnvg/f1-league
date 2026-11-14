from django.db import migrations


def publish(apps, schema_editor):
    Settings = apps.get_model("league", "ArcadeSettings")
    for settings in Settings.objects.all():
        games = settings.library_games
        if isinstance(games, list) and "vegas" not in games:
            settings.library_games = [*games, "vegas"]
            settings.save(update_fields=["library_games"])


class Migration(migrations.Migration):
    dependencies = [("league", "0069_alter_arcadebestvideo_game_key_and_more")]
    operations = [migrations.RunPython(publish, migrations.RunPython.noop)]
