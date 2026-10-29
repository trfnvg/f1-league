"""Mobile viewport regression using real templates and an ephemeral database."""
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
import threading
from urllib.parse import urlsplit

from nightshift_browser import render_pages, override_settings, finders, sync_playwright
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse
from unittest.mock import patch
from league.models import LeagueSeason, LeagueMembership, LeagueSeasonEntry


def run():
    with override_settings(ALLOWED_HOSTS=['testserver'], MEDIA_URL='/media/', STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }):
        pages = render_pages()
        season = LeagueSeason.objects.filter(is_legacy=True).first()
        client = Client()
        client.force_login(season.league.owner)
        url = reverse('league:friend_league', args=[season.league_id])
        with patch('league.league_views.current_invite', return_value=None):
            pages['/league-owner/'] = client.get(url).content
        season.league.name = 'Высокогорный паддок — ' + 'W' * 59
        season.league.save(update_fields=['name'])
        for number in range(30):
            user = User.objects.create_user(f'{number:02d}_' + 'long_name_' * 12)
            member = LeagueMembership.objects.create(league=season.league, user=user)
            LeagueSeasonEntry.objects.create(league_season=season, membership=member,
                first_event=season.start_event)
        pages['/league-many/'] = client.get(url).content
        with patch('league.league_views.select_current_event', return_value=None):
            pages['/league-no-event/'] = client.get(url).content

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            route = urlsplit(self.path).path
            if route in pages:
                body, mime = pages[route], 'text/html; charset=utf-8'
            elif route.startswith('/static/') and (filename := finders.find(route[8:])):
                body = Path(filename).read_bytes()
                mime = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    output = Path('/tmp/fastlap-league-dashboard')
    output.mkdir(exist_ok=True)
    try:
        with sync_playwright() as pw:
            for engine in ('webkit', 'chromium'):
                browser = getattr(pw, engine).launch()
                for width in (320, 390, 430, 844, 1440):
                    context = browser.new_context(viewport={'width': width, 'height': 844},
                        is_mobile=width < 900, has_touch=width < 900, device_scale_factor=2)
                    page = context.new_page()
                    for route in ('/league/', '/league-long/', '/league-owner/', '/league-many/', '/league-no-event/'):
                        page.goto(f'http://127.0.0.1:{server.server_port}{route}', wait_until='networkidle')
                        page.wait_for_timeout(300)
                        metrics = page.evaluate('''() => ({inner:innerWidth,
                            width:document.documentElement.scrollWidth,
                            visual:visualViewport.width, scale:visualViewport.scale,
                            oversized:[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1 && !e.closest('.classification-viewport')).slice(0,8).map(e=>[e.tagName,e.className,e.getBoundingClientRect().right])})''')
                        print(engine, width, route, json.dumps(metrics), flush=True)
                        if metrics['width'] > width + 1:
                            print(page.evaluate('''() => [...document.querySelectorAll('body *')].filter(e=>e.scrollWidth>e.clientWidth+20).slice(0,12).map(e=>({tag:e.tagName,cls:String(e.className),width:e.clientWidth,scroll:e.scrollWidth,overflow:getComputedStyle(e).overflow}))'''), flush=True)
                            page.screenshot(path=str(output/'overflow.png'), full_page=True)
                        assert metrics['inner'] <= width + 1, metrics
                        assert metrics['width'] <= width + 1, metrics
                        assert abs(metrics['scale'] - 1) < .01, metrics
                        page.locator('.league-switch summary').click()
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                        page.locator('.league-switch summary').click()
                        frame = page.locator('.classification-viewport')
                        pinned = frame.locator('tbody tr:first-child .classification-identity')
                        before = pinned.bounding_box()
                        frame.evaluate('e=>e.scrollLeft=e.scrollWidth')
                        after = pinned.bounding_box()
                        assert abs(before['x'] - after['x']) < 1
                        assert abs(before['y'] - after['y']) < 1
                        assert frame.evaluate('e=>e.scrollHeight<=e.clientHeight+1')
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                        if page.locator('[data-copy-invite]').count():
                            page.evaluate("Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{}}})")
                            page.locator('[data-copy-invite]').click()
                            assert 'Ссылка скопирована' in page.locator('[data-copy-status]').inner_text()
                        # Rotation must not leave the portrait layout permanently shrunken.
                        if width == 390:
                            page.set_viewport_size({'width': 844, 'height': 390})
                            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                            page.set_viewport_size({'width': width, 'height': 844})
                            assert page.evaluate('innerWidth===390 && Math.abs(visualViewport.scale-1)<.01')
                        page.screenshot(path=str(output/f'{engine}-{width}-{route.strip("/")}.png'), full_page=True)
                    context.close()
                browser.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    run()
