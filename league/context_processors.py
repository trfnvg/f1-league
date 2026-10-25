from django.utils import timezone

from .models import ArcadeSettings, Event, Season


def league_context(request):
    active = Season.get_active()
    arcade_settings = ArcadeSettings.objects.filter(pk=1).select_related("competition_event").first()
    try:
        year = int(request.GET.get("season", ""))
    except (TypeError, ValueError):
        year = None
    selected = Season.objects.filter(year=year).first() if year else active
    arcade_event = arcade_settings.competition_event if arcade_settings else None
    selected_year = (selected or active).year
    now = timezone.now()
    next_prediction_event = (
        Event.objects.filter(
            season_year=selected_year,
            status__in=(Event.Status.OPEN, Event.Status.LOCKED),
            deadline__gt=now,
        )
        .order_by("deadline", "round_number")
        .first()
    )
    arcade_running = bool(
        arcade_settings
        and arcade_settings.public_enabled
        and arcade_settings.competition_opened_at
    )
    arcade_wheel_available = bool(
        arcade_settings
        and arcade_settings.competition_opened_at
        and arcade_event
        and arcade_event.status != Event.Status.SCORED
        and arcade_event.deadline <= now
        and (not arcade_event.race_datetime or arcade_event.race_datetime > now)
    )
    arcade_visible = bool(
        arcade_settings
        and arcade_event
        and arcade_event.season_year == selected_year
        and (not arcade_event.race_datetime or arcade_event.race_datetime > now)
        and (arcade_running or arcade_wheel_available)
    )
    return {
        "current_season": selected or active,
        "arcade_public_enabled": arcade_visible,
        "next_prediction_event": next_prediction_event,
    }
