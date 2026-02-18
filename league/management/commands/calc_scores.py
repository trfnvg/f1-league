from django.core.management.base import BaseCommand
from league.models import Event, Prediction, Score
from league.scoring import calculate_points

class Command(BaseCommand):
    help = "Calculate scores for events that have results"

    def handle(self, *args, **options):
        events = Event.objects.filter(result__isnull=False)

        total_updates = 0
        for event in events:
            res = event.result
            preds = Prediction.objects.filter(event=event)

            for pred in preds:
                pts, breakdown = calculate_points(pred, res)
                Score.objects.update_or_create(
                    event=event,
                    user=pred.user,
                    defaults={"points": pts, "breakdown": breakdown},
                )
                total_updates += 1

        self.stdout.write(self.style.SUCCESS(f"Updated {total_updates} scores"))
