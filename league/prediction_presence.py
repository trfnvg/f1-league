"""Membership-scoped submission presence; no prediction answers leave this service."""
from django.db.models import F, Q
from django.utils import timezone

from .home_events import select_current_event
from .models import Event, Prediction


def prediction_presence(season, *, events=None, entries=None, now=None):
    now = now or timezone.now()
    if events is None:
        events = Event.objects.filter(season_year=season.season.year,
            round_number__gte=season.start_event.round_number)
    event = select_current_event(events, now)
    if event is None:
        return {'event': None, 'statuses': {}, 'saved': 0, 'eligible': 0}
    if entries is None:
        entries = season.entries.select_related('membership__user', 'first_event')
        if season.is_legacy:
            entries = entries.filter(membership__user__is_staff=False, membership__user__is_active=True)
    entries = list(entries)
    eligible = {entry.membership.user_id for entry in entries
        if entry.membership.is_active and entry.membership.user.is_active
        and entry.first_event.round_number <= event.round_number}
    predictions = Prediction.objects.filter(event=event, user_id__in=eligible,
        created_at__lt=event.deadline)
    # Historical rows predate submitted_at. Accept complete legacy submissions,
    # but do not turn blank model-default placeholders into a green status.
    required = ['p1', 'p2', 'p3', 'pole', 'fastest_lap', 'driver_of_day']
    if event.has_sprint:
        required += ['sprint_qualifying_winner', 'sprint_winner']
    for field in required:
        predictions = predictions.exclude(**{field: ''})
    predictions = predictions.exclude(Q(p1=F('p2')) | Q(p1=F('p3')) | Q(p2=F('p3')))
    saved = set(predictions.values_list('user_id', flat=True))
    return {
        'event': {'id': event.pk, 'round': event.round_number, 'name': event.name,
            'closed': now >= event.deadline},
        'statuses': {entry.membership.user_id:
            ('saved' if entry.membership.user_id in saved else
             'missing' if entry.membership.user_id in eligible else 'ineligible')
            for entry in entries},
        'saved': len(saved), 'eligible': len(eligible),
    }
