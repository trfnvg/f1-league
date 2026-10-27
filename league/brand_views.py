"""Public browser icon fallback, including pages outside the main site layout."""
from django.conf import settings
from django.http import FileResponse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_safe


@require_safe
@cache_control(public=True, max_age=3600)
def favicon(request):
    icon = settings.BASE_DIR / "league" / "static" / "league" / "favicon.ico"
    return FileResponse(icon.open("rb"), content_type="image/x-icon")
