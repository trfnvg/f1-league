from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models
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


class Event(models.Model):
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
        ordering = ["round_number"]

    def __str__(self):
        return f"R{self.round_number} - {self.name}"

    def voting_state(self):
        """
        returns: 'soon' | 'open' | 'closed' | 'scored'
        """
        if self.status == self.Status.SCORED:
            return "scored"

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


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="league_profile")
    avatar = models.ImageField("Аватар", upload_to="avatars/", blank=True, null=True, max_length=255)
    is_world_predict_champion = models.BooleanField("World Predict Champion", default=False)
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
    )
    constructors_champion = models.CharField(
        "Чемпион Кубка конструкторов (факт)",
        max_length=50,
        choices=CONSTRUCTOR_CHOICES,
    )
    constructors_second = models.CharField(
        "2 место Кубка конструкторов (факт)",
        max_length=50,
        choices=CONSTRUCTOR_CHOICES,
    )
    constructors_third = models.CharField(
        "3 место Кубка конструкторов (факт)",
        max_length=50,
        choices=CONSTRUCTOR_CHOICES,
    )

    # Дополнительные сезонные факты
    last_race_winner = models.CharField(
        "Победитель последней гонки сезона (факт)",
        max_length=50,
        choices=DRIVER_CHOICES,
    )
    season_pole_sitter = models.CharField(
        "Pole-sitter сезона (факт)",
        max_length=50,
        choices=DRIVER_CHOICES,
    )
    driver_change_happened = models.CharField(
        "Была ли смена пилота в сезоне (факт)",
        max_length=3,
        choices=YES_NO_CHOICES,
    )
    team_most_dnf = models.CharField(
        "Команда-лидер по количеству DNF (факт)",
        max_length=50,
        choices=CONSTRUCTOR_CHOICES,
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
    breakdown = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ("event", "user")

    def __str__(self):
        return f"{self.user} - {self.event}: {self.points}"
