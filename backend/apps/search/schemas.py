"""Request and response schemas of the search app: camelCase through CamelSchema,
app-prefixed class names where a shape is specific to this app (playbook 4.1).

The shapes are the designed contract (`docs/inputs/openapi.yaml`: SearchRequest,
SearchHit, SearchResponse, SimilarRequest, AskRequest, Citation, AnswerStatement,
Answer, AnswerFeedback), with the departures INPUT_DELTAS records for chunk 7: a
language is a key from the language rows rather than a two-value enum (§3), a hit's
urgency is taxonomy's `TermRef` of key, kind and label rather than a phrase the client
must string-match (§1), and Ask answers a stream rather than one body, so the events
below are part of the contract too.

Three enums here are kinds the rules branch on, not rows an admin manages: what a hit
points at, how it was matched, and what a reader said about an answer. All three are in
apps/shared/kinds.py under their own delta names; `search_source` stays the chunk
table's own column, which the search index owns.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from django.conf import settings
from pydantic import Field

from apps.shared.schemas import CamelSchema, WriteBody
from apps.taxonomy.schemas import TermRef

__all__ = ["CamelSchema"]


class SearchHitType(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): what a hit points at. The reader opens an
    obligation, a provision or a change, and the screen branches on it."""

    OBLIGATION = "obligation"
    PROVISION = "provision"
    CHANGE = "change"


class SearchMatchKind(enum.StrEnum):
    """Tier-one kind: how the hit was won (SRC-02, AC-SRC1). Every hit says so, and the
    pill's tone follows the kind, never a person's choice (NFR-03)."""

    KEYWORD = "keyword"
    CONCEPT = "concept"
    BOTH = "both"


# ---------------------------------------------------------------------------------------
# POST /search, POST /search/similar
# ---------------------------------------------------------------------------------------
class SearchFilters(WriteBody):
    """The filters of SRC-02 and SRC-S3, taken from the vocabularies and the tenant's own
    view. Every one of them is a key, never a label, so renaming a jurisdiction or a duty
    type changes nothing a client sent (playbook 15). The register's own filters
    (applicability, compliance status) are not here: the overlay that would answer them
    lands with the register in chunk 8, and a filter the query cannot honour would be a
    200 that quietly ignored it."""

    instrument_id: UUID | None = None
    jurisdiction: str | None = None
    duty_type: str | None = None
    term_ids: list[UUID] = Field(default_factory=list, max_length=settings.LIBRARY_TERM_FILTER_MAX)
    binding: bool | None = None
    in_footprint: bool | None = None


class SearchRequest(WriteBody):
    """`q` is the typed query. `asOf` picks the version in force on that date (SRC-02);
    absent means today in the tenant's timezone. `lang` is a language key (I18N-01). The
    limit is the page size of playbook 10: above the maximum is a 422, never a clamp."""

    q: str = Field(min_length=1, max_length=settings.SEARCH_QUERY_MAX_CHARS)
    as_of: date | None = None
    lang: str | None = None
    types: list[SearchHitType] = Field(default_factory=list)
    filters: SearchFilters | None = None
    limit: int = Field(default=settings.API_PAGE_SIZE_DEFAULT, ge=1, le=settings.API_PAGE_SIZE_MAX)


class SimilarRequest(WriteBody):
    """What an agent sends to find the library records nearest a piece of text: to spot a
    change already tracked, and to suggest obligation links (AGT-02)."""

    text: str = Field(min_length=1, max_length=settings.SEARCH_SIMILAR_MAX_CHARS)
    types: list[SearchHitType] = Field(default_factory=list)
    limit: int = Field(default=settings.API_PAGE_SIZE_DEFAULT, ge=1, le=settings.API_PAGE_SIZE_MAX)


class SearchHit(CamelSchema):
    """One result. `matchKind` is on every hit (SRC-02): the reader sees why it is here.
    The version and validity dates are copied onto the chunk, so "as of" needs no join."""

    type: SearchHitType
    id: UUID
    title: str
    snippet: str
    match_kind: SearchMatchKind
    score: float
    version_no: int | None = None
    instrument_short_name: str | None = None
    binding: bool | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    urgency: TermRef | None = None


class SearchResponse(CamelSchema):
    """Ranked results, not a page: `asOf` is the date the ranking was taken at, echoed so
    the screen can say which day's law it is showing."""

    items: list[SearchHit]
    as_of: date


# ---------------------------------------------------------------------------------------
# POST /ask, POST /answers/{answerId}/feedback
# ---------------------------------------------------------------------------------------
class AskRequest(WriteBody):
    """The question is the only tenant text that reaches a model (D-07, SRC-S6)."""

    question: str = Field(min_length=1, max_length=settings.ASK_QUESTION_MAX_CHARS)
    as_of: date | None = None
    lang: str | None = None


class AnswerCitation(CamelSchema):
    """What a statement points at. `index` is the number shown in the answer."""

    index: int
    obligation_id: UUID
    version_no: int
    instrument_short_name: str
    ref_label: str
    provision_id: UUID | None = None


class AnswerStatement(CamelSchema):
    """One sentence of the answer. Every statement carries at least one citation
    (SRC-03, AC-SRC2); a cited obligation with an open change names it, so the screen can
    warn that the law is about to move."""

    text: str
    citation_indexes: list[int]
    pending_change_id: UUID | None = None
    pending_change_label: str | None = None


class Answer(CamelSchema):
    """Grounded only in the inventory. `noAnswer` is true when nothing supported an
    answer, and then `statements` is empty: the product says so rather than guessing
    (SRC-03, AC-SRC2). `aiGenerated` stays true until a person confirms it (D-04)."""

    id: UUID
    question: str
    as_of: date
    statements: list[AnswerStatement]
    citations: list[AnswerCitation]
    no_answer: bool
    model: str
    ai_generated: bool
    created_at: datetime


# --- what `POST /ask` streams -----------------------------------------------------------
# Ask answers an event stream, because the budget is a first token under 2 s (playbook 10,
# SRC-S9) and an answer that waits for its last sentence cannot meet it. One model per
# event kind, `event` naming the kind so a client can switch on it; the wire is
# `text/event-stream`, one `data:` frame per event.
class AskStartEvent(CamelSchema):
    """`start`, the first event and the one the 2 s budget is measured to. It carries the
    answer's id, so a reader's verdict (`rateAnswer`) has something to point at before the
    answer is finished."""

    event: Literal["start"] = "start"
    id: UUID


class AskStatementEvent(CamelSchema):
    """`statement`, one cited sentence of the answer, sent as soon as it is grounded."""

    event: Literal["statement"] = "statement"
    statement: AnswerStatement


class AskAnswerEvent(CamelSchema):
    """`answer`, the terminal event: the whole answer with its citation list, which is
    what a reader keeps and what the `ai_generation` row records (AUD-02)."""

    event: Literal["answer"] = "answer"
    answer: Answer


class AskProblemEvent(CamelSchema):
    """`problem`, the other way the stream ends. It carries the `code` an RFC 9457 body
    would carry (playbook 4.4), because a failure found after the first byte can no longer
    be a status; no trace and nothing the caller did not send travel with it."""

    event: Literal["problem"] = "problem"
    code: str
    detail: str


AskEvent = AskStartEvent | AskStatementEvent | AskAnswerEvent | AskProblemEvent


class AnswerFeedbackKind(enum.StrEnum):
    """Tier-one kind: what a reader said about an answer. The evaluation set reads it."""

    HELPFUL = "helpful"
    WRONG = "wrong"


class AnswerFeedbackBody(WriteBody):
    feedback: AnswerFeedbackKind
    note: str = Field(default="", max_length=settings.SEARCH_FEEDBACK_NOTE_MAX_CHARS)
