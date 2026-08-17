from django import forms
from django.contrib import admin
from django.db import transaction
from django.template.response import TemplateResponse
from django.utils.html import format_html

from .models import (
    DRIVER_CHOICES,
    DuelChallenge,
    DuelSettings,
    Event,
    EventPhoto,
    EventWildcardDeck,
    EventWildcardDeckCard,
    EventWildcardQuestion,
    HomeResultImage,
    PlayerWildcard,
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
    WildcardCardTemplate,
    WildcardSettings,
)
from .scoring import (
    calculate_season_scores,
    preview_event_scores,
    publish_event_scores,
    restore_score_revision,
)
from .wildcards import unresolved_wildcard_questions


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


class WildcardTemplateSelect(forms.Select):
    """Expose card copy to the admin preview without an extra request."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        card = getattr(value, "instance", None)
        if card is not None:
            option["attrs"].update(
                {
                    "data-card-title": card.title,
                    "data-card-question": card.question,
                    "data-card-option-a": card.option_a,
                    "data-card-option-b": card.option_b,
                    "data-card-option-c": card.option_c,
                }
            )
        return option


class WildcardTemplateChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, card):
        state = "" if card.is_active else " · неактивна"
        return f"{card.title} — {card.question}{state}"


class EventAdminForm(forms.ModelForm):
    wildcard_field_names = ("wildcard_card_1", "wildcard_card_2", "wildcard_card_3")

    wildcard_card_1 = WildcardTemplateChoiceField(
        label="Карта 1",
        queryset=WildcardCardTemplate.objects.none(),
        required=False,
        widget=WildcardTemplateSelect,
        empty_label="Выбери первую карту",
    )
    wildcard_card_2 = WildcardTemplateChoiceField(
        label="Карта 2",
        queryset=WildcardCardTemplate.objects.none(),
        required=False,
        widget=WildcardTemplateSelect,
        empty_label="Выбери вторую карту",
    )
    wildcard_card_3 = WildcardTemplateChoiceField(
        label="Карта 3",
        queryset=WildcardCardTemplate.objects.none(),
        required=False,
        widget=WildcardTemplateSelect,
        empty_label="Выбери третью карту",
    )

    class Meta:
        model = Event
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cards = WildcardCardTemplate.objects.order_by("title", "id")
        for field_name in self.wildcard_field_names:
            self.fields[field_name].queryset = cards

        if self.instance and self.instance.pk:
            for slot, template_id in enumerate(self._current_template_ids(), start=1):
                if template_id:
                    self.fields[f"wildcard_card_{slot}"].initial = template_id

    def _current_template_ids(self):
        if not self.instance or not self.instance.pk:
            return []
        return list(
            EventWildcardDeckCard.objects.filter(deck__event=self.instance)
            .order_by("slot")
            .values_list("question__source_card_id", flat=True)
        )

    def selected_wildcard_cards(self):
        return [self.cleaned_data.get(field_name) for field_name in self.wildcard_field_names]

    def clean(self):
        cleaned_data = super().clean()
        selected_cards = self.selected_wildcard_cards()
        selected_count = sum(card is not None for card in selected_cards)

        if selected_count not in (0, 3):
            raise forms.ValidationError("Выбери все три карты этапа — по одной карте в каждом слоте.")

        selected_ids = [card.pk for card in selected_cards if card is not None]
        if len(selected_ids) != len(set(selected_ids)):
            raise forms.ValidationError("В тройке не должно быть одинаковых карт.")

        if selected_ids and self.instance and self.instance.pk:
            current_ids = [item for item in self._current_template_ids() if item]
            if current_ids != selected_ids and self.instance.player_wildcards.exists():
                raise forms.ValidationError(
                    "Состав карт уже нельзя изменить: хотя бы один игрок выбрал карту на этом этапе."
                )
        return cleaned_data

    @transaction.atomic
    def sync_wildcard_cards(self):
        if not self.instance.pk:
            return

        selected_cards = self.selected_wildcard_cards()
        if not all(selected_cards):
            return

        current_ids = [item for item in self._current_template_ids() if item]
        selected_ids_in_order = [card.pk for card in selected_cards]
        if current_ids == selected_ids_in_order:
            return

        # The form already explains this case. The second check closes the
        # small race between validation and save without rewriting live picks.
        if self.instance.player_wildcards.exists():
            return

        selected_ids = set(selected_ids_in_order)
        assignments = {
            item.source_card_id: item
            for item in self.instance.wildcard_questions.exclude(source_card=None)
        }

        selected_assignments = []
        for slot, card in enumerate(selected_cards, start=1):
            assignment = assignments.get(card.id)
            if assignment:
                EventWildcardQuestion.objects.filter(pk=assignment.pk).update(
                    is_active=True,
                    sort_order=slot,
                )
            else:
                assignment = EventWildcardQuestion.objects.create(
                    event=self.instance,
                    source_card=card,
                    question=card.question,
                    option_a=card.option_a,
                    option_b=card.option_b,
                    option_c=card.option_c,
                    draw_weight=card.draw_weight,
                    sort_order=slot,
                )
            selected_assignments.append(assignment)

        # Offers without a final player choice contain no gameplay data. Drop
        # them so every player receives the newly selected shared trio.
        self.instance.wildcard_offers.all().delete()
        deck, _ = EventWildcardDeck.objects.get_or_create(event=self.instance)
        deck.cards.all().delete()
        EventWildcardDeckCard.objects.bulk_create(
            [
                EventWildcardDeckCard(deck=deck, question=assignment, slot=slot)
                for slot, assignment in enumerate(selected_assignments, start=1)
            ]
        )

        for card_id, assignment in assignments.items():
            if card_id in selected_ids:
                continue
            if assignment.draws.exists():
                EventWildcardQuestion.objects.filter(pk=assignment.pk).update(is_active=False)
            else:
                assignment.delete()


class EventPhotoInline(admin.TabularInline):
    model = EventPhoto
    extra = 1


class ResultInline(admin.StackedInline):
    model = Result
    form = ResultAdminForm
    extra = 0
    max_num = 1


class EventWildcardQuestionInline(admin.TabularInline):
    model = EventWildcardQuestion
    extra = 0
    can_delete = False
    readonly_fields = ("source_card", "card_preview", "points")
    fields = (
        "sort_order",
        "source_card",
        "card_preview",
        "points",
        "is_active",
        "correct_option",
    )
    ordering = ("sort_order", "id")

    @admin.display(description="Содержание карты")
    def card_preview(self, obj):
        if not obj or not obj.pk:
            return "—"
        return format_html(
            "<strong>{}</strong><br><small>A: {} · B: {}</small>",
            obj.question,
            obj.option_a,
            format_html("{}{}", obj.option_b, format_html(" · C: {}", obj.option_c) if obj.option_c else ""),
        )


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    form = EventAdminForm
    list_display = (
        "season_year",
        "round_number",
        "name",
        "has_sprint",
        "status",
        "wildcard_deck_status",
        "deadline",
    )
    list_filter = ("season_year", "has_sprint", "status")
    search_fields = ("name",)
    inlines = [EventPhotoInline, EventWildcardQuestionInline, ResultInline]
    fieldsets = (
        (
            "Этап",
            {
                "fields": (
                    "season_year",
                    "name",
                    "round_number",
                    "has_sprint",
                    "status",
                    "deadline",
                    "race_datetime",
                    "cover_image",
                ),
            },
        ),
        (
            "Три карты для всех игроков",
            {
                "fields": ("wildcard_card_1", "wildcard_card_2", "wildcard_card_3"),
                "classes": ("wide", "wildcard-deck-fieldset"),
                "description": (
                    "Выбери ровно три разные карты из библиотеки. Они появятся у всех игроков "
                    "в указанном порядке. После первого выбора игрока тройка блокируется."
                ),
            },
        ),
    )

    class Media:
        css = {"all": ("league/admin-wildcards.css",)}
        js = ("league/admin-wildcards.js",)

    actions = ["preview_and_publish_scores"]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.sync_wildcard_cards()

    @admin.display(description="Карты")
    def wildcard_deck_status(self, obj):
        card_count = EventWildcardDeckCard.objects.filter(deck__event=obj).count()
        state = "is-ready" if card_count == 3 else "is-missing"
        label = "3 / 3" if card_count == 3 else "Не выбраны"
        return format_html('<span class="wildcard-deck-status {}">{}</span>', state, label)

    def preview_and_publish_scores(self, request, queryset):
        if "publish_confirmed" in request.POST:
            published = 0
            revisions = []
            for event in queryset:
                if not hasattr(event, "result"):
                    self.message_user(request, f"{event}: фактический результат не заполнен.", level="error")
                    continue
                try:
                    revision, rows = publish_event_scores(event, request.user)
                except ValueError as exc:
                    self.message_user(request, f"{event}: {exc}", level="error")
                    continue
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
                "wildcard_pending": list(unresolved_wildcard_questions(event)),
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


@admin.register(WildcardSettings)
class WildcardSettingsAdmin(admin.ModelAdmin):
    fields = ("card_back_image", "updated_at")
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        return not WildcardSettings.objects.exists()


@admin.register(WildcardCardTemplate)
class WildcardCardTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "question",
        "option_a",
        "option_b",
        "option_c",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active",)
    list_editable = ("is_active",)
    search_fields = ("title", "question", "option_a", "option_b", "option_c")
    ordering = ("title", "id")
    fieldsets = (
        (
            "Карточка",
            {
                "fields": (
                    "title",
                    "question",
                    "option_a",
                    "option_b",
                    "option_c",
                    "is_active",
                ),
                "description": "Создай карту один раз, затем выбирай её в настройках любого этапа.",
            },
        ),
    )


@admin.register(EventWildcardQuestion)
class EventWildcardQuestionAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "source_card",
        "question",
        "option_a",
        "option_b",
        "option_c",
        "points",
        "is_active",
        "correct_option",
    )
    list_filter = ("event__season_year", "event", "is_active")
    list_editable = ("is_active", "correct_option")
    search_fields = ("event__name", "question", "option_a", "option_b", "option_c")
    list_select_related = ("event", "source_card")
    ordering = ("-event__season_year", "event__round_number", "sort_order", "id")
    readonly_fields = ("points",)


class EventWildcardDeckCardInline(admin.TabularInline):
    model = EventWildcardDeckCard
    extra = 0
    can_delete = False
    fields = ("slot", "question")
    readonly_fields = ("slot", "question")
    ordering = ("slot",)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(EventWildcardDeck)
class EventWildcardDeckAdmin(admin.ModelAdmin):
    list_display = ("event", "created_at")
    list_filter = ("event__season_year",)
    search_fields = ("event__name",)
    readonly_fields = ("event", "created_at")
    inlines = (EventWildcardDeckCardInline,)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_model_perms(self, request):
        """The shared deck is managed from the event form, not as a second UI."""
        return {}


@admin.register(PlayerWildcard)
class PlayerWildcardAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "user",
        "question",
        "selected_option",
        "card_slot",
        "drawn_at",
        "answered_at",
    )
    list_filter = ("event__season_year", "event", "selected_option")
    search_fields = ("event__name", "user__username", "question__question")
    list_select_related = ("event", "user", "question")
    readonly_fields = (
        "event",
        "user",
        "question",
        "card_slot",
        "selected_option",
        "drawn_at",
        "answered_at",
    )

    def has_add_permission(self, request):
        return False


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
