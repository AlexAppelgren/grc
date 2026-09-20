"""Request and response schemas of the watch app: camelCase through CamelSchema, app-prefixed
class names where a shape is specific to this app (playbook 4.1).

Plain Pydantic, never `ModelSchema`: this contract references no Django model, so it lands
beside the watch models rather than behind them.

A write takes a vocabulary **key** (`changeType`, `flags`, `kind`, `suggestedUrgency`) and
a read answers `{key, kind, label}`: the client never string-matches a phrase, and a tone
is nobody's to send (playbook 15, NFR-03). `Literal` carries the kinds that stay in code —
`change_status`, `check_status`, `origin_type`, a source's cadence — so no enum class is
added for a shape the caller only names.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Literal

from ninja import Field
from pydantic import HttpUrl

from apps.library.schemas import LibraryRef
from apps.shared.schemas import CamelSchema, WriteBody

__all__ = ["CamelSchema"]

CheckFrequency = Literal["daily", "weekly", "monthly"]
CheckStatus = Literal["ok", "failed"]
ChangeStatus = Literal["active", "superseded", "withdrawn"]
DatePrecision = Literal["day", "month", "quarter", "year"]
Origin = Literal["agent", "user"]

# A label a person reads, a summary a person reads, and the most obligations one change
# may be linked to in a single call. Lengths, not thresholds: they bound a column or a
# request body, not a decision.
LABEL_MAX = 300
TEXT_MAX = 4000
KEY_MAX = 80
LINKS_MAX = 200


# ---------------------------------------------------------------------------------------
# Sources and the coverage log (WAT-01)
# ---------------------------------------------------------------------------------------
class WatchSourceOut(CamelSchema):
    id: uuid.UUID
    name: str
    url: str | None
    kind: LibraryRef
    authority_id: uuid.UUID | None
    check_frequency: CheckFrequency
    active: bool


class WatchSourceInput(WriteBody):
    name: str = Field(min_length=1, max_length=LABEL_MAX)
    url: HttpUrl | None = None
    kind: str = Field(min_length=1, max_length=KEY_MAX)
    authority_id: uuid.UUID | None = None
    check_frequency: CheckFrequency = "daily"


class WatchSourcePatch(WriteBody):
    url: HttpUrl | None = None
    check_frequency: CheckFrequency | None = None
    active: bool | None = None


class WatchSourceCoverage(CamelSchema):
    """One row of the coverage log per source: when it was last checked, with what result,
    and whether it is overdue against its cadence and `SOURCE_STALE_AFTER_CHECKS`."""

    source: WatchSourceOut
    last_checked_at: datetime.datetime | None
    last_status: Literal["ok", "failed", "never"]
    last_error: str | None
    overdue: bool


class WatchSourceCheckInput(WriteBody):
    """`POST /agent-runs/{runId}/source-checks` (WAT-01): a failed check carries an error
    and no items, which `watch/sources.py:record_check` enforces."""

    source_name: str = Field(min_length=1, max_length=LABEL_MAX)
    status: CheckStatus
    items_found: int | None = Field(default=None, ge=0)
    error: str | None = Field(default=None, max_length=TEXT_MAX)
    checked_at: datetime.datetime | None = None


# ---------------------------------------------------------------------------------------
# A change's timeline, documents and obligation links (WAT-02, WAT-04, AGT-07)
# ---------------------------------------------------------------------------------------
class WatchChangeEventInput(WriteBody):
    label: str = Field(min_length=1, max_length=LABEL_MAX)
    event_date: datetime.date | None = None
    date_precision: DatePrecision | None = None
    occurred: bool = False
    sort_order: int = 0
    source_url: HttpUrl | None = None


class WatchChangeEvent(CamelSchema):
    id: uuid.UUID
    label: str
    event_date: datetime.date | None
    date_precision: DatePrecision | None
    occurred: bool
    sort_order: int
    source_url: str | None


class WatchChangeDocumentInput(WriteBody):
    """A fetched page. `riskFlags` is what `agents/screen.py` found in it; the content
    itself is untrusted and is never executed or rendered as HTML (playbook 11.2)."""

    url: HttpUrl
    title: str | None = Field(default=None, max_length=LABEL_MAX)
    publisher: str | None = Field(default=None, max_length=LABEL_MAX)
    fetched_at: datetime.datetime | None = None
    content_hash: str | None = Field(default=None, max_length=128)
    is_primary: bool = False
    is_duplicate: bool = False
    risk_flags: list[str] = Field(default_factory=list, max_length=50)


class WatchChangeDocument(CamelSchema):
    id: uuid.UUID
    url: str
    title: str | None
    publisher: str | None
    fetched_at: datetime.datetime | None
    is_primary: bool
    is_duplicate: bool
    risk_flags: list[str]


class WatchObligationLinkInput(WriteBody):
    obligation_id: uuid.UUID
    confidence: float | None = Field(default=None, ge=0, le=1)


class WatchObligationLink(CamelSchema):
    """A link the agent suggested or a person set. `confirmed` is the library editor's
    decision; a tenant's own decision lives on its case, never here (WAT-04, ruling C)."""

    obligation_id: uuid.UUID
    title: str
    instrument_short_name: str
    ref_label: str
    origin: Origin
    confidence: float | None
    confirmed: bool


# ---------------------------------------------------------------------------------------
# The change itself (WAT-02, WAT-03)
# ---------------------------------------------------------------------------------------
class WatchChangeInput(WriteBody):
    """`POST /changes` (AC-WAT1): `stableKey` makes the call idempotent, so posting a known
    key merges the new pages as duplicates and returns the change that exists."""

    stable_key: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=LABEL_MAX)
    change_type: str = Field(min_length=1, max_length=KEY_MAX)
    authority_label: str = Field(min_length=1, max_length=LABEL_MAX)
    authority_code: str | None = Field(default=None, max_length=KEY_MAX)
    published_on: datetime.date | None = None
    published_precision: DatePrecision | None = None
    summary: str = Field(min_length=1, max_length=TEXT_MAX)
    so_what_draft: str | None = Field(default=None, max_length=TEXT_MAX)
    suggested_urgency: str | None = Field(default=None, max_length=KEY_MAX)
    key_date: datetime.date | None = None
    key_date_precision: DatePrecision | None = None
    key_date_label: str | None = Field(default=None, max_length=LABEL_MAX)
    recurrence_rule: str | None = Field(default=None, max_length=LABEL_MAX)
    flags: list[str] = Field(default_factory=list, max_length=50)
    source_label: str = Field(min_length=1, max_length=LABEL_MAX)
    source_url: HttpUrl
    term_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    events: list[WatchChangeEventInput] = Field(default_factory=list, max_length=50)
    documents: list[WatchChangeDocumentInput] = Field(default_factory=list, max_length=50)
    obligation_links: list[WatchObligationLinkInput] = Field(default_factory=list, max_length=LINKS_MAX)
    agent_run_id: uuid.UUID | None = None
    model: str | None = Field(default=None, max_length=120)


class WatchChangePatch(WriteBody):
    """`PATCH /changes/{changeId}` (WAT-03): the library facts of a change. What a key may
    move, and that a suggestion stays a suggestion until a library editor confirms it, is
    `watch/curation.py:update_change_facts`."""

    title: str | None = Field(default=None, min_length=1, max_length=LABEL_MAX)
    change_type: str | None = Field(default=None, min_length=1, max_length=KEY_MAX)
    summary: str | None = Field(default=None, min_length=1, max_length=TEXT_MAX)
    key_date: datetime.date | None = None
    key_date_precision: DatePrecision | None = None
    key_date_label: str | None = Field(default=None, max_length=LABEL_MAX)
    flags: list[str] | None = Field(default=None, max_length=50)
    status: ChangeStatus | None = None
    superseded_by: uuid.UUID | None = None
    term_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)


class WatchChange(CamelSchema):
    """A library record: sourced facts, shared by every tenant. No tenant judgement, no
    case and no "So what?" confirmation is here; those sit on the tenant's own case."""

    id: uuid.UUID
    stable_key: str
    title: str
    change_type: LibraryRef
    authority_label: str
    authority_id: uuid.UUID | None
    published_on: datetime.date | None
    published_precision: DatePrecision | None
    summary: str
    so_what_draft: str | None
    suggested_urgency: LibraryRef | None
    key_date: datetime.date | None
    key_date_precision: DatePrecision | None
    key_date_label: str | None
    recurrence_rule: str | None
    flags: list[LibraryRef]
    source_label: str
    source_url: str
    status: ChangeStatus
    terms: list[LibraryRef]
    events: list[WatchChangeEvent]
    documents: list[WatchChangeDocument]
    duplicate_count: int
    obligations: list[WatchObligationLink]
    origin: Origin
    model: str | None
    agent_run_id: uuid.UUID | None
    first_seen_at: datetime.datetime
