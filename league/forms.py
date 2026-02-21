from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
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


class RegisterForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({"class": "form-control"})
        self.fields["password1"].widget.attrs.update({"class": "form-control"})
        self.fields["password2"].widget.attrs.update({"class": "form-control"})
