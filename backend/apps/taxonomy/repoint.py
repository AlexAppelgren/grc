"""Re-pointing rows from one vocabulary value to another (VOC-02 merge). One function per
tenant list that something references; each returns the number of records that move and
runs inside the caller's transaction, so a failure halfway leaves nothing changed.

`dry_run=True` answers the same number without writing: the merge preview and the commit
count the same way, so the number a person approved is the number that moved.

Library lists are re-pointed by apps/proposals/apply.py when their merge proposal is
approved; chunk 2 has no library table that references one yet."""

from __future__ import annotations

from typing import Any

from apps.taxonomy.models import Tagging


def nothing_to_repoint(source: Any, target: Any, *, dry_run: bool = False) -> int:
    """No table references this list yet (chunk 2); a merge only retires the source."""
    return 0


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
