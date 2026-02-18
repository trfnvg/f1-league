from django import forms
from .models import Prediction


class PredictionForm(forms.ModelForm):
    class Meta:
        model = Prediction
        fields = ["p1", "p2", "p3", "pole"]

        widgets = {
            "p1": forms.TextInput(attrs={"class": "form-control"}),
            "p2": forms.TextInput(attrs={"class": "form-control"}),
            "p3": forms.TextInput(attrs={"class": "form-control"}),
            "pole": forms.TextInput(attrs={"class": "form-control"}),
        }
