"""Repair the original company's link to its confirmed production account."""
import uuid

from django.db import migrations
from django.db.models import Q
from django.utils import timezone


def link_main(apps, schema_editor):
    db = schema_editor.connection.alias
    User = apps.get_model("auth", "User")
    player = User.objects.using(db).filter(username="Гриша", is_active=True).first()
    if player is None:
        return
    League = apps.get_model("league", "League")
    LeagueSeason = apps.get_model("league", "LeagueSeason")
    Membership = apps.get_model("league", "LeagueMembership")
    Entry = apps.get_model("league", "LeagueSeasonEntry")
    Season = apps.get_model("league", "Season")
    Event = apps.get_model("league", "Event")
    Prediction = apps.get_model("league", "Prediction")
    Score = apps.get_model("league", "Score")
    SeasonPrediction = apps.get_model("league", "SeasonPrediction")
    SeasonScore = apps.get_model("league", "SeasonScore")
    league = League.objects.using(db).filter(legacy_key="original-friends").first()
    now = timezone.now()
    years = Event.objects.using(db).order_by("season_year").values_list("season_year", flat=True).distinct()
    for year in years:
        first = Event.objects.using(db).filter(season_year=year).order_by("round_number", "pk").first()
        participants = User.objects.using(db).filter(is_staff=False).filter(
            Q(pk__in=Prediction.objects.using(db).filter(event__season_year=year).values("user_id"))
            | Q(pk__in=Score.objects.using(db).filter(event__season_year=year).values("user_id"))
            | Q(pk__in=SeasonPrediction.objects.using(db).filter(season_year=year).values("user_id"))
            | Q(pk__in=SeasonScore.objects.using(db).filter(season_year=year).values("user_id")))
        existing_season = (LeagueSeason.objects.using(db).filter(league_id=league.pk, season__year=year).first()
            if league else None)
        if not participants.exists() and not existing_season:
            continue
        season, _ = Season.objects.using(db).get_or_create(year=year,
            defaults={"title": f"F1 Predictions {year}"})
        if league is None:
            league = League.objects.using(db).create(id=uuid.uuid4(), name="Fastlap Main",
                owner_id=player.pk, legacy_key="original-friends", created_at=min(first.deadline, now))
        ls, _ = LeagueSeason.objects.using(db).get_or_create(league_id=league.pk, season_id=season.pk,
            defaults={"start_event_id": first.pk, "ruleset": "paddock", "is_legacy": True,
                      "created_at": min(first.deadline, now)})
        # The user confirmed this exact production login. Keep any previously
        # imported owner; private membership does not grant Django staff rights.
        for user_id in set(participants.values_list("pk", flat=True)) | {league.owner_id, player.pk}:
            member, _ = Membership.objects.using(db).get_or_create(league_id=league.pk, user_id=user_id,
                defaults={"joined_at": min(first.deadline, now)})
            Entry.objects.using(db).get_or_create(league_season_id=ls.pk, membership_id=member.pk,
                defaults={"first_event_id": first.pk, "entered_at": min(first.deadline, now)})
    if league:
        League.objects.using(db).filter(pk=league.pk).update(name="Fastlap Main")


class Migration(migrations.Migration):
    dependencies = [("league", "0043_register_fastlap_main")]
    operations = [migrations.RunPython(link_main, migrations.RunPython.noop)]
