"""Social reactions are scoped separately from votes and never affect scoring."""
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .crazy_jury import crazy_vote_is_open
from .models import CrazyReaction, Event, League, LeagueSeason, Prediction

KINDS = (("heart", "❤️", "Сердечко"), ("fire", "🔥", "Огонёк"), ("poop", "💩", "Какашка"))


def summaries(predictions, viewer, league=None):
    predictions = [p for p in predictions if p.crazy_prediction.strip()]
    result = {p.pk: {"prediction_id": p.pk, "options": [
        {"kind": key, "emoji": emoji, "label": label, "count": 0, "selected": False}
        for key, emoji, label in KINDS],
        "can_react": bool(viewer.is_authenticated and viewer.is_active and viewer.pk != p.user_id),
        "url": reverse("league:friend_league_reaction", args=[league.pk, p.event_id, p.pk]) if league else
               reverse("league:crazy_reaction", args=[p.event_id, p.pk]),
    } for p in predictions}
    if not result:
        return result
    reactions = CrazyReaction.objects.filter(prediction_id__in=result, league=league)
    counts = {(row["prediction_id"], row["kind"]): row["count"] for row in
        reactions.values("prediction_id", "kind").annotate(count=Count("pk"))}
    own = dict(reactions.filter(user=viewer).values_list("prediction_id", "kind")) if viewer.is_authenticated else {}
    for pk, summary in result.items():
        for option in summary["options"]:
            option["count"] = counts.get((pk, option["kind"]), 0)
            option["selected"] = own.get(pk) == option["kind"]
    return result


@login_required
@never_cache
@require_POST
def react(request, event_id, prediction_id, league_id=None):
    kind = request.POST.get("kind")
    if kind not in CrazyReaction.Kind.values:
        return JsonResponse({"error": "Неизвестная реакция."}, status=400)
    event = get_object_or_404(Event, pk=event_id)
    now = timezone.now()
    if event.deadline > now:
        raise Http404("Прогнозы ещё закрыты.")
    league = None
    prediction = get_object_or_404(Prediction.objects.select_related("user"),
        pk=prediction_id, event=event, created_at__lt=event.deadline, user__is_active=True)
    if not prediction.crazy_prediction.strip():
        raise Http404("Крейзи-предикт не найден.")
    if league_id:
        from .league_views import _league
        league = _league(request, league_id)
        season = get_object_or_404(LeagueSeason, league=league, season__year=event.season_year,
            start_event__round_number__lte=event.round_number, ruleset="paddock")
        if not season.entries.filter(membership__user=prediction.user, membership__is_active=True,
                first_event__round_number__lte=event.round_number).exists():
            raise Http404("Участник не выступает в этом этапе лиги.")
    elif crazy_vote_is_open(event, now) or prediction.user.is_staff:
        raise Http404("Реакции пока недоступны.")
    if not request.user.is_active or request.user.pk == prediction.user_id:
        raise PermissionDenied("Реакции доступны только на чужие прогнозы.")
    with transaction.atomic():
        if league:
            from .leagues import membership_for
            league = League.objects.select_for_update().get(pk=league.pk)
            membership_for(request.user, league)
        # Serialize changes by this user, including simultaneous first clicks.
        actor = User.objects.select_for_update().get(pk=request.user.pk)
        if not actor.is_active:
            raise PermissionDenied("Аккаунт недоступен.")
        existing = CrazyReaction.objects.filter(prediction=prediction, user=request.user, league=league).first()
        if existing and existing.kind == kind:
            existing.delete()
        elif existing:
            existing.kind = kind
            existing.save(update_fields=["kind"])
        else:
            CrazyReaction.objects.create(prediction=prediction, user=request.user, league=league, kind=kind)
    if request.headers.get("Accept") == "application/json":
        return JsonResponse(summaries([prediction], request.user, league)[prediction.pk])
    if league:
        return redirect(reverse("league:friend_league_event", args=[league.pk, event.pk])+"?manage=1")
    return redirect("league:event_detail", event_id=event.pk)
