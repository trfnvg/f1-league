from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse

from . import test_private_league_ui as fixtures
from .leagues import enroll_member
from .models import CrazyReaction, Event, LeagueEventScore, Prediction, Score


@override_settings(STORAGES=fixtures.STORAGES)
class RaceSocialTests(TestCase):
    setUp = fixtures.PrivateLeagueUITests.setUp

    def prepare(self):
        entry = enroll_member(actor=self.owner, league_season=self.a, user=self.player)
        prediction = Prediction.objects.create(user=self.player, event=self.event, **self.values)
        self.clock.return_value = self.event.deadline + timedelta(hours=13)
        return entry, prediction

    def test_reaction_endpoints_are_removed_for_guests_and_members(self):
        entry, prediction = self.prepare()
        # Keep historical rows intact, but no old endpoint can modify them.
        CrazyReaction.objects.create(prediction=prediction, user=self.owner, kind="heart")
        urls = [
            f"/events/{self.event.pk}/predictions/{prediction.pk}/reactions/",
            f"/leagues/{self.a.league_id}/events/{self.event.pk}/predictions/{prediction.pk}/reactions/",
        ]
        for viewer in (self.owner, self.player, None):
            if viewer:
                self.client.force_login(viewer)
            else:
                self.client.logout()
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertEqual(self.client.post(url, {"kind": "fire"}).status_code, 404)
        self.assertEqual(CrazyReaction.objects.get().kind, "heart")
        prediction.refresh_from_db()
        self.assertEqual(prediction.crazy_prediction, self.values["crazy_prediction"])
        self.assertFalse(self.event.crazy_prediction_votes.exists())

    def test_forecasts_remain_without_reactions_or_explanatory_footer(self):
        entry, prediction = self.prepare()
        self.event.status = Event.Status.SCORED
        self.event.save(update_fields=["status"])
        Score.objects.create(event=self.event, user=self.player, points=17, breakdown={"P1":10})
        LeagueEventScore.objects.create(entry=entry, event=self.event, prediction=prediction, points=24, base_points=24)
        urls = [
            reverse("league:event_detail", args=[self.event.pk]),
            reverse("league:friend_league_event", args=[self.a.league_id,self.event.pk]),
            reverse("league:score_detail", args=[self.event.pk,self.player.pk]),
            reverse("league:friend_league_score", args=[self.a.league_id,self.event.pk,self.player.pk]),
        ]
        for url in urls:
            page = self.client.get(url)
            self.assertEqual(page.status_code, 200)
            self.assertNotContains(page, "data-reaction")
            self.assertNotContains(page, "crazy-reactions.js")
            self.assertNotContains(page, "Поставить реакцию")
            self.assertNotContains(page, "Очки взяты из сохранённого зачёта")
            self.assertNotContains(page, "Сезонные бонусы в сумму этого этапа не входят")
            self.assertNotContains(page, "<script>alert(1)</script>")
        self.assertEqual(Score.objects.get().points, 17)
        self.assertEqual(LeagueEventScore.objects.get(entry=entry).points, 24)


    def test_retired_card_urls_redirect_to_score_details_with_access_checks(self):
        entry, prediction = self.prepare()
        public = reverse("league:race_recap", args=[self.event.pk,self.player.pk])
        private = reverse("league:friend_league_recap", args=[self.a.league_id,self.event.pk,self.player.pk])
        self.assertEqual(self.client.get(public).status_code, 404)
        self.event.status = Event.Status.SCORED
        self.event.save(update_fields=["status"])
        Score.objects.create(event=self.event, user=self.player, points=17, breakdown={"P1":10})
        response = self.client.get(public)
        self.assertRedirects(response, reverse("league:score_detail", args=[self.event.pk,self.player.pk]))
        self.assertIn("no-store", response["Cache-Control"])
        detail = self.client.get(response.url)
        self.assertNotContains(detail, "Карточка итогов")
        self.assertNotContains(detail, "/recap/")
        self.assertEqual(self.client.get(private).status_code, 404)
        LeagueEventScore.objects.create(entry=entry, event=self.event, prediction=prediction, points=24, base_points=24)
        response = self.client.get(private)
        self.assertRedirects(response, reverse("league:friend_league_score", args=[self.a.league_id,self.event.pk,self.player.pk]))
        self.assertEqual(self.client.get(response.url).context["score"].points, 24)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(private).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(private).status_code, 302)
