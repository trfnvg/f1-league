"""Atomic event purchases and single-use, league-scoped item activations."""
import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .identity import display_name
from .models import (ArcadeCompetition, ArcadeSettings, DuelChallenge, Event, League,
    LeagueActivity, LeagueSeasonEntry, Prediction, VegasPurchase, VegasWallet)
from .vegas_shop import PRODUCTS
from .vegas_views import state

CATALOGUE = {p["key"]: p for p in PRODUCTS}
TARGETED = {"wheel", "teamorder", "constructors"}


def wallet_for(user, wallet_id, *, lock=False):
    try:
        if isinstance(wallet_id, bool) or not 1 <= int(wallet_id) <= 9223372036854775807:
            raise ValueError
        wallet_id = int(wallet_id)
    except (TypeError, ValueError, OverflowError):
        raise ValidationError("Некорректный игровой кошелёк.")
    wallet = get_object_or_404(VegasWallet.objects.select_related("competition__event"), pk=wallet_id, user=user)
    if not user.is_active or not wallet.competition_id or wallet.competition.game_key != "vegas" or not wallet.competition.opened_at:
        raise ValidationError("Покупки доступны только в соревновании Vegas Pit, не в свободной игре.")
    if lock:
        event = Event.objects.select_for_update().get(pk=wallet.competition.event_id)
        contest = ArcadeCompetition.objects.select_for_update().get(pk=wallet.competition_id)
        wallet = VegasWallet.objects.select_for_update().get(pk=wallet.pk)
        contest.event = event
        wallet.competition = contest
    return wallet


def entries_for(user_id, event):
    return LeagueSeasonEntry.objects.filter(membership__user_id=user_id,
        membership__user__is_active=True, membership__is_active=True,
        membership__league__archived_at__isnull=True,
        league_season__league_id=F("membership__league_id"),
        league_season__season__year=event.season_year, league_season__ruleset="paddock",
        first_event__round_number__lte=event.round_number,
        entered_at__lt=event.deadline,
        league_season__start_event__round_number__lte=event.round_number,
    ).filter(Q(league_season__is_legacy=True) | Q(entered_at__lt=F("first_event__deadline"))).select_related("league_season__league").order_by("pk")


def buying_open(wallet, now):
    contest, event = wallet.competition, wallet.competition.event
    return bool(contest.opened_at and contest.opened_at <= now < event.deadline and not contest.frozen_at
        and ArcadeSettings.objects.filter(pk=1, public_enabled=True, active_game="vegas",
            competition_event_id=contest.event_id, competition_opened_at=contest.opened_at).exists())


def payload(wallet):
    now, event = timezone.now(), wallet.competition.event
    items = {p.product: p for p in wallet.purchases.select_related("league_season__league", "target")}
    leagues = []
    for own in entries_for(wallet.user_id, event)[:50]:
        targets = LeagueSeasonEntry.objects.filter(league_season=own.league_season,
            membership__is_active=True, membership__user__is_active=True,
            first_event__round_number__lte=event.round_number,
            entered_at__lt=event.deadline).filter(Q(league_season__is_legacy=True) | Q(entered_at__lt=F("first_event__deadline"))).exclude(membership__user_id=wallet.user_id).select_related("membership__user")[:200]
        leagues.append({"id": own.league_season_id, "name": own.league_season.league.name,
            "targets": [{"id": t.membership.user_id, "name": display_name(t.membership.user)} for t in targets]})
    can_buy = buying_open(wallet, now) and bool(leagues)
    can_apply = bool(event.deadline <= now and event.race_datetime and now < event.race_datetime and event.status != Event.Status.SCORED)
    return {"wallet_id": wallet.pk, "state": state(wallet), "can_buy": can_buy,
        "can_apply": can_apply, "leagues": leagues,
        "deadline": event.deadline.isoformat(), "race_at": event.race_datetime.isoformat() if event.race_datetime else None,
        "event": event.name, "items": {key: {"owned": key in items,
            "applied": bool(key in items and items[key].activated_at),
            "league": items[key].league_season.league.name if key in items and items[key].league_season_id else None,
            "target": display_name(items[key].target) if key in items and items[key].target_id else None,
        } for key in CATALOGUE}}


@transaction.atomic
def purchase(*, user, wallet_id, product):
    wallet = wallet_for(user, wallet_id, lock=True)
    if not isinstance(product, str) or product not in CATALOGUE:
        raise ValidationError("Предмет не найден.")
    existing = wallet.purchases.filter(product=product).first()
    if existing:
        return wallet  # A lost response must never charge the same purchase twice.
    if not buying_open(wallet, timezone.now()):
        raise ValidationError("Покупки закрыты. Купить предмет можно до дедлайна аркады.")
    if not entries_for(user.pk, wallet.competition.event).exists():
        raise ValidationError("Для предметов нужно участвовать в этом этапе лиги с правилами «Паддок».")
    cost = CATALOGUE[product]["cost"]
    if wallet.balance < cost:
        raise ValidationError("Недостаточно игровых денег.")
    before = wallet.balance
    wallet.balance -= cost
    wallet.revision += 1
    if wallet.last_payload:
        wallet.last_payload = {**wallet.last_payload, "state": state(wallet)}
    wallet.save(update_fields=["balance", "revision", "last_payload"])
    VegasPurchase.objects.create(wallet=wallet, product=product, cost=cost,
        balance_before=before, balance_after=wallet.balance)
    return wallet


@transaction.atomic
def activate(*, user, wallet_id, product, league_season_id, target_id=None):
    wallet = wallet_for(user, wallet_id, lock=True)
    item = get_object_or_404(VegasPurchase.objects.select_for_update(), wallet=wallet, product=product)
    event, now = wallet.competition.event, timezone.now()
    if (type(league_season_id) is not int or not 1 <= league_season_id <= 9223372036854775807
            or (target_id is not None and (type(target_id) is not int or not 1 <= target_id <= 9223372036854775807))):
        raise ValidationError("Выбери лигу и участника.")
    if item.activated_at:
        if item.league_season_id == league_season_id and item.target_id == target_id:
            return wallet
        raise ValidationError("Предмет уже применён. Использовать его повторно нельзя.")
    if now < event.deadline:
        raise ValidationError("Применение откроется после дедлайна аркады.")
    if not event.race_datetime or now >= event.race_datetime or event.status == Event.Status.SCORED:
        raise ValidationError("Применение закрыто: предметы используются до старта гонки.")
    own = entries_for(user.pk, event).filter(league_season_id=league_season_id).first()
    if not own:
        raise ValidationError("Ты не участвуешь в этом этапе выбранной лиги «Паддок».")
    League.objects.select_for_update().get(pk=own.league_season.league_id)
    if not entries_for(user.pk, event).filter(pk=own.pk).exists():
        raise ValidationError("Участие в выбранной лиге больше не активно.")
    if not Prediction.objects.filter(user=user, event=event, created_at__lt=event.deadline).exists():
        raise ValidationError("Для применения нужен сохранённый до дедлайна прогноз.")
    if product in TARGETED:
        target = entries_for(target_id, event).filter(league_season_id=league_season_id).first() if target_id else None
        if target_id == user.pk or not target:
            raise ValidationError("Выбери другого участника этой лиги.")
        if not Prediction.objects.filter(user_id=target_id, event=event, created_at__lt=event.deadline).exists():
            raise ValidationError("У выбранного участника нет своевременного прогноза на этап.")
    elif target_id is not None:
        raise ValidationError("Для этого предмета не нужно выбирать соперника.")
    if product in {"tyres", "paddockpass"} and wallet.purchases.filter(
            product="tyres" if product == "paddockpass" else "paddockpass",
            league_season_id=league_season_id, activated_at__isnull=False).exists():
        raise ValidationError("Паддок-пасс и Свежий комплект нельзя применять вместе в одной лиге.")
    if product in {"redflag", "insurance"}:
        if not own.league_season.is_legacy:
            raise ValidationError("В этой лиге пока нет собственного зачёта дуэлей.")
        duel = DuelChallenge.objects.filter(event=event, status=DuelChallenge.Status.ACCEPTED).filter(
            Q(challenger=user) | Q(opponent=user)).first()
        if not duel:
            raise ValidationError("Для этого предмета нужна принятая дуэль на текущий этап.")
        opponent_id = duel.opponent_id if duel.challenger_id == user.pk else duel.challenger_id
        if not entries_for(opponent_id, event).filter(league_season_id=league_season_id).exists():
            raise ValidationError("Оба участника дуэли должны состоять в этой лиге.")
        item.duel = duel
    item.league_season_id, item.target_id, item.activated_at = league_season_id, target_id, now
    item.save(update_fields=["league_season", "target", "activated_at", "duel"])
    wallet.revision += 1
    if wallet.last_payload:
        wallet.last_payload = {**wallet.last_payload, "state": state(wallet)}
    wallet.save(update_fields=["revision", "last_payload"])
    LeagueActivity.objects.create(league=own.league_season.league, actor=user, action="vegas_item_applied",
        details={"purchase_id": item.pk, "product": product, "event_id": event.pk, "target_id": target_id})
    return wallet


@login_required
@never_cache
@require_GET
def status_view(request):
    try:
        wallet = wallet_for(request.user, request.GET.get("wallet"))
        return JsonResponse(payload(wallet))
    except (ValidationError, ValueError, TypeError):
        return JsonResponse({"error": "Для покупок открой Vegas Pit в зачёте этапа."}, status=400)


@login_required
@never_cache
@require_POST
def action_view(request, action):
    try:
        if len(request.body) > 2048:
            raise ValidationError("Слишком большой запрос.")
        data = json.loads(request.body)
        allowed = {"wallet_id", "product"} | ({"league_season_id", "target_id"} if action == "activate" else set())
        if not isinstance(data, dict) or set(data)-allowed or type(data.get("wallet_id")) is not int or not isinstance(data.get("product"), str):
            raise ValidationError("Некорректный запрос.")
        if action == "buy":
            wallet = purchase(user=request.user, wallet_id=data["wallet_id"], product=data["product"])
        else:
            wallet = activate(user=request.user, wallet_id=data["wallet_id"], product=data["product"],
                league_season_id=data.get("league_season_id"), target_id=data.get("target_id"))
        return JsonResponse(payload(wallet))
    except (ValidationError, ValueError, TypeError, UnicodeDecodeError, RecursionError) as error:
        return JsonResponse({"error": " ".join(error.messages) if isinstance(error, ValidationError) else "Некорректный запрос."}, status=400)
