# Calendar and prediction cards

The calendar owns the sporting schedule; `Event` owns prediction deadlines and scoring. Public calendar/home requests remain read-only. Every linked calendar card opens its Event, including far-future races. The homepage no longer duplicates the season calendar; it retains the current GP, countdown and league widgets.

Migration 0062 fills missing Events for seasons already containing prediction Events and links calendar rounds. It never renumbers, replaces or updates existing Events, predictions, results, covers or deadlines. Match priority: explicit same-season link, then a unique circuit match. An occupied round number or ambiguous identity is reported for manual review instead of reusing an unrelated event. This matters for historical/custom schedules.

New Events get their calendar race time, sprint format and qualifying end (session start plus one hour). The default prediction deadline is Thursday at 23:59 Europe/Moscow preceding the weekend. A Thursday-starting Las Vegas weekend uses that Thursday; the rule is not UTC or venue-local midnight. Past deadlines remain closed. No seven-day opening restriction applies: future cards accept predictions immediately.

Saving a calendar round in Django admin creates/links its missing card. The calendar changelist action “Создать недостающие карточки прогнозов” handles selected rows. For a fresh prediction season or explicit reconciliation:

```sh
python manage.py sync_calendar_events --season 2026
```

The operation is idempotent and never creates data during public page rendering. The versioned v1 service accepts historical model registries for migration replay; keep that entry point compatible with migration 0062.

Tests: `league.test_calendar_event_sync` covers all 23 calendar links, preserving manual events, safe identity conflicts, repeat execution, Thursday/Vegas deadlines and immediate forecast submission for distant races.
