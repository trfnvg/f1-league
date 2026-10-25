"""Render the real Django pages against an ephemeral DB; check desktop/mobile UI.

Usage: python tests/nightshift_browser.py --output-dir /tmp/fastlap-nightshift-ui
Requires Playwright + Chromium in the development environment only.
"""
import argparse
import io
import mimetypes
import os
from pathlib import Path
import sys
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.template.loader import render_to_string
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw
from league.circuits import CIRCUITS
from league.leagues import import_legacy_league
from league.duels import create_duel_challenge, respond_to_duel
from league.models import Event, Prediction, Score, Season, UserProfile, EventWildcardQuestion, EventWildcardDeck, EventWildcardDeckCard


def render_pages():
    call_command("migrate", verbosity=0)
    now = timezone.now()
    season = Season.get_active()
    past = Event.objects.create(name="Гран-при Сингапура", round_number=18, season_year=season.year,
        deadline=now-timedelta(days=9), race_datetime=now-timedelta(days=7), status="scored")
    event = Event.objects.create(name="Гран-при США", round_number=19, season_year=season.year,
        deadline=now+timedelta(days=2), race_datetime=now+timedelta(days=3), cover_image="covers/test-wide.png")
    deck = EventWildcardDeck.objects.create(event=event)
    for slot, question in enumerate(("Кто финиширует выше?", "Кто окажется выше в квалификации?", "Кто наберёт больше очков?"), 1):
        card = EventWildcardQuestion.objects.create(event=event, question=question, option_a="Леклер", option_b="Рассел")
        EventWildcardDeckCard.objects.create(deck=deck, question=card, slot=slot)
    for i, key in enumerate(("mexico", "interlagos", "las-vegas", "lusail", "yas-marina"), 20):
        Event.objects.create(name=CIRCUITS[key]["grand_prix"], circuit=key, round_number=i,
            season_year=season.year, deadline=now+timedelta(days=(i-19)*7+2), race_datetime=now+timedelta(days=(i-19)*7+3))
    player = User.objects.create_user("Гриша")
    profile, _ = UserProfile.objects.get_or_create(user=player)
    profile.avatar = "avatars/test.png"
    profile.save(update_fields=["avatar"])
    for user, points in [(User.objects.create_user("Аня"), 245), (player, 232),
                         (User.objects.create_user("Айдар"), 218), (User.objects.create_user("Славик"), 191),
                         (User.objects.create_user("Очень_длинное_имя_участника"), 144)]:
        Prediction.objects.create(user=user, event=past)
        Score.objects.create(user=user, event=past, points=points)
    Prediction.objects.create(user=player, event=event)
    owner = User.objects.create_superuser("preview-admin", "preview@example.com", "test")
    league, _ = import_legacy_league(owner=owner, season_year=season.year, name="Fastlap Main")
    client = Client()
    feed = [dict(type=kind, text=text, meta="После R18 · Fastlap Main", user_id=player.pk)
        for kind, text in (("leader", "Аня возглавляет чемпионат"),
            ("movement", "Гриша поднялся на одну позицию"),
            ("duel-accepted", "Айдар и Славик приняли дуэль"),
            ("arcade-winner", "Новый рекорд в Cowboy GP"),
            ("crazy-veto", "Голосование Paddock Jury завершено"))]
    def home_page():
        with patch("league.views.build_activity_feed", return_value=feed):
            return client.get(reverse("league:home")).content
    pages = {"/guest/": home_page()}
    client.force_login(player)
    pages["/"] = home_page()
    pages["/league/"] = client.get(reverse("league:friend_league", args=[league.league_id])).content
    pages["/standings/"] = client.get(reverse("league:global_leaderboard")).content
    pages["/event/"] = client.get(reverse("league:event_detail", args=[event.pk])).content
    pages["/drivers/"] = client.get(reverse("league:drivers")+'?season=2026').content
    pages["/driver-profile/"] = client.get(reverse("league:driver_profile", args=(2026, "russell"))).content
    pages["/profile/"] = client.get(reverse("league:player_profile", args=[player.pk])).content
    pages["/event-closed/"] = client.get(reverse("league:event_detail", args=[past.pk])).content
    challenge = create_duel_challenge(event, player, User.objects.get(username="Очень_длинное_имя_участника"), 7)
    pages["/home-duel/"] = home_page()
    pages["/duel-sent/"] = client.get(reverse("league:event_detail", args=[event.pk])).content
    client.force_login(challenge.opponent)
    pages["/duel-received/"] = client.get(reverse("league:event_detail", args=[event.pk])).content
    respond_to_duel(challenge, challenge.opponent, accept=True)
    client.force_login(player)
    pages["/duel-accepted/"] = client.get(reverse("league:event_detail", args=[event.pk])).content
    future = Event.objects.order_by("-round_number").first()
    pages["/far-future/"] = client.get(reverse("league:event_detail", args=[future.pk])).content
    event.cover_image = "covers/missing.png"
    event.save(update_fields=["cover_image"])
    pages["/event-broken-cover/"] = client.get(reverse("league:event_detail", args=[event.pk])).content
    custom = Event.objects.create(name="Особый этап", round_number=25, season_year=season.year,
        deadline=now+timedelta(days=100), race_datetime=now+timedelta(days=101))
    pages["/event-fallback/"] = client.get(reverse("league:event_detail", args=[custom.pk])).content
    Event.objects.filter(pk=event.pk).update(deadline=now-timedelta(hours=1))
    pages["/closed/"] = home_page()
    Event.objects.filter(pk=event.pk).update(race_datetime=now-timedelta(hours=1))
    pages["/in-race/"] = home_page()
    Event.objects.filter(pk=event.pk).update(race_datetime=now-timedelta(hours=2, seconds=1))
    pages["/switched/"] = home_page()
    for name, size in (("square", (600, 600)), ("portrait", (600, 900))):
        Event.objects.filter(pk=event.pk).update(cover_image=f"covers/{name}.png")
        pages[f"/cover-{name}/"] = home_page()
        pages[f"/stage-{name}/"] = client.get(reverse("league:event_detail", args=[event.pk])).content
    Event.objects.filter(pk=event.pk).update(race_datetime=event.race_datetime, cover_image="covers/test-wide.png")
    client.force_login(owner)
    pages["/admin-add/"] = client.get(reverse("admin:league_event_add")).content
    pages["/admin-edit/"] = client.get(reverse("admin:league_event_change", args=[event.pk])).content
    pages[reverse("admin:jsi18n")] = client.get(reverse("admin:jsi18n")).content
    gallery = "".join('<figure style="padding:20px;border:1px solid #353d48;border-radius:15px"><figcaption>'+c["grand_prix"]+'</figcaption>'+render_to_string("circuit_track.html", {"circuit": c, "track_id": key, "animated": True})+'</figure>' for key, c in CIRCUITS.items())
    pages["/circuits/"] = ('<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/static/league/circuit-visual.css"></head><body style="background:#1d2229;color:#f3f5f7;font:14px sans-serif;display:grid;grid-template-columns:repeat(3,1fr)">'+gallery+'</body></html>').encode()
    cover = io.BytesIO()
    Image.new("RGB", (1200, 500), "#45516a").save(cover, format="PNG")
    pages["/media/covers/test-wide.png"] = cover.getvalue()
    for name, size in (("square", (600, 600)), ("portrait", (600, 900))):
        cover = io.BytesIO()
        image = Image.new("RGB", size, "#45516a")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, size[0]-1, size[1]-1), outline="#ee7566", width=18)
        draw.line((0, 0, *size), fill="#b7c9df", width=6)
        image.save(cover, format="PNG")
        pages[f"/media/covers/{name}.png"] = cover.getvalue()
    avatar = io.BytesIO()
    image = Image.new("RGB", (200, 300), "#1e3248")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 200, 50), fill="#e29a66")
    draw.ellipse((30, 80, 170, 220), fill="#c3b39b")
    draw.line((100, 0, 100, 300), fill="#efe8da", width=4)
    image.save(avatar, format="PNG")
    pages["/media/avatars/test.png"] = avatar.getvalue()
    assert all(b"Server Error" not in html for html in pages.values())
    return pages


def run(output, widths, engine):
    with override_settings(ALLOWED_HOSTS=["testserver"], MEDIA_URL="/media/", STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }):
        pages = render_pages()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            route = unquote(urlsplit(self.path).path)
            if route in pages:
                body = pages[route]
                content_type = "text/javascript" if route.endswith("/jsi18n/") else ("image/png" if route.endswith(".png") else "text/html; charset=utf-8")
            elif route.startswith("/static/"):
                filename = finders.find(route[len("/static/"):])
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
            browser = getattr(pw, engine).launch()
            for width in widths:
                page = browser.new_page(viewport={"width": width, "height": 1000}, device_scale_factor=1)
                page.on("pageerror", lambda error: errors.append(str(error)))
                for route in ("/", "/guest/", "/closed/", "/in-race/", "/switched/", "/home-duel/", "/league/", "/standings/", "/event/", "/drivers/", "/driver-profile/", "/event-closed/", "/far-future/", "/event-broken-cover/", "/event-fallback/", "/profile/", "/duel-sent/", "/duel-received/", "/duel-accepted/", "/cover-square/", "/cover-portrait/", "/stage-square/", "/stage-portrait/"):
                    page.goto(base+route, wait_until="networkidle")
                    assert page.evaluate("document.compatMode === 'CSS1Compat'"), (width, route, "invalid document prefix enables quirks mode")
                    assert page.locator("head title").count() == 1, (width, route, "head parsed as body content")
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), (width, route, "page overflow")
                    assert page.locator('.mini-avatar,.profile-avatar,.table-avatar,.nightshift-account-avatar,.stage-duel-avatar').evaluate_all('''avatars => avatars.every(a => {
                        const image = a.querySelector('img'); if (!image) return true;
                        const box = a.getBoundingClientRect(), crop = image.getBoundingClientRect(), style = getComputedStyle(image);
                        return Math.abs(box.width-box.height)<1 && Math.abs(crop.width-box.width)<1 && Math.abs(crop.height-box.height)<1 && Math.abs(crop.x-box.x)<1 && Math.abs(crop.y-box.y)<1 && style.objectFit==='cover' && style.objectPosition==='50% 50%';
                    })'''), (width, route, "avatar crop differs from profile")
                    sidebar_visible = page.locator(".nightshift-sidebar").is_visible()
                    if sidebar_visible != (width > 780):
                        page.screenshot(path=str(output/f"failure-{width}-{route.strip('/') or 'home'}.png"), full_page=True)
                    assert sidebar_visible == (width > 780), (width, route, page.locator(".nightshift-sidebar").evaluate("e=>({display:getComputedStyle(e).display,width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height})"))
                    if route in ("/", "/guest/", "/closed/"):
                        svg = page.locator(".ns-trackdrawing .circuit-visual")
                        assert svg.get_attribute("data-circuit") == "austin"
                        assert page.locator("#circuit-path-home").evaluate("p => p.getTotalLength()") > 500
                        box = svg.bounding_box()
                        assert box["width"] > 190 and box["height"] > 150
                        assert page.locator(".ns-primary").is_visible()
                        assert page.locator('.ns-stats').count() == 0
                        assert page.locator('.ns-trackdrawing .circuit-label').all_text_contents() == ['START', 'S1', 'S2', 'S3']
                    if route == '/home-duel/':
                        notice = page.locator('.ns-duel-notice')
                        assert notice.is_visible()
                        assert 'Вызов отправлен' in notice.inner_text()
                        assert 'Очень_длинное_имя_участника' in notice.inner_text()
                        assert notice.locator('.ui-arrow').is_visible()
                        assert notice.evaluate("e=>getComputedStyle(e).textDecorationLine==='none'")
                    if route == "/closed/":
                        assert page.locator(".ns-deadline").inner_text().startswith("ДО СТАРТА ГОНКИ")
                        assert "Время гонки." not in page.locator('#featured-gp-title').inner_text()
                    if route == "/in-race/":
                        assert page.locator(".ns-race-status").inner_text() == "Гонка идёт"
                        assert page.locator(".ns-trackdrawing svg").get_attribute("data-circuit") == "austin"
                    if route == "/switched/":
                        assert page.locator(".ns-trackdrawing svg").get_attribute("data-circuit") == "mexico"
                    if route in ("/event/", "/far-future/", "/event-broken-cover/", "/event-fallback/"):
                        assert page.locator(".event-stage-hero").is_visible(), (route, "empty stage header")
                        assert page.locator(".prediction-workbench form").is_visible(), (route, "forecast missing")
                        assert page.locator(".prediction-podium-slot").count() == 3
                        assert page.locator('.prediction-podium-slot[aria-pressed="true"]').count() == 0
                        assert page.locator(".prediction-podium-slot").first.get_attribute('aria-haspopup') == 'dialog'
                        assert page.locator("#personal-wildcard").is_hidden(), "Optional mechanics must not overwhelm the forecast"
                        assert page.locator(".stage-sections a").first.get_attribute("href") == "#stage-prediction"
                        if width < 781:
                            assert float(page.locator("#id_p1").evaluate("e=>parseFloat(getComputedStyle(e).fontSize)")) >= 16, "Avoid iOS input zoom"
                    if route == "/event-broken-cover/":
                        assert not page.locator("[data-stage-cover]").is_visible()
                        assert page.locator(".event-stage-track").is_visible()
                    if route == "/event-fallback/":
                        assert page.locator(".event-stage-fallback").is_visible()
                    if route == "/event-closed/":
                        assert page.locator(".event-stage-hero").is_visible()
                        assert page.locator(".community-shell").is_visible()
                    if route == "/":
                        first = page.locator('[data-clock="seconds"]').inner_text()
                        page.wait_for_timeout(1200)
                        assert page.locator('[data-clock="seconds"]').inner_text() != first
                        assert not page.locator('.nightshift-nav a[href="/season-predictions/"]').count()
                        if width > 780:
                            assert page.locator('.nightshift-account-avatar img').evaluate('e=>e.complete && e.naturalWidth>0')
                        image = page.locator('.ns-calendar .event-media>img').first
                        assert image.evaluate('e=>getComputedStyle(e).objectFit') == 'cover'
                        assert page.locator('.ns-live .activity-news-item').count() == 5
                        assert page.locator('.ns-live .activity-news-item').evaluate_all('''items=>items.every(item=>{
                            const icon=item.querySelector('.activity-feed-icon'),copy=item.querySelector('.activity-news-copy');
                            const a=icon.getBoundingClientRect(),b=copy.getBoundingClientRect();
                            return Math.abs(a.width-32)<1 && Math.abs(a.height-32)<1 && a.right+8<=b.left && a.y>=item.getBoundingClientRect().y && getComputedStyle(icon,'::before').content==='none' && !!icon.querySelector('svg');
                        })'''), (width, "feed icons overlap copy")
                        action=page.locator('.ns-primary')
                        assert action.evaluate("e=>getComputedStyle(e).clipPath==='none' && getComputedStyle(e).transform==='none'")
                        assert action.locator('svg').is_visible()
                    if route == '/' or route.startswith('/cover-'):
                        assert page.locator('.ns-calendar .gp-card').evaluate_all('''cards=>{
                            const boxes=cards.map(e=>e.getBoundingClientRect());
                            return Math.max(...boxes.map(b=>b.width))-Math.min(...boxes.map(b=>b.width))<2 && Math.max(...boxes.map(b=>b.height))-Math.min(...boxes.map(b=>b.height))<2;
                        }'''), (width, route, "calendar cards must have equal dimensions")
                    if route.startswith('/cover-') or route.startswith('/stage-') or route == '/event/':
                        selector='.ns-calendar .event-media.has-cover img' if route.startswith('/cover-') else '[data-stage-cover]'
                        for image in page.locator(selector).all():
                            image.scroll_into_view_if_needed()
                            image.wait_for(state='visible')
                            image.evaluate('e=>e.decode()')
                            assert image.evaluate('''(e,fit)=>{
                                const b=e.getBoundingClientRect(),p=e.parentElement.getBoundingClientRect();
                                return e.complete && e.naturalWidth>0 && getComputedStyle(e).objectFit===fit && Math.abs(b.width-p.width)<1 && Math.abs(b.height-p.height)<1;
                            }''', 'cover' if route.startswith('/cover-') else 'contain'), (width, route, "cover outside its frame")
                            image.hover()
                            assert image.evaluate("e=>getComputedStyle(e).transform==='none'"), (width, route, "cover zooms and clips on hover")
                    if route.startswith('/duel-'):
                        page.locator('.stage-sections a[href="#event-duel"]').click()
                        assert page.locator('#event-duel.stage-duel').is_visible()
                        assert page.locator('.stage-showdown').is_visible()
                        if route == '/duel-received/':
                            assert page.locator('.stage-duel-btn.is-accept').is_visible()
                            assert page.locator('.stage-duel-btn.is-decline').is_visible()
                        if route == '/duel-accepted/':
                            assert page.locator('.stage-duel-locked').is_visible()
                    if route == '/event/':
                        for index, key in enumerate(['norris', 'piastri', 'russell']):
                            page.locator('.prediction-podium-slot').nth(index).click()
                            assert page.locator('#driver-picker-dialog').is_visible()
                            assert 'ПИЛОТЫ ·' not in page.locator('#driver-picker-dialog').inner_text()
                            assert 'Поиск по фамилии, команде или номеру' not in page.locator('#driver-picker-dialog').inner_text()
                            assert page.locator('#stage-prediction').evaluate("e=>getComputedStyle(e).outlineStyle") == 'none'
                            if index == 0:
                                page.locator('[data-picker-search]').fill('63')
                                assert page.locator('[data-picker-options] button').count() == 1
                                assert page.locator('[data-driver="russell"]').is_visible()
                                page.locator('[data-picker-search]').fill('невозможный поиск')
                                assert page.locator('[data-picker-empty]').is_visible()
                                page.locator('[data-picker-search]').fill('')
                                page.locator('[data-picker-options] img').first.evaluate('e=>e.decode()')
                                assert page.locator('[data-picker-options] img').first.evaluate('e=>e.naturalWidth===e.naturalHeight')
                                page.screenshot(path=str(output/f'{width}-driver-picker.png'), full_page=True)
                            if index == 1:
                                assert page.locator('[data-driver="norris"]').is_disabled()
                            page.locator(f'[data-driver="{key}"]').click()
                            assert page.locator('#driver-picker-dialog').is_hidden()
                            assert page.locator('.prediction-podium-slot').nth(index).locator('img').is_visible()
                        assert page.locator('#id_p1').input_value() == 'norris'
                        assert page.locator('#id_p2').input_value() == 'piastri'
                        assert page.locator('#id_p3').input_value() == 'russell'
                        assert 'Норрис' in page.locator('[data-summary-lines]').inner_text()
                        assert page.locator('[data-more-predictions]').is_visible()
                        assert page.locator('[data-more-predictions] summary').count() == 0
                        for name in ['pole', 'fastest_lap', 'driver_of_day']:
                            page.locator(f'[data-driver-field="{name}"]').click()
                            assert page.locator('[data-driver="norris"]').is_enabled()
                            page.locator('[data-driver="norris"]').click()
                            assert page.locator(f'[data-driver-field="{name}"] img').is_visible()
                        page.locator('#id_crazy_prediction').fill('Тест сохранения черновика')
                        assert page.locator('[data-prediction-progress]').inner_text() == '9 из 9 ответов заполнено'
                        assert page.locator('#race-prediction-form').evaluate('f=>f.checkValidity()')
                        assert page.locator('#race-prediction-form').evaluate("f=>new FormData(f).get('p1')") == 'norris'
                        page.mouse.move(0, 0)
                        assert page.locator('.prediction-podium-slot,.prediction-category-choice').evaluate_all('''buttons=>{
                            const styles=buttons.map(b=>getComputedStyle(b));
                            return new Set(styles.map(s=>s.height)).size===1 && new Set(styles.map(s=>s.backgroundColor)).size===1;
                        }'''), (width, 'Driver categories must share their height and background')
                        assert page.locator('.prediction-podium-slot .driver-choice-photo,.prediction-category-choice .driver-choice-photo').evaluate_all('items=>items.every(e=>Math.abs(e.clientWidth-e.clientHeight)<1)')
                        assert page.locator('#id_safety_car_count').evaluate('e=>getComputedStyle(e).backgroundColor') == page.locator('.prediction-podium-slot').first.evaluate('e=>getComputedStyle(e).backgroundColor')
                        page.locator('#id_pole').evaluate("e=>{e.value='';e.dispatchEvent(new Event('change',{bubbles:true}));}")
                        page.locator('.prediction-summary-action button').click()
                        assert page.locator('[data-more-predictions]').is_visible()
                        assert page.locator('#driver-picker-dialog').is_visible()
                        page.locator('[data-driver="norris"]').click()
                        page.locator('[data-driver-field="pole"]').click()
                        page.keyboard.press('Escape')
                        assert page.locator('#driver-picker-dialog').is_hidden()
                        page.locator('.stage-sections a[href="#personal-wildcard"]').click()
                        assert page.locator('#personal-wildcard').is_visible()
                        assert page.locator('#stage-prediction').is_hidden()
                        assert page.locator('.race-card-art svg').count() == 3
                        page.screenshot(path=str(output/f'{width}-strategy-backs.png'), full_page=True)
                        page.locator('[data-wildcard-card]').first.click()
                        assert page.locator('[data-wildcard-card]').first.get_attribute('aria-expanded') == 'true'
                        page.locator('[data-wildcard-card]').first.evaluate('e=>Promise.all(e.getAnimations({subtree:true}).map(a=>a.finished))')
                        page.screenshot(path=str(output/f'{width}-wildcard-tab.png'), full_page=True)
                        page.locator('.stage-sections a[href="#stage-prediction"]').click()
                        assert page.locator('#id_crazy_prediction').input_value() == 'Тест сохранения черновика'
                        page.locator('.stage-sections a[href="#stage-prediction"]').press('End')
                        assert page.locator('#stage-results').is_visible()
                        page.locator('.stage-sections a[href="#stage-results"]').press('Home')
                        page.evaluate("location.hash='event-duel'")
                        page.wait_for_function("!document.getElementById('event-duel').hidden")
                        assert page.locator('#event-duel').is_visible()
                        page.locator('.stage-sections a[href="#stage-prediction"]').click()
                    if route == "/profile/":
                        assert page.locator("#season-predictions").is_visible()
                    page.screenshot(path=str(output/f"{width}-{route.strip('/') or 'home'}.png"), full_page=True)
                page.close()
            fallback_page = browser.new_page(viewport={"width": 390, "height": 1000}, java_script_enabled=False)
            fallback_page.goto(base+'/event/', wait_until='networkidle')
            assert fallback_page.locator('#id_p1').is_visible()
            assert fallback_page.locator('#id_pole').is_visible()
            assert fallback_page.locator('[data-fallback-submit]').is_visible()
            fallback_page.close()
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base+"/admin-add/", wait_until="networkidle")
            for key in CIRCUITS:
                page.select_option("#id_circuit", key)
                assert page.locator("[data-circuit-preview]").is_visible()
                assert page.locator("#id_name").input_value() == CIRCUITS[key]["grand_prix"]
                assert page.locator("#circuit-path-admin").get_attribute("d") == CIRCUITS[key]["path"]
            page.fill("#id_name", "Мой авторский этап")
            page.select_option("#id_circuit", "austin")
            assert page.locator("#id_name").input_value() == "Мой авторский этап"
            page.screenshot(path=str(output/"admin-circuit-picker.png"), full_page=True)
            page.goto(base+"/admin-edit/", wait_until="networkidle")
            assert page.locator("#id_circuit").input_value() == "austin"
            page.goto(base+"/", wait_until="networkidle")
            position = "el => { const m=el.getScreenCTM(); return [m.e,m.f]; }"
            runner = page.locator(".ns-trackdrawing .circuit-runner")
            first = runner.evaluate(position)
            page.wait_for_timeout(350)
            assert runner.evaluate(position) != first, "Track runner is not moving"
            page.emulate_media(reduced_motion="reduce")
            assert not runner.is_visible()
            assert page.locator("#circuit-path-home").evaluate("el => getComputedStyle(el).animationName") == "none"
            page.goto(base+"/circuits/", wait_until="networkidle")
            page.screenshot(path=str(output/"all-circuits.png"), full_page=True)
            browser.close()
        assert not errors, errors
        print(f"UI OK ({engine}): {len(widths)} viewport sizes, 20 real pages, intrinsic covers, consistent avatar bounds, populated feed icons, duel states, live seconds and 27 admin choices. Screenshots: {output}")
    finally:
        server.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--widths", nargs="+", type=int, default=[320, 390, 768, 1101, 1440, 1920])
    parser.add_argument("--browser", choices=["chromium", "webkit"], default="chromium")
    args = parser.parse_args()
    run(args.output_dir, args.widths, args.browser)
