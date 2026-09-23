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

Every property below is documented to Alex's API rule of 2026-09-20: what the fact means
to a bank, `Source:` naming where it comes from (the shared library, the bank's own zone,
an agent, the caller, or the server), and `Do not read` naming what a reader must not
conclude from it. A fixed kind lists every member in its docstring with what the system
does differently for it; a vocabulary-backed key names its vocabulary, says the values
are rows an admin may extend, and gives the keys seeded on day one. Every limit that
matters is in words as well as in the schema keywords, and every request body and every
response carries a realistic example from the prototype's data: Example Bank AB, a
Swedish bank, reading FFFS and EU instruments.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from django.conf import settings
from pydantic import ConfigDict, Field

from apps.shared.schemas import CamelSchema, WriteBody
from apps.taxonomy.schemas import TermRef
from apps.watch.schemas import DatePrecision

__all__ = ["CamelSchema"]

# The page size every list in the product uses (playbook 10), stated here in words because
# a caller reads the contract and not settings.py: the default is 20 results and the
# maximum 100. A limit above the maximum answers 422 naming the field; it is never clamped
# down to 100, because a reader who asked for 200 and silently got 100 would believe they
# had seen everything.
_LIMIT = (
    f"How many results to return. Default {settings.API_PAGE_SIZE_DEFAULT}, maximum "
    f"{settings.API_PAGE_SIZE_MAX}; a larger number answers 422 naming the field and is "
    "never quietly clamped. Source: the caller. Do not read the number of results as the "
    "number of records that matched: it is one page of a ranking, not a count."
)
_AS_OF = (
    "The date the question is asked about: the server ranks and returns the version of "
    "each record that was in force on that day, so a reader can see the law as it stood. "
    "Absent means today in the bank's own time zone. Source: the caller. Do not read an "
    "`asOf` in the past as a record of what the bank knew then: it re-reads today's "
    "library at an older legal date, and a record corrected since is returned corrected."
)
_LANG = (
    "Which language's text to search and return, as a language key. The keys are rows in "
    "the library's `Language` list, not an enum, and a sixth language is added by seeding "
    "a row rather than by changing code; seeded on day one are `en` (English), `sv` "
    "(Svenska), `da` (Dansk), `nb` (Norsk bokmal) and `fi` (Suomi). Absent means the "
    "bank's default content language. Source: the caller, choosing from the shared "
    "library's language rows. Do not read a language as a jurisdiction: a Swedish "
    "obligation has an English summary, and EU material is read in five languages."
)


class SearchChunkMetadata(CamelSchema):
    """The `metadata` column of `search_chunk` (apps/search/models.py): the facts a filter
    compares before anything is ranked, copied onto the chunk from the library record it
    was built from, so `POST /search` needs no join to honour a filter.

    It is a database column and not part of the API, so it is stored by field name in
    snake_case like every other column. `instrument_id` and `obligation_id` are the
    records the chunk belongs to, `regime` and `term_ids` its taxonomy scope, `binding`
    whether the instrument binds, and `jurisdiction` and `duty_type` the vocabulary keys
    `SearchFilters` sends; `authority` is the issuing authority's key on a registered
    change's chunk. Every one of them is a key or an id, never a label, so
    relabelling a vocabulary row rewrites no chunk.
    """

    instrument_id: UUID | None = None
    obligation_id: UUID | None = None
    regime: str | None = None
    binding: bool | None = None
    term_ids: list[UUID] = Field(default_factory=list)
    jurisdiction: str | None = None
    duty_type: str | None = None
    authority: str | None = None


class SearchHitType(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): what a hit points at. The reader opens an
    obligation, a provision or a change, and the screen branches on it.

    Every member, and what the system does differently for each:

    - `obligation`: the hit is an obligation version from the shared inventory. The
      screen opens the obligation card at that version, the hit carries `versionNo`, and
      the footprint filter and the regulatory scope apply to it.
    - `provision`: the hit is a provision version, a numbered piece of an instrument's
      text. The screen opens the instrument at that provision; a provision has no
      obligation of its own, so it carries no urgency and cannot be put in a case.
    - `change`: the hit is a registered regulatory change from the watch feed. The screen
      opens the change, and this is the only member whose record may still be a proposal
      about the future rather than law in force, so its validity dates may be empty.
    """

    OBLIGATION = "obligation"
    PROVISION = "provision"
    CHANGE = "change"


class SearchMatchKind(enum.StrEnum):
    """Tier-one kind: how the hit was won (SRC-02, AC-SRC1). Every hit says so, and the
    pill's tone follows the kind, never a person's choice (NFR-03).

    Every member, and what the system did differently to find it:

    - `keyword`: the words the reader typed were found in the text, by the language's own
      PostgreSQL text search. An identifier such as `FFFS 2017:2` matches this way.
    - `concept`: no word matched, but the meaning did: the record was found by the
      nearest-neighbour search over embeddings. A record not yet embedded can never be a
      `concept` hit, so a fresh approval is found by its words first.
    - `both`: the record was found by both legs and its two ranks were fused, which is why
      it usually ranks above a hit of either other kind.
    """

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

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"jurisdiction": "se", "dutyType": "disclosure", "binding": True, "inFootprint": True}]
        }
    )

    instrument_id: UUID | None = Field(
        default=None,
        description=(
            "Narrow the search to one instrument, such as FFFS 2017:2, by the instrument's "
            "id, a UUID. Source: the shared library. Do not read a filtered result as "
            "everything the instrument requires of the bank: it is what matched the query "
            "inside that instrument, not the instrument's full obligation list."
        ),
    )
    jurisdiction: str | None = Field(
        default=None,
        description=(
            "Narrow the search to the law of one jurisdiction, by key. The keys are rows "
            "in the shared library's `jurisdiction` vocabulary; the platform seeds and "
            "maintains them (they are reference data, not proposable), and on day one they "
            "are `eu` (European Union), `se` (Sweden), `dk` (Denmark), `no` (Norway) and "
            "`fi` (Finland). Source: the shared library. Do not read `se` as excluding EU "
            "law that binds a Swedish bank: an EU regulation is filed under `eu` and still "
            "applies, so filtering to one jurisdiction hides law the bank must follow."
        ),
    )
    duty_type: str | None = Field(
        default=None,
        description=(
            "Narrow the search to one kind of duty, such as what must be reported or "
            "disclosed, by key. The keys are rows in the shared library's `duty_type` "
            "vocabulary, which an administrator may extend through an approved proposal "
            "(VOC-07); seeded on day one are `conduct`, `disclosure`, `record_keeping`, "
            "`reporting`, `governance` and `technical`. Source: the shared library. Do "
            "not read a duty type as a department: one obligation carries one duty type, "
            "and who in the bank owns it is the bank's own judgement, recorded elsewhere."
        ),
    )
    term_ids: list[UUID] = Field(
        default_factory=list,
        max_length=settings.LIBRARY_TERM_FILTER_MAX,
        description=(
            "Narrow the search to records tagged with all of these taxonomy terms, such as "
            "a regime or a legal entity kind, each by its term id, a UUID. Terms are rows in the shared "
            "library's taxonomy, which an administrator may extend through an approved "
            "proposal; the dimensions seeded on day one are `regime`, `account_type`, "
            f"`legal_entity`, `service_type`, `client_category`, `channel` and "
            f"`lifecycle_stage`. At most {settings.LIBRARY_TERM_FILTER_MAX} terms in one "
            "call; more answers 422. Source: the shared library. Do not read the terms on "
            "a record as the bank's own scope: whether the record applies to this bank is "
            "a separate fact the bank decides."
        ),
    )
    binding: bool | None = Field(
        default=None,
        description=(
            "True keeps only binding law, false keeps only guidance such as ESMA's. The "
            "value follows the instrument's level, so an act and an EU regulation are "
            "binding and EU guidance is not. Source: the shared library. Do not read "
            "`false` as optional: a supervisor expects guidance to be followed or the "
            "departure explained, and the bank still answers for it."
        ),
    )
    in_footprint: bool | None = Field(
        default=None,
        description=(
            "True keeps only records inside the bank's own footprint, the licences, "
            "entities and services it declared; false keeps only those outside it. Absent "
            "applies the bank's standing regulatory scope, which is what the search screen "
            "does until a reader asks to look outside it. Source: the bank's own zone, "
            "compared against the shared library. Do not read `inFootprint` as `applies to "
            "us`: the footprint is a filter on what is worth reading, while whether an "
            "obligation applies is a judgement the bank records per entity (chunk 8)."
        ),
    )


class SearchRequest(WriteBody):
    """`q` is the typed query. `asOf` picks the version in force on that date (SRC-02);
    absent means today in the tenant's timezone. `lang` is a language key (I18N-01). The
    limit is the page size of playbook 10: above the maximum is a 422, never a clamp.

    Budget: the server answers inside 800 ms without the reranker and 1.5 s with it
    (NFR-02), reported in `Server-Timing`. The call is a read: it writes no audit row,
    needs no idempotency key, and is not streamed."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "q": "FFFS 2017:2 costs and charges",
                    "asOf": "2026-09-20",
                    "lang": "sv",
                    "types": ["obligation", "provision"],
                    "filters": {
                        "jurisdiction": "se",
                        "dutyType": "disclosure",
                        "binding": True,
                        "inFootprint": True,
                    },
                    "limit": 20,
                }
            ]
        }
    )

    q: str = Field(
        min_length=1,
        max_length=settings.SEARCH_QUERY_MAX_CHARS,
        description=(
            "What the reader typed: an identifier such as `FFFS 2017:2`, or a concept such "
            f"as `kostnader och avgifter`. At most {settings.SEARCH_QUERY_MAX_CHARS} "
            "characters, and a longer query answers 422 rather than being truncated into a "
            "search for something else. Source: the caller; it is the bank's own text and "
            "never reaches a log line, a URL or an error message. Do not read the absence "
            "of a hit as the absence of an obligation: the index holds the shared library "
            "as it stands today, not the bank's own notes, cases or evidence."
        ),
    )
    as_of: date | None = Field(default=None, description=_AS_OF)
    lang: str | None = Field(default=None, description=_LANG)
    types: list[SearchHitType] = Field(
        default_factory=list,
        description=(
            "Which kinds of record to search; empty means all three. Source: the caller. "
            "Do not read an empty list as a promise of three kinds in the results: a query "
            "may simply match nothing of a kind."
        ),
    )
    filters: SearchFilters | None = Field(
        default=None,
        description=(
            "Narrows the search before anything is ranked, so a filtered search is not a "
            "shortened list of the unfiltered one. Absent means the bank's standing "
            "regulatory scope alone. Source: the caller. Do not read a filter the contract "
            "does not name as ignored: an unknown filter answers 422."
        ),
    )
    limit: int = Field(
        default=settings.API_PAGE_SIZE_DEFAULT,
        ge=1,
        le=settings.API_PAGE_SIZE_MAX,
        description=_LIMIT,
    )


class SimilarRequest(WriteBody):
    """What an agent sends to find the library records nearest a piece of text: to spot a
    change already tracked, and to suggest obligation links (AGT-02).

    This is the agents' route, held open by an API key with the `search:read` scope; no
    person's session reaches it. Same 800 ms budget as `POST /search`. The call is a
    read: no audit row, no idempotency key, not streamed."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "text": (
                        "Institut som tar emot investeringsanalys ska ha kriterier for en "
                        "arlig bedomning av analysens kvalitet, anvandbarhet och varde."
                    ),
                    "types": ["obligation", "change"],
                    "limit": 10,
                }
            ]
        }
    )

    text: str = Field(
        min_length=1,
        max_length=settings.SEARCH_SIMILAR_MAX_CHARS,
        description=(
            "The passage to find library records near: a paragraph an agent fetched from a "
            f"supervisor's page, or a change summary. At most "
            f"{settings.SEARCH_SIMILAR_MAX_CHARS} characters; longer answers 422. Source: "
            "the calling agent. Do not read this text as trusted: it is fetched content, "
            "it is never stored by this call, and nothing it says can direct the server."
        ),
    )
    types: list[SearchHitType] = Field(
        default_factory=list,
        description=(
            "Which kinds of record to compare the text against: `obligation`, an "
            "obligation version from the shared inventory; `provision`, a numbered piece "
            "of an instrument's text; `change`, a registered regulatory change from the "
            "watch feed. An empty list means all three are compared. Source: the calling "
            "agent. Do not read an empty list as a promise that all three appear in the "
            "results: the text may simply be near nothing of a kind."
        ),
    )
    limit: int = Field(
        default=settings.API_PAGE_SIZE_DEFAULT,
        ge=1,
        le=settings.API_PAGE_SIZE_MAX,
        description=_LIMIT,
    )


class SearchHit(CamelSchema):
    """One result. `matchKind` is on every hit (SRC-02): the reader sees why it is here.
    The version and validity dates are copied onto the chunk, so "as of" needs no join."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "obligation",
                    "id": "7b1f2c4e-8d3a-4c61-9f0b-2e5a7c9d1a44",
                    "title": "Disclose all costs and charges before and after the service",
                    "snippet": "...all costs and charges, aggregated and itemised, before the service is provided...",
                    "matchKind": "both",
                    "score": 0.87,
                    "versionNo": 3,
                    "instrumentShortName": "FFFS 2017:2",
                    "binding": True,
                    "validFrom": "2026-01-01",
                    "validTo": None,
                    "urgency": {"key": "within_3_months", "kind": "warning", "label": "Within 3 months"},
                }
            ]
        }
    )

    type: SearchHitType = Field(
        description=(
            "What this hit points at, and therefore what opens when the reader clicks it. "
            "Source: the shared library, copied onto the search index. Do not read the kind "
            "as a ranking: an obligation does not outrank a provision by being one."
        )
    )
    id: UUID = Field(
        description=(
            "The id of the record the hit points at, a UUID: the obligation, the provision "
            "or the registered change. Source: the shared library. Do not read it as the id "
            "of the indexed chunk, which is derived data the API never exposes."
        )
    )
    title: str = Field(
        description=(
            "The record's own heading, in the language searched, so a reader recognises it "
            "without opening it. Source: the shared library. Do not read a title as the "
            "obligation: the duty is in the text, and a title is written to be found."
        )
    )
    snippet: str = Field(
        description=(
            "A short extract of the record's text around what matched, so the reader can "
            "judge the hit before opening it. Source: the shared library. Do not read a "
            "snippet as the text of the law: it is cut mid-sentence and a condition may sit "
            "in the words on either side of it."
        )
    )
    match_kind: SearchMatchKind = Field(
        description=(
            "Why this record is in the list: its words matched, its meaning matched, or "
            "both. Source: computed by the server for this query. Do not read `concept` as "
            "weaker evidence, nor its absence as proof the words are missing: a record not "
            "yet embedded can only ever match by keyword."
        )
    )
    score: float = Field(
        description=(
            "How this hit ranked against the others in this one answer, after the two legs "
            "were fused and reranked. Source: computed by the server for this query. Do not "
            "read it as relevance the bank can compare across searches, as a probability, "
            "or as a measure of how much the record matters: it is only an order."
        )
    )
    version_no: int | None = Field(
        default=None,
        description=(
            "Which version of the obligation was in force on the `asOf` date, so the reader "
            "opens the card at the text that was law then. Empty on a provision or a change. "
            "Source: the shared library. Do not read a high version number as instability: "
            "a correction of a typo is a version too."
        ),
    )
    instrument_short_name: str | None = Field(
        default=None,
        description=(
            "The everyday name of the instrument the record belongs to, such as `FFFS "
            "2017:2`, `MiFID II` or `DORA`. Source: the shared library. Do not read it as "
            "the official citation: the formal reference is on the instrument itself."
        ),
    )
    binding: bool | None = Field(
        default=None,
        description=(
            "Whether the record is binding law or guidance, following the instrument's "
            "level. Source: the shared library. Do not read `false` as optional: guidance "
            "is expected to be followed or the departure explained."
        ),
    )
    valid_from: date | None = Field(
        default=None,
        description=(
            "The first day this version of the record was in force, a plain date such as "
            "`2026-01-01`, so a reader knows whether it governed a transaction. Empty when "
            "the library holds no such day, as on a change not yet in force. Source: the "
            "shared library. Do not read it as the day the bank had to comply from: a "
            "transitional rule may give longer, and that is in the text."
        ),
    )
    valid_to: date | None = Field(
        default=None,
        description=(
            "The last day this version was in force, a plain date such as `2026-08-31`; "
            "empty means it still is. Source: the shared library. Do not read an empty value "
            "as permanent: a change already registered in the watch feed may be about to "
            "close it."
        ),
    )
    urgency: TermRef | None = Field(
        default=None,
        description=(
            "How soon the shared library says this record deserves attention, as a key, its "
            "pill tone and a label in the reader's language. The keys are rows in the "
            "shared library's `urgency` vocabulary, which an administrator may extend "
            "through an approved proposal; seeded on day one are `act_now`, "
            "`within_3_months`, `six_months_plus`, `monitor` and `no_action`. Source: the "
            "shared library. Do not read it as this bank's priority: it is the library's "
            "general view, and the bank's own deadline lives on its case."
        ),
    )


class SearchResponse(CamelSchema):
    """Ranked results, not a page: `asOf` is the date the ranking was taken at, echoed so
    the screen can say which day's law it is showing."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "type": "obligation",
                            "id": "7b1f2c4e-8d3a-4c61-9f0b-2e5a7c9d1a44",
                            "title": "Disclose all costs and charges before and after the service",
                            "snippet": "...all costs and charges, aggregated and itemised, before the service...",
                            "matchKind": "both",
                            "score": 0.87,
                            "versionNo": 3,
                            "instrumentShortName": "FFFS 2017:2",
                            "binding": True,
                            "validFrom": "2026-01-01",
                            "validTo": None,
                            "urgency": {"key": "within_3_months", "kind": "warning", "label": "Within 3 months"},
                        },
                        {
                            "type": "provision",
                            "id": "3c9d6e21-5b47-4a08-9c13-6f2d8b0e7a15",
                            "title": "9 kap. Rorelseregler",
                            "snippet": "...institutet ska lamna information om kostnader och avgifter...",
                            "matchKind": "keyword",
                            "score": 0.61,
                            "versionNo": None,
                            "instrumentShortName": "LVM",
                            "binding": True,
                            "validFrom": "2007-11-01",
                            "validTo": None,
                            "urgency": None,
                        },
                    ],
                    "asOf": "2026-09-20",
                }
            ]
        }
    )

    items: list[SearchHit] = Field(
        description=(
            "The ranked results, best first, at most `limit` of them. Source: the shared "
            "library, ranked by the server. Do not read an empty list as nothing existing: "
            "the bank's regulatory scope and any filter were applied before ranking, and a "
            "reader can search outside the scope to see what was held back."
        )
    )
    as_of: date = Field(
        description=(
            "The legal date this ranking was taken at, echoed so the screen can say which "
            "day's law it is showing. Source: computed by the server from the request, or "
            "today in the bank's time zone. Do not read it as the time the search ran: it "
            "is the date of the law, not of the query."
        )
    )


# ---------------------------------------------------------------------------------------
# POST /ask, POST /answers/{answerId}/feedback
# ---------------------------------------------------------------------------------------
class AskRequest(WriteBody):
    """The question is the only tenant text that reaches a model (D-07, SRC-S6).

    Ask is the one streamed operation in this contract: the answer arrives as
    `text/event-stream`, because the budget is a first token under 2 s (NFR-02) and an
    answer that waits for its last sentence cannot meet it. The call needs no idempotency
    key: asking twice costs two model calls and two logged generations, and never changes
    a record."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "question": "What must we disclose about costs before providing a service?",
                    "asOf": "2026-09-20",
                    "lang": "en",
                }
            ]
        }
    )

    question: str = Field(
        min_length=1,
        max_length=settings.ASK_QUESTION_MAX_CHARS,
        description=(
            "What the reader wants to know, in their own words. At most "
            f"{settings.ASK_QUESTION_MAX_CHARS} characters; a longer question answers 422 "
            "and no stream is opened. Source: the caller, from the bank's own zone. This "
            "is the only tenant text that ever reaches a model (D-07), and it reaches no "
            "log line, no Sentry event and no URL. Do not put client data, case notes or "
            "evidence in it: the answer is grounded only in the shared library, so nothing "
            "of the bank's own is needed to answer, and nothing of it should be sent."
        ),
    )
    as_of: date | None = Field(default=None, description=_AS_OF)
    lang: str | None = Field(default=None, description=_LANG)


class AnswerCitation(CamelSchema):
    """What a statement points at. `index` is the number shown in the answer."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "index": 1,
                    "obligationId": "7b1f2c4e-8d3a-4c61-9f0b-2e5a7c9d1a44",
                    "versionNo": 3,
                    "instrumentShortName": "FFFS 2017:2",
                    "refLabel": "Costs and charges",
                    "provisionId": "3c9d6e21-5b47-4a08-9c13-6f2d8b0e7a15",
                }
            ]
        }
    )

    index: int = Field(
        description=(
            "The number shown beside the statement, so a reader can follow a sentence to "
            "its source. Source: computed by the server for this answer. Do not read it as "
            "a stable reference: it numbers the citations of this answer only, and the same "
            "obligation is a different number in the next answer."
        )
    )
    obligation_id: UUID = Field(
        description=(
            "The obligation the statement rests on, by its id, a UUID, which the reader "
            "opens to check it. Source: the shared library. Do not read a citation as a "
            "finding that the obligation applies to this bank: applicability is a separate "
            "judgement."
        )
    )
    version_no: int = Field(
        description=(
            "Which version of that obligation was read, so the citation stays checkable "
            "after the obligation moves on. Source: the shared library. Do not read it as "
            "the current version: it is the version in force on the answer's `asOf` date."
        )
    )
    instrument_short_name: str = Field(
        description=(
            "The everyday name of the instrument cited, such as `FFFS 2017:2` or `MiFID "
            "II`, so the citation reads as a lawyer would write it. Source: the shared "
            "library. Do not read it as the official citation, which is on the instrument."
        )
    )
    ref_label: str = Field(
        description=(
            "Where in the instrument the cited text sits, as the instrument labels it, such "
            "as `9 kap.` or `Costs and charges`. Source: the shared library. Do not read it "
            "as a stable identifier: it is the drafter's own label, and a recast renumbers."
        )
    )
    provision_id: UUID | None = Field(
        default=None,
        description=(
            "The exact provision behind the obligation, by its id, a UUID, when the answer "
            "could pin one, so the reader lands on the paragraph rather than the card. Empty "
            "today: an answer cites the obligation, and the provision is one click further. "
            "Source: the shared library. Do not read its absence as a weaker citation: many "
            "obligations summarise several provisions and pin none."
        ),
    )


class AnswerStatement(CamelSchema):
    """One sentence of the answer. Every statement carries at least one citation
    (SRC-03, AC-SRC2); a cited obligation with an open change names it, so the screen can
    warn that the law is about to move."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "text": (
                        "Costs and charges must be disclosed in aggregate and itemised "
                        "before the service is provided, and again afterwards."
                    ),
                    "citationIndexes": [1],
                    "pendingChangeId": "a41d0f36-2c88-4e7b-b5a9-13d6c4f80e27",
                    "pendingChangeLabel": "FI adopts amended rules on paying for investment research",
                    "pendingChangeInForceOn": "2026-10-01",
                    "pendingChangeInForceOnPrecision": "day",
                }
            ]
        }
    )

    text: str = Field(
        description=(
            "One sentence of the answer, written by a model from the cited library text "
            "alone. Source: a model, grounded only in the shared library. Do not read it as "
            "advice or as a compliance conclusion: it is AI output, labelled as such until "
            "a person confirms it, and the citation is the thing to check."
        )
    )
    citation_indexes: list[int] = Field(
        description=(
            "Which citations support this sentence, by their `index` in the answer. Never "
            "empty: a statement the library did not support is not sent at all. Source: "
            "computed by the server. Do not read several citations as agreement between "
            "sources: they are the passages the sentence was drawn from."
        )
    )
    pending_change_id: UUID | None = Field(
        default=None,
        description=(
            "The registered change that will move the law this sentence rests on, by its "
            "id, a UUID, so a reader is warned before acting on it. Only a change the "
            "library confirmed affects a cited obligation, still active, whose type's "
            "lifecycle kind moves the law on its key date (`adopted`, or `in_force` from a "
            "later day) and whose key date falls after the answer's `asOf`; of several, the "
            "earliest. Empty when there is none. Source: the shared library's watch feed. "
            "Do not read it as the law today: the sentence still describes the rule in "
            "force on `asOf`, and the change is what comes next."
        ),
    )
    pending_change_label: str | None = Field(
        default=None,
        description=(
            "The title of that change, so the warning reads as something rather than an id. "
            "Source: the shared library's watch feed. Do not read it as a summary of the "
            "effect on the bank: what it means here is the bank's own assessment."
        ),
    )
    pending_change_in_force_on: date | None = Field(
        default=None,
        description=(
            "The day that change takes effect, as a plain date such as `2026-10-01`, so the "
            "screen can warn \"Change pending: in force 1 Oct\" and the reader knows how long "
            "the sentence stays true. Only an adopted change, or one already in force from a "
            "later day, is flagged: a consultation or a supervisory statement moves no law on "
            "a date. Empty exactly when `pendingChangeId` is. Source: the key date the shared "
            "library's watch feed holds for the change. Do not read it as the bank's own "
            "deadline, which lives on its case, nor as a promise: a date can still move."
        ),
    )
    pending_change_in_force_on_precision: DatePrecision | None = Field(
        default=None,
        description=(
            "How exact that date is, a fixed kind: `day` renders as 1 October 2026, "
            "`month` as October 2026, `quarter` as Q4 2026 and `year` as 2026. Empty "
            "exactly when `pendingChangeInForceOn` is. Source: the shared library's watch "
            "feed, as the source stated the date. Do not print a day the source did not "
            "state: render the date by this precision."
        ),
    )


class Answer(CamelSchema):
    """Grounded only in the inventory. `noAnswer` is true when nothing supported an
    answer, and then `statements` is empty: the product says so rather than guessing
    (SRC-03, AC-SRC2). `aiGenerated` stays true until a person confirms it (D-04)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "0f5b8c2d-91a4-4e36-8b7f-5c2a0d94e613",
                    "question": "What must we disclose about costs before providing a service?",
                    "asOf": "2026-09-20",
                    "statements": [
                        {
                            "text": (
                                "Costs and charges must be disclosed in aggregate and "
                                "itemised before the service is provided, and again "
                                "afterwards."
                            ),
                            "citationIndexes": [1],
                            "pendingChangeId": None,
                            "pendingChangeLabel": None,
                            "pendingChangeInForceOn": None,
                            "pendingChangeInForceOnPrecision": None,
                        }
                    ],
                    "citations": [
                        {
                            "index": 1,
                            "obligationId": "7b1f2c4e-8d3a-4c61-9f0b-2e5a7c9d1a44",
                            "versionNo": 3,
                            "instrumentShortName": "FFFS 2017:2",
                            "refLabel": "Costs and charges",
                            "provisionId": "3c9d6e21-5b47-4a08-9c13-6f2d8b0e7a15",
                        }
                    ],
                    "noAnswer": False,
                    "model": "claude-sonnet-4-5",
                    "aiGenerated": True,
                    "createdAt": "2026-09-20T09:14:02Z",
                }
            ]
        }
    )

    id: UUID = Field(
        description=(
            "This answer's id, a UUID, which a reader's verdict points at (`rateAnswer`) and "
            "which the AI log row of its model call carries as its own. Source: the server, "
            "generated before the first event. Do not read it as a record of the bank's "
            "position: an answer is a reading aid, and nothing in the inventory changed "
            "because it was given."
        )
    )
    question: str = Field(
        description=(
            "The question as asked, echoed so the answer is readable on its own. Source: "
            "the caller, from the bank's own zone. Do not expect to find it anywhere else: "
            "it is tenant text and never reaches a log line, an audit summary or a URL."
        )
    )
    as_of: date = Field(
        description=(
            "The legal date the answer was written against: every citation is the version "
            "in force that day. Source: computed by the server from the request. Do not "
            "read it as the time the answer was produced, which is `createdAt`."
        )
    )
    statements: list[AnswerStatement] = Field(
        description=(
            "The answer, sentence by sentence, each one cited. Empty when `noAnswer` is "
            "true. Source: a model, grounded only in the shared library. Do not read the "
            "order as priority: it reads as prose, not as a ranking of duties."
        )
    )
    citations: list[AnswerCitation] = Field(
        description=(
            "Every library passage the statements rest on, numbered. Source: the shared "
            "library. Do not read the list as the complete set of obligations on the "
            "subject: it is what this answer used, retrieved from what the bank may see."
        )
    )
    no_answer: bool = Field(
        description=(
            "True when the library held nothing that supported an answer, and then the "
            "product says so rather than guessing. Source: computed by the server. Do not "
            "read it as there being no obligation: it means nothing was retrieved that "
            "answered the question, inside the bank's regulatory scope, on that date."
        )
    )
    model: str = Field(
        description=(
            "Which model wrote the statements, so a bank's vendor review can trace an "
            "answer to the system that produced it. Empty when no model was asked: a "
            "question no library passage supported is answered `noAnswer` without one. "
            "Source: the server's model call, recorded on the AI log row. Do not read a "
            "model name as a quality guarantee."
        )
    )
    ai_generated: bool = Field(
        description=(
            "True while the answer is machine output nobody has confirmed, which is what "
            "the screen's label says. Source: computed by the server. Do not read `false` "
            "as verified by a supervisor: it means a person in the bank confirmed it (D-04)."
        )
    )
    created_at: datetime = Field(
        description=(
            "When the answer was produced: an RFC 3339 date-time in UTC, such as "
            "`2026-09-20T09:14:02Z`. Source: the server, stamped when the stream opened. "
            "Do not read it as the date the law was read at, which is `asOf`."
        )
    )


# --- what `POST /ask` streams -----------------------------------------------------------
# Ask answers an event stream, because the budget is a first token under 2 s (playbook 10,
# SRC-S9) and an answer that waits for its last sentence cannot meet it. One model per
# event kind, `event` naming the kind so a client can switch on it; the wire is
# `text/event-stream`, one `data:` frame per event.
class AskStartEvent(CamelSchema):
    """`start`, the first event and the one the 2 s budget is measured to. It carries the
    answer's id, so a reader's verdict (`rateAnswer`) has something to point at before the
    answer is finished."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"event": "start", "id": "0f5b8c2d-91a4-4e36-8b7f-5c2a0d94e613"}]}
    )

    event: Literal["start"] = Field(
        default="start",
        description=(
            "Always `start`: the kind of this event, which the client switches on. Source: "
            "the server. Do not read the four event kinds as a fixed sequence: a stream may "
            "end at `problem` after `start` and before any statement."
        ),
    )
    id: UUID = Field(
        description=(
            "The answer's id, a UUID, sent first so the screen can offer a verdict while the "
            "answer is still arriving; the closing `answer` event carries the same id. "
            "Source: the server. Do not read it as a promise that an answer follows: the "
            "stream may still close with a `problem` event."
        )
    )


class AskStatementEvent(CamelSchema):
    """`statement`, one cited sentence of the answer, sent as soon as it is grounded."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "event": "statement",
                    "statement": {
                        "text": (
                            "Costs and charges must be disclosed in aggregate and itemised "
                            "before the service is provided, and again afterwards."
                        ),
                        "citationIndexes": [1],
                        "pendingChangeId": None,
                        "pendingChangeLabel": None,
                        "pendingChangeInForceOn": None,
                        "pendingChangeInForceOnPrecision": None,
                    },
                }
            ]
        }
    )

    event: Literal["statement"] = Field(
        default="statement",
        description=(
            "Always `statement`: the kind of this event. Source: the server. Do not read a "
            "statement event as the end of the answer; the `answer` event closes it."
        ),
    )
    statement: AnswerStatement = Field(
        description=(
            "One cited sentence, sent as soon as it is grounded, so the reader sees the "
            "answer form. Source: a model, grounded only in the shared library. Do not read "
            "a sentence in isolation: the conditions may be in the sentences around it."
        )
    )


class AskAnswerEvent(CamelSchema):
    """`answer`, the terminal event: the whole answer with its citation list, which is
    what a reader keeps and what the `ai_generation` row records (AUD-02)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "event": "answer",
                    "answer": {
                        "id": "0f5b8c2d-91a4-4e36-8b7f-5c2a0d94e613",
                        "question": "What must we disclose about costs before providing a service?",
                        "asOf": "2026-09-20",
                        "statements": [
                            {
                                "text": (
                                    "Costs and charges must be disclosed in aggregate and "
                                    "itemised before the service is provided, and again "
                                    "afterwards."
                                ),
                                "citationIndexes": [1],
                                "pendingChangeId": None,
                                "pendingChangeLabel": None,
                                "pendingChangeInForceOn": None,
                                "pendingChangeInForceOnPrecision": None,
                            }
                        ],
                        "citations": [
                            {
                                "index": 1,
                                "obligationId": "7b1f2c4e-8d3a-4c61-9f0b-2e5a7c9d1a44",
                                "versionNo": 3,
                                "instrumentShortName": "FFFS 2017:2",
                                "refLabel": "Costs and charges",
                                "provisionId": "3c9d6e21-5b47-4a08-9c13-6f2d8b0e7a15",
                            }
                        ],
                        "noAnswer": False,
                        "model": "claude-sonnet-4-5",
                        "aiGenerated": True,
                        "createdAt": "2026-09-20T09:14:02Z",
                    },
                    "stopReason": "end_turn",
                }
            ]
        }
    )

    event: Literal["answer"] = Field(
        default="answer",
        description=(
            "Always `answer`: the kind of this event, and the last one on a stream that "
            "succeeded. Source: the server. Do not expect anything after it."
        ),
    )
    answer: Answer = Field(
        description=(
            "The whole answer with its citations, which is what the reader keeps and what "
            "the AI log records. Source: a model, grounded only in the shared library. Do "
            "not read it as confirmed: it stays labelled AI output until a person says "
            "otherwise."
        )
    )
    stop_reason: str | None = Field(
        default=None,
        description=(
            "How the model finished writing, in the provider's own word, exactly as the "
            "answer's AI log row stores it (`stopReason` there, D-82): `end_turn` when the "
            "model finished the answer, `max_tokens` when it was cut off at the length "
            "limit (`ASK_MAX_TOKENS`, 1024 tokens), and any other word the provider gives "
            "passed on unchanged. Empty when no model was asked, because no passage "
            "supported an answer. Source: the model's provider. Do not read `max_tokens` "
            "as a wrong answer: every statement sent is still cited, but the answer may "
            "stop before its last point, so the screen says it was cut short and a "
            "narrower question may get the rest."
        ),
    )


class AskProblemEvent(CamelSchema):
    """`problem`, the other way the stream ends. It carries the `code` an RFC 9457 body
    would carry (playbook 4.4), because a failure found after the first byte can no longer
    be a status; no trace and nothing the caller did not send travel with it."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "event": "problem",
                    "code": "model_unavailable",
                    "detail": "The answer could not be finished. Ask again in a moment.",
                }
            ]
        }
    )

    event: Literal["problem"] = Field(
        default="problem",
        description=(
            "Always `problem`: the kind of this event, and the last one on a stream that "
            "failed. Source: the server. Do not expect anything after it, and do not treat "
            "the 200 on the stream as success: the events say how it ended."
        ),
    )
    code: str = Field(
        description=(
            "The machine-readable reason the answer stopped, the same `code` an RFC 9457 "
            "problem body would carry. The one code a stream ends on is "
            "`model_unavailable`: the model could not be reached, declined, or did not "
            "finish before its deadline. The call is still in the AI log, with whatever it "
            "had written and `stopReason` `failed`, and asking again may succeed. "
            "Everything that can refuse a question before it is answered (no session, no "
            "permission, the rate limit, the bank's AI switch) is a status with a problem "
            "body instead, and no stream opens. Branch on this, never on `detail`. Source: "
            "the server. Do not read a code as a verdict on the question: it says why this "
            "stream stopped, not that the library holds no answer, which is `noAnswer` on a "
            "stream that finished."
        )
    )
    detail: str = Field(
        description=(
            "One sentence a person can read, saying what happened. Source: the server. Do "
            "not branch on this text, do not expect it to be stable, and do not expect a "
            "trace: nothing of the server's internals travels in it."
        )
    )


AskEvent = AskStartEvent | AskStatementEvent | AskAnswerEvent | AskProblemEvent


class AnswerFeedbackKind(enum.StrEnum):
    """Tier-one kind: what a reader said about an answer. The evaluation set reads it.

    Every member, and what the system does differently for it:

    - `helpful`: the reader found the answer useful. The AI log row is marked helpful and
      the evaluation set counts it as a positive signal on retrieval.
    - `wrong`: the reader found the answer wrong. The AI log row is marked wrong, which is
      what the AI log screen filters on for review, and the evaluation set counts it
      against retrieval quality.
    """

    HELPFUL = "helpful"
    WRONG = "wrong"


class AnswerFeedbackBody(WriteBody):
    """A reader's verdict on one answer (AUD-02, SRC-05).

    This is the only write in the search contract: it goes through the audit trail like
    any other. It needs no idempotency key because it is idempotent by nature — the same
    verdict on the same answer twice leaves one row — and it is not streamed. It answers
    inside the ordinary 250 ms API budget."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "feedback": "wrong",
                    "note": "The itemised disclosure is required before the service, not only afterwards.",
                }
            ]
        }
    )

    feedback: AnswerFeedbackKind = Field(
        description=(
            "Whether the answer helped, so the people who tune retrieval know where it "
            "fails. Source: the reader, in the bank's own zone. Do not read `helpful` as "
            "the answer being verified: confirming AI output is a separate act (D-04)."
        )
    )
    note: str = Field(
        default="",
        max_length=settings.SEARCH_FEEDBACK_NOTE_MAX_CHARS,
        description=(
            "What was wrong or useful about it, in the reader's own words. At most "
            f"{settings.SEARCH_FEEDBACK_NOTE_MAX_CHARS} characters; longer answers 422. "
            "Source: the reader, in the bank's own zone. Do not put client data or evidence "
            "in it: it is stored beside the answer for the bank's own review, and the audit "
            "row that records the verdict carries none of this text."
        ),
    )


# ---------------------------------------------------------------------------------------
# The evaluation set in the console (SRC-05, ADM-02): GET and POST /eval/questions and
# GET /eval/runs, platform staff only. Keys, never ids: a question names the library records
# it expects by stable key, because the corpus the gate builds has new ids every time.
# ---------------------------------------------------------------------------------------
EVAL_KEY_PATTERN = r"^[a-z0-9][a-z0-9-]*$"
_EXAMPLE_EVAL_QUESTION: dict[str, Any] = {
    "id": "0b6f3c1e-5d7a-4a54-9c2e-7f1d8e2a4b90",
    "key": "r-en-01",
    "lang": "en",
    "question": "FFFS 2017:2",
    "expected": ["obl-costs-charges", "obl-research-payments", "obl-product-governance", "obl-client-assets"],
    "matchKind": "keyword",
    "asOf": None,
    "notes": "An identifier is won by keyword. Every obligation under the instrument is relevant.",
    "active": True,
    "inGate": True,
}
_EXAMPLE_EVAL_SCORES: dict[str, Any] = {"recallAt10": 0.92, "mrr": 0.81}
_EXAMPLE_EVAL_RUN: dict[str, Any] = {
    "id": "5e2d9a47-1c3b-4f6e-8a0d-2b7c9e4f1a36",
    "runAt": "2026-09-23T06:00:00Z",
    "config": {"retriever": "apps.search.eval:Retriever (embedder none, reranker none)", "isMock": False, "questions": 53},
    "metrics": {
        "overall": _EXAMPLE_EVAL_SCORES,
        "perLanguage": {"en": _EXAMPLE_EVAL_SCORES, "sv": {"recallAt10": 0.88, "mrr": 0.79}},
        "perMatchKind": {"keyword": {"recallAt10": 1.0, "mrr": 0.97}, "concept": {"recallAt10": 0.8, "mrr": 0.66}},
    },
    "results": [
        {
            "questionKey": "r-en-01",
            "returned": ["obl-costs-charges", "obl-client-assets", "obl-product-governance", "obl-research-payments"],
            "recallAt10": 1.0,
            "mrr": 1.0,
        }
    ],
}
_MATCH_KIND = (
    "What the question expects to win it, which is what AC-SRC1 checks: `keyword` when an "
    "identifier such as `FFFS 2017:2` must be found by its words, `concept` when a phrasing "
    "such as `nudging in onboarding` must be found by meaning, `both` when one query needs "
    "the two legs fused. The gate reports its scores per match kind, so a regression in one "
    "leg shows on its own. Source: platform staff. Do not read it as how any hit was "
    "actually found: that is the `matchKind` of a search hit."
)
_EXPECTED = (
    "The library records a good answer contains, each by its stable key (an obligation's "
    "`obl-costs-charges`, a provision's `sfs-2007-528/9`, a change's key), every one of them "
    "relevant. Recall at 10 is the share of them found in the first ten hits and MRR the "
    "reciprocal rank of the first. An empty list is a question the library has no answer "
    "to: it scores right only when search returns nothing. At most "
    f"{settings.API_PAGE_SIZE_MAX} keys, the widest page the gate's search asks for, each "
    "1 to 200 characters; more answers 422. Source: platform staff; the keys are not "
    "checked against the library, because the gate scores the sample corpus and not this "
    "database's records. Do not read a key here as a record this deployment holds."
)


class EvalScores(CamelSchema):
    """Two retrieval scores over a set of questions, each a mean between 0 and 1."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_EVAL_SCORES]})

    recall_at_10: float = Field(
        ge=0,
        le=1,
        description=(
            "The mean share of the expected records found in the first ten hits, from 0 "
            "(none found) to 1 (all found). Source: the server, computed by the release "
            "gate's own scoring. Do not read it as precision: extra hits cost nothing here."
        ),
    )
    mrr: float = Field(
        ge=0,
        le=1,
        description=(
            "The mean reciprocal rank of the first expected record, from 0 (never found) to "
            "1 (always first). Source: the server, computed by the release gate's own "
            "scoring. Do not read it as a share of questions answered."
        ),
    )


class EvalRunConfig(CamelSchema):
    """What a run scored: which retrieval chain, and over how many questions."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_EVAL_RUN["config"]]})

    retriever: str = Field(
        description=(
            "The retrieval chain that answered, naming its embedder and reranker, for "
            "example `apps.search.eval:Retriever (embedder none, reranker none)`. Source: "
            "the server. Do not read it as the chain this deployment serves searches with: "
            "the run scores the sample corpus in a database of its own."
        )
    )
    is_mock: bool = Field(
        description=(
            "True when any adapter in the chain was a stand-in (a mock embedder or "
            "reranker), so the scores say nothing about a real model; false when every "
            "adapter was real or absent. Source: the server. Do not compare a mock run's "
            "scores with a real one's."
        )
    )
    questions: int = Field(
        ge=0,
        description=(
            "How many active questions were asked in the run, 0 or more. Source: the server. "
            "Do not read it as the size of the set: inactive questions are not asked."
        ),
    )


class EvalRunMetrics(CamelSchema):
    """A run's scores overall, per content language and per match kind."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_EVAL_RUN["metrics"]]})

    overall: EvalScores = Field(
        description=(
            "The scores over every question asked. Source: the server. Do not read them as "
            "the release gate's verdict: the gate compares them with a recorded baseline."
        )
    )
    per_language: dict[str, EvalScores] = Field(
        description=(
            "The scores per content language of the questions, keyed by language key (`en`, "
            "`sv`, `da`, `nb`, `fi`, the library's language rows). Source: the server. Do "
            "not read a language that is absent as scoring zero: no question in it was asked."
        )
    )
    per_match_kind: dict[str, EvalScores] = Field(
        description=(
            "The scores per expected match kind, keyed `keyword`, `concept` or `both`, so a "
            "regression in the keyword or the vector leg shows on its own. Source: the "
            "server. Do not read a kind that is absent as scoring zero: no question of it was asked."
        )
    )


class EvalQuestionResult(CamelSchema):
    """What one question got back in a run, and how it scored."""

    model_config = ConfigDict(json_schema_extra={"examples": _EXAMPLE_EVAL_RUN["results"]})

    question_key: str = Field(
        description=(
            "The stable key of the question asked, for example `r-en-01`. Source: the "
            "evaluation set. Do not read it as a library record's key."
        )
    )
    returned: list[str] = Field(
        description=(
            "The stable keys of the first ten hits search returned, best first; empty when "
            "it returned nothing. Source: the server. Do not read a key missing from here as "
            "missing from the library: only the first ten are kept."
        )
    )
    recall_at_10: float = Field(
        ge=0,
        le=1,
        description=(
            "This question's share of expected records found in the first ten hits, from 0 "
            "to 1; a question with no answer scores 1 only when nothing came back. Source: "
            "the server. Do not read 1 as every hit being relevant."
        ),
    )
    mrr: float = Field(
        ge=0,
        le=1,
        description=(
            "The reciprocal rank of this question's first expected record, from 0 (not "
            "found) to 1 (first): 0.5 means it came second. Source: the server. Do not read "
            "it as how many expected records were found."
        ),
    )


class EvalQuestionInput(WriteBody):
    """`POST /eval/questions`: one labelled question. A field the schema does not name is
    refused, never dropped."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "key": "r-sv-17",
                    "lang": "sv",
                    "question": "kostnader och avgifter före tjänsten",
                    "expected": ["obl-costs-charges"],
                    "matchKind": "concept",
                    "notes": "Swedish phrasing of the cost disclosure, won by meaning.",
                }
            ]
        }
    )

    key: str = Field(
        min_length=1,
        max_length=40,
        pattern=EVAL_KEY_PATTERN,
        description=(
            "The question's stable key, which never changes: lower-case letters, digits and "
            "hyphens, starting with a letter or digit, 1 to 40 characters, by convention "
            "`r-<language>-<number>` as in `r-sv-17`. A key already in the set answers 409 "
            "`duplicate_key`; one that breaks the pattern answers 422. Source: platform staff. "
            "Do not reuse a retired question's key: a key names one question for good."
        ),
    )
    lang: str = Field(
        description=(
            "The content language the question is asked in, as a language key: one of the "
            "library's language rows (`en`, `sv`, `da`, `nb`, `fi` on day one), read from "
            "`GET /reference/languages`. A key that names no row answers 422 `unknown_key`. "
            "Source: platform staff. Do not send a label such as `Svenska`: only the key is "
            "accepted."
        )
    )
    question: str = Field(
        min_length=1,
        max_length=settings.SEARCH_QUERY_MAX_CHARS,
        description=(
            "What a reader would type into search, exactly as asked, 1 to "
            f"{settings.SEARCH_QUERY_MAX_CHARS} characters, the most search itself accepts; "
            "longer answers 422. Source: platform staff. Do not put a bank's own text in it: "
            "the set is the platform's and is written to a file in the code repository."
        ),
    )
    expected: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        default_factory=list, max_length=settings.API_PAGE_SIZE_MAX, description=_EXPECTED
    )
    match_kind: SearchMatchKind = Field(description=_MATCH_KIND)
    as_of: date | None = Field(
        default=None,
        description=(
            "The legal date the question is asked on, as an ISO date: the version in force "
            "that day is the one expected. Absent means the sample corpus's own anchor day. "
            "Source: platform staff. Do not read it as the day the question was written."
        ),
    )
    notes: str = Field(
        default="",
        max_length=settings.SEARCH_FEEDBACK_NOTE_MAX_CHARS,
        description=(
            "Why the question is in the set and what it proves, for the next person who "
            f"reads it. At most {settings.SEARCH_FEEDBACK_NOTE_MAX_CHARS} characters; longer "
            "answers 422. Source: platform staff. Do not put a bank's own text or a client's "
            "data in it: the set is written to a file in the code repository."
        ),
    )


class EvalQuestionOut(CamelSchema):
    """One question of the evaluation set as the console shows it."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_EVAL_QUESTION]})

    id: UUID = Field(
        description=(
            "The question's identifier in this database, a UUID. Source: the server. Do not "
            "use it to name the question elsewhere: the stable `key` is what the gate's file "
            "and every run use, and the id differs in every database."
        )
    )
    key: str = Field(
        description=(
            "The question's stable key, for example `r-en-01`, which never changes and is "
            "the `id` of its line in the release gate's file. Source: platform staff. Do not "
            "read it as a library record's stable key."
        )
    )
    lang: str = Field(
        description=(
            "The content language the question is asked in, as a key of the library's "
            "language rows (`en`, `sv`, `da`, `nb`, `fi` on day one). Source: platform staff. "
            "Do not read it as the language of the records it expects: a Swedish question "
            "may expect an EU obligation."
        )
    )
    question: str = Field(
        description=(
            "What is typed into search, exactly as asked, for example `FFFS 2017:2`. Source: "
            "platform staff. Do not read it as a bank's question: the set is the platform's own."
        )
    )
    expected: list[str] = Field(description=_EXPECTED)
    match_kind: SearchMatchKind = Field(description=_MATCH_KIND)
    as_of: date | None = Field(
        description=(
            "The legal date the question is asked on, or null for the sample corpus's own "
            "anchor day. Source: platform staff. Do not read it as the day the question was "
            "written."
        )
    )
    notes: str = Field(
        description=(
            "Why the question is in the set and what it proves; empty when nobody wrote why. "
            "Source: platform staff. Do not read an empty note as a question nobody checked."
        )
    )
    active: bool = Field(
        description=(
            "True while the question belongs to the set; false once it has been retired, "
            "which keeps it here for the record but leaves it out of every run and out of "
            "the file the gate reads. Source: platform staff. Do not read false as the "
            "question having failed."
        )
    )
    in_gate: bool = Field(
        description=(
            "True when the release gate that built this deployment scores the question: its "
            "key is a line of `backend/eval/retrieval.jsonl` in this build. False for a "
            "question added in the console and not yet written to that file with the "
            "dump_eval_questions command and shipped: it is kept, and scored by the "
            "record_eval_run command, but a drop on it fails no build yet. Source: the "
            "server. Do not read true as the question passing."
        )
    )


class EvalQuestionPage(CamelSchema):
    """`{items, total}` with `limit` and `offset` (playbook 10)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_EXAMPLE_EVAL_QUESTION], "total": 53}]})

    items: list[EvalQuestionOut] = Field(
        description=(
            "The questions on this page, ordered by key, retired ones included. An empty "
            "list is a 200 and means the set holds no question yet. Source: platform staff "
            "and the gate's file. Do not read a short page as the end unless `total` agrees."
        )
    )
    total: int = Field(
        description=(
            "How many questions the set holds in total, retired ones included; use it to "
            "size a pager. Source: the server. Do not read it as how many are on this page."
        )
    )


class EvalRunOut(CamelSchema):
    """One recorded run of the evaluation set: which chain, the scores, and each answer."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_EVAL_RUN]})

    id: UUID = Field(
        description=(
            "The run's identifier, a UUID, which the audit row of the run names too. Source: "
            "the server. Do not read its order as the order of the runs: use `runAt`."
        )
    )
    run_at: datetime = Field(
        description=(
            "When the run was recorded, as an ISO 8601 date-time in UTC. Source: the server. "
            "Do not read it as when the questions were last changed."
        )
    )
    config: EvalRunConfig = Field(
        description=(
            "Which retrieval chain the run scored, and over how many questions. Source: the "
            "server. Do not compare two runs whose chains differ as if only search changed."
        )
    )
    metrics: EvalRunMetrics = Field(
        description=(
            "The run's scores overall, per language and per match kind. Source: the server. "
            "Do not read them as the release gate's verdict, which is in CI against its baseline."
        )
    )
    results: list[EvalQuestionResult] = Field(
        description=(
            "One entry per question asked, in the order asked: what came back and how it "
            "scored. Source: the server. Do not read a question here as still active: one "
            "retired since stays here, as it ran."
        )
    )


class EvalRunPage(CamelSchema):
    """`{items, total}` with `limit` and `offset` (playbook 10)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_EXAMPLE_EVAL_RUN], "total": 1}]})

    items: list[EvalRunOut] = Field(
        description=(
            "The runs on this page, newest first. An empty list is a 200 and means no run "
            "has been recorded yet. Source: the server. Do not read an empty list as search "
            "being unscored: the release gate scores it in CI either way."
        )
    )
    total: int = Field(
        description=(
            "How many runs are recorded in total; use it to size a pager. Source: the server. "
            "Do not read it as how many are on this page."
        )
    )
