from django.core.management.base import BaseCommand
from django.utils import timezone
from games.models import Game

class Command(BaseCommand):
    help = "Auto-close games whose end_time has passed"

    def handle(self, *args, **kwargs):
        now = timezone.now()
        games = Game.objects.filter(
            auto_close=True,
            is_active=True,
            end_time__lte=now
        )

        for game in games:
            game.close_game_and_select_winners()
            self.stdout.write(self.style.SUCCESS(
                f"Closed game {game.id} and selected winners (if any)."
            ))
