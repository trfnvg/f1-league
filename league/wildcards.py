import secrets

from django.db import transaction
from django.utils import timezone

from .models import (
    Event,
    EventWildcardQuestion,
    PlayerWildcard,
    PlayerWildcardOffer,
    PlayerWildcardOfferCard,
)


class WildcardActionError(ValueError):
    pass


def _ensure_open(event):
    if event.voting_state() != "open":
        raise WildcardActionError("Личные карты закрываются вместе с дедлайном прогнозов.")


@transaction.atomic
def get_or_create_wildcard_offer(event, user):
    locked_event = Event.objects.select_for_update().get(pk=event.pk)
    existing = (
        PlayerWildcardOffer.objects.filter(event=locked_event, user=user)
        .prefetch_related("cards__question")
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
    if len(question_ids) < 3:
        raise WildcardActionError("Для этапа нужно подготовить минимум три активные карты.")

    selected_ids = secrets.SystemRandom().sample(question_ids, 3)
    offer = PlayerWildcardOffer.objects.create(event=locked_event, user=user)
    PlayerWildcardOfferCard.objects.bulk_create(
        [
            PlayerWildcardOfferCard(offer=offer, question_id=question_id, slot=slot)
            for slot, question_id in enumerate(selected_ids, start=1)
        ]
    )
    offer = PlayerWildcardOffer.objects.prefetch_related("cards__question").get(pk=offer.pk)
    return offer, True


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
    offer, _ = get_or_create_wildcard_offer(locked_event, user)
    try:
        offered_card = offer.cards.select_related("question").get(slot=card_slot)
    except PlayerWildcardOfferCard.DoesNotExist as exc:
        raise WildcardActionError("Эта карта не входит в твою персональную тройку.") from exc

    assignment = PlayerWildcard.objects.create(
        event=locked_event,
        user=user,
        question=offered_card.question,
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
