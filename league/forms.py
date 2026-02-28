from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Prediction, SeasonPrediction


class PredictionForm(forms.ModelForm):
    class Meta:
        model = Prediction
        fields = [
            "p1",
            "p2",
            "p3",
            "pole",
            "fastest_lap",
            "driver_of_day",
            "safety_car_count",
            "dnf_count",
            "crazy_prediction",
        ]
        widgets = {
            "p1": forms.Select(attrs={"class": "form-select"}),
            "p2": forms.Select(attrs={"class": "form-select"}),
            "p3": forms.Select(attrs={"class": "form-select"}),
            "pole": forms.Select(attrs={"class": "form-select"}),
            "fastest_lap": forms.Select(attrs={"class": "form-select"}),
            "driver_of_day": forms.Select(attrs={"class": "form-select"}),
            "safety_car_count": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "dnf_count": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "crazy_prediction": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Свободный прогноз",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fastest_lap"].required = True
        self.fields["driver_of_day"].required = True

    def clean(self):
        cleaned_data = super().clean()
        podium = [cleaned_data.get("p1"), cleaned_data.get("p2"), cleaned_data.get("p3")]
        if None not in podium and len(set(podium)) != 3:
            raise forms.ValidationError("P1, P2 и P3 должны быть разными гонщиками.")
        return cleaned_data


class SeasonPredictionForm(forms.ModelForm):
    class Meta:
        model = SeasonPrediction
        fields = [
            "hungary_driver_championship_leader",
            "hungary_constructor_championship_leader",
            "hadjar_best_finish",
            "world_drivers_champion",
            "constructors_champion",
            "constructors_second",
            "constructors_third",
            "last_race_winner",
            "season_pole_sitter",
            "driver_change_happened",
            "team_most_dnf",
        ]
        widgets = {
            "hungary_driver_championship_leader": forms.Select(attrs={"class": "form-select"}),
            "hungary_constructor_championship_leader": forms.Select(attrs={"class": "form-select"}),
            "hadjar_best_finish": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 22}),
            "world_drivers_champion": forms.Select(attrs={"class": "form-select"}),
            "constructors_champion": forms.Select(attrs={"class": "form-select"}),
            "constructors_second": forms.Select(attrs={"class": "form-select"}),
            "constructors_third": forms.Select(attrs={"class": "form-select"}),
            "last_race_winner": forms.Select(attrs={"class": "form-select"}),
            "season_pole_sitter": forms.Select(attrs={"class": "form-select"}),
            "driver_change_happened": forms.Select(attrs={"class": "form-select"}),
            "team_most_dnf": forms.Select(attrs={"class": "form-select"}),
        }

    def clean(self):
        cleaned_data = super().clean()

        constructors = [
            cleaned_data.get("constructors_champion"),
            cleaned_data.get("constructors_second"),
            cleaned_data.get("constructors_third"),
        ]
        if None not in constructors and "" not in constructors and len(set(constructors)) != 3:
            raise forms.ValidationError("Топ-3 Кубка конструкторов должен состоять из трех разных команд.")

        hadjar_best_finish = cleaned_data.get("hadjar_best_finish")
        if hadjar_best_finish is not None and not 1 <= hadjar_best_finish <= 22:
            self.add_error("hadjar_best_finish", "Укажи позицию от 1 до 22.")

        return cleaned_data


class RegisterForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({"class": "form-control"})
        self.fields["password1"].widget.attrs.update({"class": "form-control"})
        self.fields["password2"].widget.attrs.update({"class": "form-control"})
