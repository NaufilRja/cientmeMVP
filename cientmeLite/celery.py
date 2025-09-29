import os
from celery import Celery
from celery.schedules import crontab 

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cientmeLite.settings')

app = Celery('cientmeLite')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()



# -------------------------
# Celery Beat Schedule
# -------------------------
app.conf.beat_schedule = {
    "auto-close-games-every-1-min": {
        "task": "games.tasks.auto_close_games_task",
        "schedule": crontab(minute="*/1"),  # runs every 1 minute
    },
}