from django import forms
from django.contrib import admin

from .models import (
    DRIVER_CHOICES,
    Event,
    EventPhoto,
    HomeResultImage,
    Prediction,
    Result,
    Score,
    SeasonPrediction,
    SeasonResult,
    SeasonScore,
    UserProfile,
)
from .scoring import calculate_event_scores, calculate_season_scores


class ResultAdminForm(forms.ModelForm):
    driver_of_day_multi = forms.MultipleChoiceField(
        label="Driver of the Day (факт, можно несколько)",
        required=False,
        choices=DRIVER_CHOICES,
        widget=forms.SelectMultiple(attrs={"size": 8}),
        help_text="Выбери одного или нескольких пилотов.",
    )

    class Meta:
        model = Result
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        initial_values = []
        if self.instance and self.instance.pk:
            initial_values = list(self.instance.driver_of_day_multiple or [])
            if not initial_values and self.instance.driver_of_day:
                initial_values = [self.instance.driver_of_day]
        self.fields["driver_of_day_multi"].initial = initial_values

        # Legacy single field is kept for compatibility and backfill
        self.fields["driver_of_day"].widget = forms.HiddenInput()
        self.fields["driver_of_day"].required = False
        self.fields["driver_of_day_multiple"].widget = forms.HiddenInput()
        self.fields["driver_of_day_multiple"].required = False

    def clean_driver_of_day_multi(self):
        values = self.cleaned_data.get("driver_of_day_multi") or []
        unique_values = []
        seen = set()
        for value in values:
            if value and value not in seen:
                seen.add(value)
                unique_values.append(value)
        return unique_values

    def save(self, commit=True):
        instance = super().save(commit=False)
        selected = self.cleaned_data.get("driver_of_day_multi") or []
        instance.driver_of_day_multiple = selected
        instance.driver_of_day = selected[0] if selected else ""

        if commit:
            instance.save()
            self.save_m2m()

        return instance


class EventPhotoInline(admin.TabularInline):
    model = EventPhoto
    extra = 1


class ResultInline(admin.StackedInline):
    model = Result
    form = ResultAdminForm
    extra = 0
    max_num = 1


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
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


@admin.register(HomeResultImage)
class HomeResultImageAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "is_active", "sort_order", "created_at")
    list_filter = ("is_active",)
    list_editable = ("is_active", "sort_order")
    search_fields = ("title", "caption")
    ordering = ("sort_order", "-created_at")


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    form = ResultAdminForm
    list_display = (
        "event",
        "p1",
        "p2",
        "p3",
        "pole",
        "fastest_lap",
        "driver_of_day_multiple_display",
        "safety_car_count",
        "dnf_count",
    )
    search_fields = ("event__name",)
    list_select_related = ("event",)

    def driver_of_day_multiple_display(self, obj):
        values = obj.driver_of_day_multiple or ([obj.driver_of_day] if obj.driver_of_day else [])
        labels = dict(DRIVER_CHOICES)
        return ", ".join(labels.get(value, value) for value in values) if values else "-"

    driver_of_day_multiple_display.short_description = "Driver of the Day"


@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "user",
        "p1",
        "p2",
        "p3",
        "pole",
        "fastest_lap",
        "driver_of_day",
        "safety_car_count",
        "dnf_count",
        "crazy_prediction_approved",
        "created_at",
    )
    list_filter = ("event", "user", "crazy_prediction_approved")
    list_editable = ("crazy_prediction_approved",)
    search_fields = ("event__name", "user__username", "crazy_prediction")
    list_select_related = ("event", "user")
    ordering = ("-created_at",)


@admin.register(Score)
class ScoreAdmin(admin.ModelAdmin):
    list_display = ("event", "user", "points")
    list_filter = ("event",)
    search_fields = ("user__username", "event__name")
    list_select_related = ("event", "user")


@admin.register(SeasonPrediction)
class SeasonPredictionAdmin(admin.ModelAdmin):
    list_display = (
        "season_year",
        "user",
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
        "updated_at",
    )
    list_filter = ("season_year", "driver_change_happened", "constructors_champion")
    search_fields = ("user__username",)
    list_select_related = ("user",)


@admin.register(SeasonResult)
class SeasonResultAdmin(admin.ModelAdmin):
    list_display = (
        "season_year",
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
        "updated_at",
    )
    actions = ("recalculate_season_scores",)

    def recalculate_season_scores(self, request, queryset):
        total = 0
        seasons = 0
        for season_result in queryset:
            total += calculate_season_scores(season_result.season_year)
            seasons += 1

        self.message_user(request, f"Пересчитано сезонных прогнозов: {total} (сезонов: {seasons})")

    recalculate_season_scores.short_description = "Посчитать сезонные очки"


@admin.register(SeasonScore)
class SeasonScoreAdmin(admin.ModelAdmin):
    list_display = ("season_year", "user", "points", "updated_at")
    list_filter = ("season_year",)
    search_fields = ("user__username",)
    list_select_related = ("user",)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "is_world_predict_champion", "avatar", "updated_at")
    list_filter = ("is_world_predict_champion",)
    list_editable = ("is_world_predict_champion",)
    search_fields = ("user__username",)
    list_select_related = ("user",)
