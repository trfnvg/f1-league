from datetime import timedelta

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class Event(models.Model):
    name = models.CharField("Название этапа", max_length=120)
    round_number = models.PositiveIntegerField("Раунд")
    deadline = models.DateTimeField("Дедлайн предиктов")
    race_datetime = models.DateTimeField("Дата/время гонки", null=True, blank=True)
    cover_image = models.ImageField("Обложка", upload_to="event_covers/", blank=True, null=True)

    class Status(models.TextChoices):
        OPEN = "open", "Открыто"
        LOCKED = "locked", "Закрыто"
        SCORED = "scored", "Очки посчитаны"

    status = models.CharField("Статус", max_length=10, choices=Status.choices, default=Status.OPEN)

    class Meta:
        ordering = ["round_number"]

    def __str__(self):
        return f"R{self.round_number} — {self.name}"

    def voting_state(self):
        """
        returns: 'soon' | 'open' | 'closed' | 'scored'
        """
        if self.status == self.Status.SCORED:
            return "scored"

        now = timezone.now()

        # если race_datetime не заполнена — будем fallback'ать на deadline
        base = self.race_datetime or self.deadline
        if base is None or self.deadline is None:
            # если чего-то нет, безопаснее считать закрытым
            return "closed"

        open_at = base - timedelta(days=7)

        if now < open_at:
            return "soon"
        if now <= self.deadline:
            return "open"
        return "closed"


class EventPhoto(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField("Фото", upload_to="event_photos/")
    caption = models.CharField("Подпись", max_length=200, blank=True)

    def __str__(self):
        return f"Фото для {self.event}"


class Prediction(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="predictions")
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    p1 = models.CharField("Победитель (P1)", max_length=50)
    p2 = models.CharField("P2", max_length=50)
    p3 = models.CharField("P3", max_length=50)
    pole = models.CharField("Поул", max_length=50)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("event", "user")

    def is_locked(self):
        return self.event.deadline < timezone.now()

    def __str__(self):
        return f"{self.user} — {self.event}"


class Result(models.Model):
    event = models.OneToOneField(Event, on_delete=models.CASCADE, related_name="result")

    p1 = models.CharField("P1 (факт)", max_length=50)
    p2 = models.CharField("P2 (факт)", max_length=50)
    p3 = models.CharField("P3 (факт)", max_length=50)
    pole = models.CharField("Поул (факт)", max_length=50)

    def __str__(self):
        return f"Результат — {self.event}"


class Score(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="scores")
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE)

    points = models.IntegerField(default=0)
    breakdown = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ("event", "user")

    def __str__(self):
        return f"{self.user} — {self.event}: {self.points}"
