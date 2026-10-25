import uuid
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

DRIVER_CHOICES = [
    ("norris", "Норрис (McLaren)"),
    ("piastri", "Пиастри (McLaren)"),
    ("russell", "Рассел (Mercedes)"),
    ("antonelli", "Антонелли (Mercedes)"),
    ("verstappen", "Ферстаппен (Red Bull)"),
    ("hadjar", "Хаджар (Red Bull)"),
    ("leclerc", "Леклер (Ferrari)"),
    ("hamilton", "Хэмильтон (Ferrari)"),
    ("albon", "Албон (Williams)"),
    ("sainz", "Сайнс (Williams)"),
    ("lindblad", "Линдблад (Racing Bulls)"),
    ("lawson", "Лоусон (Racing Bulls)"),
    ("stroll", "Стролл (Aston Martin)"),
    ("alonso", "Алонсо (Aston Martin)"),
    ("ocon", "Окон (Haas)"),
    ("bearman", "Берман (Haas)"),
    ("hulkenberg", "Хюлкенберг (Audi)"),
    ("bortoleto", "Бортолето (Audi)"),
    ("gasly", "Гасли (Alpine)"),
    ("colapinto", "Колапинто (Alpine)"),
    ("perez", "Перес (Cadillac)"),
    ("bottas", "Боттас (Cadillac)"),
]

CONSTRUCTOR_CHOICES = [
    ("mclaren", "McLaren"),
    ("mercedes", "Mercedes"),
    ("red_bull", "Red Bull"),
    ("ferrari", "Ferrari"),
    ("williams", "Williams"),
    ("racing_bulls", "Racing Bulls"),
    ("aston_martin", "Aston Martin"),
    ("haas", "Haas"),
    ("audi", "Audi"),
    ("alpine", "Alpine"),
    ("cadillac", "Cadillac"),
]

YES_NO_CHOICES = [
    ("yes", "Да"),
    ("no", "Нет"),
]


class Season(models.Model):
    year = models.PositiveSmallIntegerField("Год", unique=True)
    title = models.CharField("Название", max_length=120, blank=True)
    is_active = models.BooleanField("Активный сезон", default=False)
    predictions_deadline = models.DateTimeField("Дедлайн сезонных предиктов", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-year",)
        verbose_name = "Сезон"
        verbose_name_plural = "Сезоны"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            Season.objects.exclude(pk=self.pk).filter(is_active=True).update(is_active=False)

    @classmethod
    def get_active(cls):
        season = cls.objects.filter(is_active=True).first()
        if season:
            return season
        season = cls.objects.order_by("-year").first()
        if season is None:
            year = timezone.localdate().year
            season = cls.objects.create(
                year=year,
                title=f"F1 Predictions {year}",
                is_active=True,
            )
        else:
            season.is_active = True
            season.save(update_fields=("is_active",))
        return season

    def __str__(self):
        return self.title or f"Сезон {self.year}"


class Event(models.Model):
    season_year = models.PositiveSmallIntegerField("Сезон", default=2026, db_index=True)
    name = models.CharField("Название этапа", max_length=120)
    round_number = models.PositiveIntegerField("Раунд")
    deadline = models.DateTimeField("Дедлайн предиктов")
    qualifying_datetime = models.DateTimeField("Время окончания квалификации", null=True, blank=True)
    race_datetime = models.DateTimeField("Дата/время гонки", null=True, blank=True)
    crazy_vote_closed_at = models.DateTimeField(
        "Время досрочного закрытия Paddock Jury",
        null=True,
        blank=True,
    )
    crazy_vote_veto_cancelled_at = models.DateTimeField("Отмена исключения Paddock Jury", null=True, blank=True)
    crazy_vote_veto_cancelled_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="cancelled_crazy_exclusions", verbose_name="Кто отменил исключение",
    )
    has_sprint = models.BooleanField("Есть спринт", default=False)
    cover_image = models.ImageField("Обложка", upload_to="event_covers/", blank=True, null=True, max_length=255)

    class Status(models.TextChoices):
        OPEN = "open", "Открыто"
        LOCKED = "locked", "Закрыто"
        SCORED = "scored", "Очки посчитаны"

    status = models.CharField("Статус", max_length=10, choices=Status.choices, default=Status.OPEN)

    class Meta:
        ordering = ["season_year", "round_number"]
        constraints = [
            models.UniqueConstraint(
                fields=("season_year", "round_number"),
                name="unique_event_round_per_season",
            )
        ]

    def __str__(self):
        return f"R{self.round_number} - {self.name}"

    def voting_state(self):
        """
        returns: 'soon' | 'open' | 'closed' | 'scored'
        """
        if self.status == self.Status.SCORED:
            return "scored"
        if self.status == self.Status.LOCKED:
            return "closed"

        now = timezone.now()

        # if race_datetime not set, fallback to deadline
        base = self.race_datetime or self.deadline
        if base is None or self.deadline is None:
            return "closed"

        open_at = base - timedelta(days=7)

        if now < open_at:
            return "soon"
        if now <= self.deadline:
            return "open"
        return "closed"


class League(models.Model):
    """A private group; ownership never grants site-wide Django staff rights."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField("Название лиги", max_length=80)
    avatar = models.ImageField("Аватар лиги", upload_to="league_avatars/", blank=True)
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="owned_leagues")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    legacy_key = models.CharField(max_length=40, unique=True, null=True, blank=True, editable=False)

    class Meta:
        ordering = ("created_at", "id")
        verbose_name = "Лига друзей"
        verbose_name_plural = "Лиги друзей"

    def __str__(self):
        return self.name


class LeagueSeason(models.Model):
    class Ruleset(models.TextChoices):
        CLASSIC = "classic", "Классика"
        PADDOCK = "paddock", "Паддок"

    league = models.ForeignKey(League, on_delete=models.PROTECT, related_name="seasons")
    season = models.ForeignKey(Season, on_delete=models.PROTECT, related_name="friend_league_seasons")
    start_event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="starting_league_seasons")
    ruleset = models.CharField(max_length=12, choices=Ruleset.choices, default=Ruleset.CLASSIC)
    rules_version = models.PositiveSmallIntegerField(default=1, editable=False)
    is_legacy = models.BooleanField(default=False, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("league", "season"), name="league_season_unique"),
            models.CheckConstraint(condition=Q(ruleset__in=("classic", "paddock")), name="league_ruleset_valid"),
            models.CheckConstraint(condition=Q(rules_version__gte=1), name="league_rules_version_positive"),
        ]

    def clean(self):
        super().clean()
        if self.start_event_id and self.season_id and self.start_event.season_year != self.season.year:
            raise ValidationError({"start_event": "Стартовый этап должен относиться к выбранному сезону."})
        if self.is_legacy and self.league_id and not self.league.legacy_key:
            raise ValidationError({"is_legacy": "Исторический зачёт создаётся только при переносе старой лиги."})

    def __str__(self):
        return f"{self.league} · {self.season.year}"


class LeagueMembership(models.Model):
    class Role(models.TextChoices):
        PLAYER = "player", "Игрок"
        MODERATOR = "moderator", "Модератор"
        MANAGER = "manager", "Управляющий"

    league = models.ForeignKey(League, on_delete=models.PROTECT, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="friend_league_memberships")
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.PLAYER)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("league", "user"), name="league_member_unique"),
            models.CheckConstraint(condition=Q(role__in=("player", "moderator", "manager")), name="league_member_role_valid"),
        ]

    def __str__(self):
        return f"{self.league}: {self.user}"


class LeagueSeasonEntry(models.Model):
    """A persisted start boundary: old global predictions never backfill it."""

    league_season = models.ForeignKey(LeagueSeason, on_delete=models.PROTECT, related_name="entries")
    membership = models.ForeignKey(LeagueMembership, on_delete=models.PROTECT, related_name="season_entries")
    first_event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="first_league_entries")
    entered_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("league_season", "membership"), name="league_entry_unique"),
        ]

    def clean(self):
        super().clean()
        if self.league_season_id and self.membership_id:
            if self.membership.league_id != self.league_season.league_id:
                raise ValidationError({"membership": "Участник должен принадлежать этой лиге."})
        if self.league_season_id and self.first_event_id:
            league_season = self.league_season
            if (self.first_event.season_year != league_season.season.year
                    or self.first_event.round_number < league_season.start_event.round_number):
                raise ValidationError({"first_event": "Первый зачётный этап должен быть в сезоне, не раньше старта лиги."})
            if not league_season.is_legacy and self.first_event.deadline <= self.entered_at:
                raise ValidationError({"first_event": "Нельзя вступить в зачёт после дедлайна этапа."})


class GlobalEventScore(models.Model):
    """Objective event projection; never reuses the legacy Score total."""

    prediction = models.OneToOneField("Prediction", on_delete=models.PROTECT, related_name="global_event_score")
    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="global_scores")
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="global_event_scores")
    points = models.PositiveIntegerField(default=0)
    breakdown = models.JSONField(default=dict, blank=True)
    rules_version = models.PositiveSmallIntegerField(default=1)
    input_data = models.JSONField(default=dict, blank=True)
    input_digest = models.CharField(max_length=64)
    calculated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("event", "user"), name="global_score_event_user_uniq"),
            models.CheckConstraint(condition=Q(rules_version__gte=1), name="global_score_version_positive"),
        ]
        indexes = [models.Index(fields=("event", "-points", "user"), name="global_score_event_rank_idx")]

    def clean(self):
        super().clean()
        if self.prediction_id:
            if self.user_id != self.prediction.user_id or self.event_id != self.prediction.event_id:
                raise ValidationError("Общий результат должен соответствовать игроку и этапу базового прогноза.")


class LeagueEventRecord(models.Model):
    """Scope shared by local inputs and projections, not an HTTP permission."""

    entry = models.ForeignKey(LeagueSeasonEntry, on_delete=models.PROTECT, related_name="%(class)s_records")
    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="%(class)s_records")

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if not self.entry_id or not self.event_id:
            return
        entry, event = self.entry, self.event
        league_season = entry.league_season
        if (entry.membership.league_id != league_season.league_id
                or league_season.start_event.season_year != league_season.season.year
                or event.season_year != league_season.season.year
                or entry.first_event.season_year != event.season_year
                or event.round_number < max(entry.first_event.round_number, league_season.start_event.round_number)
                or (not league_season.is_legacy and entry.entered_at >= event.deadline)):
            raise ValidationError("Игрок не участвует в этом этапе этой лиги.")


class LeagueCrazyDecision(LeagueEventRecord):
    prediction = models.ForeignKey("Prediction", on_delete=models.PROTECT, related_name="local_crazy_decisions")
    approved = models.BooleanField(default=False)
    text_digest = models.CharField(max_length=64)
    reviewed_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="local_crazy_reviews")
    reviewed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("entry", "event"), name="local_crazy_entry_event_uniq")]

    def clean(self):
        super().clean()
        if self.prediction_id and self.entry_id:
            if self.prediction.event_id != self.event_id or self.prediction.user_id != self.entry.membership.user_id:
                raise ValidationError("Решение относится к чужому прогнозу.")


class LeagueDayDecision(models.Model):
    league_season = models.ForeignKey(LeagueSeason, on_delete=models.PROTECT, related_name="day_decisions")
    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="league_day_decisions")
    drivers = models.JSONField(default=list)
    reviewed_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="league_day_reviews")
    reviewed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("league_season", "event"), name="league_day_event_unique")]


class LeaguePodiumBonus(LeagueEventRecord):
    """Trusted reward producers issue a grant; the player may only consume it."""

    source_key = models.CharField(max_length=160)
    granted_at = models.DateTimeField(default=timezone.now)
    slot = models.CharField(max_length=2, choices=[("p1", "P1"), ("p2", "P2"), ("p3", "P3")], blank=True)
    driver = models.CharField(max_length=50, choices=DRIVER_CHOICES, blank=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("entry", "event"), name="local_podium_entry_event_uniq"),
            models.CheckConstraint(
                condition=(Q(used_at__isnull=True, slot="", driver="")
                           | (Q(used_at__isnull=False, slot__in=("p1", "p2", "p3")) & ~Q(driver=""))),
                name="local_podium_used_consistent",
            ),
        ]


class LeagueScoreAdjustment(LeagueEventRecord):
    class Kind(models.TextChoices):
        DUEL = "duel", "Дуэль"
        ARCADE = "arcade", "Аркада"
        WILDCARD = "wildcard", "Личная карта"

    kind = models.CharField(max_length=12, choices=Kind.choices)
    source_key = models.CharField(max_length=160)
    points = models.IntegerField()
    reason = models.CharField(max_length=200)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("entry", "event", "kind", "source_key"), name="local_adjustment_source_uniq"),
            models.CheckConstraint(condition=Q(kind__in=("duel", "arcade", "wildcard")), name="local_adjustment_kind_valid"),
        ]


class LeagueEventScore(LeagueEventRecord):
    prediction = models.ForeignKey("Prediction", on_delete=models.PROTECT, related_name="local_event_scores")
    base_points = models.PositiveIntegerField(default=0)
    podium_adjustment = models.IntegerField(default=0)
    crazy_points = models.PositiveSmallIntegerField(default=0)
    other_adjustment = models.IntegerField(default=0)
    points = models.IntegerField(default=0)
    breakdown = models.JSONField(default=dict, blank=True)
    rules_version = models.PositiveSmallIntegerField(default=1)
    input_data = models.JSONField(default=dict, blank=True)
    input_digest = models.CharField(max_length=64)
    calculated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("entry", "event"), name="local_score_entry_event_uniq"),
            models.CheckConstraint(condition=Q(rules_version__gte=1), name="local_score_version_positive"),
            models.CheckConstraint(condition=Q(crazy_points__in=(0, 5)), name="local_score_crazy_points_valid"),
            models.CheckConstraint(condition=Q(points=F("base_points")+F("podium_adjustment")+F("crazy_points")+F("other_adjustment")), name="local_score_total_consistent"),
        ]
        indexes = [models.Index(fields=("event", "-points", "entry"), name="local_score_event_rank_idx")]

    def clean(self):
        super().clean()
        if self.prediction_id and self.entry_id:
            if self.prediction.event_id != self.event_id or self.prediction.user_id != self.entry.membership.user_id:
                raise ValidationError("Результат относится к чужому прогнозу.")


class CompetitionScoreAudit(models.Model):
    class Action(models.TextChoices):
        GLOBAL_PROJECTED = "global_projected", "Общий пересчёт"
        LEAGUE_PROJECTED = "league_projected", "Локальный пересчёт"
        CRAZY_DECIDED = "crazy_decided", "Решение по крейзи"
        PODIUM_APPLIED = "podium_applied", "Локальный апдейт подиума"

    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="competition_score_audits")
    league_season = models.ForeignKey(LeagueSeason, on_delete=models.PROTECT, null=True, blank=True, related_name="score_audits")
    entry = models.ForeignKey(LeagueSeasonEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="score_audits")
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="competition_score_actions")
    action = models.CharField(max_length=20, choices=Action.choices)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.CheckConstraint(
            condition=(Q(action="global_projected", entry__isnull=True, league_season__isnull=True)
                       | Q(action__in=("league_projected", "crazy_decided", "podium_applied"), entry__isnull=False, league_season__isnull=False)),
            name="competition_audit_scope_valid",
        )]

    def clean(self):
        super().clean()
        if self.entry_id and self.league_season_id and self.entry.league_season_id != self.league_season_id:
            raise ValidationError("Запись аудита относится к чужой лиге.")


class LeagueInvite(models.Model):
    league_season = models.ForeignKey(LeagueSeason, on_delete=models.PROTECT, related_name="invites")
    token_digest = models.CharField(max_length=64, unique=True, editable=False)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="league_invites")
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    uses = models.PositiveIntegerField(default=0)


class LeagueActivity(models.Model):
    league = models.ForeignKey(League, on_delete=models.PROTECT, related_name="activity")
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="league_actions")
    action = models.CharField(max_length=24, choices=[
        ("created", "Создание лиги"), ("joined", "Вступление"),
        ("invite_created", "Создание приглашения"), ("invite_revoked", "Отзыв приглашения"),
        ("role_changed", "Изменение роли"),
        ("profile_changed", "Настройки лиги"), ("day_decided", "Гонщик дня"),
        ("crazy_decided", "Крейзи-предикт"),
    ])
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)


class EventPhoto(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField("Фото", upload_to="event_photos/", max_length=255)
    caption = models.CharField("Подпись", max_length=200, blank=True)

    def __str__(self):
        return f"Фото для {self.event}"


class HomeResultImage(models.Model):
    season_year = models.PositiveSmallIntegerField("Сезон", default=2026, db_index=True)
    title = models.CharField("Заголовок", max_length=120, blank=True)
    image = models.ImageField("Изображение", upload_to="home_results/", max_length=255)
    caption = models.CharField("Подпись", max_length=220, blank=True)
    is_active = models.BooleanField("Показывать на главной", default=True)
    sort_order = models.PositiveIntegerField("Порядок", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("sort_order", "-created_at")
        verbose_name = "Фото результатов (главная)"
        verbose_name_plural = "Фото результатов (главная)"

    def __str__(self):
        if self.title:
            return self.title
        return f"Фото результатов #{self.id}"


class DuelSettings(models.Model):
    key = models.CharField(max_length=32, unique=True, default="default", editable=False)
    cover_image = models.ImageField(
        "Общая обложка дуэлей",
        upload_to="duel_theme/",
        blank=True,
        null=True,
        max_length=255,
        help_text="Загружается один раз и используется на всех этапах.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Оформление дуэлей"
        verbose_name_plural = "Оформление дуэлей"

    def __str__(self):
        return "Общее оформление дуэлей"


class WildcardSettings(models.Model):
    key = models.CharField(max_length=32, unique=True, default="default", editable=False)
    card_back_image = models.ImageField(
        "Общая рубашка личных карт",
        upload_to="wildcard_theme/",
        blank=True,
        null=True,
        max_length=255,
        help_text="Необязательно. Одна картинка используется для всех этапов.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Оформление личных карт"
        verbose_name_plural = "Оформление личных карт"

    def __str__(self):
        return "Общее оформление личных карт"


class WildcardCardTemplate(models.Model):
    title = models.CharField(
        "Название в библиотеке",
        max_length=120,
        help_text="Короткое название только для удобного поиска в админке.",
    )
    question = models.CharField("Вопрос", max_length=240)
    option_a = models.CharField("Вариант A", max_length=120)
    option_b = models.CharField("Вариант B", max_length=120)
    option_c = models.CharField(
        "Вариант C",
        max_length=120,
        blank=True,
        default="",
        help_text="Необязательно. Оставь пустым для обычной карты с двумя ответами.",
    )
    draw_weight = models.PositiveSmallIntegerField(
        "Частота выпадения",
        default=10,
        validators=(MinValueValidator(1), MaxValueValidator(100)),
        help_text="10 — обычная карта. Чем меньше число, тем реже карта попадает в общую тройку этапа.",
    )
    is_active = models.BooleanField("Можно добавлять в этапы", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("title", "id")
        verbose_name = "Шаблон личной карты"
        verbose_name_plural = "Библиотека личных карт"

    def __str__(self):
        return self.title


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="league_profile")
    avatar = models.ImageField("Аватар", upload_to="avatars/", blank=True, null=True, max_length=255)
    is_world_predict_champion = models.BooleanField("World Predict Champion", default=False)
    telegram_chat_id = models.BigIntegerField("Telegram chat ID", null=True, blank=True)
    telegram_notifications = models.BooleanField("Telegram-уведомления", default=True)
    telegram_link_token = models.UUIDField(
        "Токен привязки Telegram",
        default=uuid.uuid4,
        db_index=True,
        editable=False,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("user__username",)

    def __str__(self):
        return f"Профиль {self.user.username}"


@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


class Prediction(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="predictions")
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    p1 = models.CharField("Победитель (P1)", max_length=50, choices=DRIVER_CHOICES)
    p2 = models.CharField("P2", max_length=50, choices=DRIVER_CHOICES)
    p3 = models.CharField("P3", max_length=50, choices=DRIVER_CHOICES)
    pole = models.CharField("Пол-позиция", max_length=50, choices=DRIVER_CHOICES)
    sprint_qualifying_winner = models.CharField(
        "Победитель квалификации к спринту",
        max_length=50,
        choices=DRIVER_CHOICES,
        blank=True,
        default="",
    )
    sprint_winner = models.CharField(
        "Победитель спринта",
        max_length=50,
        choices=DRIVER_CHOICES,
        blank=True,
        default="",
    )
    fastest_lap = models.CharField("Fastest Lap", max_length=50, choices=DRIVER_CHOICES, blank=True, default="")
    driver_of_day = models.CharField("Driver of the Day", max_length=50, choices=DRIVER_CHOICES, blank=True, default="")
    crazy_prediction = models.TextField("Crazy Prediction", blank=True, default="")
    safety_car_count = models.PositiveSmallIntegerField("Количество Safety Car", default=0)
    dnf_count = models.PositiveSmallIntegerField("Количество DNF", default=0)
    crazy_prediction_approved = models.BooleanField("Crazy Prediction засчитан судьей", default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("event", "user")

    def is_locked(self):
        return self.event.deadline < timezone.now()

    def __str__(self):
        return f"{self.user} - {self.event}"


class CrazyPredictionVote(models.Model):
    updated_at = models.DateTimeField("Последнее изменение голоса", null=True, blank=True)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="crazy_prediction_votes")
    voter = models.ForeignKey(User, on_delete=models.CASCADE, related_name="crazy_prediction_votes_cast")
    target_prediction = models.ForeignKey(
        Prediction,
        on_delete=models.CASCADE,
        related_name="crazy_prediction_votes_received",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("event", "voter"), name="crazy_vote_event_user_uniq"),
        ]
        indexes = [models.Index(fields=("event", "target_prediction"), name="crazy_vote_ev_target_idx")]
        verbose_name = "Голос за Crazy Prediction"
        verbose_name_plural = "Голоса за Crazy Prediction"

    def __str__(self):
        return f"{self.event}: {self.voter} → предикт #{self.target_prediction_id}"


class EventWildcardQuestion(models.Model):
    class Option(models.TextChoices):
        A = "a", "Вариант A"
        B = "b", "Вариант B"
        C = "c", "Вариант C"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="wildcard_questions")
    source_card = models.ForeignKey(
        WildcardCardTemplate,
        on_delete=models.SET_NULL,
        related_name="event_assignments",
        verbose_name="Карта из библиотеки",
        null=True,
        blank=True,
        help_text="Текст и варианты копируются в этап, чтобы история не менялась при редактировании шаблона.",
    )
    question = models.CharField("Вопрос", max_length=240)
    option_a = models.CharField("Вариант A", max_length=120)
    option_b = models.CharField("Вариант B", max_length=120)
    option_c = models.CharField("Вариант C", max_length=120, blank=True, default="")
    correct_option = models.CharField(
        "Правильный вариант",
        max_length=1,
        choices=Option.choices,
        blank=True,
        default="",
        help_text="Заполни после завершения этапа перед публикацией очков.",
    )
    points = models.PositiveSmallIntegerField(
        "Очки",
        default=3,
        editable=False,
        validators=(MinValueValidator(1), MaxValueValidator(10)),
    )
    draw_weight = models.PositiveSmallIntegerField(
        "Частота выпадения",
        default=10,
        validators=(MinValueValidator(1), MaxValueValidator(100)),
    )
    is_active = models.BooleanField("Участвует в розыгрыше", default=True)
    sort_order = models.PositiveIntegerField("Порядок", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("sort_order", "id")
        verbose_name = "Карта этапа"
        verbose_name_plural = "Карты этапов и правильные ответы"
        indexes = [
            models.Index(fields=("event", "is_active"), name="wildcard_event_active_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("event", "source_card"),
                name="unique_wildcard_template_per_event",
            ),
        ]

    def __str__(self):
        return f"{self.event}: {self.question}"

    def save(self, *args, **kwargs):
        if self.source_card_id:
            source = self.source_card
            self.question = source.question
            self.option_a = source.option_a
            self.option_b = source.option_b
            self.option_c = source.option_c
            self.draw_weight = source.draw_weight
        self.points = 3
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.correct_option == self.Option.C and not self.option_c:
            raise ValidationError({"correct_option": "У этой карты не заполнен вариант C."})

    def answer_for(self, option):
        if option == self.Option.A:
            return self.option_a
        if option == self.Option.B:
            return self.option_b
        if option == self.Option.C:
            return self.option_c
        return ""


class EventWildcardDeck(models.Model):
    event = models.OneToOneField(
        Event,
        on_delete=models.CASCADE,
        related_name="wildcard_deck",
        verbose_name="Этап",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-event__season_year", "event__round_number")
        verbose_name = "Общая тройка карт этапа"
        verbose_name_plural = "Общие тройки карт этапов"

    def __str__(self):
        return f"Общая тройка — {self.event}"


class EventWildcardDeckCard(models.Model):
    deck = models.ForeignKey(
        EventWildcardDeck,
        on_delete=models.CASCADE,
        related_name="cards",
    )
    question = models.ForeignKey(
        EventWildcardQuestion,
        on_delete=models.RESTRICT,
        related_name="shared_deck_cards",
    )
    slot = models.PositiveSmallIntegerField(
        "Позиция карты",
        validators=(MinValueValidator(1), MaxValueValidator(3)),
    )

    class Meta:
        ordering = ("slot",)
        verbose_name = "Карта в общей тройке"
        verbose_name_plural = "Карты в общей тройке"
        constraints = [
            models.UniqueConstraint(
                fields=("deck", "slot"),
                name="unique_wildcard_deck_slot",
            ),
            models.UniqueConstraint(
                fields=("deck", "question"),
                name="unique_wildcard_deck_question",
            ),
        ]

    def __str__(self):
        return f"{self.deck}: карта {self.slot}"


class PlayerWildcard(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="player_wildcards")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="event_wildcards")
    question = models.ForeignKey(
        EventWildcardQuestion,
        on_delete=models.RESTRICT,
        related_name="draws",
    )
    card_slot = models.PositiveSmallIntegerField(
        "Выбранная карта",
        default=2,
        validators=(MinValueValidator(1), MaxValueValidator(3)),
    )
    selected_option = models.CharField(
        "Ответ игрока",
        max_length=1,
        choices=EventWildcardQuestion.Option.choices,
        blank=True,
        default="",
    )
    drawn_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField("Ответ сохранён", null=True, blank=True)

    class Meta:
        ordering = ("event", "user__username")
        verbose_name = "Выданная личная карта"
        verbose_name_plural = "Выданные личные карты"
        constraints = [
            models.UniqueConstraint(
                fields=("event", "user"),
                name="unique_wildcard_draw_per_event_user",
            ),
        ]

    def __str__(self):
        return f"{self.user} — {self.event}: {self.question.question}"

    @property
    def selected_answer(self):
        return self.question.answer_for(self.selected_option)

    @property
    def correct_answer(self):
        return self.question.answer_for(self.question.correct_option)

    @property
    def is_correct(self):
        return bool(
            self.selected_option
            and self.question.correct_option
            and self.selected_option == self.question.correct_option
        )

    @property
    def awarded_points(self):
        if not self.selected_option or not self.question.correct_option:
            return 0
        return self.question.points if self.is_correct else -self.question.points


class PlayerWildcardOffer(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="wildcard_offers")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="wildcard_offers")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("event", "user__username")
        verbose_name = "Персональная тройка карт"
        verbose_name_plural = "Персональные тройки карт"
        constraints = [
            models.UniqueConstraint(
                fields=("event", "user"),
                name="unique_wildcard_offer_per_event_user",
            ),
        ]

    def __str__(self):
        return f"{self.user} — {self.event}"


class PlayerWildcardOfferCard(models.Model):
    offer = models.ForeignKey(
        PlayerWildcardOffer,
        on_delete=models.CASCADE,
        related_name="cards",
    )
    question = models.ForeignKey(
        EventWildcardQuestion,
        on_delete=models.RESTRICT,
        related_name="offer_cards",
    )
    slot = models.PositiveSmallIntegerField(
        "Позиция карты",
        validators=(MinValueValidator(1), MaxValueValidator(3)),
    )

    class Meta:
        ordering = ("slot",)
        verbose_name = "Карта в персональной тройке"
        verbose_name_plural = "Карты в персональной тройке"
        constraints = [
            models.UniqueConstraint(
                fields=("offer", "slot"),
                name="unique_wildcard_offer_slot",
            ),
            models.UniqueConstraint(
                fields=("offer", "question"),
                name="unique_wildcard_offer_question",
            ),
        ]

    def __str__(self):
        return f"{self.offer}: карта {self.slot}"


class Result(models.Model):
    event = models.OneToOneField(Event, on_delete=models.CASCADE, related_name="result")

    p1 = models.CharField("P1 (факт)", max_length=50, choices=DRIVER_CHOICES)
    p2 = models.CharField("P2 (факт)", max_length=50, choices=DRIVER_CHOICES)
    p3 = models.CharField("P3 (факт)", max_length=50, choices=DRIVER_CHOICES)
    pole = models.CharField("Пол-позиция (факт)", max_length=50, choices=DRIVER_CHOICES)
    sprint_qualifying_winner = models.CharField(
        "Победитель квалификации к спринту (факт)",
        max_length=50,
        choices=DRIVER_CHOICES,
        blank=True,
        default="",
    )
    sprint_winner = models.CharField(
        "Победитель спринта (факт)",
        max_length=50,
        choices=DRIVER_CHOICES,
        blank=True,
        default="",
    )
    fastest_lap = models.CharField("Fastest Lap (факт)", max_length=50, choices=DRIVER_CHOICES, blank=True, default="")
    driver_of_day = models.CharField("Driver of the Day (факт)", max_length=50, choices=DRIVER_CHOICES, blank=True, default="")
    driver_of_day_multiple = models.JSONField("Driver of the Day (факт, несколько)", default=list, blank=True)
    safety_car_count = models.PositiveSmallIntegerField("Количество Safety Car (факт)", default=0)
    dnf_count = models.PositiveSmallIntegerField("Количество DNF (факт)", default=0)
    published_at = models.DateTimeField("Опубликовано", null=True, blank=True, editable=False)
    published_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="published_results",
    )

    def __str__(self):
        return f"Результат - {self.event}"


class SeasonPrediction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="season_predictions")
    season_year = models.PositiveSmallIntegerField("Сезон", default=2026)

    # Промежуточные сезонные предикты
    hungary_driver_championship_leader = models.CharField(
        "Лидер чемпионата пилотов после этапа Венгрии",
        max_length=50,
        choices=DRIVER_CHOICES,
    )
    hungary_constructor_championship_leader = models.CharField(
        "Лидер Кубка конструкторов после этапа Венгрии",
        max_length=50,
        choices=CONSTRUCTOR_CHOICES,
    )
    hadjar_best_finish = models.PositiveSmallIntegerField("Самый высокий финиш Хаджара")

    # Итоги сезона
    world_drivers_champion = models.CharField(
        "Чемпион мира среди пилотов",
        max_length=50,
        choices=DRIVER_CHOICES,
    )
    constructors_champion = models.CharField(
        "Чемпион Кубка конструкторов",
        max_length=50,
        choices=CONSTRUCTOR_CHOICES,
    )
    constructors_second = models.CharField(
        "2 место Кубка конструкторов",
        max_length=50,
        choices=CONSTRUCTOR_CHOICES,
    )
    constructors_third = models.CharField(
        "3 место Кубка конструкторов",
        max_length=50,
        choices=CONSTRUCTOR_CHOICES,
    )

    # Дополнительные сезонные категории
    last_race_winner = models.CharField(
        "Победитель последней гонки сезона",
        max_length=50,
        choices=DRIVER_CHOICES,
    )
    season_pole_sitter = models.CharField(
        "Pole-sitter сезона",
        max_length=50,
        choices=DRIVER_CHOICES,
    )
    driver_change_happened = models.CharField(
        "Была ли смена пилота в сезоне",
        max_length=3,
        choices=YES_NO_CHOICES,
    )
    team_most_dnf = models.CharField(
        "Команда-лидер по количеству DNF",
        max_length=50,
        choices=CONSTRUCTOR_CHOICES,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "season_year")
        ordering = ("season_year", "user__username")

    def __str__(self):
        return f"{self.user} - сезон {self.season_year}"


class SeasonResult(models.Model):
    season_year = models.PositiveSmallIntegerField("Сезон", unique=True, default=2026)

    # Промежуточные сезонные факты
    hungary_driver_championship_leader = models.CharField(
        "Лидер чемпионата пилотов после этапа Венгрии (факт)",
        max_length=50,
        choices=DRIVER_CHOICES,
    )
    hungary_constructor_championship_leader = models.CharField(
        "Лидер Кубка конструкторов после этапа Венгрии (факт)",
        max_length=50,
        choices=CONSTRUCTOR_CHOICES,
    )
    hadjar_best_finish = models.PositiveSmallIntegerField("Самый высокий финиш Хаджара (факт)")

    # Итоги сезона
    world_drivers_champion = models.CharField(
        "Чемпион мира среди пилотов (факт)",
        max_length=50,
        choices=DRIVER_CHOICES,
        blank=True,
        default="",
    )
    constructors_champion = models.CharField(
        "Чемпион Кубка конструкторов (факт)",
        max_length=50,
        choices=CONSTRUCTOR_CHOICES,
        blank=True,
        default="",
    )
    constructors_second = models.CharField(
        "2 место Кубка конструкторов (факт)",
        max_length=50,
        choices=CONSTRUCTOR_CHOICES,
        blank=True,
        default="",
    )
    constructors_third = models.CharField(
        "3 место Кубка конструкторов (факт)",
        max_length=50,
        choices=CONSTRUCTOR_CHOICES,
        blank=True,
        default="",
    )

    # Дополнительные сезонные факты
    last_race_winner = models.CharField(
        "Победитель последней гонки сезона (факт)",
        max_length=50,
        choices=DRIVER_CHOICES,
        blank=True,
        default="",
    )
    season_pole_sitter = models.CharField(
        "Pole-sitter сезона (факт)",
        max_length=50,
        choices=DRIVER_CHOICES,
        blank=True,
        default="",
    )
    driver_change_happened = models.CharField(
        "Была ли смена пилота в сезоне (факт)",
        max_length=3,
        choices=YES_NO_CHOICES,
        blank=True,
        default="",
    )
    team_most_dnf = models.CharField(
        "Команда-лидер по количеству DNF (факт)",
        max_length=50,
        choices=CONSTRUCTOR_CHOICES,
        blank=True,
        default="",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("season_year",)

    def __str__(self):
        return f"Фактические итоги сезона {self.season_year}"


class SeasonScore(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="season_scores")
    season_year = models.PositiveSmallIntegerField("Сезон", default=2026)
    points = models.IntegerField(default=0)
    breakdown = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "season_year")
        ordering = ("season_year", "-points", "user__username")

    def __str__(self):
        return f"{self.user} - сезон {self.season_year}: {self.points}"


class Score(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="scores")
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE)

    points = models.IntegerField(default=0)
    prediction_points = models.IntegerField("Очки прогноза", default=0)
    duel_adjustment = models.IntegerField("Поправка за дуэль", default=0)
    breakdown = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ("event", "user")

    def __str__(self):
        return f"{self.user} - {self.event}: {self.points}"


class DuelChallenge(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает ответа"
        ACCEPTED = "accepted", "Принята"
        DECLINED = "declined", "Отклонена"
        CANCELLED = "cancelled", "Отменена"
        EXPIRED = "expired", "Истекла"
        SETTLED = "settled", "Рассчитана"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="duel_challenges")
    challenger = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="duel_challenges_sent",
        verbose_name="Инициатор",
    )
    opponent = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="duel_challenges_received",
        verbose_name="Соперник",
    )
    stake = models.PositiveSmallIntegerField(
        "Ставка",
        validators=(MinValueValidator(1), MaxValueValidator(10)),
    )
    status = models.CharField(
        "Статус",
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    winner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="duel_challenges_won",
        verbose_name="Победитель",
        null=True,
        blank=True,
    )
    challenger_prediction_points = models.IntegerField("Очки инициатора", null=True, blank=True)
    opponent_prediction_points = models.IntegerField("Очки соперника", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    responded_at = models.DateTimeField("Ответ получен", null=True, blank=True)
    settled_at = models.DateTimeField("Рассчитана", null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Дуэль"
        verbose_name_plural = "Дуэли"
        constraints = [
            models.CheckConstraint(
                condition=Q(stake__gte=1, stake__lte=10),
                name="duel_stake_between_1_and_10",
            ),
            models.CheckConstraint(
                condition=~Q(challenger=F("opponent")),
                name="duel_players_must_differ",
            ),
        ]
        indexes = [
            models.Index(fields=("event", "status"), name="duel_event_status_idx"),
        ]

    def __str__(self):
        return f"{self.challenger} vs {self.opponent} — {self.event} ({self.stake})"

    def involves(self, user):
        return bool(user and user.id in (self.challenger_id, self.opponent_id))

    def opponent_for(self, user):
        if not self.involves(user):
            return None
        return self.opponent if user.id == self.challenger_id else self.challenger

    def adjustment_for(self, user):
        if self.status != self.Status.SETTLED or not self.winner_id or not self.involves(user):
            return 0
        return self.stake if self.winner_id == user.id else -self.stake


class ScoreRevision(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="score_revisions")
    revision = models.PositiveIntegerField()
    scores = models.JSONField(default=list)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="score_revisions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("event", "revision"),
                name="unique_score_revision_per_event",
            )
        ]
        verbose_name = "Версия подсчёта"
        verbose_name_plural = "Версии подсчёта"

    def __str__(self):
        return f"{self.event} — версия {self.revision}"


class TelegramReminder(models.Model):
    class Kind(models.TextChoices):
        DAY = "24h", "За 24 часа"
        THREE_HOURS = "3h", "За 3 часа"
        RESULT = "result", "Результат этапа"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="telegram_reminders")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="telegram_reminders")
    kind = models.CharField("Тип", max_length=10, choices=Kind.choices, default=Kind.THREE_HOURS)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("event", "user", "kind")
        ordering = ("-sent_at",)

    def __str__(self):
        return f"Telegram reminder: {self.user} - {self.event}"


class TelegramBotState(models.Model):
    key = models.CharField(max_length=32, unique=True, default="default", editable=False)
    update_offset = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Telegram bot state: {self.key}"


class ArcadeAttempt(models.Model):
    competition = models.ForeignKey("ArcadeCompetition", null=True, blank=True, on_delete=models.SET_NULL, related_name="flappy_attempts")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="arcade_attempts")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    score = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("-started_at",)
        indexes = [models.Index(fields=("user", "started_at"), name="arcade_attempt_user_idx")]

    def __str__(self):
        return f"{self.user} — arcade run {self.pk}"


class DoodleAttempt(models.Model):
    competition = models.ForeignKey("ArcadeCompetition", null=True, blank=True, on_delete=models.SET_NULL, related_name="doodle_attempts")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="doodle_attempts")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    score = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("-started_at",)
        indexes = [models.Index(fields=("user", "started_at"), name="doodle_attempt_user_idx")]
        verbose_name = "Попытка Doodle GP"
        verbose_name_plural = "Попытки Doodle GP"

    def __str__(self):
        return f"{self.user} — Doodle GP run {self.pk}"


class DoodleRecord(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="doodle_record")
    best_score = models.PositiveIntegerField(default=0)
    total_attempts = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-best_score", "updated_at", "user__username")
        verbose_name = "Рекорд Doodle GP"
        verbose_name_plural = "Рекорды Doodle GP"

    def __str__(self):
        return f"{self.user}: {self.best_score}"


class ArcadeRecord(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="arcade_record")
    best_score = models.PositiveIntegerField(default=0)
    total_attempts = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-best_score", "updated_at", "user__username")

    def __str__(self):
        return f"{self.user}: {self.best_score}"


class ArcadeLeadChange(models.Model):
    player = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="arcade_lead_changes",
        verbose_name="Игрок",
    )
    best_score = models.PositiveIntegerField("Рекорд на момент лидерства")
    attempts = models.PositiveIntegerField("Попытки к моменту лидерства")
    created_at = models.DateTimeField("Время смены лидера", auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        verbose_name = "Смена лидера аркады"
        verbose_name_plural = "Смены лидера аркады"

    def __str__(self):
        return f"{self.player} занял первое место в аркаде"


class ArcadeTrophyAward(models.Model):
    player = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="arcade_trophies",
        verbose_name="Игрок",
    )
    game_name = models.CharField("Игра", max_length=120, default="Pit Lane Flight")
    game_key = models.CharField(
        "Код игры",
        max_length=80,
        default="pit_lane_flight",
        help_text="Стабильный идентификатор игры; для одной игры можно выдать один трофей за этап.",
    )
    trophy_name = models.CharField("Название трофея", max_length=120, default="Банана Леклер")
    image = models.ImageField(
        "Изображение трофея",
        upload_to="arcade/trophies/",
        blank=True,
        help_text="Загрузи отдельную фигурку для этой игры. Для старых наград без картинки используется Банана Леклер.",
    )
    attempts = models.PositiveIntegerField("Попытки к моменту победы", default=0)
    awarded_at = models.DateTimeField("Дата получения", default=timezone.now)
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="arcade_trophy_awards",
        null=True,
        blank=True,
        verbose_name="Этап",
    )

    class Meta:
        ordering = ("awarded_at", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("event", "game_key"),
                name="uniq_arcade_trophy_event_game",
            ),
        ]
        verbose_name = "Трофей аркады"
        verbose_name_plural = "Трофеи аркады"

    def __str__(self):
        return f"{self.trophy_name} — {self.player} ({self.game_name})"


class ArcadeGameClosure(models.Model):
    game_key = models.CharField("Код игры", max_length=80, default="pit_lane_flight")
    season_year = models.PositiveSmallIntegerField("Сезон", default=2026)
    event = models.ForeignKey(
        Event,
        on_delete=models.PROTECT,
        related_name="arcade_game_closures",
        verbose_name="Этап закрытия",
    )
    winner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="arcade_game_closures",
        null=True,
        blank=True,
        verbose_name="Зафиксированный победитель",
    )
    winner_score = models.PositiveIntegerField("Результат победителя", null=True, blank=True)
    attempts = models.PositiveIntegerField("Попытки победителя", default=0)
    closed_at = models.DateTimeField("Дедлайн закрытия")

    class Meta:
        ordering = ("-closed_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("game_key", "season_year"),
                name="uniq_arcade_game_closure_season",
            ),
        ]
        verbose_name = "Закрытие мини-игры"
        verbose_name_plural = "Закрытия мини-игр"

    def __str__(self):
        winner = self.winner or "победитель не определён"
        return f"{self.game_key} · {self.season_year} · {winner}"


class ArcadeSettings(models.Model):
    class Game(models.TextChoices):
        FLAPPY = "flappy", "Pit Lane Flight · Flappy Bird"
        DOODLE_JUMP = "doodle_jump", "Doodle GP · бесконечный забег"
        MINESWEEPER = "minesweeper", "Сапёр · Pitwall Sweep"

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    active_game = models.CharField(
        "Активная аркада недели",
        max_length=24,
        choices=Game.choices,
        default=Game.MINESWEEPER,
        help_text="Выбор меняет игру на вкладке «Аркада», но не удаляет результаты других игр.",
    )
    public_enabled = models.BooleanField(
        "Открыть участникам",
        default=False,
        help_text="Если выключено, страницу и игру видят только администраторы. Можно включить позже без удаления результатов.",
    )
    competition_event = models.ForeignKey(
        Event,
        verbose_name="Этап зачёта",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Игра и её победитель привязаны только к этому выбранному этапу.",
    )
    competition_opened_at = models.DateTimeField(
        "Открыто участникам с",
        null=True,
        blank=True,
        help_text="С этой даты и до дедлайна выбранного этапа попытки идут в зачёт.",
    )
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Настройки аркады"
        verbose_name_plural = "Настройки аркады"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "Активная мини-игра и доступ"


class ArcadeCompetition(models.Model):
    game_key = models.CharField(max_length=24, choices=ArcadeSettings.Game.choices)
    event = models.OneToOneField(Event, on_delete=models.PROTECT, related_name="arcade_competition")
    opened_at = models.DateTimeField()
    frozen_at = models.DateTimeField(null=True, blank=True)
    standings = models.JSONField(default=list, blank=True)
    total_attempts = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-event__deadline",)


class MinesweeperAttempt(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="minesweeper_attempts")
    week_start = models.DateField("Начало игровой недели", db_index=True)
    started_at = models.DateTimeField("Начало попытки", auto_now_add=True)
    finished_at = models.DateTimeField("Завершено", null=True, blank=True)
    completed = models.BooleanField("Поле пройдено", default=False)
    elapsed_ms = models.PositiveIntegerField("Время прохождения, мс", null=True, blank=True)

    class Meta:
        ordering = ("week_start", "elapsed_ms", "started_at")
        indexes = [
            models.Index(fields=("week_start", "user"), name="mine_week_user_idx"),
            models.Index(fields=("week_start", "completed", "elapsed_ms"), name="mine_week_result_idx"),
        ]
        verbose_name = "Попытка Сапёра"
        verbose_name_plural = "Попытки Сапёра"

    def __str__(self):
        result = f"{self.elapsed_ms} мс" if self.completed and self.elapsed_ms else "не пройдено"
        return f"{self.user} · {self.week_start} · {result}"


class ArcadeWheelSpin(models.Model):
    class Prize(models.TextChoices):
        PIT_WALL = "pit_wall", "Бонус пит-уолла +2"
        CARD_BOOST = "card_boost", "ДРС личной карты +3"
        PODIUM_EDIT = "podium_edit", "Апдейт подиума"
        VA_BANK = "va_bank", "Ва-банк"
        RUEL_V_GOVNE = "ruel_v_govne", "Руль в говне"
        CRAZY_BLOCK = "crazy_block", "Блок Crazy"

    event = models.OneToOneField(
        Event,
        on_delete=models.CASCADE,
        related_name="arcade_wheel_spin",
        verbose_name="Этап",
    )
    winner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="arcade_wheel_spins",
        verbose_name="Победитель аркады",
    )
    winner_score = models.PositiveIntegerField("Результат победителя")
    prize = models.CharField("Приз", max_length=24, choices=Prize.choices)
    target_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="arcade_wheel_targets",
        verbose_name="Цель эффекта",
    )
    activation_data = models.JSONField("Параметры активации", default=dict, blank=True)
    spun_at = models.DateTimeField("Время прокрутки", auto_now_add=True)
    activated_at = models.DateTimeField("Время активации", null=True, blank=True)

    class Meta:
        verbose_name = "Прокрут колеса аркады"
        verbose_name_plural = "Прокруты колеса аркады"

    def __str__(self):
        return f"{self.event}: {self.winner} — {self.get_prize_display()}"
