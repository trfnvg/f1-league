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
        for changes in ({"balance": 999999}, {"bet": -5000}, {"bet": True}, {"bet": 1}, {"bet": 501},
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
