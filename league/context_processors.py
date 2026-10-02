from .models import ArcadeSettings, Season


def league_context(request):
    active = Season.get_active()
    arcade_settings = ArcadeSettings.objects.filter(pk=1).only("public_enabled").first()
    try:
        year = int(request.GET.get("season", ""))
    except (TypeError, ValueError):
        year = None
    selected = Season.objects.filter(year=year).first() if year else active
    return {
        "current_season": selected or active,
        "arcade_public_enabled": bool(arcade_settings and arcade_settings.public_enabled),
    }
