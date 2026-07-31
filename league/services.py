from collections import defaultdict

from django.contrib.auth.models import User
from .models import Event, Prediction, Score, Season, SeasonScore, UserProfile


def get_selected_season(request=None):
    active = Season.get_active()
    if request is None:
        return active

    try:
        requested_year = int(request.GET.get("season", ""))
    except (TypeError, ValueError):
        return active
    return Season.objects.filter(year=requested_year).first() or active


def build_leaderboard(season_year):
    events = list(Event.objects.filter(season_year=season_year).order_by("round_number"))
    scores = list(
        Score.objects.filter(event__season_year=season_year)
        .select_related("user", "event")
        .order_by("event__round_number")
    )
    scores_map = {(score.user_id, score.event_id): score for score in scores}
    season_bonuses = {
        row.user_id: row.points
        for row in SeasonScore.objects.filter(season_year=season_year)
    }
    totals = defaultdict(int, season_bonuses)
    event_ids_with_scores = set()
    for score in scores:
        totals[score.user_id] += score.points
        event_ids_with_scores.add(score.event_id)

    users = list(User.objects.filter(is_staff=False, is_active=True))
    users_sorted = sorted(users, key=lambda user: (-totals[user.id], user.username.lower()))
    profiles = {
        profile.user_id: profile
        for profile in UserProfile.objects.filter(user_id__in=[user.id for user in users])
    }

    scored_events = [event for event in events if event.id in event_ids_with_scores]
    latest_event = scored_events[-1] if scored_events else None
    previous_totals = defaultdict(int, season_bonuses)
    for score in scores:
        if latest_event and score.event_id != latest_event.id:
            previous_totals[score.user_id] += score.points
    previous_order = sorted(
        users,
        key=lambda user: (-previous_totals[user.id], user.username.lower()),
    )
    previous_ranks = {user.id: index for index, user in enumerate(previous_order, start=1)}

    latest_points = {
        score.user_id: score.points
        for score in scores
        if latest_event and score.event_id == latest_event.id
    }
    best_latest_points = max(latest_points.values(), default=None)

    rows = []
    chart_series = []
    for rank, user in enumerate(users_sorted, start=1):
        profile = profiles.get(user.id)
        previous_rank = previous_ranks.get(user.id, rank)
        movement = previous_rank - rank if len(scored_events) > 1 else 0
        rows.append(
            {
                "user": user,
                "rank": rank,
                "previous_rank": previous_rank,
                "movement": movement,
                "total": totals[user.id],
                "latest_points": latest_points.get(user.id),
                "is_round_winner": (
                    best_latest_points is not None
                    and latest_points.get(user.id) == best_latest_points
                ),
                "is_leader": rank == 1,
                "avatar_url": profile.avatar.url if profile and profile.avatar else None,
                "is_wpc": bool(profile and profile.is_world_predict_champion),
            }
        )

        cumulative = 0
        points = []
        for index, event in enumerate(scored_events):
            score = scores_map.get((user.id, event.id))
            cumulative += score.points if score else 0
            # Season bonuses have no separate round timestamp. Adding them to
            # the current endpoint keeps the graph's last value identical to
            # the live standings without rewriting the history of every race.
            if index == len(scored_events) - 1:
                cumulative += season_bonuses.get(user.id, 0)
            points.append(cumulative)
        hue = round((user.id * 137.508) % 360)
        chart_series.append(
            {
                "user_id": user.id,
                "name": user.username,
                "color": f"hsl({hue} 68% 46%)",
                "points": points,
            }
        )

    chart = {
        "events": [
            {"round": event.round_number, "name": event.name}
            for event in scored_events
        ],
        "series": chart_series,
    }
    return {
        "events": events,
        "scored_events": scored_events,
        "latest_event": latest_event,
        "scores": scores,
        "scores_map": scores_map,
        "rows": rows,
        "chart": chart,
    }


def build_player_statistics(player, season_year, leaderboard=None):
    leaderboard = leaderboard or build_leaderboard(season_year)
    scored_events = leaderboard["scored_events"]
    scores_map = leaderboard["scores_map"]
    player_scores = [scores_map.get((player.id, event.id)) for event in scored_events]
    points = [score.points if score else 0 for score in player_scores]
    submitted = Prediction.objects.filter(user=player, event__season_year=season_year).count()

    total = sum(points)
    best = max(points, default=0)
    worst = min(points, default=0)
    average = round(total / len(scored_events), 1) if scored_events else 0
    stage_wins = 0
    exact_hits = 0
    pole_hits = 0
    crazy_hits = 0
    podium_hits = 0

    for event, score in zip(scored_events, player_scores):
        event_scores = [
            item.points
            for item in leaderboard["scores"]
            if item.event_id == event.id
        ]
        if score and event_scores and score.points == max(event_scores):
            stage_wins += 1
        if not score:
            continue
        breakdown = score.breakdown or {}
        exact_hits += sum(
            1
            for key in ("P1", "P2", "P3", "Pole Position", "Fastest Lap", "Driver of the Day")
            if breakdown.get(key)
        )
        pole_hits += int(bool(breakdown.get("Pole Position")))
        crazy_hits += int(bool(breakdown.get("Crazy Prediction")))
        podium_hits += int(
            all(breakdown.get(key) for key in ("P1", "P2", "P3"))
        )

    row = next((item for item in leaderboard["rows"] if item["user"].id == player.id), None)
    leader_total = leaderboard["rows"][0]["total"] if leaderboard["rows"] else 0

    cumulative = 0
    trend = []
    for event, value in zip(scored_events, points):
        cumulative += value
        trend.append({"round": event.round_number, "points": cumulative})

    return {
        "total": total,
        "average": average,
        "best": best,
        "worst": worst,
        "stage_wins": stage_wins,
        "exact_hits": exact_hits,
        "pole_hits": pole_hits,
        "crazy_hits": crazy_hits,
        "perfect_podiums": podium_hits,
        "submitted": submitted,
        "completed_events": len(scored_events),
        "rank": row["rank"] if row else None,
        "movement": row["movement"] if row else 0,
        "leader_gap": max(0, leader_total - total),
        "trend": trend,
        "points": points,
    }


def build_achievements(player, statistics):
    profile = getattr(player, "league_profile", None)
    achievements = []

    def add(code, title, description, icon):
        achievements.append(
            {"code": code, "title": title, "description": description, "icon": icon}
        )

    if profile and profile.is_world_predict_champion:
        add("wpc", "World Predict Champion", "Чемпион общего зачёта", "◆")
    if statistics["stage_wins"]:
        add("stage_winner", "Победитель этапа", "Лучший результат хотя бы на одном Гран-при", "🏁")
    if statistics["perfect_podiums"]:
        add("perfect_podium", "Идеальный подиум", "Точно угаданы P1, P2 и P3", "🏆")
    if statistics["pole_hits"] >= 3:
        add("pole_master", "Король квалификации", "Три и более угаданных поула", "⚡")
    if statistics["crazy_hits"]:
        add("crazy", "Это было безумно", "Сбылся Crazy Prediction", "✦")

    positive_streak = 0
    longest_streak = 0
    for points in statistics["points"]:
        if points > 0:
            positive_streak += 1
            longest_streak = max(longest_streak, positive_streak)
        else:
            positive_streak = 0
    if longest_streak >= 3:
        add("streak", "Стабильный темп", f"{longest_streak} этапа подряд с очками", "↗")
    return achievements
