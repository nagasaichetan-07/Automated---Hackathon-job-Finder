"""
Aegis — Celery Worker & Beat Scheduler Configuration

Configures the distributed task queue with Redis broker and result backend.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab
from core.config.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "aegis_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["apps.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "sweep-and-dispatch-sources-every-minute": {
            "task": "aegis.sweep_and_dispatch_sources",
            "schedule": 60.0,
        },
        "send-daily-digests-at-9am-utc": {
            "task": "aegis.send_daily_digests",
            "schedule": crontab(hour=9, minute=0),
        },
        "process-pending-notifications-every-5-min": {
            "task": "aegis.process_pending_notifications",
            "schedule": 300.0,
        },
    },
)
