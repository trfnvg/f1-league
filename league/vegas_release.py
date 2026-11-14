"""Public access and event accounting, deliberately separate from lab funds."""
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.db import transaction
from django.utils import timezone

from .models import ArcadeCompetition, VegasWallet


@transaction.atomic
def account(request, *, writable=False):
    from .arcade_library import selected_contest, require_game_access
    settings, contest = selected_contest()
    require_game_access(request, "vegas", settings, contest)
    contest = contest if contest and contest.game_key == "vegas" else None
    if contest:
        # The same lock protects both the deadline snapshot and money changes.
        contest = ArcadeCompetition.objects.select_for_update().select_related("event").get(pk=contest.pk)
    closed = bool(contest and (not settings.public_enabled or contest.frozen_at
        or not contest.opened_at or not contest.opened_at <= timezone.now() < contest.event.deadline))
    if not request.user.is_active or (writable and closed):
        raise PermissionDenied("Зачёт закрыт: баланс зафиксирован на дедлайн.")
    if closed:
        wallet = VegasWallet.objects.filter(user=request.user, competition=contest).first()
        if wallet is None:
            raise PermissionDenied("Зачёт завершён; новое участие недоступно.")
    else:
        wallet, _ = VegasWallet.objects.get_or_create(user=request.user, competition=contest)
    return wallet, contest, closed


def standings(contest):
    wallets = VegasWallet.objects.filter(competition=contest, user__is_active=True,
        user__is_staff=False).select_related("user").annotate(attempts=Count("spins")).order_by("-balance", "user_id")
    rows = [{"user_id": w.user_id, "username": w.user.get_full_name().strip() or w.user.username,
        "score": w.balance, "balance": w.balance, "attempts": w.attempts, "rank": i}
        for i, w in enumerate(wallets, 1)]
    return rows, sum(row["attempts"] for row in rows)
