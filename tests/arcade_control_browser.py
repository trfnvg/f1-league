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
from league.models import ArcadeCompetition, ArcadeSettings, Event, Season


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
    future = Event.objects.create(name='Сан-Паулу, Бразилия', round_number=20, season_year=season.year,
        deadline=now+timedelta(days=8), race_datetime=now+timedelta(days=10))
    client.post(reverse('league:arcade_control'), {'action': 'select', 'competition_event': future.pk, 'active_game': 'flappy'})
    response = client.get(reverse('league:arcade_control'))
    cards = response.context['test_games']
    pages = {reverse('league:arcade_control'): response.content}
    pages[reverse('league:arcade_control') + f'?season={season.year}&event={event.pk}'] = response.content
    future_url = reverse('league:arcade_control') + f'?season={season.year}&event={future.pk}'
    pages[future_url] = client.get(future_url).content
    for card in cards:
        pages[card['url']] = client.get(card['url']).content
    event.deadline = now - timedelta(hours=1)
    event.save(update_fields=['deadline'])
    pages['/lab-expired/'] = client.get(reverse('league:arcade_control')).content
    settings.public_enabled = False
    settings.competition_event = None
    settings.competition_opened_at = None
    settings.save()
    ArcadeCompetition.objects.filter(event=future).delete()
    pages['/lab-empty/'] = client.get(reverse('league:arcade_control')).content
    return pages, cards, future.pk


def run(engine, output):
    with override_settings(ALLOWED_HOSTS=['testserver'], STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }):
        pages, cards, future_id = fixtures()

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
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # A stage change can cancel an in-flight image request.

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
                    expect(page.locator('.lab-game-card')).to_have_count(5)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), (width, path)
                    assert page.locator('#lab-competition').evaluate('node=>node.open')
                    expect(page.locator('#arcade-game-select')).to_be_visible()
                    expect(page.locator('#arcade-event-select')).to_be_enabled()
                    expect(page.locator('.lab-stage-picker button')).to_be_hidden()
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
                    expect(page.locator('#arcade-game-select')).to_be_visible()
                    assert page.locator('#arcade-game-select option').evaluate_all('(nodes)=>nodes.map(n=>n.value).filter(Boolean)') == ['tetris', 'flappy', 'doodle_jump']
                    expect(page.locator('.lab-library-option input')).to_have_count(3)
                    expect(page.locator('.lab-library-option input[value="tetris"]')).to_be_checked()
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
                    page.goto(base + '/arcade/control/', wait_until='networkidle')
                    page.evaluate('window.labDocumentMarker = "same-document"')
                    page.locator('.lab-library-option input[value="tetris"]').uncheck()
                    original_event_id = page.locator('#arcade-event-select').input_value()
                    page.locator('#arcade-event-select').scroll_into_view_if_needed()
                    scroll_before = page.evaluate('scrollY')
                    page.select_option('#arcade-event-select', str(future_id))
                    expect(page.locator('#arcade-game-select')).to_have_value('flappy')
                    expect(page.locator('.lab-competition-form [name=competition_event]')).to_have_value(str(future_id))
                    expect(page.locator('.lab-competition-form [value=publish]')).to_be_disabled()
                    expect(page.locator('.lab-competition-form [value=select]')).to_be_hidden()
                    expect(page.locator('.lab-selected-stage strong')).to_have_text('Сан-Паулу, Бразилия')
                    assert page.evaluate('window.labDocumentMarker') == 'same-document'
                    assert abs(page.evaluate('scrollY') - scroll_before) < 3
                    expect(page.locator('.lab-library-option input[value="tetris"]')).not_to_be_checked()
                    # Only autosave is permitted; it must never publish the contest.
                    fail_save = [True]
                    def save_route(route):
                        if route.request.method != 'POST':
                            route.continue_()
                            return
                        assert 'name="action"\r\n\r\nselect' in route.request.post_data
                        route.fulfill(status=400 if fail_save[0] else 200,
                            content_type='application/json', body='{"ok":false,"message":"Test failure"}' if fail_save[0] else '{"ok":true}')
                    page.route('**/arcade/control/**', save_route)
                    page.select_option('#arcade-game-select', 'tetris')
                    expect(page.locator('.lab-save-status')).to_contain_text('Не удалось подтвердить сохранение')
                    expect(page.locator('.lab-competition-form [value=select]')).to_be_visible()
                    fail_save[0] = False
                    page.locator('.lab-competition-form [value=select]').click()
                    expect(page.locator('.lab-save-status')).to_contain_text('Сохранено')
                    expect(page.locator('#arcade-event-select')).to_be_enabled()
                    expect(page.locator('.lab-competition-form [value=select]')).to_be_hidden()
                    expect(page.locator('#arcade-game-select')).to_have_value('tetris')
                    assert page.evaluate('window.labDocumentMarker') == 'same-document'
                    page.screenshot(path=str(output / f'{width}-future-stage.png'), full_page=True)
                    page.go_back(wait_until='networkidle')
                    expect(page.locator('.lab-selected-stage strong')).to_have_text('Мехико, Мексика')
                    expect(page.locator('#arcade-event-select')).to_have_value(original_event_id)
                    assert page.evaluate('window.labDocumentMarker') == 'same-document'
                    # Failed reads keep the previous editor and restore its selected GP.
                    def failed_read(route):
                        route.fulfill(status=503, body='Unavailable')
                    page.route('**/arcade/control/?season=*&event=*', failed_read)
                    page.select_option('#arcade-event-select', str(future_id))
                    expect(page.locator('#lab-stage-status')).to_contain_text('Не удалось загрузить')
                    expect(page.locator('#arcade-event-select')).to_have_value(original_event_id)
                    expect(page.locator('.lab-selected-stage strong')).to_have_text('Мехико, Мексика')
                    page.unroute('**/arcade/control/?season=*&event=*', failed_read)
                    page.select_option('#arcade-event-select', str(future_id))
                    page.select_option('#arcade-event-select', original_event_id)
                    expect(page.locator('#lab-stage-status')).to_be_empty()
                    expect(page.locator('.lab-selected-stage strong')).to_have_text('Мехико, Мексика')
                    expect(page.locator('#arcade-event-select')).to_have_value(original_event_id)
                    for card in cards:
                        page.goto(base + '/arcade/control/', wait_until='networkidle')
                        page.locator(f'[data-test-game="{card["key"]}"] a').click()
                        page.wait_for_load_state('networkidle')
                        assert not errors, errors
                        selector = {'vegas': '#vegas-machine', 'doodle_jump': '#doodle-canvas', 'flappy': '#arcade-canvas',
                                    'minesweeper': '#minesweeper-game-screen', 'tetris': '#tetris-launch-start' if width <= 600 else '#tetris-canvas'}[card['key']]
                        expect(page.locator(selector)).to_be_visible()
                        if card['key'] == 'minesweeper':
                            expect(page.locator(selector)).to_have_attribute('data-test-mode', 'true')
                            page.locator('#minesweeper-start').click()
                            expect(page.locator('#minesweeper-overlay')).to_be_hidden()
                            page.locator('.minesweeper-cell').first.click()
                            expect(page.locator('.minesweeper-cell.is-open').first).to_be_visible()
                context.close()
            # Progressive enhancement: manual GET navigation still works without JS.
            context = browser.new_context(viewport={'width': 390, 'height': 900}, java_script_enabled=False)
            context.route('https://**', lambda route: route.abort())
            page = context.new_page()
            page.goto(base + '/arcade/control/', wait_until='networkidle')
            expect(page.locator('.lab-stage-picker button')).to_be_visible()
            page.select_option('#arcade-event-select', str(future_id))
            expect(page.locator('.lab-selected-stage strong')).to_have_text('Мехико, Мексика')
            page.locator('.lab-stage-picker button').click()
            expect(page.locator('.lab-selected-stage strong')).to_have_text('Сан-Паулу, Бразилия')
            expect(page.locator('#arcade-game-select')).to_have_value('flappy')
            context.close()
            browser.close()
        assert not errors, errors
        assert len(writes) == 4, writes  # One failed autosave + one explicit retry at each test width.
        print(f'Arcade lab OK ({engine}): seven widths, same-document stage selection/back, stable scroll, unsaved library retained, autosave/retry, failed reads, four test games, no publishing. {output}')
    finally:
        server.shutdown()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', choices=('chromium', 'webkit'), default='chromium')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    run(args.browser, args.output_dir)
