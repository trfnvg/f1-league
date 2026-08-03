from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    Event,
    Prediction,
    Result,
    Score,
    Season,
    TelegramReminder,
    UserProfile,
)
from .scoring import publish_event_scores, restore_score_revision
from .services import build_achievements, build_leaderboard
from .telegram_bot import send_due_reminders, send_result_notifications


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def create_prediction(user, event):
    return Prediction.objects.create(
        user=user,
        event=event,
        p1="norris",
        p2="piastri",
        p3="russell",
        pole="norris",
        safety_car_count=0,
        dnf_count=0,
    )


def create_result(event):
    return Result.objects.create(
        event=event,
        p1="norris",
        p2="piastri",
        p3="russell",
        pole="norris",
        safety_car_count=0,
        dnf_count=0,
    )


@override_settings(STORAGES=TEST_STORAGES)
class SafeScorePublishingTests(TestCase):
    def test_publish_creates_revision_and_restore_recovers_scores(self):
        admin = User.objects.create_superuser("race-control", "admin@example.com", "test")
        player = User.objects.create_user("driver", password="test")
        event = Event.objects.create(
            name="Australian GP",
            round_number=1,
            deadline=timezone.now() - timedelta(days=1),
        )
        create_prediction(player, event)
        result = create_result(event)

        first_revision, first_rows = publish_event_scores(event, admin)

        self.assertEqual(first_revision.revision, 1)
        self.assertEqual(first_rows[0]["points"], 34)
        self.assertNotIn("Fastest Lap", first_rows[0]["breakdown"])
        self.assertEqual(Score.objects.get(event=event, user=player).points, 34)
        result.refresh_from_db()
        self.assertIsNotNone(result.published_at)
        self.assertEqual(result.published_by, admin)

        result.p1 = "verstappen"
        result.save()
        second_revision, _ = publish_event_scores(event, admin)
        self.assertEqual(second_revision.revision, 2)
        self.assertEqual(Score.objects.get(event=event, user=player).points, 24)

        restored = restore_score_revision(first_revision, admin)
        self.assertEqual(restored.revision, 3)
        self.assertEqual(Score.objects.get(event=event, user=player).points, 34)


@override_settings(STORAGES=TEST_STORAGES)
class PredictionPrivacyTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="test")
        self.viewer = User.objects.create_user("viewer", password="test")
        self.event = Event.objects.create(
            name="Miami GP",
            round_number=6,
            deadline=timezone.now() + timedelta(days=1),
        )
        create_prediction(self.owner, self.event)

    def test_other_players_prediction_is_hidden_until_deadline(self):
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("league:player_profile", args=[self.owner.id]))

        card = response.context["event_cards"][0]
        self.assertIsNone(card["prediction"])
        self.assertTrue(card["prediction_hidden"])
        self.assertContains(response, "Предикт скрыт до дедлайна")

        self.event.deadline = timezone.now() - timedelta(minutes=1)
        self.event.save(update_fields=("deadline",))
        response = self.client.get(reverse("league:player_profile", args=[self.owner.id]))
        self.assertIsNotNone(response.context["event_cards"][0]["prediction"])

    def test_community_predictions_appear_only_after_deadline(self):
        response = self.client.get(reverse("league:event_detail", args=[self.event.id]))
        self.assertFalse(response.context["can_view_community"])

        self.event.deadline = timezone.now() - timedelta(minutes=1)
        self.event.save(update_fields=("deadline",))
        response = self.client.get(reverse("league:event_detail", args=[self.event.id]))
        self.assertTrue(response.context["can_view_community"])
        self.assertContains(response, "Предикты участников")
        self.assertContains(response, self.owner.username)

        create_result(self.event)
        Score.objects.create(event=self.event, user=self.owner, points=34)
        response = self.client.get(reverse("league:event_detail", args=[self.event.id]))
        correct = response.context["community_predictions"][0]["correct"]
        self.assertTrue(correct["p1"])
        self.assertTrue(correct["p2"])
        self.assertTrue(correct["p3"])
        self.assertTrue(correct["pole"])
        self.assertFalse(correct["fastest_lap"])
        self.assertContains(response, 'class="community-prediction-correct"', count=4)
        self.assertContains(response, 'class="community-score"')
        self.assertNotContains(response, '<span class="score-pill">34</span>')


@override_settings(STORAGES=TEST_STORAGES)
class SeasonArchiveTests(TestCase):
    def test_selected_season_filters_home_calendar(self):
        Season.objects.update(is_active=False)
        Season.objects.create(year=2025, title="2025 archive")
        Season.objects.update_or_create(
            year=2026,
            defaults={"title": "2026 season", "is_active": True},
        )
        Event.objects.create(
            season_year=2025,
            name="Archived GP",
            round_number=1,
            deadline=timezone.now() - timedelta(days=300),
        )
        Event.objects.create(
            season_year=2026,
            name="Current GP",
            round_number=1,
            deadline=timezone.now() + timedelta(days=3),
        )

        response = self.client.get(reverse("league:home") + "?season=2025")

        self.assertEqual(response.context["season"].year, 2025)
        self.assertContains(response, "Archived GP")
        self.assertNotContains(response, "Current GP")


@override_settings(
    STORAGES=TEST_STORAGES,
    TELEGRAM_BOT_TOKEN="test-token",
    SITE_URL="https://f1.example",
)
class ExpandedTelegramTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("telegram-driver", password="test")
        self.profile = UserProfile.objects.get(user=self.user)
        self.profile.telegram_chat_id = 12345
        self.profile.telegram_notifications = True
        self.profile.save()

    @patch("league.telegram_bot.send_message")
    def test_sends_24_hour_and_3_hour_reminders(self, send_message):
        now = timezone.now()
        event = Event.objects.create(
            name="Canadian GP",
            round_number=9,
            deadline=now + timedelta(hours=23),
        )

        self.assertEqual(send_due_reminders(now=now), 1)
        self.assertEqual(send_due_reminders(now=event.deadline - timedelta(hours=2)), 1)
        self.assertEqual(send_message.call_count, 2)
        self.assertSetEqual(
            set(TelegramReminder.objects.filter(event=event).values_list("kind", flat=True)),
            {TelegramReminder.Kind.DAY, TelegramReminder.Kind.THREE_HOURS},
        )

    @patch("league.telegram_bot.send_message")
    def test_published_result_notification_contains_score(self, send_message):
        event = Event.objects.create(
            name="British GP",
            round_number=12,
            deadline=timezone.now() - timedelta(days=1),
        )
        create_prediction(self.user, event)
        create_result(event)
        publish_event_scores(event)

        self.assertEqual(send_result_notifications(), 1)
        self.assertIn("34 очков", send_message.call_args.args[1])
        self.assertTrue(
            TelegramReminder.objects.filter(
                event=event,
                user=self.user,
                kind=TelegramReminder.Kind.RESULT,
            ).exists()
        )


@override_settings(STORAGES=TEST_STORAGES)
class InterfaceRefinementTests(TestCase):
    def test_own_profile_has_clickable_avatar_and_logout(self):
        user = User.objects.create_user("profile-owner", password="test")
        self.client.force_login(user)

        response = self.client.get(reverse("league:player_profile", args=[user.id]))

        self.assertContains(response, "profile-avatar-editable")
        self.assertContains(response, "Загрузить аватар")
        self.assertContains(response, "avatarUploadMenu")
        self.assertContains(response, "profile-logout-btn")
        self.assertNotContains(response, "profile-avatar-overlay")
        self.assertNotContains(response, 'class="avatar-editor"')

    def test_home_countdown_uses_days_hours_and_minutes(self):
        response = self.client.get(reverse("league:home"))

        self.assertContains(response, "86400000")
        self.assertContains(response, "дн ·")
        self.assertContains(response, "мин`")

    def test_chart_uses_unique_curated_colors(self):
        users = [User.objects.create_user(f"driver-{index}") for index in range(12)]

        colors = [item["color"] for item in build_leaderboard(2026)["chart"]["series"]]

        self.assertEqual(len(colors), len(users))
        self.assertEqual(len(set(colors)), len(colors))

    def test_stable_pace_uses_correct_russian_plural(self):
        user = User.objects.create_user("consistent-driver")
        statistics = {
            "stage_wins": 0,
            "perfect_podiums": 0,
            "pole_hits": 0,
            "crazy_hits": 0,
            "points": [1] * 11,
        }

        achievements = build_achievements(user, statistics)

        stable_pace = next(item for item in achievements if item["code"] == "streak")
        self.assertEqual(stable_pace["description"], "11 этапов подряд с очками")
