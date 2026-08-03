from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import DuelChallenge, Event


ACTIVE_DUEL_STATUSES = (
    DuelChallenge.Status.PENDING,
    DuelChallenge.Status.ACCEPTED,
)


class DuelActionError(ValueError):
    pass


def _ensure_duels_are_open(event):
    if event.voting_state() != "open":
        raise DuelActionError("Вызовы закрываются одновременно с дедлайном прогнозов.")


def active_duels_for(event):
    return DuelChallenge.objects.filter(event=event, status__in=ACTIVE_DUEL_STATUSES)


def get_user_event_duel(event, user):
    if not getattr(user, "is_authenticated", False):
        return None
    return (
        DuelChallenge.objects.filter(event=event)
        .filter(Q(challenger=user) | Q(opponent=user))
        .filter(status__in=ACTIVE_DUEL_STATUSES)
        .select_related(
            "challenger",
            "opponent",
            "winner",
            "challenger__league_profile",
            "opponent__league_profile",
        )
        .first()
    )


def available_opponents(event, user):
    occupied_ids = set()
    for challenger_id, opponent_id in active_duels_for(event).values_list("challenger_id", "opponent_id"):
        occupied_ids.update((challenger_id, opponent_id))
    return (
        User.objects.filter(is_active=True, is_staff=False)
        .exclude(id=user.id)
        .exclude(id__in=occupied_ids)
        .order_by("username")
    )


@transaction.atomic
def create_duel_challenge(event, challenger, opponent, stake):
    event = Event.objects.select_for_update().get(pk=event.pk)
    _ensure_duels_are_open(event)

    if challenger.id == opponent.id:
        raise DuelActionError("Нельзя вызвать на дуэль самого себя.")
    if not opponent.is_active or opponent.is_staff:
        raise DuelActionError("Этого участника нельзя вызвать на дуэль.")
    if not 1 <= int(stake) <= 10:
        raise DuelActionError("Ставка должна быть от 1 до 10 очков.")

    locked_duels = active_duels_for(event).select_for_update()
    if locked_duels.filter(Q(challenger=challenger) | Q(opponent=challenger)).exists():
        raise DuelActionError("У тебя уже есть активная дуэль на этот этап.")
    if locked_duels.filter(Q(challenger=opponent) | Q(opponent=opponent)).exists():
        raise DuelActionError("У этого участника уже есть активная дуэль на этот этап.")

    return DuelChallenge.objects.create(
        event=event,
        challenger=challenger,
        opponent=opponent,
        stake=int(stake),
    )


@transaction.atomic
def respond_to_duel(challenge, user, *, accept):
    challenge = DuelChallenge.objects.select_for_update().select_related("event").get(pk=challenge.pk)
    _ensure_duels_are_open(challenge.event)
    if challenge.opponent_id != user.id:
        raise DuelActionError("Ответить на вызов может только приглашённый участник.")
    if challenge.status != DuelChallenge.Status.PENDING:
        raise DuelActionError("На этот вызов уже ответили.")

    challenge.status = DuelChallenge.Status.ACCEPTED if accept else DuelChallenge.Status.DECLINED
    challenge.responded_at = timezone.now()
    challenge.save(update_fields=("status", "responded_at", "updated_at"))
    return challenge


@transaction.atomic
def cancel_duel_challenge(challenge, user):
    challenge = DuelChallenge.objects.select_for_update().select_related("event").get(pk=challenge.pk)
    _ensure_duels_are_open(challenge.event)
    if challenge.challenger_id != user.id:
        raise DuelActionError("Отменить вызов может только его автор.")
    if challenge.status != DuelChallenge.Status.PENDING:
        raise DuelActionError("Можно отменить только вызов, который ещё не принят.")

    challenge.status = DuelChallenge.Status.CANCELLED
    challenge.responded_at = timezone.now()
    challenge.save(update_fields=("status", "responded_at", "updated_at"))
    return challenge
