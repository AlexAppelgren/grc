"""What the search index reads out of the library (SRC-01, SRC-02, D-10).

Every library row a chunk is built from is read here and nowhere else, and nothing here
writes: the library fence (`apps/shared/tests_library_fence.py`) keeps watching this
module without ever having to allow it, and `apps/search/tests_indexing.py` walks this
file's syntax tree and fails on any write call. The rebuild in `apps/search/indexing.py`
therefore never names a library model, and the index's one door never touches the
library's.

**A document, not a display record.** A chunk's `title` is the citation line a lawyer
would write — the instrument's official reference, the record's own reference label, then
the record's title — because only `title` and `body` reach the generated `tsvector`, and
AC-SRC1 asks that "FFFS 2017:2" be won by the keyword leg. `hierarchy_path` is the
breadcrumb a screen draws; the screen takes the words it shows from the record the hit
points at, never from the chunk.

**Validity is copied, so "as of" needs no join.** `valid_to` is the last day the version
is in force: the day before the next one takes effect, by the one rule
`apps/library/reading.py::version_rows()` uses for the obligation card, so the card and
the index can never disagree. There is no end date when there is no next version, when
the next one has no date of its own, or when it took effect on or before this one — and
in that last case the version was corrected on the day it began (`logic.in_force`: the
later number wins), so it is not indexed at all rather than indexed for ever.

**Shared records only, in R1** (D-10, owner items 4 and 10). A record a bank owns, or one
whose instrument a bank owns, yields no chunk. Its version ids are still returned, so a
rebuild removes anything an earlier run left behind.

**A registered change is the third source** (WAT-01, WAT-02, AGT-02). It is one text — its
title and its summary, in whatever language the source was written in, which the change
does not record — so it is indexed once under every content language's configuration,
and whichever reads the reader's query best is the hit (`hybrid._best_per_record`). It
carries its authority, its authority's jurisdiction and its scope terms, and it is
searchable from the day it was published. Only an active change is: a withdrawn or
superseded one keeps its id in the rebuild's scope and loses its chunks.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from typing import Any

from apps.library.models import (
    Obligation,
    ObligationSummary,
    ObligationTerm,
    ObligationTitle,
    ObligationVersion,
    Provision,
    ProvisionText,
    ProvisionVersion,
)
from apps.search.models import TEXT_SEARCH_CONFIGS, SearchSource
from apps.search.schemas import SearchChunkMetadata
from apps.watch.models import ChangeStatus, ChangeTerm, RegulatoryChange

# The breadcrumb separator the prototype's data uses ("LVM > 9 kap.").
PATH_SEPARATOR = " > "


@dataclass(frozen=True)
class ChunkSource:
    """One chunk, as the library says it should read. `metadata` is already the JSON the
    column stores: keys and ids by field name, never a label (`SearchChunkMetadata`)."""

    source_id: uuid.UUID
    language: str
    title: str
    body: str
    hierarchy_path: str
    valid_from: datetime.date | None
    valid_to: datetime.date | None
    metadata: dict[str, Any]


@dataclass(frozen=True)
class RecordChunks:
    """What one library record contributes to the index, and what the rebuild owns.

    `source_ids` is every version of the record, indexed or not: it is the scope the
    rebuild deletes outside of, so a version that stopped being indexable takes its chunk
    with it.
    """

    source_type: str
    source_ids: list[uuid.UUID]
    chunks: list[ChunkSource]


def obligation_chunks(obligation_id: uuid.UUID) -> RecordChunks:
    """The chunks obligation `obligation_id` should have: one per version per summary
    language. An unknown obligation contributes nothing at all."""
    obligation = (
        Obligation.objects.select_related("instrument", "instrument__jurisdiction", "instrument__regime", "duty_type")
        .filter(id=obligation_id)
        .first()  # ordering: one row, looked up by its id
    )
    if obligation is None:
        return RecordChunks(SearchSource.OBLIGATION_VERSION.value, [], [])
    versions = list(ObligationVersion.objects.filter(obligation=obligation))
    source_ids = [version.id for version in versions]
    if _owned(obligation.owner_tenant_id, obligation.instrument.owner_tenant_id):
        return RecordChunks(SearchSource.OBLIGATION_VERSION.value, source_ids, [])

    titles = {row.language_id: row.text for row in ObligationTitle.objects.filter(obligation=obligation)}
    original_title = next(
        (row.text for row in ObligationTitle.objects.filter(obligation=obligation) if row.is_original), ""
    )
    metadata = _metadata(
        obligation.instrument,
        obligation_id=obligation.id,
        duty_type=obligation.duty_type.key,
        term_ids=list(ObligationTerm.objects.filter(obligation=obligation).values_list("term_id", flat=True)),
    )
    path = _path(obligation.instrument.official_ref, obligation.ref_label)
    summaries = ObligationSummary.objects.filter(version__in=versions)
    by_version: dict[uuid.UUID, list[ObligationSummary]] = {version.id: [] for version in versions}
    for summary in summaries:
        by_version[summary.version_id].append(summary)

    chunks: list[ChunkSource] = []
    for index, version in enumerate(versions):
        following = versions[index + 1] if index + 1 < len(versions) else None
        if _superseded_at_birth(version.effective_from, following):
            continue
        valid_to = _in_force_until(version.effective_from, following.effective_from if following else None)
        for summary in by_version[version.id]:
            language = summary.language_id
            chunks.append(
                ChunkSource(
                    source_id=version.id,
                    language=language,
                    title=_title(obligation.instrument.official_ref, obligation.ref_label, titles.get(language) or original_title),
                    body=summary.text,
                    hierarchy_path=path,
                    valid_from=version.effective_from,
                    valid_to=valid_to,
                    metadata=metadata,
                )
            )
    return RecordChunks(SearchSource.OBLIGATION_VERSION.value, source_ids, chunks)


def provision_chunks(provision_id: uuid.UUID) -> RecordChunks:
    """The chunks provision `provision_id` should have: one per version per text language.

    A provision belongs to an instrument and to no obligation, so its chunk carries the
    instrument's regime, binding and jurisdiction and no duty type and no scope terms —
    those are the obligation's. Its end date is the one stored on the version when there
    is one, and otherwise the same derivation the obligation versions use.
    """
    provision = (
        Provision.objects.select_related("instrument", "instrument__jurisdiction", "instrument__regime")
        .filter(id=provision_id)
        .first()  # ordering: one row, looked up by its id
    )
    if provision is None:
        return RecordChunks(SearchSource.PROVISION_VERSION.value, [], [])
    versions = list(ProvisionVersion.objects.filter(provision=provision))
    source_ids = [version.id for version in versions]
    if _owned(provision.instrument.owner_tenant_id):
        return RecordChunks(SearchSource.PROVISION_VERSION.value, source_ids, [])

    metadata = _metadata(provision.instrument, obligation_id=None, duty_type=None, term_ids=[])
    path = provision.path or _path(provision.instrument.official_ref, provision.ref_label)
    texts = ProvisionText.objects.filter(version__in=versions)
    by_version: dict[uuid.UUID, list[ProvisionText]] = {version.id: [] for version in versions}
    for text in texts:
        by_version[text.version_id].append(text)

    chunks: list[ChunkSource] = []
    for index, version in enumerate(versions):
        following = versions[index + 1] if index + 1 < len(versions) else None
        if _superseded_at_birth(version.effective_from, following):
            continue
        valid_to = version.effective_to or _in_force_until(
            version.effective_from, following.effective_from if following else None
        )
        for text in by_version[version.id]:
            chunks.append(
                ChunkSource(
                    source_id=version.id,
                    language=text.language_id,
                    title=_title(provision.instrument.official_ref, provision.ref_label, provision.heading),
                    body=text.text,
                    hierarchy_path=path,
                    valid_from=version.effective_from,
                    valid_to=valid_to,
                    metadata=metadata,
                )
            )
    return RecordChunks(SearchSource.PROVISION_VERSION.value, source_ids, chunks)


def change_chunks(change_id: uuid.UUID) -> RecordChunks:
    """The chunks registered change `change_id` should have: one per content language while
    it is active, none once it is withdrawn or superseded. An unknown change contributes
    nothing at all.

    The scope terms are the change's own, a flag excluded (a flag says what the reform is
    about, not who it reaches, WAT-03), and the reader's regulatory scope is applied to
    them by `hybrid._scope` through the watch feed's own rule. A change belongs to
    no bank: it is registered by the platform's runs and its events carry no tenant, which
    `tasks.index_change` checks before it calls this.
    """
    change = (
        RegulatoryChange.objects.select_related("authority", "authority__jurisdiction")
        .filter(id=change_id)
        .first()  # ordering: one row, looked up by its id
    )
    if change is None:
        return RecordChunks(SearchSource.CHANGE.value, [], [])
    if change.status != ChangeStatus.ACTIVE.value:
        return RecordChunks(SearchSource.CHANGE.value, [change.id], [])

    authority = change.authority
    metadata = SearchChunkMetadata(
        authority=authority.key if authority else None,
        jurisdiction=authority.jurisdiction.key if authority else None,
        term_ids=list(
            ChangeTerm.objects.filter(change=change, term__isnull=False).order_by("term_id").values_list("term_id", flat=True)
        ),
    ).model_dump(mode="json", by_alias=False)
    chunks = [
        ChunkSource(
            source_id=change.id,
            language=language,
            title=change.title,
            body=change.summary,
            hierarchy_path=change.authority_label,
            valid_from=change.published_on,
            valid_to=None,
            metadata=metadata,
        )
        for language in TEXT_SEARCH_CONFIGS
    ]
    return RecordChunks(SearchSource.CHANGE.value, [change.id], chunks)


def obligation_ids() -> list[uuid.UUID]:
    """Every obligation of the library, for a full rebuild. The reads above decide which
    of them are indexable, so this asks no ownership question of its own."""
    return list(Obligation.objects.values_list("id", flat=True))


def provision_ids() -> list[uuid.UUID]:
    """Every provision of the library, for a full rebuild."""
    return list(Provision.objects.values_list("id", flat=True))


def change_ids() -> list[uuid.UUID]:
    """Every registered change, for a full rebuild. `change_chunks` decides which are
    indexable, so an inactive change's chunks are removed by the same pass."""
    return list(RegulatoryChange.objects.values_list("id", flat=True))


def _owned(*owners: uuid.UUID | None) -> bool:
    """True when a bank owns the record or the instrument it hangs under. Nothing a bank
    owns, and no child of one, is indexed in R1 (D-10, owner item 10)."""
    return any(owner is not None for owner in owners)


def _title(official_ref: str, ref_label: str, text: str) -> str:
    """The citation line: "FFFS 2017:2 9 kap. 6 § — Lämna information om kostnader"."""
    citation = " ".join(part for part in (official_ref, ref_label) if part)
    return f"{citation} — {text}" if text else citation


def _path(official_ref: str, ref_label: str) -> str:
    return PATH_SEPARATOR.join(part for part in (official_ref, ref_label) if part)


def _metadata(
    instrument: Any, *, obligation_id: uuid.UUID | None, duty_type: str | None, term_ids: list[uuid.UUID]
) -> dict[str, Any]:
    """The facts a filter compares, as the column stores them: by field name, and every
    one of them a key or an id, so relabelling a vocabulary row rewrites no chunk."""
    return SearchChunkMetadata(
        instrument_id=instrument.id,
        obligation_id=obligation_id,
        regime=instrument.regime.key,
        binding=instrument.binding,
        term_ids=term_ids,
        jurisdiction=instrument.jurisdiction.key,
        duty_type=duty_type,
    ).model_dump(mode="json", by_alias=False)


def _superseded_at_birth(start: datetime.date | None, following: Any) -> bool:
    """Whether the version that follows took effect on or before this one began, which
    makes this one a draft the correction replaced before anyone could read it."""
    if following is None:
        return False
    next_start = following.effective_from
    if next_start is None:
        return True  # the next version runs since always, so this one never did
    return start is not None and next_start <= start


def _in_force_until(start: datetime.date | None, next_start: datetime.date | None) -> datetime.date | None:
    """The last day this version is in force (`reading.version_rows()`, the same rule the
    obligation card draws): the day before the next one takes effect, or no end at all."""
    if next_start is None or (start is not None and next_start <= start):
        return None
    return next_start - datetime.timedelta(days=1)
