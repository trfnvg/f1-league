from django import forms
from django.utils import timezone

from .models import Event, LeagueSeason


class EventChoice(forms.ModelChoiceField):
    def label_from_instance(self, event):
        return f"{event.season_year} · R{event.round_number} · {event.name}"


class CreateLeagueForm(forms.Form):
    name = forms.CharField(label="Название лиги", max_length=80,
        widget=forms.TextInput(attrs={"placeholder": "Например, Паддок по пятницам", "autocomplete": "off"}))
    start_event = EventChoice(label="Первый зачётный Гран-при", queryset=Event.objects.none(), empty_label="Выберите этап")
    ruleset = forms.ChoiceField(label="Правила", choices=LeagueSeason.Ruleset.choices, initial="classic", widget=forms.RadioSelect)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        events = Event.objects.filter(
            deadline__gt=timezone.now(), status=Event.Status.OPEN,
        ).order_by("deadline", "season_year", "round_number")
        self.fields["start_event"].queryset = events
        first = events.first()
        if first:
            self.initial.setdefault("start_event", first.pk)
