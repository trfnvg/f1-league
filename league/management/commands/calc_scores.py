from django.core.management.base import BaseCommand

from league.models import Event, SeasonResult
from league.scoring import calculate_event_scores, calculate_season_scores


class Command(BaseCommand):
    help = "Calculate scores for event and season predictions"

    def handle(self, *args, **options):
        event_updates = 0
        season_updates = 0

        events = Event.objects.filter(result__isnull=False)
        for event in events:
            event_updates += calculate_event_scores(event)

        season_years = SeasonResult.objects.values_list("season_year", flat=True)
        for season_year in season_years:
            season_updates += calculate_season_scores(season_year)

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated event scores: {event_updates}; updated season scores: {season_updates}"
            )
        )
