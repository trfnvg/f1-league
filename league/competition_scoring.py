"""Isolated score projections. No legacy score/wheel/duel writes or HTTP routes.

Lock order for mutations: Event -> League -> local reward/input. Public scores
are platform-managed; private scores and judging require that league's role.
"""
import hashlib
import json
import logging
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .leagues import membership_for, require_crazy_judge, require_moderator
from .models import (
    DRIVER_CHOICES, ArcadeWheelSpin, CompetitionScoreAudit, Event, GlobalEventScore,
    League, LeagueCrazyDecision, LeagueDayDecision, LeagueEventScore, LeaguePodiumBonus,
    LeagueScoreAdjustment, LeagueSeason, LeagueSeasonEntry, Prediction, Result,
)
from .prediction_rules import PREDICTION_FIELDS, RESULT_FIELDS, RULES_VERSION, calculate_base_points

logger = logging.getLogger(__name__)


def _digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _text_digest(prediction):
    return _digest(prediction.crazy_prediction.strip())


def _require_platform_operator(actor):
    if not getattr(actor, "is_authenticated", False) or not User.objects.filter(pk=actor.pk, is_active=True, is_staff=True).exists():
        raise PermissionDenied("Публиковать общий зачёт может только администратор платформы.")


def _scope(league_season, event, *, actor, lock=False, moderator=False):
    event = (Event.objects.select_for_update() if lock else Event.objects).get(pk=event.pk)
    league_season = LeagueSeason.objects.select_related("league", "season", "start_event").get(pk=league_season.pk)
    if lock:
        league_season.league = League.objects.select_for_update().get(pk=league_season.league_id)
    if moderator:
        require_moderator(actor, league_season.league)
    else:
        membership_for(actor, league_season.league)
    if league_season.is_legacy:
        raise ValidationError("Исторический зачёт требует отдельного переноса местных бонусов и сверки очков.")
    if league_season.rules_version != RULES_VERSION:
        raise ValidationError("Неизвестная версия правил лиги.")
    if (league_season.start_event.season_year != league_season.season.year
            or event.season_year != league_season.season.year
            or event.round_number < league_season.start_event.round_number):
        raise ValidationError("Этап не входит в этот сезон лиги.")
    return league_season, event


def _published_result(event):
    now = timezone.now()
    if event.deadline > now or event.status != Event.Status.SCORED:
        raise ValidationError("Дождитесь дедлайна и публикации официальных результатов этапа.")
    result = Result.objects.filter(event=event, published_at__isnull=False, published_at__lte=now).first()
    if result is None:
        raise ValidationError("Официальный результат этапа ещё не опубликован.")
    # Legacy podium rewards edited Prediction in-place. Never guess/relabel
    # those answers as an untouched public forecast or leak them to new leagues.
    if ArcadeWheelSpin.objects.filter(event=event, prize=ArcadeWheelSpin.Prize.PODIUM_EDIT, activated_at__isnull=False).exists():
        raise ValidationError("В этом этапе старый апдейт подиума изменил базовый прогноз. Сначала нужен проверенный перенос.")
    result.event = event
    return result


def _entries(league_season, event):
    entries = list(LeagueSeasonEntry.objects.filter(league_season=league_season).select_related("membership", "first_event"))
    eligible = []
    for entry in entries:
        if (entry.membership.league_id != league_season.league_id
                or entry.first_event.season_year != event.season_year
                or entry.first_event.round_number < league_season.start_event.round_number
                or entry.entered_at >= entry.first_event.deadline):
            raise ValidationError("Повреждены границы участия в лиге. Нужна проверка состава.")
        if entry.first_event.round_number <= event.round_number:
            # Disabling access must not erase results from previous events.
            eligible.append(entry)
    return eligible


def _entry_for(league_season, event, entry_id):
    entry = next((entry for entry in _entries(league_season, event) if entry.pk == entry_id), None)
    if entry is None:
        raise PermissionDenied("Игрок не участвует в этом этапе этой лиги.")
    entry.league_season = league_season
    return entry


def _predictions(event, user_ids=None):
    query = Prediction.objects.filter(event=event, created_at__lt=event.deadline)
    if user_ids is not None:
        query = query.filter(user_id__in=user_ids)
    return {prediction.user_id: prediction for prediction in query.order_by("user_id")}


def _base_input(prediction, result):
    return {
        "version": RULES_VERSION, "event_id": result.event_id, "sprint": result.event.has_sprint,
        "prediction_id": prediction.pk, "submitted_at": prediction.created_at.isoformat(),
        "prediction": {field: getattr(prediction, field) for field in PREDICTION_FIELDS},
        "result": {field: getattr(result, field) for field in RESULT_FIELDS},
    }


def _global_rows(event, result):
    rows = []
    for prediction in _predictions(event).values():
        points, breakdown = calculate_base_points(prediction, result)
        data = _base_input(prediction, result)
        rows.append(dict(user_id=prediction.user_id, prediction_id=prediction.pk,
                         points=points, breakdown=breakdown, rules_version=RULES_VERSION,
                         input_data=data, input_digest=_digest(data)))
    return rows


def _valid_podium(bonus, prediction, event):
    if (bonus.slot not in ("p1", "p2", "p3") or bonus.driver not in dict(DRIVER_CHOICES)
            or not bonus.source_key.strip() or event.race_datetime is None
            or not bonus.granted_at <= bonus.used_at < event.race_datetime
            or bonus.driver in {getattr(prediction, slot) for slot in ("p1", "p2", "p3") if slot != bonus.slot}):
        raise ValidationError("Некорректный местный апдейт подиума.")


def _league_rows(league_season, event, result):
    entries = _entries(league_season, event)
    predictions = _predictions(event, [entry.membership.user_id for entry in entries])
    entry_ids = [entry.pk for entry in entries]
    decisions, bonuses, adjustments = {}, {}, {}
    day = LeagueDayDecision.objects.filter(league_season=league_season, event=event).first()
    if league_season.ruleset == LeagueSeason.Ruleset.PADDOCK:
        decisions = {row.entry_id: row for row in LeagueCrazyDecision.objects.filter(event=event, entry_id__in=entry_ids)}
        bonuses = {row.entry_id: row for row in LeaguePodiumBonus.objects.filter(event=event, entry_id__in=entry_ids, used_at__isnull=False)}
        for adjustment in LeagueScoreAdjustment.objects.filter(event=event, entry_id__in=entry_ids).order_by("kind", "source_key", "pk"):
            adjustments.setdefault(adjustment.entry_id, []).append(adjustment)
    rows = []
    for entry in entries:
        prediction = predictions.get(entry.membership.user_id)
        if prediction is None:
            continue
        base_points, base_breakdown = calculate_base_points(prediction, result)
        data = _base_input(prediction, result)
        data.update(entry_id=entry.pk, league_season_id=league_season.pk, ruleset=league_season.ruleset)
        local = {"crazy": None, "podium": None, "adjustments": []}
        podium_adjustment, crazy_points = 0, 0
        bonus = bonuses.get(entry.pk)
        if bonus:
            _valid_podium(bonus, prediction, event)
            local_prediction = SimpleNamespace(**data["prediction"])
            setattr(local_prediction, bonus.slot, bonus.driver)
            local_points, _ = calculate_base_points(local_prediction, result)
            podium_adjustment = local_points-base_points
            local["podium"] = dict(slot=bonus.slot, driver=bonus.driver, source_key=bonus.source_key, used_at=bonus.used_at.isoformat())
        decision = decisions.get(entry.pk)
        if decision:
            if decision.prediction_id != prediction.pk or decision.text_digest != _text_digest(prediction):
                raise ValidationError("Крейзи-предикт изменён после решения. Модератор должен проверить его заново.")
            crazy_points = 5 if decision.approved and prediction.crazy_prediction.strip() else 0
            local["crazy"] = dict(approved=decision.approved, text_digest=decision.text_digest, reviewed_by=decision.reviewed_by_id)
        for adjustment in adjustments.get(entry.pk, []):
            local["adjustments"].append(dict(kind=adjustment.kind, source_key=adjustment.source_key,
                                             points=adjustment.points, reason=adjustment.reason))
        other_adjustment = sum(item["points"] for item in local["adjustments"])
        if day:
            day_delta = (3 if (prediction.driver_of_day or "").strip().lower() in day.drivers else 0)-base_breakdown.get("Driver of the Day", 0)
            other_adjustment += day_delta
            local["driver_of_day"] = dict(drivers=day.drivers, reviewed_by=day.reviewed_by_id, delta=day_delta)
        data["local"] = local
        rows.append(dict(
            entry_id=entry.pk, prediction_id=prediction.pk, base_points=base_points,
            podium_adjustment=podium_adjustment, crazy_points=crazy_points,
            other_adjustment=other_adjustment, points=base_points+podium_adjustment+crazy_points+other_adjustment,
            breakdown={"base": base_breakdown, "podium_adjustment": podium_adjustment,
                       "crazy_points": crazy_points, "adjustments": local["adjustments"]},
            rules_version=league_season.rules_version, input_data=data, input_digest=_digest(data),
        ))
    return rows


def _audit_value(score):
    if score is None:
        return None
    result = {"prediction_id": score.prediction_id, "points": score.points,
              "rules_version": score.rules_version, "breakdown": score.breakdown,
              "input_digest": score.input_digest, "input_data": score.input_data}
    if isinstance(score, LeagueEventScore):
        result.update(entry_id=score.entry_id, base_points=score.base_points,
                      podium_adjustment=score.podium_adjustment, crazy_points=score.crazy_points,
                      other_adjustment=score.other_adjustment)
    else:
        result["user_id"] = score.user_id
    return result


def _persist(model, queryset, rows, *, actor, event, league_season=None):
    key = "entry_id" if league_season else "user_id"
    existing = {getattr(score, key): score for score in queryset}
    new, changed, removed, audits = [], [], [], []
    now = timezone.now()
    action = CompetitionScoreAudit.Action.LEAGUE_PROJECTED if league_season else CompetitionScoreAudit.Action.GLOBAL_PROJECTED
    fields = list(rows[0]) if rows else []
    for row in rows:
        score = existing.pop(row[key], None)
        before = _audit_value(score)
        if score is not None and all(getattr(score, field) == value for field, value in row.items()):
            continue
        if score is None:
            score = model(event=event, **row, calculated_at=now)
            new.append(score)
        else:
            for field, value in row.items():
                setattr(score, field, value)
            score.calculated_at = now
            changed.append(score)
        audits.append(CompetitionScoreAudit(event=event, league_season=league_season,
            entry_id=row.get("entry_id"), actor=actor, action=action, before=before, after=_audit_value(score)))
    for score in existing.values():
        removed.append(score.pk)
        audits.append(CompetitionScoreAudit(event=event, league_season=league_season,
            entry_id=getattr(score, "entry_id", None), actor=actor, action=action, before=_audit_value(score), after=None))
    if new:
        model.objects.bulk_create(new, batch_size=250)
    if changed:
        model.objects.bulk_update(changed, fields+["calculated_at"], batch_size=100)
    if removed:
        queryset.filter(pk__in=removed).delete()
    if audits:
        CompetitionScoreAudit.objects.bulk_create(audits, batch_size=250)
    return {"total": len(rows), "created": len(new), "updated": len(changed), "removed": len(removed)}


def preview_global_event(*, actor, event):
    _require_platform_operator(actor)
    event = Event.objects.get(pk=event.pk)
    return _global_rows(event, _published_result(event))


@transaction.atomic
def recalculate_global_event(*, actor, event):
    _require_platform_operator(actor)
    event = Event.objects.select_for_update().get(pk=event.pk)
    return _persist(GlobalEventScore, GlobalEventScore.objects.filter(event=event),
                    _global_rows(event, _published_result(event)), actor=actor, event=event)


def preview_league_event(*, actor, league_season, event):
    league_season, event = _scope(league_season, event, actor=actor, moderator=True)
    return _league_rows(league_season, event, _published_result(event))


def _project_league(actor, league_season, event):
    return _persist(LeagueEventScore,
        LeagueEventScore.objects.filter(event=event, entry__league_season=league_season),
        _league_rows(league_season, event, _published_result(event)),
        actor=actor, event=event, league_season=league_season)


@transaction.atomic
def recalculate_league_event(*, actor, league_season, event):
    league_season, event = _scope(league_season, event, actor=actor, lock=True, moderator=True)
    return _project_league(actor, league_season, event)


@transaction.atomic
def judge_crazy_prediction(*, actor, league_season, entry, event, approved):
    league_season, event = _scope(league_season, event, actor=actor, lock=True, moderator=True)
    require_crazy_judge(actor, league_season)
    entry = _entry_for(league_season, event, entry.pk)
    if type(approved) is not bool:
        raise ValidationError("Решение должно быть явным: засчитано или нет.")
    if timezone.now() < event.deadline:
        raise ValidationError("Крейзи-предикты проверяются после закрытия прогнозов.")
    prediction = _predictions(event, [entry.membership.user_id]).get(entry.membership.user_id)
    if prediction is None or not prediction.crazy_prediction.strip():
        raise ValidationError("У игрока нет своевременно сохранённого крейзи-предикта.")
    digest = _text_digest(prediction)
    decision = LeagueCrazyDecision.objects.filter(entry=entry, event=event).first()
    before = None if decision is None else dict(approved=decision.approved, text_digest=decision.text_digest, reviewed_by=decision.reviewed_by_id)
    if decision and decision.approved == approved and decision.text_digest == digest:
        if event.status == Event.Status.SCORED:
            _project_league(actor, league_season, event)
        return decision
    decision = decision or LeagueCrazyDecision(entry=entry, event=event, prediction=prediction)
    decision.approved = approved;decision.text_digest = digest
    decision.reviewed_by = actor;decision.reviewed_at = timezone.now()
    decision.full_clean();decision.save()
    after = dict(approved=approved, text_digest=digest, reviewed_by=actor.pk)
    CompetitionScoreAudit.objects.create(event=event, league_season=league_season, entry=entry,
        actor=actor, action=CompetitionScoreAudit.Action.CRAZY_DECIDED, before=before, after=after)
    if event.status == Event.Status.SCORED:
        _project_league(actor, league_season, event)
    return decision


@transaction.atomic
def apply_podium_bonus(*, actor, bonus, slot, driver):
    # The client never supplies points or issues a reward. A trusted future
    # arcade producer must have already persisted this grant for this player.
    if not isinstance(slot, str) or not isinstance(driver, str):
        raise ValidationError("Место подиума и пилот должны быть строками.")
    bonus = LeaguePodiumBonus.objects.select_related("entry__league_season").get(pk=bonus.pk)
    league_season, event = _scope(bonus.entry.league_season, bonus.event, actor=actor, lock=True)
    entry = _entry_for(league_season, event, bonus.entry_id)
    if entry.membership.user_id != actor.pk or league_season.ruleset != LeagueSeason.Ruleset.PADDOCK:
        raise PermissionDenied("Этот бонус недоступен игроку.")
    bonus = LeaguePodiumBonus.objects.select_for_update().get(pk=bonus.pk)
    if bonus.used_at:
        if (bonus.slot, bonus.driver) == (slot, driver):
            return bonus
        raise ValidationError("Бонус уже использован.")
    now = timezone.now()
    if (not bonus.source_key.strip() or now < bonus.granted_at or event.status == Event.Status.SCORED
            or event.race_datetime is None or now >= event.race_datetime):
        raise ValidationError("Апдейт доступен с момента получения бонуса до старта гонки.")
    prediction = _predictions(event, [actor.pk]).get(actor.pk)
    if prediction is None or slot not in ("p1", "p2", "p3") or driver == getattr(prediction, slot):
        raise ValidationError("Выберите новое место подиума и другого пилота.")
    bonus.slot = slot;bonus.driver = driver;bonus.used_at = now
    _valid_podium(bonus, prediction, event)
    bonus.full_clean();bonus.save(update_fields=("slot", "driver", "used_at"))
    CompetitionScoreAudit.objects.create(event=event, league_season=league_season, entry=entry,
        actor=actor, action=CompetitionScoreAudit.Action.PODIUM_APPLIED,
        before=None, after=dict(slot=slot, driver=driver, source_key=bonus.source_key))
    return bonus


@transaction.atomic
def sync_published_event(event_id, actor_id=None):
    """Trusted publication callback, not a user-callable permission bypass.

    Legacy publication has already committed. Failures cannot roll it back;
    moderators can retry their own projection using the guarded HTTP action.
    """
    event = Event.objects.select_for_update().get(pk=event_id)
    seasons = list(LeagueSeason.objects.filter(season__year=event.season_year,
        start_event__round_number__lte=event.round_number, is_legacy=False,
        league__archived_at__isnull=True).select_related("league", "season", "start_event").order_by("pk"))
    if not seasons:
        return
    actor = User.objects.filter(pk=actor_id).first() if actor_id else None
    try:
        result = _published_result(event)
    except ValidationError as exc:
        logger.warning("New score projection blocked for event %s: %s", event.pk, exc)
        return
    _persist(GlobalEventScore, GlobalEventScore.objects.filter(event=event), _global_rows(event, result), actor=actor, event=event)
    for season in seasons:
        season.league = League.objects.select_for_update().get(pk=season.league_id)
        try:
            if season.rules_version != RULES_VERSION:
                raise ValidationError("Неизвестная версия правил лиги.")
            _project_league(actor, season, event)
        except ValidationError as exc:
            logger.warning("Private score projection blocked for season %s, event %s: %s", season.pk, event.pk, exc)
