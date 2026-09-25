"""Re-pointing rows from one vocabulary value to another (VOC-02 merge). Each function
answers, per table, the ids of the rows that move and of the twins dropped (`Moves`), and
runs inside the caller's transaction, so a failure halfway leaves nothing changed. The
merge's `vocabulary.merged` audit row carries those ids (H23), so which records held the
merged-away value can be rebuilt from the log although the link rows move in place.

`dry_run=True` answers the same rows without writing: the merge preview and the commit
count the same way, so the number a person approved is the number that moved.

A tenant list's rows are tenant rows, moved here. A library list's rows sit behind the
fences, so this module only works out which rows move and hands each table to the door
that may write it (`move()`): a watch table to apps/watch/write.py, every other library
table to the approved proposal's own writer in apps/proposals/apply.py. The merged-away
value itself is never touched here: it stays, retired, so a version, an audit row or an
old label that names it still resolves.

Every tenant table is moved in a fixed number of statements however many rows it holds
(H32): the rows are read once, locked, split from their twins in Python (so a nullable
column of a unique key compares as the database's `NULLS NOT DISTINCT` does), and moved
with one bulk update, which also steps a versioned row's `version` so an `If-Match` read
before the merge cannot write the merged-away value back.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Exists, F, OuterRef, QuerySet
from django.utils import timezone

from apps.watch import write as watch_door
from apps.watch.models import WATCH_MODELS

# (rows that move, rows dropped as duplicates, the column, the value it moves to) -> moved
Mover = Callable[[QuerySet[Any], QuerySet[Any], str, Any], int]


@dataclass(frozen=True)
class Moved:
    """The ids of one table's rows a merge moves to the target, and of the twins it drops
    because the row they would duplicate already holds the target."""

    moved: list[str]
    dropped: list[str]


Moves = dict[str, Moved]  # table -> its rows


def count(moves: Moves) -> int:
    """The records a merge moves: dropped twins are not counted."""
    return sum(len(rows.moved) for rows in moves.values())


def audit_rows(moves: Moves) -> dict[str, dict[str, list[str]]]:
    """The ids for a merge's audit row: ids only, never a record's content."""
    return {table: {"moved": rows.moved, "dropped": rows.dropped} for table, rows in moves.items()}


def _ids(rows: QuerySet[Any]) -> list[str]:
    return [str(pk) for pk in rows.order_by("pk").values_list("pk", flat=True)]


@dataclass(frozen=True)
class Link:
    """A column of a library or watch table that holds a value of a library list. A link
    row is a current row, never a version or an append-only ledger row, so moving it
    overwrites no history. `unique_with` names the other columns of a unique constraint
    the column sits in: a row whose twin already holds the target is dropped, not moved."""

    model: type[Any]
    field: str
    unique_with: tuple[str, ...] = ()
    # Tenant links only. `removable`: the rows are removed by stamping `removed_at` and
    # `removed_by`, so only live rows count and move, and a twin is stamped removed rather
    # than deleted. `drop_twins` False: the rows are never deleted, so a twin refuses the
    # merge until a person resolves it.
    removable: bool = False
    drop_twins: bool = True

    @property
    def table(self) -> str:
        return str(self.model._meta.db_table)

    def rows(self) -> QuerySet[Any]:
        """The rows that carry a value: every row, or only the live ones of a removable link."""
        manager = self.model._default_manager
        return manager.filter(removed_at__isnull=True) if self.removable else manager.all()


def nothing_to_repoint(source: Any, target: Any, *, dry_run: bool = False, by: Any = None) -> Moves:
    """No table references this list; a merge only retires the source."""
    return {}


def split(link: Link, source: Any, target: Any) -> tuple[QuerySet[Any], QuerySet[Any]]:
    """The rows of `link` holding `source` that move to `target`, and the ones dropped
    because a row identical but for this column already holds `target`."""
    rows = link.model._default_manager.filter(**{link.field: source})
    if not link.unique_with:
        return rows, rows.none()
    twin = Exists(
        link.model._default_manager.filter(**{link.field: target}).filter(
            **{column: OuterRef(column) for column in link.unique_with}
        )
    )
    return rows.exclude(twin), rows.filter(twin)


def library_links(links: tuple[Link, ...]) -> Callable[..., Moves]:
    """The merge preview of a library list: the rows its approval would move. The move
    itself happens only inside the approval (`move()`, called by apps/proposals/apply.py)."""

    def preview(source: Any, target: Any, *, dry_run: bool = False) -> Moves:
        if not dry_run:
            raise RuntimeError("A library list's rows move only inside an approved merge proposal (VOC-07).")
        moves: Moves = {}
        for link in links:
            moving, twins = split(link, source, target)
            moves[link.table] = Moved(_ids(moving), _ids(twins))
        return moves

    return preview


def move(links: tuple[Link, ...], source: Any, target: Any, *, library: Mover) -> Moves:
    """Re-point every link of a library list from `source` to `target`, each table through
    the door that may write it; answers the ids moved and dropped per table. The rows are
    locked as their ids are read and the door writes exactly those rows, so the ids the
    audit row names are the rows that changed."""
    moves: Moves = {}
    for link in links:
        moving, twins = (_ids(rows.select_for_update()) for rows in split(link, source, target))
        rows = link.model._default_manager
        door = watch_door.repoint if link.model in WATCH_MODELS else library
        door(rows.filter(pk__in=moving), rows.filter(pk__in=twins), link.field, target)
        moves[link.table] = Moved(moving, twins)
    return moves


def tenant_links(links: tuple[Link, ...]) -> Callable[..., Moves]:
    """The merge of a tenant list: every link's rows move from `source` to `target` inside
    the request's transaction, so a refusal or a failure in a later table undoes the
    earlier ones. `by` is the person merging, who stamps a removable twin removed."""

    def merge(source: Any, target: Any, *, dry_run: bool = False, by: Any = None) -> Moves:
        moves: Moves = {}
        for link in links:
            moving, twins = _split_tenant(link, source, target, lock=not dry_run)
            if twins and not link.drop_twins:
                raise ValidationError(
                    f"{len(twins)} {link.table} rows already exist under the value merged into; rename or retire them first.",
                    code="duplicate_key",
                )
            if not dry_run:
                _move_tenant(link, moving, twins, target, by)
            moves[link.table] = Moved(moving, twins)
        return moves

    return merge


def _split_tenant(link: Link, source: Any, target: Any, *, lock: bool) -> tuple[list[str], list[str]]:
    """The ids of `link`'s rows holding `source` that move, and of the twins that do not,
    in two reads however many rows: the target's unique keys, then the source's rows."""
    held = link.rows().filter(**{link.field: target})
    taken = set(held.values_list(*link.unique_with)) if link.unique_with else set()
    rows = link.rows().filter(**{link.field: source}).order_by("pk")
    if lock:
        rows = rows.select_for_update()
    moving: list[str] = []
    twins: list[str] = []
    for pk, *key in rows.values_list("pk", *link.unique_with):
        (twins if link.unique_with and tuple(key) in taken else moving).append(str(pk))
    return moving, twins


def _move_tenant(link: Link, moving: list[str], twins: list[str], target: Any, by: Any) -> None:
    manager = link.model._default_manager
    if twins and link.removable:
        manager.filter(pk__in=twins).update(removed_at=timezone.now(), removed_by_id=by)
    elif twins:
        manager.filter(pk__in=twins).delete()
    columns: dict[str, Any] = {link.field: target}
    if any(field.name == "version" for field in link.model._meta.concrete_fields):
        columns["version"] = F("version") + 1
    manager.filter(pk__in=moving).update(**columns)
