"""Read-only casino shop preview. Prices and effects are proposals, not purchases."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .models import VegasLabWallet
from .vegas_rules import START_BALANCE


PRODUCTS = (
    {"key": "shield", "name": "Щит паддока", "price": "2 500 $", "kind": "Защита",
     "description": "Защищает от отрицательных эффектов товаров соперников на один этап. Самому атаковать других игроков щит не мешает.",
     "rule": "На один Гран-при · один щит на игрока"},
    {"key": "amnesty", "name": "Амнистия крейзи", "price": "1 500 $", "kind": "Второй шанс",
     "description": "Снимает один этап бана на Crazy Prediction. Можно снова подать крейзи-прогноз в пределах открытого дедлайна.",
     "rule": "Один этап бана · без изменения дедлайна"},
    {"key": "wheel", "name": "Грязный руль", "price": "1 200 $", "kind": "Атака",
     "description": "Отнимает 3 очка в зачёте этапа у выбранного соперника из твоей лиги. Щит паддока блокирует атаку.",
     "rule": "−3 очка сопернику · цель выбирается отдельно"},
    {"key": "pitstop", "name": "Идеальный пит-стоп", "price": "1 800 $", "kind": "Усиление",
     "description": "Добавляет 2 очка к твоему результату на выбранном этапе. Маленькое преимущество за безупречную работу механиков.",
     "rule": "+2 очка за этап · одно применение"},
    {"key": "refund", "name": "Страховка додепа", "price": "3 000 $", "kind": "Возврат",
     "description": "Возвращает до 3 турнирных очков, потраченных на пополнение игрового баланса в этом событии. Больше потраченного вернуть нельзя.",
     "rule": "До 3 потраченных очков · пример будущей механики"},
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
