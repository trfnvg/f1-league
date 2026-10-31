"""Outlined brand assets in real shared navigation; ephemeral SQLite only."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
import os
from pathlib import Path
import sys
import threading
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.test import Client, override_settings
from playwright.sync_api import sync_playwright


def run(engine, output):
    call_command('migrate', verbosity=0, interactive=False)
    output.mkdir(parents=True, exist_ok=True)
    client = Client()
    with override_settings(ALLOWED_HOSTS=['testserver'], STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }):
        pages = {path: client.get(path).content for path in ('/', '/accounts/login/')}
        user = User.objects.create_user('brand-preview', first_name='Александр', password='test-only')
        client.force_login(user)
        pages['/signed-in/'] = client.get('/').content
    pages['/brand-preview/'] = b'''<!doctype html><html lang="en"><meta charset="utf-8">
      <title>Fastlap wordmark</title><style>
      *{box-sizing:border-box}body{margin:0;background:#191d23;color:#f3f5f7;font-family:Arial,sans-serif}
      main{width:960px;padding:72px}header{display:flex;justify-content:space-between;color:#8f98a4;font:11px monospace;letter-spacing:2px}
      section{display:flex;align-items:center;justify-content:center;height:300px;border-bottom:1px solid #343a44}
      section img{width:650px;height:auto}.sizes{display:flex;align-items:center;justify-content:space-between;padding-top:42px}
      .sizes>div{display:flex;align-items:center;justify-content:center;height:90px}.sizes img{height:auto}
      </style><main><header><span>FASTLAP / WORDMARK</span><span>RACE PREDICTION CLUB</span></header>
      <section><img src="/static/league/fastlap-wordmark.svg" alt="Fastlap"></section>
      <div class="sizes"><div><img width="176" src="/static/league/fastlap-wordmark.svg" alt="Fastlap"></div>
      <div><img width="123" src="/static/league/fastlap-wordmark.svg" alt="Fastlap"></div>
      <div><img width="42" src="/static/league/fastlap-monogram.svg" alt="FL"></div></div></main></html>'''

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            if path in pages:
                body, kind = pages[path], 'text/html; charset=utf-8'
            elif path.startswith('/static/'):
                filename = finders.find(path[len('/static/'):])
                if not filename:
                    self.send_error(404)
                    return
                body = Path(filename).read_bytes()
                kind = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', kind)
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    errors = []
    try:
        with sync_playwright() as pw:
            browser = getattr(pw, engine).launch()
            for width in (320, 390, 780, 781, 1024, 1100, 1101, 1440, 1920):
                context = browser.new_context(viewport={'width': width, 'height': 900}, device_scale_factor=2)
                # Brand paths must render before, and without, any font or CDN.
                context.route('https://**', lambda route: route.abort())
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                for path in ('/', '/signed-in/', '/accounts/login/'):
                    page.goto(base + path, wait_until='networkidle')
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), (width, path)
                    assert page.locator('.fl-brandmark').count() == 0
                    assert page.locator('link[rel=icon]').get_attribute('href') == '/static/league/fastlap-tab-v4.ico'
                    if width <= 780:
                        link = page.locator('.site-header .nightshift-mobile-brand')
                        image = link.locator('.fl-wordmark')
                        assert page.locator('.nightshift-sidebar').is_hidden()
                    elif width <= 1100:
                        link = page.locator('.nightshift-sidebar .nightshift-brand')
                        image = link.locator('.fl-compactmark')
                        assert link.locator('.fl-wordmark').is_hidden()
                        assert link.locator('.fl-brand-caption').is_hidden()
                    else:
                        link = page.locator('.nightshift-sidebar .nightshift-brand')
                        image = link.locator('.fl-wordmark')
                        assert link.locator('.fl-compactmark').is_hidden()
                    assert image.is_visible(), (width, path)
                    assert image.evaluate('node => node.complete && node.naturalWidth > 0')
                    assert image.evaluate('node => Math.abs(node.clientWidth/node.clientHeight-node.naturalWidth/node.naturalHeight) < .12')
                    assert link.get_attribute('aria-label') == 'Fastlap — обзор'
                    assert link.get_attribute('href') == '/'
                    if path == '/':
                        link.screenshot(path=str(output / f'{width}-brand.png'))
                        page.screenshot(path=str(output / f'{width}-home.png'))
                # Off-canvas branding uses the same wordmark; no separate font logo.
                page.evaluate("document.querySelector('#mainMenu').classList.add('show')")
                menu_logo = page.locator('#mainMenu .fl-wordmark')
                assert menu_logo.is_visible()
                assert menu_logo.evaluate('node => node.complete && node.naturalWidth > 0')
                assert page.evaluate("getComputedStyle(document.querySelector('.fl-wordmark')).animationName === 'none'")
                context.close()
            page = browser.new_page(viewport={'width': 960, 'height': 580}, device_scale_factor=2)
            page.goto(base + '/brand-preview/', wait_until='networkidle')
            page.screenshot(path=str(output / 'wordmark-preview.png'))
            browser.close()
        assert not errors, errors
        print(f'Brand UI OK ({engine}): nine widths, public/signed-in/login, outlined assets, compact rail, menu, no font dependency, unchanged favicon. {output}')
    finally:
        server.shutdown()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', choices=('chromium', 'webkit'), default='chromium')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    run(args.browser, args.output_dir)
