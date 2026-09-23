"""Managing vocabulary lists (VOC-01, VOC-02, VOC-03, VOC-07).

One module serves every list because every list is the same shape: the model, its label
model, the kinds its rows may carry and how a merge re-points come from
apps/taxonomy/registry.py. Adding a list is adding a registry entry; no route, no screen
and no agent read changes (AC-VOC1).

Tier 3 (tenant) lists are written here, under `vocab.manage`, inside the request's
transaction with `record()`. Tier 2 (library) lists are never written here: every write
becomes a proposal (VOC-07), because a library row is shared by every tenant and a rename
moves pills and pickers for all of them. That is also why this module names no
`LibraryModel` class: the library fence's AST guard refuses any module outside the
allowlist that names one and calls a write method.

Three rules from playbook 15 that a screen cannot enforce on its own:

- **Retire, never delete**, and the usage count comes first: an unconfirmed retire of a
  used value answers 409 `in_use` with the count, so the person decides knowing the blast
  radius. `restore` is its inverse.
- **Merge re-points in one audited transaction**, previewed first (`?dryRun=true`).
- **System rows can be relabelled, not removed** (409 `system_row`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Max
from django.utils.text import slugify

from apps.shared.audit import Actor, record
from apps.shared.models import Tenant
from apps.shared.vocabulary import LibraryVocabulary
from apps.taxonomy.reading import CONFIRMATION_JOINS, Labels, confirmation_of, extra_of, label_of
from apps.taxonomy.registry import REGISTRY, VocabularyList
from apps.taxonomy.schemas import (
    PersonRef,
    VocabularyListEntry,
    VocabularyMerged,
    VocabularyRestored,
    VocabularyRetired,
    VocabularyRow,
    VocabularyRowDetail,
    VocabularySuggestionRow,
)
from apps.taxonomy.terms_logic import term_by_ref  # noqa: F401  re-exported: one place turns a ref into a term

SUBJECT_TYPE = "vocabulary"
ORIGINAL_LANGUAGE = "en"

# A near-duplicate is a typo or a case variant of a value that already exists, not a
# different value that shares words with one: "Custdy" beside "Custody" is a mistake;
# "Custody services" beside "Custody" and "Waiting for legal" beside "Waiting for
# sign-off" are values someone meant to create (AC-VOC3). Trigram similarity alone cannot
# tell them apart (0.50 for the typo, 0.44 for the two waiting states, 0.62 for custody
# services, measured 2026-09-19), so it only recalls candidates, cheaply and in Postgres,
# and an edit-similarity ratio on the casefolded labels decides (0.92, 0.70, 0.74). A
# holder of vocab.manage can always insist with `force`.
NEAR_DUPLICATE_RECALL = 0.3
NEAR_DUPLICATE_RATIO = 0.8
MAX_CANDIDATES = 5


class VocabularyProblem(ValidationError):
    """A refusal that carries more than a sentence: the candidates of a duplicate, the usage
    count of a value in use. The route returns `extra` beside the problem's `code` so the
    screen can offer the near match or state the blast radius without a second call. Kept
    off Django's `params`, which would %-format a label containing a percent sign."""

    def __init__(self, message: str, *, code: str, extra: dict[str, Any]) -> None:
        super().__init__(message, code=code)
        self.extra = extra


@dataclass(frozen=True)
class Candidate:
    key: str
    label: str

    def as_dict(self) -> dict[str, str]:
        return {"key": self.key, "label": self.label}


def entry_for(list_name: str) -> VocabularyList:
    entry = REGISTRY.get(list_name)
    if entry is None:
        raise ValidationError(
            f"{list_name!r} is not a vocabulary list. Valid lists: {', '.join(sorted(REGISTRY))}.",
            code="not_found",
        )
    return entry


def _queryset(entry: VocabularyList, tenant_id: uuid.UUID | None) -> Any:
    """The list's rows with their usage count, in the list's own order. The order is
    explicit because Django drops `Meta.ordering` from a GROUP BY query, and the usage
    count is one: without it a reordered list came back in whatever order Postgres chose
    (found by VOC-S3, 2026-09-19). A library list whose rows carry who confirmed them (every
    LibraryVocabulary) joins those facts in; the seeded jurisdiction list has no such
    columns and reads as a seeded row does, empty (D-38)."""
    queryset = entry.usage(entry.model._default_manager.all()).order_by(*(entry.model._meta.ordering or ()))
    if entry.is_library:
        if issubclass(entry.model, LibraryVocabulary):
            queryset = queryset.select_related(*CONFIRMATION_JOINS)
    else:
        if tenant_id is None:
            raise ValidationError("This list belongs to a tenant; sign in to one.", code="not_found")
        queryset = queryset.filter(tenant_id=tenant_id)
    return queryset


# ---------------------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------------------
def list_of_lists(tenant_id: uuid.UUID | None) -> list[VocabularyListEntry]:
    """`GET /vocab`: the list of lists, with how many rows each holds and how many are
    retired, so the admin screen's index needs no call per list."""
    entries: list[VocabularyListEntry] = []
    for name, entry in REGISTRY.items():
        if not entry.is_library and tenant_id is None:
            continue
        rows = entry.model._default_manager.all()
        if not entry.is_library:
            rows = rows.filter(tenant_id=tenant_id)
        total = rows.count()
        retired = rows.filter(active=False).count()
        entries.append(
            VocabularyListEntry(
                list=name,
                tier=entry.tier,
                kind=entry.kind_name,
                kinds=list(entry.kinds),
                count=total - retired,
                retired_count=retired,
                proposable=entry.proposable,
            )
        )
    return entries


def rows_of(
    list_name: str, tenant_id: uuid.UUID | None, order: list[str], *, include_retired: bool = False
) -> list[VocabularyRow]:
    entry = entry_for(list_name)
    queryset = _queryset(entry, tenant_id)
    if not include_retired:
        queryset = queryset.filter(active=True)
    rows = list(queryset)
    labels = Labels.for_rows(entry.label_model, rows)
    return [_row(entry, row, labels, order) for row in rows]


def _row(entry: VocabularyList, row: Any, labels: Labels, order: list[str]) -> VocabularyRow:
    texts = labels.texts(row.id)
    return VocabularyRow(
        key=row.key,
        kind=row.kind,
        label=label_of(texts, order, original=labels.original(row.id), key=row.key),
        labels=texts,
        usage_note=row.usage_note,
        sort_order=row.sort_order,
        active=row.active,
        is_system=row.is_system,
        is_default=row.is_default,
        usage_count=getattr(row, "usage_count", 0),
        version=getattr(row, "version", 1),
        extra=extra_of(row, entry.extra_fields),
        **confirmation_of(row),
    )


def row_by_key(list_name: str, key: str, tenant_id: uuid.UUID | None) -> Any:
    entry = entry_for(list_name)
    row = _queryset(entry, tenant_id).filter(key=key).order_by("sort_order", "key").first()
    if row is None:
        raise ValidationError(f"{key!r} is not a row of {list_name!r}.", code="not_found")
    return row


def row_for_write(list_name: str, keys: list[str], tenant_id: uuid.UUID) -> list[Any]:
    """The rows a write changes, locked before they are read, so two writers queue: the
    second reads the version and state the first committed, and `If-Match` or the state
    check refuses it rather than letting it overwrite. The usage count groups rows, which
    `FOR UPDATE` cannot, so the lock is taken on the bare rows first, in key order so two
    merges never deadlock."""
    entry = entry_for(list_name)
    lock = entry.model._default_manager.select_for_update().filter(tenant_id=tenant_id, key__in=keys)
    list(lock.order_by("key").values_list("pk", flat=True))
    return [row_by_key(list_name, key, tenant_id) for key in keys]


def row_detail(list_name: str, key: str, tenant_id: uuid.UUID | None, order: list[str]) -> VocabularyRowDetail:
    entry = entry_for(list_name)
    row = row_by_key(list_name, key, tenant_id)
    labels = Labels.for_rows(entry.label_model, [row])
    base = _row(entry, row, labels, order)
    return VocabularyRowDetail(
        **base.model_dump(),
        original_language=labels.original(row.id),
        machine_languages=labels.machine(row.id),
    )


# ---------------------------------------------------------------------------------------
# Validation shared by create and suggest
# ---------------------------------------------------------------------------------------
def known_languages() -> set[str]:
    from apps.library.models import Language

    return set(Language.objects.filter(active=True).values_list("key", flat=True))


def validated_labels(labels: dict[str, str]) -> dict[str, str]:
    """Labels are translation rows keyed by a language that exists (I18N-01). An unknown
    code is 422 `unknown_key` with the codes that would have worked, never a silent row
    nobody can read."""
    cleaned = {code: text.strip() for code, text in labels.items() if text and text.strip()}
    if not cleaned:
        raise ValidationError("Give the value a label in at least one language.", code="validation_error")
    known = known_languages()
    unknown = sorted(set(cleaned) - known)
    if unknown:
        raise ValidationError(
            f"{', '.join(unknown)} is not a content language. Valid languages: {', '.join(sorted(known))}.",
            code="unknown_key",
        )
    return cleaned


def validated_kind(entry: VocabularyList, kind: str | None) -> str | None:
    if not entry.kinds:
        return None
    if kind is None or kind == "":
        if entry.kind_required:
            raise ValidationError(
                f"Choose a {entry.kind_name}. Valid values: {', '.join(entry.kinds)}.", code="unknown_key"
            )
        return None
    if kind not in entry.kinds:
        raise ValidationError(
            f"{kind!r} is not a {entry.kind_name}. Valid values: {', '.join(entry.kinds)}.", code="unknown_key"
        )
    return kind


def extra_columns(entry: VocabularyList, extra: dict[str, Any] | None) -> dict[str, Any]:
    """The list's own columns from a write's `extra`, keyed by column name. Reads render
    them camelCased (`slaDays`), so writes accept that spelling as well as the column name
    (`sla_days`); a key that is not one of the list's columns is dropped, never stored.
    Each value is cleaned by its model field and a reference (a related row's key) becomes
    that row, so a wrong value is a 422 when the write or the proposal is made, never a
    500 when it is saved or approved."""
    from pydantic.alias_generators import to_camel

    names = {to_camel(name): name for name in entry.extra_fields} | {name: name for name in entry.extra_fields}
    columns: dict[str, Any] = {}
    for key, value in (extra or {}).items():
        name = names.get(key)
        if name is None:
            continue
        related = entry.references.get(name)
        if related is not None:
            columns[name] = None if value is None else _referenced(related, value)
            continue
        try:
            columns[name] = entry.model._meta.get_field(name).clean(value, None)
        except ValidationError as exc:
            raise ValidationError(f"{to_camel(name)}: {' '.join(exc.messages)}", code="validation_error") from exc
    return columns


def extra_payload(entry: VocabularyList, extra: dict[str, Any] | None) -> dict[str, Any]:
    """The list's own columns as a proposal stores and shows them: cleaned like the write
    that approval makes, camelCased like every other name the reviewer reads, a reference as
    the key of the row it names. apply.py maps them back to columns."""
    from pydantic.alias_generators import to_camel

    return {to_camel(name): getattr(value, "key", value) for name, value in extra_columns(entry, extra).items()}


def _referenced(list_name: str, key: Any) -> Any:
    rows = REGISTRY[list_name].model._default_manager.filter(active=True)
    row = rows.filter(key=key).order_by("sort_order", "key").first() if isinstance(key, str) else None
    if row is None:
        valid = ", ".join(rows.order_by("sort_order", "key").values_list("key", flat=True))
        raise ValidationError(f"{key!r} is not a {list_name}. Valid values: {valid}.", code="unknown_key")
    return row


def key_for(labels: dict[str, str], key: str | None) -> str:
    """The immutable key (playbook 4.3). Given explicitly, or slugified with underscores
    from the English label, then from whatever label there is."""
    if key:
        candidate = slugify(key).replace("-", "_")
    else:
        source = labels.get(ORIGINAL_LANGUAGE) or next(iter(labels.values()))
        candidate = slugify(source).replace("-", "_")
    if not candidate:
        raise ValidationError("That label makes no key; give the value a key.", code="validation_error")
    return candidate


def _existing_candidates(entry: VocabularyList, tenant_id: uuid.UUID | None, keys: list[str]) -> list[Candidate]:
    found = list(_queryset(entry, tenant_id).filter(key__in=keys))
    labels = Labels.for_rows(entry.label_model, found)
    return [
        Candidate(key=row.key, label=label_of(labels.texts(row.id), [ORIGINAL_LANGUAGE], original=None, key=row.key))
        for row in found
    ]


def check_duplicate(entry: VocabularyList, tenant_id: uuid.UUID | None, key: str) -> None:
    """Case-insensitive uniqueness (playbook 15). The 409 carries the row that already has
    the key so the screen can offer it instead of asking the person to search."""
    clash = _queryset(entry, tenant_id).filter(key__iexact=key).order_by("sort_order", "key").first()
    if clash is None:
        return
    candidates = _existing_candidates(entry, tenant_id, [clash.key])
    raise VocabularyProblem(
        f"{key!r} already exists on this list.",
        code="duplicate_key",
        extra={"candidates": [candidate.as_dict() for candidate in candidates]},
    )


def near_duplicates(
    entry: VocabularyList, tenant_id: uuid.UUID | None, labels: dict[str, str]
) -> list[Candidate]:
    """Active rows whose label is close enough to one of `labels` to be a typo, best match
    first. Trigram similarity (pg_trgm, installed by the first migration) recalls
    candidates; `difflib`'s ratio on the casefolded texts decides."""
    from difflib import SequenceMatcher

    from django.contrib.postgres.search import TrigramSimilarity

    rows = {row.id: row for row in _queryset(entry, tenant_id).filter(active=True)}
    if not rows:
        return []
    row_labels = Labels.for_rows(entry.label_model, list(rows.values()))
    best: dict[str, tuple[float, Candidate]] = {}
    for text in labels.values():
        wanted = text.casefold().strip()
        matches = (
            entry.label_model._default_manager.filter(vocabulary_id__in=list(rows))
            .annotate(score=TrigramSimilarity("text", text))
            .filter(score__gte=NEAR_DUPLICATE_RECALL)
            .order_by("-score", "language")
        )
        for match in matches:
            ratio = SequenceMatcher(None, wanted, match.text.casefold().strip()).ratio()
            if ratio < NEAR_DUPLICATE_RATIO:
                continue
            row = rows[match.vocabulary_id]
            if row.key in best and best[row.key][0] >= ratio:
                continue
            candidate = Candidate(
                key=row.key,
                label=label_of(row_labels.texts(row.id), [ORIGINAL_LANGUAGE], original=None, key=row.key),
            )
            best[row.key] = (ratio, candidate)
    ranked = sorted(best.values(), key=lambda pair: (-pair[0], pair[1].key))
    return [candidate for _ratio, candidate in ranked[:MAX_CANDIDATES]]


def check_near_duplicate(
    entry: VocabularyList, tenant_id: uuid.UUID | None, labels: dict[str, str], *, force: bool
) -> None:
    if force:
        return
    candidates = near_duplicates(entry, tenant_id, labels)
    if not candidates:
        return
    raise VocabularyProblem(
        f"Did you mean {candidates[0].label}?",
        code="near_duplicate",
        extra={"candidates": [candidate.as_dict() for candidate in candidates]},
    )


# ---------------------------------------------------------------------------------------
# Writing (tenant lists only; library lists go through apps/proposals)
# ---------------------------------------------------------------------------------------
def _next_sort_order(entry: VocabularyList, tenant_id: uuid.UUID | None) -> int:
    highest = _queryset(entry, tenant_id).aggregate(highest=Max("sort_order"))["highest"]
    return 0 if highest is None else highest + 1


def _write_labels(entry: VocabularyList, row: Any, labels: dict[str, str], tenant: Tenant | None) -> None:
    """Write translation rows (D-12). The first labels a row gets name its original: English
    when English is among them, otherwise the language the person wrote in. A person's edit
    is never machine output, so `is_machine` is cleared on the languages they touched."""
    existing = {label.language: label for label in entry.label_model._default_manager.filter(vocabulary=row)}
    original = None
    if not any(label.is_original for label in existing.values()):
        original = ORIGINAL_LANGUAGE if ORIGINAL_LANGUAGE in labels else next(iter(labels))
    for language, text in labels.items():
        label = existing.get(language)
        if label is not None:
            label.text = text
            label.is_machine = False
            label.save(update_fields=["text", "is_machine"])
            continue
        fields: dict[str, Any] = {
            "vocabulary": row,
            "language": language,
            "text": text,
            "is_original": language == original,
        }
        if tenant is not None:
            fields["tenant"] = tenant
        entry.label_model._default_manager.create(**fields)


def create_row(
    *,
    list_name: str,
    tenant: Tenant,
    actor: Actor,
    labels: dict[str, str],
    key: str | None = None,
    usage_note: str = "",
    kind: str | None = None,
    sort_order: int | None = None,
    extra: dict[str, Any] | None = None,
    force: bool = False,
    order: list[str] | None = None,
) -> VocabularyRow:
    entry = entry_for(list_name)
    cleaned = validated_labels(labels)
    row_key = key_for(cleaned, key)
    check_duplicate(entry, tenant.id, row_key)
    check_near_duplicate(entry, tenant.id, cleaned, force=force)
    fields: dict[str, Any] = {
        "tenant": tenant,
        "key": row_key,
        "kind": validated_kind(entry, kind),
        "usage_note": usage_note.strip(),
        "sort_order": _next_sort_order(entry, tenant.id) if sort_order is None else sort_order,
        "active": True,
        "is_system": False,
        "is_default": False,
    }
    fields.update(extra_columns(entry, extra))
    row = entry.model._default_manager.create(**fields)
    _write_labels(entry, row, cleaned, tenant)
    record(
        action="vocabulary.created",
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=row.id,
        subject_title=f"{list_name}:{row_key}",
        summary=f"Added {row_key} to {list_name}.",
        tenant_id=tenant.id,
        after={"list": list_name, "key": row_key, "labels": cleaned, "kind": fields["kind"]},
    )
    _resolve_suggestions(list_name, tenant, row_key)
    labels_read = Labels.for_rows(entry.label_model, [row])
    fresh = _queryset(entry, tenant.id).filter(pk=row.pk).first()  # ordering: pk lookup, at most one row
    return _row(entry, fresh or row, labels_read, order or [ORIGINAL_LANGUAGE])


def patch_row(
    *,
    list_name: str,
    tenant: Tenant,
    actor: Actor,
    key: str,
    labels: dict[str, str] | None,
    usage_note: str | None,
    sort_order: int | None,
    extra: dict[str, Any] | None,
    expected_version: int | None,
    order: list[str],
) -> VocabularyRow:
    """Relabel, re-note, reorder. The key never changes (playbook 4.3); `If-Match` carries
    the version and a stale write answers 409 `stale_write`."""
    entry = entry_for(list_name)
    [row] = row_for_write(list_name, [key], tenant.id)
    if expected_version is not None and expected_version != getattr(row, "version", 1):
        raise ValidationError("Someone changed this first. Reload and try again.", code="stale_write")
    before = {"labels": Labels.for_rows(entry.label_model, [row]).texts(row.id), "usageNote": row.usage_note}
    cleaned = validated_labels(labels) if labels else {}
    if cleaned:
        _write_labels(entry, row, cleaned, tenant)
    if usage_note is not None:
        row.usage_note = usage_note.strip()
    if sort_order is not None:
        row.sort_order = sort_order
    for name, value in extra_columns(entry, extra).items():
        setattr(row, name, value)
    row.version = getattr(row, "version", 1) + 1
    row.save()
    record(
        action="vocabulary.updated",
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=row.id,
        subject_title=f"{list_name}:{key}",
        summary=f"Changed {key} on {list_name}.",
        tenant_id=tenant.id,
        before=before,
        after={"labels": cleaned or before["labels"], "usageNote": row.usage_note},
    )
    fresh = _queryset(entry, tenant.id).filter(pk=row.pk).first()  # ordering: pk lookup, at most one row
    return _row(entry, fresh or row, Labels.for_rows(entry.label_model, [row]), order)


def reorder(*, list_name: str, tenant: Tenant, actor: Actor, keys: list[str]) -> int:
    """Drag to reorder (VOC-02): the keys in the order the screen shows them. Keys the
    caller left out keep their place after the ones it named."""
    entry = entry_for(list_name)
    rows = {row.key: row for row in _queryset(entry, tenant.id)}
    unknown = [key for key in keys if key not in rows]
    if unknown:
        raise ValidationError(
            f"{', '.join(unknown)} is not on {list_name!r}.", code="unknown_key"
        )
    before = {key: row.sort_order for key, row in rows.items()}
    named = list(dict.fromkeys(keys))
    rest = [key for key in rows if key not in named]  # already in the list's current order
    for position, key in enumerate(named + rest):
        row = rows[key]
        if row.sort_order != position:
            row.sort_order = position
            row.save(update_fields=["sort_order"])
    record(
        action="vocabulary.reordered",
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=None,
        subject_title=list_name,
        summary=f"Reordered {list_name}.",
        tenant_id=tenant.id,
        before=before,
        after={key: position for position, key in enumerate(named + rest)},
    )
    return len(named)


def usage_count(list_name: str, tenant_id: uuid.UUID | None, key: str) -> int:
    entry = entry_for(list_name)
    row = _queryset(entry, tenant_id).filter(key=key).order_by("sort_order", "key").first()
    return 0 if row is None else int(getattr(row, "usage_count", 0))


def _refuse_system_row(row: Any, verb: str) -> None:
    if row.is_system:
        raise ValidationError(
            f"{row.key} is a system value: it can be relabelled but not {verb}.", code="system_row"
        )


def retire(
    *, list_name: str, tenant: Tenant, actor: Actor, key: str, confirm: bool
) -> VocabularyRetired:
    """Retire, never delete (playbook 15, AC-VOC2). The records that carry the value keep
    it and still render its label; the picker stops offering it."""
    [row] = row_for_write(list_name, [key], tenant.id)
    _refuse_system_row(row, "retired")
    count = int(getattr(row, "usage_count", 0))
    if count and not confirm:
        raise VocabularyProblem(
            f"{key} is used by {count} records. Retiring keeps them readable and removes it from pickers.",
            code="in_use",
            extra={"usageCount": count},
        )
    if not row.active:
        raise ValidationError(f"{key} is already retired.", code="invalid_transition")
    row.active = False
    row.version = getattr(row, "version", 1) + 1
    row.save(update_fields=["active", "version"])
    record(
        action="vocabulary.retired",
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=row.id,
        subject_title=f"{list_name}:{key}",
        summary=f"Retired {key} from {list_name}.",
        tenant_id=tenant.id,
        before={"active": True},
        after={"active": False, "usageCount": count},
    )
    return VocabularyRetired(key=key, usage_count=count, retired=True)


def restore(*, list_name: str, tenant: Tenant, actor: Actor, key: str) -> VocabularyRestored:
    """The inverse of retire (playbook 15: retire, never delete, so there is always
    something to bring back). Audited like every other write."""
    [row] = row_for_write(list_name, [key], tenant.id)
    if row.active:
        raise ValidationError(f"{key} is not retired.", code="invalid_transition")
    row.active = True
    row.version = getattr(row, "version", 1) + 1
    row.save(update_fields=["active", "version"])
    record(
        action="vocabulary.restored",
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=row.id,
        subject_title=f"{list_name}:{key}",
        summary=f"Restored {key} to {list_name}.",
        tenant_id=tenant.id,
        before={"active": False},
        after={"active": True},
    )
    return VocabularyRestored(key=key, usage_count=int(getattr(row, "usage_count", 0)), restored=True)


def merge(
    *, list_name: str, tenant: Tenant, actor: Actor, key: str, into: str, dry_run: bool
) -> VocabularyMerged:
    """Merge re-points duplicates in one audited transaction (VOC-02), previewed first.
    `repointed` is what will actually move: a record that already carries the target keeps
    one link, so the count is never inflated by duplicates the unique constraint drops."""
    entry = entry_for(list_name)
    source, target = row_for_write(list_name, [key, into], tenant.id)
    if source.pk == target.pk:
        raise ValidationError("Choose a different value to merge into.", code="validation_error")
    _refuse_system_row(source, "merged away")
    count = int(getattr(source, "usage_count", 0))
    if dry_run:
        # A preview changes nothing and is not a write, so it leaves no audit row: the
        # audit log answers "what changed", and nothing did (AUD-01).
        return VocabularyMerged(
            **{"from": key}, into=into, usage_count=count, repointed=entry.repoint(source, target, dry_run=True), dry_run=True
        )
    repointed = entry.repoint(source, target, dry_run=False)
    source.active = False
    source.version = getattr(source, "version", 1) + 1
    source.save(update_fields=["active", "version"])
    record(
        action="vocabulary.merged",
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=source.id,
        subject_title=f"{list_name}:{key}",
        summary=f"Merged {key} into {into} on {list_name}.",
        tenant_id=tenant.id,
        before={"from": key, "usageCount": count, "active": True},
        after={"into": into, "repointed": repointed, "active": False},
    )
    return VocabularyMerged(**{"from": key}, into=into, usage_count=count, repointed=repointed, dry_run=False)


# ---------------------------------------------------------------------------------------
# Suggestions (VOC-03): "Create where you use it" for people without vocab.manage
# ---------------------------------------------------------------------------------------
def suggest(
    *, list_name: str, tenant: Tenant, actor: Actor, user: Any, labels: dict[str, str], key: str | None, usage_note: str
) -> VocabularySuggestionRow:
    from apps.taxonomy.models import SuggestionStatus, VocabularySuggestion

    entry = entry_for(list_name)
    cleaned = validated_labels(labels)
    row_key = key_for(cleaned, key)
    check_duplicate(entry, tenant.id, row_key)
    check_near_duplicate(entry, tenant.id, cleaned, force=False)
    suggestion = VocabularySuggestion.objects.create(
        tenant=tenant,
        list_name=list_name,
        key=row_key,
        labels=cleaned,
        usage_note=usage_note.strip(),
        suggested_by=user,
    )
    record(
        action="vocabulary.suggested",
        actor=actor,
        subject_type="vocabulary_suggestion",
        subject_id=suggestion.id,
        subject_title=f"{list_name}:{row_key}",
        summary=f"Suggested {row_key} for {list_name}.",
        tenant_id=tenant.id,
        after={"list": list_name, "key": row_key, "labels": cleaned},
    )
    return suggestion_row(suggestion, SuggestionStatus.PENDING.value)


def suggestion_row(suggestion: Any, status: str | None = None) -> VocabularySuggestionRow:
    return VocabularySuggestionRow(
        id=suggestion.id,
        list=suggestion.list_name,
        key=suggestion.key,
        labels=suggestion.labels,
        usage_note=suggestion.usage_note,
        suggested_by=PersonRef(id=suggestion.suggested_by.id, name=suggestion.suggested_by.name),
        status=status or suggestion.status,
        created_at=suggestion.created_at,
    )


def suggestions_of(
    list_name: str, tenant_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[VocabularySuggestionRow], int]:
    """One page of the list's waiting suggestions (VOC-03, NFR-02), oldest first because
    the inbox is worked in the order it filled, and how many wait in all. The id settles two
    sent in the same instant, so two reads always agree on the order."""
    from apps.taxonomy.models import SuggestionStatus, VocabularySuggestion

    entry_for(list_name)
    found = VocabularySuggestion.objects.filter(tenant_id=tenant_id, list_name=list_name, status=SuggestionStatus.PENDING.value)
    page = found.select_related("suggested_by").order_by("created_at", "id")[offset : offset + limit]
    return [suggestion_row(suggestion) for suggestion in page], found.count()


def _resolve_suggestions(list_name: str, tenant: Tenant, key: str) -> int:
    """Creating the row answers the suggestion; the inbox empties without a second click."""
    from apps.taxonomy.models import SuggestionStatus, VocabularySuggestion
    from django.utils import timezone

    pending = VocabularySuggestion.objects.filter(
        tenant=tenant, list_name=list_name, key=key, status=SuggestionStatus.PENDING.value
    ).order_by("created_at", "id")
    resolved = 0
    for suggestion in pending:
        suggestion.status = SuggestionStatus.ACCEPTED.value
        suggestion.resolved_at = timezone.now()
        suggestion.save(update_fields=["status", "resolved_at"])
        resolved += 1
    return resolved


def decline_suggestion(
    *, list_name: str, tenant: Tenant, actor: Actor, suggestion_id: uuid.UUID
) -> VocabularySuggestionRow:
    from apps.taxonomy.models import SuggestionStatus, VocabularySuggestion
    from django.utils import timezone

    entry_for(list_name)
    suggestion = (
        VocabularySuggestion.objects.filter(tenant=tenant, list_name=list_name, pk=suggestion_id)
        .select_related("suggested_by")
        .first()  # ordering: pk lookup, at most one row
    )
    if suggestion is None:
        raise ValidationError("That suggestion is not here.", code="not_found")
    if suggestion.status != SuggestionStatus.PENDING.value:
        raise ValidationError("That suggestion has already been answered.", code="invalid_transition")
    suggestion.status = SuggestionStatus.DECLINED.value
    suggestion.resolved_at = timezone.now()
    suggestion.save(update_fields=["status", "resolved_at"])
    record(
        action="vocabulary.suggestion_declined",
        actor=actor,
        subject_type="vocabulary_suggestion",
        subject_id=suggestion.id,
        subject_title=f"{list_name}:{suggestion.key}",
        summary=f"Declined the suggestion {suggestion.key} for {list_name}.",
        tenant_id=tenant.id,
        before={"status": SuggestionStatus.PENDING.value},
        after={"status": SuggestionStatus.DECLINED.value},
    )
    return suggestion_row(suggestion)
