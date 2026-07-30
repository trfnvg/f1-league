from datetime import timedelta

from django.contrib.auth.models import User
from django.forms import modelform_factory
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Event, SeasonPrediction, SeasonResult, SeasonScore
from .scoring import calculate_season_points, calculate_season_scores


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
