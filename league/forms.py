from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .duels import available_opponents
from .models import Prediction, SeasonPrediction, UserProfile


def _set_empty_select_option(field, empty_label=""):
    cleaned_choices = [(value, label) for value, label in field.choices if value != ""]
    field.choices = [("", empty_label)] + cleaned_choices


class PredictionForm(forms.ModelForm):
    class Meta:
        model = Prediction
        fields = [
            "p1",
            "p2",
            "p3",
            "pole",
            "sprint_qualifying_winner",
            "sprint_winner",
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
            "sprint_qualifying_winner": forms.Select(attrs={"class": "form-select"}),
            "sprint_winner": forms.Select(attrs={"class": "form-select"}),
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
        event = kwargs.pop("event", None)
        super().__init__(*args, **kwargs)
        # Model defaults are storage defaults, not answers chosen by the player.
        # Bound POST data and existing predictions must still preserve real zeros.
        if self.instance._state.adding:
            for name in ("safety_car_count", "dnf_count"):
                if name not in (kwargs.get("initial") or {}):
                    self.initial[name] = None
        for name in ("safety_car_count", "dnf_count"):
            self.fields[name].widget.attrs.update(placeholder="Укажите число", inputmode="numeric")
        for field_name in (
            "p1",
            "p2",
            "p3",
            "pole",
            "sprint_qualifying_winner",
            "sprint_winner",
            "fastest_lap",
            "driver_of_day",
        ):
            if field_name in self.fields:
                _set_empty_select_option(self.fields[field_name], "Выберите пилота")

        if event and not event.has_sprint:
            self.fields.pop("sprint_qualifying_winner", None)
            self.fields.pop("sprint_winner", None)
        elif event and event.has_sprint:
            self.fields["sprint_qualifying_winner"].required = True
            self.fields["sprint_winner"].required = True

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in (
            "hungary_driver_championship_leader",
            "hungary_constructor_championship_leader",
            "world_drivers_champion",
            "constructors_champion",
            "constructors_second",
            "constructors_third",
            "last_race_winner",
            "season_pole_sitter",
            "driver_change_happened",
            "team_most_dnf",
        ):
            _set_empty_select_option(self.fields[field_name])

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
    error_messages = {"password_mismatch": "Пароли не совпадают."}
    username = forms.CharField(label="Логин", min_length=3, max_length=30,
        help_text="От 3 до 30 латинских букв и цифр. Без пробелов и спецсимволов.",
        widget=forms.TextInput(attrs={"autocomplete": "username", "autocapitalize": "none", "spellcheck": "false", "pattern": "[a-zA-Z0-9]{3,30}"}))
    first_name = forms.CharField(label="Имя", max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "given-name"}))
    email = forms.EmailField(label="Почта", max_length=254,
        help_text="На неё придёт ссылка, если ты забудешь пароль.",
        widget=forms.EmailInput(attrs={"autocomplete": "email"}))

    class Meta:
        model = User
        fields = ("first_name", "username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
        self.fields["password1"].min_length = 8
        self.fields["password1"].label = "Пароль"
        self.fields["password1"].help_text = "Не менее 8 символов. В пароле можно использовать спецсимволы."
        self.fields["password2"].label = "Повтори пароль"
        self.fields["password2"].help_text = "Введи тот же пароль ещё раз."
        self.fields["username"].widget.attrs.pop("autofocus", None)
        self.fields["password1"].widget.attrs["minlength"] = 8

    def clean_username(self):
        from .identity import clean_handle
        return clean_handle(self.cleaned_data["username"])

    def clean_first_name(self):
        from .identity import clean_display_name
        return clean_display_name(self.cleaned_data["first_name"])

    def clean_email(self):
        value = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise forms.ValidationError("Эта почта уже используется. Войди или восстанови пароль.")
        return value

    def clean_password1(self):
        password = self.cleaned_data["password1"]
        if len(password) < 8:
            raise forms.ValidationError("Пароль должен содержать не менее 8 символов.")
        return password


class AccountSettingsForm(forms.Form):
    handle = forms.CharField(label="Логин", max_length=30)
    email = forms.EmailField(label="Почта для восстановления", max_length=254)
    password = forms.CharField(label="Текущий пароль", widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

        self.fields["handle"].widget.attrs.update({"autocomplete": "username", "autocapitalize": "none", "spellcheck": "false"})
        self.fields["email"].widget.attrs["autocomplete"] = "email"

    def clean_handle(self):
        from .identity import clean_handle
        return clean_handle(self.cleaned_data["handle"], self.user)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("Эта почта уже используется.")
        return email

    def clean_password(self):
        if not self.user.check_password(self.cleaned_data["password"]):
            raise forms.ValidationError("Неверный текущий пароль.")
        return self.cleaned_data["password"]


class AvatarUploadForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ("avatar",)
        widgets = {
            "avatar": forms.FileInput(
                attrs={
                    "class": "profile-avatar-input",
                    "accept": "image/jpeg,image/png,image/webp,image/gif",
                }
            ),
        }


class DuelChallengeForm(forms.Form):
    opponent = forms.ModelChoiceField(
        label="Соперник",
        queryset=User.objects.none(),
        empty_label="Выбери участника",
        widget=forms.Select(attrs={"class": "form-select western-duel-select"}),
    )
    stake = forms.IntegerField(
        label="Ставка",
        min_value=1,
        max_value=10,
        initial=5,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control western-duel-stake",
                "min": 1,
                "max": 10,
                "inputmode": "numeric",
            }
        ),
    )

    def __init__(self, *args, event, user, **kwargs):
        super().__init__(*args, **kwargs)
        from .identity import display_name
        self.fields["opponent"].label_from_instance = display_name
        self.fields["opponent"].queryset = available_opponents(event, user)
