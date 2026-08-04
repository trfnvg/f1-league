import secrets

from django.db import transaction
from django.utils import timezone

from .models import Event, EventWildcardQuestion, PlayerWildcard


class WildcardActionError(ValueError):
    pass


def _ensure_open(event):
    if event.voting_state() != "open":
        raise WildcardActionError("Личные карты закрываются вместе с дедлайном прогнозов.")


@transaction.atomic
def draw_wildcard(event, user, card_slot=2):
    try:
        card_slot = int(card_slot)
    except (TypeError, ValueError) as exc:
        raise WildcardActionError("Выбери одну из трёх карт.") from exc
    if card_slot not in (1, 2, 3):
        raise WildcardActionError("Выбери одну из трёх карт.")

    locked_event = Event.objects.select_for_update().get(pk=event.pk)
    existing = (
        PlayerWildcard.objects.select_related("question")
        .filter(event=locked_event, user=user)
        .first()
    )
    if existing:
        return existing, False

    _ensure_open(locked_event)
    question_ids = list(
        EventWildcardQuestion.objects.filter(event=locked_event, is_active=True)
        .order_by("id")
        .values_list("id", flat=True)
    )
    if not question_ids:
        raise WildcardActionError("Карты для этого этапа пока не подготовлены.")

    question = EventWildcardQuestion.objects.get(pk=secrets.choice(question_ids))
    assignment = PlayerWildcard.objects.create(
        event=locked_event,
        user=user,
        question=question,
        card_slot=card_slot,
    )
    return assignment, True


@transaction.atomic
def answer_wildcard(event, user, choice):
    if choice not in EventWildcardQuestion.Option.values:
        raise WildcardActionError("Выбери один из двух вариантов.")

    locked_event = Event.objects.select_for_update().get(pk=event.pk)
    _ensure_open(locked_event)
    assignment = (
        PlayerWildcard.objects.select_for_update()
        .select_related("question")
        .filter(event=locked_event, user=user)
        .first()
    )
    if not assignment:
        raise WildcardActionError("Сначала вытяни личную карту.")

    assignment.selected_option = choice
    assignment.answered_at = timezone.now()
    assignment.save(update_fields=("selected_option", "answered_at"))
    return assignment


def unresolved_wildcard_questions(event):
    return EventWildcardQuestion.objects.filter(
        event=event,
        correct_option="",
        draws__selected_option__in=EventWildcardQuestion.Option.values,
    ).distinct()
