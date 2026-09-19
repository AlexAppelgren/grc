"""Django project configuration. Importing the Celery app here is what lets the worker
and beat find `config.celery.app` with `celery -A config` (docs/runbooks/RAILWAY_DEPLOY.md)."""

from config.celery import app as celery_app

__all__ = ["celery_app"]
