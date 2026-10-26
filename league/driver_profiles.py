from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from .models import DriverProfile


# Team accents tuned for legibility on the charcoal prediction controls.
TEAM_COLORS = {
    "mclaren": "#ffad61",
    "mercedes": "#62dfcd",
    "red bull": "#8bafff",
    "ferrari": "#ff8585",
    "williams": "#85bfff",
    "racing bulls": "#a6b8ff",
    "aston martin": "#71d6ae",
    "haas": "#e4e8ee",
    "audi": "#ff9399",
    "alpine": "#f1a3da",
    "cadillac": "#d8c49d",
}


def picker_profiles(year):
    return [{"key": driver.key, "name": driver.name, "surname": driver.surname,
             "team": driver.team, "number": driver.number, "photo": driver.photo_url,
             "team_color": TEAM_COLORS.get(driver.team.strip().casefold(), "#b5c0ce"),
             "url": reverse("league:driver_profile", args=(year, driver.key))}
            for driver in DriverProfile.objects.filter(season_year=year)]


def directory(request):
    years = list(DriverProfile.objects.order_by("-season_year").values_list("season_year", flat=True).distinct())
    try:
        year = int(request.GET.get("season", years[0] if years else 2026))
    except (ValueError, TypeError):
        year = years[0] if years else 2026
    return render(request, "drivers/directory.html", {"drivers": DriverProfile.objects.filter(season_year=year), "driver_year": year, "driver_years": years})


def detail(request, year, key):
    driver = get_object_or_404(DriverProfile, season_year=year, key=key)
    return render(request, "drivers/profile.html", {"driver": driver})
