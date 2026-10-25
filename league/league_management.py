"""League-local management. No shared forecasts/results or staff flags change."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .leagues import membership_for, require_crazy_judge, require_moderator
from .models import (DRIVER_CHOICES, Event, League, LeagueActivity, LeagueCrazyDecision,
    LeagueDayDecision, LeagueInvite, LeagueMembership, LeagueSeason, LeagueSeasonEntry, Prediction)
from .competition_scoring import _project_league, _text_digest, judge_crazy_prediction
from .prediction_rules import RULES_VERSION


def require_manager(actor, league):
    member = membership_for(actor, league)
    if league.owner_id != actor.pk and member.role != LeagueMembership.Role.MANAGER:
        raise PermissionDenied("Нужны права управляющего этой лиги.")
    return member


@transaction.atomic
def delete_league(*, actor, league, confirmation):
    league = League.objects.select_for_update().get(pk=league.pk)
    if not getattr(actor, "is_authenticated", False) or not getattr(actor, "is_active", False) or not actor.pk:
        raise PermissionDenied("Удалить лигу может только её создатель.")
    member = LeagueMembership.objects.filter(league=league, user_id=actor.pk, is_active=True).first()
    if not member or league.owner_id != actor.pk:
        raise PermissionDenied("Удалить лигу может только её создатель.")
    if not isinstance(confirmation, str) or confirmation.strip() != league.name:
        raise ValidationError("Введите точное название лиги для подтверждения.")
    if league.archived_at:
        return league
    league.archived_at = timezone.now()
    league.save(update_fields=("archived_at",))
    LeagueInvite.objects.filter(league_season__league=league, revoked_at__isnull=True).update(revoked_at=league.archived_at)
    LeagueActivity.objects.create(league=league, actor=actor, action="archived", details={"name": league.name})
    return league


@transaction.atomic
def update_profile(*, actor, league, name, avatar=None):
    league = League.objects.select_for_update().get(pk=league.pk)
    require_manager(actor, league)
    before = {"name": league.name, "avatar": league.avatar.name}
    league.name = name.strip()
    if avatar is not None:
        league.avatar = avatar or ""
    league.full_clean();league.save(update_fields=("name", "avatar"))
    after = {"name": league.name, "avatar": league.avatar.name}
    if before != after:
        LeagueActivity.objects.create(league=league, actor=actor, action="profile_changed", details={"before": before, "after": after})
    return league


def moderation_scope(actor, season, event):
    event = Event.objects.select_for_update().get(pk=event.pk)
    season = LeagueSeason.objects.select_related("season", "start_event").get(pk=season.pk)
    season.league = League.objects.select_for_update().get(pk=season.league_id)
    require_moderator(actor, season.league)
    if season.rules_version != RULES_VERSION:
        raise ValidationError("Неизвестная версия правил лиги.")
    if event.season_year != season.season.year or event.round_number < season.start_event.round_number:
        raise ValidationError("Этап не входит в эту лигу.")
    return season, event


@transaction.atomic
def decide_day(*, actor, season, event, drivers=None):
    season, event = moderation_scope(actor, season, event)
    if timezone.now() < (event.race_datetime or event.deadline):
        raise ValidationError("Гонщика дня можно засчитать после старта гонки.")
    if drivers is not None and (not isinstance(drivers, list) or any(not isinstance(d, str) or d not in dict(DRIVER_CHOICES) for d in drivers)):
        raise ValidationError("Выберите гонщиков из списка.")
    drivers = sorted(set(drivers)) if drivers is not None else None
    previous = LeagueDayDecision.objects.filter(league_season=season, event=event).first()
    before = previous.drivers if previous else None
    if before == drivers:
        return previous
    if drivers is None:
        previous.delete()
    else:
        LeagueDayDecision.objects.update_or_create(league_season=season, event=event,
            defaults={"drivers": drivers, "reviewed_by": actor, "reviewed_at": timezone.now()})
    LeagueActivity.objects.create(league=season.league, actor=actor, action="day_decided",
        details={"event_id": event.pk, "before": before, "after": drivers})
    if not season.is_legacy and event.status == Event.Status.SCORED:
        _project_league(actor, season, event)


@transaction.atomic
def decide_crazy(*, actor, season, entry, event, approved):
    season = LeagueSeason.objects.get(pk=season.pk)
    if not season.is_legacy:
        return judge_crazy_prediction(actor=actor, league_season=season, entry=entry, event=event, approved=approved)
    season, event = moderation_scope(actor, season, event)
    require_crazy_judge(actor, season)
    entry = LeagueSeasonEntry.objects.select_related("membership", "first_event").get(pk=entry.pk)
    if (entry.league_season_id != season.pk or entry.membership.league_id != season.league_id
            or entry.first_event.round_number > event.round_number):
        raise PermissionDenied("Игрок не участвует в этом этапе лиги.")
    if type(approved) is not bool or timezone.now() < event.deadline:
        raise ValidationError("Крейзи оценивается после дедлайна явным решением.")
    prediction = Prediction.objects.filter(user_id=entry.membership.user_id, event=event,
        created_at__lt=event.deadline).first()
    if not prediction or not prediction.crazy_prediction.strip():
        raise ValidationError("Нет своевременно сохранённого крейзи-предикта.")
    digest = _text_digest(prediction)
    previous = LeagueCrazyDecision.objects.filter(entry=entry, event=event).first()
    if previous and previous.approved == approved and previous.text_digest == digest:
        return previous
    before = {"approved": previous.approved, "text_digest": previous.text_digest} if previous else None
    decision, _ = LeagueCrazyDecision.objects.update_or_create(entry=entry, event=event,
        defaults={"prediction": prediction, "approved": approved, "text_digest": digest,
                  "reviewed_by": actor, "reviewed_at": timezone.now()})
    LeagueActivity.objects.create(league=season.league, actor=actor, action="crazy_decided",
        details={"event_id": event.pk, "entry_id": entry.pk, "before": before,
                 "after": {"approved": approved, "text_digest": digest}})
    return decision
