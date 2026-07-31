from .models import Season


def league_context(request):
    active = Season.get_active()
    try:
        year = int(request.GET.get("season", ""))
    except (TypeError, ValueError):
        year = None
    selected = Season.objects.filter(year=year).first() if year else active
    return {
        "current_season": selected or active,
        "available_seasons": Season.objects.all(),
    }
