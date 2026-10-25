import random
from datetime import timedelta

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from .models import CrazyPredictionVote, Event, Prediction

CRAZY_VOTE_DURATION = timedelta(hours=12)


def crazy_vote_closes_at(event):
    if not event or not event.deadline:
        return None
    return event.deadline + CRAZY_VOTE_DURATION


class CrazyVoteError(ValueError):
    pass


def crazy_vote_is_open(event, now=None):
    if event and event.crazy_vote_veto_cancelled_at:
        return False
    now = now or timezone.now()
    return bool(
        event
        and event.deadline
        and event.deadline <= now < crazy_vote_closes_at(event)
    )


def crazy_vote_is_finished(event, now=None):
    if event and event.crazy_vote_veto_cancelled_at:
        return True
    now = now or timezone.now()
    return bool(
        event
        and event.deadline
        and now >= crazy_vote_closes_at(event)
    )


def crazy_vote_candidates(event):
    candidates = list(
        Prediction.objects.filter(
            event=event,
            user__is_active=True,
            user__is_staff=False,
        )
        .exclude(crazy_prediction="")
        .select_related("user")
        .only("id", "event_id", "user_id", "user__username", "crazy_prediction")
        .order_by("id")
    )
    candidates = [item for item in candidates if item.crazy_prediction.strip()]
    # Stable, anonymous ordering: every participant sees the same card order, but it
    # does not follow usernames or expose the prediction primary keys.
    random.Random(f"crazy-jury-{event.pk}").shuffle(candidates)
    return candidates


def vetoed_crazy_prediction_id(event, now=None):
    """Return the unique top-voted prediction after the vote closes; ties do nothing."""
    if event and event.crazy_vote_veto_cancelled_at:
        return None
    now = now or timezone.now()
    if not crazy_vote_is_finished(event, now):
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
        raise CrazyVoteError("Голосование закрыто: оно длится ровно 12 часов после дедлайна предиктов.")
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
    vote, _ = CrazyPredictionVote.objects.update_or_create(
        event=locked_event,
        voter=voter,
        defaults={"target_prediction": target, "updated_at": now},
    )
    return vote


@transaction.atomic
def cancel_crazy_exclusion(event, actor, now=None):
    """Cancel only this event's jury veto; keep ballots and audit score changes."""
    from .models import Score
    from .scoring import publish_event_scores

    if not actor.is_active or not actor.is_staff:
        raise CrazyVoteError("Отменить исключение может только администратор.")
    now = now or timezone.now()
    locked = Event.objects.select_for_update().get(pk=event.pk)
    if locked.crazy_vote_veto_cancelled_at:
        return False
    if locked.deadline > now:
        raise CrazyVoteError("Голосование по этому этапу ещё не началось.")
    locked.crazy_vote_veto_cancelled_at = now
    locked.crazy_vote_veto_cancelled_by = actor
    locked.save(update_fields=("crazy_vote_veto_cancelled_at", "crazy_vote_veto_cancelled_by"))
    if locked.status == Event.Status.SCORED or Score.objects.filter(event=locked).exists():
        # Any failed recalculation rolls the cancellation back in the same transaction.
        publish_event_scores(locked, actor)
    return True


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
        "closes_at": crazy_vote_closes_at(event),
        "is_open": is_open,
        "eligible": eligible,
        "candidate_count": len(all_candidates),
        "has_enough_candidates": has_enough_candidates,
        "candidates": candidates,
        "has_voted": previous_vote is not None,
        "can_vote": eligible and is_open and has_enough_candidates,
    }
