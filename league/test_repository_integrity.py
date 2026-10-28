"""Catch broken asset references and accidental local data before deployment."""
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase
from django.urls import resolve, reverse


ROOT = Path(settings.BASE_DIR)


class RepositoryIntegrityTests(SimpleTestCase):
    def test_literal_template_static_assets_exist(self):
        pattern = re.compile(r'''\{%\s*static\s+(['"])([^'"]+)\1''')
        roots = [ROOT / "league/templates", ROOT / "templates"]
        missing = []
        for root in roots:
            for template in root.rglob("*.html"):
                for _, name in pattern.findall(template.read_text()):
                    if not finders.find(name):
                        missing.append(f"{template.relative_to(ROOT)}: {name}")
        self.assertEqual(missing, [], "Missing template assets:\n" + "\n".join(missing))

    def test_css_local_assets_exist(self):
        static = ROOT / "league/static"
        pattern = re.compile(r'''url\(\s*(['"]?)([^'"\)]+)\1\s*\)''')
        missing = []
        for stylesheet in (static / "league").glob("*.css"):
            for _, raw in pattern.findall(stylesheet.read_text()):
                value = raw.strip()
                url = urlsplit(value)
                if url.scheme or url.netloc or not url.path or value.startswith(("var(", "#")):
                    continue
                if url.path.startswith("/static/"):
                    exists = finders.find(url.path.removeprefix("/static/"))
                elif url.path.startswith("/"):
                    continue  # Runtime media/route, not a repository-relative asset.
                else:
                    exists = (stylesheet.parent / url.path).is_file()
                if not exists:
                    missing.append(f"{stylesheet.relative_to(ROOT)}: {value}")
        self.assertEqual(missing, [], "Missing CSS assets:\n" + "\n".join(missing))

    def test_local_databases_uploads_and_system_files_are_not_tracked(self):
        if not (ROOT / ".git").exists():
            self.skipTest("Source distribution without Git metadata")
        result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                                capture_output=True, check=True)
        forbidden = []
        for name in result.stdout.decode().split("\0"):
            path = Path(name)
            if (name.startswith(("media/", "staticfiles/", "backups/"))
                    or path.name in {".DS_Store", ".env"}
                    or (path.name.startswith(".env.") and path.name not in {".env.example", ".env.sample"})
                    or path.suffix in {".sqlite", ".sqlite3", ".dump", ".pyc"}
                    or "__pycache__" in path.parts):
                forbidden.append(name)
        self.assertEqual(forbidden, [], "Local data must not be committed: " + ", ".join(forbidden))

    def test_published_games_use_the_current_library_routes(self):
        for name in ("arcade", "arcade_control", "arcade_doodle_jump", "arcade_leaderboard",
                     "doodle_leaderboard", "arcade_run_start", "arcade_run_finish",
                     "doodle_attempt_start", "doodle_attempt_finish"):
            with self.subTest(name=name):
                view = resolve(reverse("league:" + name)).func
                self.assertEqual(view.__module__, "league.arcade_library")
