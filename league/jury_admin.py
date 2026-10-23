from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse

from .crazy_jury import cancel_crazy_exclusion
from .models import Event


@login_required
def cancel_exclusion(request, event_id):
    if not request.user.is_active or not request.user.is_staff:
        return HttpResponseForbidden("Эта операция доступна только администраторам.")
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    event = get_object_or_404(Event, pk=event_id)
    try:
        changed = cancel_crazy_exclusion(event, request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Исключение отменено. Голоса сохранены; опубликованные очки пересчитаны."
                         if changed else "Исключение на этом этапе уже отменено.")
    return redirect(f"{reverse('league:paddock_jury_admin')}?season={event.season_year}&event={event.pk}")
