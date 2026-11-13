"""Approved casino catalogue. Purchasing/scoring are not enabled in the lab."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .models import VegasLabWallet
from .vegas_rules import START_BALANCE


PRODUCTS = (
    {"key": "wheel", "name": "Грязный руль", "price": "10 000 $", "cost": 1_000_000, "kind": "Атака",
     "description": "Отнимает 3 очка у выбранного соперника в зачёте этапа твоей лиги. Паддок-пасс блокирует атаку, зеркальные понтоны отражают её отправителю.",
     "rule": "−3 очка сопернику · после расчёта дуэли", "scoring_phase": "after_duel", "points": -3},
    {"key": "tyres", "name": "Свежий комплект", "price": "5 000 $", "cost": 500_000, "kind": "Усиление",
     "description": "Добавляет 1 очко к твоему результату этапа в выбранной лиге. Это очко не помогает выиграть дуэль.",
     "rule": "+1 очко себе · после расчёта дуэли", "scoring_phase": "after_duel", "points": 1},
    {"key": "redflag", "name": "Красный флаг", "price": "15 000 $", "cost": 1_500_000, "kind": "Отмена дуэли",
     "description": "Отменяет твою принятую дуэль до начала гонки. Оба участника остаются без выигрыша и штрафа за эту дуэль. После старта гонки использовать нельзя.",
     "rule": "Только до начала гонки · отмена для обоих участников", "scoring_phase": "before_race"},
    {"key": "mirrors", "name": "Зеркальные понтоны", "price": "15 000 $", "cost": 1_500_000, "kind": "Отражение",
     "description": "Отражает одну атаку «Грязный руль» обратно отправителю. Отражённую атаку нельзя отразить повторно. На исход дуэли не влияет.",
     "rule": "Одно отражение · штраф после расчёта дуэли", "scoring_phase": "after_duel"},
    {"key": "teamorder", "name": "Командный приказ", "price": "7 000 $", "cost": 700_000, "kind": "Помощь другу",
     "description": "Добавляет 2 очка другому участнику твоей лиги. Себя выбрать нельзя. Подаренные очки не участвуют в определении победителя дуэли.",
     "rule": "+2 очка другому игроку · после расчёта дуэли", "scoring_phase": "after_duel", "points": 2},
    {"key": "insurance", "name": "Страховка дуэли", "price": "8 000 $", "cost": 800_000, "kind": "Страховка",
     "description": "При поражении возвращает половину очков, потерянных в дуэли. Сначала определяется победитель и обычный штраф, затем начисляется компенсация. Поражение не превращается в ничью или победу.",
     "rule": "Возврат 50% штрафа · после расчёта дуэли", "scoring_phase": "after_duel"},
    {"key": "constructors", "name": "Кубок конструкторов", "price": "35 000 $", "cost": 3_500_000, "kind": "Командная награда",
     "description": "Ты и выбранный напарник из твоей лиги получаете по 3 очка к результату этапа. Напарником должен быть другой участник. Оба бонуса начисляются после расчёта дуэлей и не меняют их исход.",
     "rule": "+3 очка тебе и +3 напарнику · после расчёта дуэлей", "scoring_phase": "after_duel", "points": 3, "ally_points": 3},
    {"key": "paddockpass", "name": "Паддок-пасс", "price": "40 000 $", "cost": 4_000_000, "kind": "Премиальный доступ",
     "description": "Защищает от негативных предметов соперников на один этап и добавляет тебе 3 очка после расчёта дуэли. Не отменяет штраф за поражение в самой дуэли. Не складывается со «Свежим комплектом».",
     "rule": "Защита от атак и +3 очка себе · после расчёта дуэли", "scoring_phase": "after_duel", "points": 3,
     "blocks_attacks": True, "incompatible_with": ["tyres"]},
)


@login_required
@require_GET
@never_cache
def page(request):
    if not request.user.is_active or not request.user.is_staff:
        return HttpResponseForbidden()
    # Opening the showroom never creates or changes a wallet.
    balance = VegasLabWallet.objects.filter(user=request.user).values_list("balance", flat=True).first()
    return render(request, "arcade_vegas_shop.html", {
        "products": PRODUCTS, "shop_balance": START_BALANCE if balance is None else balance,
        "shop_unlimited_balance": request.user.is_superuser,
        "arcade_test_mode": True,
    })
