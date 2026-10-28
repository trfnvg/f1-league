"""Database-backed authentication limits, shared by all application workers."""
import ipaddress
import math
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import F
from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.deprecation import MiddlewareMixin

from .models import AuthRateBucket


def client_address(request):
    # Forwarded headers are trusted only when the immediate peer is explicitly
    # configured as a trusted proxy. Walk right-to-left, not attacker-first.
    networks = [ipaddress.ip_network(value.strip()) for value in
                getattr(settings, "AUTH_TRUSTED_PROXIES", []) if value.strip()]
    address = request.META.get("REMOTE_ADDR", "")
    chain = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
    try:
        while chain and any(ipaddress.ip_address(address) in net for net in networks):
            address = chain.pop().strip()
        ip = ipaddress.ip_address(address)
        # IPv6 privacy-address rotation must not bypass limits within a /64.
        return str(ipaddress.ip_network(f"{ip}/64", strict=False)) if ip.version == 6 else str(ip)
    except ValueError:
        return "unknown"


def bucket_key(scope, value):
    return salted_hmac("fastlap-auth-limits", f"{scope}:{value}", algorithm="sha256").hexdigest()


def consume(scope, value, limit, seconds):
    """Conditional UPDATE reserves a slot atomically, including across workers."""
    now = timezone.now()
    key = bucket_key(scope, value)
    expiry = now + timedelta(seconds=seconds)
    AuthRateBucket.objects.filter(key=key, expires_at__lte=now).update(hits=0, expires_at=expiry)
    AuthRateBucket.objects.get_or_create(key=key, defaults={"expires_at": expiry})
    accepted = AuthRateBucket.objects.filter(key=key, hits__lt=limit).update(hits=F("hits") + 1)
    if accepted:
        return 0
    expiry = AuthRateBucket.objects.values_list("expires_at", flat=True).get(key=key)
    return max(1, math.ceil((expiry - now).total_seconds()))


class AuthRateLimitMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.method != "POST" or not request.resolver_match:
            return None
        name = request.resolver_match.url_name
        if name in {"arcade_run_start", "doodle_attempt_start", "arcade_run_finish", "doodle_attempt_finish",
                    "arcade_run_progress", "doodle_attempt_progress"}:
            if not request.user.is_authenticated:
                return None
            action = "start" if name.endswith("start") else "update"
            waits = [consume(f"arcade-{action}-ip", client_address(request), 6000, 60),
                     consume(f"arcade-{action}-user", str(request.user.pk), 120, 60)]
            if max(waits):
                response = JsonResponse({"error": "Слишком много игровых запросов. Подожди минуту."}, status=429)
                response["Retry-After"] = str(max(waits))
                response["Cache-Control"] = "no-store"
                return response
            return None
        if name in {"register", "account_settings"}:
            if name == "register" and request.user.is_authenticated:
                return None
            if name == "account_settings" and not request.user.is_authenticated:
                return None
            address = client_address(request)
            wait = consume(f"{name}-ip", address, 20 if name == "register" else 60, 900)
            if not wait and name == "account_settings":
                wait = consume("account-settings-user", str(request.user.pk), 10, 900)
            return self.blocked(request, wait) if wait else None
        if name not in {"login", "password_reset"}:
            return None
        if name == "login" and request.user.is_authenticated:
            return None
        # Opportunistic bounded-work cleanup, no cron or additional service.
        if secrets.randbelow(100) == 0:
            stale = list(AuthRateBucket.objects.filter(expires_at__lt=timezone.now())
                         .values_list("key", flat=True)[:500])
            AuthRateBucket.objects.filter(key__in=stale, expires_at__lt=timezone.now()).delete()
        address = client_address(request)
        if name == "password_reset":
            wait = consume("reset-ip", address, 20, 3600)
            if wait:
                return self.blocked(request, wait)
            return None
        wait = consume("login-ip", address, 120, 900)
        if wait:
            return self.blocked(request, wait)
        identity = request.POST.get("username", "").strip().lstrip("@").casefold()[:254]
        raw_login = request.POST.get("username", "").strip()
        users = get_user_model().objects
        user_id = users.filter(league_profile__handle__iexact=identity).values_list("pk", flat=True).first()
        if user_id is None and not raw_login.startswith("@"):
            user_id = users.filter(username=raw_login).values_list("pk", flat=True).first()
        identity = f"user:{user_id}" if user_id is not None else f"unknown:{identity}"
        waits = [consume("login-pair", f"{address}:{identity}", 5, 60),
                 consume("login-account", identity, 20, 900)]
        if max(waits):
            return self.blocked(request, max(waits))
        request.auth_limit_identity = identity
        request.auth_limit_address = address
        return None

    def process_response(self, request, response):
        identity = getattr(request, "auth_limit_identity", None)
        if identity is not None and response.status_code == 302 and request.user.is_authenticated:
            AuthRateBucket.objects.filter(key__in=[
                bucket_key("login-account", identity),
                bucket_key("login-pair", f"{request.auth_limit_address}:{identity}"),
            ]).delete()
        return response

    @staticmethod
    def blocked(request, wait):
        response = render(request, "registration/auth_rate_limited.html", {
            "retry_minutes": max(1, math.ceil(wait / 60)),
        }, status=429)
        response["Retry-After"] = str(wait)
        response["Cache-Control"] = "no-store"
        return response
