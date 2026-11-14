"""Casino catalogue and event inventory. The staff lab remains a showroom."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .models import VegasLabWallet, VegasWallet
from .vegas_rules import START_BALANCE


_CATALOGUE = (
    {"key": "wheel", "name": "Грязный руль", "price": "6 000 $", "cost": 600_000, "kind": "Атака",
     "description": "Отнимает 3 очка у выбранного соперника в зачёте этапа твоей лиги. Паддок-пасс блокирует атаку, зеркальные понтоны отражают её отправителю.",
     "rule": "−3 очка сопернику · после расчёта дуэли", "scoring_phase": "after_duel", "points": -3},
    {"key": "tyres", "name": "Свежий комплект", "price": "2 500 $", "cost": 250_000, "kind": "Усиление",
     "description": "Добавляет 1 очко к твоему результату этапа в выбранной лиге. Это очко не помогает выиграть дуэль.",
     "rule": "+1 очко себе · после расчёта дуэли", "scoring_phase": "after_duel", "points": 1},
    {"key": "redflag", "name": "Красный флаг", "price": "8 000 $", "cost": 800_000, "kind": "Отмена дуэли",
     "description": "Отменяет начисления твоей принятой дуэли в выбранной лиге. Оба участника остаются без выигрыша и штрафа за эту дуэль в этой лиге. После старта гонки использовать нельзя.",
     "rule": "Только до начала гонки · отмена для обоих участников", "scoring_phase": "before_race"},
    {"key": "mirrors", "name": "Зеркальные понтоны", "price": "7 000 $", "cost": 700_000, "kind": "Отражение",
     "description": "Отражает одну атаку «Грязный руль» обратно отправителю. Отражённую атаку нельзя отразить повторно. На исход дуэли не влияет.",
     "rule": "Одно отражение · штраф после расчёта дуэли", "scoring_phase": "after_duel"},
    {"key": "teamorder", "name": "Командный приказ", "price": "4 500 $", "cost": 450_000, "kind": "Помощь другу",
     "description": "Добавляет 2 очка другому участнику твоей лиги. Себя выбрать нельзя. Подаренные очки не участвуют в определении победителя дуэли.",
     "rule": "+2 очка другому игроку · после расчёта дуэли", "scoring_phase": "after_duel", "points": 2},
    {"key": "insurance", "name": "Страховка дуэли", "price": "3 500 $", "cost": 350_000, "kind": "Страховка",
     "description": "При поражении возвращает половину штрафа дуэли с округлением вверх до целого очка. Сначала определяется победитель и обычный штраф, затем начисляется компенсация. Поражение не превращается в ничью или победу.",
     "rule": "Возврат 50% штрафа · после расчёта дуэли", "scoring_phase": "after_duel"},
    {"key": "constructors", "name": "Кубок конструкторов", "price": "12 000 $", "cost": 1_200_000, "kind": "Командная награда",
     "description": "Ты и выбранный напарник из твоей лиги получаете по 3 очка к результату этапа. Напарником должен быть другой участник. Оба бонуса начисляются после расчёта дуэлей и не меняют их исход.",
     "rule": "+3 очка тебе и +3 напарнику · после расчёта дуэлей", "scoring_phase": "after_duel", "points": 3, "ally_points": 3},
    {"key": "paddockpass", "name": "Паддок-пасс", "price": "15 000 $", "cost": 1_500_000, "kind": "Премиальный доступ",
     "description": "Защищает от негативных предметов соперников на один этап и добавляет тебе 3 очка после расчёта дуэли. Не отменяет штраф за поражение в самой дуэли. Не складывается со «Свежим комплектом».",
     "rule": "Защита от атак и +3 очка себе · после расчёта дуэли", "scoring_phase": "after_duel", "points": 3,
     "blocks_attacks": True, "incompatible_with": ["tyres"]},
)

SCORING_NOTES = {
    "after_duel": "Эффект применяется после расчёта дуэли. Бонусы и штрафы предмета не влияют на её исход.",
    "before_race": "Применяется до старта гонки: отменяет дуэль для обоих участников. Выигрыш и штраф за отменённую дуэль не начисляются.",
}
PRODUCTS = tuple({**item, "timing": SCORING_NOTES[item["scoring_phase"]]} for item in _CATALOGUE)


@login_required
@require_GET
@never_cache
def page(request, public=False):
    if not request.user.is_active or (not public and not request.user.is_staff):
        return HttpResponseForbidden()
    # Opening the showroom never creates or changes a wallet.
    config = None
    if public:
        if request.GET.get("wallet"):
            try:
                if not 1 <= int(request.GET["wallet"]) <= 9223372036854775807:
                    raise ValueError
                wallet = get_object_or_404(VegasWallet.objects.select_related("competition__event"),
                    pk=int(request.GET["wallet"]), user=request.user)
            except (TypeError, ValueError):
                raise Http404
        else:
            from .vegas_release import account
            wallet, _, _ = account(request)
        balance = wallet.balance
        if wallet.competition_id and wallet.competition.game_key == "vegas":
            from .vegas_inventory import payload
            config = {**payload(wallet), "status_url": reverse("league:vegas_inventory")+f"?wallet={wallet.pk}",
                "buy_url": reverse("league:vegas_buy"), "apply_url": reverse("league:vegas_apply")}
    else:
        balance = VegasLabWallet.objects.filter(user=request.user).values_list("balance", flat=True).first()
    return render(request, "arcade_vegas_shop.html", {
        "products": PRODUCTS, "shop_balance": START_BALANCE if balance is None else balance,
        "shop_unlimited_balance": request.user.is_superuser and not public,
        "vegas_public": public, "arcade_test_mode": not public,
        "shop_config": config,
    })
