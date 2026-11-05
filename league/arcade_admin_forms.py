from datetime import timedelta
from django import forms
from django.contrib.auth.models import User
from django.utils import timezone

from .arcade_moderation import GAME_MODELS
from .identity import display_name
from .models import ArcadeCompetition, MinesweeperAttempt


class PlayerChoice(forms.ModelChoiceField):
    def label_from_instance(self, user):
        profile = getattr(user, "league_profile", None)
        handle = profile.handle if profile and profile.handle else user.username
        return f"{display_name(user)} · @{handle}"


class ManualAttemptForm(forms.Form):
    user = PlayerChoice(label="Игрок", queryset=User.objects.none())
    started_at = forms.DateTimeField(label="Начало попытки", widget=forms.DateTimeInput(
        format="%Y-%m-%dT%H:%M:%S", attrs={"type":"datetime-local", "step":"1"}))
    finished_at = forms.DateTimeField(label="Завершение попытки", widget=forms.DateTimeInput(
        format="%Y-%m-%dT%H:%M:%S", attrs={"type":"datetime-local", "step":"1"}))
    score = forms.IntegerField(label="Очки", min_value=0, max_value=2_147_483_647)
    competition = forms.ModelChoiceField(label="Зачёт этапа", queryset=ArcadeCompetition.objects.none(),
        required=False, empty_label="Глобальный рейтинг — без привязки к этапу")
    elapsed_ms = forms.IntegerField(label="Игровое время, миллисекунды", min_value=1)
    reason = forms.CharField(label="Причина ручного добавления", max_length=2000,
        widget=forms.Textarea(attrs={"rows":3}))

    def __init__(self, *args, model, **kwargs):
        super().__init__(*args, **kwargs)
        now = timezone.localtime()
        self.fields["started_at"].initial = now-timedelta(minutes=1)
        self.fields["finished_at"].initial = now
        self.fields["user"].queryset = User.objects.filter(is_active=True, is_staff=False).select_related("league_profile").order_by("username")
        if model is MinesweeperAttempt:
            del self.fields["score"], self.fields["competition"]
        else:
            del self.fields["elapsed_ms"]
            self.fields["competition"].queryset = ArcadeCompetition.objects.filter(
                game_key=GAME_MODELS[model], opened_at__isnull=False).select_related("event")
            self.fields["competition"].label_from_instance = lambda c: f"R{c.event.round_number:02d} · {c.event.name} · {c.event.season_year}"


class ModerateAttemptForm(forms.Form):
    excluded = forms.TypedChoiceField(choices=(("1","Исключить из зачёта"),("0","Вернуть в зачёт")),
        coerce=lambda value: value == "1", widget=forms.HiddenInput)
    reason = forms.CharField(label="Причина изменения", max_length=2000, widget=forms.Textarea(attrs={"rows":3}))
