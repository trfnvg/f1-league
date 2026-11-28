"""Staff-only reaction game preview."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .calendar_event_sync import thursday_deadline
from .models import Event, RaceCalendarRound, Season


def finale_deadline(year):
    """Read the same prediction deadline as the stage, never create an event on GET."""
    race = RaceCalendarRound.objects.filter(season_year=year, circuit="yas-marina").select_related("prediction_event").first()
    if race and race.prediction_event and race.prediction_event.season_year == year:
        return race.prediction_event.deadline
    deadline = Event.objects.filter(season_year=year, circuit="yas-marina").values_list("deadline", flat=True).first()
    if deadline:
        return deadline
    return thursday_deadline(race.starts_on) if race else None


@never_cache
@login_required
@require_GET
def preview(request):
    if not request.user.is_active or not request.user.is_staff:
        return HttpResponseForbidden()
    now = timezone.now()
    year = Season.objects.filter(is_active=True).values_list("year", flat=True).first() or timezone.localdate(now).year
    deadline = finale_deadline(year)
    return render(request, "arcade_lights_out.html", {
        "arcade_test_mode": True, "server_ms": int(now.timestamp() * 1000),
        "deadline_ms": int(deadline.timestamp() * 1000) if deadline else "",
    })
