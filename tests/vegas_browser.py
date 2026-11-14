"""End-to-end staff sandbox with synthetic users, in-memory DB and real APIs."""
import argparse
import json
import re
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
    topup_fixture = {}

    def serve():
        try:
            def initialize():
                call_command("migrate", verbosity=0, interactive=False)
                user, _ = User.objects.get_or_create(username=f"vegas-browser-{engine}", defaults={"is_staff": True})
                client = Client(enforce_csrf_checks=True)
                client.force_login(user)
                from league.models import VegasLabWallet
                rival = User.objects.create_user(username=f"vegas-rival-{engine}", first_name="Соперник")
                public_client = Client(enforce_csrf_checks=True)
                public_client.force_login(rival)
                topup_fixture["public"] = public_client
                VegasLabWallet.objects.create(user=rival, balance=600000)
                from datetime import timedelta
                from django.urls import reverse
                from django.utils import timezone
                from league.models import Season, Event, RaceCalendarRound
                from league.leagues import create_league, enroll_member
                now = timezone.now()
                owner = User.objects.create_user(username=f"vegas-owner-{engine}")
                owner_client = Client(enforce_csrf_checks=True)
                owner_client.force_login(owner)
                season = Season.objects.create(year=2094)
                event = Event.objects.create(name="Тестовый этап додепа", season_year=2094, round_number=1,
                    deadline=now+timedelta(hours=1), race_datetime=now+timedelta(hours=6))
                league = create_league(owner=owner, name="Тестовая лига", season=season, start_event=event, ruleset="paddock")
                enroll_member(actor=owner, league_season=league, user=user)
                calendar = RaceCalendarRound.objects.create(season_year=2094, round_number=1, circuit="vegas", title="Тестовый этап",
                    location="Test", country="Test", circuit_name="Test", starts_on=now.date(), ends_on=(now+timedelta(days=1)).date(),
                    practice1_at=now+timedelta(hours=3), race_at=event.race_datetime, prediction_event=event)
                topup_fixture.update(owner=owner_client, calendar_id=calendar.pk,
                    manage_url=reverse("league:friend_league_event", args=[league.league_id,event.pk])+"?manage=1")
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
                    # Synthetic owner session for the second test tab only.
                    selected_client = topup_fixture["owner"] if self.headers.get("X-Test-League-Owner") == "yes" else client
                    if self.headers.get("X-Test-Public-Player") == "yes":
                        selected_client = topup_fixture["public"]
                    response = database.submit(selected_client.generic, method, self.path, data=body,
                        content_type=self.headers.get("Content-Type", "application/octet-stream"), **headers).result(timeout=10)
                    self.send_response(response.status_code)
                    self.send_header("Content-Type", response.get("Content-Type", "text/html"))
                    if response.get("Location"):
                        self.send_header("Location", response["Location"])
                    self.end_headers()
                    self.wfile.write(response.content)

            server.RequestHandlerClass = Handler
            def topup_round(now):
                from league.models import RaceCalendarRound
                return RaceCalendarRound.objects.select_related("prediction_event").get(pk=topup_fixture["calendar_id"])
            with patch("league.vegas_topup.current_round", side_effect=topup_round), patch("league.vegas_rules.outcome", side_effect=lambda bet, **kw: original(bet, choice=random.Random(1 if kw.get("free") else 42).choice, **kw)):
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
                context.add_init_script("""(()=>{const original=requestAnimationFrame;window.requestAnimationFrame=callback=>original.call(window,time=>{window.vegasRafCallbacks=(window.vegasRafCallbacks||0)+1;callback(time)})})()""")
                context.add_init_script("""(()=>{const Audio=window.AudioContext||window.webkitAudioContext;if(!Audio)return;const create=Audio.prototype.createOscillator;Audio.prototype.createOscillator=function(...args){const o=create.apply(this,args),start=o.start;o.start=function(...args){window.vegasNotesStarted=(window.vegasNotesStarted||0)+1;return start.apply(this,args)};return o}})()""")
                context.add_init_script("""(()=>{const Audio=window.AudioContext||window.webkitAudioContext;if(!Audio)return;const create=Audio.prototype.createBufferSource;Audio.prototype.createBufferSource=function(...args){const source=create.apply(this,args),start=source.start;source.start=function(...args){window.vegasMusicStarts=(window.vegasMusicStarts||0)+1;window.vegasMusicSource=source;return start.apply(this,args)};return source}})()""")
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
                ordinary_geometry = {}
                page.on("request", lambda request: spin_requests.append(request.post_data_json)
                        if urlsplit(request.url).path == "/arcade/lab/vegas/spin/" else None)
                page.goto(base)
                expect(page.locator("#vegas-spin")).to_be_enabled()
                expect(page.locator("#vegas-balances-status")).to_have_text("Сейчас")
                expect(page.locator("#vegas-balances-list li")).to_have_count(2)
                def update_rival():
                    from league.models import VegasLabWallet
                    VegasLabWallet.objects.filter(user__username=f"vegas-rival-{engine}").update(balance=654321)
                database.submit(update_rival).result(timeout=5)
                page.evaluate("dispatchEvent(new PageTransitionEvent('pageshow'))")
                expect(page.locator("#vegas-balances-list li:not(.is-you) strong")).to_have_text("6\u00a0543,21\u00a0$")
                assert page.evaluate("document.activeElement === document.body"), "Fresh page must not require a click"
                page.evaluate("window.vegasInitialCells=[...document.querySelectorAll('.vegas-cell')]")
                with page.expect_request("**/arcade/lab/vegas/spin/"):
                    page.keyboard.press("Space")
                expect(page.locator("#vegas-spin")).to_be_enabled(timeout=20000)
                assert len(spin_requests) == 1 and spin_requests[-1]["bet"] == 5000
                expect(page.locator("#vegas-balances-list .is-you strong")).to_have_text(page.locator("#vegas-balance").inner_text())
                # Space on another focused control spins once without its native click.
                page.locator("#vegas-plus").focus()
                with page.expect_request("**/arcade/lab/vegas/spin/"):
                    page.keyboard.down("Space")
                    page.keyboard.down("Space")
                    page.keyboard.up("Space")
                expect(page.locator("#vegas-spin")).to_be_enabled(timeout=20000)
                assert len(spin_requests) == 2 and spin_requests[-1]["bet"] == 5000
                assert page.evaluate("[...document.querySelectorAll('.vegas-cell')].every((el,i)=>el===vegasInitialCells[i])"), "Spins must reuse existing cell nodes"
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
                    page.wait_for_timeout(150)
                    inline_machine = page.locator("#vegas-machine").bounding_box()
                    bottom_nav = page.locator(".nightshift-mobile-nav").bounding_box()
                    bottom_inset = bottom_nav["height"] if bottom_nav else 0
                    if inline_machine["y"]+inline_machine["height"] > height-bottom_inset+2:
                        page.screenshot(path=str(output/f"{engine}-inline-failure.png"), full_page=True)
                        print(page.locator("#vegas-machine").evaluate("el=>({style:el.getAttribute('style'),parts:[...el.querySelectorAll('.vegas-toolbar,.vegas-marquee,.vegas-announcer,.vegas-console,.vegas-stage,.vegas-buy')].map(n=>({cls:n.className,rect:n.getBoundingClientRect().toJSON()}))})"),flush=True)
                    assert inline_machine["y"]+inline_machine["height"] <= height-bottom_inset+2, (engine,width,height,"inline cabinet must fit",inline_machine,bottom_inset)
                    inline_board = page.locator("#vegas-board").bounding_box()
                    page.set_viewport_size({"width": width, "height": height+80})
                    page.wait_for_timeout(100)
                    assert abs(page.locator("#vegas-board").bounding_box()["width"]-inline_board["width"]) < 1, "Browser toolbar must not resize inline reels"
                    page.set_viewport_size({"width": width, "height": height})
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
                    ordinary_geometry[(width, height)] = board
                    assert abs(board["width"]/board["height"]-1.25) < .01, board
                    deck = page.locator(".vegas-console").bounding_box()
                    assert deck["y"] >= board["y"]+board["height"], (engine, width, "controls must stay below reels")
                    assert page.locator('.vegas-cell:not([data-symbol="wild"]):not([data-symbol="scatter"]) small:visible').count() == 0
                    mobile_scene = width <= 700 or page.evaluate("matchMedia('(hover:none) and (pointer:coarse)').matches")
                    expected_background = "strip-city-mobile-v2-web.webp" if mobile_scene else "strip-helmet-v2-web.webp"
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
                before_launch = len(spin_requests)
                page.goto(base+"?fullscreen=1")
                expect(page.locator("#vegas-fullscreen")).to_have_attribute("aria-pressed", "true")
                expect(page.locator("#vegas-fullscreen")).not_to_be_visible()
                expect(page.locator("#vegas-exit")).to_have_text("Все аркады")
                page.locator("#vegas-exit").click()
                expect(page.locator(".arcade-library")).to_be_visible()
                assert len(spin_requests) == before_launch, "Fullscreen launch must not spend or spin"
                page.goto(base)
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
                expect(page.locator("#vegas-bonus-total")).to_have_attribute("data-value", "5000")
                count_paused = len(spin_requests)
                page.wait_for_timeout(400)
                assert len(spin_requests) == count_paused, "Pause must stop the next spin"
                for width, height in ((320, 568), (390, 844), (667, 375), (844, 390), (1280, 720)):
                    page.set_viewport_size({"width": width, "height": height})
                    page.locator("#vegas-fullscreen").click()
                    page.wait_for_timeout(100)
                    bonus_board = page.locator("#vegas-board").bounding_box()
                    ordinary_board = ordinary_geometry[(width, height)]
                    assert all(abs(bonus_board[key]-ordinary_board[key]) <= 1 for key in ("width", "height")), (engine, "bonus resized reels", width, ordinary_board, bonus_board)
                    spin_box = page.locator("#vegas-spin").bounding_box()
                    assert spin_box["y"]+spin_box["height"] <= height, (engine, "bonus viewport", width, spin_box)
                    expect(page.locator("#vegas-bonus-total")).to_have_attribute("data-value", "5000")
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
                assert restored["state"]["balance"] == 405000
                assert restored["state"]["bonus"] == {"win": 5000, "played": 1, "granted": 10, "minimum_return": 50000}
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
                expect(page.locator("#vegas-bonus-total")).to_have_attribute("data-value", "50000")
                expect(page.locator("#vegas-bonus-progress")).to_contain_text("10 / 10")
                assert page.evaluate("window.vegasNotesStarted > 0"), "Real audio nodes must play after user interaction"
                page.screenshot(path=str(output/f"{engine}-bonus-summary.png"), full_page=True)
                finished_count = len(spin_requests)
                page.keyboard.press("Space")
                page.wait_for_timeout(450)
                assert len(spin_requests) == finished_count, "Auto must never spend on a paid spin"
                page.reload()
                ended = page.locator("#vegas-config").evaluate("el=>JSON.parse(el.textContent).state")
                assert ended["balance"] == 450000 and ended["bonus"]["win"] == 50000
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
                expect(page.locator("#vegas-bonus-total")).to_have_attribute("data-value", "40000")
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
                expect(page.locator("#vegas-machine")).to_have_attribute("data-music", "playing")
                music_starts = page.evaluate("vegasMusicStarts")
                assert page.evaluate("vegasMusicSource.loop && vegasMusicSource.buffer.duration > 15")
                page.evaluate("window.vegasWinEffects=[];new MutationObserver(()=>vegasWinEffects.push(document.getElementById('vegas-fx').dataset.effect)).observe(document.getElementById('vegas-fx'),{attributes:true,attributeFilter:['data-effect']})")
                page.locator("#vegas-scenario").select_option("wild")
                page.locator("#vegas-spin").click()
                expect(page.locator("#vegas-lines polyline")).to_be_visible(timeout=10000)
                expect(page.locator("#vegas-fx")).to_have_attribute("data-active", "false")
                page.screenshot(path=str(output/f"{engine}-390-winning-line.png"), full_page=True)
                expect(page.locator("#vegas-spin")).to_be_enabled(timeout=20000)
                assert page.evaluate("!vegasWinEffects.includes('electric')"), "Winning lines and cascades must not draw blue waves"
                expect(page.locator("#vegas-fx")).to_have_attribute("data-active", "false", timeout=2000)
                expect(page.locator("#vegas-effects,#vegas-sound")).to_have_count(0)
                notes_before = page.evaluate("window.vegasNotesStarted || 0")
                page.locator("#vegas-scenario").select_option("bigwin")
                page.locator("#vegas-spin").click()
                expect(page.locator("#vegas-fx")).to_have_attribute("data-effect", "fire", timeout=10000)
                expect(page.locator("#vegas-celebration")).to_be_visible(timeout=20000)
                page.locator("#vegas-celebration-close").click()
                expect(page.locator("#vegas-spin")).to_be_enabled()
                assert page.evaluate("window.vegasNotesStarted || 0") > notes_before, "Win sound should remain enabled"
                assert page.evaluate("vegasMusicStarts") == music_starts, "Wins must not restart the music buffer"
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
                # Paid auto must issue sequential requests and stop without an extra debit.
                before_auto = len(spin_requests)
                page.locator("#vegas-auto").click()
                expect(page.locator("#vegas-auto-dialog")).to_be_visible()
                assert len(spin_requests) == before_auto, "Choosing a series must not spin"
                page.locator('[data-auto-count="25"]').click()
                page.locator("#vegas-auto-start").click()
                expect(page.locator("#vegas-auto")).to_have_attribute("aria-pressed", "true")
                for _ in range(100):
                    if len(spin_requests) >= before_auto+2:
                        break
                    page.wait_for_timeout(100)
                assert len(spin_requests) >= before_auto+2, "Auto should run multiple paid spins"
                page.locator("#vegas-auto").click()
                expect(page.locator("#vegas-auto")).to_have_attribute("aria-pressed", "false")
                expect(page.locator("#vegas-spin")).to_be_enabled(timeout=20000)
                stopped = len(spin_requests)
                page.wait_for_timeout(1200)
                assert len(spin_requests) == stopped, "Stop must prevent the next paid spin"
                # A fixed series completes exactly five paid requests, and
                # does not submit a sixth one after the counter reaches zero.
                before_fixed = len(spin_requests)
                page.locator("#vegas-auto").click()
                page.locator('[data-auto-count="5"]').click()
                page.locator("#vegas-auto-start").click()
                expect(page.locator("#vegas-auto")).to_have_attribute("aria-pressed", "false", timeout=30000)
                expect(page.locator("#vegas-spin")).to_be_enabled(timeout=20000)
                assert len(spin_requests) == before_fixed+5
                expect(page.locator("#vegas-message")).to_have_text("Серия из 5 вращений завершена")
                page.wait_for_timeout(1000)
                assert len(spin_requests) == before_fixed+5
                # Presentation-only fixture: isolate a low-value pepper win so
                # fire cannot be triggered by the generic large-win threshold.
                def pepper_response(route):
                    response = route.fetch()
                    data = response.json()
                    result = data["result"]
                    result.update(payout=100, awarded=0, free=False)
                    result["rounds"] = [{
                        "grid": [["toto", "tyre", "duck", "berry"] for _ in range(5)],
                        "multiplier": 1, "amount": 100,
                        "wins": [{"line": 1, "symbol": "toto", "count": 5, "rows": [0]*5,
                                  "cells": [[c, 0] for c in range(5)], "amount": 100}],
                    }]
                    route.fulfill(response=response, json=data)
                page.emulate_media(reduced_motion="no-preference")
                page.locator("#vegas-fullscreen").click()
                page.route("**/arcade/lab/vegas/spin/", pepper_response, times=1)
                page.locator("#vegas-spin").click()
                expect(page.locator("#vegas-fx")).to_have_attribute("data-effect", "fire", timeout=10000)
                expect(page.locator("#vegas-fx")).to_have_attribute("data-theme", "pepper")
                expect(page.locator("#vegas-callout-label")).to_have_text("ПЕРЧИК ЖЖЁТ!", timeout=10000)
                page.wait_for_timeout(200)
                page.screenshot(path=str(output/f"{engine}-pepper-win.png"), full_page=True)
                expect(page.locator("#vegas-spin")).to_be_enabled(timeout=20000)
                expect(page.locator("#vegas-fx")).to_have_attribute("data-active", "false", timeout=2000)
                assert int(page.locator("#vegas-fx").get_attribute("data-frames")) > 0
                page.wait_for_timeout(100)
                idle_frames = page.evaluate("vegasRafCallbacks")
                page.wait_for_timeout(350)
                assert page.evaluate("vegasRafCallbacks") == idle_frames, "FX must leave no idle animation loop"
                # Presentation-only near miss: two genuine stopped Scatter
                # columns keep later reels rolling, but submit no extra spins.
                def near_miss(route):
                    response = route.fetch()
                    data = response.json()
                    field = [["tyre", "duck", "berry", "banana"] for _ in range(5)]
                    field[0][0] = field[1][0] = "scatter"
                    data["result"].update(payout=0, awarded=0, free=False,
                        rounds=[{"grid": field, "wins": [], "amount": 0, "multiplier": 1}])
                    route.fulfill(response=response, json=data)
                before_near_miss = len(spin_requests)
                page.route("**/arcade/lab/vegas/spin/", near_miss, times=1)
                page.locator("#vegas-spin").click()
                expect(page.locator(".is-anticipating")).to_have_count(1)
                expect(page.locator("#vegas-message")).to_contain_text("Два Scatter")
                assert page.locator(".is-anticipating .vegas-reel-track").evaluate("el=>getComputedStyle(el).animationIterationCount==='infinite'")
                page.screenshot(path=str(output/f"{engine}-anticipation.png"))
                expect(page.locator("#vegas-spin")).to_be_enabled(timeout=20000)
                expect(page.locator(".is-anticipating")).to_have_count(0)
                assert len(spin_requests) == before_near_miss+1
                page.locator("#vegas-music").click()
                expect(page.locator("#vegas-machine")).to_have_attribute("data-music", "paused")
                page.locator("#vegas-music").click()
                expect(page.locator("#vegas-machine")).to_have_attribute("data-music", "playing")
                # Read-only shop uses the same wallet and offers all descriptions
                # without POSTs, on both the wide scene and narrow shelf layout.
                page.emulate_media(reduced_motion="reduce")
                page.locator("#vegas-shop").click()
                shop_box = page.locator("#casino-shop").bounding_box()
                assert abs(shop_box["width"]-page.viewport_size["width"]) <= 1 and abs(shop_box["height"]-page.viewport_size["height"]) <= 1
                expect(page.locator(".shop-masthead,#shop-title")).to_have_count(0)
                expect(page.get_by_role("region", name="Витрина товаров")).to_be_visible()
                expect(page.locator(".shop-product")).to_have_count(8)
                expect(page.locator(".shop-counter img")).to_have_attribute("src", "/static/league/images/vegas/shop-counter-v2.png")
                assert page.locator(".shop-counter").evaluate("el=>getComputedStyle(el).clipPath==='none' && getComputedStyle(el).backgroundImage==='none'"), "Counter must be independent alpha art, not a clipped copy of the room"
                shop_requests = len(spin_requests)
                for width, height in ((1440, 1050), (390, 844), (320, 568)):
                    page.set_viewport_size({"width": width, "height": height})
                    page.evaluate("scrollTo(0,0)")
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (engine, width, "shop overflow")
                    if width <= 700:
                        assert page.locator('.shop-shelves').evaluate('el=>el.scrollWidth>el.clientWidth'), "Mobile products must scroll horizontally"
                        center = page.locator('#shop-dealer').evaluate('el=>{const d=el.getBoundingClientRect(),s=el.closest(".shop-scene").getBoundingClientRect();return Math.abs(d.x+d.width/2-s.x-s.width/2)}')
                        assert center <= 1, "Mobile dealer must remain centered"
                    for item in ("wheel", "tyres", "redflag", "mirrors", "teamorder", "insurance", "constructors", "paddockpass"):
                        button = page.locator(f'[data-product="{item}"]')
                        button.scroll_into_view_if_needed()
                        # Read both boxes in the same layout frame: resizing
                        # the site's sidebar can still move the scene while
                        # product dialogs are opened and closed.
                        geometry = button.evaluate("el=>{const b=el.getBoundingClientRect(),s=el.closest('.shop-scene').getBoundingClientRect();return {left:b.left,right:b.right,sceneLeft:s.left,sceneRight:s.right}}")
                        if width <= 700:
                            # A neighboring item may intentionally peek from
                            # the clipped shelf; the target's center stays usable.
                            assert geometry["sceneLeft"] <= (geometry["left"]+geometry["right"])/2 <= geometry["sceneRight"], (width,item,"carousel target",geometry)
                        else:
                            assert geometry["left"] >= geometry["sceneLeft"] and geometry["right"] <= geometry["sceneRight"], (width,item,"shelf overflow",geometry)
                        button.click()
                        assert button.locator(".shop-price-tag").evaluate("el=>{const s=getComputedStyle(el);return s.borderRadius==='0px' && s.backgroundColor==='rgba(0, 0, 0, 0)'}"), "Prices must not sit in rounded pills"
                        expect(page.locator("#shop-product-dialog")).to_be_visible()
                        expect(page.locator("#shop-detail-name")).not_to_be_empty()
                        expect(page.locator("#shop-detail-description")).not_to_be_empty()
                        expect(page.locator("#shop-detail-price")).to_contain_text("$")
                        modal = page.locator("#shop-product-dialog").bounding_box()
                        assert modal["width"] <= width and modal["y"] >= 0 and modal["y"]+modal["height"] <= height, (width,"shop dialog overflow",modal)
                        if item == "paddockpass" and width == 390:
                            page.screenshot(path=str(output/f"{engine}-390-shop-detail.png"))
                        page.locator("#shop-done").click()
                        assert page.locator(".shop-scene").evaluate("el=>el.scrollLeft===0"), "Focusing a product must not pan the oversized foreground"
                    page.evaluate("scrollTo(0,0)")
                    page.locator(".shop-back").focus()
                    page.mouse.move(0, 0)
                    page.locator("#casino-shop").evaluate("el=>el.scrollTop=0")
                    page.screenshot(path=str(output/f"{engine}-{width}-shop.png"), full_page=True)
                page.set_viewport_size({"width":1440,"height":1050})
                # The counter clips only the vest; animation honors motion
                # preferences and stops behind product dialogs / offscreen.
                dealer = page.locator("#shop-dealer")
                expect(dealer).to_have_attribute("data-pose", "idle")
                expect(dealer).to_have_attribute("data-animating", "false")
                page.evaluate("window.shopPoses=[];new MutationObserver(()=>shopPoses.push(document.getElementById('shop-dealer').dataset.pose)).observe(document.getElementById('shop-dealer'),{attributes:true,attributeFilter:['data-pose']})")
                page.emulate_media(reduced_motion="no-preference")
                dealer.scroll_into_view_if_needed()
                expect(dealer).to_have_attribute("data-animating", "true")
                expect(dealer).to_have_attribute("data-pose", "greet", timeout=6000)
                assert page.locator(".shop-dealer-figure").evaluate("el=>getComputedStyle(el).transform==='none'"), "Greeting must not rotate the waist through the table"
                page.wait_for_function("shopPoses.includes('blink')", timeout=8000)
                expect(dealer).to_have_attribute("data-pose", "release", timeout=8000)
                page.wait_for_timeout(400)
                page.screenshot(path=str(output/f"{engine}-shop-chip-toss.png"), full_page=True)
                expect(dealer).to_have_attribute("data-pose", "idle", timeout=3000)
                page.wait_for_function("shopPoses.includes('catch')")
                page.locator('[data-product="constructors"]').hover()
                expect(page.locator("#shop-tooltip")).to_be_visible()
                expect(page.locator("#shop-tip-title")).to_have_text("Кубок конструкторов")
                page.locator('[data-product="constructors"]').click()
                expect(dealer).to_have_attribute("data-animating", "false")
                expect(dealer).to_have_attribute("data-pose", "idle")
                page.keyboard.press("Escape")
                expect(page.locator("#shop-product-dialog")).not_to_be_visible()
                expect(dealer).to_have_attribute("data-animating", "true")
                page.set_viewport_size({"width":390,"height":200})
                page.locator("#casino-shop").evaluate("el=>el.scrollTop=0")
                expect(dealer).to_have_attribute("data-animating", "false")
                dealer.scroll_into_view_if_needed()
                expect(dealer).to_have_attribute("data-animating", "true")
                page.emulate_media(reduced_motion="reduce")
                expect(dealer).to_have_attribute("data-animating", "false")
                expect(dealer).to_have_attribute("data-pose", "idle")
                page.set_viewport_size({"width":1440,"height":1050})
                page.locator(".shop-back").click()
                expect(page.locator("#vegas-machine")).to_be_visible()
                assert len(spin_requests) == shop_requests, "Shop browsing must not spend or spin"
                # A server-owned superuser bankroll must work even at zero.
                def enable_admin_bankroll():
                    from league.models import VegasLabWallet
                    User.objects.filter(username=f"vegas-browser-{engine}").update(is_superuser=True)
                    VegasLabWallet.objects.filter(user__username=f"vegas-browser-{engine}").update(balance=0, free_spins=0, last_payload={})
                database.submit(enable_admin_bankroll).result(timeout=5)
                page.goto(base+"?fullscreen=1")
                expect(page.locator("#vegas-balance")).to_have_text("∞")
                expect(page.locator("#vegas-balances-list .is-you strong")).to_have_text("∞")
                expect(page.locator("#vegas-auto")).to_be_enabled()
                page.keyboard.press("Space")
                expect(page.locator("#vegas-spin")).to_be_enabled(timeout=20000)
                expect(page.locator("#vegas-balance")).to_have_text("∞")
                for _ in range(20):
                    if page.locator("#vegas-plus").is_disabled():
                        break
                    page.locator("#vegas-plus").click()
                admin_board_before = page.locator("#vegas-board").bounding_box()
                page.locator("#vegas-buy").click()
                expect(page.locator("#vegas-purchase-balance")).to_have_text("∞")
                page.locator("#vegas-purchase-confirm").click()
                expect(page.locator('#vegas-celebration[data-kind="summary"]')).to_be_visible(timeout=30000)
                page.locator("#vegas-celebration-close").click()
                expect(page.locator("#vegas-spin")).to_be_enabled()
                expect(page.locator("#vegas-balance")).to_have_text("∞")
                completed_board = page.locator("#vegas-board").bounding_box()
                assert all(abs(completed_board[key]-admin_board_before[key]) <= 1 for key in ("width", "height")), "Bonus completion must not resize the field"
                page.locator("#vegas-spin").click()
                expect(page.locator("#vegas-spin")).to_be_enabled(timeout=20000)
                resumed_board = page.locator("#vegas-board").bounding_box()
                assert all(abs(resumed_board[key]-admin_board_before[key]) <= 1 for key in ("width", "height")), "Resuming paid spins must not resize the field"
                page.screenshot(path=str(output/f"{engine}-admin-bankroll.png"))
                page.locator("#vegas-shop").click()
                expect(page.locator("#shop-balance")).to_have_text("∞")
                # Activate as a finite player, approve as the league owner in
                # another tab, and refresh the real wallet without a reload.
                def finite_player():
                    from league.models import VegasLabWallet
                    User.objects.filter(username=f"vegas-browser-{engine}").update(is_superuser=False)
                    VegasLabWallet.objects.filter(user__username=f"vegas-browser-{engine}").update(balance=0, free_spins=0, last_payload={})
                database.submit(finite_player).result(timeout=5)
                page.set_viewport_size({"width":390,"height":844})
                page.goto(base+"?fullscreen=1")
                expect(page.locator("#vegas-balance")).to_have_text("0\u00a0$")
                page.locator("#vegas-topup").click()
                expect(page.locator('#vegas-topup-tasks [data-task="ban"]')).to_be_enabled()
                page.screenshot(path=str(output/f"{engine}-390-topup-choose.png"))
                page.locator('#vegas-topup-tasks [data-task="ban"]').click()
                expect(page.locator("#vegas-topup-active")).to_be_visible()
                expect(page.locator("#vegas-topup-choices")).not_to_be_visible()
                page.locator("#vegas-topup-note").fill("Задание выполнено, участник лиги подтвердил.")
                before_topup = len(spin_requests)
                page.keyboard.press("Space")
                assert len(spin_requests) == before_topup, "Topup typing must not spin"
                page.locator("#vegas-topup-submit").click()
                expect(page.locator("#vegas-topup-active-meta")).to_contain_text("На проверке")
                owner_tab = context.new_page()
                owner_tab.set_extra_http_headers({"X-Test-League-Owner":"yes"})
                owner_tab.goto(f"http://127.0.0.1:{server.server_port}"+topup_fixture["manage_url"])
                expect(owner_tab.locator("#vegas-topup-management")).to_contain_text("Задание выполнено")
                owner_tab.screenshot(path=str(output/f"{engine}-topup-owner.png"),full_page=True)
                owner_tab.locator('#vegas-topup-management button[value="approve"]').click()
                expect(owner_tab.locator("#vegas-topup-management")).to_contain_text("Засчитано")
                owner_tab.close()
                page.locator("#vegas-topup-close").click()
                page.locator("#vegas-topup").click()
                expect(page.locator("#vegas-balance")).to_have_text("3\u00a0000\u00a0$")
                expect(page.locator("#vegas-topup-history")).to_contain_text("Засчитано")
                expect(page.locator('#vegas-topup-tasks [data-task="meme"]')).to_be_disabled()
                page.screenshot(path=str(output/f"{engine}-390-topup-credited.png"))
                # Released UI uses a genuine non-staff session and public APIs.
                page.set_extra_http_headers({"X-Test-Public-Player": "yes"})
                for width, height in ((390, 844), (844, 390), (1440, 900)):
                    page.set_viewport_size({"width": width, "height": height})
                    page.goto(f"http://127.0.0.1:{server.server_port}/arcade/play/vegas/?fullscreen=1", wait_until="networkidle")
                    expect(page.locator("#vegas-reset")).to_have_count(0)
                    expect(page.locator("#vegas-scenario")).to_have_count(0)
                    expect(page.locator("#vegas-page")).to_have_class(re.compile("is-fullscreen"))
                    config = page.locator("#vegas-config").text_content()
                    assert not json.loads(config)["unlimited_balance"]
                    with page.expect_response(lambda r: "/arcade/vegas/spin/" in r.url and r.request.method == "POST") as sent:
                        page.keyboard.press("Space")
                    assert sent.value.status == 200
                    expect(page.locator("#vegas-spin")).to_be_enabled(timeout=20000)
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                    page.screenshot(path=str(output/f"{engine}-{width}-released.png"))
                    page.locator("#vegas-shop").click()
                    page.wait_for_url("**/arcade/vegas/shop/?wallet=*")
                    expect(page.locator(".shop-scene")).to_be_visible()
                    page.locator(".shop-back").click()
                    page.wait_for_url("**/arcade/play/vegas/?fullscreen=1")
                expect(page.locator("#vegas-spin")).to_be_enabled()
                closing_balance = page.locator("#vegas-balance").inner_text()
                page.evaluate('document.dispatchEvent(new Event("vegas:closed"))')
                expect(page.locator("#vegas-spin")).to_be_disabled()
                expect(page.locator("#vegas-buy")).to_be_disabled()
                expect(page.locator("#vegas-balance")).to_have_text(closing_balance)
                assert not errors, errors
                print(f"{engine}: stable responsive UI, paid auto start/stop, automatic bonus totals, pause/background/reload, retries, audio and FX OK")
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
