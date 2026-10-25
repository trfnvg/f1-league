"""The hero follows the race deadline, independently of prediction deadlines."""
from django.utils import timezone

from .models import Event


def select_featured_event(events, now=None):
    """Feature the nearest not-yet-started race, even after predictions close."""
    now = now or timezone.now()
    events = list(events)
    upcoming = [
        event for event in events
        if (event.race_datetime or event.deadline) > now
        and event.status != Event.Status.SCORED
    ]
    if upcoming:
        return min(upcoming, key=lambda event: (event.race_datetime or event.deadline, event.round_number))
    return max(events, key=lambda event: event.round_number, default=None)
