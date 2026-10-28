"""Exercise the real POSIX startup script without touching a real database."""
import importlib.util
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from unittest.mock import patch

from django.test import Client, SimpleTestCase, override_settings


ROOT = Path(__file__).resolve().parents[1]


class StartupScriptTests(SimpleTestCase):
    def run_startup(self, *, database="postgresql://synthetic.invalid/test", fail_at="", port=None):
        with tempfile.TemporaryDirectory(prefix="fastlap-startup-test-") as directory:
            path = Path(directory)
            calls = path / "calls.txt"
            # This fake executable only records command names and fails when
            # requested; it never imports Django, reads keys or connects to DB.
            executable = path / "python"
            executable.write_text("#!/bin/sh\n"
                'printf "%s\\n" "$*" >> "$STARTUP_TEST_CALLS"\n'
                'case "$*" in *"$STARTUP_TEST_FAIL"*) '
                'if [ -n "$STARTUP_TEST_FAIL" ]; then exit 7; fi ;; esac\n'
                'if [ "$1" = "-m" ]; then printf "FAKE_GUNICORN_UNBUFFERED=%s\\n" "$PYTHONUNBUFFERED"; fi\n')
            executable.chmod(0o700)
            env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT") if key in os.environ}
            env.update(PATH=str(path) + os.pathsep + env.get("PATH", ""),
                STARTUP_TEST_CALLS=str(calls), STARTUP_TEST_FAIL=fail_at)
            if database is not None:
                env["DATABASE_URL"] = database
            if port is not None:
                env["PORT"] = port
            result = subprocess.run(["sh", str(ROOT / "start.sh")], env=env,
                cwd=ROOT, text=True, capture_output=True, timeout=10)
            return result, calls.read_text().splitlines() if calls.exists() else []

    def test_boots_without_a_blocking_security_audit(self):
        result, calls = self.run_startup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[:3], ["--version", "manage.py migrate --noinput", "manage.py collectstatic --noinput"])
        self.assertNotIn("security_audit", "\n".join(calls))
        self.assertEqual(shlex.split(calls[-1])[:3], ["-m", "gunicorn", "config.wsgi:application"])
        self.assertIn("--bind 0.0.0.0:8000", calls[-1])
        self.assertIn("--capture-output", calls[-1])
        self.assertIn("FAKE_GUNICORN_UNBUFFERED=1", result.stdout)

    def test_missing_database_never_creates_local_sqlite(self):
        for value in (None, "", " \t\n"):
            with self.subTest(value=value):
                result, calls = self.run_startup(database=value)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(calls, ["--version"])
                self.assertIn("stage=database configuration", result.stderr)

    def test_migration_failure_stops_before_static_and_server(self):
        result, calls = self.run_startup(fail_at="migrate")
        self.assertEqual(result.returncode, 7)
        self.assertEqual(len(calls), 2)
        self.assertIn("stage=database migrations exit_code=7", result.stderr)

    def test_static_failure_stops_before_server(self):
        result, calls = self.run_startup(fail_at="collectstatic")
        self.assertEqual(result.returncode, 7)
        self.assertEqual(len(calls), 3)
        self.assertIn("stage=static assets exit_code=7", result.stderr)

    def test_platform_port_override_is_respected(self):
        result, calls = self.run_startup(port="8080")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--bind 0.0.0.0:8080", calls[-1])
        self.assertIn("Starting Gunicorn on 0.0.0.0:8080", result.stdout)


class HealthHostConfigurationTests(SimpleTestCase):
    def configured_hosts(self, **variables):
        # Load only the settings module under an isolated env; never read the
        # developer's .env, DB, mail credentials or optional monitoring DSN.
        env = {"DATABASE_URL": "sqlite:///:memory:", "DEBUG": "False", "USE_S3": "False",
               "SENTRY_DSN": "", **variables}
        spec = importlib.util.spec_from_file_location("fastlap_startup_test_settings", ROOT / "config/settings.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, env, clear=True):
            spec.loader.exec_module(module)
        return module.ALLOWED_HOSTS

    def test_public_only_env_does_not_break_timeweb_loopback_probe(self):
        hosts = self.configured_hosts(ALLOWED_HOSTS="fastlap.ru,www.fastlap.ru")
        with override_settings(ALLOWED_HOSTS=hosts, DEBUG=False):
            for host in ("localhost:8000", "127.0.0.1:8000", "[::1]:8000", "fastlap.ru"):
                with self.subTest(host=host):
                    response = Client().get("/health/live/", HTTP_HOST=host)
                    self.assertEqual(response.status_code, 200)
            self.assertEqual(Client().get("/health/live/", HTTP_HOST="untrusted.invalid").status_code, 400)
        self.assertNotIn("*", hosts)

    def test_timeweb_alias_keeps_custom_domain_and_deduplicates_loopback(self):
        hosts = self.configured_hosts(DJANGO_ALLOWED_HOSTS="app.example,localhost")
        self.assertIn("app.example", hosts)
        self.assertEqual(hosts.count("localhost"), 1)
        self.assertNotIn("fastlap.ru", hosts)

    def test_explicit_hosts_still_take_priority_over_timeweb_alias(self):
        hosts = self.configured_hosts(ALLOWED_HOSTS="fastlap.ru", DJANGO_ALLOWED_HOSTS="other.example")
        self.assertIn("fastlap.ru", hosts)
        self.assertNotIn("other.example", hosts)
