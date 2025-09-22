from celery import shared_task
from django.utils import timezone
from .models import Game

@shared_task
def auto_close_games_task():
    now = timezone.now()
    games = Game.objects.filter(is_active=True, end_time__lte=now, auto_close=True)
    for game in games:
        game.close_game_and_select_winners()  # closes + declares winners
