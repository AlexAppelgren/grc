"""The watch door: the second named way into the library zone (chunk 5 plan, ruling H).

`library_write()` is the fence every library row sits behind (PRO-01). Approved proposals
open it, the reference seeds open it, and the watch pipeline opens it — because a change,
its timeline and its source pages are sourced public facts that no person proposes. The
door here is narrower than the one the allowlist held before it: it reaches the seven
watch tables of apps/watch/models.py and nothing else, so a watch step cannot write an
authority, an instrument, a provision, an obligation or a version table even by mistake.
Those stay behind the proposal door, where four eyes and a step-up are.

Two halves make that true:

- **Who may open it.** `apps/watch/write.py` is the only module under apps/watch/ on
  `LIBRARY_WRITE_ALLOWLIST`, and the AST guard in apps/shared/tests_library_fence.py
  restricts `watch_write()` itself to the four watch steps that own a write.
- **What it may write.** Inside the block a database wrapper reads every statement the
  connection runs and refuses a write of any library table outside the seven, wherever in
  the statement that write sits — first, inside a common table expression, or after a
  semicolon. It sits at the connection, not at the model, so `save()`, `update()`,
  `delete()` and `bulk_create()` are all covered by one rule, and so is raw SQL.

Reads are untouched, and so are the tables that are not library rows: `record()` writes
its audit and outbox rows in the same transaction as the change it describes (AUD-01).
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

# Every table a statement writes, wherever the write sits in it. Django puts its
# `INSERT INTO "table"`, `UPDATE "table" SET` and `DELETE FROM "table"` first, but raw SQL
# need not: a data-modifying common table expression hides the write inside brackets
# (`WITH x AS (INSERT INTO obligation ...) SELECT ...`), a second statement hides it after
# a semicolon, and COPY, MERGE and TRUNCATE write without any of those three words. So a
# write verb counts wherever a statement can begin — at the start, after `(`, after `;` —
# and every match is checked, not only the first.
#
# It deliberately does not count `... FOR UPDATE OF "obligation"`, which is a locking read
# and which an anchor-free pattern would refuse.
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
    """The only context in which a watch table may be written. `reason` names the step —
    the registration, the curation, the source check, the So what draft — and travels into
    the audit row the caller records.

    The wrapper sits on the default connection, the one the application writes through;
    the `app` alias exists for the guards, which read. A refusal aborts the transaction it
    happened in, which is what a fence breach should do. The database holds the same line
    a second time: the door named below opens the seven watch tables and no other (H16,
    shared 0008, ADR 0058).

    A shared source is written with no tenant active. `source` is the one watch table with
    a zone column (WAT-06), and its write rule is the session's own zone alone, so a
    session with a tenant activated writes that bank's private source and only a session
    with none writes the shared row a sweep reads (`c5-seed-watch`, `seed_e2e`)."""
    with library_write(f"watch: {reason}", door="watch"), connections[DEFAULT_DB_ALIAS].execute_wrapper(
        _refuse_writes_outside_the_watch_zone
    ):
        yield


def upsert(model: type[Any], reason: str, *, lookup: dict[str, Any], defaults: dict[str, Any]) -> Any:
    """A natural-key `update_or_create` through the door, for a caller with nothing more
    than a fixture to write (`seed_e2e`, c6-e2e-seed): idempotent by the lookup it is given,
    so a second run of the seed finds the same row rather than a duplicate.

    `model` arrives as a parameter rather than an import, which is what lets this live in
    `write.py` beside the door's own definition without naming a watch model: the split
    `apps/shared/tests_library_fence.py` demands of every other door step (`apps/watch/
    keys.py` resolves what a caller named; the step that writes never names the record) is
    the same one this generic helper keeps, the other way round — the caller names the
    model, this function never does.

    Runs inside `tenancy.platform_zone()`: `source` is the one watch table with a zone
    column (WAT-06), written only by a session with no tenant active, and a seed script may
    share one connection across several calls whose ambient tenant this function must never
    depend on (proven to fail 2026-09-21: a second `seed_e2e()` call on the same connection
    left a tenant active from the first, and the shared source it seeds refused the write)."""
    with tenancy.platform_zone(), watch_write(reason):
        row, _ = model.objects.update_or_create(**lookup, defaults=defaults)
        return row
