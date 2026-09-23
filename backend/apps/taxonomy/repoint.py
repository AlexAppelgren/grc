"""Re-pointing rows from one vocabulary value to another (VOC-02 merge). Each function
returns the number of records that move and runs inside the caller's transaction, so a
failure halfway leaves nothing changed.

`dry_run=True` answers the same number without writing: the merge preview and the commit
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


def nothing_to_repoint(source: Any, target: Any, *, dry_run: bool = False) -> int:
    """No table references this list; a merge only retires the source."""
    return 0


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


def library_links(links: tuple[Link, ...]) -> Callable[..., int]:
    """The merge preview of a library list: how many records its approval would move. The
    move itself happens only inside the approval (`move()`, called by apps/proposals/apply.py)."""

    def preview(source: Any, target: Any, *, dry_run: bool = False) -> int:
        if not dry_run:
            raise RuntimeError("A library list's rows move only inside an approved merge proposal (VOC-07).")
        return sum(split(link, source, target)[0].count() for link in links)

    return preview


def move(links: tuple[Link, ...], source: Any, target: Any, *, library: Mover) -> dict[str, int]:
    """Re-point every link of a library list from `source` to `target`, each table through
    the door that may write it; answers the records moved per table."""
    moved: dict[str, int] = {}
    for link in links:
        moving, twins = split(link, source, target)
        door = watch_door.repoint if link.model in WATCH_MODELS else library
        moved[link.table] = door(moving, twins, link.field, target)
    return moved


def tenant_tag(source: Any, target: Any, *, dry_run: bool = False) -> int:
    """Move every tagging from `source` to `target`; a record that already carries the
    target keeps one tagging (the unique constraint), so the duplicate is dropped and not
    counted as moved."""
    already = set(Tagging.objects.filter(tag=target).values_list("subject_type", "subject_id"))
    taggings = Tagging.objects.filter(tag=source).order_by("created_at", "id")
    if dry_run:
        return sum(1 for pair in taggings.values_list("subject_type", "subject_id") if pair not in already)
    moved = 0
    for tagging in taggings:
        if (tagging.subject_type, tagging.subject_id) in already:
            tagging.delete()
            continue
        tagging.tag = target
        tagging.save(update_fields=["tag"])
        moved += 1
    return moved
