from django.core.management.base import BaseCommand
from league.arcade_video import cleanup


class Command(BaseCommand):
    help = "Remove abandoned video uploads and retry deletion of replaced best videos."

    def handle(self, *args, **options):
        cleanup()
        self.stdout.write("Очистка видеозаписей завершена.")
