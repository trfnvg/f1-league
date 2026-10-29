"""Real calendar templates/assets against an ephemeral database, desktop + mobile.

python tests/calendar_browser.py --browser webkit --output-dir /tmp/fastlap-calendar-ui
"""
import argparse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
import os
from pathlib import Path
import sys
import threading
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.test import Client, override_settings
from django.urls import reverse
from playwright.sync_api import sync_playwright
from league.models import Event


def run(browser_name, output):
    call_command("migrate", verbosity=0, interactive=False)
    now = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
    event = Event.objects.create(name="Мехико, Мексика", circuit="mexico", round_number=19,
        deadline=now + timedelta(days=2), race_datetime=now + timedelta(days=4), season_year=2026,
        cover_image="event_covers/my-mexico.jpg")
    with override_settings(ALLOWED_HOSTS=["testserver"], MEDIA_URL="/media/", STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }), patch("league.race_calendar.timezone.now", return_value=now):
        page_html = Client().get(reverse("league:calendar")).content

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            if path == "/calendar/":
                body, content_type = page_html, "text/html; charset=utf-8"
            elif path == "/media/event_covers/my-mexico.jpg":
                body = (ROOT / "league/static/league/images/calendar/mexico.jpg").read_bytes()
                content_type = "image/jpeg"
            elif path.startswith("/static/"):
                filename = finders.find(path[len("/static/"):])
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
            browser = getattr(pw, browser_name).launch()
            for width in (320, 390, 768, 1440, 1920):
                context = browser.new_context(viewport={"width": width, "height": 1000},
                    timezone_id="America/Los_Angeles", reduced_motion="reduce")
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/calendar/", wait_until="networkidle")
                assert page.locator(".rc-card").count() == 23
                assert page.locator('#mainMenu .menu-item').first.text_content().strip() == "Главная"
                assert page.locator('#mainMenu .menu-item').first.get_attribute('href') == '/'
                for link in page.locator('[data-prediction-nav]').all():
                    assert link.get_attribute('href') == '/accounts/login/?next=%2Fevents%2F' + str(event.pk) + '%2F'
                assert page.locator("#next-grand-prix").inner_text() == "Мехико"
                assert page.locator(".rc-feature-times time").last.inner_text() == "01.11 · 23:00"
                assert page.locator(".rc-feature-times [data-calendar-session]").count() == 5
                assert page.locator(".rc-feature-times [data-calendar-session=Q] time").inner_text() == "01.11 · 00:00"
                assert page.locator(".rc-feature .rc-button").get_attribute("href") == reverse("league:event_detail", args=[event.pk])
                assert page.locator(".rc-feature-image img").get_attribute("src") == "/media/event_covers/my-mexico.jpg"
                assert page.locator("#grand-prix-mexico .rc-card-visual img").get_attribute("src") == "/media/event_covers/my-mexico.jpg"
                assert page.locator("#grand-prix-shanghai [data-calendar-session=SQ]").count() == 1
                assert page.locator("#grand-prix-shanghai [data-calendar-session=FP2]").count() == 0
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), width
                assert page.locator('.rc-card').evaluate_all('''cards => cards.every(card => {
                    const bounds = card.getBoundingClientRect();
                    return [...card.querySelectorAll('.rc-card-footer > *')].every(child => {
                        const box = child.getBoundingClientRect();
                        return box.left >= bounds.left && box.right <= bounds.right;
                    });
                })'''), (width, "card footer must not overflow")
                assert page.locator('.rc-card-footer').first.evaluate("node => getComputedStyle(node).backgroundColor") == 'rgba(0, 0, 0, 0)'
                assert page.locator(".rc-feature-image img").evaluate("image => image.complete && image.naturalWidth > 0")
                page.screenshot(path=str(output / f"{width}-calendar.png"), full_page=True)
                page.screenshot(path=str(output / f"{width}-calendar-top.png"))
                page.select_option("#calendar-timezone", "device")
                assert page.locator(".rc-feature-times time").last.inner_text() == "01.11 · 12:00"
                page.select_option("#calendar-timezone", "venue")
                assert page.locator(".rc-feature-times time").last.inner_text() == "01.11 · 14:00"
                assert "по месту проведения" in page.locator("[data-calendar-zone-note]").inner_text()
                page.reload(wait_until="networkidle")
                assert page.locator("#calendar-timezone").input_value() == "venue"
                page.select_option("#calendar-timezone", "Europe/Moscow")
                page.locator('[data-filter="upcoming"]').click()
                assert page.locator(".rc-card:visible").count() == 5
                assert page.locator('[data-filter="upcoming"]').get_attribute("aria-pressed") == "true"
                page.locator('[data-filter="sprint"]').click()
                assert page.locator(".rc-card:visible").count() == 6
                page.locator('[data-filter="all"]').click()
                assert page.locator(".rc-card:visible").count() == 23
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), width
                page.locator('.rc-month-nav a[href="#calendar-month-11"]').click()
                assert page.locator("#calendar-month-11").is_visible()
                page.locator(".rc-credits summary").click()
                assert page.locator(".rc-credits li:visible").count() == 22
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), width
                context.close()
            context = browser.new_context(java_script_enabled=False, viewport={"width": 390, "height": 900})
            page = context.new_page()
            page.goto(base + "/calendar/", wait_until="networkidle")
            assert page.locator(".rc-card").count() == 23
            assert "01.11 · 23:00" in page.locator(".rc-feature-times").inner_text()
            assert page.locator("[data-calendar-timezone]").is_hidden()
            assert page.locator(".rc-feature .rc-button").is_visible()
            browser.close()
        assert not errors, errors
        print(f"Calendar UI OK ({browser_name}): 5 sizes, 23 cards, five sessions, uploaded covers, sprint format, timezones + DST, filters, credits, no-JS fallback. {output}")
    finally:
        server.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", choices=("webkit", "chromium"), default="webkit")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run(args.browser, args.output_dir)
