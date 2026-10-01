import random

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from .models import CrazyPredictionVote, Event, Prediction


class CrazyVoteError(ValueError):
    pass


def crazy_vote_is_open(event, now=None):
    now = now or timezone.now()
    return bool(
        event
        and event.status != Event.Status.SCORED
        and event.race_datetime
        and event.deadline <= now < event.race_datetime
    )


def crazy_vote_candidates(event):
    candidates = list(
        Prediction.objects.filter(
            event=event,
            user__is_active=True,
            user__is_staff=False,
        )
        .exclude(crazy_prediction="")
        .only("id", "event_id", "user_id", "crazy_prediction")
        .order_by("id")
    )
    candidates = [item for item in candidates if item.crazy_prediction.strip()]
    # Stable, anonymous ordering: every participant sees the same card order, but it
    # does not follow usernames or expose the prediction primary keys.
    random.Random(f"crazy-jury-{event.pk}").shuffle(candidates)
    return candidates


def vetoed_crazy_prediction_id(event, now=None):
    """Return the unique top-voted prediction after the vote closes; ties do nothing."""
    now = now or timezone.now()
    if event is None or event.status != Event.Status.SCORED:
        if not event or not event.race_datetime or now < event.race_datetime:
            return None

    candidate_ids = [item.id for item in crazy_vote_candidates(event)]
    if not candidate_ids:
        return None

    totals = list(
        CrazyPredictionVote.objects.filter(event=event, target_prediction_id__in=candidate_ids)
        .values("target_prediction_id")
        .annotate(total=Count("id"))
        .order_by("-total", "target_prediction_id")[:2]
    )
    if not totals or (len(totals) > 1 and totals[0]["total"] == totals[1]["total"]):
        return None
    return totals[0]["target_prediction_id"]


@transaction.atomic
def cast_crazy_prediction_vote(event, voter, target_prediction_id, now=None):
    now = now or timezone.now()
    locked_event = Event.objects.select_for_update().get(pk=event.pk)
    if not crazy_vote_is_open(locked_event, now):
        raise CrazyVoteError("Голосование закрыто: оно проходит после дедлайна и до старта гонки.")
    if not voter.is_active or voter.is_staff:
        raise CrazyVoteError("Голосовать могут только участники лиги.")

    try:
        target_id = int(target_prediction_id)
    except (TypeError, ValueError) as exc:
        raise CrazyVoteError("Выбери один из анонимных предиктов.") from exc

    candidates = crazy_vote_candidates(locked_event)
    target = next((item for item in candidates if item.id == target_id), None)
    if target is None:
        raise CrazyVoteError("Этот предикт не участвует в голосовании.")
    if target.user_id == voter.id:
        raise CrazyVoteError("Нельзя голосовать за свой Crazy Prediction.")
    if len(candidates) < 2:
        raise CrazyVoteError("Для голосования нужно хотя бы два Crazy Prediction.")
    if CrazyPredictionVote.objects.filter(event=locked_event, voter=voter).exists():
        raise CrazyVoteError("Ты уже отдал голос за этот этап. Изменить его нельзя.")

    return CrazyPredictionVote.objects.create(
        event=locked_event,
        voter=voter,
        target_prediction=target,
    )


def crazy_jury_context(event, user, now=None):
    now = now or timezone.now()
    eligible = bool(user.is_authenticated and user.is_active and not user.is_staff)
    is_open = crazy_vote_is_open(event, now)
    all_candidates = crazy_vote_candidates(event) if is_open else []
    previous_vote = (
        CrazyPredictionVote.objects.filter(event=event, voter=user).first()
        if eligible and is_open
        else None
    )
    has_enough_candidates = len(all_candidates) >= 2
    candidates = []
    if eligible and has_enough_candidates:
        candidates = [
            {
                "id": item.id,
                "number": index + 1,
                "text": item.crazy_prediction.strip(),
                "is_own": item.user_id == user.id,
                "is_selected": bool(previous_vote and previous_vote.target_prediction_id == item.id),
            }
            for index, item in enumerate(all_candidates)
        ]

    return {
        "event": event,
        "is_open": is_open,
        "eligible": eligible,
        "candidate_count": len(all_candidates),
        "has_enough_candidates": has_enough_candidates,
        "candidates": candidates,
        "has_voted": previous_vote is not None,
        "can_vote": eligible and is_open and has_enough_candidates and previous_vote is None,
    }
