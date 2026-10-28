"""Exercise real game JS + templates with mocked HTTP, no production data.

Run: python tests/arcade_security_browser.py --browser webkit
Backend ownership/tokens/score rejection are tested separately in Django.
"""
import argparse
import json
import mimetypes
import os
from pathlib import Path
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
from playwright.sync_api import sync_playwright
from league.models import ArcadeRecord, DoodleRecord


def run(engine):
    with override_settings(ALLOWED_HOSTS=["testserver"], STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}):
        call_command("migrate", verbosity=0)
        user = User.objects.create_user("runtime63")
        ArcadeRecord.objects.create(user=user, best_score=7)
        DoodleRecord.objects.create(user=user, best_score=7)
        client = Client()
        client.force_login(user)
        pages = {"/"+key: client.get(reverse("league:arcade_game", args=[key])).content
                 for key in ("doodle_jump", "flappy")}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            path = urlsplit(self.path).path
            if path in pages:
                body, mime = pages[path], "text/html; charset=utf-8"
            elif path.startswith("/static/") and (filename := finders.find(path[8:])):
                body, mime = Path(filename).read_bytes(), mimetypes.guess_type(filename)[0]
                # TEST ONLY hooks: no test/debug exports are added to deployed JS.
                hooks = {
                    "doodle-jump.js": "window.__game={start:()=>startGame(true),end:endGame,score:n=>{peakY=startY+n*11;},state:()=>({best,attemptId,mode})};",
                    "arcade.js": "window.__game={start:startGame,end:endGame,score:n=>{score=n;},state:()=>({best,attemptId,state})};",
                }
                if Path(filename).name in hooks:
                    before, marker, after = body.decode().rpartition("})();")
                    assert marker
                    body = (before+hooks[Path(filename).name]+marker+after).encode()
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", mime or "application/octet-stream")
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    errors = []
    try:
        with sync_playwright() as pw:
            browser = getattr(pw, engine).launch()
            for width in (390, 1440):
                for key in ("doodle_jump", "flappy"):
                    page = browser.new_page(viewport={"width": width, "height": 900})
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.add_init_script("""localStorage.setItem('f1-doodle-gp-best-v1','999999');
                        localStorage.setItem('f1-pit-lane-flight-record-v1','999999');
                        // Freeze simulation only; assets and network still use real browser APIs.
                        window.requestAnimationFrame=()=>1; window.cancelAnimationFrame=()=>{};""")
                    requests = []
                    def api(route):
                        data = json.loads(route.request.post_data or '{}')
                        assert route.request.headers.get('x-csrftoken')
                        path = urlsplit(route.request.url).path
                        requests.append((path, data))
                        if path.endswith('/start/'):
                            route.fulfill(json={"attempt_id": 42, "run_token": "server-issued-session-token-123456789",
                                "records": [], "record": 7})
                        elif path.endswith('/progress/'):
                            route.fulfill(json={"ok": True})
                        else:
                            route.fulfill(json={"record": 50, "records": [], "rank": 1})
                    page.route('**/arcade/**/start/', api)
                    page.route('**/arcade/**/progress/', api)
                    page.route('**/arcade/**/finish/', api)
                    page.goto(f'http://127.0.0.1:{server.server_port}/{key}', wait_until='networkidle')
                    page.wait_for_function('window.__game && window.__game.state().best === 7', polling=50)
                    if key == 'doodle_jump':
                        page.wait_for_function("!document.querySelector('.doodle-machine').classList.contains('is-loading')", polling=50)
                    page.clock.install()
                    page.evaluate('() => { window.__game.start(); }')
                    page.wait_for_function('window.__game.state().attemptId === 42', polling=50)
                    page.evaluate('window.__game.score(30)')
                    page.clock.fast_forward(10000)
                    page.wait_for_function("() => true", polling=50)  # Allow route fulfilment to reach fetch.
                    for _ in range(50):
                        if any(path.endswith('/progress/') for path, _ in requests):
                            break
                        page.wait_for_timeout(20)
                    assert any(path.endswith('/progress/') for path, _ in requests), (key, requests)
                    page.evaluate('window.__game.score(50)')
                    assert page.evaluate('() => { window.__game.end(); return window.__game.state().best; }') == 7
                    page.wait_for_function('window.__game.state().best === 50', polling=50)
                    updates = [(path, data) for path, data in requests if not path.endswith('/start/')]
                    assert all(data['run_token'] == 'server-issued-session-token-123456789' for _, data in updates)
                    assert updates[-1][0].endswith('/finish/') and updates[-1][1]['score'] == 50
                    assert len([path for path, _ in requests if path.endswith('/finish/')]) == 1
                    assert page.evaluate("localStorage.getItem('f1-doodle-gp-best-v1')") == '999999'
                    assert page.evaluate("localStorage.getItem('f1-pit-lane-flight-record-v1')") == '999999'
                    page.close()
            browser.close()
        assert not errors, errors
        print(f'Arcade security runtime OK ({engine}): both games at mobile/desktop sizes; localStorage ignored, tokens/checkpoints/finish/confirmed records.')
    finally:
        server.shutdown()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', choices=['chromium', 'webkit'], default='chromium')
    run(parser.parse_args().browser)
