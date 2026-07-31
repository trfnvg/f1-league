from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from league.telegram_bot import TelegramAPIError, get_bot_info, run_worker


class Command(BaseCommand):
    help = "Poll Telegram updates and send prediction deadline reminders"

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=60,
            help="Seconds between Telegram polling/reminder checks (default: 60)",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run one iteration and exit",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Check the token with Telegram and exit",
        )

    def handle(self, *args, **options):
        if not getattr(settings, "TELEGRAM_BOT_TOKEN", "").strip():
            if options["check"]:
                raise CommandError("TELEGRAM_BOT_TOKEN is not configured")
            self.stdout.write(self.style.WARNING("TELEGRAM_BOT_TOKEN is not configured; Telegram worker is disabled."))
            return

        if not options["check"] and not getattr(settings, "TELEGRAM_WORKER_ENABLED", True):
            self.stdout.write(self.style.WARNING("TELEGRAM_WORKER_ENABLED is false; Telegram worker is disabled."))
            return

        if options["check"]:
            try:
                info = get_bot_info()
            except TelegramAPIError as exc:
                raise CommandError(str(exc)) from exc
            username = info.get("username") or "без username"
            self.stdout.write(self.style.SUCCESS(f"Telegram token works: @{username}"))
            return

        self.stdout.write(self.style.SUCCESS("Telegram worker started."))
        run_worker(interval=options["interval"], once=options["once"])
