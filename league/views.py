from django.shortcuts import render, get_object_or_404
from .models import Event, Prediction, Score
from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import render, get_object_or_404, redirect

def home(request):
    events = Event.objects.all()
    return render(request, "home.html", {"events": events})

from django.utils import timezone
from .forms import PredictionForm

def event_detail(request, event_id: int):
    event = get_object_or_404(Event, id=event_id)
    photos = event.photos.all()

    prediction = None
    if request.user.is_authenticated:
        prediction = Prediction.objects.filter(event=event, user=request.user).first()

    state = event.voting_state()
    is_locked = state != "open"
    # is_locked = (event.status != "open") or (event.deadline and event.deadline < timezone.now())

    if request.method == "POST":
        if not request.user.is_authenticated:
            messages.error(request, "Нужно войти.")
            return redirect(f"/events/{event.id}/")

        state = event.voting_state()
        is_locked = state != "open"

        if is_locked:
            if state == "soon":
                messages.error(request, "Голосование ещё не началось. Откроется за 7 дней до гонки.")
            elif state == "scored":
                messages.error(request, "Очки уже посчитаны — прогнозы зафиксированы.")
            else:
                messages.error(request, "Дедлайн прошёл — прогнозы закрыты.")
            return redirect(f"/events/{event.id}/")

        form = PredictionForm(request.POST, instance=prediction)
        if form.is_valid():
            new_prediction = form.save(commit=False)
            new_prediction.user = request.user
            new_prediction.event = event
            new_prediction.save()
            messages.success(request, "Прогноз сохранён ✅")
            return redirect(f"/events/{event.id}/")
    else:
        state = event.voting_state()
        is_locked = state != "open"
        form = PredictionForm(instance=prediction)

    score = None
    if request.user.is_authenticated:
        score = Score.objects.filter(event=event, user=request.user).first()

    return render(request, "event_detail.html", {
        "event": event,
        "photos": photos,
        "form": form,
        "prediction": prediction,
        "state": state,
        "is_locked": is_locked,
        "score": score,
    })


from django.contrib.auth.models import User
from django.db.models import Count

from django.contrib.auth.models import User
from django.db.models import Sum
from .models import Event, Score

def leaderboard(request):
    events = Event.objects.all()

    # Все очки по этапам
    scores = Score.objects.select_related("user", "event").all()
    scores_map = {(s.user_id, s.event_id): s for s in scores}

    # Сумма очков по пользователю
    totals_qs = (
        Score.objects.values("user_id")
        .annotate(total=Sum("points"))
    )
    totals_map = {x["user_id"]: int(x["total"] or 0) for x in totals_qs}

    # Игроки (не staff)
    users = list(User.objects.filter(is_staff=False))

    # Сортировка по очкам (desc), затем по username (для стабильности)
    users_sorted = sorted(users, key=lambda u: (-totals_map.get(u.id, 0), u.username.lower()))

    leader_score = totals_map.get(users_sorted[0].id, 0) if users_sorted else 0

    # Готовим строки таблицы
    rows = []
    for idx, u in enumerate(users_sorted, start=1):
        total = totals_map.get(u.id, 0)
        gap = leader_score - total
        rows.append({
            "user": u,
            "rank": idx,
            "total": total,
            "is_leader": (idx == 1),
        })

    return render(request, "leaderboard.html", {
        "events": events,
        "rows": rows,
        "scores_map": scores_map,
    })
