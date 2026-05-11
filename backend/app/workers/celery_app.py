from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "aitesthub",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)
celery_app.conf.task_default_queue = "aitesthub"
celery_app.conf.task_routes = {"app.workers.tasks.*": {"queue": "aitesthub"}}
