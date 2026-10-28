"""Safe production configuration diagnostics: never print credentials."""
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Report security configuration flags without exposing secrets or modifying data."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true", help="Refuse unsafe production configuration.")

    def handle(self, *args, **options):
        key = settings.SECRET_KEY
        report = {
            "debug_disabled": not settings.DEBUG,
            "secret_key_strong": len(key) >= 50 and len(set(key)) >= 5 and not key.startswith("django-insecure-")
                and key != "dev-fallback-secret-key",
            "allowed_hosts_explicit": bool(settings.ALLOWED_HOSTS) and "*" not in settings.ALLOWED_HOSTS,
            "session_cookie_secure": settings.SESSION_COOKIE_SECURE,
            "session_cookie_httponly": settings.SESSION_COOKIE_HTTPONLY,
            "csrf_cookie_secure": settings.CSRF_COOKIE_SECURE,
            "csrf_middleware_enabled": "django.middleware.csrf.CsrfViewMiddleware" in settings.MIDDLEWARE,
            "database_engine": settings.DATABASES["default"]["ENGINE"],
            "database_configured_explicitly": bool(getattr(settings, "DATABASE_URL", "")),
            "https_redirect_in_django": settings.SECURE_SSL_REDIRECT,
            "hsts_seconds": settings.SECURE_HSTS_SECONDS,
            "trusted_proxy_ranges_configured": any(getattr(settings, "AUTH_TRUSTED_PROXIES", [])),
            "notes": ["A false HTTPS redirect flag may be OK if the hosting proxy enforces HTTPS.",
                "Firewall, backups, repository visibility and actual proxy header handling require separate checks.",
                "Never paste environment dumps, database URLs or SECRET_KEY into support chats."],
        }
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        required = ("debug_disabled", "secret_key_strong", "allowed_hosts_explicit", "session_cookie_secure",
                    "session_cookie_httponly", "csrf_cookie_secure", "csrf_middleware_enabled",
                    "database_configured_explicitly")
        failed = [name for name in required if not report[name]]
        if options["strict"] and failed:
            raise CommandError("Unsafe production settings: " + ", ".join(failed))
