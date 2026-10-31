"""Versioned reconciliation used by migrations and explicit administrator actions.

Never run this on public GETs. Existing prediction events are never rewritten or
renumbered; ambiguous matches are reported instead of risking historic scores.
Keep the v1 entry point compatible with historical Django model registries.
"""
from collections import defaultdict
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.apps import apps as live_apps
from django.db import transaction

from .circuits import CIRCUIT_CHOICES, resolve_circuit


def thursday_deadline(starts_on):
    thursday = starts_on - timedelta(days=(starts_on.weekday() - 3) % 7)
    return datetime.combine(thursday, time(23, 59), tzinfo=ZoneInfo("Europe/Moscow"))


def event_circuit_key(event):
    circuit = resolve_circuit(event.circuit, event.name, event.season_year)
    if circuit:
        return circuit["key"]
    if event.circuit == "sepang" or any(alias in event.name.casefold() for alias in ("сепанг", "sepang", "малайзи")):
        return "sepang"
    return ""


def sync_calendar_events_v1(season_year, *, model_registry=live_apps, using="default", round_ids=None):
    Round = model_registry.get_model("league", "RaceCalendarRound")
    Event = model_registry.get_model("league", "Event")
    report = {"created": 0, "linked": 0, "preserved": 0, "conflicts": []}
    valid_circuits = {key for key, _ in CIRCUIT_CHOICES}
    with transaction.atomic(using=using):
        rounds = Round.objects.using(using).select_for_update().filter(season_year=season_year).order_by("round_number")
        if round_ids is not None:
            rounds = rounds.filter(pk__in=round_ids)
        events = list(Event.objects.using(using).select_for_update().filter(season_year=season_year))
        by_id = {event.pk: event for event in events}
        by_round = {event.round_number: event for event in events}
        by_circuit = defaultdict(list)
        for event in events:
            key = event_circuit_key(event)
            if key:
                by_circuit[key].append(event)
        for race in rounds:
            if race.prediction_event_id:
                if race.prediction_event_id in by_id:
                    report["preserved"] += 1
                else:
                    report["conflicts"].append(f"R{race.round_number}: ссылка ведёт в другой сезон")
                continue
            candidates = by_circuit[race.circuit]
            if len(candidates) > 1:
                report["conflicts"].append(f"R{race.round_number}: несколько карточек трассы {race.circuit}")
                continue
            event = candidates[0] if candidates else None
            if event is None and race.round_number in by_round:
                report["conflicts"].append(f"R{race.round_number}: номер занят другой карточкой ({by_round[race.round_number].name})")
                continue
            if event is None:
                event = Event.objects.using(using).create(
                    season_year=season_year, round_number=race.round_number,
                    name=f"{race.location}, {race.country}",
                    circuit=race.circuit if race.circuit in valid_circuits else "",
                    deadline=thursday_deadline(race.starts_on), race_datetime=race.race_at,
                    qualifying_datetime=race.qualifying_at + timedelta(hours=1) if race.qualifying_at else None,
                    has_sprint=race.has_sprint, cover_image=race.cover_image.name or None, status="open")
                by_id[event.pk] = event
                by_round[event.round_number] = event
                by_circuit[race.circuit].append(event)
                report["created"] += 1
            else:
                report["preserved"] += 1
            Round.objects.using(using).filter(pk=race.pk).update(prediction_event_id=event.pk)
            report["linked"] += 1
    return report
