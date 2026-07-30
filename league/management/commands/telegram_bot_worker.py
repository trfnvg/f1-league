from django.conf import settings
from django.core.management.base import BaseCommand

from league.telegram_bot import run_worker


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

    def handle(self, *args, **options):
        if not getattr(settings, "TELEGRAM_BOT_TOKEN", "").strip():
            self.stdout.write(self.style.WARNING("TELEGRAM_BOT_TOKEN is not configured; Telegram worker is disabled."))
            return

        self.stdout.write(self.style.SUCCESS("Telegram worker started."))
        run_worker(interval=options["interval"], once=options["once"])
