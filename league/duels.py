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


def previous_event_for(event):
    """Return the immediately preceding event in the same season."""
    return (
        Event.objects.filter(
            season_year=event.season_year,
            round_number__lt=event.round_number,
        )
        .order_by("-round_number")
        .first()
    )


def previous_event_duel_targets(event, user):
    """Return opponents this user challenged on the immediately prior event."""
    previous_event = previous_event_for(event)
    if previous_event is None:
        return DuelChallenge.objects.none()
    return DuelChallenge.objects.filter(
        event=previous_event,
        challenger=user,
    ).values("opponent_id")


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
    queryset = (
        User.objects.filter(is_active=True, is_staff=False)
        .exclude(id=user.id)
        .exclude(id__in=occupied_ids)
    )
    # A player may not target the same opponent on two consecutive events.
    # Keep the option out of the form as well as enforcing it in the service
    # below, so the rule is visible before a challenge is submitted.
    queryset = queryset.exclude(id__in=previous_event_duel_targets(event, user))
    return queryset.order_by("username")


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
    if previous_event_duel_targets(event, challenger).filter(opponent_id=opponent.id).exists():
        raise DuelActionError("Нельзя выбирать одного и того же соперника два этапа подряд.")

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
