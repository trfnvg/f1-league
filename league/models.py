import uuid
from datetime import timedelta

from django.contrib.auth.models import User
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
    race_datetime = models.DateTimeField("Дата/время гонки", null=True, blank=True)
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


class EventWildcardQuestion(models.Model):
    class Option(models.TextChoices):
        A = "a", "Вариант A"
        B = "b", "Вариант B"

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
        self.points = 3
        super().save(*args, **kwargs)

    def answer_for(self, option):
        if option == self.Option.A:
            return self.option_a
        if option == self.Option.B:
            return self.option_b
        return ""


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
