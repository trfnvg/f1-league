import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .arcade_library import contest_rows, freeze
from .arcade_rewards import wheel_window_is_open
from .models import ArcadeSettings, ArcadeCompetition, Event, VegasLabWallet, VegasWallet, VegasSpin


@override_settings(VEGAS_LAB_MIN_INTERVAL=0, STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class VegasReleaseTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("vegas-racer")
        self.admin = User.objects.create_user("vegas-admin", is_staff=True, is_superuser=True)
        self.now = timezone.now()
        self.event = Event.objects.create(name="Vegas release", round_number=22, season_year=2088,
            deadline=self.now+timedelta(hours=1), race_datetime=self.now+timedelta(days=2))
        self.settings, _ = ArcadeSettings.objects.update_or_create(pk=1, defaults={
            "active_game": "vegas", "public_enabled": True, "competition_event": self.event,
            "competition_opened_at": self.now-timedelta(hours=1), "library_games": ["vegas"]})
        self.contest = ArcadeCompetition.objects.create(event=self.event, game_key="vegas",
            opened_at=self.settings.competition_opened_at)
        self.client.force_login(self.user)
        self.page = reverse("league:arcade_game", args=["vegas"])
        self.spin_url = reverse("league:vegas_public_spin")

    def spin(self, **changes):
        wallet = VegasWallet.objects.get(user=self.user, competition=self.contest)
        data = dict(request_id=str(uuid.uuid4()), revision=wallet.revision, bet=5000,
            scenario="random", action="spin", wallet_id=wallet.pk)
        data.update(changes)
        return self.client.post(self.spin_url, json.dumps(data), content_type="application/json")

    def test_release_exposes_game_without_test_tools(self):
        response = self.client.get(self.page)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="vegas-reset"')
        self.assertNotContains(response, 'id="vegas-scenario"')
        self.assertContains(response, "Vegas release")
        config = response.context["vegas_config"]
        self.assertFalse(config["unlimited_balance"])
        self.assertEqual(config["spin_url"], self.spin_url)
        self.assertEqual(self.client.get(reverse("league:vegas_lab")).status_code, 403)
        self.assertEqual(self.client.get(reverse("league:vegas_lab_shop")).status_code, 403)
        self.assertContains(self.client.get(reverse("league:vegas_public_shop")), 'id="shop-buy"')

    def test_server_rejects_every_test_scenario_and_wallet_spoof(self):
        self.client.get(self.page)
        for data in ({"action": "reset"}, {"scenario": "wild"}, {"scenario": "bonus"},
                     {"scenario": "bigwin"}, {"wallet_id": 999999}, {"balance": 99999999}):
            self.assertEqual(self.spin(**data).status_code, 400)
        self.assertFalse(VegasSpin.objects.exists())

    def test_lab_and_practice_balances_cannot_enter_competition(self):
        VegasLabWallet.objects.create(user=self.user, balance=99999999)
        VegasWallet.objects.create(user=self.user, balance=88888888)
        self.client.get(self.page)
        wallet = VegasWallet.objects.get(user=self.user, competition=self.contest)
        self.assertEqual(wallet.balance, 500000)
        self.assertEqual(contest_rows(self.contest)[0][0]["balance"], 500000)

    def test_durable_retries_never_double_debit(self):
        self.client.get(self.page)
        request_id = str(uuid.uuid4())
        first = self.spin(request_id=request_id)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(self.spin().status_code, 200)
        wallet = VegasWallet.objects.get(user=self.user, competition=self.contest)
        balance = wallet.balance
        retried = self.spin(request_id=request_id, revision=0)
        wallet.refresh_from_db()
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(retried.json()["state"]["balance"], balance)
        self.assertEqual(wallet.balance, balance)
        self.assertEqual(VegasSpin.objects.count(), 2)

    def test_bonus_minimum_is_paid_once_on_last_spin_and_recorded_on_server(self):
        self.client.get(self.page)
        self.assertEqual(self.spin(action="buy_bonus").status_code, 200)
        with patch("league.vegas_rules.outcome", side_effect=lambda *a, **kw: {
                "bet": 5000, "payout": 0, "awarded": 0}):
            for _ in range(9):
                data = self.spin().json()
                self.assertEqual(data["state"]["balance"], 400000)
                self.assertNotIn("bonus_adjustment", data["result"])
            request_id = str(uuid.uuid4())
            data = self.spin(request_id=request_id).json()
            self.assertEqual(data["state"]["balance"], 450000)
            self.assertEqual(data["state"]["bonus"]["win"], 50000)
            self.assertEqual(data["result"]["bonus_adjustment"], 50000)
            self.assertEqual(data["result"]["payout"], 50000)
            row = VegasSpin.objects.get(request_id=request_id)
            self.assertEqual(row.balance_after-row.balance_before, 50000)
            self.assertEqual(row.payload["result"]["bonus_adjustment"], 50000)
            self.assertEqual(self.spin(request_id=request_id, revision=0).json()["state"]["balance"], 450000)
            self.spin()
            self.assertEqual(self.spin(request_id=request_id, revision=0).json()["state"]["balance"], 445000)
            self.assertEqual(VegasSpin.objects.count(), 12)

    def test_old_or_natural_bonus_has_no_retroactive_purchase_floor(self):
        self.client.get(self.page)
        VegasWallet.objects.filter(user=self.user).update(free_spins=1, bonus_bet=5000,
            last_payload={"state": {"bonus": {"win": 100, "played": 9, "granted": 10}}})
        with patch("league.vegas_rules.outcome", return_value={"bet": 5000, "payout": 0, "awarded": 0}):
            data = self.spin().json()
        self.assertEqual(data["state"]["balance"], 500000)
        self.assertNotIn("bonus_adjustment", data["result"])

    def test_bonus_floor_waits_for_retrigger_and_does_not_cap_big_wins(self):
        self.client.get(self.page)
        self.spin(action="buy_bonus")
        VegasWallet.objects.filter(user=self.user).update(free_spins=1)
        with patch("league.vegas_rules.outcome", return_value={"bet": 5000, "payout": 200000, "awarded": 4}):
            data = self.spin().json()
        self.assertEqual(data["state"]["free_spins"], 4)
        self.assertNotIn("bonus_adjustment", data["result"])
        with patch("league.vegas_rules.outcome", side_effect=lambda *a, **kw: {"bet": 5000, "payout": 0, "awarded": 0}):
            for _ in range(4):
                data = self.spin().json()
        self.assertEqual(data["state"]["balance"], 600000)
        self.assertEqual(data["state"]["bonus"]["win"], 200000)
        self.assertNotIn("bonus_adjustment", data["result"])

    def test_deadline_freezes_balance_not_peak_or_total_winnings(self):
        self.client.get(self.page)
        wallet = VegasWallet.objects.get(user=self.user, competition=self.contest)
        wallet.balance = 321000
        wallet.save()
        with patch("django.utils.timezone.now", return_value=self.event.deadline):
            self.assertEqual(self.spin().status_code, 403)
            frozen = freeze(self.contest)
            self.assertEqual(frozen.standings[0]["score"], 321000)
            self.assertFalse(wheel_window_is_open(self.event))
            self.assertTrue(self.client.get(self.page).context["vegas_config"]["closed"])
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 321000)

    def test_admin_public_balance_is_finite_and_excluded_from_ranking(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.page)
        self.assertFalse(response.context["vegas_config"]["unlimited_balance"])
        self.assertEqual(contest_rows(self.contest), ([], 0))

    def test_new_event_starts_fresh_and_old_tab_cannot_spend_it(self):
        self.client.get(self.page)
        old = VegasWallet.objects.get(user=self.user, competition=self.contest)
        next_event = Event.objects.create(name="Next Vegas", season_year=2088, round_number=23,
            deadline=self.now+timedelta(days=5))
        next_contest = ArcadeCompetition.objects.create(event=next_event, game_key="vegas", opened_at=self.now)
        self.settings.competition_event = next_event
        self.settings.competition_opened_at = self.now
        self.settings.save()
        self.assertEqual(self.spin(wallet_id=old.pk).status_code, 400)
        self.assertEqual(VegasWallet.objects.get(user=self.user, competition=next_contest).balance, 500000)

    def test_signed_out_user_is_sent_to_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.page).status_code, 302)

    def test_new_participant_cannot_enter_closed_standings(self):
        with patch("django.utils.timezone.now", return_value=self.event.deadline):
            self.assertEqual(self.client.get(self.page).status_code, 403)
            self.assertFalse(VegasWallet.objects.exists())

    def test_task_credits_competition_wallet_not_laboratory(self):
        from .models import Season, RaceCalendarRound, VegasTopupClaim
        from .leagues import create_league, enroll_member
        from .vegas_topup import review
        season = Season.objects.create(year=2088)
        calendar = RaceCalendarRound.objects.create(season_year=2088, round_number=22,
            circuit="vegas", title="Vegas", location="Test", country="Test", circuit_name="Test",
            starts_on=self.now.date(), ends_on=(self.now+timedelta(days=2)).date(),
            practice1_at=self.now+timedelta(minutes=30), race_at=self.event.race_datetime,
            prediction_event=self.event)
        league = create_league(owner=self.admin, name="Vegas league", season=season,
            start_event=self.event, ruleset="paddock")
        enroll_member(actor=self.admin, league_season=league, user=self.user)
        self.client.get(self.page)
        wallet = VegasWallet.objects.get(user=self.user, competition=self.contest)
        wallet.balance = 99999
        wallet.save()
        lab = VegasLabWallet.objects.create(user=self.user, balance=123)
        response = self.client.post(reverse("league:vegas_public_topup_activate"), json.dumps({
            "league_id": str(league.league_id), "event_id": self.event.pk, "task": "meme"}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        claim = VegasTopupClaim.objects.get(user=self.user)
        self.assertEqual(claim.wallet_id, wallet.pk)
        response = self.client.post(reverse("league:vegas_public_topup_submit", args=[claim.pk]),
            json.dumps({"note": "Выполнено"}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        review(actor=self.admin, league_id=league.league_id, event_id=self.event.pk, claim_id=claim.pk, approved=True)
        wallet.refresh_from_db()
        lab.refresh_from_db()
        self.assertEqual(wallet.balance, 399999)
        self.assertEqual(lab.balance, 123)
        # Ordinary players can never use the lab API to submit public claims.
        self.assertEqual(self.client.get(reverse("league:vegas_topup_status")).status_code, 403)

    def test_admin_can_plan_vegas_without_starting_it(self):
        from .models import Season
        Season.objects.create(year=2088)
        self.client.force_login(self.admin)
        event = Event.objects.create(name="Future Vegas", season_year=2088, round_number=23,
            deadline=self.now+timedelta(days=7))
        response = self.client.post(reverse("league:arcade_control")+"?season=2088", {
            "action": "select", "competition_event": event.pk, "active_game": "vegas"})
        self.assertEqual(response.status_code, 302)
        plan = ArcadeCompetition.objects.get(event=event)
        self.assertEqual(plan.game_key, "vegas")
        self.assertIsNone(plan.opened_at)
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.competition_event_id, self.event.pk)
