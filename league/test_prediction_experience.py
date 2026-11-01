from datetime import timedelta
from types import SimpleNamespace
from django.test import TestCase, override_settings
from django.urls import reverse
from . import test_private_league_ui as fixtures
from .leagues import create_invite, accept_invite
from .models import DriverProfile, Event, Prediction, Result, Score, LeagueMembership, LeagueDayDecision
from .prediction_submission import save_shared_prediction
from .scoring import publish_event_scores
from .score_details import decorate_rows, explain


@override_settings(STORAGES=fixtures.STORAGES)
class PredictionExperienceTests(TestCase):
    setUp = fixtures.PrivateLeagueUITests.setUp

    def test_invite_guest_preview_and_registration_return(self):
        _, token = create_invite(actor=self.owner, league_season=self.a)
        url = reverse("league:friend_league_join", args=[token])
        self.client.logout()
        response = self.client.get(url)
        self.assertContains(response, "Private Alpha")
        self.assertNotContains(response, "Secret Bravo")
        self.assertContains(response, "next=" + url)
        self.assertEqual(response["Referrer-Policy"], "same-origin")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(self.client.post(url).status_code, 302)
        data = dict(first_name="Новый", username="newplayer", email="new@example.com",
            password1="StrongRacePassword!63", password2="StrongRacePassword!63", next=url)
        response = self.client.post(reverse("league:register"), data)
        self.assertRedirects(response, url)
        self.assertFalse(LeagueMembership.objects.filter(user__username="newplayer").exists())
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertTrue(LeagueMembership.objects.filter(user__username="newplayer", league=self.a.league).exists())

    def test_only_successful_submission_updates_timestamp(self):
        _, prediction = save_shared_prediction(user=self.owner, event=self.event, data=self.values)
        self.assertEqual(prediction.submitted_at, self.now)
        self.clock.return_value = self.now + timedelta(minutes=2)
        form, saved = save_shared_prediction(user=self.owner, event=self.event,
            data={**self.values, "p1": "invalid"})
        self.assertIsNone(saved)
        prediction.refresh_from_db()
        self.assertEqual(prediction.submitted_at, self.now)
        _, saved = save_shared_prediction(user=self.owner, event=self.event, data=self.values)
        self.assertEqual(saved.submitted_at, self.clock.return_value)
        response = self.client.get(reverse("league:event_detail", args=[self.event.pk]))
        self.assertContains(response, "Последнее сохранение:")

    def publish(self):
        Prediction.objects.create(user=self.owner, event=self.event, **self.values)
        self.clock.return_value = self.event.race_datetime + timedelta(hours=1)
        Result.objects.create(event=self.event, **{k:v for k,v in self.values.items() if k != "crazy_prediction"})
        with self.captureOnCommitCallbacks(execute=True):
            publish_event_scores(self.event, self.staff)

    def test_save_receipt_requires_success_and_is_consumed_once(self):
        urls = [reverse('league:event_detail', args=[self.event.pk]),
            reverse('league:friend_league_event', args=[self.a.league_id, self.event.pk])]
        for url in urls:
            invalid = self.client.post(url, {**self.values, 'p1': 'invalid'})
            self.assertNotContains(invalid, 'data-save-receipt')
            success = self.client.post(url, self.values, follow=True)
            self.assertContains(success, 'data-save-receipt', count=1)
            self.assertContains(success, 'Прогноз принят')
            self.assertNotContains(self.client.get(url), 'data-save-receipt')

    def test_details_use_saved_snapshot_and_are_membership_scoped(self):
        url = reverse("league:friend_league_score", args=[self.a.league_id, self.event.pk, self.owner.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.publish()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(sum(r["points"] for r in response.context["score_rows"]+response.context["extras"]), 40)
        self.assertNotContains(response, "<script>alert(1)</script>")
        Result.objects.filter(event=self.event).update(p1="norris")
        again = self.client.get(url)
        self.assertEqual(again.context["score_rows"], response.context["score_rows"])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_global_breakdown_total_and_predeadline_privacy(self):
        self.publish()
        score = Score.objects.get(user=self.owner, event=self.event)
        score.breakdown["Дуэль"] = -7
        score.points -= 7
        score.save()
        url = reverse("league:score_detail", args=[self.event.pk, self.owner.pk])
        response = self.client.get(url)
        self.assertEqual(sum(r["points"] for r in response.context["score_rows"]+response.context["extras"]), score.points)
        self.assertContains(response, "Дуэль")
        Event.objects.filter(pk=self.event.pk).update(deadline=self.clock.return_value+timedelta(days=1))
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_portrait_review_uses_the_scored_season_and_preserves_score(self):
        DriverProfile.objects.create(season_year=self.event.season_year, key=self.values["p1"],
            name="Джордж Рассел", surname="Рассел", team="Mercedes", number=63,
            portrait_url="https://example.invalid/russell.webp")
        self.publish()
        saved = Score.objects.get(user=self.owner, event=self.event)
        before = (saved.points, saved.breakdown)
        page = self.client.get(reverse("league:score_detail", args=[self.event.pk, self.owner.pk]))
        self.assertContains(page, "score-review.css")
        self.assertContains(page, "Прогноз игрока")
        self.assertContains(page, "Результат гонки")
        self.assertContains(page, "data-driver-photo")
        first = page.context["score_rows"][0]
        self.assertEqual(first["prediction_drivers"][0]["key"], self.values["p1"])
        self.assertTrue(first["prediction_drivers"][0]["photo"])
        self.assertEqual(page.context["base_points"] + page.context["extra_points"], saved.points)
        saved.refresh_from_db()
        self.assertEqual((saved.points, saved.breakdown), before)

    def test_portraits_support_multiple_day_winners_zero_counts_and_missing_profiles(self):
        score = SimpleNamespace(points=0, breakdown={}, input_data={
            "prediction": {"driver_of_day": "norris", "safety_car_count": 0},
            "result": {"driver_of_day_multiple": ["norris", "piastri"], "safety_car_count": 0},
        })
        rows, _ = explain(score, None, None, self.event)
        with self.assertNumQueries(1):
            decorate_rows(rows, 2026)
        day = next(row for row in rows if row["field"] == "driver_of_day")
        self.assertEqual([d["key"] for d in day["actual_drivers"]], ["norris", "piastri"])
        count = next(row for row in rows if row["field"] == "safety_car_count")
        self.assertEqual(count["prediction"], "0")
        self.assertFalse(count["prediction_drivers"])
        decorate_rows(rows, 2025)
        self.assertEqual(day["prediction_drivers"][0]["surname"], "Норрис")
        self.assertFalse(day["prediction_drivers"][0]["photo"], "Never borrow a portrait from a different season")

    def test_legacy_local_decisions_match_standings(self):
        self.publish()
        self.a.is_legacy = True
        self.a.save(update_fields=["is_legacy"])
        LeagueDayDecision.objects.create(league_season=self.a, event=self.event, drivers=["norris"], reviewed_by=self.owner)
        response = self.client.get(reverse("league:friend_league_score", args=[self.a.league_id, self.event.pk, self.owner.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["score"].points, 37)
        self.assertEqual(sum(r["points"] for r in response.context["score_rows"]+response.context["extras"]), 37)
        self.assertContains(response, "Гонщик дня в этой лиге")

    def test_top3_and_zero_are_explicit_and_missing_history_is_not_invented(self):
        score = SimpleNamespace(points=8, breakdown={"P1 (Top-3)": 3})
        rows, extras = explain(score, None, None, self.event)
        self.assertEqual(rows[0]["points"], 3)
        self.assertEqual(rows[1]["points"], 0)
        self.assertEqual(extras[0]["points"], 5)
        self.assertIn("детализация отсутствует", extras[0]["title"])
