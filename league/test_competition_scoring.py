from datetime import datetime, timedelta, timezone as dt_timezone
import hashlib
import json
import random
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext

from .competition_scoring import (
    apply_podium_bonus, judge_crazy_prediction, preview_global_event,
    preview_league_event, recalculate_global_event, recalculate_league_event,
)
from .leagues import create_league, enroll_member, import_legacy_league
from .models import (
    ArcadeWheelSpin, CompetitionScoreAudit, Event, GlobalEventScore, LeagueCrazyDecision,
    LeagueEventScore, LeagueMembership, LeaguePodiumBonus, LeagueScoreAdjustment,
    LeagueSeasonEntry, Prediction, Result, Score, Season,
)
from .prediction_rules import PREDICTION_FIELDS, calculate_base_points
from .scoring import calculate_points


class ObjectivePredictionRuleTests(SimpleTestCase):
    def fixtures(self):
        values = dict(p1="russell", p2="leclerc", p3="norris", pole="russell",
            sprint_qualifying_winner="russell", sprint_winner="russell",
            fastest_lap="russell", driver_of_day="russell", safety_car_count=1, dnf_count=2)
        prediction = SimpleNamespace(**values, crazy_prediction_approved=True)
        result = SimpleNamespace(**values, event=SimpleNamespace(has_sprint=True), driver_of_day_multiple=[])
        return prediction, result

    def test_version_one_weights_and_no_crazy_in_objective_score(self):
        prediction, result = self.fixtures()
        self.assertEqual(calculate_base_points(prediction, result)[0], 48)
        self.assertEqual(calculate_points(prediction, result)[0], 53)
        for blocked in (False, True):
            for vetoed in (False, True):
                points, breakdown = calculate_points(prediction, result, crazy_blocked=blocked, crazy_vetoed=vetoed)
                self.assertEqual(points, 48 if blocked or vetoed else 53)
                self.assertEqual(list(breakdown)[-2:], ["Safety Car Count", "DNF Count"])
        with self.assertRaises(ValueError):
            calculate_base_points(prediction, result, rules_version=99)

    def test_sprint_and_multiple_driver_of_day_match_existing_rules(self):
        prediction, result = self.fixtures()
        result.event.has_sprint = False
        result.driver_of_day = "leclerc"
        result.driver_of_day_multiple = ["LECLERC", " Russell "]
        self.assertEqual(calculate_base_points(prediction, result)[0], 40)
        result.driver_of_day_multiple = []
        self.assertEqual(calculate_base_points(prediction, result)[0], 37)
        result.p1, result.p2, result.p3 = "norris", "russell", "leclerc"
        points, breakdown = calculate_base_points(prediction, result)
        self.assertEqual(points, 26)
        self.assertEqual([breakdown[f"P{i} (Top-3)"] for i in (1, 2, 3)], [3, 3, 3])

    def test_12000_cases_match_frozen_published_legacy_formula(self):
        # Golden digest generated from the unmodified formula at 41084b7.
        # Self-contained: CI does not need Git history or database access.
        rng = random.Random(2502027)
        drivers = ["", "russell", "leclerc", "norris", " Russell ", "LECLERC", None]
        digest = hashlib.sha256()
        for _ in range(3000):
            pv = {f: rng.choice(drivers) if not f.endswith("_count") else rng.randrange(4) for f in PREDICTION_FIELDS}
            rv = {f: rng.choice(drivers) if not f.endswith("_count") else rng.randrange(4) for f in PREDICTION_FIELDS}
            prediction = SimpleNamespace(**pv, crazy_prediction_approved=rng.choice([True, False]))
            result = SimpleNamespace(**rv, driver_of_day_multiple=rng.choice([[], None, ["russell"], ["", "LECLERC"], ["norris", "russell"]]), event=SimpleNamespace(has_sprint=rng.choice([True, False])))
            for blocked in [True, False]:
                for vetoed in [True, False]:
                    points, details = calculate_points(prediction, result, crazy_blocked=blocked, crazy_vetoed=vetoed)
                    digest.update(json.dumps([points, list(details.items())], ensure_ascii=False, separators=(",", ":")).encode())
        self.assertEqual(digest.hexdigest(), "371a75d155cc88f8fffb2c9ce4ae6ff2391e8a20937837418be04e2dce9f018e")


class IsolatedCompetitionScoringTests(TestCase):
    def setUp(self):
        self.open_now = datetime(2027, 3, 1, 12, tzinfo=dt_timezone.utc)
        self.clock_patch = patch("django.utils.timezone.now", return_value=self.open_now)
        self.clock = self.clock_patch.start()
        self.addCleanup(self.clock_patch.stop)
        self.season = Season.objects.create(year=2027)
        self.owner = User.objects.create_user("owner-a")
        self.owner_b = User.objects.create_user("owner-b")
        self.player = User.objects.create_user("player")
        self.staff = User.objects.create_user("operator", is_staff=True)
        self.event = Event.objects.create(name="GP", season_year=2027, round_number=1,
            deadline=self.open_now+timedelta(days=1), race_datetime=self.open_now+timedelta(days=2))
        self.next_event = Event.objects.create(name="Next GP", season_year=2027, round_number=2,
            deadline=self.open_now+timedelta(days=8), race_datetime=self.open_now+timedelta(days=9))
        self.a = create_league(owner=self.owner, name="A", season=self.season, start_event=self.event, ruleset="paddock")
        self.b = create_league(owner=self.owner_b, name="B", season=self.season, start_event=self.event, ruleset="paddock")
        self.classic = create_league(owner=self.owner, name="Classic", season=self.season, start_event=self.event)
        self.ea = enroll_member(actor=self.owner, league_season=self.a, user=self.player)
        self.eb = enroll_member(actor=self.owner_b, league_season=self.b, user=self.player)
        self.ec = enroll_member(actor=self.owner, league_season=self.classic, user=self.player)
        self.values = dict(p1="russell", p2="leclerc", p3="norris", pole="russell", safety_car_count=1, dnf_count=2)
        self.prediction = Prediction.objects.create(event=self.event, user=self.player,
            **self.values, crazy_prediction="Мемный прогноз", crazy_prediction_approved=True)

    def finish(self, **changes):
        self.clock.return_value = self.event.race_datetime+timedelta(hours=2)
        Event.objects.filter(pk=self.event.pk).update(status=Event.Status.SCORED)
        self.event.refresh_from_db()
        values = {**self.values, **changes}
        return Result.objects.create(event=self.event, published_at=self.clock.return_value, **values)

    def global_score(self):
        return recalculate_global_event(actor=self.staff, event=self.event)

    def local_score(self, league_season=None):
        ls = league_season or self.a
        actor = self.owner_b if ls == self.b else self.owner
        return recalculate_league_event(actor=actor, league_season=ls, event=self.event)

    def judge(self, approved=True, ls=None, entry=None, actor=None):
        return judge_crazy_prediction(actor=actor or self.owner, league_season=ls or self.a,
            entry=entry or self.ea, event=self.event, approved=approved)

    def grant(self, entry=None, **changes):
        return LeaguePodiumBonus.objects.create(entry=entry or self.ea, event=self.event,
            source_key="wheel:test-grant", **changes)

    def test_global_ignores_legacy_approval_local_adjustments_and_legacy_score(self):
        Score.objects.create(event=self.event, user=self.player, points=999, duel_adjustment=10)
        LeagueScoreAdjustment.objects.create(entry=self.ea, event=self.event, kind="arcade", source_key="spin:1", points=2, reason="Пит-уолл")
        self.finish()
        self.assertEqual(self.global_score(), {"total": 1, "created": 1, "updated": 0, "removed": 0})
        score = GlobalEventScore.objects.get()
        self.assertEqual(score.points, 34)
        self.assertNotIn("crazy_prediction", score.input_data["prediction"])
        self.assertNotIn("Crazy Prediction", score.breakdown)
        self.assertEqual(Score.objects.get().points, 999)
        self.assertFalse(LeagueEventScore.objects.exists())

    def test_global_includes_real_staff_predictions_and_not_late_submissions(self):
        Prediction.objects.create(event=self.event, user=self.staff, **self.values)
        self.finish()
        late = Prediction.objects.create(event=self.event, user=self.owner, **self.values)
        self.global_score()
        self.assertEqual(set(GlobalEventScore.objects.values_list("user_id", flat=True)), {self.player.pk, self.staff.pk})
        self.assertFalse(GlobalEventScore.objects.filter(prediction=late).exists())

    def test_global_and_local_retries_do_not_duplicate_points_timestamps_or_audits(self):
        self.finish();self.global_score();self.local_score()
        original = list(GlobalEventScore.objects.values())
        local_original = list(LeagueEventScore.objects.values())
        audit_count = CompetitionScoreAudit.objects.count()
        self.clock.return_value += timedelta(hours=1)
        self.assertEqual(self.global_score()["updated"], 0)
        self.assertEqual(self.local_score()["updated"], 0)
        self.assertEqual(original, list(GlobalEventScore.objects.values()))
        self.assertEqual(local_original, list(LeagueEventScore.objects.values()))
        self.assertEqual(CompetitionScoreAudit.objects.count(), audit_count)

    def test_moderator_decision_changes_only_its_league_and_can_be_revoked(self):
        self.finish();self.global_score()
        self.local_score();self.local_score(self.b);self.local_score(self.classic)
        public_before = list(GlobalEventScore.objects.values())
        foreign_before = list(LeagueEventScore.objects.exclude(entry=self.ea).values())
        self.judge()
        self.assertEqual(LeagueEventScore.objects.get(entry=self.ea).points, 39)
        self.assertEqual(foreign_before, list(LeagueEventScore.objects.exclude(entry=self.ea).values()))
        self.assertEqual(public_before, list(GlobalEventScore.objects.values()))
        audits = CompetitionScoreAudit.objects.count()
        self.judge();self.assertEqual(CompetitionScoreAudit.objects.count(), audits)
        self.judge(False)
        self.assertEqual(LeagueEventScore.objects.get(entry=self.ea).points, 34)
        self.assertEqual(LeagueCrazyDecision.objects.count(), 1)
        self.assertEqual(CompetitionScoreAudit.objects.filter(action="crazy_decided").count(), 2)
        self.assertTrue(Prediction.objects.get(pk=self.prediction.pk).crazy_prediction_approved)

    def test_judging_before_result_publication_is_retained_and_retry_can_project_later(self):
        self.clock.return_value = self.event.deadline
        decision = self.judge()
        self.assertFalse(LeagueEventScore.objects.exists())
        self.finish();self.assertEqual(self.judge().pk, decision.pk)
        self.assertEqual(LeagueEventScore.objects.get(entry=self.ea).crazy_points, 5)
        self.assertEqual(CompetitionScoreAudit.objects.filter(action="crazy_decided").count(), 1)

    def test_crazy_foreign_players_non_members_staff_and_classic_are_denied(self):
        self.finish()
        for actor, ls, entry in [
            (self.player, self.a, self.ea), (self.staff, self.a, self.ea),
            (self.owner_b, self.a, self.ea), (self.owner, self.a, self.eb),
            (self.owner, self.classic, self.ec), (AnonymousUser(), self.a, self.ea),
        ]:
            with self.assertRaises(PermissionDenied):
                self.judge(actor=actor, ls=ls, entry=entry)
        self.assertFalse(LeagueCrazyDecision.objects.exists())
        self.assertFalse(CompetitionScoreAudit.objects.exists())

    def test_crazy_timing_boolean_and_empty_text_are_validated(self):
        with self.assertRaises(ValidationError):
            self.judge()
        self.finish()
        with self.assertRaises(ValidationError):
            self.judge("false")
        Prediction.objects.filter(pk=self.prediction.pk).update(crazy_prediction=" ")
        with self.assertRaises(ValidationError):
            self.judge()
        self.assertFalse(LeagueCrazyDecision.objects.exists())

    def test_changed_crazy_text_requires_re_review_but_cannot_change_public_points(self):
        self.finish();self.judge();self.global_score()
        public_before = list(GlobalEventScore.objects.values())
        previous = list(LeagueEventScore.objects.values())
        Prediction.objects.filter(pk=self.prediction.pk).update(crazy_prediction="Другая формулировка")
        with self.assertRaises(ValidationError):
            self.local_score()
        self.assertEqual(previous, list(LeagueEventScore.objects.values()))
        self.assertEqual(self.global_score()["updated"], 0)
        self.assertEqual(public_before, list(GlobalEventScore.objects.values()))
        self.judge(False)
        self.assertEqual(LeagueEventScore.objects.get(entry=self.ea).points, 34)

    def test_local_podium_changes_neither_shared_prediction_nor_other_league_or_public(self):
        bonus = self.grant()
        before = dict(Prediction.objects.values().get(pk=self.prediction.pk))
        apply_podium_bonus(actor=self.player, bonus=bonus, slot="p1", driver="verstappen")
        self.assertEqual(before, dict(Prediction.objects.values().get(pk=self.prediction.pk)))
        self.finish(p1="verstappen");self.global_score();self.local_score();self.local_score(self.b)
        local = LeagueEventScore.objects.get(entry=self.ea)
        self.assertEqual((local.base_points, local.podium_adjustment, local.points), (24, 10, 34))
        self.assertEqual(GlobalEventScore.objects.get().points, 24)
        self.assertEqual(LeagueEventScore.objects.get(entry=self.eb).points, 24)
        self.assertEqual(before, dict(Prediction.objects.values().get(pk=self.prediction.pk)))

    def test_podium_only_uses_existing_own_grant_once_and_never_duplicates_drivers(self):
        bonus = self.grant()
        for actor in [self.owner, self.owner_b, self.staff]:
            with self.assertRaises(PermissionDenied):
                apply_podium_bonus(actor=actor, bonus=bonus, slot="p1", driver="verstappen")
        for slot, driver in [("p4", "verstappen"), ("p1", "russell"), ("p1", "norris"), ("p1", "forged"), ("p1", None), ("p1", ["norris"]), ({}, "verstappen")]:
            with self.assertRaises(ValidationError):
                apply_podium_bonus(actor=self.player, bonus=bonus, slot=slot, driver=driver)
        self.assertFalse(CompetitionScoreAudit.objects.exists())
        applied = apply_podium_bonus(actor=self.player, bonus=bonus, slot="p1", driver="verstappen")
        self.clock.return_value = self.event.race_datetime
        same = apply_podium_bonus(actor=self.player, bonus=bonus, slot="p1", driver="verstappen")
        self.assertEqual(applied.pk, same.pk)
        with self.assertRaises(ValidationError):
            apply_podium_bonus(actor=self.player, bonus=bonus, slot="p3", driver="hamilton")
        self.assertEqual(CompetitionScoreAudit.objects.filter(action="podium_applied").count(), 1)

    def test_podium_expires_at_race_start_and_cannot_use_future_or_classic_grants(self):
        bonus = self.grant(granted_at=self.open_now+timedelta(hours=1))
        with self.assertRaises(ValidationError):
            apply_podium_bonus(actor=self.player, bonus=bonus, slot="p1", driver="verstappen")
        self.clock.return_value = self.event.race_datetime
        with self.assertRaises(ValidationError):
            apply_podium_bonus(actor=self.player, bonus=bonus, slot="p1", driver="verstappen")
        classic = self.grant(entry=self.ec)
        with self.assertRaises(PermissionDenied):
            apply_podium_bonus(actor=self.player, bonus=classic, slot="p1", driver="verstappen")
        self.assertFalse(CompetitionScoreAudit.objects.exists())

    def test_local_adjustments_are_deduplicated_scoped_and_classic_ignores_them(self):
        for entry in [self.ea, self.ec]:
            LeagueScoreAdjustment.objects.create(entry=entry, event=self.event, kind="duel", source_key="duel:17", points=-4, reason="Дуэль")
        with self.assertRaises(IntegrityError), transaction.atomic():
            LeagueScoreAdjustment.objects.create(entry=self.ea, event=self.event, kind="duel", source_key="duel:17", points=-4, reason="Повтор")
        self.finish();self.global_score();self.local_score();self.local_score(self.b);self.local_score(self.classic)
        self.assertEqual(LeagueEventScore.objects.get(entry=self.ea).points, 30)
        self.assertEqual(LeagueEventScore.objects.get(entry=self.eb).points, 34)
        self.assertEqual(LeagueEventScore.objects.get(entry=self.ec).points, 34)
        self.assertEqual(GlobalEventScore.objects.get().points, 34)
        self.local_score();self.assertEqual(LeagueEventScore.objects.get(entry=self.ea).points, 30)

    def test_projection_permissions_use_database_roles_not_caller_supplied_flags(self):
        self.finish()
        self.owner.is_staff = True  # Unsaved impersonation cannot publish globally.
        for actor in [self.owner, self.player, AnonymousUser()]:
            with self.assertRaises(PermissionDenied):
                recalculate_global_event(actor=actor, event=self.event)
            with self.assertRaises(PermissionDenied):
                preview_global_event(actor=actor, event=self.event)
        for actor in [self.staff, self.owner_b, self.player, AnonymousUser()]:
            with self.assertRaises(PermissionDenied):
                recalculate_league_event(actor=actor, league_season=self.a, event=self.event)
            with self.assertRaises(PermissionDenied):
                preview_league_event(actor=actor, league_season=self.a, event=self.event)
        self.assertFalse(GlobalEventScore.objects.exists());self.assertFalse(LeagueEventScore.objects.exists())

    def test_previews_are_read_only_and_unknown_rules_or_wrong_season_fail_closed(self):
        self.finish()
        self.assertEqual(preview_global_event(actor=self.staff, event=self.event)[0]["points"], 34)
        self.assertEqual(preview_league_event(actor=self.owner, league_season=self.a, event=self.event)[0]["points"], 34)
        self.assertFalse(CompetitionScoreAudit.objects.exists());self.assertFalse(GlobalEventScore.objects.exists())
        self.a.rules_version = 2;self.a.save(update_fields=("rules_version",))
        with self.assertRaises(ValidationError):
            self.local_score()
        self.a.rules_version = 1;self.a.save(update_fields=("rules_version",))
        other = Event.objects.create(name="Wrong year", season_year=2028, round_number=1, deadline=self.open_now)
        with self.assertRaises(ValidationError):
            recalculate_league_event(actor=self.owner, league_season=self.a, event=other)

    def test_pending_or_future_official_result_is_not_published(self):
        for action in [self.global_score, self.local_score]:
            with self.assertRaises(ValidationError):
                action()
        result = self.finish()
        result.published_at = self.clock.return_value+timedelta(hours=1);result.save(update_fields=("published_at",))
        with self.assertRaises(ValidationError):
            self.global_score()
        result.published_at = None;result.save(update_fields=("published_at",))
        with self.assertRaises(ValidationError):
            self.local_score()

    def test_result_correction_replaces_points_and_keeps_audited_input_snapshots(self):
        result = self.finish();self.global_score();self.local_score()
        result.p1 = "verstappen";result.save(update_fields=("p1",))
        self.assertEqual(self.global_score()["updated"], 1)
        self.assertEqual(self.local_score()["updated"], 1)
        self.assertEqual(GlobalEventScore.objects.get().points, 24)
        self.assertEqual(LeagueEventScore.objects.get(entry=self.ea).points, 24)
        audit = CompetitionScoreAudit.objects.filter(action="global_projected").order_by("pk").last()
        self.assertEqual(audit.before["points"], 34);self.assertEqual(audit.after["points"], 24)
        self.assertEqual(audit.before["input_data"]["result"]["p1"], "russell")
        self.assertEqual(audit.after["input_data"]["result"]["p1"], "verstappen")

    def test_recalculation_repairs_corrupt_projection_instead_of_trusting_digest(self):
        self.finish();self.global_score();self.local_score()
        GlobalEventScore.objects.update(points=999)
        LeagueEventScore.objects.update(points=999, other_adjustment=965)
        self.assertEqual(self.global_score()["updated"], 1)
        self.assertEqual(self.local_score()["updated"], 1)
        self.assertEqual(GlobalEventScore.objects.get().points, 34)
        self.assertEqual(LeagueEventScore.objects.get(entry=self.ea).points, 34)

    def test_late_entry_does_not_backfill_earlier_prediction_and_disabled_access_keeps_history(self):
        late = User.objects.create_user("late")
        Prediction.objects.create(event=self.event, user=late, **self.values)
        self.clock.return_value = self.event.deadline
        entry = enroll_member(actor=self.owner, league_season=self.a, user=late)
        self.assertEqual(entry.first_event, self.next_event)
        self.finish();self.global_score();self.local_score()
        self.assertTrue(GlobalEventScore.objects.filter(user=late).exists())
        self.assertFalse(LeagueEventScore.objects.filter(entry=entry, event=self.event).exists())
        LeagueMembership.objects.filter(pk=self.ea.membership_id).update(is_active=False)
        self.assertEqual(self.local_score()["updated"], 0)
        self.assertTrue(LeagueEventScore.objects.filter(entry=self.ea).exists())

    def test_old_podium_edits_and_legacy_leagues_require_explicit_migration(self):
        legacy, _ = import_legacy_league(owner=self.owner, season_year=2027)
        self.finish()
        with self.assertRaises(ValidationError):
            recalculate_league_event(actor=self.owner, league_season=legacy, event=self.event)
        ArcadeWheelSpin.objects.create(event=self.event, winner=self.player, winner_score=10,
            prize="podium_edit", activated_at=self.clock.return_value)
        for action in [self.global_score, self.local_score]:
            with self.assertRaises(ValidationError):
                action()
        self.assertFalse(GlobalEventScore.objects.exists());self.assertFalse(LeagueEventScore.objects.exists())

    def test_atomic_decision_rolls_back_if_projection_cannot_be_completed(self):
        self.finish()
        with patch("league.competition_scoring._persist", side_effect=RuntimeError("simulated database error")):
            with self.assertRaises(RuntimeError):
                self.judge()
        self.assertFalse(LeagueCrazyDecision.objects.exists())
        self.assertFalse(CompetitionScoreAudit.objects.exists())
        self.assertFalse(LeagueEventScore.objects.exists())

    def test_invalidated_source_removes_only_its_projection_with_audit(self):
        self.finish();self.global_score();self.local_score();self.local_score(self.b)
        Prediction.objects.filter(pk=self.prediction.pk).update(created_at=self.event.deadline)
        self.assertEqual(self.global_score()["removed"], 1)
        self.assertEqual(self.local_score()["removed"], 1)
        self.assertFalse(GlobalEventScore.objects.exists())
        self.assertTrue(LeagueEventScore.objects.filter(entry=self.eb).exists(), "Other leagues are not silently recalculated")
        audit = CompetitionScoreAudit.objects.filter(action="global_projected").order_by("pk").last()
        self.assertEqual(audit.before["points"], 34);self.assertIsNone(audit.after)

    def test_corrupt_cross_league_entry_fails_without_reading_foreign_inputs(self):
        self.finish()
        LeagueSeasonEntry.objects.filter(pk=self.ea.pk).update(membership=self.eb.membership)
        with self.assertRaises(ValidationError):
            self.local_score()
        self.assertFalse(LeagueEventScore.objects.exists());self.assertFalse(CompetitionScoreAudit.objects.exists())

    def test_scoped_model_validation_and_database_total_constraints(self):
        for model, kwargs in [
            (LeagueCrazyDecision, dict(prediction=self.prediction, reviewed_by=self.owner, text_digest="a"*64)),
            (LeagueEventScore, dict(prediction=self.prediction, input_digest="a"*64)),
        ]:
            foreign = self.a.entries.get(membership__user=self.owner)
            with self.assertRaises(ValidationError):
                model(entry=foreign, event=self.event, **kwargs).full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            LeagueEventScore.objects.create(entry=self.ea, event=self.event, prediction=self.prediction, points=15, input_digest="a"*64)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CompetitionScoreAudit.objects.create(event=self.event, action="crazy_decided", entry=None, league_season=None)

    def test_250_player_projection_uses_bounded_queries_and_retry_is_read_only(self):
        users = User.objects.bulk_create([User(username=f"load-{i}") for i in range(249)])
        members = LeagueMembership.objects.bulk_create([LeagueMembership(league=self.a.league, user=user) for user in users])
        LeagueSeasonEntry.objects.bulk_create([LeagueSeasonEntry(league_season=self.a, membership=member, first_event=self.event) for member in members])
        Prediction.objects.bulk_create([Prediction(event=self.event, user=user, **self.values) for user in users])
        self.finish()
        with CaptureQueriesContext(connection) as queries:
            summary = self.local_score()
        self.assertEqual(summary["created"], 250)
        self.assertLess(len(queries), 30, f"Per-player database queries detected: {len(queries)}")
        with CaptureQueriesContext(connection) as retry:
            summary = self.local_score()
        self.assertEqual(summary, {"total": 250, "created": 0, "updated": 0, "removed": 0})
        self.assertLess(len(retry), 16)
        self.assertEqual(CompetitionScoreAudit.objects.filter(action="league_projected").count(), 250)
