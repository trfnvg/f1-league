from io import StringIO
import json
import socket
from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.forms import modelform_factory
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    Event,
    Prediction,
    Result,
    Score,
    ScoreRevision,
    Season,
    SeasonPrediction,
    SeasonResult,
    SeasonScore,
    TelegramReminder,
    UserProfile,
)
from .scoring import (
    calculate_season_points,
    calculate_season_scores,
    preview_event_scores,
    publish_event_scores,
    restore_score_revision,
)
from .telegram_bot import (
    TelegramAPIError,
    _IPv4HTTPSConnection,
    _IPv4HTTPSHandler,
    _api_call,
    _create_ipv4_connection,
    _handle_start,
    send_due_reminders,
    send_result_notifications,
)


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


class PartialSeasonScoringTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="summer-player", password="test")
        self.prediction = SeasonPrediction.objects.create(
            user=self.user,
            season_year=2026,
            hungary_driver_championship_leader="norris",
            hungary_constructor_championship_leader="mclaren",
            hadjar_best_finish=4,
            world_drivers_champion="norris",
            constructors_champion="mclaren",
            constructors_second="ferrari",
            constructors_third="mercedes",
            last_race_winner="piastri",
            season_pole_sitter="norris",
            driver_change_happened="yes",
            team_most_dnf="alpine",
        )

    def test_partial_result_form_does_not_require_end_of_season_fields(self):
        form_class = modelform_factory(SeasonResult, fields="__all__")
        form = form_class(
            data={
                "season_year": 2026,
                "hungary_driver_championship_leader": "norris",
                "hungary_constructor_championship_leader": "mclaren",
                "hadjar_best_finish": 4,
            }
        )

        self.assertTrue(form.is_valid(), form.errors.as_json())

    def test_only_filled_actual_categories_are_scored(self):
        result = SeasonResult.objects.create(
            season_year=2026,
            hungary_driver_championship_leader="norris",
            hungary_constructor_championship_leader="mclaren",
            hadjar_best_finish=4,
        )

        points, breakdown = calculate_season_points(self.prediction, result)

        self.assertEqual(points, 30)
        self.assertEqual(
            breakdown,
            {
                "Лидер пилотского зачета после Венгрии": 12,
                "Лидер Кубка конструкторов после Венгрии": 10,
                "Лучший финиш Хаджара": 8,
            },
        )

        self.assertEqual(calculate_season_scores(2026), 1)
        score = SeasonScore.objects.get(user=self.user, season_year=2026)
        self.assertEqual(score.points, 30)
        self.assertEqual(score.breakdown, breakdown)


@override_settings(STORAGES=TEST_STORAGES)
class HomeEventOrderingTests(TestCase):
    def test_home_lists_each_event_section_from_newest_round_to_oldest(self):
        now = timezone.now()
        upcoming_old = Event.objects.create(
            name="Ближайший ранний этап",
            round_number=3,
            deadline=now + timedelta(days=3),
        )
        upcoming_new = Event.objects.create(
            name="Ближайший поздний этап",
            round_number=4,
            deadline=now + timedelta(days=10),
        )
        past_old = Event.objects.create(
            name="Прошедший ранний этап",
            round_number=1,
            deadline=now - timedelta(days=10),
            status=Event.Status.SCORED,
        )
        past_new = Event.objects.create(
            name="Прошедший поздний этап",
            round_number=2,
            deadline=now - timedelta(days=3),
            status=Event.Status.SCORED,
        )

        response = self.client.get(reverse("league:home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["upcoming_events"], [upcoming_new, upcoming_old])
        self.assertEqual(response.context["past_events"], [past_new, past_old])
        self.assertContains(response, 'class="event-editorial-card"')
        self.assertContains(response, 'class="event-media-placeholder"')


@override_settings(STORAGES=TEST_STORAGES)
class LeaderboardChartTests(TestCase):
    def test_chart_uses_cumulative_scores_in_chronological_round_order(self):
        first_player = User.objects.create_user(username="Алексей", password="test")
        second_player = User.objects.create_user(username="Борис", password="test")
        now = timezone.now()
        first_event = Event.objects.create(
            name="Первый этап",
            round_number=1,
            deadline=now - timedelta(days=20),
            status=Event.Status.SCORED,
        )
        second_event = Event.objects.create(
            name="Второй этап",
            round_number=2,
            deadline=now - timedelta(days=10),
            status=Event.Status.SCORED,
        )
        Event.objects.create(
            name="Будущий этап без очков",
            round_number=3,
            deadline=now + timedelta(days=10),
        )
        Score.objects.create(user=first_player, event=first_event, points=10)
        Score.objects.create(user=first_player, event=second_event, points=4)
        Score.objects.create(user=second_player, event=first_event, points=2)
        Score.objects.create(user=second_player, event=second_event, points=20)

        response = self.client.get(reverse("league:leaderboard"))

        self.assertEqual(response.status_code, 200)
        chart = response.context["leaderboard_chart"]
        self.assertEqual([event["round"] for event in chart["events"]], [1, 2])
        series = {item["name"]: item for item in chart["series"]}
        self.assertEqual(series["Алексей"]["points"], [10, 14])
        self.assertEqual(series["Борис"]["points"], [2, 22])
        self.assertEqual([row["user"].username for row in response.context["rows"]], ["Борис", "Алексей"])
        self.assertContains(response, 'id="pointsChart"')
        self.assertContains(response, "league/leaderboard-chart.js")


@override_settings(STORAGES=TEST_STORAGES)
class PlayerProfileOrderingTests(TestCase):
    def test_latest_grand_prix_is_rendered_first(self):
        player = User.objects.create_user(username="profile-player", password="test")
        now = timezone.now()
        older = Event.objects.create(
            name="Первый этап",
            round_number=1,
            deadline=now + timedelta(days=1),
        )
        newer = Event.objects.create(
            name="Второй этап",
            round_number=2,
            deadline=now + timedelta(days=8),
        )

        response = self.client.get(reverse("league:player_profile", args=[player.id]))

        self.assertEqual(response.status_code, 200)
        event_cards = response.context["event_cards"]
        self.assertEqual([row["event"].id for row in event_cards], [newer.id, older.id])


@override_settings(STORAGES=TEST_STORAGES)
class ApexNightThemeTests(TestCase):
    def test_base_template_loads_apex_night_theme_last(self):
        response = self.client.get(reverse("league:home"))

        self.assertContains(response, "league/summer-theme.css")
        self.assertContains(response, "league/editorial-rework.css")
        self.assertContains(response, "league/apex-night.css")
        self.assertContains(
            response,
            'class="summer-theme editorial-theme apex-night-theme d-flex flex-column min-vh-100"',
        )


@override_settings(
    STORAGES=TEST_STORAGES,
    TELEGRAM_BOT_TOKEN="test-token",
    TELEGRAM_BOT_USERNAME="f1_predictions_test",
    SITE_URL="https://f1.example",
)
class TelegramTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="telegram-player", password="test")
        self.profile = UserProfile.objects.get(user=self.user)

    @patch("league.telegram_bot.socket.socket")
    @patch("league.telegram_bot.socket.getaddrinfo")
    def test_telegram_connection_uses_ipv4_only(self, getaddrinfo, socket_factory):
        connection = Mock()
        socket_factory.return_value = connection
        getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("149.154.167.220", 443))
        ]

        result = _create_ipv4_connection(("api.telegram.org", 443), timeout=5)

        self.assertIs(result, connection)
        getaddrinfo.assert_called_once_with(
            "api.telegram.org",
            443,
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )
        connection.connect.assert_called_once_with(("149.154.167.220", 443))

    def test_ipv4_https_handler_is_compatible_with_python_312(self):
        handler = _IPv4HTTPSHandler()
        request = Mock()

        with patch.object(handler, "do_open", return_value="response") as do_open:
            response = handler.https_open(request)

        self.assertEqual(response, "response")
        do_open.assert_called_once_with(
            _IPv4HTTPSConnection,
            request,
            context=getattr(handler, "_context", None),
        )

    @override_settings(
        TELEGRAM_API_BASE_URL="https://f1-telegram-proxy.example.workers.dev/",
        TELEGRAM_PROXY_SECRET="proxy-test-secret",
    )
    @patch("league.telegram_bot._PROXY_OPENER.open")
    def test_api_call_can_use_protected_proxy_without_token_in_url(self, open_request):
        response = Mock()
        response.read.return_value = json.dumps({"ok": True, "result": {"id": 123}}).encode()
        open_request.return_value.__enter__.return_value = response

        self.assertEqual(_api_call("getMe"), {"id": 123})

        request = open_request.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://f1-telegram-proxy.example.workers.dev/getMe",
        )
        self.assertNotIn("test-token", request.full_url)
        self.assertEqual(request.get_header("X-proxy-secret"), "proxy-test-secret")
        self.assertTrue(request.get_header("User-agent").startswith("Mozilla/5.0"))

    @override_settings(
        TELEGRAM_API_BASE_URL="https://f1-telegram-proxy.example.workers.dev",
        TELEGRAM_PROXY_SECRET="",
    )
    def test_proxy_requires_a_shared_secret(self):
        with self.assertRaisesMessage(TelegramAPIError, "TELEGRAM_PROXY_SECRET"):
            _api_call("getMe")

    @override_settings(TELEGRAM_WORKER_ENABLED=False)
    @patch("league.management.commands.telegram_bot_worker.run_worker")
    def test_worker_can_be_disabled_without_removing_bot_token(self, run_worker):
        output = StringIO()

        call_command("telegram_bot_worker", stdout=output)

        run_worker.assert_not_called()
        self.assertIn("Telegram worker is disabled", output.getvalue())

    def test_authenticated_user_gets_deep_link_for_current_profile(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("league:telegram_connect"))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("https://t.me/f1_predictions_test?start="))
        self.assertIn(str(self.profile.telegram_link_token), response["Location"])

    def test_profile_shows_telegram_connection_button(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("league:player_profile", args=[self.user.id]))

        self.assertContains(response, "Подключить Telegram")

    @patch("league.telegram_bot.send_message")
    def test_start_command_links_chat_and_rotates_token(self, send_message):
        old_token = self.profile.telegram_link_token

        _handle_start(987654, str(old_token))

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.telegram_chat_id, 987654)
        self.assertTrue(self.profile.telegram_notifications)
        self.assertNotEqual(self.profile.telegram_link_token, old_token)
        send_message.assert_called_once()

    @patch("league.telegram_bot.send_message")
    def test_due_reminder_is_sent_once_only_when_prediction_is_missing(self, send_message):
        event = Event.objects.create(
            name="Тестовый этап",
            round_number=99,
            deadline=timezone.now() + timedelta(hours=2),
        )
        self.profile.telegram_chat_id = 123456
        self.profile.save(update_fields=("telegram_chat_id", "updated_at"))

        self.assertEqual(send_due_reminders(), 1)
        self.assertTrue(TelegramReminder.objects.filter(event=event, user=self.user).exists())
        self.assertEqual(send_due_reminders(), 0)
        send_message.assert_called_once()

    @patch("league.telegram_bot.send_message")
    def test_bot_sends_day_and_three_hour_reminders(self, send_message):
        now = timezone.now()
        event = Event.objects.create(
            name="Двойное напоминание",
            round_number=98,
            deadline=now + timedelta(hours=20),
        )
        self.profile.telegram_chat_id = 123456
        self.profile.save(update_fields=("telegram_chat_id", "updated_at"))

        self.assertEqual(send_due_reminders(now=now), 1)
        self.assertTrue(
            TelegramReminder.objects.filter(
                event=event, user=self.user, kind=TelegramReminder.Kind.DAY
            ).exists()
        )
        self.assertEqual(send_due_reminders(now=event.deadline - timedelta(hours=2)), 1)
        self.assertTrue(
            TelegramReminder.objects.filter(
                event=event, user=self.user, kind=TelegramReminder.Kind.THREE_HOURS
            ).exists()
        )
        self.assertEqual(send_message.call_count, 2)

    @patch("league.telegram_bot.send_message")
    def test_published_result_notification_is_sent_once(self, send_message):
        event = Event.objects.create(
            name="Готовый этап",
            round_number=97,
            deadline=timezone.now() - timedelta(days=1),
            status=Event.Status.SCORED,
        )
        Result.objects.create(
            event=event,
            p1="norris",
            p2="piastri",
            p3="russell",
            pole="norris",
            published_at=timezone.now(),
        )
        Score.objects.create(event=event, user=self.user, points=21)
        self.profile.telegram_chat_id = 123456
        self.profile.save(update_fields=("telegram_chat_id", "updated_at"))

        self.assertEqual(send_result_notifications(), 1)
        self.assertEqual(send_result_notifications(), 0)
        self.assertTrue(
            TelegramReminder.objects.filter(
                event=event, user=self.user, kind=TelegramReminder.Kind.RESULT
            ).exists()
        )


@override_settings(STORAGES=TEST_STORAGES)
class SeasonAndPrivacyTests(TestCase):
    def setUp(self):
        self.player = User.objects.create_user(username="hidden-player", password="test")
        self.viewer = User.objects.create_user(username="viewer", password="test")

    def test_selected_season_filters_calendar(self):
        Season.objects.create(year=2025, title="Season 2025")
        old_event = Event.objects.create(
            season_year=2025,
            name="Архивный этап",
            round_number=1,
            deadline=timezone.now() - timedelta(days=300),
        )
        Event.objects.create(
            season_year=2026,
            name="Новый этап",
            round_number=1,
            deadline=timezone.now() + timedelta(days=3),
        )

        response = self.client.get(reverse("league:home"), {"season": 2025})

        self.assertEqual(response.context["events"], [old_event])
        self.assertEqual(response.context["season"].year, 2025)

    def test_other_players_prediction_is_hidden_until_deadline(self):
        event = Event.objects.create(
            name="Секретный этап",
            round_number=2,
            deadline=timezone.now() + timedelta(days=2),
            race_datetime=timezone.now() + timedelta(days=3),
        )
        Prediction.objects.create(
            event=event,
            user=self.player,
            p1="norris",
            p2="piastri",
            p3="russell",
            pole="norris",
        )
        self.client.force_login(self.viewer)

        response = self.client.get(reverse("league:player_profile", args=[self.player.id]))
        self.assertContains(response, "Предикт скрыт до дедлайна")
        self.assertNotContains(response, "Норрис (McLaren)")

        event.deadline = timezone.now() - timedelta(minutes=1)
        event.save(update_fields=("deadline",))
        response = self.client.get(reverse("league:player_profile", args=[self.player.id]))
        self.assertContains(response, "Норрис (McLaren)")


@override_settings(STORAGES=TEST_STORAGES)
class SafeScorePublicationTests(TestCase):
    def test_publish_preview_and_restore_revision(self):
        admin_user = User.objects.create_superuser(username="judge", password="test")
        player = User.objects.create_user(username="scored-player", password="test")
        event = Event.objects.create(
            name="Этап для подсчёта",
            round_number=8,
            deadline=timezone.now() - timedelta(days=1),
        )
        Prediction.objects.create(
            event=event,
            user=player,
            p1="norris",
            p2="piastri",
            p3="russell",
            pole="norris",
        )
        Result.objects.create(
            event=event,
            p1="norris",
            p2="piastri",
            p3="russell",
            pole="norris",
        )
        Score.objects.create(event=event, user=player, points=1, breakdown={"old": 1})

        preview = preview_event_scores(event)
        self.assertEqual(preview[0]["points"], 34)
        self.assertEqual(preview[0]["delta"], 33)
        first_revision, _ = publish_event_scores(event, admin_user)

        event.refresh_from_db()
        event.result.refresh_from_db()
        self.assertEqual(event.status, Event.Status.SCORED)
        self.assertIsNotNone(event.result.published_at)
        self.assertEqual(event.result.published_by, admin_user)
        self.assertEqual(Score.objects.get(event=event, user=player).points, 34)
        self.assertEqual(first_revision.revision, 1)

        Score.objects.filter(event=event, user=player).update(points=2)
        restored = restore_score_revision(first_revision, admin_user)
        self.assertEqual(restored.revision, 2)
        self.assertEqual(Score.objects.get(event=event, user=player).points, 34)
        self.assertEqual(ScoreRevision.objects.filter(event=event).count(), 2)
