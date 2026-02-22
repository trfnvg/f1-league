from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render

from .forms import PredictionForm, RegisterForm
from .models import Event, Prediction, Score


def home(request):
    events = Event.objects.all()
    return render(request, "home.html", {"events": events})


def register(request):
    next_url = request.GET.get("next") or request.POST.get("next") or "league:home"

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            if next_url.startswith("/"):
                return redirect(next_url)
            return redirect("league:home")
    else:
        form = RegisterForm()

    return render(request, "registration/register.html", {"form": form, "next": next_url})


def event_detail(request, event_id: int):
    event = get_object_or_404(Event, id=event_id)
    photos = event.photos.all()

    prediction = None
    if request.user.is_authenticated:
        prediction = Prediction.objects.filter(event=event, user=request.user).first()

    state = event.voting_state()
    is_locked = state != "open"

    if request.method == "POST":
        if not request.user.is_authenticated:
            messages.error(request, "Нужно войти в аккаунт.")
            return redirect("league:event_detail", event_id=event.id)

        state = event.voting_state()
        is_locked = state != "open"

        if is_locked:
            if state == "soon":
                messages.error(request, "Голосование еще не началось. Оно откроется за 7 дней до гонки.")
            elif state == "scored":
                messages.error(request, "Очки уже посчитаны, прогнозы зафиксированы.")
            else:
                messages.error(request, "Дедлайн прошел, прогнозы закрыты.")
            return redirect("league:event_detail", event_id=event.id)

        form = PredictionForm(request.POST, instance=prediction)
        if form.is_valid():
            new_prediction = form.save(commit=False)
            new_prediction.user = request.user
            new_prediction.event = event
            new_prediction.save()
            messages.success(request, "Прогноз сохранен.")
            return redirect("league:event_detail", event_id=event.id)
    else:
        state = event.voting_state()
        is_locked = state != "open"
        form = PredictionForm(instance=prediction)

    score = None
    if request.user.is_authenticated:
        score = Score.objects.filter(event=event, user=request.user).first()

    return render(request, "event_detail_v2.html", {
        "event": event,
        "photos": photos,
        "form": form,
        "prediction": prediction,
        "state": state,
        "is_locked": is_locked,
        "score": score,
    })


def leaderboard(request):
    events = Event.objects.all()

    scores = Score.objects.select_related("user", "event").all()
    scores_map = {(s.user_id, s.event_id): s for s in scores}

    totals_qs = Score.objects.values("user_id").annotate(total=Sum("points"))
    totals_map = {x["user_id"]: int(x["total"] or 0) for x in totals_qs}

    users = list(User.objects.filter(is_staff=False))
    users_sorted = sorted(users, key=lambda u: (-totals_map.get(u.id, 0), u.username.lower()))

    rows = []
    for idx, user in enumerate(users_sorted, start=1):
        rows.append({
            "user": user,
            "rank": idx,
            "total": totals_map.get(user.id, 0),
            "is_leader": idx == 1,
        })

    return render(request, "leaderboard.html", {
        "events": events,
        "rows": rows,
        "scores_map": scores_map,
    })
