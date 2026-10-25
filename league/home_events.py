"""One current-GP rule shared by the homepage, navigation and league pages."""
from datetime import timedelta
from django.utils import timezone

from .models import Event


RACE_DISPLAY_GRACE = timedelta(hours=2)


def event_display_until(event):
    """A race stays current for two hours; undated races use their deadline."""
    return (event.race_datetime or event.deadline) + RACE_DISPLAY_GRACE


def select_current_event(events, now=None):
    """Keep the nearest GP through the race, independently of its score state."""
    now = now or timezone.now()
    upcoming = [
        event for event in events
        if event_display_until(event) > now
    ]
    return min(upcoming, key=lambda event: (event.race_datetime or event.deadline, event.round_number), default=None)


def select_featured_event(events, now=None):
    """The homepage retains an archive card when there is no next race."""
    events = list(events)
    current = select_current_event(events, now)
    if current:
        return current
    return max(events, key=lambda event: event.round_number, default=None)
