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
from . import vegas_rules as rules


def state(wallet):
    return {"balance": wallet.balance, "revision": wallet.revision,
            "free_spins": wallet.free_spins, "bonus_bet": wallet.bonus_bet}


@login_required
@require_GET
@never_cache
def page(request):
    if not request.user.is_active or not request.user.is_staff:
        return HttpResponseForbidden()
    wallet, _ = VegasLabWallet.objects.get_or_create(user=request.user)
    config = {"state": state(wallet), "last": wallet.last_payload.get("result"),
              "symbols": rules.SYMBOLS, "lines": rules.PAYLINES, "bets": rules.BETS,
              "spin_url": reverse("league:vegas_lab_spin")}
    return render(request, "arcade_vegas.html", {"vegas_config": config, "arcade_test_mode": True})


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
        if action not in ("spin", "reset") or scenario not in ("random", "bonus", "bigwin", "wild"):
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
    result = None
    if action == "reset":
        wallet.balance, wallet.free_spins, wallet.bonus_bet = rules.START_BALANCE, 0, rules.BETS[1]
    else:
        free = wallet.free_spins > 0
        bet = wallet.bonus_bet if free else data["bet"]
        if not free and wallet.balance < bet:
            return JsonResponse({"error": "Недостаточно игровых денег. В тесте можно сбросить баланс."}, status=400)
        result = rules.outcome(bet, free=free, scenario=scenario)
        wallet.balance += result["payout"] - (0 if free else bet)
        wallet.free_spins = min(rules.MAX_FREE_SPINS, wallet.free_spins - int(free) + result["awarded"])
        if result["awarded"] and not free:
            wallet.bonus_bet = bet
    wallet.revision += 1
    wallet.last_request, wallet.last_spun_at = request_id, now
    wallet.last_payload = {"state": state(wallet), "result": result, "request_id": str(request_id)}
    wallet.save()
    return JsonResponse(wallet.last_payload)
