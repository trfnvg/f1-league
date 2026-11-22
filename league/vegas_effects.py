"""League-only item overlay, strictly AFTER the stored duel calculation.

Never mutate Prediction, Score, DuelChallenge or other leagues' projections.
Rebuilding a table or recalculating the base result cannot double the bonus.
"""
from collections import defaultdict
from copy import copy

from .identity import display_name
from .models import DuelChallenge, VegasPurchase
from .vegas_shop import PRODUCTS


def event_activity(event, *, season=None, viewer=None, player=None, effects=()):
    """Display activations only in the league where they were applied."""
    if season is None and (viewer is None or not viewer.is_authenticated):
        return []
    items = VegasPurchase.objects.filter(
        wallet__competition__event=event, activated_at__isnull=False,
    ).select_related("wallet__user", "target", "duel__challenger", "duel__opponent", "league_season__league")
    if season is not None:
        items = items.filter(league_season=season)
    else:
        items = items.filter(league_season__league__archived_at__isnull=True,
            league_season__league__memberships__user=viewer,
            league_season__league__memberships__is_active=True)
    names = {product["key"]: product["name"] for product in PRODUCTS}
    effects_by_item = {effect["purchase_id"]: effect for effect in effects}
    rows = []
    for item in items.order_by("league_season__league__name", "league_season_id", "activated_at", "pk"):
        actor = item.wallet.user
        recipient = item.target or actor
        recipients = {recipient.pk}
        target = display_name(recipient) if item.target_id else "На себя"
        if item.duel_id:
            duel = item.duel
            opponent = duel.opponent if actor.pk == duel.challenger_id else duel.challenger
            if item.product == "redflag":
                recipients.add(opponent.pk)
                target = f"Оба участника дуэли с {display_name(opponent)}"
            else:
                target = f"На себя · дуэль с {display_name(opponent)}"
        effect = effects_by_item.get(item.pk)
        if player is not None and player.pk != actor.pk and player.pk not in recipients and effect is None:
            continue
        rows.append(dict(id=item.pk, actor=display_name(actor), target=target,
            product=names.get(item.product, item.product), league=item.league_season.league,
            activated_at=item.activated_at, effect=effect))
    return rows


def apply_items(season, scores_map):
    event_ids = {event_id for _, event_id in scores_map}
    if not event_ids:
        return
    items = list(VegasPurchase.objects.filter(league_season=season, activated_at__isnull=False,
        wallet__competition__event_id__in=event_ids).select_related("wallet__competition", "duel")
        .order_by("activated_at", "pk"))
    effects = defaultdict(list)
    def add(user, event, title, points, item):
        if (user, event) in scores_map:
            effects[user, event].append({"title": title, "points": points, "purchase_id": item.pk})
    shields, mirrors = set(), set()
    cancelled = {item.duel_id for item in items if item.product == "redflag" and item.duel_id}
    handled_cancellations = set()
    for item in items:
        key = item.wallet.user_id, item.wallet.competition.event_id
        if item.product == "paddockpass":
            shields.add(key)
        elif item.product == "mirrors":
            mirrors.add(key)
    for item in items:
        user, event, kind = item.wallet.user_id, item.wallet.competition.event_id, item.product
        if kind == "tyres":
            add(user, event, "Свежий комплект · после дуэли", 1, item)
        elif kind == "paddockpass":
            add(user, event, "Паддок-пасс · после дуэли", 3, item)
        elif kind == "teamorder":
            add(item.target_id, event, "Командный приказ · после дуэли", 2, item)
        elif kind == "constructors":
            for player in (user, item.target_id):
                add(player, event, "Кубок конструкторов · после дуэли", 3, item)
        elif kind == "wheel":
            target = item.target_id
            if (target, event) in shields:
                add(target, event, "Паддок-пасс заблокировал Грязный руль", 0, item)
            elif (target, event) in mirrors:
                mirrors.remove((target, event))
                add(target, event, "Зеркальные понтоны отразили Грязный руль", 0, item)
                add(user, event, "Отражённый Грязный руль" + (" · заблокирован Паддок-пассом" if (user, event) in shields else ""),
                    0 if (user, event) in shields else -3, item)
            else:
                add(target, event, "Грязный руль · после дуэли", -3, item)
        elif kind in {"redflag", "insurance"} and item.duel_id:
            duel = item.duel
            if duel.status != DuelChallenge.Status.SETTLED or not duel.winner_id:
                continue
            if kind == "redflag":
                if duel.pk in handled_cancellations:
                    continue
                # Undo this duel's stake only in this selected league.
                for player in (duel.challenger_id, duel.opponent_id):
                    add(player, event, "Красный флаг · отмена дуэли в лиге",
                        -duel.stake if player == duel.winner_id else duel.stake, item)
                handled_cancellations.add(duel.pk)
            elif item.duel_id not in cancelled and duel.winner_id != user:
                add(user, event, "Страховка дуэли · возврат половины штрафа", (duel.stake+1)//2, item)
    for key, additions in effects.items():
        original = scores_map[key]
        projected = copy(original)
        previous = sum(row["points"] for row in original.breakdown.get("vegas_items", []))
        projected.points = original.points - previous + sum(row["points"] for row in additions)
        projected.breakdown = {**original.breakdown, "vegas_items": additions}
        scores_map[key] = projected
