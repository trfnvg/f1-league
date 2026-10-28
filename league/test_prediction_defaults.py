from django.test import TestCase, override_settings
from django.urls import reverse

from . import test_private_league_ui as fixtures
from .forms import PredictionForm
from .models import Prediction
from .prediction_submission import save_shared_prediction


@override_settings(STORAGES=fixtures.STORAGES)
class PredictionDefaultTests(TestCase):
    setUp = fixtures.PrivateLeagueUITests.setUp

    def test_new_forecast_has_empty_numeric_answers_in_both_pages(self):
        for url in (reverse("league:event_detail", args=[self.event.pk]),
                    reverse("league:friend_league_event", args=[self.a.league_id, self.event.pk])):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            for name in ("safety_car_count", "dnf_count"):
                self.assertIsNone(response.context["form"][name].value())
                self.assertNotIn('value="0"', str(response.context["form"][name]))
        self.assertFalse(Prediction.objects.filter(event=self.event, user=self.owner).exists())

    def test_empty_answers_are_required_and_never_silently_saved_as_zero(self):
        for field in ("safety_car_count", "dnf_count"):
            for supplied in ("", None):
                with self.subTest(field=field, supplied=supplied):
                    data = dict(self.values)
                    if supplied is None:
                        data.pop(field)
                    else:
                        data[field] = supplied
                    form, saved = save_shared_prediction(user=self.owner, event=self.event, data=data)
                    self.assertIsNone(saved)
                    self.assertIn(field, form.errors)
        self.assertFalse(Prediction.objects.exists())

    def test_explicit_zero_saves_and_remains_visible_on_reopen(self):
        form, saved = save_shared_prediction(user=self.owner, event=self.event,
            data={**self.values, "safety_car_count": "0", "dnf_count": "0"})
        self.assertIsNotNone(saved)
        self.assertEqual((saved.safety_car_count, saved.dnf_count), (0,0))
        existing = PredictionForm(instance=saved, event=self.event)
        self.assertEqual(existing["safety_car_count"].value(), 0)
        self.assertEqual(existing["dnf_count"].value(), 0)
        response = self.client.get(reverse("league:event_detail", args=[self.event.pk]))
        self.assertEqual(response.context["form"]["safety_car_count"].value(), 0)

    def test_invalid_post_preserves_zero_and_does_not_refill_a_cleared_answer(self):
        form = PredictionForm({**self.values, "p1":"invalid", "safety_car_count":"0", "dnf_count":""}, event=self.event)
        self.assertFalse(form.is_valid())
        self.assertEqual(form["safety_car_count"].value(), "0")
        self.assertEqual(form["dnf_count"].value(), "")
        self.assertIn("dnf_count", form.errors)

    def test_existing_nonzero_answers_are_preserved(self):
        saved = Prediction.objects.create(user=self.owner, event=self.event, **self.values)
        form = PredictionForm(instance=saved, event=self.event)
        self.assertEqual(form["safety_car_count"].value(), 1)
        self.assertEqual(form["dnf_count"].value(), 2)
