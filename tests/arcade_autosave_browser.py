"""Real browser -> Django autosave regression, isolated in an in-memory DB."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
import os
from pathlib import Path
import sys
import threading
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["USE_S3"] = "False"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import sync_playwright, expect
from league.models import ArcadeCompetition, ArcadeSettings, Event, Season


def run(engine):
    database = ThreadPoolExecutor(max_workers=1)

    def initialize():
        call_command("migrate", verbosity=0, interactive=False)
        client = Client(enforce_csrf_checks=True)
        client.force_login(User.objects.create_user("autosave-admin", is_staff=True))
        season = Season.get_active()
        event = Event.objects.create(name="Autosave Vegas GP", season_year=season.year, round_number=22,
            deadline=timezone.now()+timedelta(days=7))
        ArcadeSettings.objects.update_or_create(pk=1, defaults={"public_enabled": False,
            "competition_event": None, "competition_opened_at": None})
        return client, event.pk, reverse("league:arcade_control")+f"?season={season.year}&event={event.pk}"

    with override_settings(ALLOWED_HOSTS=["127.0.0.1", "testserver"], STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }):
        client, event_id, control_url = database.submit(initialize).result(timeout=20)

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                path = urlsplit(self.path).path
                if path.startswith("/static/") and (filename := finders.find(path[8:])):
                    self.send_response(200)
                    self.send_header("Content-Type", mimetypes.guess_type(filename)[0] or "application/octet-stream")
                    self.end_headers()
                    self.write(Path(filename).read_bytes())
                else:
                    self.dynamic("GET")

            def do_POST(self):
                self.dynamic("POST")

            def write(self, body):
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def dynamic(self, method):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                response = database.submit(client.generic, method, self.path, data=body,
                    content_type=self.headers.get("Content-Type", "application/octet-stream"),
                    HTTP_HOST=self.headers["Host"], HTTP_X_REQUESTED_WITH=self.headers.get("X-Requested-With", "")).result(timeout=10)
                self.send_response(response.status_code)
                self.send_header("Content-Type", response.get("Content-Type", "text/html"))
                if response.get("Location"):
                    self.send_header("Location", response["Location"])
                self.end_headers()
                self.write(response.content)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"
        errors = []
        try:
            with sync_playwright() as p:
                browser = getattr(p, engine).launch()
                for width in (390, 1440):
                    context = browser.new_context(viewport={"width": width, "height": 900})
                    context.route("https://**", lambda route: route.abort())
                    page = context.new_page()
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(base+control_url, wait_until="networkidle")
                    page.evaluate('window.autosaveMarker="same-document"')
                    game, note = page.locator("#arcade-game-select"), page.locator(".lab-save-status")
                    # Preserve the actual clobbered form, not a sanitized mock.
                    assert page.locator(".lab-competition-form").evaluate('f=>String(f.action)') == "[object RadioNodeList]"
                    with page.expect_response(lambda r: r.request.method == "POST") as saved:
                        game.select_option("vegas")
                    assert saved.value.status == 200 and urlsplit(saved.value.url).path == "/arcade/control/"
                    expect(note).to_contain_text("Сохранено")
                    plan = database.submit(lambda: ArcadeCompetition.objects.get(event_id=event_id)).result()
                    assert plan.game_key == "vegas" and plan.opened_at is None
                    assert not database.submit(lambda: ArcadeSettings.objects.get(pk=1).public_enabled).result()
                    assert page.evaluate("window.autosaveMarker") == "same-document"

                    def fail(code, mime="text/html", body="Error"):
                        def handler(route):
                            if route.request.method == "POST":
                                route.fulfill(status=code, content_type=mime, body=body)
                            else:
                                route.continue_()
                        return handler

                    for code, message in ((403, "Сервер отклонил запрос"), (404, "HTTP 404"),
                                          (503, "Ошибка сервера"), (200, "неожиданный ответ"),
                                          (401, "войти в аккаунт заново")):
                        handler = fail(code)
                        page.route("**/arcade/control/**", handler)
                        game.select_option("tetris")
                        expect(note).to_contain_text(message)
                        expect(note).not_to_contain_text("Сессия истекла")
                        expect(page.locator('.lab-competition-form [value="publish"]')).to_be_disabled()
                        page.unroute("**/arcade/control/**", handler)
                        page.locator('.lab-competition-form [value="select"]').click()
                        expect(note).to_contain_text("Сохранено")
                        plan = database.submit(lambda: ArcadeCompetition.objects.get(event_id=event_id)).result()
                        assert plan.game_key == "tetris" and plan.opened_at is None

                    # Actual CSRF rejection is not mislabeled as session expiry.
                    token = page.locator('.lab-competition-form [name="csrfmiddlewaretoken"]')
                    original = token.input_value()
                    token.evaluate('el=>el.value="invalid"')
                    game.select_option("vegas")
                    expect(note).to_contain_text("Сервер отклонил запрос")
                    token.evaluate("(el,value)=>el.value=value", original)
                    page.locator('.lab-competition-form [value="select"]').click()
                    expect(note).to_contain_text("Сохранено")
                    expect(page.locator('.lab-competition-form [value="publish"]')).to_be_enabled()
                    assert page.evaluate("window.autosaveMarker") == "same-document"
                    context.close()
                browser.close()
            assert not errors, errors
            print(f"{engine}: real CSRF-protected Vegas autosave, persisted drafts, no publish/reload, HTTP error messages and retries OK")
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)
            database.shutdown(wait=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("webkit", "chromium"), default="webkit")
    run(parser.parse_args().engine)
