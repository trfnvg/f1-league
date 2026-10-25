from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from league.leagues import import_legacy_league, legacy_member_ids
from league.models import Event, LeagueSeason, Season


class Command(BaseCommand):
    help = "Prepare the original friends' league. Read-only preview unless --apply is explicitly supplied."

    def add_arguments(self, parser):
        parser.add_argument("--owner", required=True, help="Exact username of the league owner")
        parser.add_argument("--season", required=True, type=int)
        parser.add_argument("--name", default="Наша лига")
        parser.add_argument("--apply", action="store_true", help="Create league membership metadata; never edit predictions or scores")

    def handle(self, *args, **options):
        try:
            owner = User.objects.get(username=options["owner"], is_active=True)
            season = Season.objects.get(year=options["season"])
        except (User.DoesNotExist, Season.DoesNotExist) as exc:
            raise CommandError("Укажите существующего активного владельца и существующий сезон.") from exc
        existing = LeagueSeason.objects.filter(league__legacy_key="original-friends", season=season).select_related("league").first()
        if existing:
            if existing.league.owner_id != owner.pk:
                raise CommandError("У перенесённой лиги уже другой владелец.")
            self.stdout.write(f"Уже подготовлено: {existing.league_id}. Изменений нет.")
            return
        first = Event.objects.filter(season_year=season.year).order_by("round_number", "pk").first()
        if first is None:
            raise CommandError("В сезоне нет этапов.")
        players = User.objects.filter(pk__in=legacy_member_ids(season.year, owner)).order_by("username")
        self.stdout.write(f"Сезон {season.year}; старт R{first.round_number}; владелец: {owner.username}.")
        self.stdout.write(f"Участники ({players.count()}): {', '.join(players.values_list('username', flat=True))}")
        if not options["apply"]:
            self.stdout.write("Предварительный просмотр. База не изменена. Для применения добавьте --apply.")
            return
        try:
            league_season, created = import_legacy_league(owner=owner, season_year=season.year, name=options["name"])
        except (ValidationError, PermissionDenied) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            f"{'Подготовлено' if created else 'Уже подготовлено'}: {league_season.league_id}. "
            "Прогнозы, очки и действующие страницы не изменены."
        ))
