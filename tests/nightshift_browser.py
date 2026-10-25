"""Render the real Django pages against an ephemeral DB; check desktop/mobile UI.

Usage: python tests/nightshift_browser.py --output-dir /tmp/fastlap-nightshift-ui
Requires Playwright + Chromium in the development environment only.
"""
import argparse
import mimetypes
import os
from pathlib import Path
import sys
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.template.loader import render_to_string
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import sync_playwright
from league.circuits import CIRCUITS
from league.leagues import import_legacy_league
from league.models import Event, Prediction, Score, Season


def render_pages():
    call_command("migrate", verbosity=0)
    now = timezone.now()
    season = Season.get_active()
    past = Event.objects.create(name="Гран-при Сингапура", round_number=18, season_year=season.year,
        deadline=now-timedelta(days=9), race_datetime=now-timedelta(days=7), status="scored")
    event = Event.objects.create(name="Гран-при США", round_number=19, season_year=season.year,
        deadline=now+timedelta(days=2), race_datetime=now+timedelta(days=3))
    for i, key in enumerate(("mexico", "interlagos", "las-vegas", "lusail", "yas-marina"), 20):
        Event.objects.create(name=CIRCUITS[key]["grand_prix"], circuit=key, round_number=i,
            season_year=season.year, deadline=now+timedelta(days=(i-19)*7+2), race_datetime=now+timedelta(days=(i-19)*7+3))
    player = User.objects.create_user("Гриша")
    for user, points in [(User.objects.create_user("Аня"), 245), (player, 232),
                         (User.objects.create_user("Айдар"), 218), (User.objects.create_user("Славик"), 191),
                         (User.objects.create_user("Очень_длинное_имя_участника"), 144)]:
        Prediction.objects.create(user=user, event=past)
        Score.objects.create(user=user, event=past, points=points)
    Prediction.objects.create(user=player, event=event)
    owner = User.objects.create_superuser("preview-admin", "preview@example.com", "test")
    league, _ = import_legacy_league(owner=owner, season_year=season.year, name="Fastlap Main")
    client = Client()
    pages = {"/guest/": client.get(reverse("league:home")).content}
    client.force_login(player)
    pages["/"] = client.get(reverse("league:home")).content
    pages["/league/"] = client.get(reverse("league:friend_league", args=[league.league_id])).content
    pages["/standings/"] = client.get(reverse("league:global_leaderboard")).content
    pages["/event/"] = client.get(reverse("league:event_detail", args=[event.pk])).content
    Event.objects.filter(pk=event.pk).update(deadline=now-timedelta(hours=1))
    pages["/closed/"] = client.get(reverse("league:home")).content
    client.force_login(owner)
    pages["/admin-add/"] = client.get(reverse("admin:league_event_add")).content
    pages["/admin-edit/"] = client.get(reverse("admin:league_event_change", args=[event.pk])).content
    pages[reverse("admin:jsi18n")] = client.get(reverse("admin:jsi18n")).content
    gallery = "".join('<figure style="padding:20px;border:1px solid #353d48;border-radius:15px"><figcaption>'+c["grand_prix"]+'</figcaption>'+render_to_string("circuit_track.html", {"circuit": c, "track_id": key, "animated": True})+'</figure>' for key, c in CIRCUITS.items())
    pages["/circuits/"] = ('<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/static/league/circuit-visual.css"></head><body style="background:#1d2229;color:#f3f5f7;font:14px sans-serif;display:grid;grid-template-columns:repeat(3,1fr)">'+gallery+'</body></html>').encode()
    assert all(b"Server Error" not in html for html in pages.values())
    return pages


def run(output, widths):
    with override_settings(ALLOWED_HOSTS=["testserver"], STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }):
        pages = render_pages()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            route = unquote(urlsplit(self.path).path)
            if route in pages:
                body = pages[route]
                content_type = "text/javascript" if route.endswith("/jsi18n/") else "text/html; charset=utf-8"
            elif route.startswith("/static/"):
                filename = finders.find(route[len("/static/"):])
                if not filename:
                    self.send_error(404)
                    return
                body = Path(filename).read_bytes()
                content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for width in widths:
                page = browser.new_page(viewport={"width": width, "height": 1000}, device_scale_factor=1)
                page.on("pageerror", lambda error: errors.append(str(error)))
                for route in ("/", "/guest/", "/closed/", "/league/", "/standings/", "/event/"):
                    page.goto(base+route, wait_until="networkidle")
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), (width, route, "page overflow")
                    sidebar_visible = page.locator(".nightshift-sidebar").is_visible()
                    if sidebar_visible != (width > 780):
                        page.screenshot(path=str(output/f"failure-{width}-{route.strip('/') or 'home'}.png"), full_page=True)
                    assert sidebar_visible == (width > 780), (width, route, page.locator(".nightshift-sidebar").evaluate("e=>({display:getComputedStyle(e).display,width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height})"))
                    if route in ("/", "/guest/", "/closed/"):
                        svg = page.locator(".ns-trackdrawing .circuit-visual")
                        assert svg.get_attribute("data-circuit") == "austin"
                        assert page.locator("#circuit-path-home").evaluate("p => p.getTotalLength()") > 500
                        box = svg.bounding_box()
                        assert box["width"] > 190 and box["height"] > 150
                        assert page.locator(".ns-primary").is_visible()
                    if route == "/closed/":
                        assert page.locator(".ns-deadline").inner_text().startswith("ДО СТАРТА ГОНКИ")
                    page.screenshot(path=str(output/f"{width}-{route.strip('/') or 'home'}.png"), full_page=True)
                page.close()
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base+"/admin-add/", wait_until="networkidle")
            for key in CIRCUITS:
                page.select_option("#id_circuit", key)
                assert page.locator("[data-circuit-preview]").is_visible()
                assert page.locator("#id_name").input_value() == CIRCUITS[key]["grand_prix"]
                assert page.locator("#circuit-path-admin").get_attribute("d") == CIRCUITS[key]["path"]
            page.fill("#id_name", "Мой авторский этап")
            page.select_option("#id_circuit", "austin")
            assert page.locator("#id_name").input_value() == "Мой авторский этап"
            page.screenshot(path=str(output/"admin-circuit-picker.png"), full_page=True)
            page.goto(base+"/admin-edit/", wait_until="networkidle")
            assert page.locator("#id_circuit").input_value() == "austin"
            page.goto(base+"/", wait_until="networkidle")
            position = "el => { const m=el.getScreenCTM(); return [m.e,m.f]; }"
            runner = page.locator(".ns-trackdrawing .circuit-runner")
            first = runner.evaluate(position)
            page.wait_for_timeout(350)
            assert runner.evaluate(position) != first, "Track runner is not moving"
            page.emulate_media(reduced_motion="reduce")
            assert not runner.is_visible()
            assert page.locator("#circuit-path-home").evaluate("el => getComputedStyle(el).animationName") == "none"
            page.goto(base+"/circuits/", wait_until="networkidle")
            page.screenshot(path=str(output/"all-circuits.png"), full_page=True)
            browser.close()
        assert not errors, errors
        print(f"UI OK: {len(widths)} viewport sizes, 6 real pages, 27 admin choices, SVG motion and reduced motion. Screenshots: {output}")
    finally:
        server.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--widths", nargs="+", type=int, default=[320, 390, 768, 1101, 1440, 1920])
    args = parser.parse_args()
    run(args.output_dir, args.widths)
