from django.db import migrations
from django.db.models import F


def assign(apps, schema_editor):
    Member = apps.get_model("league", "LeagueMembership")
    db = schema_editor.connection.alias
    Member.objects.using(db).filter(is_active=True, user_id=F("league__owner_id")).update(role="manager")
    Member.objects.using(db).filter(is_active=True, league__legacy_key="original-friends",
        user__username="Гриша", user__is_active=True).update(role="manager")


class Migration(migrations.Migration):
    dependencies = [("league", "0045_league_manager_and_identity")]
    operations = [migrations.RunPython(assign, migrations.RunPython.noop)]
