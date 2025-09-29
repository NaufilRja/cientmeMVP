from django.core.management.base import BaseCommand
from django.utils import timezone
from games.models import Game, GameHistory, WinningNumber
import random

class Command(BaseCommand):
    help = "Fix old finished games by selecting winners and generating winning numbers."

    def handle(self, *args, **kwargs):
        now = timezone.now()

        # -----------------------------
        # Step 0: Fix past GameHistory objects with empty decrypted_winning_numbers
        # -----------------------------
        empty_histories = GameHistory.objects.filter(decrypted_winning_numbers__exact="")
        for gh in empty_histories:
            numbers = list(range(gh.guess_min, gh.guess_min + gh.number_of_winners))
            gh.decrypted_winning_numbers = ",".join(map(str, numbers))
            gh.save(update_fields=['decrypted_winning_numbers'])
            self.stdout.write(self.style.SUCCESS(
                f"Fixed GameHistory {gh.id}: {gh.decrypted_winning_numbers}"
            ))

        # -----------------------------
        # Step 1: Fix old games
        # -----------------------------
        games = Game.objects.filter(end_time__lt=now, winners_selected=False)

        if not games.exists():
            self.stdout.write(self.style.SUCCESS("No old games found that need fixing."))
            return

        for game in games:
            try:
                self.stdout.write(f"Fixing Game: {game.title} (id={game.id})")

                # Try to get numbers
                numbers = []
                if game.winning_numbers_encrypted:
                    try:
                        decrypted = game.decrypt_numbers(game.winning_numbers_encrypted)
                        numbers = list(map(int, decrypted.split(",")))
                    except Exception:
                        self.stdout.write(self.style.WARNING("Decryption failed, generating new numbers."))
                
                if not numbers:
                    numbers = random.sample(
                        range(game.guess_min, game.guess_max + 1),
                        min(game.number_of_winners, game.guess_max - game.guess_min + 1)
                    )
                    if hasattr(game, "encrypt_numbers"):
                        game.winning_numbers_encrypted = game.encrypt_numbers(",".join(map(str, numbers)))
                        game.save(update_fields=["winning_numbers_encrypted"])

                # Create WinningNumber rows
                for idx, num in enumerate(numbers, start=1):
                    wn, created = WinningNumber.objects.get_or_create(
                        game=game,
                        number=num,
                        defaults={
                            "prize_position": idx,
                            "is_claimed": False,
                        },
                    )

                # Mark game updated
                game.winners_selected = True
                game.auto_close = True
                game.auto_select_winner = True
                game.save(update_fields=["winners_selected", "auto_close", "auto_select_winner"])

                self.stdout.write(self.style.SUCCESS(f"✅ Fixed Game ID {game.id}, winners selected."))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Error fixing Game ID {game.id}: {e}"))
