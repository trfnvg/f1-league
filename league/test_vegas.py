import json
import uuid
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, Client, override_settings
from django.urls import reverse

from . import vegas_rules as rules
from .models import VegasLabWallet, Score, ArcadeWheelSpin, TetrisRecord


def empty_grid():
    return [["scatter"] * 4 for _ in range(5)]


class VegasRulesTests(SimpleTestCase):
    def test_forty_unique_reachable_lines(self):
        self.assertEqual(len(rules.PAYLINES), 40)
        self.assertEqual(len(set(rules.PAYLINES)), 40)
        for line in rules.PAYLINES:
            self.assertEqual(len(line), 5)
            self.assertTrue(all(0 <= row < 4 for row in line))
        self.assertTrue(all((row,)*5 in rules.PAYLINES for row in range(4)))

    def test_left_to_right_minimum_three_and_exact_cells(self):
        grid = empty_grid()
        for col in (1, 2, 3, 4):
            grid[col][0] = "banana"
        self.assertFalse(rules.evaluate(grid, 5000))
        grid[0][0] = "banana"
        wins = rules.evaluate(grid, 5000)
        first = next(win for win in wins if win["line"] == 1)
        self.assertEqual(first["count"], 5)
        self.assertEqual(first["amount"], 5000*rules.BY_KEY["banana"]["pays"][2]//40)
        self.assertEqual(first["cells"], [[col, 0] for col in range(5)])

    def test_wild_substitution_and_one_best_payment_per_line(self):
        grid = empty_grid()
        for col, value in enumerate(("wild", "banana", "wild", "banana", "banana")):
            grid[col][0] = value
        wins = rules.evaluate(grid, 5000)
        first = next(win for win in wins if win["line"] == 1)
        self.assertEqual((first["symbol"], first["count"]), ("banana", 5))
        self.assertEqual(len({win["line"] for win in wins}), len(wins))

    def test_scatters_are_not_line_wins(self):
        self.assertEqual(rules.evaluate(empty_grid(), 5000), [])

    def test_all_wild_uses_best_interpretation(self):
        wins = rules.evaluate([["wild"]*4 for _ in range(5)], 5000)
        self.assertEqual(len(wins), 40)
        self.assertTrue(all(win["symbol"] == "wild" for win in wins))

    def test_cascades_have_hard_cost_bound_and_server_totals(self):
        result = rules.outcome(5000, choice=lambda _: "banana")
        self.assertEqual(len(result["rounds"]), 6)
        self.assertTrue(result["cascade_limit"])
        self.assertEqual(result["payout"], sum(r["amount"] for r in result["rounds"]))
        self.assertEqual([r["multiplier"] for r in result["rounds"]], [1,2,3,4,5,6])
        free = rules.outcome(5000, free=True, choice=lambda _: "banana")
        self.assertEqual(free["payout"], 2*result["payout"])

    def test_scatter_bonus_and_retrigger(self):
        normal = rules.outcome(5000, choice=lambda _: "scatter")
        free = rules.outcome(5000, free=True, choice=lambda _: "scatter")
        self.assertEqual((normal["awarded"], free["awarded"]), (12, 4))
        self.assertEqual(normal["payout"], 0)

    def test_three_debug_scatters_award_eight(self):
        result = rules.outcome(5000, scenario="bonus", choice=lambda _: "tyre")
        self.assertGreaterEqual(result["scatters"], 3)
        self.assertGreaterEqual(result["awarded"], 8)

    def test_purchase_entry_has_exactly_three_scatters(self):
        grid = rules.bonus_buy_grid(choice=lambda values: values[-1])
        self.assertEqual(len(grid), 5)
        self.assertTrue(all(len(col) == 4 for col in grid))
        self.assertEqual(sum(col.count("scatter") for col in grid), 3)
        self.assertEqual(rules.evaluate(grid, 5000), [])


@override_settings(VEGAS_LAB_MIN_INTERVAL=0, STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class VegasLabTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("vegas-admin", is_staff=True)
        self.player = User.objects.create_user("vegas-player")
        self.client.force_login(self.staff)
        self.page = reverse("league:vegas_lab")
        self.url = reverse("league:vegas_lab_spin")
        self.client.get(self.page)

    def payload(self, **kwargs):
        wallet = VegasLabWallet.objects.get(user=self.staff)
        return {"request_id": str(uuid.uuid4()), "revision": wallet.revision, "bet": 5000, **kwargs}

    def post(self, data):
        return self.client.post(self.url, json.dumps(data), content_type="application/json")

    def enable_unlimited_admin(self):
        self.staff.is_superuser = True
        self.staff.save(update_fields=["is_superuser"])
        VegasLabWallet.objects.filter(user=self.staff).update(balance=0)

    def test_unlimited_admin_can_spin_at_zero_without_changing_wallet(self):
        self.assertFalse(self.client.get(self.page).context["vegas_config"]["unlimited_balance"])
        self.enable_unlimited_admin()
        self.assertTrue(self.client.get(self.page).context["vegas_config"]["unlimited_balance"])
        for payout in (0, 123456):
            with self.subTest(payout=payout):
                payload = self.payload(bet=max(rules.BETS))
                with patch("league.vegas_rules.outcome", return_value={"payout": payout, "awarded": 0}) as outcome:
                    response = self.post(payload)
                    self.assertEqual(response.status_code, 200)
                    data = response.json()
                    self.assertEqual(data["state"]["balance"], 0)
                    self.assertEqual(data["result"]["payout"], payout)
                    self.assertEqual(self.post(payload).json(), data)
                    outcome.assert_called_once()
        self.assertEqual(VegasLabWallet.objects.get(user=self.staff).balance, 0)

    def test_unlimited_admin_bonus_at_zero_keeps_totals_and_retry_safety(self):
        self.enable_unlimited_admin()
        payload = self.payload(action="buy_bonus", bet=max(rules.BETS))
        bought = self.post(payload)
        self.assertEqual(bought.status_code, 200)
        self.assertEqual(self.post(payload).json(), bought.json())
        self.assertEqual(bought.json()["state"]["balance"], 0)
        self.assertEqual(bought.json()["state"]["free_spins"], rules.BONUS_BUY_SPINS)
        with patch("league.vegas_rules.outcome", return_value={"payout": 12345, "awarded": 0}) as outcome:
            data = self.post(self.payload()).json()
        outcome.assert_called_once_with(max(rules.BETS), free=True, scenario="random")
        self.assertEqual(data["state"]["balance"], 0)
        self.assertEqual(data["state"]["bonus"], {"win": 12345, "played": 1, "granted": rules.BONUS_BUY_SPINS})

    def test_unlimited_admin_is_not_ranked_and_shop_remains_read_only(self):
        self.enable_unlimited_admin()
        VegasLabWallet.objects.filter(user=self.staff).update(balance=99999999)
        VegasLabWallet.objects.create(user=self.player, balance=1000)
        data = self.client.get(reverse("league:vegas_lab_balances")).json()
        self.assertEqual([p["id"] for p in data["players"]], [self.player.pk])
        self.assertEqual(data["players"][0]["rank"], 1)
        response = self.client.get(reverse("league:vegas_lab_shop"))
        self.assertTrue(response.context["shop_unlimited_balance"])
        self.assertEqual(VegasLabWallet.objects.get(user=self.staff).balance, 99999999)

    def test_revoked_superuser_cannot_keep_unlimited_funds(self):
        self.enable_unlimited_admin()
        self.staff.is_superuser = False
        self.staff.save(update_fields=["is_superuser"])
        self.assertEqual(self.post(self.payload()).status_code, 400)
        self.assertEqual(self.post(self.payload(action="buy_bonus")).status_code, 400)
        self.assertFalse(self.client.get(self.page).context["vegas_config"]["unlimited_balance"])

    def test_staff_only_all_endpoints(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.page).status_code, 302)
        self.assertEqual(self.post(self.payload()).status_code, 302)
        self.client.force_login(self.player)
        self.assertEqual(self.client.get(self.page).status_code, 403)
        self.assertEqual(self.post(self.payload()).status_code, 403)
        self.assertFalse(VegasLabWallet.objects.filter(user=self.player).exists())

    def test_page_and_server_wallet_survive_reload(self):
        response = self.client.get(self.page)
        self.assertContains(response, 'id="vegas-machine"')
        wallet = VegasLabWallet.objects.get(user=self.staff)
        wallet.balance = 12345
        wallet.save()
        self.assertEqual(self.client.get(self.page).context["vegas_config"]["state"]["balance"], 12345)

    def test_balance_board_is_live_read_only_and_staff_only(self):
        url = reverse("league:vegas_lab_balances")
        rival = User.objects.create_user("vegas-rival", first_name="Друг")
        wallet = VegasLabWallet.objects.create(user=rival, balance=750000)
        data = self.client.get(url).json()
        self.assertEqual(data["players"][0], {"id": rival.pk, "name": "Друг", "balance": 750000, "rank": 1, "is_you": False})
        self.assertEqual(data["own_balance"], rules.START_BALANCE)
        wallet.balance = 120000
        wallet.save(update_fields=["balance"])
        self.assertEqual(self.client.get(url).json()["players"][1]["balance"], 120000)
        self.assertFalse(VegasLabWallet.objects.filter(user=self.player).exists())
        self.assertEqual(self.client.post(url).status_code, 405)
        self.client.force_login(self.player)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_balance_board_pages_ties_and_hides_inactive_accounts(self):
        for i in range(53):
            user = User.objects.create_user(f"wallet-{i:02d}", is_active=i != 0)
            VegasLabWallet.objects.create(user=user, balance=1000)
        url = reverse("league:vegas_lab_balances")
        first = self.client.get(url).json()
        second = self.client.get(url, {"offset": first["next_offset"]}).json()
        self.assertEqual(len(first["players"]), 50)
        self.assertEqual(len(second["players"]), 3)
        self.assertIsNone(second["next_offset"])
        self.assertFalse(set(p["id"] for p in first["players"]) & set(p["id"] for p in second["players"]))
        self.assertEqual(second["players"][0]["rank"], 51)
        self.assertEqual(self.client.get(url, {"offset": "bad"}).json()["players"], first["players"])

    def test_shop_is_read_only_and_keeps_server_balance(self):
        shop = reverse("league:vegas_lab_shop")
        before = VegasLabWallet.objects.get(user=self.staff)
        response = self.client.get(shop)
        self.assertContains(response, 'id="shop-product-dialog"')
        self.assertEqual(len(response.context["products"]), 5)
        self.assertEqual(response.context["shop_balance"], before.balance)
        after = VegasLabWallet.objects.get(user=self.staff)
        self.assertEqual((after.balance, after.revision, after.last_payload),
                         (before.balance, before.revision, before.last_payload))
        self.assertEqual(self.client.post(shop).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.get(shop).status_code, 302)
        self.client.force_login(self.player)
        self.assertEqual(self.client.get(shop).status_code, 403)

    def test_shop_does_not_create_wallet_on_direct_visit(self):
        VegasLabWallet.objects.filter(user=self.staff).delete()
        response = self.client.get(reverse("league:vegas_lab_shop"))
        self.assertEqual(response.context["shop_balance"], rules.START_BALANCE)
        self.assertFalse(VegasLabWallet.objects.filter(user=self.staff).exists())

    def test_expanded_stakes_charge_the_selected_amount(self):
        config = self.client.get(self.page).context["vegas_config"]
        self.assertEqual(config["default_bet"], 5000)
        self.assertEqual((min(config["bets"]), max(config["bets"])), (500, 50000))
        self.assertGreater(len(config["bets"]), 3)
        with patch("league.vegas_rules.outcome", return_value={"payout": 0, "awarded": 0}) as outcome:
            for bet in config["bets"]:
                with self.subTest(bet=bet):
                    VegasLabWallet.objects.filter(user=self.staff).update(balance=rules.START_BALANCE)
                    response = self.post(self.payload(bet=bet))
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json()["state"]["balance"], rules.START_BALANCE-bet)
                    outcome.assert_called_with(bet, free=False, scenario="random")

    def test_real_outcome_matches_balance_and_idempotent_retry(self):
        data = self.payload()
        response = self.post(data)
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["state"]["balance"], rules.START_BALANCE-5000+result["result"]["payout"])
        self.assertEqual(self.post(data).json(), result)
        self.assertEqual(VegasLabWallet.objects.get(user=self.staff).revision, 1)

    def test_old_tab_revision_does_not_spend_again(self):
        data = self.payload()
        self.assertEqual(self.post(data).status_code, 200)
        data["request_id"] = str(uuid.uuid4())
        self.assertEqual(self.post(data).status_code, 409)
        self.assertEqual(VegasLabWallet.objects.get(user=self.staff).revision, 1)

    def test_invalid_client_money_and_bets_rejected(self):
        for changes in ({"balance": 999999}, {"unlimited_balance": True}, {"bet": -5000}, {"bet": True}, {"bet": 1}, {"bet": 501},
                        {"revision": True}, {"request_id": "bad"}, {"scenario": "cheat"}):
            with self.subTest(changes=changes):
                self.assertEqual(self.post(self.payload(**changes)).status_code, 400)
        self.assertEqual(VegasLabWallet.objects.get(user=self.staff).balance, rules.START_BALANCE)

    def test_no_credit_when_broke_and_reset_is_sandbox_only(self):
        wallet = VegasLabWallet.objects.get(user=self.staff)
        wallet.balance = 0
        wallet.save()
        self.assertEqual(self.post(self.payload()).status_code, 400)
        reset = self.post(self.payload(action="reset")).json()["state"]
        self.assertEqual(reset["balance"], rules.START_BALANCE)
        self.assertEqual(reset["bonus_bet"], 5000)
        self.assertFalse(Score.objects.exists())
        self.assertFalse(ArcadeWheelSpin.objects.exists())
        self.assertFalse(TetrisRecord.objects.exists())

    def test_free_spin_locks_bet_does_not_charge_and_caps_retrigger(self):
        wallet = VegasLabWallet.objects.get(user=self.staff)
        wallet.balance, wallet.free_spins, wallet.bonus_bet = 0, 30, 2500
        wallet.save()
        fake = rules.outcome(2500, free=True, choice=lambda _: "scatter")
        with patch("league.vegas_rules.outcome", return_value=fake) as outcome:
            response = self.post(self.payload(bet=10000))
        outcome.assert_called_once_with(2500, free=True, scenario="random")
        self.assertEqual(response.json()["state"]["balance"], 0)
        self.assertEqual(response.json()["state"]["free_spins"], 30)

    def test_debug_bonus_is_available_only_in_staff_sandbox(self):
        result = self.post(self.payload(scenario="bonus")).json()
        self.assertGreaterEqual(result["state"]["free_spins"], 8)
        self.assertEqual(result["result"]["scenario"], "bonus")

    def test_buy_bonus_debits_cost_and_locks_ten_free_spins(self):
        with patch("league.vegas_rules.outcome") as outcome:
            response = self.post(self.payload(action="buy_bonus", bet=7500))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["state"], {"balance": rules.START_BALANCE-150000,
                         "revision": 1, "free_spins": 10, "bonus_bet": 7500,
                         "bonus": {"win": 0, "played": 0, "granted": 10}})
        self.assertIsNone(data["result"])
        self.assertEqual(data["bonus_purchase"]["cost"], 150000)
        self.assertEqual(data["bonus_purchase"]["spins"], 10)
        outcome.assert_not_called()  # Purchase is not an additional paid spin.

    def test_purchase_retry_is_idempotent_and_survives_reload(self):
        payload = self.payload(action="buy_bonus")
        first = self.post(payload).json()
        self.assertEqual(self.post(payload).json(), first)
        wallet = VegasLabWallet.objects.get(user=self.staff)
        self.assertEqual(wallet.revision, 1)
        self.assertEqual(wallet.balance, rules.START_BALANCE-100000)
        config = self.client.get(self.page).context["vegas_config"]
        self.assertEqual(config["state"]["free_spins"], 10)
        self.assertEqual(config["last_purchase"], first["bonus_purchase"])
        payload["request_id"] = str(uuid.uuid4())
        self.assertEqual(self.post(payload).status_code, 409)

    def test_purchase_requires_funds_and_no_existing_bonus(self):
        for balance, spins in ((99999, 0), (rules.START_BALANCE, 3)):
            with self.subTest(balance=balance, spins=spins):
                VegasLabWallet.objects.filter(user=self.staff).update(balance=balance, free_spins=spins)
                self.assertEqual(self.post(self.payload(action="buy_bonus")).status_code, 400)
                wallet = VegasLabWallet.objects.get(user=self.staff)
                self.assertEqual((wallet.balance, wallet.free_spins, wallet.revision), (balance, spins, 0))

    def test_purchase_rejects_client_price_and_forced_scenario(self):
        for fields in ({"cost": 0}, {"spins": 100}, {"scenario": "bonus"}, {"bet": 501}):
            with self.subTest(fields=fields):
                self.assertEqual(self.post(self.payload(action="buy_bonus", **fields)).status_code, 400)
        self.assertEqual(VegasLabWallet.objects.get(user=self.staff).balance, rules.START_BALANCE)

    def test_purchase_can_spend_exact_balance_then_free_spins_cost_nothing(self):
        VegasLabWallet.objects.filter(user=self.staff).update(balance=100000)
        self.assertEqual(self.post(self.payload(action="buy_bonus")).json()["state"]["balance"], 0)
        with patch("league.vegas_rules.outcome", return_value={"payout": 0, "awarded": 0}) as outcome:
            data = self.post(self.payload(bet=50000)).json()
        outcome.assert_called_once_with(5000, free=True, scenario="random")
        self.assertEqual((data["state"]["balance"], data["state"]["free_spins"]), (0, 9))

    def test_bonus_total_tracks_all_ten_spins_without_recounting_retries(self):
        self.post(self.payload(action="buy_bonus"))
        total = 0
        for n in range(1, 11):
            payout = n*123
            payload = self.payload()
            with patch("league.vegas_rules.outcome", return_value={"payout": payout, "awarded": 0}):
                response = self.post(payload).json()
            total += payout
            self.assertEqual(response["state"]["bonus"], {"win": total, "played": n, "granted": 10})
            self.assertEqual(response["state"]["free_spins"], 10-n)
            self.assertEqual(self.post(payload).json(), response)
            self.assertEqual(self.client.get(self.page).context["vegas_config"]["state"]["bonus"]["win"], total)
        self.assertEqual(response["state"]["balance"], rules.START_BALANCE-100000+total)

    def test_paid_trigger_payout_is_not_included_in_bonus_total(self):
        with patch("league.vegas_rules.outcome", return_value={"payout": 9000, "awarded": 8}):
            data = self.post(self.payload()).json()
        self.assertEqual(data["state"]["bonus"], {"win": 0, "played": 0, "granted": 8})
        with patch("league.vegas_rules.outcome", return_value={"payout": 1500, "awarded": 4}):
            data = self.post(self.payload()).json()
        self.assertEqual(data["state"]["bonus"], {"win": 1500, "played": 1, "granted": 12})
        self.assertEqual(data["state"]["free_spins"], 11)

    def test_retrigger_counts_only_spins_kept_by_cap(self):
        wallet = VegasLabWallet.objects.get(user=self.staff)
        wallet.free_spins = 30
        wallet.save()
        with patch("league.vegas_rules.outcome", return_value={"payout": 100, "awarded": 4}):
            data = self.post(self.payload()).json()
        self.assertEqual(data["state"]["bonus"], {"win": 100, "played": 1, "granted": 31})
        self.assertEqual(data["state"]["free_spins"], 30)

    def test_reset_and_next_series_clear_old_bonus_totals(self):
        self.post(self.payload(action="buy_bonus"))
        with patch("league.vegas_rules.outcome", return_value={"payout": 1200, "awarded": 0}):
            self.post(self.payload())
        reset = self.post(self.payload(action="reset")).json()
        self.assertEqual(reset["state"]["bonus"], {"win": 0, "played": 0, "granted": 0})
        bought = self.post(self.payload(action="buy_bonus")).json()
        self.assertEqual(bought["state"]["bonus"], {"win": 0, "played": 0, "granted": 10})

    @override_settings(VEGAS_LAB_MIN_INTERVAL=60)
    def test_rate_limit_and_duplicate_retry(self):
        data = self.payload()
        self.assertEqual(self.post(data).status_code, 200)
        self.assertEqual(self.post(data).status_code, 200)
        self.assertEqual(self.post(self.payload()).status_code, 429)

    def test_csrf_is_not_disabled(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        self.assertEqual(client.post(self.url, json.dumps(self.payload()), content_type="application/json").status_code, 403)

    def test_large_json_rejected(self):
        self.assertEqual(self.post({"x": "a"*3000}).status_code, 400)
