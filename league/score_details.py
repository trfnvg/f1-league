"""Read-only explanation of stored scores; never recalculate on a GET."""
from django.contrib.auth.models import User
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .models import (DRIVER_CHOICES, Event, LeagueCrazyDecision, LeagueDayDecision,
    LeagueEventScore, PlayerWildcard, Prediction, Result, Score)
from .identity import display_name


CATEGORIES = (
    ("p1", "P1", "Первое место"), ("p2", "P2", "Второе место"),
    ("p3", "P3", "Третье место"), ("pole", "Pole Position", "Поул"),
    ("fastest_lap", "Fastest Lap", "Быстрый круг"),
    ("driver_of_day", "Driver of the Day", "Гонщик дня"),
    ("safety_car_count", "Safety Car Count", "Safety Car"),
    ("dnf_count", "DNF Count", "Сходы"),
    ("sprint_qualifying_winner", "Sprint Qualifying Winner", "Поул спринта"),
    ("sprint_winner", "Sprint Winner", "Победитель спринта"),
)


def explain(score, prediction, result, event):
    snapshot = getattr(score, "input_data", {}) or {}
    predicted = snapshot.get("prediction", {})
    actual = snapshot.get("result", {})
    base = dict(score.breakdown.get("base", score.breakdown))
    drivers = dict(DRIVER_CHOICES)
    def value(data, obj, field):
        return data[field] if field in data else getattr(obj, field, None)
    def label(raw):
        if raw is None or raw == "":
            return "—"
        if isinstance(raw, list):
            return ", ".join(drivers.get(item, str(item)) for item in raw) or "—"
        return drivers.get(raw, str(raw))
    rows = []
    for field, key, title in CATEGORIES:
        if field.startswith("sprint_") and not event.has_sprint:
            continue
        top3 = base.pop(f"{key} (Top-3)", 0)
        points = base.pop(key, 0) + top3
        fact = value(actual, result, field)
        if field == "driver_of_day":
            fact = value(actual, result, "driver_of_day_multiple") or fact
        raw_prediction = value(predicted, prediction, field)
        rows.append(dict(title=title, field=field, prediction_raw=raw_prediction, actual_raw=fact,
            prediction=label(raw_prediction), actual=label(fact), points=points,
            note="В тройке, но на другом месте" if top3 else ""))
    extras = []
    for key, points in base.items():
        if isinstance(points, (int, float)):
            extras.append(dict(title=key, points=points))
    if "base" in score.breakdown:
        extras.append(dict(title="Crazy Prediction · решение лиги", points=score.crazy_points))
        extras.append(dict(title="Апдейт подиума", points=score.podium_adjustment))
        for adjustment in score.breakdown.get("adjustments", []):
            extras.append(dict(title=adjustment.get("reason") or "Поправка лиги", points=adjustment["points"]))
        day = snapshot.get("local", {}).get("driver_of_day")
        if day:
            extras.append(dict(title="Гонщик дня · решение лиги: " + label(day["drivers"]), points=day["delta"]))
    allocated = sum(row["points"] for row in rows + extras)
    if score.points != allocated:
        extras.append(dict(title="Прочие сохранённые начисления (детализация отсутствует)", points=score.points-allocated))
    return rows, extras


def decorate_rows(rows, year):
    """Presentation only: portraits belong to the event season, scores stay stored."""
    from .driver_profiles import picker_profiles
    profiles = {driver["key"]: driver for driver in picker_profiles(year)}
    labels = dict(DRIVER_CHOICES)
    markers = dict(zip((item[0] for item in CATEGORIES),
        ("P1", "P2", "P3", "POLE", "FL", "DOT", "SC", "DNF", "SQ", "SPR")))
    for row in rows:
        field = row["field"]
        row["marker"] = markers[field]
        for side in ("prediction", "actual"):
            raw = row[side + "_raw"]
            cards = []
            if not field.endswith("_count"):
                for key in raw if isinstance(raw, list) else [raw]:
                    if key is None or key == "":
                        continue
                    driver = profiles.get(key)
                    if not driver:
                        name, _, team = labels.get(key, str(key)).partition(" (")
                        driver = dict(key=key, surname=name, team=team.rstrip(")"),
                            photo="", number=None, url="", team_color="#a4b0c0")
                    cards.append(driver)
            row[side + "_drivers"] = cards
        if row["actual"] == "—":
            row["state"], row["status"] = "empty", "Нет данных"
        elif row["prediction"] == "—":
            row["state"], row["status"] = "empty", "Не заполнено"
        elif row["note"]:
            row["state"], row["status"] = "partial", "В тройке"
        elif row["points"] > 0:
            row["state"], row["status"] = "hit", "Засчитано"
        else:
            row["state"], row["status"] = "miss", "Без очков"
    return rows


@never_cache
@require_GET
def detail(request, event_id, user_id, league_id=None, recap=False):
    event = get_object_or_404(Event, pk=event_id)
    if event.deadline > timezone.now() or event.status != Event.Status.SCORED:
        raise Http404("Результат ещё не опубликован.")
    league = season = None
    notes = []
    if league_id:
        from .league_views import _league
        from .league_standings import standings
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.path)
        league = _league(request, league_id)
        season = get_object_or_404(league.seasons, season__year=event.season_year,
            start_event__round_number__lte=event.round_number)
        entry = get_object_or_404(season.entries.select_related("membership__user"),
            membership__user_id=user_id, first_event__round_number__lte=event.round_number)
        player = entry.membership.user
        if season.is_legacy:
            score = standings(season)["scores_map"].get((user_id, event_id))
            if score is None:
                raise Http404("Результат не найден.")
            day = LeagueDayDecision.objects.filter(league_season=season, event=event).select_related("reviewed_by").first()
            if day:
                names = ", ".join(dict(DRIVER_CHOICES).get(d, d) for d in day.drivers) or "Никто"
                notes.append(f"Гонщик дня в этой лиге: {names}. Решение: {display_name(day.reviewed_by)}.")
        else:
            score = get_object_or_404(LeagueEventScore, entry=entry, event=event)
        decision = LeagueCrazyDecision.objects.filter(entry=entry, event=event).select_related("reviewed_by").first()
        # New projections describe the decision used at the time of calculation.
        local_crazy = getattr(score, "input_data", {}).get("local", {}).get("crazy")
        if local_crazy:
            approved = local_crazy["approved"]
            judge = User.objects.filter(pk=local_crazy.get("reviewed_by")).first()
            notes.append(f"Крейзи-предикт: {'засчитан' if approved else 'не засчитан'}. Решение при расчёте: {display_name(judge) if judge else 'модератор'}.")
        elif season.is_legacy and decision:
            notes.append(f"Крейзи-предикт: {'засчитан' if decision.approved else 'не засчитан'}. Решение: {display_name(decision.reviewed_by)}.")
    else:
        score = get_object_or_404(Score.objects.select_related("user"), event=event, user_id=user_id)
        player = score.user
    prediction = Prediction.objects.filter(event=event, user_id=user_id, created_at__lt=event.deadline).first()
    result = Result.objects.filter(event=event).first()
    rows, extras = explain(score, prediction, result, event)
    wildcard = None
    if not season or season.is_legacy:
        wildcard = PlayerWildcard.objects.filter(event=event, user_id=user_id).select_related("question").first()
    if recap:
        from .race_recap import summary
        return render(request, "race_recap.html", dict(event=event, player=player, league=league,
            recap_data=summary(event=event, player=player, score=score, score_rows=rows, season=season)))
    reactions = None
    if prediction and (season is None or season.ruleset == "paddock"):
        from .crazy_jury import crazy_vote_is_open
        from .reactions import summaries
        if league or not crazy_vote_is_open(event):
            reactions = summaries([prediction], request.user, league).get(prediction.pk)
    decorate_rows(rows, event.season_year)
    return render(request, "score_detail.html", dict(event=event, player=player, score=score, reactions=reactions,
        league=league, league_season=season, score_rows=rows, extras=extras, notes=notes,
        prediction=prediction, wildcard=wildcard, show_crazy=not season or season.ruleset == "paddock",
        base_points=sum(row["points"] for row in rows), extra_points=sum(item["points"] for item in extras),
        hit_count=sum(row["points"] > 0 for row in rows),
        has_snapshot=bool(getattr(score, "input_data", {}))))
