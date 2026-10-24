"""Homepage feature selection is separate from the next open prediction form."""
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from .models import Event

MOSCOW = ZoneInfo("Europe/Moscow")


def select_featured_event(events, now=None):
    """Keep this racing week's GP until Monday 00:00 Moscow, including scored GPs."""
    now = now or timezone.now()
    events = list(events)
    today = timezone.localtime(now, MOSCOW).date()
    monday = today - timedelta(days=today.weekday())
    next_monday = monday + timedelta(days=7)
    current = [
        event for event in events
        if monday <= timezone.localtime(event.race_datetime or event.deadline, MOSCOW).date() < next_monday
    ]
    if current:
        return min(current, key=lambda event: (event.race_datetime or event.deadline, event.round_number))
    upcoming = [event for event in events if event.deadline > now and event.status != Event.Status.SCORED]
    if upcoming:
        return min(upcoming, key=lambda event: (event.deadline, event.round_number))
    return max(events, key=lambda event: event.round_number, default=None)
