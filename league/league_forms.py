from io import BytesIO
from uuid import uuid4

from django import forms
from django.core.files.base import ContentFile
from PIL import Image, ImageOps
from django.utils import timezone

from .models import DRIVER_CHOICES, Event, League, LeagueSeason


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


class LeagueProfileForm(forms.ModelForm):
    class Meta:
        model = League
        fields = ("name", "avatar")

    def clean_avatar(self):
        upload = self.cleaned_data.get("avatar")
        if not upload or not hasattr(upload, "content_type"):
            return upload
        if upload.size > 5*1024*1024:
            raise forms.ValidationError("Размер изображения — не больше 5 МБ.")
        try:
            upload.seek(0)
            with Image.open(upload) as original:
                if original.format not in {"JPEG", "PNG", "WEBP"} or max(original.size) > 4096:
                    raise ValueError
                # Logos need their complete silhouette and PNG transparency,
                # not the centre-cover crop used for player portraits.
                logo = ImageOps.contain(
                    ImageOps.exif_transpose(original).convert("RGBA"),
                    (512, 512), Image.Resampling.LANCZOS,
                )
                image = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
                image.alpha_composite(logo, ((512 - logo.width) // 2, (512 - logo.height) // 2))
                output = BytesIO();image.save(output, "WEBP", lossless=True)
            return ContentFile(output.getvalue(), name=f"{uuid4().hex}.webp")
        except (OSError, ValueError, Image.DecompressionBombError):
            raise forms.ValidationError("Загрузите PNG, JPEG или WebP размером до 4096 × 4096.")


class LeagueDayForm(forms.Form):
    use_official = forms.BooleanField(label="Использовать официальный результат", required=False, initial=True)
    drivers = forms.MultipleChoiceField(label="Гонщик дня в этой лиге", choices=DRIVER_CHOICES,
        required=False, widget=forms.CheckboxSelectMultiple)
