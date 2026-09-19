"""Structured JSON log lines with the request ID (playbook 2.1, 4.7)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from pythonjsonlogger.json import JsonFormatter as _JsonFormatter


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
