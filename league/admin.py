from django.contrib import admin
from django import forms
from .scoring import calculate_event_scores
from .models import Event, EventPhoto, Prediction, Result, Score


class EventAdminForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = "__all__"
        widgets = {
            "deadline": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "race_datetime": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        dt_input = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]
        self.fields["deadline"].input_formats = dt_input
        self.fields["race_datetime"].input_formats = dt_input
        self.fields["deadline"].help_text = "Точная дата и время закрытия предиктов."


class EventPhotoInline(admin.TabularInline):
    model = EventPhoto
    extra = 1

class ResultInline(admin.StackedInline):
    model = Result
    extra = 0
    max_num = 1

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    form = EventAdminForm
    list_display = ("round_number", "name", "status", "deadline")
    list_filter = ("status",)
    search_fields = ("name",)
    inlines = [EventPhotoInline, ResultInline]
    fields = ("name", "round_number", "status", "deadline", "race_datetime", "cover_image")

    actions = ["recalculate_scores"]

    def recalculate_scores(self, request, queryset):
        total = 0
        for event in queryset:
            total += calculate_event_scores(event)

        self.message_user(request, f"Пересчитано прогнозов: {total}")

    recalculate_scores.short_description = "Посчитать очки"

@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ("event", "p1", "p2", "p3", "pole")
    search_fields = ("event__name",)
    list_select_related = ("event",)


@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = ("event", "user", "p1", "p2", "p3", "pole", "created_at")
    list_filter = ("event", "user")
    search_fields = ("event__name", "user__username")
    list_select_related = ("event", "user")
    ordering = ("-created_at",)


@admin.register(Score)
class ScoreAdmin(admin.ModelAdmin):
    list_display = ("event", "user", "points")
    list_filter = ("event",)
    search_fields = ("user__username", "event__name")
    list_select_related = ("event", "user")
