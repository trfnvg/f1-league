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

from .models import Event, SeasonPrediction, SeasonResult, SeasonScore, TelegramReminder, UserProfile
from .scoring import calculate_season_points, calculate_season_scores
from .telegram_bot import (
    TelegramAPIError,
    _IPv4HTTPSConnection,
    _IPv4HTTPSHandler,
    _api_call,
    _create_ipv4_connection,
    _handle_start,
    send_due_reminders,
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
class SummerThemeTests(TestCase):
    def test_base_template_loads_summer_theme(self):
        response = self.client.get(reverse("league:home"))

        self.assertContains(response, "league/summer-theme.css")
        self.assertContains(response, 'class="summer-theme d-flex flex-column min-vh-100"')


@override_settings(
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
