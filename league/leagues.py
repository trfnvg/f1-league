"""Private-league foundation. Not wired into legacy scores or public HTTP yet.

All mutations lock the league first, verify the actor's live membership, and
choose eligibility on the server. UUIDs select a league, not authorize access.
"""
import hashlib
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from .models import (
    Event, League, LeagueActivity, LeagueInvite, LeagueMembership, LeagueSeason, LeagueSeasonEntry, Prediction,
    Score, Season, SeasonPrediction, SeasonScore,
)


def _require_user(user):
    if not getattr(user, "is_authenticated", False) or not user.pk or not user.is_active:
        raise PermissionDenied("Нужен активный аккаунт.")


def membership_for(user, league):
    _require_user(user)
    membership = LeagueMembership.objects.select_related("league").filter(league_id=league.pk, user=user, is_active=True).first()
    if membership is None:
        raise PermissionDenied("Вы не участник этой лиги.")
    if membership.league.archived_at:
        raise PermissionDenied("Лига находится в архиве.")
    return membership


def require_moderator(user, league):
    membership = membership_for(user, league)
    if membership.league.owner_id != user.pk and membership.role != LeagueMembership.Role.MODERATOR:
        raise PermissionDenied("Нужны права модератора этой лиги.")
    return membership


def require_crazy_judge(user, league_season):
    league_season = LeagueSeason.objects.select_related("league").get(pk=league_season.pk)
    membership = require_moderator(user, league_season.league)
    if league_season.ruleset != LeagueSeason.Ruleset.PADDOCK:
        raise PermissionDenied("В классическом зачёте нет крейзи-предиктов.")
    return membership


def _next_event(league_season, now):
    event = Event.objects.filter(
        season_year=league_season.season.year,
        round_number__gte=league_season.start_event.round_number,
        deadline__gt=now, status=Event.Status.OPEN,
    ).order_by("round_number", "pk").first()
    if event is None:
        raise ValidationError("В этом зачёте нет доступных будущих этапов.")
    return event


def _enroll(league_season, user, now):
    _require_user(user)
    membership, _ = LeagueMembership.objects.get_or_create(
        league=league_season.league, user=user, defaults={"joined_at": now},
    )
    if not membership.is_active:
        raise PermissionDenied("Членство отключено. Вступление не восстанавливает права автоматически.")
    existing = LeagueSeasonEntry.objects.filter(league_season=league_season, membership=membership).first()
    if existing:
        return existing
    entry = LeagueSeasonEntry(
        league_season=league_season, membership=membership,
        first_event=_next_event(league_season, now), entered_at=now,
    )
    entry.full_clean()
    entry.save()
    return entry


@transaction.atomic
def create_league(*, owner, name, season, start_event, ruleset=LeagueSeason.Ruleset.CLASSIC):
    _require_user(owner)
    if not isinstance(name, str):
        raise ValidationError("Укажите название лиги.")
    now = timezone.now()
    start_event = Event.objects.select_for_update().get(pk=start_event.pk)
    # Serialize per-account quotas even if concurrent requests pick other GPs.
    User.objects.select_for_update().get(pk=owner.pk)
    if League.objects.filter(owner=owner, archived_at__isnull=True).count() >= getattr(settings, "PRIVATE_LEAGUE_MAX_OWNED", 10):
        raise ValidationError("Достигнут лимит активных лиг аккаунта.")
    if League.objects.filter(owner=owner, created_at__gte=now-timedelta(minutes=10)).count() >= 3:
        raise ValidationError("Слишком много новых лиг. Попробуйте через 10 минут.")
    if start_event.deadline <= now or start_event.status != Event.Status.OPEN:
        raise ValidationError("Выберите этап с открытым дедлайном.")
    league = League(name=name.strip(), owner=owner, created_at=now)
    league.full_clean()
    league.save()
    league_season = LeagueSeason(league=league, season=season, start_event=start_event, ruleset=ruleset, created_at=now)
    league_season.full_clean()
    league_season.save()
    _enroll(league_season, owner, now)
    LeagueActivity.objects.create(league=league, actor=owner, action="created", details={"season": season.year, "ruleset": ruleset})
    return league_season


@transaction.atomic
def enroll_member(*, actor, league_season, user):
    # This is moderator enrollment, NOT a public join-by-UUID endpoint.
    league_season = LeagueSeason.objects.select_related("league", "season", "start_event").get(pk=league_season.pk)
    league = League.objects.select_for_update().get(pk=league_season.league_id)
    require_moderator(actor, league)
    return _enroll(league_season, user, timezone.now())


@transaction.atomic
def set_member_role(*, actor, membership, role):
    membership = LeagueMembership.objects.select_related("league").get(pk=membership.pk)
    league = League.objects.select_for_update().get(pk=membership.league_id)
    membership_for(actor, league)
    if actor.pk != league.owner_id:
        raise PermissionDenied("Назначать модераторов может только владелец лиги.")
    if not membership.is_active:
        raise ValidationError("Нельзя менять роль отключённого участника.")
    membership.role = role
    membership.full_clean()
    previous = LeagueMembership.objects.get(pk=membership.pk).role
    if previous == role:
        return membership
    membership.save(update_fields=("role",))
    LeagueActivity.objects.create(league=league, actor=actor, action="role_changed",
        details={"user_id": membership.user_id, "before": previous, "after": role})
    return membership


def legacy_member_ids(season_year, owner):
    """Existing players with actual historical data, not every registered user."""
    return set(User.objects.filter(is_staff=False).filter(
        Q(pk__in=Prediction.objects.filter(event__season_year=season_year).values("user_id"))
        | Q(pk__in=Score.objects.filter(event__season_year=season_year).values("user_id"))
        | Q(pk__in=SeasonPrediction.objects.filter(season_year=season_year).values("user_id"))
        | Q(pk__in=SeasonScore.objects.filter(season_year=season_year).values("user_id"))
    ).values_list("pk", flat=True)) | {owner.pk}


@transaction.atomic
def import_legacy_league(*, owner, season_year, name="Наша лига"):
    """Explicit operator-only import, once per season; never called by HTTP.

    Existing Prediction/Score/duel/arcade rows are NOT edited. A later scoring
    migration will preserve their local adjustments, not make them global.
    """
    _require_user(owner)
    season = Season.objects.get(year=season_year)
    first_event = Event.objects.filter(season_year=season_year).order_by("round_number", "pk").first()
    if first_event is None:
        raise ValidationError("В сезоне нет этапов.")
    league, _ = League.objects.get_or_create(
        legacy_key="original-friends", defaults={"owner": owner, "name": name.strip()},
    )
    league = League.objects.select_for_update().get(pk=league.pk)
    if league.owner_id != owner.pk:
        raise ValidationError("У перенесённой лиги уже другой владелец.")
    existing = LeagueSeason.objects.filter(league=league, season=season).first()
    if existing:
        return existing, False
    league.full_clean()
    league_season = LeagueSeason(
        league=league, season=season, start_event=first_event,
        ruleset=LeagueSeason.Ruleset.PADDOCK, is_legacy=True,
    )
    league_season.full_clean()
    league_season.save()
    now = timezone.now()
    for user in User.objects.filter(pk__in=legacy_member_ids(season_year, owner)).order_by("pk"):
        membership, _ = LeagueMembership.objects.get_or_create(league=league, user=user, defaults={"joined_at": now})
        entry = LeagueSeasonEntry(league_season=league_season, membership=membership, first_event=first_event, entered_at=now)
        entry.full_clean()
        entry.save()
    return league_season, True


def _invite_digest(token):
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise ValidationError("Приглашение недоступно или срок его действия истёк.")
    return hashlib.sha256(token.encode()).hexdigest()


def invite_for_token(token):
    invite = LeagueInvite.objects.select_related("league_season__league", "league_season__season", "league_season__start_event").filter(token_digest=_invite_digest(token)).first()
    if (invite is None or invite.revoked_at or invite.expires_at <= timezone.now()
            or invite.league_season.league.archived_at or invite.league_season.is_legacy):
        raise ValidationError("Приглашение недоступно или срок его действия истёк.")
    return invite


@transaction.atomic
def create_invite(*, actor, league_season):
    league_season = LeagueSeason.objects.select_related("league").get(pk=league_season.pk)
    league = League.objects.select_for_update().get(pk=league_season.league_id)
    require_moderator(actor, league)
    if league_season.is_legacy:
        raise ValidationError("Сначала нужно завершить перенос исторической лиги.")
    now = timezone.now()
    _next_event(league_season, now)
    if league_season.invites.filter(revoked_at__isnull=True, expires_at__gt=now).count() >= 5:
        raise ValidationError("Уже есть пять действующих приглашений. Отзовите ненужное.")
    token = secrets.token_urlsafe(32)
    invite = LeagueInvite.objects.create(league_season=league_season, token_digest=_invite_digest(token),
        created_by=actor, expires_at=now+timedelta(days=7))
    LeagueActivity.objects.create(league=league, actor=actor, action="invite_created", details={"invite_id": invite.pk})
    return invite, token


@transaction.atomic
def revoke_invite(*, actor, invite):
    invite = LeagueInvite.objects.select_related("league_season__league").get(pk=invite.pk)
    league = League.objects.select_for_update().get(pk=invite.league_season.league_id)
    require_moderator(actor, league)
    invite = LeagueInvite.objects.select_for_update().get(pk=invite.pk)
    if not invite.revoked_at:
        invite.revoked_at = timezone.now();invite.save(update_fields=("revoked_at",))
        LeagueActivity.objects.create(league=league, actor=actor, action="invite_revoked", details={"invite_id": invite.pk})


@transaction.atomic
def accept_invite(*, user, token):
    _require_user(user)
    invite = invite_for_token(token)
    league = League.objects.select_for_update().get(pk=invite.league_season.league_id)
    # Recheck expiry/revocation after waiting for a concurrent revoke/join.
    invite = invite_for_token(token)
    membership = LeagueMembership.objects.filter(league=league, user=user).first()
    if membership and not membership.is_active:
        raise PermissionDenied("Доступ к этой лиге отключён.")
    if membership:
        existing = LeagueSeasonEntry.objects.filter(league_season=invite.league_season, membership=membership).first()
        if existing:
            return existing
    if not membership and league.memberships.filter(is_active=True).count() >= getattr(settings, "PRIVATE_LEAGUE_MAX_MEMBERS", 250):
        raise ValidationError("В лиге достигнут лимит участников.")
    entry = _enroll(invite.league_season, user, timezone.now())
    LeagueInvite.objects.filter(pk=invite.pk).update(uses=F("uses")+1)
    LeagueActivity.objects.create(league=league, actor=user, action="joined", details={"season": invite.league_season.season.year})
    return entry
