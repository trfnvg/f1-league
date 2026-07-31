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

from .models import Event, Prediction, TelegramBotState, TelegramReminder, UserProfile


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
        "Я напишу за 3 часа до дедлайна, если предикт ещё не отправлен.\n\n"
        "Команды: /stop — отключить уведомления, /resume — включить снова.",
    )


def _handle_command(chat_id, command, argument=""):
    command = command.lower().split("@", 1)[0]
    if command == "/start":
        if argument:
            _handle_start(chat_id, argument.strip())
        else:
            profile = UserProfile.objects.filter(telegram_chat_id=chat_id).first()
            if profile:
                send_message(chat_id, "Telegram уже подключён к твоему аккаунту.")
            else:
                send_message(chat_id, "Открой кнопку подключения Telegram в профиле на сайте.")
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
    events = Event.objects.filter(
        deadline__gt=now,
        deadline__lte=now + timedelta(hours=3),
    ).exclude(status=Event.Status.SCORED)
    sent = 0

    for event in events:
        predicted_user_ids = set(Prediction.objects.filter(event=event).values_list("user_id", flat=True))
        for profile in profiles:
            if profile.user_id in predicted_user_ids:
                continue
            if TelegramReminder.objects.filter(event=event, user=profile.user).exists():
                continue

            text = (
                "🏎 Напоминание о предикте\n\n"
                f"До дедлайна этапа «{event.name}» осталось около 3 часов.\n"
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
                TelegramReminder.objects.create(event=event, user=profile.user)
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
            if processed or sent:
                logger.info("Telegram worker: processed updates=%s, reminders sent=%s", processed, sent)
        except Exception:
            logger.exception("Telegram worker iteration failed")

        if once:
            return
        time.sleep(max(10, interval))
