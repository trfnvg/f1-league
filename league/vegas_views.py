"""Staff-only slot sandbox. Server owns funds, RNG, bonus state and retries."""
import json
import uuid

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .models import VegasLabWallet
from .identity import display_name
from . import vegas_rules as rules


def bonus_state(wallet):
    # Persist the running series in the already atomic/idempotent response.
    # Older active bonuses start tracking their remaining spins on upgrade.
    saved = wallet.last_payload.get("state", {}).get("bonus")
    return dict(saved) if saved else {"win": 0, "played": 0, "granted": wallet.free_spins}


def state(wallet, bonus=None):
    return {"balance": wallet.balance, "revision": wallet.revision,
            "free_spins": wallet.free_spins, "bonus_bet": wallet.bonus_bet,
            "bonus": bonus if bonus is not None else bonus_state(wallet)}


@login_required
@require_GET
@never_cache
def page(request):
    if not request.user.is_active or not request.user.is_staff:
        return HttpResponseForbidden()
    wallet, _ = VegasLabWallet.objects.get_or_create(user=request.user)
    config = {"state": state(wallet), "last": wallet.last_payload.get("result"),
              "last_purchase": wallet.last_payload.get("bonus_purchase"),
              "bonus_buy": {"multiplier": rules.BONUS_BUY_MULTIPLIER, "spins": rules.BONUS_BUY_SPINS},
              "min_spin_interval_ms": int(getattr(settings, "VEGAS_LAB_MIN_INTERVAL", 0.8)*1000),
              "symbols": rules.SYMBOLS, "bets": rules.BETS, "default_bet": rules.DEFAULT_BET,
              "spin_url": reverse("league:vegas_lab_spin"),
              "balances_url": reverse("league:vegas_lab_balances")}
    config["player"] = {"id": request.user.pk, "name": display_name(request.user)}
    return render(request, "arcade_vegas.html", {"vegas_config": config, "arcade_test_mode": True})


@login_required
@require_GET
@never_cache
def balances(request):
    if not request.user.is_active or not request.user.is_staff:
        return HttpResponseForbidden()
    # Only public names and virtual balances. Reading this board never creates
    # wallets. Deterministic ordering and bounded pages keep polling cheap.
    try:
        offset = max(0, min(int(request.GET.get("offset", 0)), 100_000))
    except (ValueError, TypeError):
        offset = 0
    wallets = VegasLabWallet.objects.filter(user__is_active=True).select_related("user").only(
        "balance", "user_id", "user__id", "user__first_name", "user__last_name", "user__username"
    ).order_by("-balance", "user_id")
    batch = list(wallets[offset:offset+51])
    return JsonResponse({"players": [
        {"id": wallet.user_id, "name": display_name(wallet.user), "balance": wallet.balance,
         "rank": offset+index+1, "is_you": wallet.user_id == request.user.pk}
        for index, wallet in enumerate(batch[:50])],
        "next_offset": offset+50 if len(batch)>50 else None,
        "own_balance": VegasLabWallet.objects.filter(user=request.user).values_list("balance", flat=True).first()})


@login_required
@require_POST
@never_cache
@transaction.atomic
def spin(request):
    if not request.user.is_active or not request.user.is_staff:
        return HttpResponseForbidden()
    try:
        if int(request.META.get("CONTENT_LENGTH") or 0) > 2048 or len(request.body) > 2048:
            raise ValueError
        data = json.loads(request.body)
        if not isinstance(data, dict) or set(data) - {"request_id", "revision", "bet", "scenario", "action"}:
            raise ValueError
        request_id = uuid.UUID(data["request_id"])
        if type(data["revision"]) is not int or data["revision"] < 0:
            raise ValueError
        action = data.get("action", "spin")
        scenario = data.get("scenario", "random")
        if action not in ("spin", "reset", "buy_bonus") or scenario not in ("random", "bonus", "bigwin", "wild"):
            raise ValueError
        if action == "buy_bonus" and scenario != "random":
            raise ValueError
        if type(data.get("bet")) is not int or data["bet"] not in rules.BETS:
            raise ValueError
    except (ValueError, KeyError, TypeError, UnicodeDecodeError, RecursionError):
        return JsonResponse({"error": "Некорректный запрос прокрутки."}, status=400)
    wallet, _ = VegasLabWallet.objects.get_or_create(user=request.user)
    wallet = VegasLabWallet.objects.select_for_update().get(pk=wallet.pk)
    if wallet.last_request == request_id:
        return JsonResponse(wallet.last_payload)
    if wallet.revision != data["revision"]:
        return JsonResponse({"error": "Баланс изменился в другой вкладке. Обнови состояние.",
                             "state": state(wallet)}, status=409)
    now = timezone.now()
    interval = getattr(settings, "VEGAS_LAB_MIN_INTERVAL", 0.8)
    if wallet.last_spun_at and (now-wallet.last_spun_at).total_seconds() < interval:
        return JsonResponse({"error": "Дождись завершения прокрутки."}, status=429)
    result, purchase = None, None
    bonus = bonus_state(wallet)
    if action == "reset":
        wallet.balance, wallet.free_spins, wallet.bonus_bet = rules.START_BALANCE, 0, rules.DEFAULT_BET
        bonus = {"win": 0, "played": 0, "granted": 0}
    elif action == "buy_bonus":
        if wallet.free_spins:
            return JsonResponse({"error": "Сначала заверши текущий бонусный стинт."}, status=400)
        cost = data["bet"] * rules.BONUS_BUY_MULTIPLIER
        if wallet.balance < cost:
            return JsonResponse({"error": "Недостаточно игровых денег для покупки бонуса."}, status=400)
        wallet.balance -= cost
        wallet.bonus_bet, wallet.free_spins = data["bet"], rules.BONUS_BUY_SPINS
        bonus = {"win": 0, "played": 0, "granted": rules.BONUS_BUY_SPINS}
        purchase = {"bet": data["bet"], "cost": cost, "spins": rules.BONUS_BUY_SPINS,
                    "grid": rules.bonus_buy_grid()}
    else:
        free = wallet.free_spins > 0
        bet = wallet.bonus_bet if free else data["bet"]
        if not free and wallet.balance < bet:
            return JsonResponse({"error": "Недостаточно игровых денег. В тесте можно сбросить баланс."}, status=400)
        result = rules.outcome(bet, free=free, scenario=scenario)
        wallet.balance += result["payout"] - (0 if free else bet)
        old_remaining = wallet.free_spins
        wallet.free_spins = min(rules.MAX_FREE_SPINS, wallet.free_spins - int(free) + result["awarded"])
        if free:
            bonus["win"] += result["payout"]
            bonus["played"] += 1
            bonus["granted"] += wallet.free_spins - (old_remaining-1)
        else:
            # The paid triggering spin has its own payout, outside the bonus.
            bonus = {"win": 0, "played": 0, "granted": wallet.free_spins}
        if result["awarded"] and not free:
            wallet.bonus_bet = bet
    wallet.revision += 1
    wallet.last_request, wallet.last_spun_at = request_id, now
    wallet.last_payload = {"state": state(wallet, bonus), "result": result, "request_id": str(request_id)}
    if purchase:
        wallet.last_payload["bonus_purchase"] = purchase
    wallet.save()
    return JsonResponse(wallet.last_payload)
