from django.core.management.base import BaseCommand

from league.calendar_event_sync import sync_calendar_events_v1


class Command(BaseCommand):
    help = "Создать недостающие карточки прогнозов из календаря, не меняя существующие."

    def add_arguments(self, parser):
        parser.add_argument("--season", type=int, required=True)

    def handle(self, *args, **options):
        report = sync_calendar_events_v1(options["season"])
        self.stdout.write(self.style.SUCCESS(
            f'Создано: {report["created"]}; привязано: {report["linked"]}; сохранено без изменений: {report["preserved"]}.'))
        for conflict in report["conflicts"]:
            self.stdout.write(self.style.WARNING(conflict))
