"""Daily rescue: server clock, account-wide uniqueness and atomic wallet credit."""
from datetime import datetime, time, timedelta
import json
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .models import VegasDailyGrant, VegasWallet
from .vegas_release import account
from .vegas_views import state

MOSCOW = ZoneInfo("Europe/Moscow")
AMOUNT = 200000
THRESHOLD = 10000


def daily_payload(wallet, closed=False, now=None):
    day = (now or timezone.now()).astimezone(MOSCOW).date()
    claimed = VegasDailyGrant.objects.filter(user_id=wallet.user_id, day=day).exists()
    reason = ("Зачёт завершён." if closed else "Сегодня уже получено. Обновление в 00:00 МСК." if claimed
              else "Сначала заверши бонусную серию." if wallet.free_spins
              else "Доступно при балансе ниже 100 $." if wallet.balance >= THRESHOLD else "Можно забрать без заданий.")
    return {"wallet_id": wallet.pk, "state": state(wallet), "claimed": claimed, "closed": closed,
        "can_claim": not closed and not claimed and not wallet.free_spins and wallet.balance < THRESHOLD,
        "amount": AMOUNT, "reason": reason,
        "resets_at": datetime.combine(day+timedelta(days=1), time.min, MOSCOW).isoformat()}


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
@transaction.atomic
def daily_view(request):
    try:
        if request.method == "POST":
            if len(request.body) > 256:
                raise ValidationError("Слишком большой запрос.")
            data = json.loads(request.body)
            if (not isinstance(data, dict) or set(data) != {"wallet_id"}
                    or type(data["wallet_id"]) is not int):
                raise ValidationError("Некорректный запрос.")
            # Serialize even attempts from two different event/practice wallets.
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
        wallet, _, closed = account(request, writable=request.method == "POST")
        if request.method == "POST":
            if data["wallet_id"] != wallet.pk:
                raise ValidationError("Обнови страницу: выбран другой игровой кошелёк.")
            wallet = VegasWallet.objects.select_for_update().get(pk=wallet.pk)
            now = timezone.now()
            status = daily_payload(wallet, closed, now)
            if status["claimed"]:
                return JsonResponse(status)  # Lost response/repeated click is harmless.
            if not status["can_claim"]:
                raise ValidationError(status["reason"])
            day = now.astimezone(MOSCOW).date()
            VegasDailyGrant.objects.create(user=request.user, wallet=wallet, day=day, amount=AMOUNT)
            wallet.balance += AMOUNT
            wallet.revision += 1
            if wallet.last_payload:
                wallet.last_payload = {**wallet.last_payload, "state": state(wallet)}
            wallet.save(update_fields=["balance", "revision", "last_payload"])
        return JsonResponse(daily_payload(wallet, closed))
    except PermissionDenied as error:
        return JsonResponse({"error": str(error)}, status=403)
    except (ValidationError, ValueError, TypeError, UnicodeDecodeError, RecursionError) as error:
        return JsonResponse({"error": " ".join(error.messages) if isinstance(error, ValidationError) else "Некорректный запрос."}, status=400)
