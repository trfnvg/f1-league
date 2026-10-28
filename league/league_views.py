"""Private league HTTP surface; all object lookups are membership scoped."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .competition_scoring import recalculate_league_event
from .forms import PredictionForm
from .league_forms import CreateLeagueForm, LeagueDayForm, LeagueProfileForm
from .league_management import decide_crazy, decide_day, delete_league, require_manager, update_profile
from .league_standings import standings
from .home_events import select_current_event
from .prediction_submission import save_shared_prediction
from .leagues import (
    accept_invite, create_invite, create_league, current_invite, invite_for_token, membership_for,
    require_moderator, revoke_invite, set_member_role,
)
from .models import (
    Event, League, LeagueCrazyDecision, LeagueDayDecision, LeagueEventScore,
    LeagueInvite, LeagueMembership, LeagueSeason, LeagueSeasonEntry, Prediction, Season,
)


def _error(exc):
    return " ".join(exc.messages)


def _league(request, league_id):
    return get_object_or_404(League.objects.filter(
        memberships__user=request.user, memberships__is_active=True, archived_at__isnull=True,
    ), pk=league_id)


def _season(request, league):
    seasons = league.seasons.select_related("season", "start_event", "league")
    year = request.GET.get("year") or request.POST.get("year")
    if year:
        try:
            year = int(year)
        except (TypeError, ValueError, OverflowError) as exc:
            raise Http404("Сезон не найден.") from exc
        if not 1900 <= year <= 9999:
            raise Http404("Сезон не найден.")
        return get_object_or_404(seasons, season__year=year)
    selected = seasons.filter(season__is_active=True).first() or seasons.order_by("-season__year").first()
    if selected is None:
        raise Http404("У лиги пока нет сезона.")
    return selected


def _rights(user, league):
    member = membership_for(user, league)
    return {"is_owner": league.owner_id == user.pk,
        "can_configure": league.owner_id == user.pk or member.role == "manager",
        "can_manage": league.owner_id == user.pk or member.role in ("moderator", "manager")}


@login_required
@never_cache
@require_GET
def index(request):
    seasons = LeagueSeason.objects.filter(league__memberships__user=request.user,
        league__memberships__is_active=True, league__archived_at__isnull=True
    ).select_related("league", "season", "start_event").annotate(
        member_count=Case(When(is_legacy=True, then=Count("entries", distinct=True,
            filter=Q(entries__membership__user__is_staff=False, entries__membership__user__is_active=True))),
            default=Count("entries", distinct=True), output_field=IntegerField()),
        main_first=Case(When(league__legacy_key="original-friends", then=Value(0)), default=Value(1), output_field=IntegerField()),
    ).order_by("main_first", "-season__year", "-created_at")
    if request.GET.get("all") != "1" and not request.GET.get("page"):
        remembered = request.session.get("active_friend_league")
        remembered_year = request.session.get("active_friend_league_year")
        selected = next((s for s in seasons if str(s.league_id) == remembered
            and (remembered_year is None or s.season.year == remembered_year)), None) if remembered else None
        selected = selected or seasons.filter(season__is_active=True).first() or seasons.first()
        if selected:
            return redirect("league:friend_league", league_id=selected.league_id)
    page = Paginator(seasons, 12).get_page(request.GET.get("page"))
    return render(request, "leagues/index.html", {"page": page})


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def create(request):
    form = CreateLeagueForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        event = form.cleaned_data["start_event"]
        try:
            with transaction.atomic():
                # Event cards use a year, not a Season FK. A newly added card
                # must work before anyone has created the season settings row.
                calendar, _ = Season.objects.get_or_create(year=event.season_year,
                    defaults={"title": f"F1 Predictions {event.season_year}"})
                season = create_league(owner=request.user, name=form.cleaned_data["name"],
                    season=calendar, start_event=event, ruleset=form.cleaned_data["ruleset"])
        except ValidationError as exc:
            form.add_error(None, _error(exc))
        else:
            messages.success(request, "Лига создана. Пригласите друзей — ваш прогноз уже общий для всех зачётов.")
            return redirect("league:friend_league", league_id=season.league_id)
    return render(request, "leagues/create.html", {"form": form})


@login_required
@never_cache
@require_GET
def detail(request, league_id):
    league = _league(request, league_id)
    season = _season(request, league)
    request.session["active_friend_league"] = str(league.pk)
    request.session["active_friend_league_year"] = season.season.year
    data = standings(season)
    page = Paginator(data.pop("entries"), 50).get_page(request.GET.get("page"))
    visible = {entry.membership.user_id for entry in page}
    data["rows"] = [r for r in data["rows"] if r["user"].pk in visible]
    now = timezone.now()
    next_event = select_current_event(data["events"], now)
    prediction_open = bool(next_event and next_event.voting_state() == "open" and now < next_event.deadline)
    prediction_soon = bool(next_event and next_event.voting_state() == "soon")
    choices = LeagueSeason.objects.filter(league__memberships__user=request.user,
        league__memberships__is_active=True, league__archived_at__isnull=True).select_related("league", "season").order_by("-season__year", "league__name")
    token = current_invite(actor=request.user, league=league)
    invite_link = request.build_absolute_uri(reverse("league:friend_league_join", args=[token])) if token else None
    context = dict(league=league, league_season=season, season=season.season, league_choices=choices,
        invite_link=invite_link,
        invites_enabled=not season.is_legacy or league.legacy_key == "original-friends",
        page=page, next_event=next_event, prediction_open=prediction_open, prediction_soon=prediction_soon,
        **data, **_rights(request.user, league))
    return render(request, "leagues/detail.html", context)

@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def invites(request, league_id):
    league = _league(request, league_id)
    season = _season(request, league)
    require_moderator(request.user, league)
    if request.method == "POST":
        try:
            create_invite(actor=request.user, league_season=season)
        except ValidationError as exc:
            messages.error(request, _error(exc))
        else:
            return redirect(f"{reverse('league:friend_league_invites', args=[league.pk])}?year={season.season.year}")
    token = current_invite(actor=request.user, league=league)
    link = request.build_absolute_uri(reverse("league:friend_league_join", args=[token])) if token else None
    rows = LeagueInvite.objects.filter(league_season__league=league).select_related("created_by").order_by("-created_at")[:30]
    return render(request, "leagues/invites.html", dict(league=league, league_season=season, invites=rows, invite_link=link, now=timezone.now()))


@login_required
@never_cache
@require_POST
def revoke(request, league_id, invite_id):
    league = _league(request, league_id)
    invite = get_object_or_404(LeagueInvite, pk=invite_id, league_season__league=league)
    revoke_invite(actor=request.user, invite=invite)
    messages.success(request, "Приглашение отозвано.")
    return redirect(f"{reverse('league:friend_league_invites', args=[league.pk])}?year={invite.league_season.season.year}")


@never_cache
@require_http_methods(["GET", "POST"])
def join(request, token):
    try:
        invite = invite_for_token(token)
    except ValidationError as exc:
        raise Http404("Приглашение недоступно или срок его действия истёк.") from exc
    if request.method == "POST":
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.path)
        try:
            entry = accept_invite(user=request.user, token=token)
        except ValidationError as exc:
            messages.error(request, _error(exc))
        else:
            messages.success(request, f"Вы в лиге! Ваш первый зачётный этап — {entry.first_event}.")
            return redirect(f"{reverse('league:friend_league', args=[entry.membership.league_id])}?year={entry.league_season.season.year}")
    members = invite.league_season.entries.filter(membership__is_active=True).select_related("membership__user")
    member_count = members.count()
    preview = list(members.order_by("pk")[:6])
    response = render(request, "leagues/join.html", {"invite": invite, "league": invite.league_season.league,
        "member_count": member_count, "invite_members": preview,
        "invite_more_count": max(0, member_count-len(preview))})
    # Keep invitation URLs off third-party requests without suppressing the
    # same-origin Referer required by Django for HTTPS POSTs without Origin.
    response["Referrer-Policy"] = "same-origin"
    return response


@login_required
@never_cache
@require_POST
def role(request, league_id, membership_id):
    league = _league(request, league_id)
    member = get_object_or_404(LeagueMembership, pk=membership_id, league=league)
    try:
        set_member_role(actor=request.user, membership=member, role=request.POST.get("role", ""))
    except ValidationError as exc:
        messages.error(request, _error(exc))
    else:
        messages.success(request, "Роль участника обновлена.")
    return redirect("league:friend_league", league_id=league.pk)


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def event_detail(request, league_id, event_id):
    league = _league(request, league_id)
    event = get_object_or_404(Event, pk=event_id)
    season = get_object_or_404(league.seasons.select_related("season", "start_event", "league"), season__year=event.season_year,
        start_event__round_number__lte=event.round_number)
    if season.is_legacy and request.GET.get("manage") != "1":
        return redirect("league:event_detail", event_id=event.pk)
    own_entry = season.entries.filter(membership__user=request.user, membership__league=league,
        first_event__round_number__lte=event.round_number).first()
    now = timezone.now()
    editable = bool(own_entry and event.voting_state() == "open" and now < event.deadline and not season.is_legacy)
    prediction = Prediction.objects.filter(user=request.user, event=event).first() if own_entry else None
    form = PredictionForm(instance=prediction, event=event)
    if season.ruleset == "classic":
        form.fields.pop("crazy_prediction", None)
    if request.method == "POST":
        with transaction.atomic():
            event = Event.objects.select_for_update().get(pk=event.pk)
            League.objects.select_for_update().get(pk=league.pk)
            membership_for(request.user, league)
            if not own_entry or event.voting_state() != "open" or timezone.now() >= event.deadline or season.is_legacy:
                messages.error(request, "Прогноз для этого этапа закрыт или ваше участие ещё не началось.")
                return redirect("league:friend_league_event", league_id=league.pk, event_id=event.pk)
            try:
                form, saved = save_shared_prediction(user=request.user, event=event, data=request.POST,
                    include_crazy=season.ruleset == "paddock")
            except ValidationError as exc:
                messages.error(request, _error(exc))
                return redirect("league:friend_league_event", league_id=league.pk, event_id=event.pk)
            if saved:
                messages.success(request, "Прогноз принят для всех ваших зачётов", extra_tags="prediction-saved")
                return redirect("league:friend_league_event", league_id=league.pk, event_id=event.pk)
    rows = []
    if now >= event.deadline:
        predictions = {p.user_id: p for p in Prediction.objects.filter(event=event, created_at__lt=event.deadline,
            user_id__in=season.entries.filter(first_event__round_number__lte=event.round_number).values("membership__user_id"))}
        scores = {s.entry_id: s for s in LeagueEventScore.objects.filter(event=event, entry__league_season=season)}
        legacy_scores = standings(season)["scores_map"] if season.is_legacy else {}
        decisions = {d.entry_id: d for d in LeagueCrazyDecision.objects.filter(event=event, entry__league_season=season)}
        for entry in season.entries.filter(first_event__round_number__lte=event.round_number).select_related("membership__user"):
            p = predictions.get(entry.membership.user_id)
            score = legacy_scores.get((entry.membership.user_id, event.pk)) if season.is_legacy else scores.get(entry.pk)
            rows.append({"entry": entry, "prediction": p, "score": score, "decision": decisions.get(entry.pk)})
    day = LeagueDayDecision.objects.filter(league_season=season, event=event).first()
    day_form = LeagueDayForm(initial={"use_official": day is None, "drivers": day.drivers if day else []})
    return render(request, "leagues/event.html", dict(league=league, league_season=season, event=event,
        prediction=prediction, form=form, editable=editable, rows=rows, closed=now >= event.deadline, day_form=day_form,
        **_rights(request.user, league)))


@login_required
@never_cache
@require_POST
def judge(request, league_id, event_id, entry_id):
    league = _league(request, league_id)
    event = get_object_or_404(Event, pk=event_id)
    entry = get_object_or_404(LeagueSeasonEntry.objects.select_related("league_season"), pk=entry_id, league_season__league=league)
    choice = request.POST.get("approved")
    try:
        if choice not in ("yes", "no"):
            raise ValidationError("Выберите решение по крейзи-предикту.")
        decide_crazy(actor=request.user, season=entry.league_season, entry=entry,
            event=event, approved=choice == "yes")
    except ValidationError as exc:
        messages.error(request, _error(exc))
    else:
        messages.success(request, "Решение сохранено только в этой лиге.")
    return redirect(f"{reverse('league:friend_league_event', args=[league.pk, event.pk])}?manage=1")


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def settings(request, league_id):
    league = _league(request, league_id)
    require_manager(request.user, league)
    season = _season(request, league)
    creating_invite = request.method == "POST" and request.POST.get("action") == "create_invite"
    form = LeagueProfileForm(None if creating_invite else request.POST or None,
        None if creating_invite else request.FILES or None, instance=league)
    if creating_invite:
        try:
            create_invite(actor=request.user, league_season=season)
        except ValidationError as exc:
            messages.error(request, _error(exc))
        else:
            return redirect(f"{reverse('league:friend_league_settings', args=[league.pk])}?year={season.season.year}")
    elif request.method == "POST" and form.is_valid():
        try:
            update_profile(actor=request.user, league=league, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, _error(exc))
        else:
            messages.success(request, "Настройки лиги сохранены.")
            return redirect(f"{reverse('league:friend_league', args=[league.pk])}?year={season.season.year}")
    members = league.memberships.filter(is_active=True).select_related("user", "user__league_profile").order_by("user__username")
    events = list(Event.objects.filter(season_year=season.season.year,
        round_number__gte=season.start_event.round_number).order_by("-round_number"))
    now = timezone.now()
    # Judging is actionable after the prediction deadline. Keep these rounds
    # visible first, followed by upcoming rounds in chronological order.
    events = [event for event in events if event.deadline <= now] + [
        event for event in reversed(events) if event.deadline > now
    ]
    token = current_invite(actor=request.user, league=league)
    invite_link = request.build_absolute_uri(reverse("league:friend_league_join", args=[token])) if token else None
    return render(request, "leagues/settings.html", dict(league=league, league_season=season, form=form,
        members=members, events=events, invite_link=invite_link,
        invites_enabled=not season.is_legacy or league.legacy_key == "original-friends",
        **_rights(request.user, league)))


@login_required
@never_cache
@require_POST
def day_decision(request, league_id, event_id):
    league = _league(request, league_id)
    event = get_object_or_404(Event, pk=event_id)
    season = get_object_or_404(league.seasons, season__year=event.season_year)
    form = LeagueDayForm(request.POST)
    try:
        if not form.is_valid():
            raise ValidationError("Проверьте выбор гонщика дня.")
        decide_day(actor=request.user, season=season, event=event,
            drivers=None if form.cleaned_data["use_official"] else form.cleaned_data["drivers"])
    except ValidationError as exc:
        messages.error(request, _error(exc))
    else:
        messages.success(request, "Гонщик дня сохранён только в этой лиге.")
    return redirect(f"{reverse('league:friend_league_event', args=[league.pk, event.pk])}?manage=1")


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def delete(request, league_id):
    league = _league(request, league_id)
    if league.owner_id != request.user.pk:
        raise PermissionDenied("Удалить лигу может только её создатель.")
    error = None
    if request.method == "POST":
        try:
            delete_league(actor=request.user, league=league, confirmation=request.POST.get("confirmation"))
        except ValidationError as exc:
            error = _error(exc)
        else:
            if request.session.get("active_friend_league") == str(league.pk):
                request.session.pop("active_friend_league", None)
                request.session.pop("active_friend_league_year", None)
            messages.success(request, "Лига удалена из списка у всех участников. Общие прогнозы сохранены.")
            return redirect(f"{reverse('league:friend_leagues')}?all=1")
    return render(request, "leagues/delete.html", {"league": league, "error": error})


@login_required
@never_cache
@require_POST
def recalculate(request, league_id, event_id):
    league = _league(request, league_id)
    event = get_object_or_404(Event, pk=event_id)
    season = get_object_or_404(league.seasons, season__year=event.season_year)
    try:
        recalculate_league_event(actor=request.user, league_season=season, event=event)
    except ValidationError as exc:
        messages.error(request, _error(exc))
    else:
        messages.success(request, "Очки этой лиги пересчитаны.")
    return redirect("league:friend_league_event", league_id=league.pk, event_id=event.pk)
