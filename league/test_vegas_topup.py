import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import vegas_topup as topup
from .leagues import create_league, enroll_member
from .models import (Event, LeagueActivity, RaceCalendarRound, Season,
                     VegasLabWallet, VegasTopupClaim)


@override_settings(VEGAS_LAB_MIN_INTERVAL=0, STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class VegasTopupTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.owner = User.objects.create_user("topup-owner")  # No site-wide staff permission.
        self.other_owner = User.objects.create_user("topup-other-owner")
        self.player = User.objects.create_user("topup-player", is_staff=True)
        self.other = User.objects.create_user("topup-other", is_staff=True)
        self.season = Season.objects.create(year=2088)
        self.event = Event.objects.create(name="Test Vegas", season_year=2088, round_number=1,
            deadline=self.now+timedelta(days=1), race_datetime=self.now+timedelta(days=3))
        self.calendar = RaceCalendarRound.objects.create(season_year=2088, round_number=1,
            circuit="vegas", title="Test Vegas", location="Test", country="Test", circuit_name="Test",
            starts_on=self.now.date(), ends_on=(self.now+timedelta(days=4)).date(),
            practice1_at=self.now+timedelta(days=2), race_at=self.event.race_datetime,
            prediction_event=self.event)
        self.a = create_league(owner=self.owner, name="Topup Alpha", season=self.season, start_event=self.event, ruleset="paddock")
        self.b = create_league(owner=self.other_owner, name="Topup Beta", season=self.season, start_event=self.event, ruleset="paddock")
        self.entry = enroll_member(actor=self.owner, league_season=self.a, user=self.player)
        enroll_member(actor=self.other_owner, league_season=self.b, user=self.player)
        enroll_member(actor=self.owner, league_season=self.a, user=self.other)
        self.wallet = VegasLabWallet.objects.create(user=self.player, balance=99999)
        self.client.force_login(self.player)
        self.round_patch = patch("league.vegas_topup.current_round", side_effect=lambda now:
            RaceCalendarRound.objects.select_related("prediction_event").get(pk=self.calendar.pk))
        self.round_patch.start()
        self.addCleanup(self.round_patch.stop)

    def activate(self, task="ban", league=None, **changes):
        data = {"league_id": str((league or self.a).league_id), "event_id": self.event.pk, "task": task, **changes}
        return self.client.post(reverse("league:vegas_topup_activate"), json.dumps(data), content_type="application/json")

    def action(self, claim, action="submit", **data):
        return self.client.post(reverse("league:vegas_topup_"+action, args=[claim.pk]), json.dumps(data), content_type="application/json")

    def claim(self):
        response = self.activate()
        self.assertEqual(response.status_code, 200)
        return VegasTopupClaim.objects.get(user=self.player)

    def submitted(self):
        claim = self.claim()
        self.assertEqual(self.action(claim, note="Показал мем участнику лиги.").status_code, 200)
        return claim

    def approve(self, claim, actor=None, approved=True):
        return topup.review(actor=actor or self.owner, league_id=claim.league_season.league_id,
                            event_id=claim.event_id, claim_id=claim.pk, approved=approved)

    def test_strict_threshold_and_server_reward(self):
        self.wallet.balance = 100000
        self.wallet.save()
        self.assertEqual(self.activate().status_code, 400)
        self.wallet.balance = 99999
        self.wallet.save()
        claim = self.submitted()
        self.approve(claim)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 599999)
        self.assertEqual(self.wallet.revision, 1)

    def test_one_active_task_even_across_leagues(self):
        self.claim()
        self.assertEqual(self.activate("meme", league=self.b).status_code, 400)
        self.assertEqual(VegasTopupClaim.objects.filter(user=self.player).count(), 1)

    def test_activation_submit_and_approval_retries_are_idempotent(self):
        claim = self.submitted()
        self.assertEqual(self.activate().status_code, 200)
        self.assertEqual(self.action(claim).status_code, 200)
        self.approve(claim)
        self.approve(claim)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 599999)
        self.assertEqual(LeagueActivity.objects.filter(action="vegas_topup_reviewed").count(), 1)

    def test_second_task_requires_low_balance_again_and_no_repeated_reward(self):
        claim = self.submitted()
        self.approve(claim)
        self.assertEqual(self.activate("meme").status_code, 400)
        VegasLabWallet.objects.filter(pk=self.wallet.pk).update(balance=500)
        self.assertEqual(self.activate("meme").status_code, 200)
        second = VegasTopupClaim.objects.get(user=self.player, task="meme")
        self.action(second)
        self.approve(second)
        self.assertEqual(self.activate("ban", league=self.b).status_code, 400)
        self.assertEqual(self.activate("meme", league=self.b).status_code, 400)

    def test_cancel_allows_switching_but_does_not_credit(self):
        claim = self.claim()
        self.assertEqual(self.action(claim, "cancel").status_code, 200)
        self.assertEqual(self.activate("meme").status_code, 200)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 99999)

    def test_reject_does_not_credit_and_cannot_later_approve_same_claim(self):
        claim = self.submitted()
        self.approve(claim, approved=False)
        with self.assertRaises(ValidationError):
            self.approve(claim)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 99999)

    def test_only_selected_league_owner_can_review_not_platform_staff(self):
        claim = self.submitted()
        for actor in (self.other, self.player, self.other_owner):
            with self.subTest(actor=actor.username), self.assertRaises(PermissionDenied):
                self.approve(claim, actor=actor)
        self.approve(claim)  # A non-staff league owner can approve.

    def test_admin_cannot_approve_own_task(self):
        self.a.league.owner = self.player
        self.a.league.save(update_fields=["owner"])
        claim = self.submitted()
        with self.assertRaises(PermissionDenied):
            self.approve(claim, actor=self.player)

    def test_owner_cannot_approve_unsubmitted_claim(self):
        claim = self.claim()
        with self.assertRaises(ValidationError):
            self.approve(claim)

    def test_live_fp1_deadline_blocks_activation_submission_and_credit(self):
        claim = self.submitted()
        RaceCalendarRound.objects.filter(pk=self.calendar.pk).update(practice1_at=self.now)
        self.assertEqual(self.activate("meme").status_code, 400)
        self.assertEqual(self.action(claim).status_code, 400)
        with self.assertRaises(ValidationError):
            self.approve(claim)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 99999)

    def test_missing_practice_time_fails_closed(self):
        RaceCalendarRound.objects.filter(pk=self.calendar.pk).update(practice1_at=None)
        self.assertEqual(self.activate().status_code, 400)

    def test_free_spins_and_unlimited_admin_cannot_activate(self):
        VegasLabWallet.objects.filter(pk=self.wallet.pk).update(free_spins=1)
        self.assertEqual(self.activate().status_code, 400)
        VegasLabWallet.objects.filter(pk=self.wallet.pk).update(free_spins=0)
        self.player.is_superuser = True
        self.player.save(update_fields=["is_superuser"])
        self.assertEqual(self.activate().status_code, 400)

    def test_invalid_or_forged_inputs_do_not_credit(self):
        for data in ({"event_id": self.event.pk+999}, {"event_id": True}, {"task": "cheat"},
                     {"league_id": "bad"}, {"amount": 999999}, {"balance": 0}):
            with self.subTest(data=data):
                self.assertEqual(self.activate(**data).status_code, 400)
        self.assertFalse(VegasTopupClaim.objects.exists())

    def test_claim_id_is_not_authorization(self):
        claim = self.claim()
        self.client.force_login(self.other)
        self.assertEqual(self.action(claim).status_code, 404)
        self.client.force_login(self.other_owner)
        url = reverse("league:vegas_topup_review", args=[self.b.league_id, self.event.pk, claim.pk])
        self.assertEqual(self.client.post(url, {"decision": "approve"}).status_code, 404)

    def test_review_requires_live_membership(self):
        claim = self.submitted()
        self.entry.membership.is_active = False
        self.entry.membership.save(update_fields=["is_active"])
        with self.assertRaises(ValidationError):
            self.approve(claim)

    def test_credit_after_balance_changes_and_cached_spin_retry(self):
        spin = {"request_id": str(uuid.uuid4()), "revision": 0, "bet": 5000}
        with patch("league.vegas_rules.outcome", return_value={"payout": 0, "awarded": 0}):
            self.client.post(reverse("league:vegas_lab_spin"), json.dumps(spin), content_type="application/json")
        claim = self.submitted()
        self.approve(claim)
        retry = self.client.post(reverse("league:vegas_lab_spin"), json.dumps(spin), content_type="application/json")
        self.assertEqual(retry.json()["state"]["balance"], 594999)
        self.assertEqual(retry.json()["state"]["revision"], 2)
        spin["request_id"] = str(uuid.uuid4())
        self.assertEqual(self.client.post(reverse("league:vegas_lab_spin"), json.dumps(spin), content_type="application/json").status_code, 409)

    def test_database_constraints_prevent_two_open_tasks_and_duplicate_awards(self):
        claim = self.claim()
        for task in ("ban", "meme"):
            with self.subTest(task=task), self.assertRaises(IntegrityError), transaction.atomic():
                VegasTopupClaim.objects.create(user=self.player, event=self.event, task=task,
                    league_season=self.b, expires_at=claim.expires_at)

    def test_status_is_read_only_and_management_shows_pending_before_prediction_deadline(self):
        claim = self.submitted()
        before = self.wallet.balance
        for _ in range(2):
            response = self.client.get(reverse("league:vegas_topup_status"))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["topup"]["active"]["status"], "review")
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, before)
        self.client.force_login(self.owner)
        url = reverse("league:friend_league_event", args=[self.a.league_id, self.event.pk])+"?manage=1"
        self.assertContains(self.client.get(url), "Засчитать +5 000")
        self.assertContains(self.client.get(url), "Показал мем участнику лиги.")
        review_url = reverse("league:vegas_topup_review", args=[self.a.league_id, self.event.pk, claim.pk])
        self.assertEqual(self.client.post(review_url, {"decision": "approve", "amount": 9000000}).status_code, 302)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, 599999)

    def test_no_new_public_access_and_csrf_remains_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.player)
        self.assertEqual(client.post(reverse("league:vegas_topup_activate"), "{}", content_type="application/json").status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("league:vegas_topup_status")).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("league:vegas_topup_status")).status_code, 302)
