import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import (
    DRIVER_CHOICES,
    ArcadeAttempt,
    ArcadeWheelSpin,
    Event,
    PlayerWildcard,
    Prediction,
)


WHEEL_SECTORS = (
    {
        "key": ArcadeWheelSpin.Prize.PIT_WALL,
        "label": "ПИТ-УОЛЛ +2",
        "title": "Бонус пит-уолла",
        "description": "+2 очка к результату этого Гран-при.",
        "weight": 25,
        "color": "#f1bd4b",
    },
    {
        "key": ArcadeWheelSpin.Prize.CARD_BOOST,
        "label": "КАРТА +3",
        "title": "ДРС личной карты",
        "description": "+3 очка, если ответ на выбранной карте этапа окажется верным.",
        "weight": 20,
        "color": "#55d69e",
    },
    {
        "key": ArcadeWheelSpin.Prize.PODIUM_EDIT,
        "label": "АПДЕЙТ\nПОДИУМА",
        "title": "Апдейт подиума",
        "description": "После квалификации можно заменить одного пилота в прогнозе подиума.",
        "weight": 20,
        "color": "#4389e8",
    },
    {
        "key": ArcadeWheelSpin.Prize.VA_BANK,
        "label": "ВА-БАНК\n+4 / −1",
        "title": "Ва-банк",
        "description": "Выбери один свой прогноз: +4 за верный ответ или −1 за неверный.",
        "weight": 15,
        "color": "#a47be8",
    },
    {
        "key": ArcadeWheelSpin.Prize.RUEL_V_GOVNE,
        "label": "РУЛЬ\nВ ГОВНЕ",
        "title": "Руль в говне",
        "description": "Выбранный соперник получит −3 очка за этап. Эффект учитывается в дуэли.",
        "weight": 10,
        "color": "#ee674f",
    },
    {
        "key": ArcadeWheelSpin.Prize.CRAZY_BLOCK,
        "label": "БЛОК\nCRAZY",
        "title": "Блок Crazy",
        "description": "Если Crazy Prediction выбранного соперника сбудется, за него будет 0 очков.",
        "weight": 10,
        "color": "#d84c80",
    },
)

WHEEL_PRIZE_BY_KEY = {sector["key"]: sector for sector in WHEEL_SECTORS}
WHEEL_WINDOW = timedelta(days=7)


class ArcadeWheelError(ValueError):
    pass


def arcade_wheel_event(season_year, now=None):
    now = now or timezone.now()
    events = Event.objects.filter(season_year=season_year).exclude(
        status=Event.Status.SCORED
    ).order_by("deadline", "round_number")
    for event in events:
        if event.race_datetime and event.race_datetime <= now:
            continue
        return event
    return None


def best_event_arcade_attempt(event, *, through=None):
    if through is None:
        through = timezone.now()
    window_start = event.deadline - WHEEL_WINDOW
    eligible_users = Prediction.objects.filter(event=event).values("user_id")
    return (
        ArcadeAttempt.objects.filter(
            user_id__in=eligible_users,
            user__is_active=True,
            user__is_staff=False,
            finished_at__gte=window_start,
            finished_at__lte=min(through, event.deadline),
            score__isnull=False,
        )
        .select_related("user")
        .order_by("-score", "finished_at", "user__username")
        .first()
    )


def wheel_window_is_open(event, now=None):
    now = now or timezone.now()
    return bool(
        event
        and event.status != Event.Status.SCORED
        and now >= event.deadline
        and (not event.race_datetime or now < event.race_datetime)
    )


def podium_edit_is_open(event, now=None):
    now = now or timezone.now()
    return bool(
        wheel_window_is_open(event, now)
        and event.qualifying_datetime
        and now >= event.qualifying_datetime
    )


def _draw_prize():
    target = secrets.randbelow(sum(sector["weight"] for sector in WHEEL_SECTORS))
    for sector in WHEEL_SECTORS:
        target -= sector["weight"]
        if target < 0:
            return sector["key"]
    return WHEEL_SECTORS[-1]["key"]


@transaction.atomic
def spin_event_wheel(event, user, now=None):
    now = now or timezone.now()
    locked_event = Event.objects.select_for_update().get(pk=event.pk)
    if not wheel_window_is_open(locked_event, now):
        raise ArcadeWheelError("Колесо открывается после дедлайна и закрывается перед стартом гонки.")

    attempt = best_event_arcade_attempt(locked_event, through=locked_event.deadline)
    if not attempt:
        raise ArcadeWheelError("За эту неделю пока нет засчитанных заездов участников этапа.")
    if attempt.user_id != user.id:
        raise ArcadeWheelError("Прокрутить колесо может только лидер аркады за эту неделю.")

    existing = ArcadeWheelSpin.objects.filter(event=locked_event).first()
    if existing:
        return existing, False

    spin = ArcadeWheelSpin.objects.create(
        event=locked_event,
        winner=attempt.user,
        winner_score=attempt.score,
        prize=_draw_prize(),
    )
    return spin, True


PREDICTION_FIELDS = (
    ("p1", "Победитель гонки"),
    ("p2", "Пилот на P2"),
    ("p3", "Пилот на P3"),
    ("pole", "Обладатель поула"),
    ("fastest_lap", "Fastest Lap"),
    ("driver_of_day", "Driver of the Day"),
    ("safety_car_count", "Количество Safety Car"),
    ("dnf_count", "Количество DNF"),
    ("sprint_qualifying_winner", "Квалификация к спринту"),
    ("sprint_winner", "Победитель спринта"),
    ("crazy_prediction", "Crazy Prediction"),
)


def available_va_bank_fields(event, user):
    prediction = Prediction.objects.filter(event=event, user=user).first()
    if not prediction:
        return []
    fields = []
    for key, label in PREDICTION_FIELDS:
        if key.startswith("sprint_") and not event.has_sprint:
            continue
        value = getattr(prediction, key, None)
        if value not in (None, ""):
            fields.append({"key": key, "label": label})
    wildcard = PlayerWildcard.objects.filter(event=event, user=user).first()
    if wildcard and wildcard.selected_option:
        fields.append({"key": "wildcard", "label": "Личная карта этапа"})
    return fields


def va_bank_answer_is_correct(prediction, result, field_key, wildcard=None):
    if field_key == "wildcard":
        return bool(wildcard and wildcard.is_correct)
    if field_key in {"safety_car_count", "dnf_count"}:
        return getattr(prediction, field_key) == getattr(result, field_key)
    if field_key == "driver_of_day":
        predicted = str(prediction.driver_of_day or "").strip().lower()
        actual_values = getattr(result, "driver_of_day_multiple", None) or []
        if not actual_values and result.driver_of_day:
            actual_values = [result.driver_of_day]
        return bool(predicted and predicted in {str(value).strip().lower() for value in actual_values})
    if field_key == "crazy_prediction":
        return bool((prediction.crazy_prediction or "").strip() and prediction.crazy_prediction_approved)
    if field_key in {"p1", "p2", "p3", "pole", "fastest_lap", "sprint_qualifying_winner", "sprint_winner"}:
        predicted = str(getattr(prediction, field_key, "") or "").strip().lower()
        actual = str(getattr(result, field_key, "") or "").strip().lower()
        return bool(predicted and actual and predicted == actual)
    return False


def _score_window_open(event, now):
    return wheel_window_is_open(event, now)


def _target_prediction(event, user_id, *, must_have_crazy=False):
    prediction = Prediction.objects.select_related("user").filter(
        event=event,
        user_id=user_id,
        user__is_active=True,
        user__is_staff=False,
    ).first()
    if prediction is None:
        raise ArcadeWheelError("Выбранный игрок не отправил прогноз на этот этап.")
    if must_have_crazy and not (prediction.crazy_prediction or "").strip():
        raise ArcadeWheelError("У выбранного игрока нет Crazy Prediction на этот этап.")
    return prediction


@transaction.atomic
def activate_event_wheel_prize(event, user, payload, now=None):
    now = now or timezone.now()
    locked_event = Event.objects.select_for_update().get(pk=event.pk)
    if not _score_window_open(locked_event, now):
        raise ArcadeWheelError("Приз нужно активировать до старта гонки.")

    spin = ArcadeWheelSpin.objects.select_for_update().filter(event=locked_event).first()
    if not spin or spin.winner_id != user.id:
        raise ArcadeWheelError("Этот приз доступен только победителю аркадной недели.")
    if spin.activated_at:
        raise ArcadeWheelError("Приз уже активирован.")

    activation_data = {}
    target_user = None

    if spin.prize == ArcadeWheelSpin.Prize.PODIUM_EDIT:
        if not podium_edit_is_open(locked_event, now):
            raise ArcadeWheelError("Апдейт подиума можно применить после квалификации и до старта гонки.")
        prediction = Prediction.objects.select_for_update().filter(
            event=locked_event,
            user=user,
        ).first()
        if prediction is None:
            raise ArcadeWheelError("Для апдейта подиума сначала нужен твой прогноз на этап.")
        slot = str(payload.get("slot", "")).strip()
        driver = str(payload.get("driver", "")).strip()
        if slot not in ("p1", "p2", "p3") or driver not in dict(DRIVER_CHOICES):
            raise ArcadeWheelError("Выбери место подиума и пилота из списка.")
        other_drivers = {
            getattr(prediction, field)
            for field in ("p1", "p2", "p3")
            if field != slot
        }
        if driver == getattr(prediction, slot) or driver in other_drivers:
            raise ArcadeWheelError("Новый пилот должен отличаться от текущего прогноза подиума.")
        activation_data = {
            "slot": slot,
            "old_driver": getattr(prediction, slot),
            "new_driver": driver,
        }
        setattr(prediction, slot, driver)
        prediction.save(update_fields=(slot,))

    elif spin.prize == ArcadeWheelSpin.Prize.VA_BANK:
        field_key = str(payload.get("field", "")).strip()
        fields = available_va_bank_fields(locked_event, user)
        if field_key not in {field["key"] for field in fields}:
            raise ArcadeWheelError("Выбери один из своих сохранённых прогнозов для Ва-банка.")
        activation_data = {"field": field_key}

    elif spin.prize in (ArcadeWheelSpin.Prize.RUEL_V_GOVNE, ArcadeWheelSpin.Prize.CRAZY_BLOCK):
        try:
            target_id = int(payload.get("target_user"))
        except (TypeError, ValueError) as exc:
            raise ArcadeWheelError("Выбери участника для эффекта.") from exc
        if target_id == user.id:
            raise ArcadeWheelError("Нельзя выбрать самого себя.")
        target_prediction = _target_prediction(
            locked_event,
            target_id,
            must_have_crazy=spin.prize == ArcadeWheelSpin.Prize.CRAZY_BLOCK,
        )
        target_user = target_prediction.user

    spin.target_user = target_user
    spin.activation_data = activation_data
    spin.activated_at = now
    spin.save(update_fields=("target_user", "activation_data", "activated_at"))
    return spin
