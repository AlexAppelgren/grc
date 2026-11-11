"""The watch door: the second named way into the library zone.

A change, its timeline and pages are sourced public facts no person proposes, so the watch
pipeline opens `library_write()` (PRO-01), but narrowly: only the seven watch tables, never
an authority, instrument, provision, obligation or version table, which stay behind the
proposal door.

- Who may open it: only this module is on `LIBRARY_WRITE_ALLOWLIST` under apps/watch/, and
  `tests_library_fence.py` restricts `watch_write()` to the watch steps that own a write.
- What it may write: a connection wrapper refuses a write of any other library table
  wherever it sits in the statement (first, in a CTE, after a semicolon), covering ORM calls
  and raw SQL alike.

Reads and non-library tables are untouched: `record()` writes audit and outbox rows (AUD-01).
"""

from __future__ import annotations

import functools
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from django.apps import apps as django_apps
from django.db import DEFAULT_DB_ALIAS, connections

from apps.shared import tenancy
from apps.shared.tenancy import LibraryModel, library_write
from apps.watch.models import WATCH_MODELS

WATCH_TABLES = frozenset(model._meta.db_table for model in WATCH_MODELS)

# Every table a statement writes, wherever the write sits: a write verb counts where a
# statement can begin (start, after `(`, after `;`), since raw SQL can hide a write in a CTE
# or a second statement, and COPY, MERGE and TRUNCATE use none of the usual words. Every
# match is checked. `FOR UPDATE OF "obligation"` is a locking read and does not count.
_WRITE_STATEMENT = re.compile(
    r'(?:^|[(;])\s*(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+INTO|COPY|TRUNCATE(?:\s+TABLE)?)'
    r'\s+(?:ONLY\s+)?"?(?P<table>\w+)"?',
    re.IGNORECASE,
)


class WatchWriteRefused(RuntimeError):
    """A library table outside the watch zone was written through the watch door."""


@functools.cache
def _tables_behind_the_proposal_door() -> frozenset[str]:
    """Every library table the watch door may not write. Computed once: the model registry
    is fixed by the time the first request runs."""
    return frozenset(
        model._meta.db_table
        for model in django_apps.get_models()
        if issubclass(model, LibraryModel) and model._meta.db_table not in WATCH_TABLES
    )


def _refuse_writes_outside_the_watch_zone(
    execute: Any, sql: str, params: Any, many: bool, context: dict[str, Any]
) -> Any:
    forbidden = _tables_behind_the_proposal_door()
    for match in _WRITE_STATEMENT.finditer(sql):
        table = match.group("table")
        if table in forbidden:
            raise WatchWriteRefused(
                f"{table} is not a watch table. The watch door reaches "
                f"{sorted(WATCH_TABLES)} only; every other library record changes through an "
                "approved proposal (PRO-01)."
            )
    return execute(sql, params, many, context)


@contextmanager
def watch_write(reason: str) -> Iterator[None]:
    """The only context in which a watch table may be written. `reason` names the step and
    travels into the audit row.

    The wrapper sits on the default connection, the one the application writes through; a
    refusal aborts its transaction. The database holds the same line through the watch door
    (H16, shared 0008, ADR 0058). `source` is the one watch table with a zone column
    (WAT-06): a shared source is written with no tenant active."""
    with library_write(f"watch: {reason}", door="watch"), connections[DEFAULT_DB_ALIAS].execute_wrapper(
        _refuse_writes_outside_the_watch_zone
    ):
        yield


def upsert(model: type[Any], reason: str, *, lookup: dict[str, Any], defaults: dict[str, Any]) -> Any:
    """A natural-key `update_or_create` through the door for a seed: idempotent by `lookup`.
    `model` is a parameter, so this never names a watch model (library fence). Runs in
    `tenancy.platform_zone()`, since a seed may share a connection whose ambient tenant would
    make the shared `source` write refuse."""
    with tenancy.platform_zone(), watch_write(reason):
        row, _ = model.objects.update_or_create(**lookup, defaults=defaults)
        return row


def repoint(moving: Any, twins: Any, field: str, target: Any) -> int:
    """Re-point a watch table's rows from a merged-away library value to its target (VOC-02,
    VOC-07) inside an approved merge, whose `apply()` already holds the fence open. Adds only
    the watch door: its own refusal in Python, and in the database the watch door, which
    `library_door()` swaps back to the approval's on exit (H16, ADR 0058). No second
    `library_write()`. `twins` already carry `target`, so they are dropped, not moved."""
    with tenancy.library_door("watch"), connections[DEFAULT_DB_ALIAS].execute_wrapper(_refuse_writes_outside_the_watch_zone):
        twins.delete()
        return int(moving.update(**{field: target}))
