"""Private league HTTP surface; all object lookups are membership scoped."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .competition_scoring import judge_crazy_prediction, recalculate_league_event
from .forms import PredictionForm
from .league_forms import CreateLeagueForm
from .prediction_submission import save_shared_prediction
from .leagues import (
    accept_invite, create_invite, create_league, invite_for_token, membership_for,
    require_moderator, revoke_invite, set_member_role,
)
from .models import (
    Event, League, LeagueCrazyDecision, LeagueEventScore,
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
    selected = seasons.order_by("-season__year").first()
    if selected is None:
        raise Http404("У лиги пока нет сезона.")
    return selected


def _rights(user, league):
    member = membership_for(user, league)
    return {"is_owner": league.owner_id == user.pk, "can_manage": league.owner_id == user.pk or member.role == "moderator"}


@login_required
@never_cache
@require_GET
def index(request):
    seasons = LeagueSeason.objects.filter(league__memberships__user=request.user,
        league__memberships__is_active=True, league__archived_at__isnull=True
    ).select_related("league", "season", "start_event").annotate(
        member_count=Count("entries", distinct=True)).order_by("-season__year", "-created_at")
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
            season = create_league(owner=request.user, name=form.cleaned_data["name"],
                season=get_object_or_404(Season, year=event.season_year), start_event=event,
                ruleset=form.cleaned_data["ruleset"])
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
    entries = season.entries.select_related("membership__user__league_profile", "first_event").annotate(
        total=Sum("leagueeventscore_records__points", default=0),
        rounds=Count("leagueeventscore_records", distinct=True),
    ).order_by("-total", "membership__user__username", "pk")
    page = Paginator(entries, 50).get_page(request.GET.get("page"))
    for offset, entry in enumerate(page.object_list, page.start_index()):
        entry.rank = offset
        entry.is_owner = entry.membership.user_id == league.owner_id
    events = Event.objects.filter(season_year=season.season.year,
        round_number__gte=season.start_event.round_number).order_by("round_number")
    next_event = events.filter(deadline__gt=timezone.now(), status=Event.Status.OPEN).first()
    context = dict(league=league, league_season=season, seasons=league.seasons.select_related("season").order_by("-season__year"),
        page=page, events=events, next_event=next_event, **_rights(request.user, league))
    return render(request, "leagues/detail.html", context)


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def invites(request, league_id):
    league = _league(request, league_id)
    season = _season(request, league)
    require_moderator(request.user, league)
    link = None
    if request.method == "POST":
        try:
            _, token = create_invite(actor=request.user, league_season=season)
            link = request.build_absolute_uri(reverse("league:friend_league_join", args=[token]))
        except ValidationError as exc:
            messages.error(request, _error(exc))
    rows = season.invites.select_related("created_by").order_by("-created_at")[:30]
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


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def join(request, token):
    try:
        invite = invite_for_token(token)
    except ValidationError as exc:
        raise Http404("Приглашение недоступно или срок его действия истёк.") from exc
    if request.method == "POST":
        try:
            entry = accept_invite(user=request.user, token=token)
        except ValidationError as exc:
            messages.error(request, _error(exc))
        else:
            messages.success(request, f"Вы в лиге! Ваш первый зачётный этап — {entry.first_event}.")
            return redirect(f"{reverse('league:friend_league', args=[entry.membership.league_id])}?year={entry.league_season.season.year}")
    response = render(request, "leagues/join.html", {"invite": invite, "league": invite.league_season.league})
    response["Referrer-Policy"] = "no-referrer"
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
                messages.success(request, "Базовый прогноз сохранён для всех ваших зачётов.")
                return redirect("league:friend_league_event", league_id=league.pk, event_id=event.pk)
    rows = []
    if now >= event.deadline:
        predictions = {p.user_id: p for p in Prediction.objects.filter(event=event, created_at__lt=event.deadline,
            user_id__in=season.entries.filter(first_event__round_number__lte=event.round_number).values("membership__user_id"))}
        scores = {s.entry_id: s for s in LeagueEventScore.objects.filter(event=event, entry__league_season=season)}
        decisions = {d.entry_id: d for d in LeagueCrazyDecision.objects.filter(event=event, entry__league_season=season)}
        for entry in season.entries.filter(first_event__round_number__lte=event.round_number).select_related("membership__user"):
            p = predictions.get(entry.membership.user_id)
            rows.append({"entry": entry, "prediction": p, "score": scores.get(entry.pk), "decision": decisions.get(entry.pk)})
    return render(request, "leagues/event.html", dict(league=league, league_season=season, event=event,
        prediction=prediction, form=form, editable=editable, rows=rows, closed=now >= event.deadline,
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
        judge_crazy_prediction(actor=request.user, league_season=entry.league_season, entry=entry,
            event=event, approved=choice == "yes")
    except ValidationError as exc:
        messages.error(request, _error(exc))
    else:
        messages.success(request, "Решение сохранено только в этой лиге.")
    return redirect("league:friend_league_event", league_id=league.pk, event_id=event.pk)


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
