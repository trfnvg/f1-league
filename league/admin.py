from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
import json
from .models import VegasSpin, VegasPurchase, VegasDailyGrant
from django.db import transaction
from django.db.models import DurationField, ExpressionWrapper, F
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import redirect
from django.urls import path, reverse
from django.template.response import TemplateResponse
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    ArcadeTrophyAward,
    ArcadeWheelSpin,
    DRIVER_CHOICES,
    DriverProfile,
    DuelChallenge,
    Event,
    EventPhoto,
    EventWildcardDeck,
    EventWildcardDeckCard,
    EventWildcardQuestion,
    HomeResultImage,
    PlayerWildcard,
    Prediction,
    RaceCalendarRound,
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
    DoodleAttempt,
    ArcadeAttempt,
    TetrisAttempt,
    MinesweeperAttempt,
    ArcadeBestVideo,
)
from .scoring import (
    calculate_season_scores,
    preview_event_scores,
    publish_event_scores,
    restore_score_revision,
)
from .wildcards import unresolved_wildcard_questions
from .identity import display_name


class HandleSearchMixin:
    def get_search_results(self, request, queryset, search_term):
        term = search_term.strip()
        if term.startswith("@"):
            term = term[1:]
        return super().get_search_results(request, queryset, term)


admin.site.unregister(User)


@admin.register(User)
class PlayerUserAdmin(HandleSearchMixin, UserAdmin):
    list_display = ("player_handle", "player_display_name", "email", "is_staff")
    list_display_links = ("player_handle",)
    list_select_related = ("league_profile",)
    search_fields = (*UserAdmin.search_fields, "league_profile__handle")
    search_help_text = "Имя, почта или логин — с @ или без него."
    readonly_fields = (*UserAdmin.readonly_fields, "player_handle")
    fieldsets = (
        (None, {"fields": ("username", "password", "player_handle")}),
        *UserAdmin.fieldsets[1:],
    )

    @admin.display(description="Логин", ordering="league_profile__handle")
    def player_handle(self, obj):
        profile = getattr(obj, "league_profile", None)
        return f"@{profile.handle}" if profile and profile.handle else "—"

    @admin.display(description="Имя", ordering="first_name")
    def player_display_name(self, obj):
        return display_name(obj)


@admin.register(DriverProfile)
class DriverProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "season_year", "team", "number")
    list_filter = ("season_year", "team")
    search_fields = ("name", "surname", "key")


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


class CircuitSelect(forms.Select):
    circuits = {}

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        circuit = self.circuits.get(str(value))
        if circuit:
            option["attrs"].update({
                "data-circuit-path": circuit["path"],
                "data-circuit-start-x": circuit["start_x"],
                "data-circuit-start-y": circuit["start_y"],
                "data-circuit-name": circuit["name"],
                "data-circuit-gp": circuit["grand_prix"],
                "data-circuit-labels": json.dumps([circuit["start_label"], *circuit["sector_labels"]]),
            })
        return option


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
        self.fields["name"].required = False
        self.fields["name"].help_text = "Можно оставить пустым: название подставится из выбранного Гран-при."
        if self.instance.pk and not self.instance.circuit and self.instance.circuit_visual:
            self.initial["circuit"] = self.instance.circuit_visual["key"]
        from .circuits import CIRCUITS
        self.fields["circuit"].widget = CircuitSelect(choices=self.fields["circuit"].choices)
        self.fields["circuit"].widget.circuits = CIRCUITS
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
        from .circuits import CIRCUITS
        if not cleaned_data.get("name"):
            circuit = CIRCUITS.get(cleaned_data.get("circuit"))
            if circuit:
                cleaned_data["name"] = circuit["grand_prix"]
            else:
                self.add_error("name", "Введите название или выберите Гран-при / трассу.")
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
    classes = ("wide", "race-result-inline")


class EventPredictionInline(admin.TabularInline):
    """Keep Crazy Prediction approvals beside the race result."""

    model = Prediction
    extra = 0
    fields = ("user", "crazy_prediction", "crazy_prediction_approved")
    readonly_fields = ("user", "crazy_prediction")
    ordering = ("user__username",)
    classes = ("wide", "crazy-predictions-inline")
    verbose_name = "Crazy Prediction"
    verbose_name_plural = "Crazy Predictions — проверка ответов"


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


@admin.register(RaceCalendarRound)
class RaceCalendarRoundAdmin(admin.ModelAdmin):
    list_display = ("season_year", "round_number", "title", "starts_on", "practice1_at", "race_at", "has_sprint")
    list_filter = ("season_year", "has_sprint")
    search_fields = ("title", "location", "circuit_name")
    ordering = ("-season_year", "round_number")
    autocomplete_fields = ("prediction_event",)
    actions = ("create_prediction_cards",)
    fieldsets = (
        ("Этап", {"fields": ("season_year", "round_number", "circuit", "title", "location", "country", "circuit_name", "cover_image", "has_sprint")}),
        ("Расписание", {"fields": ("starts_on", "ends_on", "venue_timezone", "practice1_at", "practice2_at", "practice3_at", "sprint_qualifying_at", "sprint_at", "qualifying_at", "race_at"),
            "description": "Даты уик-энда — местные. Время сессий вводится в часовом поясе админки (МСК). Необъявленное время оставьте пустым."}),
        ("Прогнозы и источники", {"fields": ("prediction_event", "source_url", "checked_on"),
            "description": "Недостающая карточка прогнозов создаётся при сохранении. Новые дедлайны — четверг, 23:59 МСК. Существующие карточки и дедлайны не меняются."}),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from .calendar_event_sync import sync_calendar_events_v1
        report = sync_calendar_events_v1(obj.season_year, round_ids=[obj.pk])
        if report["created"]:
            self.message_user(request, "Карточка прогнозов создана. Дедлайн — четверг перед уик-эндом, 23:59 МСК.")
        for conflict in report["conflicts"]:
            self.message_user(request, conflict, level="warning")

    @admin.action(description="Создать недостающие карточки прогнозов")
    def create_prediction_cards(self, request, queryset):
        from .calendar_event_sync import sync_calendar_events_v1
        created = linked = 0
        for year in queryset.order_by().values_list("season_year", flat=True).distinct():
            report = sync_calendar_events_v1(year, round_ids=list(queryset.filter(season_year=year).values_list("pk", flat=True)))
            created += report["created"]
            linked += report["linked"]
            for conflict in report["conflicts"]:
                self.message_user(request, conflict, level="warning")
        self.message_user(request, f"Создано карточек: {created}. Привязано к календарю: {linked}. Существующие данные сохранены.")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    form = EventAdminForm
    readonly_fields = ("circuit_preview",)
    list_display = (
        "season_year",
        "round_number",
        "name",
        "has_sprint",
        "status",
        "wildcard_deck_status",
        "deadline",
        "qualifying_datetime",
    )
    list_filter = ("season_year", "has_sprint", "status")
    search_fields = ("name",)
    inlines = [
        EventPhotoInline,
        ResultInline,
        EventWildcardQuestionInline,
        EventPredictionInline,
    ]
    fieldsets = (
        (
            "Этап",
            {
                "fields": (
                    "season_year",
                    "circuit",
                    "circuit_preview",
                    "name",
                    "round_number",
                    "has_sprint",
                    "status",
                    "deadline",
                    "qualifying_datetime",
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
        css = {"all": ("league/admin-wildcards.css", "league/circuit-visual.css", "league/admin-circuits.css")}
        js = ("league/admin-wildcards.js", "league/admin-circuits.js", "league/circuit-peloton.js")

    @admin.display(description="Схема трассы")
    def circuit_preview(self, obj):
        from django.template.loader import render_to_string
        from django.utils.safestring import mark_safe
        return mark_safe(render_to_string("admin/circuit_preview.html", {
            "circuit": obj.circuit_visual if obj else None,
        }))

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
class UserProfileAdmin(HandleSearchMixin, admin.ModelAdmin):
    list_display = (
        "user",
        "player_handle",
        "is_world_predict_champion",
        "telegram_chat_id",
        "telegram_notifications",
        "avatar",
        "updated_at",
    )
    list_filter = ("is_world_predict_champion", "telegram_notifications")
    list_editable = ("is_world_predict_champion",)
    search_fields = ("handle", "user__username", "user__first_name", "user__last_name", "user__email")
    list_select_related = ("user",)

    @admin.display(description="Логин", ordering="handle")
    def player_handle(self, obj):
        return f"@{obj.handle}" if obj.handle else "—"


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


def attempt_duration(milliseconds):
    if milliseconds is None or milliseconds < 0:
        return "—"
    seconds, ms = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{ms:03d}"


class AttemptStatusFilter(admin.SimpleListFilter):
    title = "Статус попытки"
    parameter_name = "run_status"

    def lookups(self, request, model_admin):
        return (("saved", "Результат сохранён"), ("unfinished", "Не завершена"),
                ("no_result", "Завершена без результата"))

    def queryset(self, request, queryset):
        if self.value() == "unfinished":
            return queryset.filter(finished_at__isnull=True)
        if self.value() in ("saved", "no_result"):
            queryset = queryset.filter(finished_at__isnull=False)
            if queryset.model is MinesweeperAttempt:
                return queryset.filter(completed=self.value() == "saved")
            return queryset.filter(score__isnull=self.value() == "no_result")
        return queryset


class ArcadeAttemptLogAdmin(HandleSearchMixin, admin.ModelAdmin):
    """Immutable game proof, with separate audited correction actions."""
    change_list_template = "admin/league/arcade_attempt_log.html"
    change_form_template = "admin/league/arcade_attempt_detail.html"
    list_display = ("id", "player", "run_result", "run_status", "start_time", "end_time", "wall_duration", "competition_label", "origin")
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__league_profile__handle")
    search_help_text = "Имя игрока или логин с @ или без него."
    ordering = ("-started_at", "-pk")
    date_hierarchy = "started_at"
    list_per_page = 50
    show_full_result_count = False
    actions = None

    def has_moderation_permission(self, request):
        return request.user.is_active and request.user.is_staff and request.user.has_perm(f"league.change_{self.model._meta.model_name}")

    def has_manual_permission(self, request):
        return self.has_moderation_permission(request) and request.user.has_perm(f"league.add_{self.model._meta.model_name}")

    def get_urls(self):
        name = self.model._meta.model_name
        return [path("manual/", self.admin_site.admin_view(self.manual_view), name=f"league_{name}_manual"),
                path("<int:attempt_id>/moderate/", self.admin_site.admin_view(self.moderate_view), name=f"league_{name}_moderate")] + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        context = dict(extra_context or {})
        if self.has_manual_permission(request):
            context["manual_url"] = reverse(f"admin:league_{self.model._meta.model_name}_manual")
        return super().changelist_view(request, extra_context=context)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        context = dict(extra_context or {})
        if object_id and self.has_moderation_permission(request):
            obj = self.get_object(request, object_id)
            if obj:
                context.update(moderation_url=reverse(f"admin:league_{self.model._meta.model_name}_moderate", args=[obj.pk]),
                    moderation_label="Вернуть в зачёт" if obj.is_excluded else "Исключить из зачёта")
        return super().changeform_view(request, object_id, form_url, context)

    def manual_view(self, request):
        from .arcade_admin_forms import ManualAttemptForm
        from .arcade_moderation import create_manual
        if not self.has_manual_permission(request):
            raise PermissionDenied
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        form = ManualAttemptForm(request.POST if request.method == "POST" else None, model=self.model)
        if request.method == "POST" and form.is_valid():
            try:
                obj = create_manual(actor=request.user, model=self.model, **form.cleaned_data)
            except ValidationError as error:
                form.add_error(None, error)
            else:
                self.message_user(request, "Ручная попытка добавлена. Рейтинги обновлены.")
                return redirect(f"admin:league_{self.model._meta.model_name}_change", obj.pk)
        return self.management_page(request, form, "Добавить попытку вручную", "Добавить в зачёт")

    def moderate_view(self, request, attempt_id):
        from .arcade_admin_forms import ModerateAttemptForm
        from .arcade_moderation import set_excluded
        if not self.has_moderation_permission(request):
            raise PermissionDenied
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        obj = self.get_object(request, str(attempt_id))
        if obj is None:
            raise Http404
        form = ModerateAttemptForm(request.POST if request.method == "POST" else None,
            initial={"excluded":"0" if obj.is_excluded else "1"})
        title = "Вернуть попытку в зачёт" if obj.is_excluded else "Исключить попытку из зачёта"
        if request.method == "POST" and form.is_valid():
            try:
                set_excluded(actor=request.user, model=self.model, attempt_id=obj.pk, **form.cleaned_data)
            except ValidationError as error:
                form.add_error(None, error)
            else:
                self.message_user(request, "Статус попытки изменён. Рейтинги обновлены.")
                return redirect(f"admin:league_{self.model._meta.model_name}_change", obj.pk)
        return self.management_page(request, form, title, "Подтвердить", obj)

    def management_page(self, request, form, title, submit_label, obj=None):
        return TemplateResponse(request, "admin/league/arcade_attempt_manage.html", {
            **self.admin_site.each_context(request), "opts":self.model._meta, "form":form,
            "title":title, "submit_label":submit_label, "attempt":obj,
            "back_url":reverse(f"admin:league_{self.model._meta.model_name}_changelist")})

    def get_queryset(self, request):
        related = ["user", "user__league_profile"]
        if self.model is not MinesweeperAttempt:
            related.append("competition__event")
        large_fields = [field.name for field in self.model._meta.fields if field.name in {"verification", "replay"}]
        return super().get_queryset(request).select_related(*related).defer(*large_fields).annotate(
            server_duration=ExpressionWrapper(F("finished_at") - F("started_at"), output_field=DurationField()))

    def get_list_filter(self, request):
        return (AttemptStatusFilter, "is_excluded", "is_manual", "started_at", "week_start" if self.model is MinesweeperAttempt else "competition__event")

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields) + (
            "player", "run_result", "run_status", "start_time", "end_time", "wall_duration", "active_duration", "competition_label", "attempt_video")

    def get_fieldsets(self, request, obj=None):
        return (
            ("Попытка", {"fields": ("id", "player", "run_result", "run_status", "competition_label")}),
            ("Время", {"fields": ("start_time", "end_time", "wall_duration", "active_duration"),
                "description": "Серверная длительность включает паузы и ожидание отправки результата. Игровое время доступно только там, где оно сохраняется отдельно."}),
            ("Корректировки", {"fields": ("is_manual", "is_excluded", "moderation_note", "moderated_by", "moderated_at")}),
            ("Видео попытки", {"fields": ("attempt_video",)}),
            ("Технические данные", {"classes": ("collapse",), "fields": tuple(
                field.name for field in self.model._meta.fields if field.name != "id")}),
        )

    @admin.display(description="Игрок", ordering="user__username")
    def player(self, obj):
        profile = getattr(obj.user, "league_profile", None)
        handle = profile.handle if profile and profile.handle else obj.user.username
        return f"{display_name(obj.user)} · @{handle}"

    @admin.display(description="Результат")
    def run_result(self, obj):
        if isinstance(obj, MinesweeperAttempt):
            return attempt_duration(obj.elapsed_ms) if obj.completed else "—"
        return f"{obj.score} очк." if obj.score is not None else "—"

    @admin.display(description="Статус")
    def run_status(self, obj):
        if obj.is_excluded:
            return "Исключена из зачёта"
        if obj.finished_at is None:
            return "Не завершена"
        if isinstance(obj, MinesweeperAttempt):
            return "Поле пройдено" if obj.completed else "Поле не пройдено"
        return "Результат сохранён" if obj.score is not None else "Результат не принят"

    @admin.display(description="Начало", ordering="started_at")
    def start_time(self, obj):
        return obj.started_at

    @admin.display(description="Завершение", ordering="finished_at")
    def end_time(self, obj):
        return obj.finished_at

    @admin.display(description="Длительность (сервер)", ordering="server_duration")
    def wall_duration(self, obj):
        if obj.finished_at is None:
            return "—"
        return attempt_duration((obj.finished_at - obj.started_at).total_seconds() * 1000)

    @admin.display(description="Игровое время")
    def active_duration(self, obj):
        if isinstance(obj, TetrisAttempt) and not obj.is_manual and obj.score is not None and obj.finished_at:
            return attempt_duration(obj.ticks * 1000 / 60)
        if isinstance(obj, MinesweeperAttempt) and obj.completed:
            return attempt_duration(obj.elapsed_ms)
        return "—"

    @admin.display(description="Источник", ordering="is_manual")
    def origin(self, obj):
        return "Добавлена администратором" if obj.is_manual else "Игра игрока"

    @admin.display(description="Видеозапись")
    def attempt_video(self, obj):
        from .arcade_moderation import GAME_MODELS
        return video_player(ArcadeBestVideo.objects.filter(user_id=obj.user_id,
            game_key=GAME_MODELS[self.model], attempt_id=obj.pk).first())

    @admin.display(description="Зачёт")
    def competition_label(self, obj):
        if isinstance(obj, MinesweeperAttempt):
            return f"Неделя с {obj.week_start:%d.%m.%Y}"
        if obj.competition_id:
            event = obj.competition.event
            return f"R{event.round_number:02d} · {event.name} · {event.season_year}"
        return "Без привязки к этапу"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register((ArcadeAttempt, DoodleAttempt, TetrisAttempt, MinesweeperAttempt), ArcadeAttemptLogAdmin)


@admin.register(ArcadeBestVideo)
class ArcadeBestVideoAdmin(HandleSearchMixin, admin.ModelAdmin):
    list_display = ("user", "game_key", "score", "attempt_id", "duration", "updated_at")
    list_filter = ("game_key", "updated_at")
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__league_profile__handle")
    list_select_related = ("user",)
    readonly_fields = ("user", "game_key", "score", "attempt_id", "duration", "size", "updated_at", "player")
    fields = readonly_fields
    ordering = ("-updated_at",)

    @admin.display(description="Видео")
    def player(self, obj):
        return video_player(obj)

    @admin.display(description="Длительность")
    def duration(self, obj):
        return attempt_duration(obj.duration_ms)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


def video_player(video):
    if not video or not video.video:
        return "Видео не сохранено: старая попытка, ручной результат или браузер не завершил запись/загрузку."
    return format_html('<video controls preload="metadata" playsinline style="max-width:100%;width:560px;max-height:75vh" src="{}"></video><p><a href="{}" target="_blank" rel="noopener">Открыть видео по прямой ссылке</a></p>', video.video.url, video.video.url)


@admin.register(VegasPurchase)
class VegasPurchaseAdmin(admin.ModelAdmin):
    list_display = ("id", "wallet", "product", "cost", "purchased_at", "activated_at", "league_season", "target")
    list_select_related = ("wallet", "league_season", "target")
    list_filter = ("product", "league_season", "activated_at")
    search_fields = ("wallet__user__username", "wallet__user__first_name")
    readonly_fields = tuple(field.name for field in VegasPurchase._meta.fields)
    ordering = ("-purchased_at", "-pk")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(VegasDailyGrant)
class VegasDailyGrantAdmin(VegasPurchaseAdmin):
    list_display = ("id", "user", "wallet", "day", "amount", "created_at")
    list_select_related = ("user", "wallet")
    list_filter = ("day",)
    search_fields = ("user__username", "user__first_name")
    readonly_fields = tuple(field.name for field in VegasDailyGrant._meta.fields)
    ordering = ("-created_at", "-pk")


@admin.register(VegasSpin)
class VegasSpinAdmin(admin.ModelAdmin):
    list_display = ("id", "player", "event", "created_at", "action", "bet", "balance_before", "balance_after")
    list_select_related = ("wallet__user", "wallet__competition__event")
    list_filter = ("action", "wallet__competition__event", "created_at")
    search_fields = ("wallet__user__username", "wallet__user__first_name")
    readonly_fields = tuple(field.name for field in VegasSpin._meta.fields)
    ordering = ("-created_at", "-pk")

    @admin.display(description="Игрок")
    def player(self, obj):
        return obj.wallet.user

    @admin.display(description="Этап")
    def event(self, obj):
        return obj.wallet.competition.event if obj.wallet.competition_id else "Свободная игра"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ArcadeTrophyAward)
class ArcadeTrophyAwardAdmin(admin.ModelAdmin):
    list_display = ("player", "trophy_name", "game_name", "event", "attempts", "awarded_at")
    list_filter = ("game_name", "event__season_year", "awarded_at")
    search_fields = ("player__username", "trophy_name", "game_name", "event__name")
    list_select_related = ("player", "event")
    date_hierarchy = "awarded_at"
    ordering = ("-awarded_at", "-pk")
    fields = (
        "player",
        "game_name",
        "game_key",
        "trophy_name",
        "image",
        "event",
        "attempts",
        "awarded_at",
    )


@admin.register(ArcadeWheelSpin)
class ArcadeWheelSpinAdmin(admin.ModelAdmin):
    list_display = ("event", "winner", "winner_score", "prize", "target_user", "spun_at", "activated_at")
    list_filter = ("prize", "event__season_year", "activated_at")
    search_fields = ("winner__username", "target_user__username", "event__name")
    list_select_related = ("event", "winner", "target_user")
    readonly_fields = tuple(field.name for field in ArcadeWheelSpin._meta.fields)
    ordering = ("-spun_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
