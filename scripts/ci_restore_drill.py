"""Backup/restore rehearsal on a disposable localhost CI database ONLY.

Never accepts a production URL or an arbitrary restore destination. Does not
prove that Timeweb production backups exist or can be restored.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit

import psycopg2


SOURCE = "fastlap_ci"
TARGET = "fastlap_restore_ci"


def run():
    url = urlsplit(os.environ.get("DATABASE_URL", ""))
    if (os.getenv("CI") != "true" or url.scheme not in {"postgres", "postgresql"}
            or url.hostname not in {"127.0.0.1", "localhost"} or url.path != "/" + SOURCE
            or url.username != "fastlap_ci" or url.query or url.fragment):
        raise SystemExit("Refusing restore drill: isolated localhost CI database required.")
    # Matching client major version avoids pg_dump client/server incompatibility.
    pg_bin = Path("/usr/lib/postgresql/16/bin")
    tools = {name: str(pg_bin / name) if (pg_bin / name).exists() else shutil.which(name)
             for name in ("pg_dump", "pg_restore")}
    if not all(tools.values()):
        raise SystemExit("Install PostgreSQL client tools first.")
    import django
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()
    from django.contrib.auth.models import User
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM auth_user")
        if cursor.fetchone()[0]:
            raise SystemExit("Refusing restore drill: source must contain no user accounts.")
        cursor.execute("SELECT app, name FROM django_migrations ORDER BY app, name")
        expected_migrations = cursor.fetchall()
    user = User.objects.create_user("ci_restore_probe", email="probe@example.invalid")
    user.set_unusable_password()
    user.save(update_fields=["password"])
    env = os.environ.copy()
    # Credentials are passed through the child environment, never command arguments.
    env.update(PGHOST=url.hostname, PGPORT=str(url.port or 5432), PGUSER="fastlap_ci",
               PGPASSWORD=connection.settings_dict["PASSWORD"], PGCONNECT_TIMEOUT="5")
    with tempfile.TemporaryDirectory(prefix="fastlap-ci-restore-") as directory:
        dump = Path(directory) / "database.dump"
        subprocess.run([tools["pg_dump"], "--format=custom", "--no-owner", "--no-acl",
                        "--dbname=" + SOURCE, "--file=" + str(dump)], env=env, check=True, timeout=120)
        dump.chmod(0o600)
        # Never DROP/overwrite anything. An existing target is an error.
        admin = psycopg2.connect(host=url.hostname, port=url.port or 5432, user="fastlap_ci",
                                password=env["PGPASSWORD"], dbname="postgres", connect_timeout=5)
        try:
            admin.autocommit = True
            with admin.cursor() as cursor:
                cursor.execute("CREATE DATABASE fastlap_restore_ci")
        finally:
            admin.close()
        subprocess.run([tools["pg_restore"], "--exit-on-error", "--no-owner", "--no-acl",
                        "--dbname=" + TARGET, str(dump)], env=env, check=True, timeout=120)
        with psycopg2.connect(host=url.hostname, port=url.port or 5432, user="fastlap_ci",
                              password=env["PGPASSWORD"], dbname=TARGET, connect_timeout=5) as restored:
            with restored.cursor() as cursor:
                cursor.execute("SELECT app, name FROM django_migrations ORDER BY app, name")
                assert cursor.fetchall() == expected_migrations, "Migration history differs after restore"
                cursor.execute("SELECT username, email, password FROM auth_user")
                assert cursor.fetchall() == [(user.username, user.email, user.password)], "Restored account differs"
                cursor.execute("SELECT COUNT(*) FROM league_userprofile WHERE user_id = %s", [user.pk])
                assert cursor.fetchone()[0] == 1, "Related profile missing after restore"
    print("CI restore OK: migrations, synthetic account and related profile survived pg_dump/pg_restore.")


if __name__ == "__main__":
    run()
