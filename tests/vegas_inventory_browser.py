"""Shop purchase -> reload -> deadline -> activation, using real Django APIs."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
import os
from pathlib import Path
import sys
import threading
from unittest.mock import patch
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
from django.utils import timezone
from playwright.sync_api import sync_playwright, expect
from league.leagues import create_league, enroll_member
from league.models import ArcadeCompetition, ArcadeSettings, Event, Prediction, Season, VegasPurchase, VegasWallet


def run(engine, output):
    now = timezone.now()
    database = ThreadPoolExecutor(max_workers=1)
    holder = {}
    with override_settings(ALLOWED_HOSTS=["127.0.0.1", "testserver"], STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }), patch("django.utils.timezone.now", return_value=now) as clock:
        def initialize():
            call_command("migrate", verbosity=0, interactive=False)
            season = Season.get_active()
            event = Event.objects.create(name="Vegas inventory GP", season_year=season.year, round_number=22,
                deadline=now+timedelta(hours=1), race_datetime=now+timedelta(hours=5))
            owner = User.objects.create_user("inventory-owner")
            league = create_league(owner=owner, name="Vegas friends", season=season, start_event=event, ruleset="paddock")
            contest = ArcadeCompetition.objects.create(event=event, game_key="vegas", opened_at=now)
            ArcadeSettings.objects.update_or_create(pk=1, defaults={"active_game": "vegas", "public_enabled": True,
                "competition_event": event, "competition_opened_at": now})
            return event, owner, league, contest
        event, owner, league, contest = database.submit(initialize).result(timeout=20)

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                path = urlsplit(self.path).path
                if path.startswith("/static/") and (file := finders.find(path[8:])):
                    self.respond(200, mimetypes.guess_type(file)[0] or "application/octet-stream", Path(file).read_bytes())
                else:
                    self.dynamic("GET")

            def do_POST(self):
                self.dynamic("POST")

            def respond(self, status, mime, body):
                self.send_response(status)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def dynamic(self, method):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                response = database.submit(holder["client"].generic, method, self.path, data=body,
                    content_type=self.headers.get("Content-Type", "application/octet-stream"),
                    HTTP_HOST=self.headers["Host"], HTTP_X_CSRFTOKEN=self.headers.get("X-CSRFToken", "")).result(timeout=10)
                self.respond(response.status_code, response.get("Content-Type", "text/html"), response.content)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        output.mkdir(parents=True, exist_ok=True)
        errors = []
        try:
            with sync_playwright() as p:
                browser = getattr(p, engine).launch()
                for width in (390, 1440):
                    clock.return_value = now
                    def player():
                        user = User.objects.create_user(f"inventory-{width}")
                        enroll_member(actor=owner, league_season=league, user=user)
                        Prediction.objects.create(event=event, user=user, p1="norris", p2="russell", p3="leclerc")
                        wallet = VegasWallet.objects.create(user=user, competition=contest)
                        holder["client"] = Client(enforce_csrf_checks=True)
                        holder["client"].force_login(user)
                        return wallet.pk
                    wallet_id = database.submit(player).result()
                    context = browser.new_context(viewport={"width": width, "height": 900}, reduced_motion="reduce")
                    context.route("https://**", lambda route: route.abort())
                    page = context.new_page()
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on("dialog", lambda dialog: dialog.accept())
                    url = f"http://127.0.0.1:{server.server_port}/arcade/vegas/shop/?wallet={wallet_id}"
                    page.goto(url, wait_until="domcontentloaded")
                    page.locator('[data-product="tyres"]').click()
                    expect(page.locator("#shop-buy")).to_be_enabled()
                    page.locator("#shop-buy").click()
                    expect(page.locator("#shop-detail-note")).to_contain_text("Куплено")
                    expect(page.locator("#shop-buy")).to_be_hidden()
                    expect(page.locator("#shop-apply")).to_be_disabled()
                    expect(page.locator("#shop-balance")).to_contain_text("2\u00a0500")
                    page.reload(wait_until="domcontentloaded")
                    expect(page.locator('[data-item-state="tyres"]')).to_have_text("КУПЛЕНО")
                    clock.return_value = event.deadline
                    page.reload(wait_until="domcontentloaded")
                    page.locator('[data-product="tyres"]').click()
                    expect(page.locator("#shop-apply")).to_be_enabled()
                    page.locator("#shop-apply").click()
                    expect(page.locator("#shop-detail-note")).to_contain_text("Применено · Vegas friends")
                    expect(page.locator("#shop-apply")).to_be_hidden()
                    if engine == "webkit":
                        page.screenshot(path=str(output/f"{engine}-{width}-applied.png"))
                    page.reload(wait_until="domcontentloaded")
                    expect(page.locator('[data-item-state="tyres"]')).to_have_text("ПРИМЕНЕНО")
                    if engine == "webkit":
                        page.screenshot(path=str(output/f"{engine}-{width}-inventory.png"))
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+1")
                    item = database.submit(lambda: VegasPurchase.objects.get(wallet_id=wallet_id)).result()
                    self_balance = database.submit(lambda: VegasWallet.objects.get(pk=wallet_id).balance).result()
                    assert item.activated_at and item.league_season_id == league.pk and self_balance == 250000
                    context.close()
                browser.close()
            assert not errors, errors
            print(f"{engine}: mobile/desktop real purchases, persistent ownership, deadline gate, activation and unchanged post-deadline balance OK")
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)
            database.shutdown(wait=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("webkit", "chromium"), default="webkit")
    parser.add_argument("--output", type=Path, default=Path("/tmp/fastlap-vegas-inventory"))
    args = parser.parse_args()
    run(args.engine, args.output)
