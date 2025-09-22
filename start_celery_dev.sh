

# Activate virtual environment
source /Users/naufil/cientmeMVP/venv/bin/activate

# Stop any existing Celery worker or beat to avoid duplicates
pkill -f 'celery -A cientmeLite'

# Start Celery worker in background with unique name and log to file
celery -A cientmeLite worker --loglevel=INFO --detach --logfile=/Users/naufil/cientmeMVP/celery_worker.log -n worker1@%h

# Start Celery beat in background and log to file
celery -A cientmeLite beat --loglevel=INFO --detach --logfile=/Users/naufil/cientmeMVP/celery_beat.log

echo "✅ Celery worker and beat started in the background."
