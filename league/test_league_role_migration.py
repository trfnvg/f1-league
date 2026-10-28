from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class RetireManagerMigrationTests(TransactionTestCase):
    def test_existing_managers_are_converted_without_changing_ownership_or_entries(self):
        before = [("league", "0054_permanent_league_invite")]
        after = [("league", "0055_remove_league_manager_role")]
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(after))
        old = executor.loader.project_state(before).apps
        User = old.get_model("auth", "User")
        League = old.get_model("league", "League")
        Member = old.get_model("league", "LeagueMembership")
        owner = User.objects.create(username="migration-owner")
        deputy = User.objects.create(username="migration-manager")
        inactive = User.objects.create(username="migration-inactive")
        league = League.objects.create(name="Migration league", owner=owner)
        owner_member = Member.objects.create(league=league, user=owner, role="manager")
        deputy_member = Member.objects.create(league=league, user=deputy, role="manager")
        inactive_member = Member.objects.create(league=league, user=inactive, role="manager", is_active=False)
        season = old.get_model("league", "Season").objects.create(year=2029)
        event = old.get_model("league", "Event").objects.create(name="Monaco", season_year=2029,
            round_number=1, deadline=timezone.now()+timedelta(days=1))
        league_season = old.get_model("league", "LeagueSeason").objects.create(
            league=league, season=season, start_event=event, ruleset="paddock")
        entry = old.get_model("league", "LeagueSeasonEntry").objects.create(
            league_season=league_season, membership=deputy_member, first_event=event)
        executor = MigrationExecutor(connection)
        executor.migrate(after)
        new = executor.loader.project_state(after).apps
        members = new.get_model("league", "LeagueMembership").objects
        self.assertEqual(members.get(pk=owner_member.pk).role, "player")
        self.assertEqual(members.get(pk=deputy_member.pk).role, "moderator")
        self.assertEqual(members.get(pk=inactive_member.pk).role, "moderator")
        self.assertFalse(members.get(pk=inactive_member.pk).is_active)
        self.assertEqual(new.get_model("league", "League").objects.get(pk=league.pk).owner_id, owner.pk)
        saved_entry = new.get_model("league", "LeagueSeasonEntry").objects.get(pk=entry.pk)
        self.assertEqual(saved_entry.first_event_id, event.pk)
        self.assertEqual(saved_entry.membership_id, deputy_member.pk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            members.filter(pk=deputy_member.pk).update(role="manager")
