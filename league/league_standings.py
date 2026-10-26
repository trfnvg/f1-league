"""Bounded, membership-scoped standings; original scores stay immutable."""
from collections import defaultdict
from types import SimpleNamespace
from django.db.models import F

from .identity import display_name
from .competition_scoring import _text_digest
from .models import (Event, LeagueCrazyDecision, LeagueDayDecision, LeagueEventScore,
    Prediction, Score, SeasonScore)


def standings(season):
    events = list(Event.objects.filter(season_year=season.season.year,
        round_number__gte=season.start_event.round_number).order_by("round_number"))
    entries = season.entries.select_related("membership__user__league_profile", "first_event")
    if season.is_legacy:
        entries = entries.filter(membership__user__is_staff=False, membership__user__is_active=True)
    entries = list(entries)
    users = [e.membership.user_id for e in entries]
    scores_map = {}
    bonuses = {}
    if season.is_legacy:
        scores = list(Score.objects.filter(user_id__in=users, event__in=events))
        bonuses = dict(SeasonScore.objects.filter(season_year=season.season.year,
            user_id__in=users).values_list("user_id", "points"))
        predictions = {p.pk: p for p in Prediction.objects.filter(user_id__in=users, event__in=events,
            created_at__lt=F("event__deadline"))}
        by_user_event = {(p.user_id, p.event_id): p for p in predictions.values()}
        decisions = {(d.entry.membership.user_id, d.event_id): d for d in
            LeagueCrazyDecision.objects.filter(entry__league_season=season).select_related("entry__membership")}
        days = {d.event_id: d for d in LeagueDayDecision.objects.filter(league_season=season)}
        for score in scores:
            key = (score.user_id, score.event_id)
            points = score.points
            breakdown = dict(score.breakdown)
            prediction = by_user_event.get(key)
            decision, day = decisions.get(key), days.get(score.event_id)
            if decision and prediction and decision.prediction_id == prediction.pk and decision.text_digest == _text_digest(prediction):
                points += (5 if decision.approved else 0)-score.breakdown.get("Crazy Prediction", 0)
                breakdown["Crazy Prediction"] = 5 if decision.approved else 0
            if day and prediction:
                points += (3 if (prediction.driver_of_day or "").strip().lower() in day.drivers else 0)-score.breakdown.get("Driver of the Day", 0)
                breakdown["Driver of the Day"] = 3 if (prediction.driver_of_day or "").strip().lower() in day.drivers else 0
            scores_map[key] = SimpleNamespace(points=points, breakdown=breakdown)
    else:
        for score in LeagueEventScore.objects.filter(entry__league_season=season).select_related("entry__membership"):
            scores_map[(score.entry.membership.user_id, score.event_id)] = score
    totals = defaultdict(int, bonuses)
    scored_ids = set()
    for (user_id, event_id), score in scores_map.items():
        totals[user_id] += score.points;scored_ids.add(event_id)
    scored = [e for e in events if e.pk in scored_ids]
    latest = scored[-1] if scored else None
    previous = sorted(entries, key=lambda e: (-(totals[e.membership.user_id]-getattr(scores_map.get((e.membership.user_id, latest.pk if latest else None)), "points", 0)), display_name(e.membership.user).lower()))
    previous_rank = {e.pk: i for i, e in enumerate(previous, 1)}
    entries.sort(key=lambda e: (-totals[e.membership.user_id], display_name(e.membership.user).lower()))
    latest_points = [s.points for (uid, eid), s in scores_map.items() if latest and eid == latest.pk]
    best = max(latest_points, default=None)
    rows = []
    for rank, entry in enumerate(entries, 1):
        user = entry.membership.user
        entry.rank, entry.total = rank, totals[user.pk]
        entry.rounds = sum((user.pk, e.pk) in scores_map for e in events)
        entry.is_owner = user.pk == season.league.owner_id
        profile = getattr(user, "league_profile", None)
        last = scores_map.get((user.pk, latest.pk)) if latest else None
        rows.append(dict(user=user, rank=rank, total=entry.total,
            movement=previous_rank[entry.pk]-rank if len(scored)>1 else 0,
            avatar_url=profile.avatar.url if profile and profile.avatar else None,
            latest_points=last.points if last else None, is_round_winner=bool(last and last.points==best)))
    return dict(entries=entries, rows=rows, events=events, scores_map=scores_map,
        result_events=list(reversed(scored)),
        latest_event=latest, round_winners=[r for r in rows if r["is_round_winner"]])
