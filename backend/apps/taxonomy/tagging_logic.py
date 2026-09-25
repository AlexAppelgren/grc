"""The bank's own tags on a record (VOC-08): one by one, or in a previewed batch.

A tag is a `tagging` row in the tenant zone naming a `tenant_tag` and a record by kind and
id; tagging never touches the record itself, so a library obligation or change stays the
shared fact it was. Which kinds take a tag, and which records a caller may read, is
tagging_subjects.py's read; anything the caller may not read is not there: one record
answers the 404 an unknown id answers, and a batch skips it, counts it and never names it
back, not even in the audit event.

Every write is audited through `record()`: one event per single tag or untag, naming the
record, and exactly one per batch, naming the tag and the ids. A repeat changes nothing
and still writes its one event saying so, so the log shows what was asked as well as what
happened.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.shared.audit import Actor, record
from apps.shared.authentication import Principal
from apps.shared.models import Tenant
from apps.shared.vocabulary import label_for
from apps.taxonomy.models import Tagging, TenantTag
from apps.taxonomy.schemas import TaggingBatchOutcome, TaggingIds, TaggingRecordTags, TaggingSkipped, TaggingTagRef
from apps.taxonomy.tagging_subjects import kind_of, readable, title_of

BATCH_SUBJECT_TYPE = "tenant_tag"


def _tag(tenant: Tenant, key: str, *, applying: bool) -> TenantTag:
    """A retired tag leaves the pickers (AC-VOC2), so it goes on nothing new; it still comes
    off a record that carries it."""
    tag = TenantTag.objects.filter(tenant=tenant, key=key).first()  # ordering: tenant_tag_key_unique, at most one row
    if tag is None or (applying and not tag.active):
        raise ValidationError(f"{key!r} is not one of your organisation's tags.", code="unknown_key")
    return tag


def _ref(tag: TenantTag, order: list[str]) -> TaggingTagRef:
    return TaggingTagRef(key=tag.key, kind=None, label=label_for(tag, order))


def tags_of(subject_type: str, subject_id: uuid.UUID, order: list[str]) -> TaggingRecordTags:
    """The bank's tags on one record, two queries: the tags and their labels."""
    tags = TenantTag.objects.filter(taggings__subject_type=subject_type, taggings__subject_id=subject_id).prefetch_related("labels")
    return TaggingRecordTags(subject_type=subject_type, subject_id=subject_id, tags=[_ref(tag, order) for tag in tags])


def tag(*, tenant: Tenant, who: Principal, actor: Actor, tag_key: str, subject_type: str, subject_id: uuid.UUID) -> None:
    """Put one tag on one record; two racing requests are settled by `tagging_unique`, which
    `get_or_create` falls back on."""
    kind_of(subject_type)
    row_tag = _tag(tenant, tag_key, applying=True)
    title = title_of(who, subject_type, subject_id)
    _, created = Tagging.objects.get_or_create(tenant=tenant, tag=row_tag, subject_type=subject_type, subject_id=subject_id)
    record(
        action="taggings.added",
        actor=actor,
        subject_type=subject_type,
        subject_id=subject_id,
        subject_title=title,
        summary=f"Tagged with {tag_key}." if created else f"Already tagged with {tag_key}; nothing changed.",
        tenant_id=tenant.id,
        after={"tag": tag_key, "changed": created},
    )


def untag(*, tenant: Tenant, who: Principal, actor: Actor, tag_key: str, subject_type: str, subject_id: uuid.UUID) -> None:
    """Take one tag off one record; a record that does not carry it is left as it is."""
    kind_of(subject_type)
    row_tag = _tag(tenant, tag_key, applying=False)
    title = title_of(who, subject_type, subject_id)
    deleted, _ = Tagging.objects.filter(tag=row_tag, subject_type=subject_type, subject_id=subject_id).delete()
    record(
        action="taggings.removed",
        actor=actor,
        subject_type=subject_type,
        subject_id=subject_id,
        subject_title=title,
        summary=f"Removed the tag {tag_key}." if deleted else f"Was not tagged with {tag_key}; nothing changed.",
        tenant_id=tenant.id,
        before={"tag": tag_key} if deleted else None,
        after={"tag": tag_key, "changed": bool(deleted)},
    )


@dataclass(frozen=True)
class _Batch:
    tag: TenantTag
    gained: list[uuid.UUID]
    already: list[uuid.UUID]
    skipped: int


def _plan(tenant: Tenant, who: Principal, tag_key: str, subject_type: str, subject_ids: list[uuid.UUID]) -> _Batch:
    """Sort a batch into gains, records already tagged and skips, in three queries however
    many records: the tag, the readable records and the taggings they already carry."""
    kind_of(subject_type)
    ids = list(dict.fromkeys(subject_ids))
    cap = settings.BULK_TAGGING_MAX_RECORDS
    if len(ids) > cap:
        raise ValidationError(f"Tag at most {cap} records at a time; {len(ids)} were selected.", code="too_many_records")
    row_tag = _tag(tenant, tag_key, applying=True)
    reached = readable(who, subject_type, ids)
    carried = set(
        Tagging.objects.filter(tag=row_tag, subject_type=subject_type, subject_id__in=reached).values_list("subject_id", flat=True)
    )
    gained = [i for i in ids if i in reached and i not in carried]
    already = [i for i in ids if i in carried]
    return _Batch(tag=row_tag, gained=gained, already=already, skipped=len(ids) - len(gained) - len(already))


def _outcome(batch: _Batch, subject_type: str, order: list[str]) -> TaggingBatchOutcome:
    return TaggingBatchOutcome(
        tag=_ref(batch.tag, order),
        subject_type=subject_type,
        gained=TaggingIds(count=len(batch.gained), ids=batch.gained),
        already_tagged=TaggingIds(count=len(batch.already), ids=batch.already),
        skipped=TaggingSkipped(count=batch.skipped),
    )


def preview(
    *, tenant: Tenant, who: Principal, tag_key: str, subject_type: str, subject_ids: list[uuid.UUID], order: list[str]
) -> TaggingBatchOutcome:
    """What a batch would do. A read: it writes nothing, not even an audit row."""
    return _outcome(_plan(tenant, who, tag_key, subject_type, subject_ids), subject_type, order)


def tag_batch(
    *,
    tenant: Tenant,
    who: Principal,
    actor: Actor,
    tag_key: str,
    subject_type: str,
    subject_ids: list[uuid.UUID],
    order: list[str],
) -> TaggingBatchOutcome:
    """Apply one tag to a batch in the request's transaction, with exactly one audit event
    holding the key and the ids of every record the batch reached (VOC-S12)."""
    batch = _plan(tenant, who, tag_key, subject_type, subject_ids)
    Tagging.objects.bulk_create(
        [Tagging(tenant=tenant, tag=batch.tag, subject_type=subject_type, subject_id=subject_id) for subject_id in batch.gained],
        ignore_conflicts=True,
    )
    record(
        action="taggings.batch_added",
        actor=actor,
        subject_type=BATCH_SUBJECT_TYPE,
        subject_id=batch.tag.id,
        subject_title=tag_key,
        summary=(
            f"Tagged {len(batch.gained)} {subject_type} records with {tag_key}; {len(batch.already)} already carried it"
            f" and {batch.skipped} were skipped."
        ),
        tenant_id=tenant.id,
        after={
            "tag": tag_key,
            "subjectType": subject_type,
            "ids": [str(i) for i in batch.gained + batch.already],
            "added": [str(i) for i in batch.gained],
            "skipped": batch.skipped,
        },
    )
    return _outcome(batch, subject_type, order)
