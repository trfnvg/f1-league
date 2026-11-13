"""Server-authorized, league-reviewed play-money topups. No score mutations."""
import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .league_management import require_owner
from .models import (League, LeagueActivity, LeagueSeasonEntry, RaceCalendarRound,
                     VegasLabWallet, VegasTopupClaim)

REWARD = 300_000
THRESHOLD = 100_000
OPEN = (VegasTopupClaim.Status.ACTIVE, VegasTopupClaim.Status.REVIEW)


def reward_display():
    return f"{REWARD // 100:,}".replace(",", " ")


def current_round(now):
    # Keep the same round through its race, rather than immediately offering
    # the following round's tasks when FP1 has already started.
    return RaceCalendarRound.objects.select_related("prediction_event").filter(
        prediction_event__isnull=False, race_at__gt=now-timedelta(hours=2),
    ).order_by("race_at", "pk").first()


def deadline(claim):
    times = list(RaceCalendarRound.objects.filter(prediction_event_id=claim.event_id,
        practice1_at__isnull=False).values_list("practice1_at", flat=True))
    return min(claim.expires_at, min(times)) if times else None


def expired(claim, now):
    cutoff = deadline(claim)
    return cutoff is None or now >= cutoff


def eligible_entries(user, calendar):
    if not calendar or not calendar.prediction_event_id:
        return LeagueSeasonEntry.objects.none()
    event = calendar.prediction_event
    return LeagueSeasonEntry.objects.filter(membership__user=user,
        membership__is_active=True, membership__user__is_active=True, membership__league__archived_at__isnull=True,
        league_season__league_id=F("membership__league_id"),
        league_season__season__year=event.season_year,
        first_event__round_number__lte=event.round_number,
        league_season__start_event__round_number__lte=event.round_number,
    ).select_related("league_season__league").order_by("league_season__league__name", "pk")


def serialize(claim, now):
    status = "expired" if claim.status in OPEN and expired(claim, now) else claim.status
    return {"id": claim.pk, "task": claim.task, "text": claim.get_task_display(),
            "status": status, "label": dict(VegasTopupClaim.Status.choices)[status],
            "league": claim.league_season.league.name, "event": claim.event.name,
            "expires_at": claim.expires_at.isoformat(), "note": claim.note}


def payload(user):
    from .vegas_views import state
    wallet = VegasLabWallet.objects.filter(user=user).first()
    now = timezone.now()
    calendar = current_round(now)
    claims = list(VegasTopupClaim.objects.filter(user=user).select_related("league_season__league", "event").order_by("-activated_at", "-pk"))
    active = next((c for c in claims if c.status in OPEN and not expired(c, now)), None)
    event_claims = {c.task: c for c in claims if calendar and c.event_id == calendar.prediction_event_id}
    leagues = [{"id": str(e.league_season.league_id), "name": e.league_season.league.name}
               for e in eligible_entries(user, calendar)]
    reason = ("У администратора уже неограниченный тестовый баланс." if user.is_superuser else
              "Сначала заверши активное задание или дождись проверки." if active else
              "Додеп доступен только при балансе меньше 1 000." if not wallet or wallet.balance >= THRESHOLD else
              "Сначала заверши бесплатные вращения." if wallet.free_spins else
              "Для ближайшего этапа ещё нет времени первой практики." if not calendar or not calendar.practice1_at else
              "Первая практика уже началась. Задания закрыты." if now >= calendar.practice1_at else
              "Для этого этапа нужно состоять в лиге." if not leagues else "")
    tasks = []
    for key, text in VegasTopupClaim.Task.choices:
        previous = event_claims.get(key)
        tasks.append({"key": key, "text": text, "available": not previous or previous.status == "cancelled",
                      "status": serialize(previous, now)["label"] if previous else ""})
    if not reason and not any(task["available"] for task in tasks):
        reason = "Оба задания для этого этапа уже использованы."
    return {"state": state(wallet) if wallet else None, "topup": {
        "reward": REWARD, "threshold": THRESHOLD, "can_activate": not reason,
        "reason": reason, "active": serialize(active, now) if active else None,
        "event": {"id": calendar.prediction_event_id, "name": calendar.prediction_event.name,
                  "deadline": calendar.practice1_at.isoformat() if calendar.practice1_at else None} if calendar else None,
        "leagues": leagues, "tasks": tasks,
        "history": [serialize(c, now) for c in claims[:6]],
    }}


def require_player(user):
    # The slot remains a staff-only lab; this does not publish the game.
    if not user.is_active or not user.is_staff:
        raise PermissionDenied


def management_claims(season, event, now, page_number):
    claims = VegasTopupClaim.objects.filter(league_season=season, event=event).select_related("user", "reviewed_by").order_by("status", "-activated_at", "-pk")
    page = Paginator(claims, 50).get_page(page_number)
    live_deadline = RaceCalendarRound.objects.filter(prediction_event=event,
        practice1_at__isnull=False).order_by("practice1_at").values_list("practice1_at", flat=True).first()
    for claim in page:
        claim.is_expired = claim.status in OPEN and (not live_deadline or now >= min(claim.expires_at, live_deadline))
        claim.can_review = claim.status == VegasTopupClaim.Status.REVIEW and not claim.is_expired
    return page


def locked_wallet(user):
    wallet = get_object_or_404(VegasLabWallet.objects.select_for_update(), user=user)
    for claim in VegasTopupClaim.objects.select_for_update().filter(user=user, status__in=OPEN):
        if expired(claim, timezone.now()):
            claim.status = VegasTopupClaim.Status.EXPIRED
            claim.save(update_fields=["status"])
    return wallet


@transaction.atomic
def activate(*, user, league_id, event_id, task):
    require_player(user)
    wallet = locked_wallet(user)
    now = timezone.now()
    calendar = current_round(now)
    if user.is_superuser:
        raise ValidationError("У администратора уже неограниченный баланс.")
    if not calendar or not calendar.practice1_at or now >= calendar.practice1_at:
        raise ValidationError("Активация доступна только до первой практики ближайшего этапа.")
    if type(event_id) is not int or event_id != calendar.prediction_event_id or task not in VegasTopupClaim.Task.values:
        raise ValidationError("Выбери задание для текущего этапа.")
    entry = eligible_entries(user, calendar).filter(league_season__league_id=league_id).first()
    if not entry:
        raise PermissionDenied("Нет участия в этом этапе лиги.")
    claim = VegasTopupClaim.objects.filter(user=user, event_id=event_id, task=task).first()
    if claim and claim.status in OPEN:
        return claim  # Lost activation response: never create a second claim.
    if claim and claim.status != VegasTopupClaim.Status.CANCELLED:
        raise ValidationError("Это задание уже использовано на этапе.")
    if wallet.balance >= THRESHOLD or wallet.free_spins:
        raise ValidationError("Нужен баланс меньше 1 000 и завершённая бонусная серия.")
    if VegasTopupClaim.objects.filter(user=user, status__in=OPEN).exists():
        raise ValidationError("Одновременно можно активировать только одно задание.")
    values = dict(league_season=entry.league_season, status=VegasTopupClaim.Status.ACTIVE,
                  expires_at=calendar.practice1_at, activated_at=now)
    if claim:
        for key, value in values.items():
            setattr(claim, key, value)
        claim.save(update_fields=list(values))
    else:
        claim = VegasTopupClaim.objects.create(user=user, event_id=event_id, task=task, **values)
    return claim


@transaction.atomic
def submit(*, user, claim_id, note="", cancel=False):
    require_player(user)
    locked_wallet(user)
    claim = get_object_or_404(VegasTopupClaim.objects.select_for_update(), pk=claim_id, user=user)
    if claim.status == VegasTopupClaim.Status.REVIEW and not cancel:
        return claim
    if claim.status != VegasTopupClaim.Status.ACTIVE or expired(claim, timezone.now()):
        raise ValidationError("Задание уже закрыто.")
    if not isinstance(note, str) or len(note) > 300:
        raise ValidationError("Комментарий — не больше 300 символов.")
    claim.status = VegasTopupClaim.Status.CANCELLED if cancel else VegasTopupClaim.Status.REVIEW
    claim.note = note.strip()
    claim.submitted_at = None if cancel else timezone.now()
    claim.save(update_fields=["status", "note", "submitted_at"])
    return claim


@transaction.atomic
def review(*, actor, league_id, event_id, claim_id, approved):
    from .vegas_views import state
    # Same lock order as spins and activation: wallet, then claim.
    selected = get_object_or_404(VegasTopupClaim, pk=claim_id,
        league_season__league_id=league_id, event_id=event_id)
    wallet = VegasLabWallet.objects.select_for_update().get(user_id=selected.user_id)
    claim = VegasTopupClaim.objects.select_for_update().select_related("league_season__league").get(pk=selected.pk)
    league = get_object_or_404(League.objects.select_for_update(), pk=league_id, archived_at__isnull=True)
    require_owner(actor, league)
    if actor.pk == claim.user_id:
        raise PermissionDenied("Нельзя засчитать собственное задание.")
    if type(approved) is not bool:
        raise ValidationError("Выберите решение.")
    target = VegasTopupClaim.Status.APPROVED if approved else VegasTopupClaim.Status.REJECTED
    if claim.status == target:
        return claim  # Repeated approval is a no-op, including after FP1.
    if claim.status != VegasTopupClaim.Status.REVIEW or expired(claim, timezone.now()):
        raise ValidationError("Засчитать можно только отправленное задание до первой практики.")
    if not LeagueSeasonEntry.objects.filter(league_season=claim.league_season,
            membership__user_id=claim.user_id, membership__is_active=True, membership__user__is_active=True,
            membership__league=league, first_event__round_number__lte=claim.event.round_number).exists():
        raise ValidationError("Игрок больше не участвует в этом этапе лиги.")
    now = timezone.now()
    before = wallet.balance
    if approved:
        wallet.balance += REWARD
        wallet.revision += 1
        if wallet.last_payload:
            wallet.last_payload = {**wallet.last_payload, "state": state(wallet)}
        wallet.save(update_fields=["balance", "revision", "last_payload"])
        claim.credited_at = now
    claim.status, claim.reviewed_at, claim.reviewed_by = target, now, actor
    claim.save(update_fields=["status", "reviewed_at", "reviewed_by", "credited_at"])
    LeagueActivity.objects.create(league=league, actor=actor, action="vegas_topup_reviewed",
        details={"claim_id": claim.pk, "event_id": event_id, "user_id": claim.user_id,
                 "approved": approved, "amount": REWARD if approved else 0,
                 "balance_before": before, "balance_after": wallet.balance})
    return claim


def read_json(request, allowed):
    try:
        if len(request.body) > 2048:
            raise ValueError
        data = json.loads(request.body)
        if not isinstance(data, dict) or set(data)-set(allowed):
            raise ValueError
        return data
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise ValidationError("Некорректный запрос.")


@login_required
@never_cache
@require_GET
def status_view(request):
    require_player(request.user)
    return JsonResponse(payload(request.user))


@login_required
@never_cache
@require_POST
def action_view(request, action, claim_id=None):
    require_player(request.user)
    try:
        if action == "activate":
            data = read_json(request, ("league_id", "event_id", "task"))
            try:
                import uuid
                league_id = uuid.UUID(str(data.get("league_id", "")))
            except ValueError:
                raise ValidationError("Выбери лигу.")
            activate(user=request.user, league_id=league_id, event_id=data.get("event_id"), task=data.get("task"))
        else:
            data = read_json(request, ("note",))
            submit(user=request.user, claim_id=claim_id, note=data.get("note", ""), cancel=action == "cancel")
    except ValidationError as exc:
        return JsonResponse({"error": " ".join(exc.messages)}, status=400)
    return JsonResponse(payload(request.user))


@login_required
@never_cache
@require_POST
def review_view(request, league_id, event_id, claim_id):
    league = get_object_or_404(League, pk=league_id, archived_at__isnull=True)
    require_owner(request.user, league)
    try:
        decision = request.POST.get("decision")
        if decision not in ("approve", "reject"):
            raise ValidationError("Выберите решение по заданию.")
        review(actor=request.user, league_id=league_id, event_id=event_id,
               claim_id=claim_id, approved=decision == "approve")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, f"Задание засчитано · +{reward_display()} на игровой баланс." if decision == "approve" else "Задание не засчитано.")
    return redirect(reverse("league:friend_league_event", args=[league_id, event_id])+"?manage=1#vegas-topup-management")
