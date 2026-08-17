import secrets

from django.db import transaction
from django.utils import timezone

from .models import (
    Event,
    EventWildcardDeck,
    EventWildcardDeckCard,
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


def _weighted_sample(questions, count):
    """Choose distinct questions while respecting their configured rarity."""
    remaining = list(questions)
    selected = []
    for _ in range(count):
        total_weight = sum(max(1, item.draw_weight) for item in remaining)
        marker = secrets.randbelow(total_weight)
        cursor = 0
        for index, question in enumerate(remaining):
            cursor += max(1, question.draw_weight)
            if marker < cursor:
                selected.append(remaining.pop(index))
                break
    return selected


def _get_or_create_shared_deck(event):
    deck = EventWildcardDeck.objects.filter(event=event).prefetch_related("cards__question").first()
    if deck and deck.cards.count() == 3:
        return deck

    if deck:
        deck.cards.all().delete()

    questions = list(
        EventWildcardQuestion.objects.filter(event=event, is_active=True).order_by("id")
    )
    if len(questions) < 3:
        raise WildcardActionError("Для этапа нужно подготовить минимум три активные карты.")

    # If this stage already had offers under the old personal-random logic,
    # preserve the earliest trio as the shared deck and align later players to it.
    legacy_offer = (
        PlayerWildcardOffer.objects.filter(event=event)
        .prefetch_related("cards__question")
        .order_by("created_at", "id")
        .first()
    )
    legacy_cards = list(legacy_offer.cards.all()) if legacy_offer else []
    if len(legacy_cards) == 3:
        selected = [item.question for item in legacy_cards]
    else:
        selected = _weighted_sample(questions, 3)

    if not deck:
        deck = EventWildcardDeck.objects.create(event=event)
    EventWildcardDeckCard.objects.bulk_create(
        [
            EventWildcardDeckCard(deck=deck, question=question, slot=slot)
            for slot, question in enumerate(selected, start=1)
        ]
    )
    return EventWildcardDeck.objects.prefetch_related("cards__question").get(pk=deck.pk)


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
    deck = _get_or_create_shared_deck(locked_event)
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
