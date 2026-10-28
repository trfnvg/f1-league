from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from . import test_private_league_ui as fixtures
from .leagues import enroll_member
from .models import CrazyReaction, DuelChallenge, Event, LeagueEventScore, Prediction, Score
from .race_recap import summary
from .reactions import summaries


@override_settings(STORAGES=fixtures.STORAGES)
class RaceSocialTests(TestCase):
    setUp = fixtures.PrivateLeagueUITests.setUp

    def prepare(self):
        entry = enroll_member(actor=self.owner, league_season=self.a, user=self.player)
        prediction = Prediction.objects.create(user=self.player, event=self.event, **self.values)
        self.clock.return_value = self.event.deadline+timedelta(hours=13)
        return entry, prediction

    def reaction_url(self, prediction, league=None):
        return reverse("league:friend_league_reaction", args=[league.league_id, prediction.event_id, prediction.pk]) if league else reverse(
            "league:crazy_reaction", args=[prediction.event_id, prediction.pk])

    def test_reactions_toggle_replace_and_never_change_scores_or_votes(self):
        entry, prediction = self.prepare()
        Score.objects.create(event=self.event, user=self.player, points=17)
        url = self.reaction_url(prediction)
        response = self.client.post(url, {"kind":"heart"}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["options"][0]["count"], 1)
        self.assertTrue(response.json()["options"][0]["selected"])
        self.client.post(url, {"kind":"fire"})
        self.assertEqual(CrazyReaction.objects.get().kind, "fire")
        self.client.post(url, {"kind":"poop"})
        self.assertEqual(CrazyReaction.objects.get().kind, "poop")
        self.client.post(url, {"kind":"poop"})
        self.assertFalse(CrazyReaction.objects.exists())
        prediction.refresh_from_db()
        self.assertFalse(prediction.crazy_prediction_approved)
        self.assertEqual(Score.objects.get().points, 17)
        self.assertFalse(self.event.crazy_prediction_votes.exists())

    def test_global_and_private_reactions_are_isolated(self):
        entry, prediction = self.prepare()
        self.client.post(self.reaction_url(prediction), {"kind":"heart"})
        self.client.post(self.reaction_url(prediction, self.a), {"kind":"fire"})
        public = summaries([prediction], self.owner)[prediction.pk]
        private = summaries([prediction], self.owner, self.a.league)[prediction.pk]
        self.assertEqual([option["count"] for option in public["options"]], [1,0,0])
        self.assertEqual([option["count"] for option in private["options"]], [0,1,0])
        self.assertEqual(self.client.post(self.reaction_url(prediction, self.b), {"kind":"poop"}).status_code, 404)
        self.assertEqual(CrazyReaction.objects.count(), 2)

    def test_private_reactions_require_paddock_and_target_entry_and_active_membership(self):
        entry, prediction = self.prepare()
        self.a.ruleset = "classic"
        self.a.save(update_fields=["ruleset"])
        url = self.reaction_url(prediction, self.a)
        self.assertEqual(self.client.post(url, {"kind":"heart"}).status_code, 404)
        self.a.ruleset = "paddock"
        self.a.save(update_fields=["ruleset"])
        entry.first_event = self.next_event
        entry.save(update_fields=["first_event"])
        self.assertEqual(self.client.post(url, {"kind":"heart"}).status_code, 404)
        entry.first_event = self.event
        entry.save(update_fields=["first_event"])
        owner_membership = self.a.entries.get(membership__user=self.owner).membership
        owner_membership.is_active = False
        owner_membership.save(update_fields=["is_active"])
        self.assertEqual(self.client.post(url, {"kind":"heart"}).status_code, 404)
        self.assertFalse(CrazyReaction.objects.exists())

    def test_counts_are_batched_not_one_query_per_prediction(self):
        entry, prediction = self.prepare()
        another = Prediction.objects.create(user=self.other, event=self.event, crazy_prediction="Another")
        CrazyReaction.objects.create(prediction=prediction, user=self.owner, kind="fire")
        with self.assertNumQueries(2):
            result = summaries([prediction, another], self.owner)
        self.assertEqual(result[prediction.pk]["options"][1]["count"], 1)
        self.assertEqual(result[another.pk]["options"][1]["count"], 0)

    def test_deadline_anonymous_jury_and_self_reactions_are_protected(self):
        entry, prediction = self.prepare()
        self.clock.return_value = self.event.deadline-timedelta(seconds=1)
        for league in (None, self.a):
            self.assertEqual(self.client.post(self.reaction_url(prediction, league), {"kind":"fire"}).status_code, 404)
        self.clock.return_value = self.event.deadline+timedelta(hours=1)
        self.assertEqual(self.client.post(self.reaction_url(prediction), {"kind":"fire"}).status_code, 404)
        # Private paddock forecasts are already attributed, unlike public jury ballots.
        self.assertEqual(self.client.post(self.reaction_url(prediction, self.a), {"kind":"fire"}).status_code, 302)
        self.clock.return_value = self.event.deadline+timedelta(hours=12)
        self.client.force_login(self.player)
        self.assertEqual(self.client.post(self.reaction_url(prediction), {"kind":"heart"}).status_code, 403)

    def test_empty_late_wrong_event_and_invalid_kinds_are_rejected(self):
        entry, prediction = self.prepare()
        url = self.reaction_url(prediction)
        self.assertEqual(self.client.post(url, {"kind":"evil"}).status_code, 400)
        wrong = reverse("league:crazy_reaction", args=[self.next_event.pk, prediction.pk])
        self.assertEqual(self.client.post(wrong, {"kind":"heart"}).status_code, 404)
        Prediction.objects.filter(pk=prediction.pk).update(crazy_prediction="  ")
        self.assertEqual(self.client.post(url, {"kind":"heart"}).status_code, 404)
        Prediction.objects.filter(pk=prediction.pk).update(crazy_prediction="A", created_at=self.event.deadline)
        self.assertEqual(self.client.post(url, {"kind":"heart"}).status_code, 404)
        self.assertFalse(CrazyReaction.objects.exists())

    def test_post_only_login_csrf_and_unique_constraints(self):
        entry, prediction = self.prepare()
        url = self.reaction_url(prediction)
        self.assertEqual(self.client.get(url).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.owner)
        self.assertEqual(strict.post(url, {"kind":"fire"}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(url, {"kind":"fire"}).status_code, 302)
        CrazyReaction.objects.create(prediction=prediction, user=self.owner, kind="heart")
        with self.assertRaises(IntegrityError), transaction.atomic():
            CrazyReaction.objects.create(prediction=prediction, user=self.owner, kind="fire")
        with self.assertRaises(IntegrityError), transaction.atomic():
            CrazyReaction.objects.create(prediction=prediction, user=self.player, kind="unknown")
        public = summaries([prediction], AnonymousUser())[prediction.pk]
        self.assertFalse(public["can_react"])

    def test_public_page_hides_reactions_during_jury_then_renders(self):
        entry, prediction = self.prepare()
        self.clock.return_value = self.event.deadline+timedelta(hours=1)
        url = reverse("league:event_detail", args=[self.event.pk])
        self.assertNotContains(self.client.get(url), "data-reaction-form")
        self.clock.return_value = self.event.deadline+timedelta(hours=12)
        self.assertContains(self.client.get(url), "data-reaction-form", count=3)

    def test_recap_requires_published_scores_and_private_membership(self):
        entry, prediction = self.prepare()
        public = reverse("league:race_recap", args=[self.event.pk,self.player.pk])
        private = reverse("league:friend_league_recap", args=[self.a.league_id,self.event.pk,self.player.pk])
        self.assertEqual(self.client.get(public).status_code, 404)
        self.event.status = Event.Status.SCORED
        self.event.save(update_fields=["status"])
        Score.objects.create(event=self.event, user=self.player, points=17, breakdown={"P1":10})
        response = self.client.get(public)
        self.assertContains(response, 'width="1080" height="1350"')
        self.assertEqual(response.context["recap_data"]["points"], 17)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(self.client.get(private).status_code, 404)
        LeagueEventScore.objects.create(entry=entry, event=self.event, prediction=prediction, points=24, base_points=24)
        response = self.client.get(private)
        self.assertEqual(response.context["recap_data"]["points"], 24)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(private).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(private).status_code, 302)

    def test_recap_movement_ignores_later_scores_and_safely_encodes_names(self):
        entry, prediction = self.prepare()
        owner_entry = self.a.entries.get(membership__user=self.owner)
        earlier = Event.objects.create(name="Shanghai", season_year=2027, round_number=5,
            deadline=self.event.deadline-timedelta(days=7), status="scored")
        self.a.start_event = earlier
        self.a.save(update_fields=["start_event"])
        self.a.entries.update(first_event=earlier)
        self.event.status = "scored"
        self.event.save(update_fields=["status"])
        for member, race, points in ((entry,earlier,5),(owner_entry,earlier,10),(entry,self.event,20),(owner_entry,self.event,1),
                                     (owner_entry,self.next_event,999)):
            saved_prediction, _ = Prediction.objects.get_or_create(user_id=member.membership.user_id, event=race)
            LeagueEventScore.objects.create(entry=member, event=race, prediction=saved_prediction, points=points, base_points=points)
        score = LeagueEventScore.objects.get(entry=entry, event=self.event)
        data = summary(event=self.event, player=self.player, score=score, score_rows=[], season=self.a)
        self.assertEqual(data["rank"], 1)
        self.assertEqual(data["movement"], 1)
        self.assertEqual(data["overtook"], [self.owner.username])
        self.player.first_name = '</script><script>alert(1)</script>'
        self.player.save(update_fields=["first_name"])
        response = self.client.get(reverse("league:friend_league_recap", args=[self.a.league_id,self.event.pk,self.player.pk]))
        self.assertNotContains(response, '</script><script>alert(1)</script>')

    def test_duel_summary_uses_actual_settled_outcome(self):
        entry, prediction = self.prepare()
        score = Score.objects.create(event=self.event, user=self.player, points=-3)
        DuelChallenge.objects.create(event=self.event, challenger=self.player, opponent=self.owner,
            stake=4, status="settled", winner=self.owner)
        data = summary(event=self.event, player=self.player, score=score, score_rows=[])
        self.assertEqual(data["points"], -3)
        self.assertEqual(data["duel"]["points"], -4)
        self.assertEqual(data["duel"]["label"], "ПОРАЖЕНИЕ")
