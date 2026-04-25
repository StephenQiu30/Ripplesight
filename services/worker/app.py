from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab


def create_celery_app() -> Celery:
    app = Celery("ai_hotspot_radar", include=["services.worker.tasks"])
    app.conf.update(
        broker_url=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
        result_backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1"),
        timezone=os.getenv("APP_TIMEZONE", "Asia/Shanghai"),
        enable_utc=True,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_always_eager=os.getenv("CELERY_TASK_ALWAYS_EAGER", "0") == "1",
        task_store_eager_result=True,
        beat_schedule={
            "deliver-daily-digest": {
                "task": "worker.generate_and_deliver_daily_digest",
                "schedule": crontab(hour=8, minute=0),
            }
        },
    )
    return app


celery_app = create_celery_app()

# Import task modules after the app is constructed so decorators register tasks
# deterministically in both eager tests and worker runtime.
from services.worker import tasks as _tasks  # noqa: F401,E402
