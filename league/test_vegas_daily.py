import json
from datetime import timedelta
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import ArcadeSettings, VegasDailyGrant, VegasWallet
from . import test_vegas_release as release_tests
from .vegas_daily import MOSCOW


@override_settings(VEGAS_LAB_MIN_INTERVAL=0, STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class VegasDailyTests(TestCase):
    setUp = release_tests.VegasReleaseTests.setUp

    def wallet(self, **fields):
        self.client.get(self.page)
        wallet = VegasWallet.objects.get(user=self.user, competition=self.contest)
        VegasWallet.objects.filter(pk=wallet.pk).update(**fields)
        wallet.refresh_from_db()
        return wallet

    def claim(self, wallet_id, **extra):
        return self.client.post(reverse("league:vegas_daily"),
            json.dumps({"wallet_id": wallet_id, **extra}), content_type="application/json")

    def test_threshold_is_strict_and_failed_attempt_does_not_consume_day(self):
        wallet = self.wallet(balance=10000)
        self.assertEqual(self.claim(wallet.pk).status_code, 400)
        self.assertFalse(VegasDailyGrant.objects.exists())
        VegasWallet.objects.filter(pk=wallet.pk).update(balance=9999)
        data = self.claim(wallet.pk).json()
        self.assertEqual(data["state"]["balance"], 309999)
        self.assertEqual(data["state"]["revision"], 1)
        self.assertTrue(data["claimed"])
        self.assertFalse(data["can_claim"])

    def test_retry_and_second_tab_never_credit_twice_even_if_balance_is_low_again(self):
        wallet = self.wallet(balance=0, last_payload={"state": {"bonus": {"win": 0, "played": 0, "granted": 0}}})
        self.assertEqual(self.claim(wallet.pk).json()["state"]["balance"], 300000)
        self.assertEqual(self.claim(wallet.pk).json()["state"]["balance"], 300000)
        wallet.refresh_from_db()
        self.assertEqual(wallet.last_payload["state"]["balance"], 300000)
        VegasWallet.objects.filter(pk=wallet.pk).update(balance=0)
        self.assertEqual(self.claim(wallet.pk).json()["state"]["balance"], 0)
        self.assertEqual(VegasDailyGrant.objects.count(), 1)

    def test_reset_at_moscow_midnight_not_24_hours_later(self):
        before = self.now.astimezone(MOSCOW).replace(hour=23, minute=59, second=59, microsecond=0)
        self.event.deadline = before+timedelta(days=2)
        self.event.save(update_fields=["deadline"])
        wallet = self.wallet(balance=0)
        with patch("django.utils.timezone.now", return_value=before):
            first = self.claim(wallet.pk).json()
        self.assertTrue(first["resets_at"].endswith("T00:00:00+03:00"))
        VegasWallet.objects.filter(pk=wallet.pk).update(balance=0)
        with patch("django.utils.timezone.now", return_value=before+timedelta(seconds=1)):
            second = self.claim(wallet.pk).json()
        self.assertEqual(second["state"]["balance"], 300000)
        self.assertEqual(VegasDailyGrant.objects.count(), 2)

    def test_closed_contest_and_active_bonus_cannot_claim(self):
        wallet = self.wallet(balance=0, free_spins=1)
        self.assertEqual(self.claim(wallet.pk).status_code, 400)
        VegasWallet.objects.filter(pk=wallet.pk).update(free_spins=0)
        with patch("django.utils.timezone.now", return_value=self.event.deadline):
            self.assertEqual(self.claim(wallet.pk).status_code, 403)
        self.assertFalse(VegasDailyGrant.objects.exists())

    def test_practice_and_event_cannot_each_claim_on_the_same_day(self):
        wallet = self.wallet(balance=0)
        self.claim(wallet.pk)
        ArcadeSettings.objects.filter(pk=1).update(competition_event=None, competition_opened_at=None)
        self.client.get(self.page)
        practice = VegasWallet.objects.get(user=self.user, competition=None)
        VegasWallet.objects.filter(pk=practice.pk).update(balance=0)
        self.assertEqual(self.claim(practice.pk).json()["state"]["balance"], 0)
        self.assertEqual(VegasDailyGrant.objects.count(), 1)

    def test_wallet_spoof_amount_and_csrf_rejected(self):
        wallet = self.wallet(balance=0)
        for key in (True, wallet.pk+1, 1.5):
            self.assertEqual(self.claim(key).status_code, 400)
        self.assertEqual(self.claim(wallet.pk, amount=999999).status_code, 400)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse("league:vegas_daily"), json.dumps({"wallet_id": wallet.pk}), content_type="application/json").status_code, 403)
        self.assertFalse(VegasDailyGrant.objects.exists())

    def test_status_get_is_read_only_and_anonymous_redirects(self):
        wallet = self.wallet(balance=1)
        response = self.client.get(reverse("league:vegas_daily"))
        self.assertTrue(response.json()["can_claim"])
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 1)
        self.assertFalse(VegasDailyGrant.objects.exists())
        self.client.logout()
        self.assertEqual(self.claim(wallet.pk).status_code, 302)
