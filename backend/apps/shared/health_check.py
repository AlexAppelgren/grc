"""`/health/` (playbook 2.2, 5): checks the database, the cache, the worker and the
pgvector extension. 200 when every component is ok; 503 naming the failing component.
The worker ping is bounded (`limit=1`) so one reply ends it, and its timeout is a
setting. Never authenticated, never CORS-scoped, never cached."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.db import DEFAULT_DB_ALIAS, connections
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)

CACHE_PROBE_KEY = "health:probe"


@dataclass(frozen=True)
class ComponentStatus:
    name: str
    ok: bool
    detail: str = ""


def check_database() -> ComponentStatus:
    try:
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:  # compliance: allow-broad-except a health probe reports any failure as down
        return ComponentStatus("database", False, type(exc).__name__)
    return ComponentStatus("database", True)


def check_pgvector() -> ComponentStatus:
    try:
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            row = cursor.fetchone()
    except Exception as exc:  # compliance: allow-broad-except a health probe reports any failure as down
        return ComponentStatus("pgvector", False, type(exc).__name__)
    if row is None:
        return ComponentStatus("pgvector", False, "extension vector is not installed")
    return ComponentStatus("pgvector", True, f"vector {row[0]}")


def check_cache() -> ComponentStatus:
    try:
        cache.set(CACHE_PROBE_KEY, "ok", timeout=5)
        value = cache.get(CACHE_PROBE_KEY)
    except Exception as exc:  # compliance: allow-broad-except a health probe reports any failure as down
        return ComponentStatus("cache", False, type(exc).__name__)
    if value != "ok":
        return ComponentStatus("cache", False, "probe value did not round-trip")
    return ComponentStatus("cache", True)


def check_worker() -> ComponentStatus:
    from config.celery import app as celery_app

    try:
        replies = celery_app.control.ping(
            timeout=settings.HEALTH_WORKER_PING_TIMEOUT_S, limit=settings.HEALTH_WORKER_PING_LIMIT
        )
    except Exception as exc:  # compliance: allow-broad-except a health probe reports any failure as down
        return ComponentStatus("worker", False, type(exc).__name__)
    if not replies:
        return ComponentStatus("worker", False, "no worker answered the ping")
    return ComponentStatus("worker", True)


CHECKS: tuple[Callable[[], ComponentStatus], ...] = (
    check_database,
    check_pgvector,
    check_cache,
    check_worker,
)


def run_checks() -> list[ComponentStatus]:
    return [check() for check in CHECKS]


@require_GET
def health_view(request: HttpRequest) -> JsonResponse:
    statuses = run_checks()
    failing = [status.name for status in statuses if not status.ok]
    body = {
        "status": "ok" if not failing else "degraded",
        "failing": failing,
        "components": {
            status.name: {"ok": status.ok, "detail": status.detail} for status in statuses
        },
    }
    if failing:
        logger.warning("health check failing", extra={"failing": failing})
    response = JsonResponse(body, status=200 if not failing else 503)
    response["Cache-Control"] = "no-store"
    return response
