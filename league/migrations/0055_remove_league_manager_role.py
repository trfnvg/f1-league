from django.db import migrations, models
from django.db.models import F


def retire_manager_role(apps, schema_editor):
    members = apps.get_model("league", "LeagueMembership").objects.using(schema_editor.connection.alias)
    # Ownership lives in League.owner, not in the membership role.
    managers = members.filter(role="manager")
    managers.filter(user_id=F("league__owner_id")).update(role="player")
    managers.update(role="moderator")


class Migration(migrations.Migration):
    dependencies = [("league", "0054_permanent_league_invite")]
    operations = [
        migrations.RunPython(retire_manager_role, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="leaguemembership", name="league_member_role_valid"),
        migrations.AlterField(model_name="leaguemembership", name="role",
            field=models.CharField(choices=[("player", "Игрок"), ("moderator", "Модератор")], default="player", max_length=12)),
        migrations.AddConstraint(model_name="leaguemembership",
            constraint=models.CheckConstraint(condition=models.Q(role__in=("player", "moderator")), name="league_member_role_valid")),
    ]
