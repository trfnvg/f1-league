"""Staff-only reaction game preview."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@never_cache
@login_required
@require_GET
def preview(request):
    if not request.user.is_active or not request.user.is_staff:
        return HttpResponseForbidden()
    return render(request, "arcade_lights_out.html", {"arcade_test_mode": True})
