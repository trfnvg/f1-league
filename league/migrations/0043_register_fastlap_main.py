"""Attach the existing company to My Leagues, without migrating its scores."""
import uuid

from django.db import migrations
from django.db.models import Q
from django.utils import timezone


def register_main(apps, schema_editor):
    db = schema_editor.connection.alias
    User = apps.get_model("auth", "User")
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
    # This account is the confirmed owner of the original installation. Never
    # choose an arbitrary staff user or assign a public user's account ownership.
    owner = (User.objects.using(db).filter(pk=league.owner_id).first() if league else
        User.objects.using(db).filter(username="trfnvg", is_active=True, is_staff=True).first())
    if owner is None:
        # Fresh installs/test DBs have no original company. A differently named
        # production owner can use the existing explicit --owner import command.
        return
    now = timezone.now()
    years = Event.objects.using(db).order_by("season_year").values_list("season_year", flat=True).distinct()
    for year in years:
        first = Event.objects.using(db).filter(season_year=year).order_by("round_number", "pk").first()
        players = User.objects.using(db).filter(is_staff=False).filter(
            Q(pk__in=Prediction.objects.using(db).filter(event__season_year=year).values("user_id"))
            | Q(pk__in=Score.objects.using(db).filter(event__season_year=year).values("user_id"))
            | Q(pk__in=SeasonPrediction.objects.using(db).filter(season_year=year).values("user_id"))
            | Q(pk__in=SeasonScore.objects.using(db).filter(season_year=year).values("user_id")))
        if not players.exists():
            continue
        season, _ = Season.objects.using(db).get_or_create(year=year, defaults={"title": f"F1 Predictions {year}"})
        if league is None:
            league = League.objects.using(db).create(id=uuid.uuid4(), name="Fastlap Main",
                owner_id=owner.pk, legacy_key="original-friends", created_at=min(first.deadline, now))
        ls, _ = LeagueSeason.objects.using(db).get_or_create(league_id=league.pk, season_id=season.pk,
            defaults={"start_event_id": first.pk, "ruleset": "paddock", "is_legacy": True,
                      "created_at": min(first.deadline, now)})
        for user_id in set(players.values_list("pk", flat=True)) | {owner.pk}:
            member, _ = Membership.objects.using(db).get_or_create(league_id=league.pk, user_id=user_id,
                defaults={"joined_at": min(first.deadline, now)})
            Entry.objects.using(db).get_or_create(league_season_id=ls.pk, membership_id=member.pk,
                defaults={"first_event_id": first.pk, "entered_at": min(first.deadline, now)})
    if league:
        League.objects.using(db).filter(pk=league.pk).update(name="Fastlap Main")


class Migration(migrations.Migration):
    dependencies = [("league", "0042_private_league_invites")]
    # Retain the memberships on rollback: removing them would destroy access
    # and could cascade or conflict with subsequently recorded league history.
    operations = [migrations.RunPython(register_main, migrations.RunPython.noop)]
