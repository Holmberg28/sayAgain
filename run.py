from api import create_app
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
from pytz import timezone

# PST Timezone
pst_timezone = timezone('America/Los_Angeles')

app = create_app()
scheduler = BackgroundScheduler(timezone=pst_timezone)


def schedule_task():
    # Import your target function here
    from api.utils import clear_history_and_uploads
    with app.app_context():
        clear_history_and_uploads()


target_time = datetime.now(pst_timezone).replace(hour=2, minute=0, second=0, microsecond=0)

# If target time is in the past, run it next day
if target_time < datetime.now(pst_timezone):
    target_time += timedelta(days=1)

# Schedule the task
scheduler.add_job(
    schedule_task,
    trigger=CronTrigger(hour=target_time.hour, minute=target_time.minute, timezone=pst_timezone)
)

scheduler.start()

if __name__ == "__main__":
    app.run(port=8080)
