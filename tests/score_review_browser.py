"""Published score UI with synthetic accounts in an ephemeral database only."""
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
from league.models import DriverProfile, Event, Prediction, Result, Score, Season


def render_pages(portraits):
    call_command('migrate', verbosity=0, interactive=False)
    Season.objects.update_or_create(year=2026, defaults={'is_active': True})
    if portraits:
        for driver in DriverProfile.objects.filter(season_year=2026):
            if (portraits / f'{driver.key}.webp').exists():
                driver.portrait_url = f'/portraits/{driver.key}.webp'
                driver.save(update_fields=['portrait_url'])
    player = User.objects.create_user('review-player', first_name='Александр')
    now = timezone.now()
    event = Event.objects.create(name='Сан-Паулу, Бразилия', season_year=2026, round_number=20,
        has_sprint=True, deadline=now-timedelta(days=3), race_datetime=now-timedelta(days=1), status=Event.Status.SCORED)
    values = dict(p1='russell', p2='leclerc', p3='norris', pole='leclerc', fastest_lap='piastri',
        driver_of_day='norris', safety_car_count=0, dnf_count=2,
        sprint_qualifying_winner='piastri', sprint_winner='norris')
    prediction = Prediction.objects.create(user=player, event=event, **values,
        crazy_prediction='Рассел выиграет гонку после дождевого рестарта, а Ferrari проведёт лучший пит-стоп уик-энда.')
    Prediction.objects.filter(pk=prediction.pk).update(created_at=event.deadline-timedelta(hours=1))
    Result.objects.create(event=event, **{**values, 'p2':'norris', 'p3':'leclerc', 'dnf_count':3},
        driver_of_day_multiple=['norris','piastri'])
    Score.objects.create(user=player, event=event, points=31,
        breakdown={'P1':10,'P2 (Top-3)':3,'Pole Position':3,'Fastest Lap':3,
                   'Driver of the Day':3,'Safety Car Count':3,'Sprint Winner':3,
                   'Sprint Qualifying Winner':3,'Crazy Prediction':5,'Дуэль':-5})
    client = Client()
    client.force_login(player)
    url = reverse('league:score_detail', args=[event.pk, player.pk])
    page = client.get(url)
    assert page.status_code == 200
    pages = {'/review/': page.content}
    player.first_name = 'Оченьдлинноеимяучастникабезпробелов' * 2
    player.save(update_fields=['first_name'])
    DriverProfile.objects.filter(season_year=2026).delete()
    pages['/fallback/'] = client.get(url).content
    return pages


def run(engine, output, portraits):
    with override_settings(ALLOWED_HOSTS=['testserver'], STORAGES={
        'default': {'BACKEND':'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }):
        pages = render_pages(portraits)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            route = urlsplit(self.path).path
            if route in pages:
                body, mime = pages[route], 'text/html; charset=utf-8'
            elif route.startswith('/static/') and (filename := finders.find(route[8:])):
                body, mime = Path(filename).read_bytes(), mimetypes.guess_type(filename)[0]
            elif portraits and route.startswith('/portraits/') and (filename := portraits / Path(route).name).is_file():
                body, mime = filename.read_bytes(), 'image/webp'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', mime or 'application/octet-stream')
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    output.mkdir(parents=True, exist_ok=True)
    errors, writes = [], []
    try:
        with sync_playwright() as pw:
            browser = getattr(pw, engine).launch()
            for width in (320,390,700,844,1280,1440,1920):
                context = browser.new_context(viewport={'width':width,'height':950}, device_scale_factor=2)
                context.route('https://**', lambda route: route.abort())
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('request', lambda req: writes.append(req.url) if req.method == 'POST' else None)
                for route in pages:
                    page.goto(f'http://127.0.0.1:{server.server_port}{route}', wait_until='networkidle')
                    expect(page.locator('.sr-row')).to_have_count(10)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), (width,route)
                    expect(page.locator('.sr-total strong')).to_have_text('31')
                    expect(page.locator('#score-review-title')).to_have_text('Сан-Паулу, Бразилия')
                    expect(page.locator('.sr-hero .sr-eyebrow')).to_contain_text('R20 · 2026')
                    expect(page.locator('a[href*="/recap/"]')).to_have_count(0)
                    expect(page.locator('[data-recap-canvas],[data-recap-download]')).to_have_count(0)
                    expect(page.locator('[data-reactions],[data-reaction-form]')).to_have_count(0)
                    assert 'Очки взяты из сохранённого зачёта' not in page.locator('.score-review').inner_text()
                    expect(page.locator('.sr-row.is-partial')).to_have_count(1)
                    expect(page.locator('.sr-value').first).to_have_text('0')
                    if width <= 700:
                        for row in page.locator('.sr-row').all():
                            category = row.locator('.sr-category').bounding_box()
                            assert category['width'] >= row.bounding_box()['width'] - 3
                            assert category['height'] < 130, 'Category titles must not collapse into one-letter columns'
                    for driver in page.locator('.sr-driver-photo').all():
                        r = driver.bounding_box()
                        assert r['width'] == r['height'] and r['width'] >= 38
                        assert driver.evaluate('el=>getComputedStyle(el).boxShadow') == 'none'
                    if route == '/review/' and width in (390,1440):
                        if portraits:
                            for image in page.locator('img[data-driver-photo][src^="/portraits/"]').all():
                                image.scroll_into_view_if_needed()
                                expect(image).to_have_js_property('complete', True)
                                assert image.evaluate('el=>el.naturalWidth>0')
                        page.evaluate('scrollTo(0,0)')
                        page.screenshot(path=str(output / f'{engine}-{width}.png'), full_page=True)
                context.close()
            browser.close()
        assert not errors, errors
        assert not writes, writes
        print(f'Score review {engine}: seven widths, portraits, multi-winner, zero counts, partial credit, long names and missing-photo fallback; no overflow, script errors or writes. {output}')
    finally:
        server.shutdown()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', choices=['chromium','webkit'], default='chromium')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--portraits-dir', type=Path)
    args = parser.parse_args()
    run(args.browser, args.output_dir, args.portraits_dir)
