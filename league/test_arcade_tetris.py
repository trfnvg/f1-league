import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .arcade_library import GAMES, freeze
from .arcade_rewards import best_event_arcade_attempt, spin_event_wheel
from .models import (ArcadeCompetition, ArcadeRecord, ArcadeSettings, DoodleRecord,
                     Event, Prediction, Season, TetrisAttempt, TetrisRecord)
from .tetris_rules import Game, VERSION


def finished_replay(seed):
    game, inputs, tick = Game(seed), [], 0
    while game.phase != "over":
        if game.phase == "running":
            inputs.append([tick, 5])
            game.action(5)
        if game.phase == "over":
            break
        game.update()
        tick += 1
    return {"ticks": tick, "inputs": inputs, "rules_version": VERSION}, game.score


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class TetrisReleaseTests(TestCase):
    def setUp(self):
        self.url = reverse("league:arcade_game", args=["tetris"])
        self.control = reverse("league:arcade_control")
        self.start = reverse("league:tetris_attempt_start")
        self.finish = reverse("league:tetris_attempt_finish")
        self.admin = User.objects.create_user("tetris-admin", is_staff=True)
        self.player = User.objects.create_user("tetris-player")
        self.other = User.objects.create_user("other-player")
        Season.objects.update_or_create(year=2026, defaults={"is_active": True})
        self.settings, _ = ArcadeSettings.objects.get_or_create(pk=1)
        self.event = Event.objects.create(name="Tetris GP", round_number=1, season_year=2026,
            deadline=timezone.now()+timedelta(hours=1), race_datetime=timezone.now()+timedelta(hours=3))

    def publish(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.control, {"action": "publish", "active_game": "tetris",
            "competition_event": self.event.pk})
        self.assertEqual(response.status_code, 302)
        self.settings.refresh_from_db()
        return ArcadeCompetition.objects.get(event=self.event)

    def run_attempt(self):
        self.client.force_login(self.player)
        data = self.client.post(self.start).json()
        payload, score = finished_replay(data["seed"])
        payload["attempt_id"] = data["attempt_id"]
        return payload, score

    def test_public_page_and_library_and_uniform_results(self):
        for user in (None, self.player):
            if user:
                self.client.force_login(user)
            page = self.client.get(self.url)
            self.assertEqual(page.status_code, 200)
            self.assertContains(page, 'id="tetris-canvas"')
            self.assertContains(page, "league/arcade-results.css")
            self.assertContains(page, 'class="tetris-leaderboard arcade-results"')
            self.assertContains(page, "Всего попыток")
            self.assertNotContains(page, "Управление аркадами ↗")
            self.assertNotContains(page, "Лаборатория · закрытый тест")
            self.assertNotContains(page, 'id="tetris-mascot"')
            self.assertContains(self.client.get(reverse("league:arcade")), self.url)
        self.assertIn("tetris", GAMES)

    def test_admin_can_publish_tetris_and_only_admin_can_change_library(self):
        contest = self.publish()
        self.assertEqual(contest.game_key, "tetris")
        self.assertIsNotNone(contest.opened_at)
        self.assertEqual(self.settings.active_game, "tetris")
        page = self.client.get(self.url)
        self.assertContains(page, 'id="arcade-wheel-panel"')
        self.assertContains(page, "league/arcade.css")
        self.assertContains(page, "league/arcade-player.css")
        self.assertContains(page, "league/arcade-wheel.js")
        self.assertContains(self.client.get(self.control), '<option value="tetris"')
        self.client.force_login(self.player)
        self.assertEqual(self.client.post(self.control, {"action":"library","library_games":[]}).status_code, 403)
        self.client.force_login(self.admin)
        self.client.post(self.control, {"action":"library","library_games":["flappy"]})
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.library_games, ["flappy"])
        self.assertTrue(self.settings.public_enabled)
        contest.refresh_from_db()
        self.assertEqual(contest.game_key,"tetris")
        self.client.force_login(self.player)
        library = self.client.get(reverse("league:arcade"))
        self.assertEqual([g["key"] for g in library.context["games"]], ["flappy"])
        self.assertEqual(library.context["current_game"]["key"], "tetris")
        self.assertEqual(self.client.get(self.url).status_code,200)
        self.assertEqual(self.client.post(self.start).status_code,200)

    def test_empty_library_and_direct_access_are_enforced_without_deleting_records(self):
        TetrisRecord.objects.create(user=self.player,best_score=300,total_attempts=2)
        self.client.force_login(self.admin)
        self.client.post(self.control, {"action":"library"})
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.library_games,[])
        self.client.force_login(self.player)
        self.assertEqual(self.client.get(self.url).status_code,404)
        self.assertEqual(self.client.post(self.start).status_code,404)
        self.assertEqual(self.client.get(reverse("league:tetris_leaderboard")).status_code,404)
        self.assertFalse(self.client.get(reverse("league:arcade")).context["games"])
        self.assertEqual(TetrisRecord.objects.get(user=self.player).best_score,300)
        self.client.force_login(self.admin)
        self.client.post(self.control, {"action":"library","library_games":["tetris"]})
        self.client.force_login(self.player)
        self.assertEqual(self.client.get(self.url).status_code,200)
        self.assertEqual(TetrisRecord.objects.get(user=self.player).best_score,300)

    def test_unreleased_library_value_does_not_change_any_setting(self):
        self.client.force_login(self.admin)
        before=self.settings.library_games
        self.client.post(self.control, {"action":"library","library_games":["minesweeper"]})
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.library_games,before)
        self.client.post(self.control, {"action":"publish","active_game":"minesweeper","competition_event":self.event.pk})
        self.assertFalse(ArcadeCompetition.objects.filter(event=self.event).exists())

    def test_library_save_preserves_the_event_being_planned(self):
        self.client.force_login(self.admin)
        response=self.client.post(self.control,{"action":"library","library_games":["tetris"],"library_event":self.event.pk})
        self.assertIn(f"&event={self.event.pk}#lab-library",response.url)
        self.assertFalse(ArcadeCompetition.objects.exists())

    def test_authenticated_start_and_verified_finish_update_only_tetris(self):
        payload,score=self.run_attempt()
        self.assertFalse(ArcadeRecord.objects.exists())
        self.assertFalse(DoodleRecord.objects.exists())
        response=self.client.post(self.finish,payload,content_type="application/json")
        self.assertEqual(response.status_code,200,response.content)
        attempt=TetrisAttempt.objects.get(pk=payload["attempt_id"])
        self.assertEqual(attempt.score,score)
        self.assertEqual(attempt.replay,payload["inputs"])
        self.assertEqual(response.json()["board_record"],score)
        record=TetrisRecord.objects.get(user=self.player)
        self.assertEqual((record.best_score,record.total_attempts),(score,1))
        self.assertEqual(self.client.post(self.finish,payload,content_type="application/json").status_code,200)
        self.assertEqual(TetrisRecord.objects.get(user=self.player).total_attempts,1)

    def test_score_cannot_be_submitted_without_a_replay_or_for_another_player(self):
        payload,_=self.run_attempt()
        response=self.client.post(self.finish,{"attempt_id":payload["attempt_id"],"score":999999},content_type="application/json")
        self.assertEqual(response.status_code,400)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(self.finish,payload,content_type="application/json").status_code,409)
        self.assertIsNone(TetrisAttempt.objects.get(pk=payload["attempt_id"]).score)
        self.assertFalse(TetrisRecord.objects.filter(best_score__gt=0).exists())

    def test_invalid_replay_is_consumed_and_cannot_be_retried(self):
        payload,_=self.run_attempt()
        payload["inputs"]=[[-1,5]]
        self.assertEqual(self.client.post(self.finish,payload,content_type="application/json").status_code,400)
        self.assertEqual(self.client.post(self.finish,payload,content_type="application/json").status_code,409)
        self.assertEqual(TetrisRecord.objects.get(user=self.player).best_score,0)

    def test_admin_test_is_publicly_forge_proof_and_does_not_save(self):
        self.client.force_login(self.admin)
        response=self.client.get(self.url+"?admin_test=1")
        self.assertContains(response,'data-save-results="false"')
        self.assertIsNone(self.client.post(self.start+"?admin_test=1").json()["attempt_id"])
        self.assertEqual(self.client.post(self.finish+"?admin_test=1",{},content_type="application/json").status_code,403)
        self.assertFalse(TetrisAttempt.objects.exists())
        self.assertFalse(TetrisRecord.objects.exists())
        self.client.force_login(self.player)
        self.assertContains(self.client.get(self.url+"?admin_test=1"),'data-save-results="true"')
        self.assertIsNotNone(self.client.post(self.start+"?admin_test=1").json()["attempt_id"])

    def test_contest_record_freezes_and_winner_can_use_wheel(self):
        contest=self.publish()
        payload,score=self.run_attempt()
        Prediction.objects.create(user=self.player,event=self.event)
        response=self.client.post(self.finish,payload,content_type="application/json")
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()["board_scope"],"competition")
        self.assertEqual(TetrisAttempt.objects.get(pk=payload["attempt_id"]).competition_id,contest.pk)
        now=self.event.deadline+timedelta(seconds=1)
        with patch("league.arcade_library.timezone.now",return_value=now):
            freeze(contest)
            self.assertEqual(best_event_arcade_attempt(self.event,game_key="tetris",opened_at=contest.opened_at).score,score)
            spin,created=spin_event_wheel(self.event,self.player,now=now)
            self.assertTrue(created)
            self.assertEqual(spin.winner_score,score)
            page=self.client.get(reverse("league:arcade"))
            self.assertIsNone(page.context["current_game"])
            data=self.client.post(self.start).json()
            self.assertIsNone(TetrisAttempt.objects.get(pk=data["attempt_id"]).competition_id)
        contest.refresh_from_db()
        self.assertEqual(contest.standings[0]["score"],score)

    def test_anonymous_cannot_save_and_game_page_is_get_only(self):
        self.assertEqual(self.client.post(self.start).status_code,302)
        self.assertEqual(self.client.post(self.finish,{},content_type="application/json").status_code,302)
        self.assertEqual(self.client.post(self.url).status_code,405)

    def test_csrf_and_start_rate_limit_are_enforced(self):
        protected=Client(enforce_csrf_checks=True)
        protected.force_login(self.player)
        self.assertEqual(protected.post(self.start).status_code,403)
        self.client.force_login(self.player)
        for _ in range(30):
            self.assertEqual(self.client.post(self.start).status_code,200)
        self.assertEqual(self.client.post(self.start).status_code,429)
        self.assertEqual(TetrisAttempt.objects.count(),30)

    def test_impossible_time_and_incomplete_game_do_not_create_records(self):
        for bad in ({"ticks":300000}, {"ticks":0,"inputs":[]}):
            payload,_=self.run_attempt()
            payload.update(bad)
            response=self.client.post(self.finish,payload,content_type="application/json")
            self.assertEqual(response.status_code,400,response.content)
        self.assertFalse(TetrisRecord.objects.filter(best_score__gt=0).exists())

    def test_running_attempt_can_finish_after_visibility_is_disabled(self):
        payload,score=self.run_attempt()
        self.settings.library_games=[];self.settings.save(update_fields=["library_games"])
        response=self.client.post(self.finish,payload,content_type="application/json")
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(TetrisRecord.objects.get(user=self.player).best_score,score)
        self.assertEqual(self.client.post(self.start).status_code,404)

    def test_unchecked_competition_disappears_but_wheel_remains_after_deadline(self):
        self.settings.library_games=[];self.settings.save(update_fields=["library_games"])
        self.publish()
        payload,_=self.run_attempt()
        Prediction.objects.create(user=self.player,event=self.event)
        self.assertEqual(self.client.post(self.finish,payload,content_type="application/json").status_code,200)
        with patch("league.arcade_library.timezone.now",return_value=self.event.deadline+timedelta(seconds=1)):
            page=self.client.get(self.url)
            self.assertEqual(page.status_code,200)
            self.assertNotContains(page,'id="tetris-machine"')
            self.assertContains(page,'id="arcade-wheel-panel"')
            self.assertEqual(self.client.post(self.start).status_code,404)
