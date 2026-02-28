from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Prediction


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
                    "placeholder": "Свободный прогноз (оценит Судья после этапа)",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ("p1", "p2", "p3", "pole", "fastest_lap", "driver_of_day"):
            base_choices = [(value, label) for value, label in self.fields[field_name].choices if value != ""]
            self.fields[field_name].choices = [("", "Выбери гонщика")] + base_choices
        self.fields["fastest_lap"].required = True
        self.fields["driver_of_day"].required = True

    def clean(self):
        cleaned_data = super().clean()
        podium = [cleaned_data.get("p1"), cleaned_data.get("p2"), cleaned_data.get("p3")]
        if None not in podium and len(set(podium)) != 3:
            raise forms.ValidationError("P1, P2 и P3 должны быть разными гонщиками.")
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
