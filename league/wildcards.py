from django.db import transaction
from django.utils import timezone

from .models import (
    Event,
    EventWildcardDeck,
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


def _get_shared_deck(event):
    deck = EventWildcardDeck.objects.filter(event=event).prefetch_related("cards__question").first()
    if deck and deck.cards.count() == 3:
        return deck
    raise WildcardActionError("Администратор ещё не выбрал три карты для этого этапа.")


@transaction.atomic
def get_or_create_wildcard_offer(event, user):
    locked_event = Event.objects.select_for_update().get(pk=event.pk)
    existing = (
        PlayerWildcardOffer.objects.filter(event=locked_event, user=user)
        .prefetch_related("cards__question")
        .first()
    )
    if existing and locked_event.voting_state() != "open":
        return existing, False

    _ensure_open(locked_event)
    deck = _get_shared_deck(locked_event)
    shared_cards = list(deck.cards.all())

    if existing:
        player_has_picked = PlayerWildcard.objects.filter(event=locked_event, user=user).exists()
        current_cards = list(existing.cards.order_by("slot").values_list("slot", "question_id"))
        shared_values = [(item.slot, item.question_id) for item in shared_cards]
        if not player_has_picked and current_cards != shared_values:
            existing.cards.all().delete()
            PlayerWildcardOfferCard.objects.bulk_create(
                [
                    PlayerWildcardOfferCard(
                        offer=existing,
                        question_id=card.question_id,
                        slot=card.slot,
                    )
                    for card in shared_cards
                ]
            )
            existing = PlayerWildcardOffer.objects.prefetch_related("cards__question").get(pk=existing.pk)
        return existing, False

    offer = PlayerWildcardOffer.objects.create(event=locked_event, user=user)
    PlayerWildcardOfferCard.objects.bulk_create(
        [
            PlayerWildcardOfferCard(
                offer=offer,
                question_id=card.question_id,
                slot=card.slot,
            )
            for card in shared_cards
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
    if choice == EventWildcardQuestion.Option.C and not assignment.question.option_c:
        raise WildcardActionError("У этой карты нет третьего варианта ответа.")

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
