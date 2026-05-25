"""Celery application factory.

Import this module to get the configured Celery app:

    from aegisops_api.worker import celery_app
"""

from __future__ import annotations

from celery import Celery

from .settings import get_settings


def _make_celery() -> Celery:
    settings = get_settings()
    app = Celery(
        "aegisops",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=["aegisops_api.tasks"],
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        # Store results for 24 hours so the polling endpoint can always answer
        result_expires=86400,
        # Retry failed tasks up to 3 times with exponential back-off
        task_acks_late=True,
        task_reject_on_worker_lost=True,
    )
    return app


celery_app = _make_celery()
