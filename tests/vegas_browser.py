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


def run(engine, output, cdn_dir=None):
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
            with patch("league.vegas_rules.outcome", side_effect=lambda bet, **kw: original(bet, choice=random.Random(1 if kw.get("free") else 42).choice, **kw)):
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
                context.add_init_script("""(()=>{const Audio=window.AudioContext||window.webkitAudioContext;if(!Audio)return;const create=Audio.prototype.createOscillator;Audio.prototype.createOscillator=function(...args){const o=create.apply(this,args),start=o.start;o.start=function(...args){window.vegasNotesStarted=(window.vegasNotesStarted||0)+1;return start.apply(this,args)};return o}})()""")
                if cdn_dir:
                    # Optional exact upstream Bootstrap files for environments where
                    # WebKit cannot reach jsDelivr. Do not replace them with stubs.
                    for name, kind in (("bootstrap.min.css", "text/css"), ("bootstrap.bundle.min.js", "application/javascript")):
                        folder = "css" if name.endswith(".css") else "js"
                        url = f"https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/{folder}/{name}"
                        body = (cdn_dir/name).read_bytes()
                        context.route(url, lambda route, request, body=body, kind=kind: route.fulfill(body=body, content_type=kind))
                    # Keep local geometry/gameplay tests independent of Google Fonts;
                    # the production font stacks provide matching system fallbacks.
                    context.route("https://fonts.googleapis.com/**", lambda route: route.abort())
                    context.route("https://fonts.gstatic.com/**", lambda route: route.abort())
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("dialog", lambda dialog: dialog.accept())
                outstanding = set()
                page.on("request", lambda request: outstanding.add(request.url))
                page.on("requestfinished", lambda request: outstanding.discard(request.url))
                page.on("requestfailed", lambda request: outstanding.discard(request.url))
                base = f"http://127.0.0.1:{server.server_port}/arcade/lab/vegas/"
                spin_requests = []
                page.on("request", lambda request: spin_requests.append(request.post_data_json)
                        if urlsplit(request.url).path == "/arcade/lab/vegas/spin/" else None)
                page.goto(base)
                expect(page.locator("#vegas-spin")).to_be_enabled()
                assert page.evaluate("document.activeElement === document.body"), "Fresh page must not require a click"
                with page.expect_request("**/arcade/lab/vegas/spin/"):
                    page.keyboard.press("Space")
                expect(page.locator("#vegas-spin")).to_be_enabled(timeout=20000)
                assert len(spin_requests) == 1 and spin_requests[-1]["bet"] == 5000
                # Space on another focused control spins once without its native click.
                page.locator("#vegas-plus").focus()
                with page.expect_request("**/arcade/lab/vegas/spin/"):
                    page.keyboard.down("Space")
                    page.keyboard.down("Space")
                    page.keyboard.up("Space")
                expect(page.locator("#vegas-spin")).to_be_enabled(timeout=20000)
                assert len(spin_requests) == 2 and spin_requests[-1]["bet"] == 5000
                for width, height in ((320, 568), (320, 740), (390, 844), (667, 375), (844, 390), (1280, 720), (1440, 1050)):
                    page.set_viewport_size({"width": width, "height": height})
                    try:
                        page.goto(base)
                    except Exception:
                        print(f"{engine} {width}×{height}: unfinished page requests: {sorted(outstanding)}", flush=True)
                        raise
                    expect(page.locator(".vegas-cell")).to_have_count(20)
                    expect(page.locator(".vegas-rules,#vegas-result-log,#vegas-line-picker")).to_have_count(0)
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (engine, width, "overflow")
                    expect(page.locator("#vegas-spin")).to_be_enabled()
                    page.locator("#vegas-fullscreen").click()
                    page.wait_for_timeout(150)
                    box = page.locator("#vegas-page").bounding_box()
                    assert abs(box["width"]-width) <= 1 and abs(box["height"]-height) <= 1, box
                    spin = page.locator("#vegas-spin").bounding_box()
                    if spin["y"]+spin["height"] > height:
                        page.screenshot(path=str(output/f"{engine}-layout-failure.png"), full_page=True)
                        print(page.locator("#vegas-machine").evaluate("el=>({style:el.getAttribute('style'),classes:el.className,parts:[...el.querySelectorAll('.vegas-marquee,.vegas-bonus-hud,.vegas-stage,.vegas-console,.vegas-board-frame,.vegas-buy')].map(n=>({cls:n.className,hidden:n.hidden,display:getComputedStyle(n).display,rect:n.getBoundingClientRect().toJSON()}))})"), flush=True)
                        print(errors, flush=True)
                    assert spin["y"] >= 0 and spin["y"]+spin["height"] <= height, (engine, width, height, spin)
                    label = page.locator("#vegas-spin span").bounding_box()
                    assert label["x"]-spin["x"] >= 8 and spin["x"]+spin["width"]-label["x"]-label["width"] >= 8, (engine, width, "spin label inset", label)
                    board = page.locator("#vegas-board").bounding_box()
                    assert abs(board["width"]/board["height"]-1.25) < .01, board
                    deck = page.locator(".vegas-console").bounding_box()
                    assert deck["y"] >= board["y"]+board["height"], (engine, width, "controls must stay below reels")
                    assert page.locator('.vegas-cell:not([data-symbol="wild"]):not([data-symbol="scatter"]) small:visible').count() == 0
                    expected_background = "strip-mobile-v3.png" if width <= 700 else "strip-v3.png"
                    assert expected_background in page.locator(".vegas-night").evaluate("el=>getComputedStyle(el).backgroundImage")
                    expect(page.locator("#vegas-minus")).to_have_css("min-height", "44px")
                    buy = page.locator("#vegas-buy").bounding_box()
                    assert 0 <= buy["x"] and buy["x"]+buy["width"] <= width, buy
                    assert 0 <= buy["y"] and buy["y"]+buy["height"] <= height, buy
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
                    before = len(spin_requests)
                    page.locator("#vegas-buy").click()
                    expect(page.locator("#vegas-purchase")).to_be_visible()
                    expect(page.locator("#vegas-purchase-cancel")).to_be_focused()
                    modal = page.locator("#vegas-purchase").bounding_box()
                    assert modal["height"] <= height-28 and modal["width"] <= width, modal
                    if width in (390, 1280):
                        page.screenshot(path=str(output/f"{engine}-{width}-purchase.png"))
                    page.keyboard.press("Space" if width == 320 else "Escape")
                    expect(page.locator("#vegas-purchase")).not_to_be_visible()
                    expect(page.locator("#vegas-page")).to_have_class("vegas-page is-fullscreen")
                    assert len(spin_requests) == before, "Cancel must not submit or spin"
                    page.keyboard.press("Escape")
                    expect(page.locator("#vegas-page")).not_to_have_class("vegas-page is-fullscreen")
                    if width in (390, 1440):
                        page.screenshot(path=str(output/f"{engine}-{width}-idle.png"), full_page=True)
                page.locator(".vegas-lab-tools > summary").click()
                page.locator("#vegas-reset").click()
                expect(page.locator("#vegas-message")).to_contain_text("сброшен")
                # Walk the complete expanded stake range, then return to $50.
                stakes = page.locator("#vegas-config").evaluate("el=>JSON.parse(el.textContent).bets")
                for _ in range(stakes.index(5000)):
                    page.locator("#vegas-minus").click()
                expect(page.locator("#vegas-minus")).to_be_disabled()
                for i in range(len(stakes)-1):
                    page.locator("#vegas-plus").click()
                expect(page.locator("#vegas-plus")).to_be_disabled()
                for _ in range(len(stakes)-1-stakes.index(5000)):
                    page.locator("#vegas-minus").click()
                # Native Space in a select must not spend a stake.
                page.locator("#vegas-scenario").focus()
                before = len(spin_requests)
                page.keyboard.press("Space")
                page.keyboard.press("Escape")
                page.wait_for_timeout(100)
                assert len(spin_requests) == before
                # High stake purchase needs the full price, not just the spin stake.
                for _ in range(len(stakes)-1-stakes.index(5000)):
                    page.locator("#vegas-plus").click()
                expect(page.locator("#vegas-buy")).to_be_disabled()
                expect(page.locator("#vegas-buy-note")).to_contain_text("НЕДОСТАТОЧНО")
                for _ in range(len(stakes)-1-stakes.index(5000)):
                    page.locator("#vegas-minus").click()
                # Purchase accepted on server, response lost: same UUID must recover it.
                purchase_ids = []
                def lost_purchase(route):
                    purchase_ids.append(route.request.post_data_json["request_id"])
                    route.fetch()
                    route.abort()
                page.route("**/arcade/lab/vegas/spin/", lost_purchase, times=1)
                page.locator("#vegas-buy").click()
                page.locator("#vegas-purchase-confirm").click()
                expect(page.locator("#vegas-spin span")).to_have_text("ПОВТОРИТЬ", timeout=15000)
                expect(page.locator("#vegas-buy-label")).to_contain_text("ПОВТОРИТЬ")
                def retry_purchase(route):
                    purchase_ids.append(route.request.post_data_json["request_id"])
                    assert route.request.post_data_json["action"] == "buy_bonus"
                    route.continue_()
                page.route("**/arcade/lab/vegas/spin/", retry_purchase, times=1)
                page.locator("#vegas-buy").click()
                expect(page.locator("#vegas-celebration")).to_be_visible(timeout=15000)
                expect(page.locator("#vegas-celebration-value")).to_have_text("10 FREE SPINS")
                assert len(purchase_ids) == 2 and purchase_ids[0] == purchase_ids[1]
                # Dismiss entry, then pause while the first automatic free spin runs.
                with page.expect_request("**/arcade/lab/vegas/spin/"):
                    page.keyboard.press("Space")
                page.locator("#vegas-bonus-pause").click()
                expect(page.locator("#vegas-spin")).to_be_enabled(timeout=15000)
                expect(page.locator("#vegas-bonus-pause")).to_have_attribute("aria-pressed", "true")
                expect(page.locator("#vegas-free")).to_have_text("9")
                expect(page.locator("#vegas-bonus-total")).to_have_attribute("data-value", "4000")
                count_paused = len(spin_requests)
                page.wait_for_timeout(400)
                assert len(spin_requests) == count_paused, "Pause must stop the next spin"
                for width, height in ((320, 568), (390, 844), (667, 375), (844, 390), (1280, 720)):
                    page.set_viewport_size({"width": width, "height": height})
                    page.locator("#vegas-fullscreen").click()
                    page.wait_for_timeout(100)
                    spin_box = page.locator("#vegas-spin").bounding_box()
                    assert spin_box["y"]+spin_box["height"] <= height, (engine, "bonus viewport", width, spin_box)
                    expect(page.locator("#vegas-bonus-total")).to_have_attribute("data-value", "4000")
                    if width in (390, 1280):
                        page.screenshot(path=str(output/f"{engine}-{width}-bonus-running.png"))
                    page.keyboard.press("Escape")
                page.set_viewport_size({"width": 1440, "height": 1050})
                # Simulate a background document: resuming must not send a request.
                page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'))")
                page.locator("#vegas-bonus-pause").click()
                page.wait_for_timeout(400)
                assert len(spin_requests) == count_paused, "Hidden tab must not spin"
                page.locator("#vegas-bonus-pause").click()
                page.evaluate("delete document.hidden;document.dispatchEvent(new Event('visibilitychange'))")
                # Reload resumes automatically. Lose the first response AFTER commit.
                auto_retry_ids = []
                def lose_free(route):
                    auto_retry_ids.append(route.request.post_data_json["request_id"])
                    route.fetch()
                    route.abort()
                page.route("**/arcade/lab/vegas/spin/", lose_free, times=1)
                page.reload()
                expect(page.locator("#vegas-buy")).to_be_disabled()
                expect(page.locator("#vegas-plus")).to_be_disabled()
                restored = page.locator("#vegas-config").evaluate("el=>JSON.parse(el.textContent)")
                assert restored["state"]["balance"] == 404000
                assert restored["state"]["bonus"] == {"win": 4000, "played": 1, "granted": 10}
                expect(page.locator("#vegas-spin span")).to_have_text("ПОВТОРИТЬ", timeout=15000)
                failed_count = len(spin_requests)
                page.wait_for_timeout(400)
                assert len(spin_requests) == failed_count, "Network error must not loop requests"
                def retry_free(route):
                    auto_retry_ids.append(route.request.post_data_json["request_id"])
                    route.continue_()
                page.route("**/arcade/lab/vegas/spin/", retry_free, times=1)
                page.keyboard.press("Space")
                expect(page.locator('#vegas-celebration[data-kind="summary"]')).to_be_visible(timeout=30000)
                assert auto_retry_ids[0] == auto_retry_ids[1]
                expect(page.locator("#vegas-free")).to_have_text("0")
                expect(page.locator("#vegas-bonus-total")).to_have_attribute("data-value", "40000")
                expect(page.locator("#vegas-bonus-progress")).to_contain_text("10 / 10")
                assert page.evaluate("window.vegasNotesStarted > 0"), "Real audio nodes must play after user interaction"
                page.screenshot(path=str(output/f"{engine}-bonus-summary.png"), full_page=True)
                finished_count = len(spin_requests)
                page.keyboard.press("Space")
                page.wait_for_timeout(450)
                assert len(spin_requests) == finished_count, "Auto must never spend on a paid spin"
                page.reload()
                ended = page.locator("#vegas-config").evaluate("el=>JSON.parse(el.textContent).state")
                assert ended["balance"] == 440000 and ended["bonus"]["win"] == 40000
                page.locator(".vegas-lab-tools > summary").click()
                page.locator("#vegas-reset").click()
                expect(page.locator("#vegas-message")).to_contain_text("сброшен")
                page.locator("#vegas-scenario").select_option("bonus")
                page.locator("#vegas-spin").click()
                expect(page.locator("#vegas-celebration")).to_be_visible(timeout=20000)
                expect(page.locator("#vegas-celebration-value")).to_contain_text("FREE SPINS")
                page.screenshot(path=str(output/f"{engine}-bonus.png"), full_page=True)
                # Natural bonus entry and all free spins close/run without a click.
                expect(page.locator('#vegas-celebration[data-kind="summary"]')).to_be_visible(timeout=30000)
                expect(page.locator("#vegas-bonus-progress")).to_contain_text("8 / 8")
                expect(page.locator("#vegas-bonus-total")).to_have_attribute("data-value", "32000")
                page.keyboard.press("Space")
                page.locator("#vegas-scenario").select_option("bigwin")
                page.locator("#vegas-spin").click()
                expect(page.locator("#vegas-celebration")).to_be_visible(timeout=20000)
                page.locator("#vegas-celebration-close").click()
                expect(page.locator("#vegas-spin")).to_be_enabled()
                expect(page.locator("#vegas-result-log")).to_have_count(0)
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
                page.locator("#vegas-sound").click()
                expect(page.locator("#vegas-sound")).to_have_attribute("aria-pressed", "false")
                notes_before = page.evaluate("window.vegasNotesStarted || 0")
                page.locator("#vegas-scenario").select_option("bigwin")
                page.locator("#vegas-spin").click()
                expect(page.locator("#vegas-fx")).to_have_attribute("data-effect", "fire", timeout=10000)
                expect(page.locator("#vegas-celebration")).to_be_visible(timeout=20000)
                page.locator("#vegas-celebration-close").click()
                expect(page.locator("#vegas-spin")).to_be_enabled()
                assert page.evaluate("window.vegasNotesStarted || 0") == notes_before, "Mute must suppress all new sound nodes"
                page.locator("#vegas-sound").click()
                expect(page.locator("#vegas-sound")).to_have_attribute("aria-pressed", "true")
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
                print(f"{engine}: responsive UI, automatic bonus totals, pause/background/reload, bonus and spin retries, audio/mute and FX OK")
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
    parser.add_argument("--cdn-dir", type=Path, help="Optional directory with the exact Bootstrap 5.3.3 CSS and bundle from jsDelivr")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    run(args.engine, args.output, args.cdn_dir)
