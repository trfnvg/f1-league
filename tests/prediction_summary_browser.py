"""Forecast portraits and live summary, using synthetic data in memory only."""
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
from league.models import DriverProfile, Event, Prediction, Season


def render_pages(portraits):
    call_command('migrate', verbosity=0, interactive=False)
    Season.objects.update_or_create(year=2026, defaults={'is_active': True})
    if portraits:
        for profile in DriverProfile.objects.filter(season_year=2026):
            if (portraits / f'{profile.key}.webp').exists():
                profile.portrait_url = f'/portraits/{profile.key}.webp'
                profile.save(update_fields=['portrait_url'])
    player = User.objects.create_user('forecast-player', first_name='Тестовый игрок')
    now = timezone.now()
    values = dict(p1='russell', p2='leclerc', p3='norris', pole='leclerc',
        fastest_lap='russell', driver_of_day='norris', safety_car_count=0, dnf_count=0,
        sprint_qualifying_winner='norris', sprint_winner='leclerc',
        crazy_prediction='Дождь, неожиданный подиум и длинный крейзи-предикт.\nВторая строка.')
    client = Client()
    client.force_login(player)
    pages = {}
    for route, closed in (('/open/', False), ('/closed/', True)):
        event = Event.objects.create(name='Сан-Паулу, Бразилия', season_year=2026,
            round_number=20 if closed else 21, has_sprint=True,
            deadline=now+timedelta(days=-1 if closed else 7), race_datetime=now+timedelta(days=9))
        Prediction.objects.create(event=event, user=player, **values)
        response = client.get(reverse('league:event_detail', args=[event.pk]))
        assert response.status_code == 200
        pages[route] = response.content
    DriverProfile.objects.filter(season_year=2026).update(
        surname='Оченьдлиннаяфамилиягонщикабезпробелов', portrait_url='/portraits/missing.webp')
    pages['/missing/'] = client.get(reverse('league:event_detail', args=[event.pk])).content
    DriverProfile.objects.filter(season_year=2026).delete()
    pages['/no-roster/'] = client.get(reverse('league:event_detail', args=[event.pk])).content
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
                    if route == '/open/':
                        summary = page.locator('[data-live-summary]')
                        expect(summary).to_be_visible()
                        expect(summary.locator('.forecast-driver')).to_have_count(8)
                        expect(summary.locator('[data-summary-field="p1"] strong')).to_have_text('Рассел')
                        expect(summary.locator('[data-summary-field="safety_car_count"] dd')).to_have_text('0')
                        page.evaluate('''() => {
                            window.forecastPhotos=[...document.querySelectorAll('.prediction-summary-lines img')];
                            window.forecastMutations=0;
                            window.forecastObserver=new MutationObserver(r=>window.forecastMutations+=r.length);
                            document.querySelectorAll('[data-summary-field]:not([data-summary-field="crazy_prediction"])').forEach(n=>
                                window.forecastObserver.observe(n,{subtree:true,attributes:true,childList:true,characterData:true}));
                        }''')
                        page.locator('#id_crazy_prediction').press_sequentially(' Ещё текст', delay=3)
                        expect(summary.locator('[data-summary-field="crazy_prediction"] dd')).to_contain_text('Ещё текст')
                        assert page.evaluate('window.forecastMutations') == 0
                        assert page.evaluate('window.forecastPhotos.every(img=>img.isConnected)')
                        page.evaluate('window.forecastObserver.disconnect()')
                        page.locator('.prediction-podium-slot').first.click()
                        page.locator('[data-driver="norris"]').click()
                        expect(summary.locator('[data-summary-field="p1"] strong')).to_have_text('Норрис')
                        expect(summary.locator('[data-summary-field="p3"] strong')).to_have_text('Рассел')
                        page.evaluate('''() => {
                            document.querySelector('#race-prediction-form').addEventListener('submit', e=>{
                                e.preventDefault();window.savedForecast=Object.fromEntries(new FormData(e.target));
                            });
                        }''')
                        summary.locator('button[type="submit"]').click()
                        data = page.evaluate('window.savedForecast')
                        assert (data['p1'],data['p3'],data['safety_car_count'],data['dnf_count']) == ('norris','russell','0','0')
                    else:
                        page.locator('.stage-sections a[href="#stage-prediction"]').click()
                        summary = page.locator('.stage-forecast')
                        expect(summary).to_be_visible()
                        expect(summary.locator('.forecast-answer')).to_have_count(8)
                        assert summary.locator('.forecast-count dd').all_text_contents() == ['0','0']
                        if route == '/no-roster/':
                            expect(summary.locator('img')).to_have_count(0)
                            expect(summary.locator('[data-forecast-answer="p1"] strong')).to_have_text('Рассел')
                        if width <= 600:
                            boxes = summary.locator('.forecast-podium .forecast-answer').evaluate_all('ns=>ns.map(n=>n.getBoundingClientRect().y)')
                            assert boxes[0] < boxes[1] < boxes[2]
                    summary.scroll_into_view_if_needed()
                    if portraits and route in ('/open/','/closed/'):
                        for img in summary.locator('img[src^="/portraits/"]').all():
                            img.scroll_into_view_if_needed()
                            expect(img).to_have_js_property('complete', True)
                            assert img.evaluate('n=>n.naturalWidth>0')
                    for photo in summary.locator('.forecast-photo').all():
                        rect = photo.bounding_box()
                        assert abs(rect['width']-rect['height']) < 1
                        assert photo.evaluate('n=>getComputedStyle(n).boxShadow') == 'none'
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'), (width,route)
                    if width in (390,1440) and route in ('/open/','/closed/'):
                        summary.screenshot(path=str(output/f'{engine}-{width}-{route.strip("/")}.png'))
                context.close()
            browser.close()
        assert not errors, errors
        assert not writes, writes
        print(f'Forecast summary {engine}: seven widths; saved/live portraits, swaps, zero, fallback, stable typing and form submission OK. {output}')
    finally:
        server.shutdown()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', choices=['chromium','webkit'], default='chromium')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--portraits-dir', type=Path)
    args = parser.parse_args()
    run(args.browser, args.output_dir, args.portraits_dir)
