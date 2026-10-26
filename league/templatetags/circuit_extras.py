from django import template
from league.models import DriverProfile
from league.driver_profiles import TEAM_COLORS

register = template.Library()


@register.simple_tag(takes_context=True)
def circuit_drivers(context):
    event = context.get("event") or context.get("featured_event") or context.get("next_event")
    year = getattr(event, "season_year", None) or getattr(context.get("current_season"), "year", 2026)
    request = context.get("request")
    cache = getattr(request, "_circuit_driver_rosters", {})
    if year not in cache:
        drivers = list(DriverProfile.objects.filter(season_year=year).order_by("number").values("key", "name", "team", "number"))
        # The decorative preview can also be shown before next season is configured.
        if not drivers:
            drivers = list(DriverProfile.objects.filter(season_year=2026).order_by("number").values("key", "name", "team", "number"))
        cache[year] = [dict(driver, color=TEAM_COLORS.get(driver["team"].strip().casefold(), "#b5c0ce")) for driver in drivers]
        if request is not None:
            request._circuit_driver_rosters = cache
    return cache[year]
