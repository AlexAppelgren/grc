"""Structured JSON log lines with the request ID (playbook 2.1, 4.7)."""

from __future__ import annotations

import logging
import traceback
from datetime import UTC, datetime
from types import TracebackType
from typing import Any

from django.http import HttpRequest
from pythonjsonlogger.json import JsonFormatter as _JsonFormatter

from apps.shared.middleware import loggable_route


class JsonFormatter(_JsonFormatter):
    """One JSON object per line: ts, level, logger, message, request_id, plus any `extra`.
    The request_id is attached by apps.shared.middleware.RequestIdLogFilter."""

    def add_fields(
        self, log_record: dict[str, Any], record: logging.LogRecord, message_dict: dict[str, Any]
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        log_record["ts"] = datetime.fromtimestamp(record.created, tz=UTC).isoformat()
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        log_record.setdefault("request_id", getattr(record, "request_id", None))
        # A request's repr and path can carry a tenant's key or search text (F6), so `request`
        # is dropped and django.request's message names the route; the request id already
        # names the request. The one place that rewrites it.
        log_record.pop("request", None)
        request = getattr(record, "request", None)
        if record.name == "django.request" and isinstance(request, HttpRequest):
            log_record["message"] = f"{getattr(record, 'status_code', '')} {request.method} {loggable_route(request)}"
        # Celery's failure lines carry the exception's repr, traceback and task arguments, and
        # a database error's message holds the failing row (security-review-c10 M2). The task,
        # its id and what happened stay; frames and types come from formatException.
        if record.name == "celery.app.trace" and isinstance(record.args, dict) and "exc" in record.args:
            log_record["message"] = str(record.msg) % {**record.args, "exc": "[redacted]"}
            log_record.pop("data", None)

    def formatException(
        self, ei: tuple[type[BaseException], BaseException, TracebackType | None] | tuple[None, None, None]
    ) -> str:
        """The frames and the exception types, oldest cause first, and never a message: a
        database error's message carries the failing row's values and a unique violation
        its key, so a message is tenant content (playbook 4.7)."""
        chain: list[BaseException] = []
        error = ei[1]
        while error is not None and all(error is not seen for seen in chain):
            chain.append(error)
            error = error.__cause__ or (None if error.__suppress_context__ else error.__context__)
        return "\n".join(
            "Traceback (most recent call last):\n"
            + "".join(traceback.format_tb(link.__traceback__))
            + f"{type(link).__module__}.{type(link).__qualname__}"
            for link in reversed(chain)
        )
