from django import forms
from django.contrib import admin
from django.template.response import TemplateResponse

from .models import (
    DRIVER_CHOICES,
    DuelChallenge,
    DuelSettings,
    Event,
    EventPhoto,
    HomeResultImage,
    Prediction,
    Result,
    Score,
    ScoreRevision,
    Season,
    SeasonPrediction,
    SeasonResult,
    SeasonScore,
    TelegramBotState,
    TelegramReminder,
    UserProfile,
)
from .scoring import (
    calculate_season_scores,
    preview_event_scores,
    publish_event_scores,
    restore_score_revision,
)


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
    list_display = ("season_year", "round_number", "name", "has_sprint", "status", "deadline")
    list_filter = ("season_year", "has_sprint", "status")
    search_fields = ("name",)
    inlines = [EventPhotoInline, ResultInline]
    fields = (
        "season_year",
        "name",
        "round_number",
        "has_sprint",
        "status",
        "deadline",
        "race_datetime",
        "cover_image",
    )

    actions = ["preview_and_publish_scores"]

    def preview_and_publish_scores(self, request, queryset):
        if "publish_confirmed" in request.POST:
            published = 0
            revisions = []
            for event in queryset:
                if not hasattr(event, "result"):
                    self.message_user(request, f"{event}: фактический результат не заполнен.", level="error")
                    continue
                revision, rows = publish_event_scores(event, request.user)
                revisions.append(f"R{event.round_number} v{revision.revision}")
                published += len(rows)
            if revisions:
                self.message_user(
                    request,
                    f"Результаты опубликованы: {', '.join(revisions)}. Пересчитано прогнозов: {published}.",
                )
            return None

        previews = [
            {
                "event": event,
                "has_result": hasattr(event, "result"),
                "rows": preview_event_scores(event),
            }
            for event in queryset
        ]
        context = {
            **self.admin_site.each_context(request),
            "title": "Проверка перед публикацией результатов",
            "previews": previews,
            "queryset": queryset,
            "action_checkbox_name": admin.helpers.ACTION_CHECKBOX_NAME,
        }
        return TemplateResponse(request, "admin/score_publish_preview.html", context)

    preview_and_publish_scores.short_description = "Проверить и опубликовать очки"


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ("year", "title", "is_active", "predictions_deadline")
    ordering = ("-year",)
    actions = ("make_active",)

    def make_active(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Выбери ровно один сезон.", level="error")
            return
        season = queryset.get()
        season.is_active = True
        season.save(update_fields=("is_active",))
        self.message_user(request, f"Активный сезон: {season}.")

    make_active.short_description = "Сделать выбранный сезон активным"


@admin.register(HomeResultImage)
class HomeResultImageAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "season_year", "is_active", "sort_order", "created_at")
    list_filter = ("season_year", "is_active")
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
        "sprint_qualifying_winner",
        "sprint_winner",
        "fastest_lap",
        "driver_of_day_multiple_display",
        "safety_car_count",
        "dnf_count",
        "published_at",
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
        "sprint_qualifying_winner",
        "sprint_winner",
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
    list_display = ("event", "user", "prediction_points", "duel_adjustment", "points")
    list_filter = ("event",)
    search_fields = ("user__username", "event__name")
    list_select_related = ("event", "user")


@admin.register(DuelChallenge)
class DuelChallengeAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "challenger",
        "opponent",
        "stake",
        "status",
        "winner",
        "created_at",
    )
    list_filter = ("status", "event__season_year", "event")
    search_fields = ("challenger__username", "opponent__username", "event__name")
    list_select_related = ("event", "challenger", "opponent", "winner")
    readonly_fields = (
        "status",
        "winner",
        "challenger_prediction_points",
        "opponent_prediction_points",
        "created_at",
        "updated_at",
        "responded_at",
        "settled_at",
    )


@admin.register(DuelSettings)
class DuelSettingsAdmin(admin.ModelAdmin):
    fields = ("cover_image", "updated_at")
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not DuelSettings.objects.exists()


@admin.register(ScoreRevision)
class ScoreRevisionAdmin(admin.ModelAdmin):
    list_display = ("event", "revision", "created_by", "created_at")
    list_filter = ("event__season_year", "event")
    readonly_fields = ("event", "revision", "scores", "created_by", "created_at")
    actions = ("restore_selected_revision",)

    def has_add_permission(self, request):
        return False

    def restore_selected_revision(self, request, queryset):
        restored = []
        for revision in queryset.select_related("event"):
            new_revision = restore_score_revision(revision, request.user)
            restored.append(f"{revision.event} → v{new_revision.revision}")
        self.message_user(request, "Восстановлено: " + ", ".join(restored))

    restore_selected_revision.short_description = "Восстановить выбранную версию"


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
    fieldsets = (
        (
            "Промежуточные итоги — можно заполнить после первой половины сезона",
            {
                "fields": (
                    "season_year",
                    "hungary_driver_championship_leader",
                    "hungary_constructor_championship_leader",
                    "hadjar_best_finish",
                ),
                "description": (
                    "Заполни эти поля после этапа Венгрии. "
                    "Финальные поля ниже можно оставить пустыми до завершения сезона."
                ),
            },
        ),
        (
            "Финальные итоги сезона — заполняются позднее",
            {
                "fields": (
                    "world_drivers_champion",
                    "constructors_champion",
                    "constructors_second",
                    "constructors_third",
                    "last_race_winner",
                    "season_pole_sitter",
                    "driver_change_happened",
                    "team_most_dnf",
                ),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        total = calculate_season_scores(obj.season_year)
        self.message_user(
            request,
            f"Сохранено. Текущие сезонные очки пересчитаны для {total} участников.",
        )

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
    list_display = (
        "user",
        "is_world_predict_champion",
        "telegram_chat_id",
        "telegram_notifications",
        "avatar",
        "updated_at",
    )
    list_filter = ("is_world_predict_champion", "telegram_notifications")
    list_editable = ("is_world_predict_champion",)
    search_fields = ("user__username",)
    list_select_related = ("user",)


@admin.register(TelegramReminder)
class TelegramReminderAdmin(admin.ModelAdmin):
    list_display = ("event", "user", "kind", "sent_at")
    list_filter = ("kind", "event")
    search_fields = ("event__name", "user__username")
    list_select_related = ("event", "user")


@admin.register(TelegramBotState)
class TelegramBotStateAdmin(admin.ModelAdmin):
    list_display = ("key", "update_offset", "updated_at")
    readonly_fields = ("key", "updated_at")
