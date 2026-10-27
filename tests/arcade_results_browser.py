"""Real template/CSS cascade and live row renderers, using only an ephemeral DB.

python tests/arcade_results_browser.py --output-dir /tmp/fastlap-results
"""
import argparse
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
import os
from pathlib import Path
import re
import sys
import threading
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import sync_playwright
from league.models import ArcadeRecord, ArcadeSettings, DoodleRecord, Event, MinesweeperAttempt, Season


def fixtures():
    call_command("migrate", verbosity=0)
    now = timezone.now()
    season = Season.get_active()
    event = Event.objects.create(name="Results GP", round_number=1, season_year=season.year,
                                 deadline=now+timedelta(days=1), race_datetime=now+timedelta(days=2))
    ArcadeSettings.objects.update_or_create(pk=1, defaults={"public_enabled": False,
        "active_game": "minesweeper", "competition_event": event,
        "competition_opened_at": now-timedelta(hours=1)})
    admin = User.objects.create_superuser("results-admin", "admin@example.com", "test-password")
    player = User.objects.create_user("long-player", first_name="Очень длинное имя игрока")
    other = User.objects.create_user("other-player", first_name="Гриша")
    for user, score in [(player, 999999), (other, 500)]:
        ArcadeRecord.objects.create(user=user, best_score=score, total_attempts=12345)
        DoodleRecord.objects.create(user=user, best_score=score, total_attempts=12345)
    client = Client()
    client.force_login(player)
    pages = {key: client.get(reverse("league:arcade_game", args=[key])).content.decode()
             for key in ("flappy", "doodle_jump")}
    client.logout()
    pages["flappy-guest"] = client.get(reverse("league:arcade_game", args=["flappy"])).content.decode()
    client.force_login(admin)
    pages["minesweeper-empty"] = client.get(reverse("league:arcade_minesweeper_preview")).content.decode()
    week = __import__("league.views", fromlist=["_current_arcade_week_start"])._current_arcade_week_start()
    for user, elapsed in [(player, 95000), (other, 100000)]:
        MinesweeperAttempt.objects.create(user=user, week_start=week, completed=True, elapsed_ms=elapsed)
    pages["minesweeper"] = client.get(reverse("league:arcade_minesweeper_preview")).content.decode()
    # Keep the actual head/style ordering and actual leaderboard markup; omit
    # game canvases and runtime scripts to isolate the results component.
    return {"/"+key: "<!doctype html><html lang='ru'><head>"+
            re.search(r"<head>(.*?)</head>", html, re.S)[1]+"</head>"+
            "<body class='summer-theme editorial-theme apex-night-theme' style='display:block!important'>"+
            "<main style='width:calc(100% - 24px);max-width:1120px;margin:20px auto'>"+
            ("<div class='doodle-page'" if key == "doodle_jump" else
             "<div class='minesweeper-page'" if key.startswith("minesweeper") else
             "<div class='arcade-page'")+" style='margin:0;padding:0;width:100%;max-width:none'>"+
            re.search(r'<section class="[^"]*arcade-results[\s\S]*?</section>', html)[0]+
            "</div></main></body></html>" for key, html in pages.items()}


def run(output, engine):
    with override_settings(ALLOWED_HOSTS=["testserver"], STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }):
        pages = fixtures()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            path = urlsplit(self.path).path
            if path in pages:
                body, mime = pages[path].encode(), "text/html; charset=utf-8"
            elif path.startswith("/static/") and (filename := finders.find(path[8:])):
                body, mime = Path(filename).read_bytes(), mimetypes.guess_type(filename)[0]
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", mime or "application/octet-stream")
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    output.mkdir(parents=True, exist_ok=True)
    sources = {key: (ROOT/"league/static/league"/filename).read_text() for key, filename in
               [("flappy", "arcade.js"), ("doodle_jump", "doodle-jump.js"), ("minesweeper", "arcade-minesweeper.js")]}
    try:
        with sync_playwright() as pw:
            browser = getattr(pw, engine).launch()
            for width in (320, 390, 1440):
                signatures = []
                for route in pages:
                    page = browser.new_page(viewport={"width": width, "height": 900})
                    page.goto(f"http://127.0.0.1:{server.server_port}{route}", wait_until="networkidle")
                    assert page.locator(".arcade-results").count() == 1
                    assert abs(page.locator(".arcade-results").bounding_box()["width"] - min(width-24, 1120)) <= 1, (route, width)
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                    if route.endswith("empty"):
                        assert page.locator(".minesweeper-board-empty").is_visible()
                        page.close()
                        continue
                    row = page.locator(".arcade-results-list>li").first
                    signature = row.evaluate("""e => {
                        const s=getComputedStyle(e), name=getComputedStyle(e.children[1]), score=getComputedStyle(e.children[2]);
                        return [s.gridTemplateColumns,s.minHeight,name.fontFamily,name.fontSize,name.color,score.fontFamily,score.fontSize,score.color];
                    }""")
                    signatures.append(signature)
                    assert row.locator(":scope> :nth-child(2)").evaluate("e=>getComputedStyle(e).textOverflow") == "ellipsis"
                    assert page.locator(".arcade-table-labels>span").count() == 4
                    # Call the real polling renderer in isolation; its generated
                    # rows must retain the same geometry, typography and colors.
                    key = route.strip("/").removesuffix("-guest")
                    source = sources[key]
                    renderer = re.search(r"  function renderLeaderboard\([^\n]*\)[\s\S]*?(?=\n  (?:async )?function )", source)[0]
                    setup = "const leaderboardNode=document.querySelector('.arcade-results-list'); const board=leaderboardNode; const deadlineClosed=false;"
                    if key == "minesweeper":
                        setup += source[source.index("  const formatTime ="):source.index("  const currentElapsed =")]
                    page.evaluate("(script)=>{eval(script)}", setup+renderer+"\nrenderLeaderboard([{rank:1,username:'<b>Очень длинное имя</b>',score:999999,attempts:12345,wins:3,best_time_ms:95000,is_current_user:true}]);")
                    assert page.locator(".arcade-results-list>li").count() == 1
                    assert page.locator(".arcade-results-list>li>:nth-child(2) b").count() == 0
                    assert page.locator(".arcade-results-list>li").first.evaluate("e=>getComputedStyle(e).gridTemplateColumns") == signature[0]
                    page.locator(".arcade-results").screenshot(path=str(output/f"{width}-{route[1:]}.png"))
                    page.close()
                assert all(signature == signatures[0] for signature in signatures), signatures
            browser.close()
        print(f"Results UI OK ({engine}): three sizes, all games, guest/empty states and real polling renderers")
    finally:
        server.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--browser", choices=["chromium", "webkit"], default="chromium")
    args = parser.parse_args()
    run(args.output_dir, args.browser)
