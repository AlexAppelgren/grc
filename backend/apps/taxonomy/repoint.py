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
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.db.models import Exists, OuterRef, QuerySet

from apps.taxonomy.models import Tagging
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

    @property
    def table(self) -> str:
        return str(self.model._meta.db_table)


def nothing_to_repoint(source: Any, target: Any, *, dry_run: bool = False) -> Moves:
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


def tenant_tag(source: Any, target: Any, *, dry_run: bool = False) -> Moves:
    """Move every tagging from `source` to `target`; a record that already carries the
    target keeps one tagging (the unique constraint), so the duplicate is dropped and not
    counted as moved."""
    already = set(Tagging.objects.filter(tag=target).values_list("subject_type", "subject_id"))
    taggings = Tagging.objects.filter(tag=source).order_by("created_at", "id")
    rows = Moved([], [])
    for tagging in taggings:
        twin = (tagging.subject_type, tagging.subject_id) in already
        (rows.dropped if twin else rows.moved).append(str(tagging.id))
        if dry_run:
            continue
        if twin:
            tagging.delete()
            continue
        tagging.tag = target
        tagging.save(update_fields=["tag"])
    return {Tagging._meta.db_table: rows}
