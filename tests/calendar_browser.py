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
from league.calendar_event_sync import sync_calendar_events_v1


def run(browser_name, output):
    call_command("migrate", verbosity=0, interactive=False)
    now = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
    event = Event.objects.create(name="Мехико, Мексика", circuit="mexico", round_number=19,
        deadline=now + timedelta(days=2), race_datetime=now + timedelta(days=4), season_year=2026,
        cover_image="event_covers/my-mexico.jpg")
    sync_calendar_events_v1(2026)
    with override_settings(ALLOWED_HOSTS=["testserver"], MEDIA_URL="/media/", STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }), patch("league.race_calendar.timezone.now", return_value=now):
        page_html = Client().get(reverse("league:calendar")).content
        home_html = Client().get(reverse("league:home")).content

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            if path == "/calendar/":
                body, content_type = page_html, "text/html; charset=utf-8"
            elif path == "/":
                body, content_type = home_html, "text/html; charset=utf-8"
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
                    timezone_id="America/Los_Angeles", reduced_motion="reduce",
                    device_scale_factor=3 if width == 390 else 1)
                # The calendar/globe is entirely local. Keep QA independent of font/CDN availability.
                context.route("https://**", lambda route: route.abort())
                page = context.new_page()
                page.clock.set_fixed_time(now)
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/calendar/", wait_until="networkidle")
                assert page.locator(".rc-card").count() == 23
                assert page.locator('.rc-card-footer .rc-button').evaluate_all("nodes=>nodes.every(node=>node.getAttribute('href').startsWith('/events/'))")
                assert page.locator('[data-calendar-filters] button').all_text_contents() == ['Предстоящие', 'Все']
                assert page.locator('[data-filter="sprint"]').count() == 0
                assert page.locator('[data-filter="upcoming"]').get_attribute('aria-pressed') == 'true'
                assert page.locator('.rc-card:visible').count() == 5
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
                globe = page.locator('[data-race-globe]')
                assert globe.is_visible()
                page.wait_for_function("document.querySelector('[data-race-globe]').dataset.globeRenderer")
                assert globe.get_attribute('data-globe-renderer') == 'webgl', (browser_name, width)
                assert page.locator('[data-globe-canvas]').evaluate('node => node.width <= Math.ceil(node.getBoundingClientRect().width * 2)')
                assert page.locator('[data-globe-race]').count() == 23
                assert page.locator('[data-globe-race][aria-pressed=true]').get_attribute('data-globe-race') == 'mexico'
                assert page.locator('[data-globe-cover]').get_attribute('src') == '/media/event_covers/my-mexico.jpg'
                assert page.locator('[data-globe-open]').get_attribute('href') == reverse('league:event_detail', args=[event.pk])
                assert page.locator('[data-globe-location]').inner_text() == 'Мехико'
                assert page.locator('[data-globe-race-time]').inner_text() == '01.11 · 23:00'
                assert page.locator('[data-globe-clock]').is_visible()
                assert page.locator('[data-globe-clock-value]').all_text_contents() == ['04', '08', '00', '00']
                assert page.locator('[data-globe-track-start]').get_attribute('cx') is not None
                assert page.locator('[data-globe-motion] svg').count() == 1
                assert page.locator('.rg-pin.is-labelled').count() == 0
                assert page.locator('.rg-pin-label').evaluate_all("labels => labels.every(node => getComputedStyle(node).opacity === '0')")
                assert page.locator('[data-globe-stage]').evaluate("node => getComputedStyle(node).touchAction") == 'none'
                # Idle WebGL does not spin a permanent requestAnimationFrame loop.
                page.wait_for_timeout(120)
                idle_frame = globe.get_attribute('data-globe-frame')
                page.wait_for_timeout(180)
                assert globe.get_attribute('data-globe-frame') == idle_frame
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
                globe.screenshot(path=str(output / f"{width}-globe.png"))
                # Strip selection centres the Earth; arrows/zoom/drag work on the same renderer.
                page.locator('[data-globe-race=melbourne]').click()
                page.locator('[data-globe-stage]').scroll_into_view_if_needed()
                assert page.locator('[data-globe-location]').inner_text() == 'Мельбурн'
                assert page.locator('[data-globe-clock]').is_hidden()
                assert page.locator('[data-globe-countdown]').inner_text() == 'Этап завершён'
                try:
                    page.wait_for_function("!document.querySelector('[data-globe-pin=melbourne]').hidden", timeout=5000)
                except Exception:
                    page.screenshot(path=str(output / f'{width}-globe-failure.png'))
                    print('Globe state:', width, globe.get_attribute('data-globe-renderer'), globe.get_attribute('data-globe-visible'), flush=True)
                    raise
                stage = page.locator('[data-globe-stage]')
                stage.focus()
                if width == 1440:
                    get_axes = """node => {const gl=node.getContext('webgl'),program=gl.getParameter(gl.CURRENT_PROGRAM);
                        return Array.from(gl.getUniform(program,gl.getUniformLocation(program,'axes')));}"""
                    canvas = page.locator('[data-globe-canvas]')
                    start_axes = canvas.evaluate(get_axes)
                    for direction in ('ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'):
                        for _ in range(30):
                            page.keyboard.press(direction)
                        page.wait_for_timeout(80)
                        axes = canvas.evaluate(get_axes)
                        assert max(abs(a-b) for a,b in zip(axes,start_axes)) < .005, (direction, axes)
                    for offset in (0, 3, 6):
                        assert abs(sum(value*value for value in axes[offset:offset+3])-1) < .0001
                    for a, b in ((0, 3), (0, 6), (3, 6)):
                        assert abs(sum(axes[a+i]*axes[b+i] for i in range(3))) < .0001
                before = page.locator('[data-globe-pin=melbourne]').get_attribute('style')
                page.keyboard.press('ArrowLeft')
                page.wait_for_function("node => node.getAttribute('style') !== " + repr(before), arg=page.locator('[data-globe-pin=melbourne]').element_handle())
                stage_box = stage.bounding_box()
                page.mouse.move(stage_box['x'] + stage_box['width'] * .22, stage_box['y'] + stage_box['height'] * .6)
                page.mouse.down()
                page.mouse.move(stage_box['x'] + stage_box['width'] * .4, stage_box['y'] + stage_box['height'] * .6, steps=6)
                page.mouse.up()
                if width == 1440:
                    before_scroll = page.evaluate('scrollY')
                    page.mouse.wheel(0, 160)
                    page.wait_for_timeout(150)
                    assert page.evaluate('scrollY') > before_scroll + 20, 'Focused map must not hijack wheel scrolling'
                    stage.scroll_into_view_if_needed()
                page.locator('[data-globe-zoom="1"]').click()
                page.locator('[data-globe-home]').click()
                assert page.locator('[data-globe-location]').inner_text() == 'Мехико'
                assert page.locator('[data-globe-clock]').is_visible()
                page.locator('[data-globe-pin=mexico]').hover()
                assert page.locator('[data-globe-location]').inner_text() == 'Мехико'
                page.locator('[data-globe-pin=las-vegas]').hover()
                assert page.locator('[data-globe-location]').inner_text() == 'Мехико'
                assert page.locator('[data-globe-pin=las-vegas] .rg-pin-label').evaluate("node => getComputedStyle(node).opacity") == '0'
                page.locator('[data-globe-pin=las-vegas]').click()
                assert page.locator('[data-globe-location]').inner_text() == 'Лас-Вегас'
                page.wait_for_function("document.querySelector('[data-globe-pin=las-vegas]').classList.contains('is-labelled')")
                assert page.locator('.rg-pin.is-labelled').count() == 1
                page.locator('[data-globe-home]').click()
                page.locator('[data-globe-home]').hover()
                assert page.locator('[data-globe-location]').inner_text() == 'Мехико'
                page.locator('[data-globe-step="1"]').click()
                assert page.locator('[data-globe-location]').inner_text() == 'Сан-Паулу'
                page.locator('[data-globe-step="-1"]').click()
                page.locator('[data-globe-motion]').click()
                assert page.locator('[data-globe-motion]').get_attribute('aria-pressed') == 'false'  # Reduced motion.
                page.select_option("#calendar-timezone", "device")
                assert page.locator(".rc-feature-times time").last.inner_text() == "01.11 · 12:00"
                assert page.locator('[data-globe-race-time]').inner_text() == '01.11 · 12:00'
                page.select_option("#calendar-timezone", "venue")
                assert page.locator(".rc-feature-times time").last.inner_text() == "01.11 · 14:00"
                assert "по месту проведения" in page.locator("[data-calendar-zone-note]").inner_text()
                page.reload(wait_until="networkidle")
                assert page.locator("#calendar-timezone").input_value() == "venue"
                page.select_option("#calendar-timezone", "Europe/Moscow")
                page.locator('[data-filter="upcoming"]').click()
                assert page.locator(".rc-card:visible").count() == 5
                assert page.locator('[data-filter="upcoming"]').get_attribute("aria-pressed") == "true"
                page.locator('[data-filter="all"]').click()
                assert page.locator(".rc-card:visible").count() == 23
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), width
                page.locator('.rc-month-nav a[href="#calendar-month-11"]').click()
                assert page.locator("#calendar-month-11").is_visible()
                page.locator(".rc-credits summary").click()
                assert page.locator(".rc-credits li:visible").count() == 22
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), width
                page.locator('[data-globe-race=melbourne]').click()
                page.locator('[data-filter="upcoming"]').click()
                assert page.locator('#grand-prix-melbourne').is_hidden()
                page.locator('[data-globe-schedule]').click()
                assert page.locator('#grand-prix-melbourne').is_visible()
                assert page.locator('[data-filter="all"]').get_attribute('aria-pressed') == 'true'
                page.goto(base + '/', wait_until='networkidle')
                assert page.locator('#calendar').count() == 0
                assert page.locator('.event-editorial-card').count() == 0
                assert page.locator('#featured-gp-title').is_visible()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
                context.close()
            # Real touch input, orientation changes, automatic rotation suspended off-screen.
            context = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
            context.route('https://**', lambda route: route.abort())
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base + '/calendar/', wait_until='networkidle')
            page.wait_for_function("document.querySelector('[data-race-globe]').dataset.globeRenderer === 'webgl'")
            page.locator('[data-globe-race=monaco]').tap()
            assert page.locator('[data-globe-location]').inner_text() == 'Монако'
            page.locator('[data-globe-stage]').scroll_into_view_if_needed()
            stage = page.locator('[data-globe-stage]')
            page.locator('[data-globe-home]').tap()
            page.wait_for_timeout(500)
            page.locator('[data-globe-pin=las-vegas]').tap()
            assert page.locator('[data-globe-location]').inner_text() == 'Лас-Вегас'
            assert page.locator('.rg-pin.is-labelled').count() == 1
            page.locator('[data-globe-home]').tap()
            page.wait_for_timeout(500)
            if browser_name == 'chromium':
                # Trusted mobile touch input, not synthetic JS pointer events.
                # CDP is restricted to this disposable Playwright test context.
                touch = context.new_cdp_session(page)
                box = stage.bounding_box()
                cx, cy = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
                get_axes = """node => {const gl=node.getContext('webgl'),program=gl.getParameter(gl.CURRENT_PROGRAM);
                    return Array.from(gl.getUniform(program,gl.getUniformLocation(program,'axes')));}"""
                get_radius = """node => {const gl=node.getContext('webgl'),program=gl.getParameter(gl.CURRENT_PROGRAM);
                    return gl.getUniform(program,gl.getUniformLocation(program,'radius'));}"""
                canvas = page.locator('[data-globe-canvas]')
                initial_scroll = page.evaluate('[scrollX, scrollY, visualViewport.scale]')

                def swipe(start, end):
                    touch.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': start[0], 'y': start[1], 'id': 1}]})
                    for step in range(1, 7):
                        x = start[0] + (end[0]-start[0])*step/6
                        y = start[1] + (end[1]-start[1])*step/6
                        touch.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': x, 'y': y, 'id': 1}]})
                        page.wait_for_timeout(20)
                    touch.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
                    page.wait_for_timeout(80)

                for dx, dy in ((0, -70), (0, 70), (-65, 0), (65, 0), (45, -50)):
                    before = canvas.evaluate(get_axes)
                    swipe((cx, cy), (cx+dx, cy+dy))
                    after = canvas.evaluate(get_axes)
                    assert max(abs(a-b) for a,b in zip(before,after)) > .01, (dx, dy)
                    assert page.evaluate('[scrollX, scrollY, visualViewport.scale]') == initial_scroll
                    assert page.locator('[data-globe-race][aria-pressed=true]').get_attribute('data-globe-race') == 'mexico'
                # Pinching zooms the Earth, never the browser viewport.
                radius = canvas.evaluate(get_radius)
                touch.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': cx-30, 'y': cy, 'id': 1}, {'x': cx+30, 'y': cy, 'id': 2}]})
                for spread in (35, 45, 55, 65):
                    touch.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': cx-spread, 'y': cy, 'id': 1}, {'x': cx+spread, 'y': cy, 'id': 2}]})
                    page.wait_for_timeout(30)
                touch.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
                page.wait_for_timeout(80)
                assert canvas.evaluate(get_radius) > radius * 1.3
                assert page.evaluate('[scrollX, scrollY, visualViewport.scale]') == initial_scroll
                # Cancellation must release pointer state, allowing the next gesture.
                touch.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': cx, 'y': cy, 'id': 1}]})
                touch.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': cx+20, 'y': cy+20, 'id': 1}]})
                assert stage.evaluate("node => node.classList.contains('is-dragging')")
                touch.send('Input.dispatchTouchEvent', {'type': 'touchCancel', 'touchPoints': []})
                assert not stage.evaluate("node => node.classList.contains('is-dragging')")
                page.locator('[data-globe-home]').tap()
                page.wait_for_timeout(500)
                pin_box = page.locator('[data-globe-pin=las-vegas]').bounding_box()
                px, py = pin_box['x'] + pin_box['width']/2, pin_box['y'] + pin_box['height']/2
                swipe((px, py), (px+45, py+25))
                assert page.locator('[data-globe-location]').inner_text() == 'Мехико', 'Dragging a marker must not select it'
                # A browser-height change must not resize the map or shift the layout sideways.
                old_width = stage.bounding_box()['width']
                page.set_viewport_size({'width': 390, 'height': 720})
                assert stage.bounding_box()['width'] == old_width
                assert page.evaluate('scrollX === 0 && document.documentElement.scrollWidth <= innerWidth + 1')
                page.set_viewport_size({'width': 390, 'height': 844})
                page.locator('[data-globe-card]').scroll_into_view_if_needed()
                card_box = page.locator('[data-globe-card]').bounding_box()
                before_scroll = page.evaluate('scrollY')
                swipe((card_box['x']+25, card_box['y']+150), (card_box['x']+25, card_box['y']+50))
                assert page.evaluate('scrollY') > before_scroll + 20, 'Page scrolling outside the map must stay native'
                touch.detach()
                stage.scroll_into_view_if_needed()
            page.locator('[data-globe-home]').tap()
            stage.scroll_into_view_if_needed()
            page.locator('[data-globe-motion]').tap()
            page.wait_for_timeout(500)
            active_frames = int(page.locator('[data-race-globe]').get_attribute('data-globe-frame'))
            page.wait_for_timeout(250)
            assert int(page.locator('[data-race-globe]').get_attribute('data-globe-frame')) > active_frames
            page.locator('.rc-credits').scroll_into_view_if_needed()
            page.wait_for_timeout(150)
            stopped = page.locator('[data-race-globe]').get_attribute('data-globe-frame')
            page.wait_for_timeout(250)
            assert page.locator('[data-race-globe]').get_attribute('data-globe-frame') == stopped
            page.set_viewport_size({'width': 844, 'height': 390})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
            # Context loss must leave accessible race buttons and the original schedule intact.
            lost_context = page.evaluate_handle("document.querySelector('[data-globe-canvas]').getContext('webgl').getExtension('WEBGL_lose_context')")
            lost_context.evaluate('extension => extension.loseContext()')
            page.wait_for_function("document.querySelector('[data-race-globe]').dataset.globeRenderer === 'fallback'")
            page.locator('[data-globe-race=melbourne]').click()
            assert page.locator('[data-globe-location]').inner_text() == 'Мельбурн'
            assert page.locator('[data-globe-fallback]').is_visible()
            page.locator('[data-globe-stage]').scroll_into_view_if_needed()
            lost_context.evaluate('extension => extension.restoreContext()')
            page.wait_for_function("document.querySelector('[data-race-globe]').dataset.globeRenderer === 'webgl'")
            page.wait_for_function("!document.querySelector('[data-globe-pin=melbourne]').hidden")
            context.close()
            context = browser.new_context(viewport={'width': 390, 'height': 900})
            context.route('https://**', lambda route: route.abort())
            context.add_init_script("""(() => {
                const original=HTMLCanvasElement.prototype.getContext;
                HTMLCanvasElement.prototype.getContext=function(type,...args) {
                    return type==='webgl'?null:original.call(this,type,...args);
                };
            })();""")
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base + '/calendar/', wait_until='networkidle')
            page.wait_for_function("document.querySelector('[data-race-globe]').dataset.globeRenderer === 'fallback'")
            page.locator('[data-globe-race=suzuka]').click()
            assert page.locator('[data-globe-location]').inner_text() == 'Судзука'
            assert page.locator('[data-globe-loading]').is_hidden()
            assert page.locator('.rc-card').count() == 23
            context.close()
            context = browser.new_context(java_script_enabled=False, viewport={"width": 390, "height": 900})
            context.route('https://**', lambda route: route.abort())
            page = context.new_page()
            page.goto(base + "/calendar/", wait_until="networkidle")
            assert page.locator(".rc-card").count() == 23
            assert "01.11 · 23:00" in page.locator(".rc-feature-times").inner_text()
            assert page.locator("[data-calendar-timezone]").is_hidden()
            assert page.locator(".rc-feature .rc-button").is_visible()
            assert page.locator('[data-race-globe]').is_hidden()
            browser.close()
        assert not errors, errors
        print(f"Calendar UI OK ({browser_name}): 5 sizes, click-only labels, full 360-degree rotation, selection/drag/zoom, mobile gestures, native page scroll, idle/offscreen pause, context-loss fallback, 23 cards, sessions, covers, timezones, filters, no-JS fallback. {output}")
    finally:
        server.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", choices=("webkit", "chromium"), default="webkit")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run(args.browser, args.output_dir)
