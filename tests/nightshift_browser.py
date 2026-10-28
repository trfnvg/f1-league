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
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw
from league.circuits import CIRCUITS
from league.leagues import import_legacy_league
from league.duels import create_duel_challenge, respond_to_duel
from league.models import Event, Prediction, Score, Season, UserProfile, EventWildcardQuestion, EventWildcardDeck, EventWildcardDeckCard, ArcadeTrophyAward


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
    icon = client.get('/favicon.ico')
    pages = {"/guest/": home_page(), '/favicon.ico': b''.join(icon.streaming_content)}
    client.force_login(player)
    pages["/"] = home_page()
    pages["/league/"] = client.get(reverse("league:friend_league", args=[league.league_id])).content
    pages["/standings/"] = client.get(reverse("league:global_leaderboard")).content
    pages["/event/"] = client.get(reverse("league:event_detail", args=[event.pk])).content
    pages["/drivers/"] = client.get(reverse("league:drivers")+'?season=2026').content
    pages["/driver-profile/"] = client.get(reverse("league:driver_profile", args=(2026, "russell"))).content
    ArcadeTrophyAward.objects.create(player=player, event=past, game_key='pit_lane_flight', game_name='Pit Lane Flight', trophy_name='Банана Леклер', attempts=7)
    ArcadeTrophyAward.objects.create(player=player, event=past, game_key='doodle_jump', game_name='Cowboy GP', trophy_name='Космический ковбой', attempts=12, image='test-cowboy.png')
    pages['/media/test-cowboy.png'] = Path(finders.find('league/images/russell-cowboy-pixel-reward-v1.png')).read_bytes()
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
    league.league.avatar = 'avatars/test.png'
    league.league.save(update_fields=['avatar'])
    pages['/league-settings/'] = client.get(reverse('league:friend_league_settings', args=[league.league_id])).content
    pages['/league-judging/'] = client.get(reverse('league:friend_league_settings', args=[league.league_id]), {'section':'judging'}).content
    pages['/league-settings-invite/'] = client.post(reverse('league:friend_league_settings', args=[league.league_id]), {'action':'create_invite'}, follow=True).content
    client.force_login(player)
    pages['/league/'] = client.get(reverse('league:friend_league', args=[league.league_id])).content
    client.force_login(owner)
    pages["/admin-add/"] = client.get(reverse("admin:league_event_add")).content
    pages["/admin-edit/"] = client.get(reverse("admin:league_event_change", args=[event.pk])).content
    pages[reverse("admin:jsi18n")] = client.get(reverse("admin:jsi18n")).content
    # Long season is rendered separately, so both desktop and mobile exercise scrolling.
    historical = [Event.objects.create(name=f"Гран-при · этап {i}", round_number=i,
        season_year=season.year, deadline=now-timedelta(days=130-i), status="scored") for i in range(1, 18)]
    Score.objects.bulk_create([Score(user=user, event=round_event, points=(round_event.round_number+user.pk)%24)
        for user in User.objects.filter(is_staff=False) for round_event in historical])
    pages["/standings-long/"] = client.get(reverse("league:global_leaderboard")).content
    league.start_event = historical[0]
    league.save(update_fields=["start_event"])
    # These fixtures represent imported original members, not late invitees.
    league.entries.update(first_event=historical[0])
    client.force_login(player)
    pages["/league-long/"] = client.get(reverse("league:friend_league", args=[league.league_id])).content
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
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode
    client.logout()
    for route, name in (("/register/", "league:register"), ("/login/", "login"),
                        ("/password-reset/", "password_reset"), ("/password-reset-done/", "password_reset_done"),
                        ("/password-reset-complete/", "password_reset_complete")):
        pages[route] = client.get(reverse(name)).content
    token_url = reverse("password_reset_confirm", kwargs={"uidb64": urlsafe_base64_encode(force_bytes(player.pk)),
        "token": default_token_generator.make_token(player)})
    token_response = client.get(token_url)
    pages["/new-password/"] = client.get(token_response.url).content
    client.force_login(player)
    pages["/account-settings/"] = client.get(reverse("league:account_settings")).content
    from league.leagues import create_league, create_invite, enroll_member
    from league.models import Result
    private = create_league(owner=player, name="Гоночная компания друзей", season=season, start_event=future, ruleset="paddock")
    _, invite_token = create_invite(actor=player, league_season=private)
    pages["/invite-manage/"] = client.get(reverse("league:friend_league_invites", args=[private.league_id])).content
    pages["/invite-member/"] = client.get(reverse("league:friend_league_join", args=[invite_token])).content
    pages["/private-predict/"] = client.get(reverse("league:friend_league_event", args=[private.league_id, future.pk])).content
    saved = client.post(reverse('league:event_detail', args=[future.pk]), dict(
        p1='russell', p2='leclerc', p3='norris', pole='russell', fastest_lap='russell',
        driver_of_day='russell', safety_car_count=1, dnf_count=2, crazy_prediction='Тестовый прогноз'), follow=True)
    assert b'data-save-receipt' in saved.content
    pages['/saved-predict/'] = saved.content
    Result.objects.create(event=past, p1="russell", p2="leclerc", p3="norris", pole="russell", safety_car_count=1, dnf_count=2)
    Prediction.objects.filter(user=player, event=past).update(p1="leclerc", p2="russell", p3="norris", pole="russell", created_at=past.deadline-timedelta(hours=1))
    Score.objects.filter(user=player, event=past).update(points=12, breakdown={"P1 (Top-3)":3,"P2 (Top-3)":3,"P3":4,"Pole Position":4,"Дуэль":-2})
    pages["/score-detail/"] = client.get(reverse("league:score_detail", args=[past.pk, player.pk])).content
    pages["/race-recap/"] = client.get(reverse("league:race_recap", args=[past.pk, player.pk])).content
    pages["/league-recap/"] = client.get(reverse("league:friend_league_recap", args=[league.league_id, past.pk, player.pk])).content
    friend = User.objects.get(username="Аня")
    Prediction.objects.filter(user=friend, event=past).update(crazy_prediction="Гонку выиграет тот, кто первым доедет до финиша.", created_at=past.deadline-timedelta(hours=1))
    pages["/social-event/"] = client.get(reverse("league:event_detail", args=[past.pk])).content
    client.logout()
    for i in range(29):
        guest = User.objects.create_user(f'invite-preview-{i}', first_name=f'Новый участник {i+1}')
        enroll_member(actor=player, league_season=private, user=guest)
    pages["/invite-preview/"] = client.get(reverse("league:friend_league_join", args=[invite_token])).content
    client.force_login(player)
    pages["/members-manage/"] = client.get(reverse("league:friend_league_settings", args=[private.league_id]), {"section":"members"}).content
    client.logout()
    blocked = client.post(reverse('league:register'), dict(first_name='Гриша', username='putin63',
        email='blocked-preview@example.com', password1='RaceStart!63', password2='RaceStart!63'))
    assert blocked.status_code == 200
    pages['/register-blocked/'] = blocked.content
    from league import error_views
    error_request = RequestFactory().get('/leagues/join/example/')
    for name, view in (("403", error_views.permission_denied), ("404", error_views.page_not_found),
                       ("500", error_views.server_error), ("csrf", error_views.csrf_failure)):
        pages[f"/error-{name}/"] = view(error_request).content
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
                content_type = "image/x-icon" if route == '/favicon.ico' else "text/javascript" if route.endswith("/jsi18n/") else ("image/png" if route.endswith(".png") else "text/html; charset=utf-8")
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
                page.goto(base+'/register-blocked/', wait_until='networkidle')
                assert 'не соответствует правилам Fastlap' in page.locator('.account-card').inner_text()
                assert page.locator('[name="username"]').input_value() == 'putin63'
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                page.screenshot(path=str(output/f'{width}-registration-moderation.png'), full_page=True)
                for route in ('/race-recap/', '/league-recap/'):
                    page.goto(base+route, wait_until='networkidle')
                    page.locator('canvas[data-ready="true"]').wait_for()
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    with page.expect_download() as exported:
                        page.locator('[data-recap-download]').click()
                    image_path = output/f'{width}-{route.strip("/")}-export.png'
                    exported.value.save_as(str(image_path))
                    with Image.open(image_path) as saved_image:
                        assert saved_image.size == (1080,1350)
                        assert saved_image.format == 'PNG'
                    assert image_path.stat().st_size > 20000
                    page.screenshot(path=str(output/f'{width}-{route.strip("/")}.png'), full_page=True)
                reaction_state = {'kind': None, 'failed': False}
                def react(route):
                    if reaction_state['failed']:
                        route.fulfill(status=403, content_type='text/html', body='Forbidden')
                        return
                    # Browser FormData uses multipart, inspect its kind field.
                    body = route.request.post_data or ''
                    chosen = next(kind for kind in ('heart','fire','poop') if f'\r\n{kind}\r\n' in body)
                    reaction_state['kind'] = None if reaction_state['kind']==chosen else chosen
                    import json
                    route.fulfill(content_type='application/json', body=json.dumps({'options':[
                        {'kind':kind,'count':int(reaction_state['kind']==kind),'selected':reaction_state['kind']==kind}
                        for kind in ('heart','fire','poop')]}))
                page.route('**/events/*/predictions/*/reactions/', react)
                page.goto(base+'/social-event/', wait_until='networkidle')
                page.locator('.crazy-social-list summary').click()
                group = page.locator('[data-reactions]').first
                group.evaluate('item=>item.scrollIntoView({block:"center"})')
                for kind, selected in (('heart', True),('fire',True),('fire',False),('poop',True)):
                    button = group.locator(f'[data-reaction-kind="{kind}"]')
                    button.click()
                    page.wait_for_function('(item)=>item.getAttribute("aria-busy")!=="true"', arg=group.element_handle())
                    assert button.get_attribute('aria-pressed') == str(selected).lower()
                    assert button.locator('[data-reaction-count]').inner_text() == str(int(selected))
                reaction_state['failed']=True
                group.locator('[data-reaction-kind="heart"]').click()
                page.wait_for_function('(item)=>item.getAttribute("aria-busy")!=="true"', arg=group.element_handle())
                assert 'Не удалось сохранить' in group.locator('[data-reaction-status]').inner_text()
                assert group.locator('[data-reaction-kind="poop"]').get_attribute('aria-pressed') == 'true'
                group.screenshot(path=str(output/f'{width}-crazy-reactions.png'))
                page.unroute('**/events/*/predictions/*/reactions/', react)
                for name in ('403', '404', '500', 'csrf', 'member'):
                    route = '/invite-member/' if name == 'member' else f'/error-{name}/'
                    page.goto(base + route)
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'), (width, route)
                    if name == 'member':
                        assert page.locator('.leagues-join a', has_text='Открыть лигу').is_visible()
                        assert page.locator('.leagues-join form').count() == 0
                    else:
                        assert page.locator('main h1').is_visible()
                        assert page.locator('nav a[href="/"]').is_visible()
                        assert page.locator('form').count() == 0
                    page.screenshot(path=str(output/f'{width}-{name}-recovery.png'), full_page=True)
                page.goto(base + '/members-manage/')
                assert page.locator('[data-member-row]:visible').count() == 30
                assert page.locator('[data-role-form]').count() == 29
                page.locator('[data-member-search]').fill('Новый участник 29')
                assert page.locator('[data-member-row]:visible').count() == 1
                page.locator('[data-member-search]').fill('НЕТ ТАКОГО УЧАСТНИКА')
                assert page.locator('[data-member-empty]').is_visible()
                page.locator('[data-member-search]').fill('')
                page.locator('[data-member-filter]').select_option('owner')
                assert page.locator('[data-member-row]:visible').count() == 1
                assert page.locator('[data-member-row]:visible [data-role-form]').count() == 0
                page.locator('[data-member-filter]').select_option('player')
                assert page.locator('[data-member-row]:visible').count() == 29
                first_handle = page.locator('[data-member-row]:visible [data-member-handle]').first.inner_text()
                page.locator('[data-member-search]').fill(first_handle.upper())
                assert page.locator('[data-member-row]:visible').count() == 1
                page.locator('[data-member-search]').fill('')
                role_form = page.locator('[data-role-form]').first
                assert role_form.locator('button').is_disabled()
                assert page.locator('option[value="manager"]').count() == 0
                role_form.locator('select').select_option('moderator')
                assert role_form.locator('button').is_enabled()
                for allowed in (False, True):
                    assert role_form.evaluate('''(form, allowed) => {
                        const original = window.confirm; let text = '', blocked;
                        window.confirm = message => {text = message; return allowed;};
                        form.addEventListener('submit', event => {blocked = event.defaultPrevented; event.preventDefault();}, {once:true});
                        form.requestSubmit(); window.confirm = original;
                        return blocked === !allowed && text.includes('Модератор');
                    }''', allowed)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                page.locator('[data-member-search]').fill(first_handle)
                page.locator('.manage-members').screenshot(path=str(output/f'{width}-members-directory.png'))
                page.goto(base + '/league-judging/')
                assert page.locator('.manage-round:visible').count() == 5
                page.locator('.manage-round-more summary').click()
                assert page.locator('.manage-round:visible').count() > 5
                page.locator('.manage-round-more summary').click()
                assert page.locator('.manage-profile').count() == 0
                assert page.locator('.manage-nav a[aria-current]').inner_text() == 'Судейство'
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                page.screenshot(path=str(output/f'{width}-judging.png'), full_page=True)
                for route in ("/", "/guest/", "/closed/", "/in-race/", "/switched/", "/home-duel/", "/league/", "/league-settings/", "/league-settings-invite/", "/standings/", "/league-long/", "/standings-long/", "/event/", "/drivers/", "/driver-profile/", "/event-closed/", "/far-future/", "/event-broken-cover/", "/event-fallback/", "/profile/", "/duel-sent/", "/duel-received/", "/duel-accepted/", "/cover-square/", "/cover-portrait/", "/stage-square/", "/stage-portrait/", "/register/", "/login/", "/password-reset/", "/password-reset-done/", "/password-reset-complete/", "/new-password/", "/account-settings/", "/score-detail/", "/invite-preview/", "/invite-manage/", "/private-predict/"):
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
                    if route in ('/', '/closed/', '/guest/'):
                        assert page.locator('.ns-home a', has_text='Создать лигу').count() == (2 if route == '/guest/' else 0)
                    if route in ('/register/', '/login/', '/password-reset/', '/password-reset-done/', '/password-reset-complete/', '/new-password/', '/account-settings/'):
                        assert page.locator('.account-card').is_visible()
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    if route == '/league-settings/':
                        assert page.locator('.manage-header h1').inner_text() == 'Управление лигой'
                        assert page.locator('.manage-card').count() == 2
                        assert page.locator('.manage-members,.manage-rounds').count() == 0
                        assert page.locator('.manage-nav a[aria-current]').inner_text() == 'Настройки'
                        assert page.locator('.manage-invite-actions button').inner_text() == 'Создать ссылку'
                        assert not page.locator('.manage-danger a').is_visible()
                        page.locator('.manage-danger summary').click()
                        assert page.locator('.manage-danger a').is_visible()
                        page.locator('.manage-danger summary').click()
                        assert page.locator('[data-logo-image]').evaluate("e=>getComputedStyle(e).objectFit==='contain'")
                        assert page.locator('[data-logo-clear]').is_visible()
                        page.locator('[data-logo-clear]').check()
                        assert page.locator('[data-logo-placeholder]').is_visible()
                        page.locator('[data-logo-clear]').uncheck()
                        assert page.locator('[data-logo-image]').is_visible()
                        assert page.locator('[data-logo-button]').inner_text() == 'Выбрать файл'
                        page.locator('[data-logo-input]').set_input_files({'name':'logo.png','mimeType':'image/png','buffer':pages['/media/avatars/test.png']})
                        assert page.locator('[data-logo-filename]').inner_text() == 'logo.png'
                        assert page.locator('[data-logo-image]').get_attribute('src').startswith('blob:')
                        page.locator('[data-logo-clear]').check()
                        assert page.locator('[data-logo-filename]').inner_text() == 'Файл не выбран'
                        assert page.locator('[data-logo-input]').evaluate('e=>e.files.length') == 0
                        page.locator('[data-logo-clear]').uncheck()
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                        page.evaluate("document.activeElement.blur();document.documentElement.style.scrollBehavior='auto';window.scrollTo(0,0)")
                        page.wait_for_function('window.scrollY < 2')
                    if route == '/league-settings-invite/':
                        link = page.locator('#league-invite-link').input_value()
                        assert '/leagues/join/' in link
                        assert page.locator('.manage-invite-actions button').inner_text() == 'Обновить ссылку'
                        assert page.evaluate("""() => {
                            const form=document.querySelector('[data-confirm-invite-rotation]');
                            const confirm=window.confirm;
                            window.confirm=()=>false;
                            const blocked=!form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
                            window.confirm=()=>true;
                            const allowed=form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));
                            window.confirm=confirm;
                            return blocked && allowed;
                        }""")
                        page.evaluate("Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>{window.testCopiedInvite=text;}}})")
                        page.locator('[data-copy-invite]').click()
                        page.wait_for_function("document.querySelector('[data-copy-status]').textContent.includes('Ссылка скопирована')")
                        assert page.evaluate('window.testCopiedInvite') == link
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    if route == '/register/':
                        assert page.locator('#id_first_name,#id_username,#id_email,#id_password1,#id_password2').count() == 5
                        assert page.locator('.account-handle>span').inner_text() == '@'
                        assert page.locator('#id_password2').get_attribute('autocomplete') == 'new-password'
                    if route in ('/event/', '/private-predict/'):
                        status = page.locator('[data-save-label]')
                        assert status.is_visible()
                        field = page.locator('textarea[name="crazy_prediction"]')
                        original = field.input_value()
                        field.fill('Несохранённый тестовый прогноз')
                        assert status.inner_text() == 'Есть несохранённые изменения'
                        field.fill(original)
                        assert status.inner_text() in ('Прогноз сохранён', 'Прогноз ещё не сохранён')
                    if route == '/score-detail/':
                        assert page.locator('.score-explanation-total strong').inner_text() == '12'
                        assert page.locator('.score-explanation-table tbody tr').count() == 8
                    if route == '/invite-preview/':
                        assert page.locator('.league-invite-more').inner_text().strip() == '· и ещё 24'
                        assert page.locator('.leagues-join a[href*="next="]').count() == 2
                    if route == '/login/':
                        assert page.locator('a[href="/accounts/password_reset/"]').is_visible()
                    if route in ('/league/', '/standings/', '/league-long/', '/standings-long/'):
                        assert page.locator('.classification').is_visible()
                        if route.startswith('/league'):
                            share = page.locator('.league-share')
                            assert share.is_visible()
                            source = share.locator('#league-invite-link')
                            link = source.get_attribute('href')
                            assert '/leagues/join/' in link
                            assert share.locator('[data-confirm-invite-rotation]').count() == 0
                            page.evaluate("Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>{window.testSharedInvite=text;}}})")
                            share.locator('[data-copy-invite]').click()
                            page.wait_for_function("document.querySelector('[data-copy-status]').textContent.includes('Ссылка скопирована')")
                            assert page.evaluate('window.testSharedInvite') == link
                            page.evaluate("() => {navigator.clipboard.writeText=async()=>{throw new Error('Clipboard unavailable');};}")
                            share.locator('[data-copy-invite]').click()
                            page.wait_for_function("document.querySelector('[data-copy-status]').textContent.includes('Выделили ссылку')")
                            assert page.evaluate('window.getSelection().toString()') == link
                            share.screenshot(path=str(output/f'{width}-{route.strip("/")}-share.png'))
                        assert page.locator('#pointsChart,script[src*="leaderboard-chart"],#leaderboard-chart-data').count() == 0
                        assert page.locator('.classification-table tbody tr').count() == 5
                        assert page.locator('[data-table-mode],.classification-summary,.classification-selection').count() == 0
                        assert page.locator('.classification-result:visible').count() == page.locator('.classification-stage-header').count()*5
                        rounds = page.locator('.classification-stage-header strong').all_text_contents()
                        assert rounds == sorted(rounds, reverse=True)
                        assert rounds[0] == 'R18'
                        assert len(rounds) == (18 if route.endswith('-long/') else 1)
                        link = page.locator('.classification-stage-header a').first.get_attribute('href')
                        assert link.startswith('/leagues/' if route.startswith('/league') else '/events/')
                        frame = page.locator('.classification-viewport')
                        assert frame.evaluate('e=>e.scrollLeft') == 0
                        frame.scroll_into_view_if_needed()
                        frozen = page.locator('.classification-table tbody tr').first.locator('.classification-identity,.classification-pinned-total')
                        initial = frozen.evaluate_all('cells=>cells.map(e=>({x:e.getBoundingClientRect().x,y:e.getBoundingClientRect().y,width:e.getBoundingClientRect().width}))')
                        assert initial[0]['x']+initial[0]['width'] <= initial[1]['x']+1
                        frame.evaluate('e=>e.scrollLeft=e.scrollWidth')
                        page.wait_for_timeout(100)
                        assert frozen.evaluate_all('cells=>cells.map(e=>({x:e.getBoundingClientRect().x,y:e.getBoundingClientRect().y,width:e.getBoundingClientRect().width}))') == initial
                        assert frame.evaluate('e=>e.scrollTop===0 && e.scrollHeight<=e.clientHeight+1'), (width, route, 'Table must not scroll vertically')
                        assert frozen.evaluate_all('cells=>cells.every(e=>{const s=getComputedStyle(e),r=e.getBoundingClientRect();return s.backgroundColor!=="rgba(0, 0, 0, 0)" && document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.closest("th,td")===e;})'), (width, route, 'Frozen cells overlap or become transparent')
                        assert page.locator('.classification-table tbody th').evaluate_all('cells=>new Set(cells.map(e=>getComputedStyle(e).backgroundColor)).size===1')
                        assert page.locator('.classification-player,.classification-score').evaluate_all('cells=>cells.every(e=>getComputedStyle(e).animationName==="none" && getComputedStyle(e).transform==="none")')
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                        frame.screenshot(path=str(output/f'{width}-{route.strip("/")}-scrolled.png'))
                        if route.endswith('-long/'):
                            assert page.locator('.classification-controls').is_visible()
                            frame.evaluate('e=>e.scrollLeft=0')
                            page.wait_for_timeout(80)
                            assert page.locator('[data-table-step="-1"]').is_disabled()
                            old_y = frame.bounding_box()['y']
                            page.locator('[data-table-step="1"]').click()
                            assert frame.evaluate('e=>e.scrollLeft') > 0
                            assert abs(frame.bounding_box()['y']-old_y) < 1
                        frame.evaluate('e=>e.scrollLeft=0')
                        page.evaluate('document.activeElement.blur(); window.scrollTo(0,0)')
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
                        assert notice.evaluate("e=>getComputedStyle(e,'::before').animationName") == 'duel-ember-drift'
                        assert notice.evaluate("e=>getComputedStyle(e,'::before').pointerEvents") == 'none'
                        original_box = notice.bounding_box()
                        page.wait_for_timeout(180)
                        assert notice.bounding_box() == original_box
                        notice.screenshot(path=str(output/f'{width}-duel-ember.png'))
                        page.emulate_media(reduced_motion='reduce')
                        assert notice.evaluate("e=>getComputedStyle(e,'::before').animationName") == 'none'
                        page.emulate_media(reduced_motion='no-preference')
                        notice.focus()
                        assert notice.evaluate("e=>getComputedStyle(e).outlineStyle") == 'solid'
                        notice.evaluate('e=>e.blur()')
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
                        if route == '/far-future/':
                            for name in ('safety_car_count', 'dnf_count'):
                                assert page.locator(f'[name="{name}"]').input_value() == ''
                            assert page.locator('[data-progress-bar]').get_attribute('value') == '0'
                            page.locator('[name="safety_car_count"]').fill('0')
                            assert page.locator('[data-progress-bar]').get_attribute('value') == '1'
                            page.locator('[name="dnf_count"]').fill('0')
                            assert page.locator('[data-progress-bar]').get_attribute('value') == '2'
                            page.locator('[name="safety_car_count"]').fill('')
                            assert page.locator('[data-progress-bar]').get_attribute('value') == '1'
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
                        assert page.locator('[data-home-launch],script[src*="home-launch"],link[href*="home-launch"]').count() == 0
                        first = page.locator('[data-clock="seconds"]').inner_text()
                        page.wait_for_timeout(1200)
                        assert page.locator('[data-clock="seconds"]').inner_text() != first
                        assert not page.locator('.nightshift-nav a[href="/season-predictions/"]').count()
                        if width > 780:
                            assert page.locator('.nightshift-account-avatar img').evaluate('e=>e.complete && e.naturalWidth>0')
                        image = page.locator('.ns-calendar .event-media>img').first
                        assert image.evaluate('e=>getComputedStyle(e).objectFit') == 'cover'
                        assert page.locator('.ns-live .activity-news-item').count() == 5
                        compact_radio = width <= 1000
                        assert page.locator('.ns-live .activity-news-item:visible').count() == (3 if compact_radio else 5)
                        radio = page.locator('.ns-live')
                        if compact_radio:
                            assert radio.bounding_box()['height'] < 390, (width, 'Radio takes too much vertical space')
                            page.locator('.paddock-radio-toggle').click()
                            assert page.locator('.paddock-radio-toggle').get_attribute('aria-expanded') == 'true'
                        else:
                            assert not page.locator('.paddock-radio-toggle').is_visible()
                            left_box = page.locator('.ns-socialgrid>.ns-panel').first.bounding_box()
                            right_box = radio.bounding_box()
                            assert abs(left_box['y']-right_box['y']) < 1
                            assert abs(left_box['height']-right_box['height']) < 1, (width, left_box, right_box)
                        assert page.locator('.ns-live .activity-news-item:visible').count() == 5
                        assert page.locator('.ns-live .activity-news-item:visible').evaluate_all('''items=>items.every(item=>{
                            const icon=item.querySelector('.activity-feed-icon'),copy=item.querySelector('.activity-news-copy');
                            const a=icon.getBoundingClientRect(),b=copy.getBoundingClientRect();
                            return Math.abs(a.width-24)<1 && Math.abs(a.height-24)<1 && a.right+8<=b.left && a.y>=item.getBoundingClientRect().y && getComputedStyle(icon,'::before').content==='none' && !!icon.querySelector('svg');
                        })'''), (width, "feed icons overlap copy")
                        feed_url = page.locator('#live-paddock-list').get_attribute('data-feed-url')
                        updated_feed = page.locator('#live-paddock-list').inner_html().replace('Аня возглавляет чемпионат', 'Аня возглавляет чемпионат · обновлено')
                        page.route('**'+feed_url, lambda route: route.fulfill(json={'html': updated_feed}))
                        with page.expect_response('**'+feed_url):
                            page.evaluate("document.activeElement.blur();document.dispatchEvent(new Event('visibilitychange'))")
                        page.locator('.ns-live .activity-news-copy strong').first.get_by_text('Аня возглавляет чемпионат · обновлено', exact=True).wait_for()
                        assert page.locator('.paddock-radio-toggle').get_attribute('aria-expanded') == str(compact_radio).lower()
                        assert page.locator('.ns-live .activity-news-item:visible').count() == 5
                        if compact_radio:
                            page.locator('.paddock-radio-toggle').click()
                            assert page.locator('.ns-live .activity-news-item:visible').count() == 3
                        radio.screenshot(path=str(output/f'{width}-paddock-radio.png'))
                        page.locator('.ns-socialgrid').screenshot(path=str(output/f'{width}-pitwall-panels.png'))
                        if not compact_radio:
                            page.set_viewport_size({'width':390,'height':1000})
                            page.wait_for_function("document.querySelectorAll('.radio-transmission:not([hidden])').length===3")
                            assert page.locator('.paddock-radio-toggle').is_visible()
                            page.locator('.paddock-radio-toggle').click()
                            assert page.locator('.ns-live .activity-news-item:visible').count() == 5
                            page.set_viewport_size({'width':width,'height':1000})
                            page.wait_for_function("document.querySelector('.paddock-radio-toggle').hidden")
                            assert page.locator('.ns-live .activity-news-item:visible').count() == 5
                            page.set_viewport_size({'width':390,'height':1000})
                            page.wait_for_function("!document.querySelector('.paddock-radio-toggle').hidden")
                            assert page.locator('.paddock-radio-toggle').get_attribute('aria-expanded') == 'true'
                            page.locator('.paddock-radio-toggle').click()
                            page.set_viewport_size({'width':width,'height':1000})
                            page.wait_for_function("document.querySelector('.paddock-radio-toggle').hidden")
                        page.unroute('**'+feed_url)
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
                            }''', 'cover'), (width, route, "cover outside its frame")
                            if route.startswith('/cover-'):
                                image.hover()
                            else:
                                page.locator('.event-stage-hero').hover()
                            assert image.evaluate("e=>getComputedStyle(e).transform==='none'"), (width, route, "cover zooms and clips on hover")
                        if not route.startswith('/cover-'):
                            assert page.locator('.event-stage-hero').evaluate('''hero=>{
                                const media=hero.querySelector('.event-stage-media'),copy=hero.querySelector('.event-stage-copy');
                                const h=hero.getBoundingClientRect(),m=media.getBoundingClientRect(),c=copy.getBoundingClientRect();
                                const photo=media.querySelector('img'),style=getComputedStyle(photo);
                                return Math.abs(h.width-m.width)<3 && Math.abs(h.height-m.height)<3 && c.left>=m.left && c.right<=m.right+1 && c.top>=m.top && c.bottom<=m.bottom+1 && Number(style.opacity)>0 && Number(style.opacity)<1 && getComputedStyle(copy).opacity==='1' && getComputedStyle(media,'::after').backgroundImage!=='none';
                            }'''), (width, route, 'Cover must fill the hero behind readable text')
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
                                assert page.locator('[data-driver="russell"] .driver-team-name').evaluate('e=>getComputedStyle(e).color') == 'rgb(98, 223, 205)'
                                assert page.locator('[data-driver="leclerc"] .driver-team-name').evaluate('e=>getComputedStyle(e).color') == 'rgb(255, 133, 133)'
                                assert page.locator('[data-driver="norris"] .driver-team-name').evaluate('e=>getComputedStyle(e).color') == 'rgb(255, 173, 97)'
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
                        assert page.locator('.prediction-podium-slot').nth(2).locator('.driver-team-name').evaluate('e=>getComputedStyle(e).color') == 'rgb(98, 223, 205)'
                        assert 'Норрис' in page.locator('[data-summary-lines]').inner_text()
                        assert page.locator('[data-more-predictions]').is_visible()
                        assert page.locator('[data-more-predictions] summary').count() == 0
                        for name in ['pole', 'fastest_lap', 'driver_of_day']:
                            page.locator(f'[data-driver-field="{name}"]').click()
                            assert page.locator('[data-driver="norris"]').is_enabled()
                            page.locator('[data-driver="norris"]').click()
                            assert page.locator(f'[data-driver-field="{name}"] img').is_visible()
                            assert page.locator(f'[data-driver-field="{name}"] .driver-team-name').evaluate('e=>getComputedStyle(e).color') == 'rgb(255, 173, 97)'
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
                        page.locator('#driver-picker-dialog').wait_for(state='visible')
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
                        assert page.locator('#playerTrend').count() == 0
                        assert page.locator('.player-trophy-card').count() == 2
                        assert page.locator('.player-trophy-content dl').first.is_visible()
                        page.locator('#avatarMenuButton').click()
                        assert page.locator('#avatarUploadMenu').is_visible()
                        page.keyboard.press('Escape')
                        assert page.locator('#avatarUploadMenu').is_hidden()
                        with page.expect_file_chooser():
                            page.locator('[data-change-avatar]').click()
                        page.locator('.player-event summary').first.click()
                        assert page.locator('.player-event-content').first.is_visible()
                        assert page.locator('#player-history .player-event').count() == 2
                        page.evaluate('document.activeElement.blur(); window.scrollTo(0,0)')
                        page.wait_for_timeout(250)
                    page.screenshot(path=str(output/f"{width}-{route.strip('/') or 'home'}.png"), full_page=True)
                # Feedback is cosmetic: final scores and fixed geometry stay authoritative.
                page.goto(base+'/standings-long/', wait_until='networkidle')
                page.locator('.classification-viewport').scroll_into_view_if_needed()
                page.wait_for_timeout(750)
                assert page.locator('[data-count-to]:visible').evaluate_all('nodes=>nodes.every(n=>n.textContent===n.dataset.countTo)')
                page.goto(base+'/saved-predict/', wait_until='networkidle')
                assert page.locator('[data-save-receipt]').is_visible()
                assert page.locator('[data-save-status]').get_attribute('data-state') == 'confirmed'
                page.locator('[data-save-receipt]').screenshot(path=str(output/f'{width}-save-receipt.png'))
                page.locator('textarea[name="crazy_prediction"]').fill('Изменённый прогноз')
                assert page.locator('[data-save-status]').get_attribute('data-state') == 'dirty'
                page.evaluate('''() => { const f=document.querySelector('select[name="p1"]'); f.value=''; f.dispatchEvent(new Event('change',{bubbles:true})); }''')
                page.locator('.prediction-summary-action button').click()
                assert page.locator('[data-save-status]').get_attribute('data-state') != 'sending'
                page.goto(base+'/', wait_until='networkidle')
                finish = page.locator('[data-race-finish]')
                finish.scroll_into_view_if_needed()
                assert 'is-finishing' not in (finish.get_attribute('class') or ''), 'Repeated visits must not replay the finish'
                finish.screenshot(path=str(output/f'{width}-race-finish.png'))
                feed_url = page.locator('#live-paddock-list').get_attribute('data-feed-url')
                long_text = 'Новое сообщение командного радио: ' + 'на трассе идёт борьба за позиции. '*12
                updated = page.locator('#live-paddock-list').inner_html().replace('Аня возглавляет чемпионат', long_text)
                page.route('**'+feed_url, lambda route: route.fulfill(json={'html': updated}))
                page.locator('.ns-live').scroll_into_view_if_needed()
                with page.expect_response('**'+feed_url):
                    page.evaluate("document.activeElement.blur();document.dispatchEvent(new Event('visibilitychange'))")
                first_message = page.locator('.radio-transmission').first
                disclosure = first_message.locator('.radio-message-open')
                disclosure.wait_for(state='visible')
                assert first_message.locator('.activity-news-item').evaluate('e=>e.classList.contains("is-unread")')
                disclosure.click()
                assert disclosure.get_attribute('aria-expanded') == 'true'
                assert first_message.locator('.activity-news-copy>strong').evaluate('e=>e.scrollHeight<=e.clientHeight+1')
                assert not first_message.locator('.activity-news-item').evaluate('e=>e.classList.contains("is-unread")')
                disclosure.click()
                page.unroute('**'+feed_url)
                page.emulate_media(reduced_motion='reduce')
                page.goto(base+'/standings/', wait_until='networkidle')
                assert page.locator('[data-count-to]').evaluate_all('nodes=>nodes.every(n=>n.textContent===n.dataset.countTo)')
                page.goto(base+'/saved-predict/', wait_until='networkidle')
                assert page.locator('.race-save-check path').evaluate('e=>getComputedStyle(e).animationName') == 'none'
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                page.close()
            fallback_page = browser.new_page(viewport={"width": 390, "height": 1000}, java_script_enabled=False)
            fallback_page.goto(base+'/league-settings/', wait_until='networkidle')
            assert fallback_page.locator('[data-logo-input]').is_visible()
            assert fallback_page.locator('[data-logo-clear]').is_visible()
            fallback_page.goto(base+'/event/', wait_until='networkidle')
            assert fallback_page.locator('#id_p1').is_visible()
            assert fallback_page.locator('#id_pole').is_visible()
            assert fallback_page.locator('[data-fallback-submit]').is_visible()
            fallback_page.goto(base+'/standings/', wait_until='networkidle')
            assert fallback_page.locator('.classification-result:visible').count() > 0
            assert fallback_page.locator('.classification-stage-header a').first.is_visible()
            assert fallback_page.locator('.classification-stage-header button:visible').count() == 0
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
            position = "nodes => nodes.map(el => [el.getAttribute('cx'),el.getAttribute('cy')])"
            runners = page.locator(".ns-trackdrawing .circuit-car")
            assert runners.count() == 22
            assert runners.evaluate_all("nodes => new Set(nodes.map(el => el.dataset.racer)).size") == 22
            assert runners.evaluate_all("nodes => new Set(nodes.map(el => el.getAttribute('fill'))).size") == 11
            assert page.locator('.ns-trackdrawing .circuit-peloton').is_visible()
            first = runners.evaluate_all(position)
            page.wait_for_timeout(350)
            assert runners.evaluate_all(position) != first, "Peloton is not moving"
            page.emulate_media(reduced_motion="reduce")
            page.wait_for_timeout(100)  # Browser delivers the media change asynchronously.
            first = runners.evaluate_all(position)
            page.wait_for_timeout(350)
            assert runners.evaluate_all(position) == first, "Reduced motion must freeze the peloton"
            assert runners.first.is_visible()
            assert page.locator("#circuit-path-home").evaluate("el => getComputedStyle(el).animationName") == "none"
            page.goto(base+"/circuits/", wait_until="networkidle")
            page.screenshot(path=str(output/"all-circuits.png"), full_page=True)
            browser.close()
        assert not errors, errors
        print(f"UI OK ({engine}): {len(widths)} viewport sizes, 38 real pages, league management, confirmed saves, score counters, radio, stable tables, invites, accounts and 27 admin choices. Screenshots: {output}")
    finally:
        server.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--widths", nargs="+", type=int, default=[320, 390, 768, 1101, 1440, 1920])
    parser.add_argument("--browser", choices=["chromium", "webkit"], default="chromium")
    args = parser.parse_args()
    run(args.output_dir, args.widths, args.browser)
