from django.utils import timezone

from .models import ArcadeSettings, Event
from .home_events import select_current_event
from .services import get_selected_season


def league_context(request):
    selected = get_selected_season(request)
    arcade_settings = ArcadeSettings.objects.filter(pk=1).select_related("competition_event").first()
    arcade_event = arcade_settings.competition_event if arcade_settings else None
    selected_year = selected.year
    now = timezone.now()
    events = getattr(request, "_navigation_events", None)
    if events is None:
        events = Event.objects.filter(season_year=selected_year).order_by("round_number")
    current_event = select_current_event(events, now)
    viewer_profile = getattr(request.user, "league_profile", None) if request.user.is_authenticated else None
    viewer_avatar_url = viewer_profile.avatar.url if viewer_profile and viewer_profile.avatar else ""
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
        "current_season": selected,
        "arcade_public_enabled": arcade_visible,
        "current_event": current_event,
        "next_prediction_event": current_event,
        "viewer_avatar_url": viewer_avatar_url,
    }
