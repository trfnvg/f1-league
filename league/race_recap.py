"""Build share-card facts from published, stored results; no score mutation."""
from django.db.models import Q

from .circuits import resolve_circuit
from .identity import display_name
from .models import DuelChallenge, Event, Score


def summary(*, event, player, score, score_rows, season=None):
    circuit = resolve_circuit(event.circuit, event.name, event.season_year)
    profile = getattr(player, "league_profile", None)
    data = dict(name=display_name(player), handle="@"+profile.handle if profile and profile.handle else "",
        initials="".join(word[0] for word in display_name(player).split()[:2]).upper(),
        event=event.name, round=event.round_number, year=event.season_year, points=score.points,
        circuit_path=circuit["path"] if circuit else "", location=circuit["location"] if circuit else "GRAND PRIX",
        scope=season.league.name if season else "Общий зачёт", is_league=season is not None, rank=None, movement=None, overtook=[],
        rank_label="МЕСТО НА ЭТАПЕ", hits=sum(row["points"] > 0 for row in score_rows),
        categories=len(score_rows), duel=None)
    if season:
        from .league_standings import standings
        table = standings(season)
        events = {item.pk: item for item in table["events"]
                  if item.round_number <= event.round_number and item.status == Event.Status.SCORED}
        entries = [entry for entry in table["entries"] if entry.first_event.round_number <= event.round_number]
        totals = {entry.membership.user_id: 0 for entry in entries}
        previous = dict(totals)
        for (uid, eid), saved in table["scores_map"].items():
            if eid not in events or uid not in totals:
                continue
            totals[uid] += saved.points
            if events[eid].round_number < event.round_number:
                previous[uid] += saved.points
        def ranks(values, candidates):
            ordered = sorted(candidates, key=lambda entry: (-values[entry.membership.user_id],
                display_name(entry.membership.user).lower(), entry.membership.user_id))
            return {entry.membership.user_id: index for index, entry in enumerate(ordered, 1)}
        after = ranks(totals, entries)
        data.update(rank=after.get(player.pk), rank_label="ПОЗИЦИЯ В ЛИГЕ")
        earlier_round = max((item.round_number for item in events.values() if item.round_number < event.round_number), default=None)
        if earlier_round is not None:
            old_entries = [entry for entry in entries if entry.first_event.round_number <= earlier_round]
            before = ranks(previous, old_entries)
            if player.pk in before and player.pk in after:
                data["movement"] = before[player.pk]-after[player.pk]
                data["overtook"] = [display_name(entry.membership.user) for entry in old_entries
                    if before[entry.membership.user_id] < before[player.pk]
                    and after[entry.membership.user_id] > after[player.pk]]
    else:
        scores = list(Score.objects.filter(event=event, user__is_active=True, user__is_staff=False)
            .select_related("user"))
        scores.sort(key=lambda item: (-item.points, display_name(item.user).lower(), item.user_id))
        data["rank"] = next((index for index, item in enumerate(scores, 1) if item.user_id == player.pk), None)
    # Private league projections don't contain the global duel bonus.
    if season is None or season.is_legacy:
        duel = DuelChallenge.objects.filter(event=event, status=DuelChallenge.Status.SETTLED).filter(
            Q(challenger=player) | Q(opponent=player)).select_related("challenger", "opponent").first()
        if duel:
            data["duel"] = dict(opponent=display_name(duel.opponent_for(player)),
                label="НИЧЬЯ" if not duel.winner_id else "ПОБЕДА" if duel.winner_id == player.pk else "ПОРАЖЕНИЕ",
                points=duel.adjustment_for(player))
    return data
