import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .leagues import create_league, enroll_member
from .models import (ArcadeCompetition, ArcadeSettings, DuelChallenge, Event, Prediction,
    Score, Season, VegasPurchase, VegasWallet)
from .vegas_inventory import activate, payload, purchase
from .vegas_effects import apply_items


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class VegasInventoryTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        clock = patch("django.utils.timezone.now", return_value=self.now)
        self.clock = clock.start()
        self.addCleanup(clock.stop)
        self.owner, self.a, self.b, self.c = [User.objects.create_user("shop-"+key) for key in ("owner", "a", "b", "c")]
        self.season = Season.objects.create(year=2098)
        self.event = Event.objects.create(name="Shop GP", season_year=2098, round_number=1,
            deadline=self.now+timedelta(hours=1), race_datetime=self.now+timedelta(hours=4))
        self.league = create_league(owner=self.owner, name="Shop league", season=self.season,
            start_event=self.event, ruleset="paddock")
        self.other = create_league(owner=self.owner, name="Other league", season=self.season,
            start_event=self.event, ruleset="paddock")
        for user in (self.a, self.b, self.c):
            enroll_member(actor=self.owner, league_season=self.league, user=user)
            enroll_member(actor=self.owner, league_season=self.other, user=user)
            Prediction.objects.create(user=user, event=self.event, p1="norris", p2="russell", p3="leclerc")
        self.contest = ArcadeCompetition.objects.create(event=self.event, game_key="vegas", opened_at=self.now)
        ArcadeSettings.objects.update_or_create(pk=1, defaults={"active_game": "vegas", "competition_event": self.event,
            "competition_opened_at": self.now, "public_enabled": True})
        self.wallets = {user.pk: VegasWallet.objects.create(user=user, competition=self.contest, balance=10000000)
            for user in (self.a, self.b, self.c)}
        self.client.force_login(self.a)

    def buy(self, key, user=None):
        user = user or self.a
        return purchase(user=user, wallet_id=self.wallets[user.pk].pk, product=key)

    def use(self, key, user=None, target=None, league=None):
        user = user or self.a
        return activate(user=user, wallet_id=self.wallets[user.pk].pk, product=key,
            league_season_id=(league or self.league).pk, target_id=target.pk if target else None)

    def close_betting(self):
        self.clock.return_value = self.event.deadline

    def projected(self, league=None):
        scores = {(user.pk, self.event.pk): SimpleNamespace(points=20, breakdown={}) for user in (self.a, self.b, self.c)}
        apply_items(league or self.league, scores)
        return {key[0]: value.points for key, value in scores.items()}

    def test_buy_once_charges_server_price_and_retries_are_free(self):
        first = self.buy("tyres")
        second = self.buy("tyres")
        self.assertEqual((first.balance, second.balance), (9750000, 9750000))
        self.assertEqual(second.revision, 1)
        self.assertEqual(VegasPurchase.objects.count(), 1)
        self.assertEqual(VegasPurchase.objects.get().cost, 250000)
        self.assertFalse(VegasPurchase.objects.get().activated_at)

    def test_insufficient_funds_and_unknown_item(self):
        VegasWallet.objects.filter(pk=self.wallets[self.a.pk].pk).update(balance=1)
        for key in ("tyres", "invented"):
            with self.assertRaises(ValidationError):
                self.buy(key)
        self.assertFalse(VegasPurchase.objects.exists())

    def test_buy_before_deadline_apply_after_and_before_race(self):
        self.buy("tyres")
        with self.assertRaises(ValidationError):
            self.use("tyres")
        self.close_betting()
        with self.assertRaises(ValidationError):
            self.buy("wheel")
        self.use("tyres")
        self.use("tyres")
        self.assertEqual(self.projected()[self.a.pk], 21)
        self.assertEqual(self.projected(self.other)[self.a.pk], 20)
        self.assertEqual(VegasPurchase.objects.get().league_season_id, self.league.pk)
        with self.assertRaises(ValidationError):
            self.use("tyres", league=self.other)

    def test_cannot_activate_at_race_start(self):
        self.buy("tyres")
        self.clock.return_value = self.event.race_datetime
        with self.assertRaises(ValidationError):
            self.use("tyres")

    def test_unowned_item_and_other_users_wallet_are_inaccessible(self):
        response = self.client.post(reverse("league:vegas_buy"), json.dumps({"wallet_id": self.wallets[self.b.pk].pk,
            "product": "tyres"}), content_type="application/json")
        self.assertEqual(response.status_code, 404)
        self.close_betting()
        response = self.client.post(reverse("league:vegas_apply"), json.dumps({"wallet_id": self.wallets[self.a.pk].pk,
            "product": "tyres", "league_season_id": self.league.pk}), content_type="application/json")
        self.assertEqual(response.status_code, 404)

    def test_client_price_and_target_spoofing_rejected(self):
        for extras in ({"cost": 0}, {"balance": 999999999}, {"wallet_id": True}):
            data = {"wallet_id": self.wallets[self.a.pk].pk, "product": "tyres", **extras}
            self.assertEqual(self.client.post(reverse("league:vegas_buy"), json.dumps(data), content_type="application/json").status_code, 400)

    def test_target_validation_self_foreign_and_no_prediction(self):
        self.buy("wheel")
        self.close_betting()
        for target in (self.a, User.objects.create_user("outsider")):
            with self.assertRaises(ValidationError):
                self.use("wheel", target=target)
        Prediction.objects.filter(user=self.b).delete()
        with self.assertRaises(ValidationError):
            self.use("wheel", target=self.b)

    def test_csrf_is_required_for_real_purchase(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.a)
        self.assertEqual(client.post(reverse("league:vegas_buy"), json.dumps({"wallet_id": self.wallets[self.a.pk].pk,
            "product": "tyres"}), content_type="application/json").status_code, 403)
        self.assertFalse(VegasPurchase.objects.exists())

    def test_team_items_and_penalties_are_applied_once_only_in_selected_league(self):
        for key in ("wheel", "constructors", "teamorder"):
            self.buy(key)
        self.close_betting()
        for key in ("wheel", "constructors", "teamorder"):
            self.use(key, target=self.b)
        self.assertEqual(self.projected(), {self.a.pk: 23, self.b.pk: 22, self.c.pk: 20})
        self.assertEqual(self.projected(), self.projected())
        self.assertEqual(self.projected(self.other), {u.pk: 20 for u in (self.a, self.b, self.c)})

    def test_pass_blocks_all_attacks_even_if_activated_later(self):
        self.buy("wheel")
        self.buy("wheel", user=self.c)
        self.buy("paddockpass", user=self.b)
        self.close_betting()
        self.use("wheel", target=self.b)
        self.use("wheel", user=self.c, target=self.b)
        self.use("paddockpass", user=self.b)
        self.assertEqual(self.projected()[self.b.pk], 23)

    def test_mirrors_reflect_one_attack_without_recursion(self):
        self.buy("wheel")
        self.buy("wheel", user=self.c)
        self.buy("mirrors", user=self.b)
        self.buy("mirrors")
        self.close_betting()
        self.use("mirrors", user=self.b)
        self.use("mirrors")
        self.use("wheel", target=self.b)
        self.use("wheel", user=self.c, target=self.b)
        self.assertEqual(self.projected(), {self.a.pk: 17, self.b.pk: 17, self.c.pk: 20})

    def test_incompatible_items_in_either_order(self):
        for user, first, second in ((self.a, "tyres", "paddockpass"), (self.b, "paddockpass", "tyres")):
            self.buy(first, user=user)
            self.buy(second, user=user)
        self.close_betting()
        for user, first, second in ((self.a, "tyres", "paddockpass"), (self.b, "paddockpass", "tyres")):
            self.use(first, user=user)
            with self.assertRaises(ValidationError):
                self.use(second, user=user)

    def duel(self):
        self.league.is_legacy = True
        self.league.save(update_fields=["is_legacy"])
        return DuelChallenge.objects.create(event=self.event, challenger=self.a, opponent=self.b,
            status="accepted", stake=5)

    def settle(self, duel):
        duel.status = "settled"
        duel.winner = self.a
        duel.challenger_prediction_points, duel.opponent_prediction_points = 20, 19
        duel.save()

    def test_insurance_compensates_without_changing_duel_result(self):
        duel = self.duel()
        self.buy("insurance", user=self.b)
        self.close_betting()
        self.use("insurance", user=self.b)
        self.settle(duel)
        self.assertEqual(self.projected()[self.b.pk], 23)
        duel.refresh_from_db()
        self.assertEqual(duel.winner_id, self.a.pk)
        self.assertEqual(duel.opponent_prediction_points, 19)

    def test_two_red_flags_cancel_stake_only_once_and_disable_insurance(self):
        duel = self.duel()
        self.buy("redflag")
        self.buy("redflag", user=self.b)
        self.buy("insurance", user=self.b)
        self.close_betting()
        self.use("redflag")
        self.use("redflag", user=self.b)
        self.use("insurance", user=self.b)
        self.settle(duel)
        self.assertEqual(self.projected(), {self.a.pk: 15, self.b.pk: 25, self.c.pk: 20})
        duel.refresh_from_db()
        self.assertEqual(duel.status, "settled")

    def test_standings_overlay_never_changes_stored_global_score(self):
        from .league_standings import standings
        self.league.is_legacy = True
        self.league.save(update_fields=["is_legacy"])
        self.buy("tyres")
        self.close_betting()
        self.use("tyres")
        original = Score.objects.create(user=self.a, event=self.event, points=20, prediction_points=15, duel_adjustment=5)
        self.assertEqual(standings(self.league)["scores_map"][(self.a.pk, self.event.pk)].points, 21)
        original.refresh_from_db()
        self.assertEqual((original.points, original.prediction_points, original.duel_adjustment), (20, 15, 5))

    def test_status_and_shop_retain_owned_inventory_after_settings_change(self):
        self.buy("tyres")
        wallet = self.wallets[self.a.pk]
        ArcadeSettings.objects.filter(pk=1).update(competition_event=None, competition_opened_at=None)
        response = self.client.get(reverse("league:vegas_inventory"), {"wallet": wallet.pk})
        self.assertTrue(response.json()["items"]["tyres"]["owned"])
        self.assertFalse(response.json()["can_buy"])
        self.assertEqual(self.client.get(reverse("league:vegas_public_shop"), {"wallet": wallet.pk}).status_code, 200)

    def test_practice_wallet_cannot_buy(self):
        wallet = VegasWallet.objects.create(user=self.a)
        with self.assertRaises(ValidationError):
            purchase(user=self.a, wallet_id=wallet.pk, product="tyres")

    def test_activation_changes_revision_but_not_frozen_arcade_balance(self):
        wallet = self.buy("tyres")
        before = wallet.balance
        self.close_betting()
        wallet = self.use("tyres")
        self.assertEqual(wallet.balance, before)
        self.assertEqual(wallet.revision, 2)

    def test_projection_is_idempotent_even_on_same_objects(self):
        self.buy("tyres")
        self.close_betting()
        self.use("tyres")
        scores = {(self.a.pk, self.event.pk): SimpleNamespace(points=20, breakdown={})}
        apply_items(self.league, scores)
        apply_items(self.league, scores)
        self.assertEqual(scores[self.a.pk, self.event.pk].points, 21)

    def test_inventory_link_survives_deadline_even_if_game_is_not_permanent(self):
        self.buy("tyres")
        ArcadeSettings.objects.filter(pk=1).update(library_games=[])
        self.close_betting()
        response = self.client.get(reverse("league:arcade"))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["current_game"])
        self.assertContains(response, "Открыть инвентарь")
        self.assertContains(response, f'?wallet={self.wallets[self.a.pk].pk}')

    def test_imported_legacy_members_remain_eligible(self):
        from .vegas_inventory import entries_for
        self.event.round_number = 2
        self.event.save(update_fields=["round_number"])
        old = Event.objects.create(name="Historical GP", season_year=2098, round_number=1,
            deadline=self.now-timedelta(days=30))
        self.league.is_legacy, self.league.start_event = True, old
        self.league.save(update_fields=["is_legacy", "start_event"])
        self.league.entries.filter(membership__user=self.a).update(first_event=old)
        self.assertTrue(entries_for(self.a.pk, self.event).filter(league_season=self.league).exists())

    def test_new_league_score_and_explanation_include_item_but_stored_score_does_not(self):
        from .models import LeagueEventScore
        from .league_standings import standings
        self.buy("tyres")
        self.close_betting()
        self.use("tyres")
        entry = self.league.entries.get(membership__user=self.a)
        score = LeagueEventScore.objects.create(entry=entry, event=self.event,
            prediction=Prediction.objects.get(user=self.a, event=self.event), base_points=20, points=20,
            breakdown={"base": {}}, input_data={}, input_digest="test")
        self.assertEqual(standings(self.league)["scores_map"][self.a.pk, self.event.pk].points, 21)
        self.event.status = "scored"
        self.event.save(update_fields=["status"])
        response = self.client.get(reverse("league:friend_league_score", args=[self.league.league_id, self.event.pk, self.a.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Свежий комплект")
        self.assertEqual(response.context["score"].points, 21)
        score.refresh_from_db()
        self.assertEqual(score.points, 20)
