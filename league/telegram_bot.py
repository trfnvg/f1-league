import http.client
import json
import logging
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone

from .models import Event, Prediction, Score, Season, TelegramBotState, TelegramReminder, UserProfile
from .services import build_leaderboard


logger = logging.getLogger(__name__)
TELEGRAM_API_URL = "https://api.telegram.org"


class TelegramAPIError(RuntimeError):
    def __init__(self, message, error_code=None):
        super().__init__(message)
        self.error_code = error_code


def _create_ipv4_connection(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
    """Create an outbound connection using IPv4 only.

    Some App Platform containers advertise IPv6 DNS results without having a
    usable IPv6 route. Telegram has IPv4 endpoints, so preferring IPv4 avoids
    ``Errno 99: Cannot assign requested address`` in that environment.
    """
    host, port = address
    last_error = None

    for family, socktype, proto, _, sockaddr in socket.getaddrinfo(
        host,
        port,
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
    ):
        connection = None
        try:
            connection = socket.socket(family, socktype, proto)
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                connection.settimeout(timeout)
            if source_address:
                connection.bind(source_address)
            connection.connect(sockaddr)
            return connection
        except OSError as exc:
            last_error = exc
            if connection is not None:
                connection.close()

    if last_error is not None:
        raise last_error
    raise OSError(f"Could not resolve an IPv4 address for {host}")


class _IPv4HTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _create_ipv4_connection


class _IPv4HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, request):
        return self.do_open(
            _IPv4HTTPSConnection,
            request,
            context=getattr(self, "_context", None),
        )


_TELEGRAM_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    _IPv4HTTPSHandler(),
)
# A custom API endpoint (for example, Cloudflare Workers) must use the normal
# system networking stack. Unlike the direct Telegram connection, it may be
# reachable through a proxy supplied by the hosting platform.
_PROXY_OPENER = urllib.request.build_opener()


def bot_is_configured():
    return bool(getattr(settings, "TELEGRAM_BOT_TOKEN", "").strip())


def get_bot_username():
    configured_username = getattr(settings, "TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
    if configured_username:
        return configured_username
    if not bot_is_configured():
        return ""

    try:
        result = _api_call("getMe") or {}
    except TelegramAPIError:
        logger.exception("Could not determine Telegram bot username")
        return ""
    return (result.get("username") or "").strip().lstrip("@")


def get_bot_info():
    return _api_call("getMe") or {}


def _api_call(method, data=None):
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise TelegramAPIError("TELEGRAM_BOT_TOKEN is not configured")

    api_base_url = (
        getattr(settings, "TELEGRAM_API_BASE_URL", TELEGRAM_API_URL).strip().rstrip("/")
        or TELEGRAM_API_URL
    )
    proxy_secret = getattr(settings, "TELEGRAM_PROXY_SECRET", "").strip()
    uses_proxy = api_base_url != TELEGRAM_API_URL
    if uses_proxy and not proxy_secret:
        raise TelegramAPIError(
            "TELEGRAM_PROXY_SECRET must be configured when TELEGRAM_API_BASE_URL uses a proxy"
        )

    # When the protected proxy is enabled, the bot token is kept out of the
    # request URL. The Cloudflare Worker stores the same token as a secret and
    # adds it only when forwarding the request to Telegram.
    url = f"{api_base_url}/{method}" if uses_proxy else f"{TELEGRAM_API_URL}/bot{token}/{method}"
    payload = urllib.parse.urlencode(data or {}).encode("utf-8")
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if uses_proxy:
        headers["X-Proxy-Secret"] = proxy_secret
        # Cloudflare Browser Integrity Check rejects urllib's default
        # ``Python-urllib/x.y`` signature with error 1010 before the request
        # reaches the Worker.
        headers["User-Agent"] = (
            "Mozilla/5.0 (compatible; F1LeagueTelegramBot/1.0; +https://f1-league.ru)"
        )
    request = urllib.request.Request(
        url,
        data=payload,
        headers=headers,
        method="POST",
    )
    opener = _PROXY_OPENER if uses_proxy else _TELEGRAM_OPENER
    try:
        with opener.open(request, timeout=15) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except (OSError, json.JSONDecodeError):
            raise TelegramAPIError(f"Telegram HTTP error: {exc}") from exc
        raise TelegramAPIError(
            body.get("description", f"Telegram HTTP error: {exc}"),
            error_code=body.get("error_code"),
        ) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise TelegramAPIError(f"Telegram request failed: {exc}") from exc

    if not body.get("ok"):
        raise TelegramAPIError(
            body.get("description", "Telegram API returned an error"),
            error_code=body.get("error_code"),
        )
    return body.get("result")


def send_message(chat_id, text, event=None):
    data = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true",
    }
    site_url = getattr(settings, "SITE_URL", "").strip().rstrip("/")
    if event and site_url.startswith(("http://", "https://")):
        data["reply_markup"] = json.dumps(
            {
                "inline_keyboard": [
                    [
                        {
                            "text": "Открыть этап",
                            "url": f"{site_url}{reverse('league:event_detail', kwargs={'event_id': event.id})}",
                        }
                    ]
                ]
            }
        )
    return _api_call("sendMessage", data)


def _deadline_text(event):
    deadline = timezone.localtime(event.deadline)
    return deadline.strftime("%d.%m.%Y в %H:%M (МСК)")


def _handle_start(chat_id, token):
    profile = UserProfile.objects.select_related("user").filter(telegram_link_token=token).first()
    if not profile:
        send_message(
            chat_id,
            "Ссылка привязки недействительна или уже использована. "
            "Открой новую ссылку в профиле на сайте.",
        )
        return

    UserProfile.objects.filter(telegram_chat_id=chat_id).exclude(pk=profile.pk).update(
        telegram_chat_id=None,
        telegram_notifications=False,
    )
    profile.telegram_chat_id = chat_id
    profile.telegram_notifications = True
    profile.telegram_link_token = uuid.uuid4()
    profile.save(update_fields=("telegram_chat_id", "telegram_notifications", "telegram_link_token", "updated_at"))
    send_message(
        chat_id,
        f"Готово, {profile.user.username}! Telegram подключён к твоему аккаунту. "
        "Я напомню за сутки и за 3 часа до дедлайна, если предикт ещё не отправлен.\n\n"
        "Команды: /next — следующий этап, /status — статус предикта, "
        "/table — топ-5, /stop — отключить уведомления.",
    )


def _linked_profile(chat_id):
    return (
        UserProfile.objects.select_related("user")
        .filter(telegram_chat_id=chat_id, user__is_active=True)
        .first()
    )


def _next_event():
    season = Season.get_active()
    return (
        Event.objects.filter(
            season_year=season.year,
            deadline__gt=timezone.now(),
        )
        .exclude(status=Event.Status.SCORED)
        .order_by("deadline")
        .first()
    )


def _command_help():
    return (
        "Команды бота:\n"
        "/next — следующий этап и дедлайн\n"
        "/status — отправлен ли твой предикт\n"
        "/my — состав твоего предикта\n"
        "/table — первая пятёрка чемпионата\n"
        "/stop — отключить уведомления\n"
        "/resume — включить уведомления"
    )


def _handle_command(chat_id, command, argument=""):
    command = command.lower().split("@", 1)[0]
    if command == "/start":
        if argument:
            _handle_start(chat_id, argument.strip())
        else:
            profile = UserProfile.objects.filter(telegram_chat_id=chat_id).first()
            if profile:
                send_message(chat_id, "Telegram уже подключён к твоему аккаунту.\n\n" + _command_help())
            else:
                send_message(chat_id, "Открой кнопку подключения Telegram в профиле на сайте.")
    elif command in ("/help", "/commands"):
        send_message(chat_id, _command_help())
    elif command == "/next":
        event = _next_event()
        if event:
            send_message(
                chat_id,
                f"🏁 Следующий этап: {event.name}\n"
                f"Раунд: R{event.round_number}\n"
                f"Дедлайн: {_deadline_text(event)}",
                event=event,
            )
        else:
            send_message(chat_id, "Сейчас нет открытых этапов.")
    elif command in ("/status", "/my"):
        profile = _linked_profile(chat_id)
        if not profile:
            send_message(chat_id, "Сначала подключи Telegram в своём профиле на сайте.")
            return
        event = _next_event()
        if not event:
            send_message(chat_id, "Сейчас нет открытых этапов.")
            return
        prediction = Prediction.objects.filter(event=event, user=profile.user).first()
        if prediction and command == "/my":
            send_message(
                chat_id,
                f"Твой предикт на «{event.name}»:\n\n"
                f"P1 — {prediction.get_p1_display()}\n"
                f"P2 — {prediction.get_p2_display()}\n"
                f"P3 — {prediction.get_p3_display()}\n"
                f"Поул — {prediction.get_pole_display()}\n\n"
                f"Дедлайн: {_deadline_text(event)}",
                event=event,
            )
        elif prediction:
            send_message(
                chat_id,
                f"✅ Предикт на «{event.name}» принят.\n"
                f"P1: {prediction.get_p1_display()}\n"
                f"Дедлайн: {_deadline_text(event)}",
                event=event,
            )
        else:
            send_message(
                chat_id,
                f"⏳ Предикт на «{event.name}» ещё не отправлен.\n"
                f"Дедлайн: {_deadline_text(event)}",
                event=event,
            )
    elif command == "/table":
        season = Season.get_active()
        rows = build_leaderboard(season.year)["rows"][:5]
        if not rows:
            send_message(chat_id, "Таблица пока пуста.")
            return
        lines = [f"🏆 Топ-5 · сезон {season.year}"]
        for row in rows:
            lines.append(f"{row['rank']}. {row['user'].username} — {row['total']} очков")
        send_message(chat_id, "\n".join(lines))
    elif command == "/stop":
        updated = UserProfile.objects.filter(telegram_chat_id=chat_id).update(telegram_notifications=False)
        send_message(
            chat_id,
            "Уведомления отключены." if updated else "Этот Telegram ещё не подключён к аккаунту.",
        )
    elif command == "/resume":
        updated = UserProfile.objects.filter(telegram_chat_id=chat_id).update(telegram_notifications=True)
        send_message(
            chat_id,
            "Уведомления снова включены." if updated else "Этот Telegram ещё не подключён к аккаунту.",
        )
    else:
        send_message(chat_id, "Не знаю такую команду.\n\n" + _command_help())


def process_update(update):
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    if chat.get("type") != "private":
        return

    text = (message.get("text") or "").strip()
    if not text.startswith("/"):
        return

    parts = text.split(maxsplit=1)
    _handle_command(chat.get("id"), parts[0], parts[1] if len(parts) > 1 else "")


def poll_updates():
    state, _ = TelegramBotState.objects.get_or_create(key="default")
    data = {"limit": 100, "timeout": 5}
    if state.update_offset:
        data["offset"] = state.update_offset

    updates = _api_call("getUpdates", data) or []
    for update in updates:
        try:
            process_update(update)
        except Exception:
            logger.exception("Failed to process Telegram update %s", update.get("update_id"))
        update_id = update.get("update_id")
        if update_id is not None:
            state.update_offset = max(state.update_offset, update_id + 1)
            state.save(update_fields=("update_offset", "updated_at"))
    return len(updates)


def send_due_reminders(now=None):
    now = now or timezone.now()
    profiles = list(
        UserProfile.objects.filter(
            telegram_chat_id__isnull=False,
            telegram_notifications=True,
            user__is_active=True,
            user__is_staff=False,
        ).select_related("user")
    )
    events = list(Event.objects.filter(
        deadline__gt=now,
        deadline__lte=now + timedelta(hours=24),
    ).exclude(status=Event.Status.SCORED))
    sent = 0

    for event in events:
        remaining = event.deadline - now
        reminder_kind = (
            TelegramReminder.Kind.THREE_HOURS
            if remaining <= timedelta(hours=3)
            else TelegramReminder.Kind.DAY
        )
        time_label = "около 3 часов" if reminder_kind == TelegramReminder.Kind.THREE_HOURS else "меньше суток"
        predicted_user_ids = set(Prediction.objects.filter(event=event).values_list("user_id", flat=True))
        for profile in profiles:
            if profile.user_id in predicted_user_ids:
                continue
            if TelegramReminder.objects.filter(
                event=event,
                user=profile.user,
                kind=reminder_kind,
            ).exists():
                continue

            text = (
                "🏎 Напоминание о предикте\n\n"
                f"До дедлайна этапа «{event.name}» осталось {time_label}.\n"
                f"Дедлайн: {_deadline_text(event)}\n\n"
                "Ты ещё не отправил прогноз."
            )
            try:
                send_message(profile.telegram_chat_id, text, event=event)
            except TelegramAPIError as exc:
                if exc.error_code == 403:
                    profile.telegram_notifications = False
                    profile.save(update_fields=("telegram_notifications", "updated_at"))
                logger.warning("Could not notify Telegram chat %s: %s", profile.telegram_chat_id, exc)
                continue

            try:
                TelegramReminder.objects.create(
                    event=event,
                    user=profile.user,
                    kind=reminder_kind,
                )
            except IntegrityError:
                continue
            sent += 1

    return sent


def notify_prediction_saved(prediction):
    profile = getattr(prediction.user, "league_profile", None)
    if not profile or not profile.telegram_chat_id or not profile.telegram_notifications:
        return False
    send_message(
        profile.telegram_chat_id,
        "✅ Предикт сохранён\n\n"
        f"{prediction.event.name} · R{prediction.event.round_number}\n"
        f"P1: {prediction.get_p1_display()}\n"
        f"P2: {prediction.get_p2_display()}\n"
        f"P3: {prediction.get_p3_display()}\n"
        f"Дедлайн: {_deadline_text(prediction.event)}",
        event=prediction.event,
    )
    return True


def send_result_notifications():
    profiles = list(
        UserProfile.objects.filter(
            telegram_chat_id__isnull=False,
            telegram_notifications=True,
            user__is_active=True,
            user__is_staff=False,
        ).select_related("user")
    )
    if not profiles:
        return 0

    events = list(
        Event.objects.filter(
            status=Event.Status.SCORED,
            result__published_at__isnull=False,
        ).order_by("round_number")
    )
    sent = 0
    leaderboards = {}
    for event in events:
        if event.season_year not in leaderboards:
            leaderboards[event.season_year] = {
                row["user"].id: row
                for row in build_leaderboard(event.season_year)["rows"]
            }
        score_map = {
            score.user_id: score
            for score in Score.objects.filter(event=event)
        }
        for profile in profiles:
            if TelegramReminder.objects.filter(
                event=event,
                user=profile.user,
                kind=TelegramReminder.Kind.RESULT,
            ).exists():
                continue
            score = score_map.get(profile.user_id)
            points = score.points if score else 0
            row = leaderboards[event.season_year].get(profile.user_id)
            rank_line = ""
            if row:
                movement = row["movement"]
                movement_text = f" · {'↑' if movement > 0 else '↓'}{abs(movement)}" if movement else ""
                rank_line = f"Место в чемпионате: {row['rank']}{movement_text}\n"
            try:
                send_message(
                    profile.telegram_chat_id,
                    "🏁 Результаты опубликованы\n\n"
                    f"{event.name} · R{event.round_number}\n"
                    f"Твой результат: {points} очков.\n"
                    f"{rank_line}"
                    "Открой этап, чтобы увидеть подробный разбор.",
                    event=event,
                )
            except TelegramAPIError as exc:
                if exc.error_code == 403:
                    profile.telegram_notifications = False
                    profile.save(update_fields=("telegram_notifications", "updated_at"))
                logger.warning("Could not send result to Telegram chat %s: %s", profile.telegram_chat_id, exc)
                continue
            try:
                TelegramReminder.objects.create(
                    event=event,
                    user=profile.user,
                    kind=TelegramReminder.Kind.RESULT,
                )
            except IntegrityError:
                continue
            sent += 1
    return sent


def run_worker(interval=60, once=False):
    if not bot_is_configured():
        logger.warning("Telegram worker is disabled: TELEGRAM_BOT_TOKEN is not configured")
        return

    while True:
        try:
            processed = poll_updates()
            sent = send_due_reminders()
            result_sent = send_result_notifications()
            if processed or sent or result_sent:
                logger.info(
                    "Telegram worker: processed updates=%s, reminders sent=%s, results sent=%s",
                    processed,
                    sent,
                    result_sent,
                )
        except Exception:
            logger.exception("Telegram worker iteration failed")

        if once:
            return
        time.sleep(max(10, interval))
