"""Staff lab and real game links, using synthetic data in an ephemeral SQLite DB."""
import argparse
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
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import expect, sync_playwright
from league.models import ArcadeSettings, Event, Season


def fixtures():
    call_command('migrate', verbosity=0, interactive=False)
    client = Client()
    user = User.objects.create_user('lab-preview', first_name='Александр', is_staff=True)
    client.force_login(user)
    season = Season.get_active()
    now = timezone.now()
    event = Event.objects.create(name='Мехико, Мексика', round_number=19, season_year=season.year,
        deadline=now + timedelta(days=1), race_datetime=now + timedelta(days=2))
    settings, _ = ArcadeSettings.objects.update_or_create(pk=1, defaults={
        'active_game': 'doodle_jump', 'public_enabled': True, 'competition_event': event,
        'competition_opened_at': now - timedelta(hours=1)})
    # Django's test environment exposes the lab's URLs without duplicating routing logic.
    from django.test.utils import setup_test_environment
    setup_test_environment()
    response = client.get(reverse('league:arcade_control'))
    cards = response.context['test_games']
    pages = {reverse('league:arcade_control'): response.content}
    for card in cards:
        pages[card['url']] = client.get(card['url']).content
    event.deadline = now - timedelta(hours=1)
    event.save(update_fields=['deadline'])
    pages['/lab-expired/'] = client.get(reverse('league:arcade_control')).content
    settings.public_enabled = False
    settings.competition_event = None
    settings.competition_opened_at = None
    settings.save()
    pages['/lab-empty/'] = client.get(reverse('league:arcade_control')).content
    return pages, cards


def run(engine, output):
    with override_settings(ALLOWED_HOSTS=['testserver'], STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }):
        pages, cards = fixtures()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            path = urlsplit(self.path).path
            if self.path in pages:
                body, mime = pages[self.path], 'text/html; charset=utf-8'
            elif path.startswith('/static/') and (filename := finders.find(path[8:])):
                body, mime = Path(filename).read_bytes(), mimetypes.guess_type(filename)[0]
            elif 'leaderboard' in path:
                body, mime = b'{"records":[],"total_attempts":0}', 'application/json'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', mime or 'application/octet-stream')
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    errors, writes = [], []
    output.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as pw:
            browser = getattr(pw, engine).launch()
            for width in (320, 390, 768, 1024, 1280, 1440, 1920):
                context = browser.new_context(viewport={'width': width, 'height': 900}, device_scale_factor=2,
                    reduced_motion='reduce')
                context.route('https://**', lambda route: route.abort())
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('request', lambda request: writes.append(request.url) if request.method == 'POST' else None)
                for path in ('/arcade/control/', '/lab-expired/', '/lab-empty/'):
                    page.goto(base + path, wait_until='networkidle')
                    expect(page.locator('.lab-game-card')).to_have_count(4)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), (width, path)
                    assert not page.locator('#lab-competition').get_attribute('open')
                    assert page.locator('#arcade-game-select').is_hidden()
                    assert page.locator('#test-wheel-spin').is_hidden()
                    for card in cards:
                        cover = page.locator(f'[data-test-game="{card["key"]}"] img')
                        cover.scroll_into_view_if_needed()
                        expect(cover).to_have_js_property('complete', True)
                        assert cover.evaluate('node=>node.naturalWidth>0')
                        link = page.locator(f'[data-test-game="{card["key"]}"] a')
                        expect(link).to_have_attribute('href', card['url'])
                        box = link.bounding_box()
                        assert box['height'] >= 44 and box['x'] >= 0 and box['x'] + box['width'] <= width + 1
                    if path == '/arcade/control/' and width in (390, 1440):
                        page.evaluate('window.scrollTo(0, 0)')
                        page.screenshot(path=str(output / f'{width}-lab.png'), full_page=True)
                    page.locator('#lab-competition>summary').click()
                    expect(page.locator('#arcade-game-select')).to_be_visible()
                    assert page.locator('#arcade-game-select option').evaluate_all('(nodes)=>nodes.map(n=>n.value)') == ['flappy', 'doodle_jump']
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                    page.locator('#lab-wheel>summary').click()
                    expect(page.locator('#test-wheel-spin')).to_be_visible()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), ('open-wheel', width)
                # Click every real card and verify the appropriate game surface opens.
                if width in (390, 1440):
                    page.locator('#test-wheel-outcome').select_option('pit_wall')
                    page.locator('#test-wheel-spin').click()
                    expect(page.locator('#test-wheel-apply')).to_be_visible()
                    page.locator('#test-wheel-apply').click()
                    expect(page.locator('#test-wheel-outcome-summary')).to_contain_text('+2')
                    for card in cards:
                        page.goto(base + '/arcade/control/', wait_until='networkidle')
                        page.locator(f'[data-test-game="{card["key"]}"] a').click()
                        page.wait_for_load_state('networkidle')
                        assert not errors, errors
                        selector = {'doodle_jump': '#doodle-canvas', 'flappy': '#arcade-canvas',
                                    'minesweeper': '#minesweeper-game-screen', 'tetris': '#tetris-canvas'}[card['key']]
                        expect(page.locator(selector)).to_be_visible()
                        if card['key'] == 'minesweeper':
                            expect(page.locator(selector)).to_have_attribute('data-test-mode', 'true')
                            page.locator('#minesweeper-start').click()
                            expect(page.locator('#minesweeper-overlay')).to_be_hidden()
                            page.locator('.minesweeper-cell').first.click()
                            expect(page.locator('.minesweeper-cell.is-open').first).to_be_visible()
                context.close()
            browser.close()
        assert not errors, errors
        assert not writes, writes
        print(f'Arcade lab OK ({engine}): seven widths, four real test links, empty/active/expired states, disclosures, isolated minesweeper, no POSTs. {output}')
    finally:
        server.shutdown()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', choices=('chromium', 'webkit'), default='chromium')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    run(args.browser, args.output_dir)
