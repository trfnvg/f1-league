"""Public F1 calendar. Viewing it never creates prediction events or deadlines."""
from collections import defaultdict
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from .calendar_assets import calendar_photos
from .circuits import resolve_circuit
from .models import Event, RaceCalendarRound


MONTHS = ("", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
          "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь")


def calendar_rows(year, now):
    rounds = list(RaceCalendarRound.objects.filter(season_year=year).select_related("prediction_event"))
    events = list(Event.objects.filter(season_year=year).order_by("pk"))
    by_circuit = defaultdict(list)
    for event in events:
        circuit = resolve_circuit(event.circuit, event.name, year)
        if circuit:
            by_circuit[circuit["key"]].append(event)
        elif any(alias in event.name.casefold() for alias in ("сепанг", "sepang", "малайзи")):
            by_circuit["sepang"].append(event)
    photos = calendar_photos()
    for item in rounds:
        item.photo = photos.get(item.circuit)
        item.photo_static = item.photo["path"] if item.photo else ""
        item.photo_alt = item.photo.get("alt", item.circuit_name) if item.photo else item.circuit_name
        candidates = by_circuit[item.circuit]
        linked = item.prediction_event
        # Never silently link to another year, including when edited via scripts.
        item.linked_event = (linked if linked and linked.season_year == year else
                             candidates[0] if not linked and len(candidates) == 1 else None)
        local_day = now.astimezone(ZoneInfo(item.venue_timezone)).date()
        item.is_finished = (item.race_at + timedelta(hours=2) <= now if item.race_at else item.ends_on < local_day)
        item.is_weekend = item.starts_on <= local_day <= item.ends_on and not item.is_finished
        item.is_next = False
    upcoming = next((item for item in rounds if not item.is_finished), None)
    if upcoming:
        upcoming.is_next = True
    return rounds, upcoming


@require_GET
def calendar(request):
    years = list(RaceCalendarRound.objects.order_by("-season_year").values_list("season_year", flat=True).distinct())
    default_year = timezone.localdate().year
    default_year = default_year if default_year in years else (years[0] if years else default_year)
    try:
        year = int(request.GET.get("season", default_year))
    except (TypeError, ValueError):
        year = default_year
    if year not in years:
        year = default_year
    now = timezone.now()
    rounds, upcoming = calendar_rows(year, now)
    months = []
    for month in range(1, 13):
        items = [item for item in rounds if item.starts_on.month == month]
        if items:
            months.append({"number": month, "name": MONTHS[month], "rounds": items})
    credits = {item.circuit: item.photo for item in rounds if item.photo and not item.cover_image}
    return render(request, "race_calendar.html", {
        "calendar_year": year, "calendar_years": years, "calendar_months": months,
        "calendar_rounds": rounds, "calendar_next": upcoming,
        "calendar_completed": sum(item.is_finished for item in rounds),
        "calendar_credits": credits.values(),
        "calendar_checked_on": min((item.checked_on for item in rounds if item.checked_on), default=None),
    })
