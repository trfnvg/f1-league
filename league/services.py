from collections import Counter, defaultdict

from django.contrib.auth.models import User
from .models import (
    DRIVER_CHOICES,
    DuelChallenge,
    Event,
    Prediction,
    Result,
    Score,
    Season,
    SeasonScore,
    UserProfile,
)


CHART_COLORS = (
    "#E6392F",  # racing red
    "#1473E6",  # vivid blue
    "#159D73",  # emerald
    "#8E44D6",  # violet
    "#F28C18",  # orange
    "#00A6B4",  # cyan
    "#D62F8A",  # magenta
    "#687A16",  # olive
    "#223A75",  # navy
    "#C55A11",  # burnt orange
    "#6D3B9C",  # deep purple
    "#008A9A",  # teal
    "#B02A37",  # crimson
    "#548C2F",  # leaf green
    "#B66A00",  # amber
    "#3D7C98",  # steel blue
    "#A23B72",  # berry
    "#5E6AD2",  # indigo
)
DRIVER_LABELS = dict(DRIVER_CHOICES)


def _normalize(value):
    if value is None:
        return ""
    return str(value).strip().lower()


def _percent(hits, attempts):
    return round(hits * 100 / attempts) if attempts else 0


def _driver_of_day_values(result):
    values = result.driver_of_day_multiple or ([result.driver_of_day] if result.driver_of_day else [])
    return {_normalize(value) for value in values if _normalize(value)}


def _russian_plural(value, forms):
    value = abs(int(value))
    if value % 100 in range(11, 15):
        return forms[2]
    if value % 10 == 1:
        return forms[0]
    if value % 10 in range(2, 5):
        return forms[1]
    return forms[2]


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
    chart_color_index = {
        user.id: index
        for index, user in enumerate(sorted(users, key=lambda item: item.id))
    }
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
        color = CHART_COLORS[chart_color_index[user.id] % len(CHART_COLORS)]
        chart_series.append(
            {
                "user_id": user.id,
                "name": user.username,
                "color": color,
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
        "season_year": season_year,
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

    completed_predictions = {
        prediction.event_id: prediction
        for prediction in Prediction.objects.filter(
            user=player,
            event_id__in=[event.id for event in scored_events],
        ).select_related("event__result")
    }
    accuracy = {
        "winner": {"label": "Победитель", "hits": 0, "attempts": 0},
        "podium": {"label": "Пилоты в топ-3", "hits": 0, "attempts": 0},
        "pole": {"label": "Поул", "hits": 0, "attempts": 0},
        "fastest_lap": {"label": "Fastest Lap", "hits": 0, "attempts": 0},
        "driver_of_day": {"label": "Driver of the Day", "hits": 0, "attempts": 0},
        "safety_car": {"label": "Safety Car", "hits": 0, "attempts": 0},
        "dnf": {"label": "DNF", "hits": 0, "attempts": 0},
        "crazy": {"label": "Crazy Prediction", "hits": 0, "attempts": 0},
    }
    favorite_driver_counts = Counter()

    def register_accuracy(code, hit):
        accuracy[code]["attempts"] += 1
        accuracy[code]["hits"] += int(bool(hit))

    for event in scored_events:
        prediction = completed_predictions.get(event.id)
        result = getattr(event, "result", None)
        if not prediction or not result:
            continue

        actual_top3 = {
            _normalize(result.p1),
            _normalize(result.p2),
            _normalize(result.p3),
        }
        actual_top3.discard("")
        register_accuracy("winner", _normalize(prediction.p1) == _normalize(result.p1))

        predicted_podium = [prediction.p1, prediction.p2, prediction.p3]
        podium_slot_hits = sum(
            1 for value in predicted_podium if _normalize(value) in actual_top3
        )
        accuracy["podium"]["attempts"] += len(predicted_podium)
        accuracy["podium"]["hits"] += podium_slot_hits

        register_accuracy("pole", _normalize(prediction.pole) == _normalize(result.pole))
        if _normalize(prediction.fastest_lap) and _normalize(result.fastest_lap):
            register_accuracy(
                "fastest_lap",
                _normalize(prediction.fastest_lap) == _normalize(result.fastest_lap),
            )
        driver_of_day_values = _driver_of_day_values(result)
        if _normalize(prediction.driver_of_day) and driver_of_day_values:
            register_accuracy(
                "driver_of_day",
                _normalize(prediction.driver_of_day) in driver_of_day_values,
            )
        register_accuracy("safety_car", prediction.safety_car_count == result.safety_car_count)
        register_accuracy("dnf", prediction.dnf_count == result.dnf_count)
        if (prediction.crazy_prediction or "").strip():
            register_accuracy("crazy", prediction.crazy_prediction_approved)

        favorite_fields = [
            prediction.p1,
            prediction.p2,
            prediction.p3,
            prediction.pole,
            prediction.fastest_lap,
            prediction.driver_of_day,
        ]
        if event.has_sprint:
            favorite_fields.extend(
                [prediction.sprint_qualifying_winner, prediction.sprint_winner]
            )
        favorite_driver_counts.update(value for value in favorite_fields if value)

    for category in accuracy.values():
        category["rate"] = _percent(category["hits"], category["attempts"])

    ranked_categories = [item for item in accuracy.values() if item["attempts"]]
    strongest_category = (
        max(ranked_categories, key=lambda item: (item["rate"], item["attempts"], item["hits"]))
        if ranked_categories
        else None
    )
    weakest_category = (
        min(ranked_categories, key=lambda item: (item["rate"], -item["attempts"], item["label"]))
        if ranked_categories
        else None
    )
    favorite_driver_code = favorite_driver_counts.most_common(1)[0][0] if favorite_driver_counts else ""

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
        "winner_accuracy": accuracy["winner"]["rate"],
        "podium_accuracy": accuracy["podium"]["rate"],
        "pole_accuracy": accuracy["pole"]["rate"],
        "category_accuracy": accuracy,
        "favorite_driver": DRIVER_LABELS.get(favorite_driver_code, "—"),
        "strongest_category": strongest_category,
        "weakest_category": weakest_category,
    }


def build_duel(player_a, player_b, season_year, leaderboard=None):
    leaderboard = leaderboard or build_leaderboard(season_year)
    scores_map = leaderboard["scores_map"]
    scored_events = leaderboard["scored_events"]
    rows_by_user = {row["user"].id: row for row in leaderboard["rows"]}
    profiles = {
        profile.user_id: profile
        for profile in UserProfile.objects.filter(user_id__in=(player_a.id, player_b.id))
    }
    stats_a = build_player_statistics(player_a, season_year, leaderboard=leaderboard)
    stats_b = build_player_statistics(player_b, season_year, leaderboard=leaderboard)

    wins_a = 0
    wins_b = 0
    ties = 0
    cumulative_a = 0
    cumulative_b = 0
    event_rows = []
    graph_events = []
    graph_a = []
    graph_b = []
    for event in scored_events:
        score_a = scores_map.get((player_a.id, event.id))
        score_b = scores_map.get((player_b.id, event.id))
        points_a = score_a.points if score_a else 0
        points_b = score_b.points if score_b else 0
        cumulative_a += points_a
        cumulative_b += points_b
        if points_a > points_b:
            winner = "a"
            wins_a += 1
        elif points_b > points_a:
            winner = "b"
            wins_b += 1
        elif score_a or score_b:
            winner = "tie"
            ties += 1
        else:
            winner = "none"
        event_rows.append(
            {
                "event": event,
                "points_a": points_a,
                "points_b": points_b,
                "winner": winner,
                "cumulative_a": cumulative_a,
                "cumulative_b": cumulative_b,
            }
        )
        graph_events.append({"round": event.round_number, "name": event.name})
        graph_a.append(cumulative_a)
        graph_b.append(cumulative_b)

    category_rows = []
    for code in (
        "winner",
        "podium",
        "pole",
        "fastest_lap",
        "driver_of_day",
        "safety_car",
        "dnf",
        "crazy",
    ):
        category_a = stats_a["category_accuracy"][code]
        category_b = stats_b["category_accuracy"][code]
        if not category_a["attempts"] and not category_b["attempts"]:
            continue
        category_rows.append(
            {
                "label": category_a["label"],
                "a": category_a,
                "b": category_b,
            }
        )

    def player_data(player, statistics, color):
        row = rows_by_user.get(player.id, {})
        profile = profiles.get(player.id)
        return {
            "user": player,
            "total": row.get("total", 0),
            "rank": row.get("rank"),
            "average": statistics["average"],
            "avatar_url": profile.avatar.url if profile and profile.avatar else None,
            "color": color,
        }

    return {
        "player_a": player_data(player_a, stats_a, "#E6392F"),
        "player_b": player_data(player_b, stats_b, "#1473E6"),
        "wins_a": wins_a,
        "wins_b": wins_b,
        "ties": ties,
        "event_rows": event_rows,
        "category_rows": category_rows,
        "graph": {
            "events": graph_events,
            "series": [
                {"name": player_a.username, "color": "#E6392F", "points": graph_a},
                {"name": player_b.username, "color": "#1473E6", "points": graph_b},
            ],
        },
    }


def build_activity_feed(leaderboard, limit=10):
    users = [row["user"] for row in leaderboard["rows"]]
    if not users:
        return []

    season_year = leaderboard["season_year"]
    scored_events = leaderboard["scored_events"]
    event_ids = [event.id for event in scored_events]
    user_ids = [user.id for user in users]
    predictions = {
        (prediction.user_id, prediction.event_id): prediction
        for prediction in Prediction.objects.filter(
            event_id__in=event_ids,
            user_id__in=user_ids,
        )
    }
    results = {
        result.event_id: result
        for result in Result.objects.filter(event_id__in=event_ids)
    }

    def event_timestamp(event):
        result = results.get(event.id)
        return (
            (result.published_at if result else None)
            or event.race_datetime
            or event.deadline
        )

    def add_event(
        entries,
        *,
        event,
        activity_type,
        icon,
        text,
        meta,
        user_id,
        link_to_event=False,
        anchor="",
    ):
        entries.append(
            {
                "type": activity_type,
                "icon": icon,
                "text": text,
                "meta": meta,
                "user_id": user_id,
                "event_id": event.id if link_to_event else None,
                "source_event_id": event.id,
                "anchor": anchor,
                "occurred_at": event_timestamp(event),
            }
        )

    cumulative = defaultdict(int)
    personal_bests = {}
    previous_ranks = {
        user.id: index
        for index, user in enumerate(sorted(users, key=lambda item: item.username.lower()), start=1)
    }
    previous_leader_id = None
    feed = []
    for event_index, event in enumerate(scored_events):
        event_scores = {}
        for user in users:
            score = leaderboard["scores_map"].get((user.id, event.id))
            event_scores[user.id] = score.points if score else 0
        best_points = max(event_scores.values(), default=0)
        for user in users:
            cumulative[user.id] += event_scores[user.id]
        ordered = sorted(users, key=lambda user: (-cumulative[user.id], user.username.lower()))
        current_ranks = {user.id: index for index, user in enumerate(ordered, start=1)}

        entries = []
        if best_points > 0:
            for winner in users:
                if event_scores[winner.id] == best_points:
                    add_event(
                        entries,
                        event=event,
                        activity_type="winner",
                        icon="🏁",
                        text=f"{winner.username} выиграл этап",
                        meta=f"R{event.round_number} · {event.name} · {best_points} очков",
                        user_id=winner.id,
                        link_to_event=True,
                    )

        unique_leader_id = None
        if ordered:
            leader_points = cumulative[ordered[0].id]
            runner_up_points = cumulative[ordered[1].id] if len(ordered) > 1 else None
            if runner_up_points is None or leader_points > runner_up_points:
                unique_leader_id = ordered[0].id
        if event_index and unique_leader_id and unique_leader_id != previous_leader_id:
            leader = next(user for user in users if user.id == unique_leader_id)
            add_event(
                entries,
                event=event,
                activity_type="leader",
                icon="P1",
                text=f"{leader.username} стал новым лидером чемпионата",
                meta=f"После R{event.round_number} · {cumulative[leader.id]} очков",
                user_id=leader.id,
            )

        for user in users:
            score = leaderboard["scores_map"].get((user.id, event.id))
            if not score:
                continue
            previous_best = personal_bests.get(user.id)
            if previous_best is not None and score.points > previous_best:
                add_event(
                    entries,
                    event=event,
                    activity_type="record",
                    icon="PB",
                    text=f"{user.username} обновил личный рекорд",
                    meta=f"R{event.round_number} · {event.name} · {score.points} очков",
                    user_id=user.id,
                )
            personal_bests[user.id] = max(previous_best or score.points, score.points)

        result = results.get(event.id)
        if result:
            for user in users:
                prediction = predictions.get((user.id, event.id))
                if not prediction:
                    continue
                if all(
                    _normalize(getattr(prediction, field_name))
                    == _normalize(getattr(result, field_name))
                    for field_name in ("p1", "p2", "p3")
                ):
                    add_event(
                        entries,
                        event=event,
                        activity_type="perfect-podium",
                        icon="123",
                        text=f"{user.username} идеально угадал подиум",
                        meta=f"R{event.round_number} · {event.name} · P1, P2 и P3 точно",
                        user_id=user.id,
                        link_to_event=True,
                    )

        if event_index:
            movers = [
                (previous_ranks[user.id] - current_ranks[user.id], user)
                for user in users
                if previous_ranks[user.id] - current_ranks[user.id] > 0
            ]
            if movers:
                movement, mover = max(movers, key=lambda item: (item[0], event_scores[item[1].id]))
                place_word = _russian_plural(movement, ("место", "места", "мест"))
                add_event(
                    entries,
                    event=event,
                    activity_type="movement",
                    icon="↗",
                    text=f"{mover.username} поднялся на {movement} {place_word}",
                    meta=f"После R{event.round_number} · теперь P{current_ranks[mover.id]}",
                    user_id=mover.id,
                )
        feed.extend(entries)
        previous_ranks = current_ranks
        previous_leader_id = unique_leader_id

    duels = (
        DuelChallenge.objects.filter(
            event__season_year=season_year,
            status__in=(DuelChallenge.Status.ACCEPTED, DuelChallenge.Status.SETTLED),
        )
        .select_related("event", "challenger", "opponent", "winner")
        .order_by("responded_at", "id")
    )
    for duel in duels:
        stake_word = _russian_plural(duel.stake, ("очко", "очка", "очков"))
        if duel.responded_at:
            feed.append(
                {
                    "type": "duel-accepted",
                    "icon": "VS",
                    "text": f"Дуэль {duel.challenger.username} — {duel.opponent.username} принята",
                    "meta": f"R{duel.event.round_number} · ставка {duel.stake} {stake_word}",
                    "user_id": duel.opponent_id,
                    "event_id": duel.event_id,
                    "source_event_id": duel.event_id,
                    "anchor": "#event-duel",
                    "occurred_at": duel.responded_at,
                }
            )
        if duel.status == DuelChallenge.Status.SETTLED and duel.settled_at and duel.winner_id:
            feed.append(
                {
                    "type": "duel-result",
                    "icon": "+",
                    "text": f"{duel.winner.username} выиграл дуэль",
                    "meta": (
                        f"R{duel.event.round_number} · {duel.challenger.username} — "
                        f"{duel.opponent.username} · +{duel.stake} {stake_word}"
                    ),
                    "user_id": duel.winner_id,
                    "event_id": duel.event_id,
                    "source_event_id": duel.event_id,
                    "anchor": "#event-duel",
                    "occurred_at": duel.settled_at,
                }
            )

    type_priority = {
        "duel-result": 100,
        "winner": 95,
        "leader": 90,
        "duel-accepted": 85,
        "movement": 80,
        "perfect-podium": 75,
        "record": 70,
    }
    latest_event_id = scored_events[-1].id if scored_events else None
    feed = [item for item in feed if item["source_event_id"] == latest_event_id]
    feed.sort(
        key=lambda item: (item["occurred_at"], type_priority.get(item["type"], 0)),
        reverse=True,
    )
    return feed[:limit]


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
        stage_word = _russian_plural(longest_streak, ("этап", "этапа", "этапов"))
        add("streak", "Стабильный темп", f"{longest_streak} {stage_word} подряд с очками", "↗")
    return achievements
