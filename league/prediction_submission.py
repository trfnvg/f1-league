"""The shared forecast is changed under the event lock, never by league ID."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .forms import PredictionForm
from .models import Event, Prediction


@transaction.atomic
def save_shared_prediction(*, user, event, data, include_crazy=True):
    if not user.is_authenticated or not user.is_active:
        raise PermissionDenied("Нужен активный аккаунт.")
    event = Event.objects.select_for_update().get(pk=event.pk)
    if event.voting_state() != "open" or timezone.now() >= event.deadline:
        raise ValidationError("Прогнозы для этого этапа закрыты.")
    prediction = Prediction.objects.select_for_update().filter(user=user, event=event).first()
    form = PredictionForm(data, instance=prediction, event=event)
    if not include_crazy:
        form.fields.pop("crazy_prediction", None)
    if not form.is_valid():
        return form, None
    prediction = form.save(commit=False)
    prediction.user = user;prediction.event = event
    prediction.save()
    return form, prediction
