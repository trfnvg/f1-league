import re
from django.db import migrations, models
from django.db.models.functions import Lower


def assign_handles(apps, schema_editor):
    User = apps.get_model("auth", "User")
    Profile = apps.get_model("league", "UserProfile")
    alias = schema_editor.connection.alias
    users = list(User.objects.using(alias).order_by("pk"))
    reserved = {user.username.casefold(): user.pk for user in users}
    used = set()
    for user in users:
        base = re.sub(r"[^a-z0-9]", "", user.username.lower())[:30]
        candidate = base if len(base) >= 3 else f"player{user.pk}"
        attempt = 0
        while candidate in used or reserved.get(candidate, user.pk) != user.pk:
            attempt += 1
            candidate = f"player{user.pk}x{attempt}"
        used.add(candidate)
        Profile.objects.using(alias).update_or_create(user_id=user.pk, defaults={"handle": candidate})


class Migration(migrations.Migration):
    dependencies = [("league", "0050_seed_driver_profiles_2026")]
    operations = [
        migrations.AddField(model_name="userprofile", name="handle", field=models.CharField("Логин", max_length=30, unique=True, null=True, blank=True)),
        migrations.RunPython(assign_handles, migrations.RunPython.noop),
        migrations.AddConstraint(model_name="userprofile", constraint=models.UniqueConstraint(Lower("handle"), name="unique_player_handle_ci")),
    ]
