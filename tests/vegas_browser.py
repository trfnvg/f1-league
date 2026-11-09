"""End-to-end staff sandbox with synthetic users, in-memory DB and real APIs."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
import os
from pathlib import Path
import random
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
from playwright.sync_api import sync_playwright, expect
from league import vegas_rules


def run(engine, output):
    ready = threading.Event()
    server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    database = ThreadPoolExecutor(max_workers=1)
    errors = []

    def serve():
        try:
            def initialize():
                call_command("migrate", verbosity=0, interactive=False)
                user, _ = User.objects.get_or_create(username=f"vegas-browser-{engine}", defaults={"is_staff": True})
                client = Client(enforce_csrf_checks=True)
                client.force_login(user)
                return client
            client = database.submit(initialize).result(timeout=15)
            original = vegas_rules.outcome

            class Handler(BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass

                def do_GET(self):
                    path = urlsplit(self.path).path
                    if path.startswith("/static/"):
                        file = finders.find(path[len("/static/"):])
                        if file:
                            body = Path(file).read_bytes()
                            self.send_response(200)
                            self.send_header("Content-Type", mimetypes.guess_type(file)[0] or "application/octet-stream")
                            self.end_headers()
                            self.wfile.write(body)
                            return
                        self.send_error(404)
                        return
                    self.dynamic("GET")

                def do_POST(self):
                    self.dynamic("POST")

                def dynamic(self, method):
                    body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                    headers = {"HTTP_HOST": self.headers["Host"]}
                    for name in ("X-CSRFToken", "Origin", "Referer"):
                        if self.headers.get(name):
                            headers["HTTP_"+name.upper().replace("-", "_")] = self.headers[name]
                    response = database.submit(client.generic, method, self.path, data=body,
                        content_type=self.headers.get("Content-Type", "application/octet-stream"), **headers).result(timeout=10)
                    self.send_response(response.status_code)
                    self.send_header("Content-Type", response.get("Content-Type", "text/html"))
                    self.end_headers()
                    self.wfile.write(response.content)

            server.RequestHandlerClass = Handler
            with patch("league.vegas_rules.outcome", side_effect=lambda bet, **kw: original(bet, choice=random.Random(42).choice, **kw)):
                ready.set()
                server.serve_forever(poll_interval=.1)
        except Exception as error:
            errors.append(error)
            ready.set()

    with override_settings(ALLOWED_HOSTS=["127.0.0.1", "testserver"], VEGAS_LAB_MIN_INTERVAL=0,
            STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                      "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}):
        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        assert ready.wait(15), "Server initialization timed out"
        assert not errors, errors
        try:
            with sync_playwright() as p:
                browser = getattr(p, engine).launch()
                context = browser.new_context(reduced_motion="reduce")
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("dialog", lambda dialog: dialog.accept())
                base = f"http://127.0.0.1:{server.server_port}/arcade/lab/vegas/"
                for width, height in ((320, 568), (320, 740), (390, 844), (844, 390), (1280, 720), (1440, 1050)):
                    page.set_viewport_size({"width": width, "height": height})
                    page.goto(base)
                    expect(page.locator(".vegas-cell")).to_have_count(20)
                    expect(page.locator("#vegas-line-picker button")).to_have_count(40)
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (engine, width, "overflow")
                    expect(page.locator("#vegas-spin")).to_be_enabled()
                    page.locator("#vegas-fullscreen").click()
                    page.wait_for_timeout(150)
                    box = page.locator("#vegas-page").bounding_box()
                    assert abs(box["width"]-width) <= 1 and abs(box["height"]-height) <= 1, box
                    spin = page.locator("#vegas-spin").bounding_box()
                    assert spin["y"] >= 0 and spin["y"]+spin["height"] <= height, (engine, width, height, spin)
                    board = page.locator("#vegas-board").bounding_box()
                    assert abs(board["width"]/board["height"]-1.25) < .01, board
                    expect(page.locator("#vegas-minus")).to_have_css("min-height", "44px")
                    if width in (390, 844, 1280):
                        page.screenshot(path=str(output/f"{engine}-{width}-fullscreen.png"))
                    if width in (390, 844):
                        # Synthetic safe-area padding also exercises the viewport fitter.
                        page.locator("#vegas-page").evaluate("el=>{el.style.padding='20px 16px 24px';dispatchEvent(new Event('resize'))}")
                        page.wait_for_timeout(150)
                        safe_spin = page.locator("#vegas-spin").bounding_box()
                        assert safe_spin["y"] >= 20 and safe_spin["y"]+safe_spin["height"] <= height-24, safe_spin
                        page.locator("#vegas-page").evaluate("el=>{el.style.removeProperty('padding');dispatchEvent(new Event('resize'))}")
                        page.wait_for_timeout(100)
                    page.keyboard.press("Escape")
                    expect(page.locator("#vegas-page")).not_to_have_class("vegas-page is-fullscreen")
                    if width in (390, 1440):
                        page.screenshot(path=str(output/f"{engine}-{width}-idle.png"), full_page=True)
                page.locator(".vegas-lab-tools > summary").click()
                page.locator("#vegas-reset").click()
                expect(page.locator("#vegas-message")).to_contain_text("сброшен")
                page.locator("#vegas-scenario").select_option("bonus")
                page.locator("#vegas-spin").click()
                expect(page.locator("#vegas-celebration")).to_be_visible(timeout=20000)
                expect(page.locator("#vegas-celebration-value")).to_contain_text("FREE SPINS")
                page.screenshot(path=str(output/f"{engine}-bonus.png"), full_page=True)
                page.locator("#vegas-celebration-close").click()
                expect(page.locator("#vegas-spin")).to_be_enabled()
                expect(page.locator("#vegas-plus")).to_be_disabled()
                expect(page.locator("#vegas-spin span")).to_have_text("FREE SPIN")
                free_before = page.locator("#vegas-free").inner_text()
                page.reload()
                expect(page.locator("#vegas-free")).to_have_text(free_before)
                page.locator(".vegas-lab-tools > summary").click()
                page.locator("#vegas-scenario").select_option("bigwin")
                page.locator("#vegas-spin").click()
                expect(page.locator("#vegas-celebration")).to_be_visible(timeout=20000)
                page.locator("#vegas-celebration-close").click()
                expect(page.locator("#vegas-spin")).to_be_enabled()
                expect(page.locator("#vegas-result-log")).to_contain_text("ПРИНУДИТЕЛЬНЫЙ ТЕСТ")
                expect(page.locator("#vegas-fx")).to_have_attribute("data-active", "false")
                page.emulate_media(reduced_motion="no-preference")
                page.set_viewport_size({"width": 390, "height": 844})
                page.locator("#vegas-scenario").select_option("wild")
                page.locator("#vegas-spin").click()
                expect(page.locator("#vegas-lines polyline")).to_be_visible(timeout=10000)
                expect(page.locator("#vegas-fx")).to_have_attribute("data-active", "true")
                expect(page.locator("#vegas-fx")).to_have_attribute("data-effect", "electric")
                page.wait_for_function("(()=>{const c=document.querySelector('#vegas-fx');return c.getContext('2d').getImageData(0,0,c.width,c.height).data.some((v,i)=>i%4===3&&v>0)})()")
                page.screenshot(path=str(output/f"{engine}-390-winning-line.png"), full_page=True)
                expect(page.locator("#vegas-spin")).to_be_enabled(timeout=20000)
                expect(page.locator("#vegas-fx")).to_have_attribute("data-active", "false", timeout=2000)
                page.locator("#vegas-effects").click()
                expect(page.locator("#vegas-effects")).to_have_attribute("aria-pressed", "false")
                page.locator("#vegas-effects").click()
                page.locator("#vegas-scenario").select_option("bigwin")
                page.locator("#vegas-spin").click()
                expect(page.locator("#vegas-fx")).to_have_attribute("data-effect", "fire", timeout=10000)
                expect(page.locator("#vegas-celebration")).to_be_visible(timeout=20000)
                page.locator("#vegas-celebration-close").click()
                expect(page.locator("#vegas-spin")).to_be_enabled()
                expect(page.locator("#vegas-fx")).to_have_attribute("data-active", "false", timeout=2000)
                page.emulate_media(reduced_motion="reduce")
                # A lost response AFTER the real server commits must retry the same request.
                request_ids = []
                def lost_response(route):
                    request_ids.append(route.request.post_data_json["request_id"])
                    route.fetch()
                    route.abort()
                page.route("**/arcade/lab/vegas/spin/", lost_response, times=1)
                page.locator("#vegas-spin").click()
                expect(page.locator("#vegas-spin span")).to_have_text("ПОВТОРИТЬ", timeout=15000)
                def retry(route):
                    request_ids.append(route.request.post_data_json["request_id"])
                    route.continue_()
                page.route("**/arcade/lab/vegas/spin/", retry, times=1)
                page.locator("#vegas-spin").click()
                expect(page.locator("#vegas-spin")).to_be_enabled(timeout=20000)
                assert len(request_ids) == 2 and request_ids[0] == request_ids[1], request_ids
                assert not errors, errors
                print(f"{engine}: mobile/desktop geometry, fullscreen, bonus, Wild, reload and idempotent network retry OK")
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=3)
            database.shutdown(wait=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("chromium", "webkit"), default="chromium")
    parser.add_argument("--output", type=Path, default=Path("/tmp/fastlap-vegas-browser"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    run(args.engine, args.output)
