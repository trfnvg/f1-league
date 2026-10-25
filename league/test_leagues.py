from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from .leagues import (
    create_league, enroll_member, import_legacy_league, legacy_member_ids,
    membership_for, require_crazy_judge, require_moderator, set_member_role,
)
from .models import (
    Event, League, LeagueMembership, LeagueSeason, LeagueSeasonEntry, Prediction,
    Score, Season, SeasonScore,
)


class PrivateLeagueFoundationTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.season = Season.objects.create(year=2027)
        self.owner = User.objects.create_user("owner")
        self.other = User.objects.create_user("other-owner")
        self.player = User.objects.create_user("player")
        self.staff = User.objects.create_user("platform-staff", is_staff=True)
        self.events = [Event.objects.create(
            name=f"GP {i}", season_year=2027, round_number=i,
            deadline=self.now+timedelta(days=(i-1)*7),
        ) for i in range(1, 5)]
        # R1 is already closed; R2, R3, R4 are future events.
        self.events[0].deadline = self.now-timedelta(days=1)
        self.events[0].save(update_fields=("deadline",))

    def create(self, owner=None, start=None, ruleset=LeagueSeason.Ruleset.CLASSIC):
        return create_league(owner=owner or self.owner, name="  Наша компания  ",
                             season=self.season, start_event=start or self.events[1], ruleset=ruleset)

    def test_creation_owns_only_this_league_and_enrolls_owner(self):
        ls = self.create()
        self.assertEqual(ls.league.name, "Наша компания")
        self.assertEqual(ls.start_event, self.events[1])
        self.assertEqual(ls.rules_version, 1)
        self.assertFalse(ls.is_legacy)
        self.assertIsNone(ls.league.legacy_key)
        entry = ls.entries.get()
        self.assertEqual(entry.membership.user, self.owner)
        self.assertEqual(entry.first_event, self.events[1])
        self.assertEqual(require_moderator(self.owner, ls.league), entry.membership)
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_staff)
        self.assertFalse(self.owner.is_superuser)

    def test_one_account_can_enter_multiple_independent_leagues_without_copying_predictions(self):
        a, b = self.create(), self.create(owner=self.other, start=self.events[2])
        prediction = Prediction.objects.create(event=self.events[2], user=self.player, p1="russell", p2="leclerc", p3="norris", pole="russell")
        ea = enroll_member(actor=self.owner, league_season=a, user=self.player)
        eb = enroll_member(actor=self.other, league_season=b, user=self.player)
        self.assertNotEqual(ea.membership.league_id, eb.membership.league_id)
        self.assertEqual(ea.first_event, self.events[1])
        self.assertEqual(eb.first_event, self.events[2])
        self.assertEqual(list(Prediction.objects.filter(user=self.player).values_list("pk", flat=True)), [prediction.pk])

    def test_starting_midseason_does_not_rewrite_existing_scores(self):
        old = Score.objects.create(user=self.player, event=self.events[0], points=45, prediction_points=40, duel_adjustment=5)
        ls = self.create(start=self.events[2])
        entry = enroll_member(actor=self.owner, league_season=ls, user=self.player)
        self.assertEqual(entry.first_event, self.events[2])
        old.refresh_from_db()
        self.assertEqual((old.points, old.prediction_points, old.duel_adjustment), (45, 40, 5))

    def test_late_join_starts_at_next_open_event_and_is_idempotent(self):
        ls = self.create()
        with patch("league.leagues.timezone.now", return_value=self.events[1].deadline):
            entry = enroll_member(actor=self.owner, league_season=ls, user=self.player)
        self.assertEqual(entry.first_event, self.events[2], "Deadline equality is already closed")
        original_time = entry.entered_at
        with patch("league.leagues.timezone.now", return_value=self.events[3].deadline+timedelta(days=1)):
            again = enroll_member(actor=self.owner, league_season=ls, user=self.player)
        self.assertEqual(again.pk, entry.pk)
        self.assertEqual(again.first_event, self.events[2])
        self.assertEqual(again.entered_at, original_time)
        self.assertEqual(LeagueMembership.objects.filter(league=ls.league, user=self.player).count(), 1)

    def test_admin_locked_future_event_is_skipped(self):
        ls = self.create()
        self.events[1].status = Event.Status.LOCKED
        self.events[1].save(update_fields=("status",))
        self.assertEqual(enroll_member(actor=self.owner, league_season=ls, user=self.player).first_event, self.events[2])

    def test_no_open_events_rolls_back_new_membership(self):
        ls = self.create()
        with patch("league.leagues.timezone.now", return_value=self.events[-1].deadline):
            with self.assertRaises(ValidationError):
                enroll_member(actor=self.owner, league_season=ls, user=self.player)
        self.assertFalse(LeagueMembership.objects.filter(league=ls.league, user=self.player).exists())

    def test_closed_or_wrong_season_creation_is_atomic(self):
        wrong_season = Season.objects.create(year=2028)
        for start, season in [(self.events[0], self.season), (self.events[1], wrong_season)]:
            with self.assertRaises(ValidationError):
                create_league(owner=self.owner, name="Bad", season=season, start_event=start)
        self.assertEqual(League.objects.count(), 0)
        self.assertEqual(LeagueMembership.objects.count(), 0)

    def test_invalid_name_and_ruleset_are_rejected_without_partial_records(self):
        for name, ruleset in [("   ", "classic"), ("a"*81, "classic"), ("Valid", "forged"), (None, "classic"), (42, "classic")]:
            with self.assertRaises(ValidationError):
                create_league(owner=self.owner, name=name, season=self.season, start_event=self.events[1], ruleset=ruleset)
        self.assertFalse(League.objects.exists())

    def test_non_member_and_staff_have_no_implicit_access(self):
        ls = self.create()
        for actor in [AnonymousUser(), self.other, self.staff]:
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    membership_for(actor, ls.league)
                with self.assertRaises(PermissionDenied):
                    enroll_member(actor=actor, league_season=ls, user=self.player)
        self.assertEqual(ls.entries.count(), 1)

    def test_player_cannot_enroll_or_self_promote(self):
        ls = self.create()
        entry = enroll_member(actor=self.owner, league_season=ls, user=self.player)
        with self.assertRaises(PermissionDenied):
            enroll_member(actor=self.player, league_season=ls, user=self.other)
        with self.assertRaises(PermissionDenied):
            set_member_role(actor=self.player, membership=entry.membership, role="moderator")

    def test_moderator_can_enroll_and_judge_only_their_paddock_league(self):
        a = self.create(ruleset=LeagueSeason.Ruleset.PADDOCK)
        b = self.create(owner=self.other, ruleset=LeagueSeason.Ruleset.PADDOCK)
        entry = enroll_member(actor=self.owner, league_season=a, user=self.player)
        set_member_role(actor=self.owner, membership=entry.membership, role="moderator")
        self.assertEqual(require_crazy_judge(self.player, a).user, self.player)
        added = enroll_member(actor=self.player, league_season=a, user=self.other)
        with self.assertRaises(PermissionDenied):
            require_crazy_judge(self.player, b)
        with self.assertRaises(PermissionDenied):
            enroll_member(actor=self.player, league_season=b, user=self.owner)
        with self.assertRaises(PermissionDenied):
            set_member_role(actor=self.player, membership=added.membership, role="moderator")
        with self.assertRaises(PermissionDenied):
            set_member_role(actor=self.owner, membership=b.entries.get().membership, role="moderator")

    def test_classic_has_no_crazy_judging_even_for_owner(self):
        ls = self.create()
        ls.ruleset = "paddock"  # Unsaved caller-supplied fields never grant rights.
        with self.assertRaises(PermissionDenied):
            require_crazy_judge(self.owner, ls)

    def test_permissions_use_current_database_ownership_archive_and_roles(self):
        ls = self.create()
        member = enroll_member(actor=self.owner, league_season=ls, user=self.player).membership
        fake = League(pk=ls.league_id, owner=self.player)
        with self.assertRaises(PermissionDenied):
            require_moderator(self.player, fake)
        set_member_role(actor=self.owner, membership=member, role="moderator")
        self.assertEqual(require_moderator(self.player, fake).pk, member.pk)
        set_member_role(actor=self.owner, membership=member, role="player")
        with self.assertRaises(PermissionDenied):
            require_moderator(self.player, fake)
        League.objects.filter(pk=ls.league_id).update(archived_at=self.now)
        with self.assertRaises(PermissionDenied):
            membership_for(self.owner, ls.league)  # Stale in-memory archive flag.

    def test_inactive_and_archived_access_denied_even_for_owner(self):
        ls = self.create()
        for actor in [AnonymousUser(), User(username="unsaved")]:
            with self.assertRaises(PermissionDenied):
                self.create(owner=actor)
        self.owner.is_active = False
        with self.assertRaises(PermissionDenied):
            require_moderator(self.owner, ls.league)
        self.owner.is_active = True
        ls.league.archived_at = self.now
        ls.league.save(update_fields=("archived_at",))
        with self.assertRaises(PermissionDenied):
            enroll_member(actor=self.owner, league_season=ls, user=self.player)

    def test_inactive_membership_not_reactivated_by_enrollment(self):
        ls = self.create()
        entry = enroll_member(actor=self.owner, league_season=ls, user=self.player)
        membership = entry.membership
        membership.is_active = False
        membership.save(update_fields=("is_active",))
        with self.assertRaises(PermissionDenied):
            enroll_member(actor=self.owner, league_season=ls, user=self.player)
        with self.assertRaises(ValidationError):
            set_member_role(actor=self.owner, membership=membership, role="moderator")
        with self.assertRaises(PermissionDenied):
            membership_for(self.player, ls.league)

    def test_model_validation_rejects_cross_league_and_retroactive_entry(self):
        a, b = self.create(), self.create(owner=self.other)
        foreign = b.entries.get().membership
        with self.assertRaises(ValidationError):
            LeagueSeasonEntry(league_season=a, membership=foreign, first_event=self.events[1]).full_clean()
        membership = LeagueMembership.objects.create(league=a.league, user=self.player)
        for event, entered_at in [(self.events[0], self.now), (self.events[1], self.events[1].deadline)]:
            with self.assertRaises(ValidationError):
                LeagueSeasonEntry(league_season=a, membership=membership, first_event=event, entered_at=entered_at).full_clean()
        a.is_legacy = True
        with self.assertRaises(ValidationError):
            a.full_clean()

    def test_database_rejects_duplicate_members_entries_seasons_and_unknown_roles(self):
        ls = self.create()
        entry = ls.entries.get()
        operations = [
            lambda: LeagueMembership.objects.create(league=ls.league, user=self.owner),
            lambda: LeagueMembership.objects.create(league=ls.league, user=self.player, role="owner"),
            lambda: LeagueSeason.objects.create(league=ls.league, season=self.season, start_event=self.events[1]),
            lambda: LeagueSeasonEntry.objects.create(league_season=ls, membership=entry.membership, first_event=self.events[1]),
        ]
        for operation in operations:
            with self.assertRaises(IntegrityError), transaction.atomic():
                operation()

    def test_legacy_preview_is_read_only_and_does_not_include_unrelated_users(self):
        Prediction.objects.create(event=self.events[0], user=self.player)
        SeasonScore.objects.create(user=self.other, season_year=2027, points=20)
        before = [model.objects.count() for model in [League, LeagueSeason, LeagueMembership, LeagueSeasonEntry]]
        output = StringIO()
        call_command("import_legacy_league", owner=self.owner.username, season=2027, stdout=output)
        self.assertIn("База не изменена", output.getvalue())
        self.assertEqual(before, [model.objects.count() for model in [League, LeagueSeason, LeagueMembership, LeagueSeasonEntry]])
        self.assertEqual(legacy_member_ids(2027, self.owner), {self.owner.pk, self.other.pk, self.player.pk})
        self.assertNotIn(self.staff.username, output.getvalue())

    def test_legacy_import_preserves_history_and_repeat_does_not_backfill_new_players(self):
        prediction = Prediction.objects.create(event=self.events[0], user=self.player, p1="russell", crazy_prediction_approved=True)
        score = Score.objects.create(event=self.events[0], user=self.player, points=35, prediction_points=30, duel_adjustment=5)
        before = (list(Prediction.objects.values()), list(Score.objects.values()))
        output = StringIO()
        call_command("import_legacy_league", owner=self.owner.username, season=2027, apply=True, stdout=output)
        ls = LeagueSeason.objects.get()
        self.assertTrue(ls.is_legacy)
        self.assertEqual(ls.start_event, self.events[0])
        self.assertEqual(ls.ruleset, "paddock")
        self.assertEqual(set(ls.entries.values_list("membership__user_id", flat=True)), {self.owner.pk, self.player.pk})
        prediction.refresh_from_db();score.refresh_from_db()
        self.assertTrue(prediction.crazy_prediction_approved)
        self.assertEqual(score.points, 35)
        self.assertEqual(before, (list(Prediction.objects.values()), list(Score.objects.values())))
        Prediction.objects.create(event=self.events[1], user=self.other)
        again, created = import_legacy_league(owner=self.owner, season_year=2027)
        self.assertEqual(again.pk, ls.pk);self.assertFalse(created)
        self.assertFalse(ls.entries.filter(membership__user=self.other).exists())
        call_command("import_legacy_league", owner=self.owner.username, season=2027, apply=True, stdout=output)
        self.assertIn("Изменений нет", output.getvalue())
        with self.assertRaises(CommandError):
            call_command("import_legacy_league", owner=self.other.username, season=2027, apply=True, stdout=StringIO())

    def test_legacy_import_errors_and_unknown_owner_never_create_partial_leagues(self):
        empty = Season.objects.create(year=2028)
        for owner, season in [("missing", 2027), (self.owner.username, 2099), (self.owner.username, empty.year)]:
            with self.assertRaises(CommandError):
                call_command("import_legacy_league", owner=owner, season=season, apply=True, stdout=StringIO())
        with self.assertRaises(ValidationError):
            import_legacy_league(owner=self.owner, season_year=2027, name=" ")
        self.assertFalse(League.objects.exists())

    def test_legacy_import_supports_next_season_without_duplicate_group(self):
        original, _ = import_legacy_league(owner=self.owner, season_year=2027)
        next_season = Season.objects.create(year=2028)
        Event.objects.create(name="Next season", season_year=next_season.year, round_number=1, deadline=self.now+timedelta(days=200))
        new, created = import_legacy_league(owner=self.owner, season_year=2028)
        self.assertTrue(created)
        self.assertEqual(new.league_id, original.league_id)
        self.assertEqual(League.objects.count(), 1)
        self.assertEqual(LeagueSeason.objects.count(), 2)
