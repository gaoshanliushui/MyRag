"""
Celery Application Configuration

Async task processing for:
- Document parsing and chunking
- Embedding generation
- Indexing into Milvus, ES, Neo4j
- Tiered storage management
- Cleanup and maintenance
"""

from celery import Celery
from celery.schedules import crontab

from app.config import settings

# Create Celery app
celery_app = Celery(
    "myrag",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Configuration
celery_app.conf.update(
    # Serialization
    task_serializer=settings.CELERY_TASK_SERIALIZER,
    result_serializer=settings.CELERY_RESULT_SERIALIZER,
    accept_content=settings.CELERY_ACCEPT_CONTENT,

    # Time limits
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,

    # Result settings
    result_expires=3600,  # 1 hour
    result_backend_transport_options={
        "master_name": "mymaster",
    },

    # Task settings
    task_track_started=True,
    task_send_sent_event=True,
    task_acks_late=True,  # Acknowledge after task completes
    task_reject_on_worker_lost=True,

    # Worker settings
    worker_prefetch_multiplier=1,  # One task per worker at a time
    worker_concurrency=4,

    # Beat schedule for periodic tasks
    beat_schedule={
        # Tiered storage management - daily at 2am
        "tier-management": {
            "task": "app.tasks.indexing.tier_management_task",
            "schedule": crontab(hour=2, minute=0),
        },
        # Query quota reset - daily at midnight
        "quota-reset": {
            "task": "app.tasks.indexing.reset_daily_quotas_task",
            "schedule": crontab(hour=0, minute=0),
        },
        # Fragment merge - weekly on Sunday at 3am
        "fragment-merge": {
            "task": "app.tasks.indexing.merge_fragments_task",
            "schedule": crontab(hour=3, minute=0, day_of_week=0),
        },
        # Cleanup old sessions - hourly
        "session-cleanup": {
            "task": "app.tasks.indexing.cleanup_sessions_task",
            "schedule": crontab(minute=0),
        },
    },

    # Task routing
    task_routes={
        "app.tasks.documents.*": {"queue": "documents"},
        "app.tasks.indexing.*": {"queue": "indexing"},
    },

    # Default queue
    task_default_queue="default",

    # Logging
    worker_log_format="[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
    worker_task_log_format="[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s",
)

# Autodiscover tasks from modules
celery_app.autodiscover_tasks([
    "app.tasks.documents",
    "app.tasks.indexing",
])


# Base task class with error handling
from celery import Task
from app.utils.logging import get_logger

logger = get_logger("tasks.base")


class BaseTask(Task):
    """Base task with error handling and retry logic."""

    def on_failure(self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo: str) -> None:
        """Handle task failure."""
        logger.error(
            f"Task {self.name} ({task_id}) failed: {exc}",
            extra={"task_id": task_id, "args": args, "kwargs": kwargs}
        )

        # Record error metric
        from app.core.monitoring.metrics import record_error, TASKS_TOTAL
        tenant_id = kwargs.get("tenant_id", args[1] if len(args) > 1 else "unknown")
        record_error(tenant_id, type(exc).__name__)
        TASKS_TOTAL.labels(task_name=self.name, status="failure").inc()

    def on_success(self, retval: Any, task_id: str, args: tuple, kwargs: dict) -> None:
        """Handle task success."""
        logger.debug(f"Task {self.name} ({task_id}) succeeded")

        from app.core.monitoring.metrics import TASKS_TOTAL
        TASKS_TOTAL.labels(task_name=self.name, status="success").inc()

    def on_retry(self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo: str) -> None:
        """Handle task retry."""
        logger.warning(
            f"Task {self.name} ({task_id}) retrying: {exc}",
            extra={"task_id": task_id}
        )

        from app.core.monitoring.metrics import TASKS_TOTAL
        TASKS_TOTAL.labels(task_name=self.name, status="retry").inc()


# Register base task class
celery_app.Task = BaseTask