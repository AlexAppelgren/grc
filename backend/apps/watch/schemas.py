"""Request and response schemas of the watch app: camelCase through CamelSchema, app-prefixed
class names where a shape is specific to this app (playbook 4.1).

Plain Pydantic, never `ModelSchema`: this contract references no Django model, so it lands
beside the watch models rather than behind them.

A write takes a vocabulary **key** (`changeType`, `flags`, `kind`, `suggestedUrgency`) and
a read answers `{key, kind, label}`: the client never string-matches a phrase, and a tone
is nobody's to send (playbook 15, NFR-03). `Literal` carries the kinds that stay in code —
`change_status`, `check_status`, `origin_type`, a source's cadence — so no enum class is
added for a shape the caller only names.

Every property below carries a description saying what the fact means to a bank, which
zone it comes from and what a reader must not conclude from it (Alex's API rule,
2026-09-20). Two zones appear in these descriptions and they never mix:

- **Library.** Sourced public facts shared by every bank: the source registry, the change,
  its timeline, its pages, its classification and its suggested obligation links. They
  change only through the watch door (`apps/watch/write.py`) or an approved proposal.
- **The bank's own zone.** Everything under `case`: the bank's copy of the "So what?",
  its confirmation, its owner and its decision about a suggested link. Those rows carry a
  `tenant_id` under row-level security, never leave the bank, and are invisible to bleqq,
  to every other bank and to every model endpoint (NFR-01, NFR-04, D-07).

The shapes the two lists answer extend `LibraryResponse` rather than `CamelSchema`: the
server builds them from plain values and never from an ORM object, and that base is the
one that answers a validated instance as it is instead of walking every field of every
nested object through Ninja's Django getter, which was most of a full page's server time
(NFR-02, measured 2026-09-19 and again 2026-09-21). The aliases and the published contract
are identical either way.

Limits, in words as well as in the keywords: every list here pages at 20 by default and
100 at most, and a `limit` above the maximum answers 422 rather than being clamped
(`apps/shared/schemas.py:PageQuery`). No record in this app is versioned in R1, so no
write here takes `If-Match`; the case's own concurrency arrives with the rest of CAS-08 in
chunk 9. The agent writes (`POST /changes`, its documents, its events, its obligation
links and the source check) take an `Idempotency-Key` header because an agent retries;
`POST /changes` is additionally idempotent on `stableKey` (AC-WAT1). Nothing in this app
takes a passkey step-up: no route here approves, signs off, exports or creates a key.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Literal

from django.conf import settings
from ninja import Field
from pydantic import ConfigDict, HttpUrl
from pydantic.json_schema import JsonDict

from apps.governance.schemas import AiCitation
from apps.library.schemas import LibraryRef, LibraryResponse
from apps.shared.schemas import CamelSchema, PageQuery, WriteBody

__all__ = ["CamelSchema"]

CheckFrequency = Literal["daily", "weekly", "monthly"]
CheckStatus = Literal["ok", "failed"]
SourceCheckKind = Literal["sweep", "recheck"]
RecheckSubject = Literal["instrument", "provision", "obligation"]
ChangeStatus = Literal["active", "superseded", "withdrawn"]
DatePrecision = Literal["day", "month", "quarter", "year"]
Origin = Literal["agent", "user"]
CaseCategory = Literal["new", "assigned", "assessing", "implementing", "signoff", "closed", "dismissed"]
FeedTab = Literal["all", "new", "assigned", "assessing", "implementing", "signoff", "closed", "dismissed"]
FootprintFilter = Literal["in", "all", "watched"]
CaseLinkDecision = Literal["accepted", "removed"]

# A label a person reads, a summary a person reads, and the most obligations one change
# may be linked to in a single call. Lengths, not thresholds: they bound a column or a
# request body, not a decision.
LABEL_MAX = 300
TEXT_MAX = 4000
KEY_MAX = 80
LINKS_MAX = 200
# The longest `q` a feed accepts: a phrase to look for, never a document. It is a bank's
# own search phrase, so it is tenant content and never reaches a log (playbook 4.7).
QUERY_MAX = 200

# ---------------------------------------------------------------------------------------
# The examples more than one schema shows, named once so a page and its row cannot drift
# apart. Every value is the prototype's own data (a Swedish supervisor, an FI reform, an
# FFFS instrument), never a real customer's.
# ---------------------------------------------------------------------------------------
SOURCE_EXAMPLE: JsonDict = {
    "id": "0f6d2f20-6d7a-4a7c-9a5e-4a2f8a0f1c31",
    "name": "fi.se",
    "url": "https://www.fi.se/",
    "kind": {"key": "authority_site", "kind": None, "label": "Authority website"},
    "authorityId": "3a1c94c2-3f41-4f0e-9a4e-5b2a1d0c7e11",
    "checkFrequency": "weekly",
    "active": True,
}
FACT_EXAMPLE: JsonDict = {
    "ref": {"key": "advice_perimeter", "kind": None, "label": "Advice perimeter"},
    "confidence": 0.74,
    "suggested": True,
}
CHANGE_TYPE_FACT_EXAMPLE: JsonDict = {
    "ref": {"key": "adopted", "kind": "adopted", "label": "Adopted"},
    "confidence": 0.91,
    "suggested": True,
}
TERM_FACT_EXAMPLE: JsonDict = {
    "ref": {"key": "securities", "kind": None, "label": "Securities"},
    "confidence": None,
    "suggested": False,
}
EVENT_EXAMPLE: JsonDict = {
    "id": "1c8d5e02-7a94-4b61-83f2-6e0a4d9b3c15",
    "label": "Consultation closed",
    "eventDate": "2026-06-01",
    "datePrecision": "day",
    "occurred": True,
    "sortOrder": 1,
    "sourceUrl": "https://www.fi.se/en/published/consultations/2026/",
}
DOCUMENT_EXAMPLE: JsonDict = {
    "id": "e2b9a071-4c35-4d68-9b1f-8a0c3e5d7b24",
    "url": "https://www.fi.se/en/published/news/2026/reporting/",
    "title": "FI adopts amended rules on paying for investment research",
    "publisher": "Finansinspektionen",
    "fetchedAt": "2026-09-16T06:02:00Z",
    "isPrimary": True,
    "isDuplicate": False,
    "riskFlags": [],
}
OBLIGATION_LINK_EXAMPLE: JsonDict = {
    "obligationId": "7c1f0b3e-52a4-4f9e-8a21-6d4b2c0a9e17",
    "title": "Assess the quality of investment research paid for",
    "instrumentShortName": "FFFS 2017:2",
    "refLabel": "11 kap. 4 §",
    "origin": "agent",
    "confidence": 0.82,
    "confirmed": False,
}
LINK_DECISION_EXAMPLE: JsonDict = {
    "obligationId": "7c1f0b3e-52a4-4f9e-8a21-6d4b2c0a9e17",
    "decision": "accepted",
    "decidedAt": "2026-09-17T09:12:00Z",
}
CASE_EXAMPLE: JsonDict = {
    "id": "9d0b5a3c-6e14-4f27-8c93-5a1e7b0d2f46",
    "category": "new",
    "urgency": {"key": "act_now", "kind": None, "label": "Act now"},
    "urgencyConfirmed": False,
    "ownerId": None,
    "footprintMatch": True,
    "soWhatText": "Teams that pay for external research should confirm that documented criteria exist.",
    "soWhatConfirmed": False,
    "soWhatConfirmedAt": None,
    "obligationDecisions": [],
    "allowedTransitions": [],
}
CHANGE_ROW_EXAMPLE: JsonDict = {
    "id": "c3a6e1f0-7b42-4d8e-95a1-2f0b6c8d4e19",
    "stableKey": "chg-fi-2026-research-payments",
    "title": "FI adopts amended rules on paying for investment research",
    "changeType": CHANGE_TYPE_FACT_EXAMPLE,
    "authorityLabel": "Finansinspektionen",
    "authorityId": "3a1c94c2-3f41-4f0e-9a4e-5b2a1d0c7e11",
    "publishedOn": "2026-09-15",
    "publishedPrecision": "day",
    "keyDate": "2026-10-01",
    "keyDatePrecision": "day",
    "keyDateLabel": "In force",
    "status": "active",
    "flags": [FACT_EXAMPLE],
    "terms": [TERM_FACT_EXAMPLE],
    "suggestedUrgency": {"key": "act_now", "kind": None, "label": "Act now"},
    "inFootprint": True,
    "firstSeenAt": "2026-09-16T06:02:00Z",
    "case": CASE_EXAMPLE,
}
CONSOLE_ROW_EXAMPLE: JsonDict = {
    "id": "c3a6e1f0-7b42-4d8e-95a1-2f0b6c8d4e19",
    "stableKey": "chg-fi-2026-research-payments",
    "title": "FI adopts amended rules on paying for investment research",
    "changeType": CHANGE_TYPE_FACT_EXAMPLE,
    "authorityLabel": "Finansinspektionen",
    "authorityId": "3a1c94c2-3f41-4f0e-9a4e-5b2a1d0c7e11",
    "publishedOn": "2026-09-15",
    "publishedPrecision": "day",
    "status": "active",
    "flags": [FACT_EXAMPLE],
    "terms": [],
    "obligations": [OBLIGATION_LINK_EXAMPLE],
    "unconfirmedCount": 2,
    "firstSeenAt": "2026-09-16T06:02:00Z",
}
# The library record a write answers, and the change page built from it. Named here rather
# than written out twice, so the page and the record it extends cannot drift apart: the page
# differs in exactly the four members below and a reader can see which.
CHANGE_EXAMPLE: JsonDict = {
    "id": "c3a6e1f0-7b42-4d8e-95a1-2f0b6c8d4e19",
    "stableKey": "chg-fi-2026-research-payments",
    "title": "FI adopts amended rules on paying for investment research",
    "changeType": {"key": "adopted", "kind": "adopted", "label": "Adopted"},
    "authorityLabel": "Finansinspektionen",
    "authorityId": "3a1c94c2-3f41-4f0e-9a4e-5b2a1d0c7e11",
    "publishedOn": "2026-09-15",
    "publishedPrecision": "day",
    "summary": "FI's board decided on 15 September 2026 to amend three regulations in the securities area.",
    "soWhatDraft": "Teams that pay for external research should confirm that documented criteria exist.",
    "suggestedUrgency": {"key": "act_now", "kind": None, "label": "Act now"},
    "keyDate": "2026-10-01",
    "keyDatePrecision": "day",
    "keyDateLabel": "In force",
    "recurrenceRule": None,
    "flags": [{"key": "advice_perimeter", "kind": None, "label": "Advice perimeter"}],
    "sourceLabel": "Finansinspektionen",
    "sourceUrl": "https://www.fi.se/",
    "status": "active",
    "terms": [{"key": "securities", "kind": None, "label": "Securities"}],
    "events": [EVENT_EXAMPLE],
    "documents": [DOCUMENT_EXAMPLE],
    "duplicateCount": 1,
    "obligations": [OBLIGATION_LINK_EXAMPLE],
    "origin": "agent",
    "model": "agent pipeline 0.4",
    "agentRunId": "5b8e1a44-9c2d-4f17-b0a3-1e7c6d5f4a21",
    "firstSeenAt": "2026-09-16T06:02:00Z",
}
CHANGE_DETAIL_EXAMPLE: JsonDict = CHANGE_EXAMPLE | {
    # The change page answers a flag and a scope term as facts, exactly as a feed row does:
    # a person judges a change here, so an agent's suggestion has to be visible as one.
    "flags": [FACT_EXAMPLE],
    "terms": [TERM_FACT_EXAMPLE],
    "inFootprint": True,
    "case": CASE_EXAMPLE,
}


# ---------------------------------------------------------------------------------------
# The sentences repeated across these schemas, so one wording cannot drift from another.
# ---------------------------------------------------------------------------------------
_VOCABULARY = (
    "The values are rows an admin manages, not a closed set: a platform admin may extend, "
    "relabel or retire one without a deploy, so read `GET /vocab/{listName}` for the live "
    "set and match on the key, never on the label."
)
_UUID = "a UUID"
_PRECISION = (
    "How exact the date beside it is, a fixed kind: `day` renders as 15 June 2026, `month` "
    "as June 2026, `quarter` as Q2 2026 and `year` as 2026. The screen formats by this and "
    "never prints a day the source did not state. Library fact."
)
_SUGGESTED = (
    "True while this is an agent's suggestion that no library editor has confirmed. The "
    "screen marks it 'Suggested by the agent'. A reader must not treat a suggested fact as "
    "checked, and a bank never confirms it: it is a library fact and confirming one needs "
    "`proposals.review` (WAT-03, PRO-01)."
)
_CONFIDENCE = (
    "How sure the agent was, 0 to 1, or null when a person set this rather than an agent. "
    "It is the model's own number and says nothing about whether the fact is right; it "
    "orders the list and nothing else."
)
# D-66: the agent that read the change writes the "So what?" and files it with the change,
# so the model behind those words is that agent's account of itself. Said in the request
# shape and in both routes' descriptions, so nobody reads it as bleqq's own measurement.
_REPORTED_BY_THE_AGENT = (
    "Reported by the agent that read the source, not measured by bleqq (D-66). In R1 every "
    "agent is bleqq's own, so this is a reporting boundary; it becomes a trust boundary the "
    "day a bank runs its own agent against this route."
)


# ---------------------------------------------------------------------------------------
# WAT-05, AUD-02, D-66: the "So what?" an agent files with the change it read
# ---------------------------------------------------------------------------------------
class WatchSoWhatInput(WriteBody):
    """The drafted “So what?” of a change, with the model and the sources behind
    it, sent on `POST /changes` or `PATCH /changes/{changeId}`.

    One object rather than a bare string, because a draft is not filed without its
    provenance: the agent that read the change writes these words and reports which model
    wrote them and what they rest on, and the write turns that report into the
    `ai_generation` row AUD-02 asks for (D-66). A call that sends words with no model, no
    version or no citation is refused rather than logged as an unattributable draft.

    Library facts only. No bank's term, name, footprint, entity, product or text may reach
    the prompt behind these words (D-07, D-32): one draft is written per change and copied
    into every bank's case, where that bank confirms or rewrites its own copy."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "text": (
                        "Teams that pay for external research should confirm that documented "
                        "quality criteria exist before the rules take effect."
                    ),
                    "model": "claude-opus-5",
                    "modelVersion": "2026-05-01",
                    "promptTemplate": "watch-sweeper/so-what/v1",
                    "promptHash": "9f2a1c7d4b8e05f3",
                    "citations": [
                        {
                            "label": "Finansinspektionen, decision memorandum FI Dnr 25-12345",
                            "url": "https://www.fi.se/en/published/news/2026/reporting/",
                        }
                    ],
                }
            ]
        }
    )

    text: str = Field(
        min_length=1,
        max_length=TEXT_MAX,
        description=(
            f"What the change means, 1 to {TEXT_MAX} characters, drawn from the change's own "
            "public facts. It is stored on the library change, copied into every bank's case "
            "and labelled AI output until a person in that bank confirms or rewrites it "
            "(WAT-05). Write it for every bank at once: it must name no bank, no footprint "
            "and no judgement of anybody's business."
        ),
        examples=["Teams that pay for external research should confirm that documented criteria exist."],
    )
    model: str = Field(
        min_length=1,
        max_length=120,
        description=(
            f"Which model wrote the text, as the provider names it, 1 to 120 characters. "
            f"{_REPORTED_BY_THE_AGENT} Required: a draft nobody can attribute to a model is "
            "not something AUD-02's log can record, so the call is refused rather than "
            "stored."
        ),
        examples=["claude-opus-5"],
    )
    model_version: str = Field(
        min_length=1,
        max_length=120,
        description=(
            "Which version of that model, 1 to 120 characters, so two drafts months apart "
            f"can be told apart. {_REPORTED_BY_THE_AGENT} Required, for the same reason as "
            "`model`."
        ),
        examples=["2026-05-01"],
    )
    prompt_template: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Which prompt produced the text, by name and version, at most 200 characters, so "
            "an odd draft can be traced to the instructions behind it. Optional. Send the "
            "name, never the prompt: bleqq stores no prompt text at all."
        ),
        examples=["watch-sweeper/so-what/v1"],
    )
    prompt_hash: str | None = Field(
        default=None,
        max_length=128,
        description=(
            "A hash of the prompt actually sent, at most 128 characters, so two calls can be "
            "compared without either prompt being kept. Optional, and the only thing about "
            "the input that is stored."
        ),
        examples=["9f2a1c7d4b8e05f3"],
    )
    citations: list[AiCitation] = Field(
        min_length=1,
        max_length=settings.AI_GENERATION_CITATIONS_MAX,
        description=(
            "The public pages the text rests on, at least one and at most "
            f"{settings.AI_GENERATION_CITATIONS_MAX}; more answers 422 naming the field. At "
            "least one, because a draft a reader cannot check against a source is not "
            "something to put in front of every bank. Every citation is a public page: no "
            "bank's own record is ever cited, because nothing from a bank's zone reaches the "
            "prompt (NFR-04, D-07)."
        ),
    )


# ---------------------------------------------------------------------------------------
# Sources and the coverage log (WAT-01)
# ---------------------------------------------------------------------------------------
class WatchSourceOut(CamelSchema):
    """A place bleqq's agents check for new regulation. Library: every bank sees the same
    registry, and it answers how we know a reform was not missed."""

    model_config = ConfigDict(json_schema_extra={"examples": [SOURCE_EXAMPLE]})

    id: uuid.UUID = Field(
        description=(
            "The source's identifier in the shared library. Stable for as long as the source "
            "exists; it is not the publisher's own identifier and means nothing outside bleqq."
        ),
        examples=["0f6d2f20-6d7a-4a7c-9a5e-4a2f8a0f1c31"],
    )
    name: str = Field(
        description=(
            "What the source is called in the registry, unique across the library so a run "
            "can name the source it checked without an id. A person's label, not the "
            "publisher's legal name."
        ),
        examples=["fi.se", "eur-lex.europa.eu"],
    )
    url: str | None = Field(
        description=(
            "The page the agents fetch, as a URL of at most 2083 characters. Null for a "
            "source that is not one address — the open web sweep has none. Never a page behind "
            "a login: every source is public."
        ),
        examples=["https://www.fi.se/"],
    )
    kind: LibraryRef = Field(
        description=(
            "What kind of place this is, as `{key, kind, label}` from the `source_kind` "
            "library vocabulary. The values are rows a platform admin may extend without a "
            "deploy; seeded on day one are `authority_site` (the publisher's own site), "
            "`legal_database` (consolidated texts such as riksdagen.se and EUR-Lex), "
            "`open_web_sweep` (a search across the open web for anything the registered "
            "sources missed) and `tenant_private` (a source one bank follows, whose findings "
            "never enter the shared library; R3). The `kind` member is null for every row of "
            "this list: it carries no sub-kind."
        )
    )
    authority_id: uuid.UUID | None = Field(
        description=(
            "The authority that publishes here, as a UUID, when the source is one "
            "authority's. Null for a legal database or an open-web sweep, which carry no single "
            "publisher. A reader must not infer a change's jurisdiction from this: a change "
            "takes its jurisdiction from its own authority (FP-04)."
        ),
        examples=["3a1c94c2-3f41-4f0e-9a4e-5b2a1d0c7e11"],
    )
    check_frequency: CheckFrequency = Field(
        description=(
            "How often the source is meant to be checked, a fixed kind the scheduler and the "
            "stale rule branch on: `daily`, `weekly` or `monthly`. It is the cadence we "
            "promise, not a record of what happened — `GET /sources/coverage` says that."
        ),
        examples=["weekly"],
    )
    active: bool = Field(
        description=(
            "Whether the source is checked automatically. False is a source that is "
            "registered and deliberately left alone — how a standards publisher is seeded "
            "until its terms allow an automated check (WAT-07, D-45). False does not mean "
            "the source is broken; a failed check shows in the coverage log instead."
        ),
        examples=[True],
    )


class WatchSourceInput(WriteBody):
    """`POST /sources` (WAT-01): a library editor registers a place to watch. Library
    write, so `sources.manage` and a person's session only — no API key scope registers a
    source. No step-up and no `If-Match`: the registry carries no version in R1."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Finansinspektionen news",
                    "url": "https://www.fi.se/en/published/news/",
                    "kind": "authority_site",
                    "authorityId": "3a1c94c2-3f41-4f0e-9a4e-5b2a1d0c7e11",
                    "checkFrequency": "daily",
                }
            ]
        }
    )

    name: str = Field(
        min_length=1,
        max_length=LABEL_MAX,
        description=(
            f"What to call the source, 1 to {LABEL_MAX} characters and unique across the "
            "library. A name already taken answers 409; the registry is shared, so the name "
            "one editor picks is the name every bank reads."
        ),
        examples=["Finansinspektionen news"],
    )
    url: HttpUrl | None = Field(
        default=None,
        description=(
            "The public page to fetch, http or https, at most 2083 characters, validated as a "
            "URL before anything is stored. Omit it for a source that is not one address, such "
            "as an open-web sweep."
        ),
        examples=["https://www.fi.se/en/published/news/"],
    )
    kind: str = Field(
        min_length=1,
        max_length=KEY_MAX,
        description=(
            f"The key of a row of the `source_kind` library vocabulary, at most {KEY_MAX} "
            "characters and never a label: `authority_site`, `legal_database`, `open_web_sweep` "
            "or `tenant_private` are seeded, and an admin may add more without a deploy. A key "
            "the list does not hold answers 422 `unknown_key` with the valid keys listed "
            "(AC-WAT2)."
        ),
        examples=["authority_site"],
    )
    authority_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "The authority that publishes here, as a UUID, when there is exactly one. Null is "
            "the normal answer for a legal database or a sweep and is not a gap to fill. An id "
            "the authority list does not hold answers 422 `unknown_key`."
        ),
        examples=["3a1c94c2-3f41-4f0e-9a4e-5b2a1d0c7e11"],
    )
    check_frequency: CheckFrequency = Field(
        default="daily",
        description=(
            "How often to check it: `daily`, `weekly` or `monthly`, a fixed kind. Defaults to "
            "`daily`. The value the stale rule measures the coverage log against."
        ),
        examples=["daily"],
    )


class WatchSourcePatch(WriteBody):
    """`PATCH /sources/{sourceId}` (WAT-01): what a library editor may move on a registered
    source. The name and the kind are not here: a source's identity does not change, and a
    different place to watch is a different source."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"checkFrequency": "weekly", "active": False}]})

    url: HttpUrl | None = Field(
        default=None,
        description=(
            "A new address for the same source, as a URL of at most 2083 characters, when the "
            "publisher moves the page. Omit to leave it alone."
        ),
        examples=["https://www.fi.se/en/published/news/"],
    )
    check_frequency: CheckFrequency | None = Field(
        default=None,
        description="A new cadence: `daily`, `weekly` or `monthly`. Omit to leave it alone.",
        examples=["weekly"],
    )
    active: bool | None = Field(
        default=None,
        description=(
            "Switch automated checks off or on. Switching off keeps every check already "
            "logged: the coverage log is never rewritten, so a reader must not read an "
            "inactive source as one that was never checked."
        ),
        examples=[False],
    )


COVERAGE_EXAMPLE: JsonDict = {
    "source": SOURCE_EXAMPLE,
    "lastCheckedAt": "2026-09-16T06:02:00Z",
    "lastStatus": "ok",
    "lastError": None,
    "overdue": False,
}


class WatchSourceCoverage(CamelSchema):
    """One row of the coverage log per source: when it was last checked, with what result,
    and whether it is overdue against its cadence and `SOURCE_STALE_AFTER_CHECKS`. Library:
    the same answer for every bank, and the evidence behind "we missed nothing"."""

    model_config = ConfigDict(json_schema_extra={"examples": [COVERAGE_EXAMPLE]})

    source: WatchSourceOut = Field(description="The source this row is about, as `GET /sources` answers it.")
    last_checked_at: datetime.datetime | None = Field(
        description=(
            "When the most recent sweep of this source finished, as a UTC date-time. Null "
            "means no sweep has ever been logged, which is not the same as one that failed."
        ),
        examples=["2026-09-16T06:02:00Z"],
    )
    last_status: Literal["ok", "failed", "never"] = Field(
        description=(
            "How the most recent check ended, computed by the server from the coverage log. A "
            "fixed kind with three members: `ok` (the source answered and the run read it), "
            "`failed` (the fetch or the parse failed; `lastError` says how) and `never` (no "
            "check has been logged at all). `ok` with no new items is still `ok` — finding "
            "nothing is a result."
        ),
        examples=["ok"],
    )
    last_error: str | None = Field(
        description=(
            "What went wrong on the last check, when it failed: the agent's own short message "
            f"of at most {TEXT_MAX} characters, never a stack trace and never fetched page "
            "content. Null when the last check succeeded."
        ),
        examples=["502 from the publisher after three retries"],
    )
    overdue: bool = Field(
        description=(
            "Computed by the server: true when the source has gone longer than its cadence "
            "without a successful check, or has failed more times in a row than "
            "`SOURCE_STALE_AFTER_CHECKS` allows (a setting, default 1). The console shows it "
            "as stale. True does not mean a change was missed; it means we cannot yet say "
            "one was not."
        ),
        examples=[False],
    )


class WatchSourceCheckInput(WriteBody):
    """`POST /agent-runs/{runId}/source-checks` (WAT-01): one line of the coverage log,
    written by an agent's key holding `sources:write`. A failed check carries an error and
    no items, which `watch/sources.py:record_check` enforces. Send an `Idempotency-Key`:
    an agent retries, and a line of a log is cheap to repeat."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "sourceName": "fi.se",
                    "status": "ok",
                    "itemsFound": 3,
                    "checkedAt": "2026-09-16T06:02:00Z",
                },
                {
                    "sourceName": "eur-lex.europa.eu",
                    "status": "failed",
                    "error": "502 from the publisher after three retries",
                },
                {
                    "sourceName": "fi.se",
                    "status": "ok",
                    "kind": "recheck",
                    "subjectType": "obligation",
                    "subjectId": "7c1f0b3e-52a4-4f9e-8a21-6d4b2c0a9e17",
                },
            ]
        }
    )

    source_name: str = Field(
        min_length=1,
        max_length=LABEL_MAX,
        description=(
            f"The registered source's `name`, at most {LABEL_MAX} characters, which an agent "
            "reads from `GET /sources` at run start. A name the registry does not hold answers "
            "422 `unknown_source`: an agent never registers a source, it only reports on one."
        ),
        examples=["fi.se"],
    )
    status: CheckStatus = Field(
        description=(
            "How the check ended, a fixed kind the coverage report and the stale rule branch "
            "on: `ok` (the source answered and was read, whether or not anything was new) or "
            "`failed` (it did not). There is no third value; a check that was never attempted "
            "is simply not logged."
        ),
        examples=["ok"],
    )
    items_found: int | None = Field(
        default=None,
        ge=0,
        description=(
            "How many items the agent read on this check, its own count, a minimum of 0 and no "
            "maximum. Zero is a real and common answer. It is not a count of changes "
            "registered: several items may describe one reform and one item may describe none. "
            "Leave it out on a failed check, which is stored as 0 whatever is sent."
        ),
        examples=[3],
    )
    error: str | None = Field(
        default=None,
        max_length=TEXT_MAX,
        description=(
            f"Why a failed check failed, at most {TEXT_MAX} characters. The agent's own "
            "message: never fetched page content, never a stack trace, never a credential. "
            "Required on a failed check and refused on one that succeeded, both with "
            "`validation_error`."
        ),
        examples=["502 from the publisher after three retries"],
    )
    checked_at: datetime.datetime | None = Field(
        default=None,
        description=(
            "When the check happened, as a UTC date-time. Defaults to the moment the server "
            "records it, which is what an agent reporting as it goes should use."
        ),
        examples=["2026-09-16T06:02:00Z"],
    )
    kind: SourceCheckKind = Field(
        default="sweep",
        description=(
            "What the check was for, a fixed kind, defaulting to `sweep`: `sweep` is the look "
            "for documents the source has published that bleqq has not seen, and `recheck` is "
            "a second look at one library record this source already gave us, to see whether "
            "it still matches (AGT-01). Only sweeps decide whether a source has gone stale, "
            "because a re-check says nothing about whether the source has been read since — a "
            "run full of re-checks never makes a source look fresh."
        ),
        examples=["sweep"],
    )
    subject_type: RecheckSubject | None = Field(
        default=None,
        description=(
            "Which kind of library record a `recheck` looked at, a fixed kind: `instrument`, "
            "`provision` or `obligation`. Required together with `subjectId` when `kind` is "
            "`recheck`, and refused on a `sweep`, which looks at no one record; either pairing "
            "answers 422 `validation_error`."
        ),
        examples=["obligation"],
    )
    subject_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Which library record a `recheck` looked at, as a UUID, alongside `subjectType`. "
            "Logging the re-check changes no library record: where one has drifted from its "
            "source the correction goes through the proposal door under four eyes (PRO-01), "
            "and this line is only the evidence that the look happened."
        ),
        examples=["7c1f0b3e-52a4-4f9e-8a21-6d4b2c0a9e17"],
    )


# ---------------------------------------------------------------------------------------
# A change's timeline, documents and obligation links (WAT-02, WAT-04, AGT-07)
# ---------------------------------------------------------------------------------------
class WatchChangeEventInput(WriteBody):
    """One entry of a change's timeline, written by an agent's key with `changes:write` or
    by a library editor with `proposals.review`. Idempotency-Key applies."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "label": "Consultation closed",
                    "eventDate": "2026-06-01",
                    "datePrecision": "day",
                    "occurred": True,
                    "sortOrder": 1,
                    "sourceUrl": "https://www.fi.se/en/published/consultations/2026/",
                }
            ]
        }
    )

    label: str = Field(
        min_length=1,
        max_length=LABEL_MAX,
        description=(
            f"What happened, in the words of the source, 1 to {LABEL_MAX} characters — "
            "'Consultation closed', 'Adopted by the board', 'Transition ends'. Free text on "
            "purpose: the milestones of a reform are not a list anyone can close. It is never "
            "a status the system branches on."
        ),
        examples=["Consultation closed"],
    )
    event_date: datetime.date | None = Field(
        default=None,
        description=(
            "The legal date of this milestone, a plain date and never a timestamp. Null when "
            "the source has not stated one yet, which is normal early in a reform."
        ),
        examples=["2026-06-01"],
    )
    date_precision: DatePrecision | None = Field(default=None, description=_PRECISION, examples=["day"])
    occurred: bool = Field(
        default=False,
        description=(
            "Whether this milestone has already happened, as the source says — not as the "
            "clock says. An entry may carry a past date and still be `false` if the source "
            "has not confirmed it."
        ),
        examples=[True],
    )
    sort_order: int = Field(
        default=0,
        description=(
            "Where the entry sits in the timeline, ascending, defaulting to 0. Entries share "
            "the order the agent gave them; ties fall back to the row id so a page never "
            "repeats a row."
        ),
        examples=[1],
    )
    source_url: HttpUrl | None = Field(
        default=None,
        description=(
            "The public page that states this milestone, so a reviewer can open it, as a URL "
            "of at most 2083 characters. Null when it is the change's own source."
        ),
        examples=["https://www.fi.se/en/published/consultations/2026/"],
    )


class WatchChangeEvent(CamelSchema):
    """One entry of the timeline as every bank reads it. Library fact: the same timeline
    for everyone, with no bank's own dates in it."""

    model_config = ConfigDict(json_schema_extra={"examples": [EVENT_EXAMPLE]})

    id: uuid.UUID = Field(description="The timeline entry's identifier, used to correct it later.")
    label: str = Field(description="What happened, in the source's words (see the write shape above).", examples=["Consultation closed"])
    event_date: datetime.date | None = Field(
        description="The legal date of the milestone, or null when the source has not stated one.", examples=["2026-06-01"]
    )
    date_precision: DatePrecision | None = Field(description=_PRECISION, examples=["day"])
    occurred: bool = Field(description="Whether the source says it has happened. Not derived from today's date.", examples=[True])
    sort_order: int = Field(description="Position in the timeline, ascending.", examples=[1])
    source_url: str | None = Field(
        description="The page that states this milestone, or null when it is the change's own source.",
        examples=["https://www.fi.se/en/published/consultations/2026/"],
    )


class WatchChangeDocumentInput(WriteBody):
    """A fetched page, attached by the agent that fetched it (`changes:write`, never a
    person: a page arrives from the run that screened it, AGT-07). `riskFlags` is what
    `agents/screen.py` found in it; the content itself is untrusted and is never executed
    or rendered as HTML (playbook 11.2). Idempotency-Key applies."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "url": "https://www.fi.se/en/published/news/2026/reporting/",
                    "title": "FI adopts amended rules on paying for investment research",
                    "publisher": "Finansinspektionen",
                    "fetchedAt": "2026-09-16T06:02:00Z",
                    "contentHash": "9f2c4d0a6b1e8f37c5a90d2e4b6f8013a7c5e9d1b3f5079a2c4e6081d3f5a7c9",
                    "isPrimary": True,
                    "isDuplicate": False,
                    "riskFlags": [],
                }
            ]
        }
    )

    url: HttpUrl = Field(
        description=(
            "The page's public address, a URL of at most 2083 characters, unique per change: "
            "posting the same url again answers the page that is already there rather than "
            "adding a second row. Must be http or https."
        ),
        examples=["https://www.fi.se/en/published/news/2026/reporting/"],
    )
    title: str | None = Field(
        default=None,
        max_length=LABEL_MAX,
        description=f"The page's own headline, at most {LABEL_MAX} characters. Null when the page states none.",
        examples=["FI adopts amended rules on paying for investment research"],
    )
    publisher: str | None = Field(
        default=None,
        max_length=LABEL_MAX,
        description=(
            f"Who published the page, as the page says, at most {LABEL_MAX} characters. A "
            "label for a reader, never matched against the authority list."
        ),
        examples=["Finansinspektionen"],
    )
    fetched_at: datetime.datetime | None = Field(
        default=None,
        description="When the agent fetched it, as a UTC date-time. Null when the run did not say.",
        examples=["2026-09-16T06:02:00Z"],
    )
    content_hash: str | None = Field(
        default=None,
        max_length=128,
        description=(
            "A hash of the fetched text, at most 128 characters, so a later run can tell "
            "whether the page moved. For a standards publisher it is all we keep: the URL, "
            "the date and the hash, never a snapshot of the text (WAT-07, D-45)."
        ),
        examples=["9f2c4d0a6b1e8f37c5a90d2e4b6f8013a7c5e9d1b3f5079a2c4e6081d3f5a7c9"],
    )
    is_primary: bool = Field(
        default=False,
        description=(
            "Whether this is the page the change is chiefly about, false by default. At most "
            "one page of a change is primary: a second one answers `validation_error`."
        ),
        examples=[True],
    )
    is_duplicate: bool = Field(
        default=False,
        description=(
            "Whether this page is a second sighting of a reform already registered, false by "
            "default. True is how AC-WAT1's merge is recorded, and a page that arrives on a "
            "known `stableKey` is stored as one whatever is sent here; it does not mean the "
            "page is worthless."
        ),
        examples=[False],
    )
    risk_flags: list[str] = Field(
        default_factory=list,
        max_length=50,
        description=(
            "What the injection screen found in the fetched text (`agents/screen.py`), at most "
            "50 entries. Computed by the agent, not by a person and not by an admin: these are "
            "the screen's own findings, which is why they are strings and not a vocabulary. A "
            "flag here says the text is suspicious, never that the reform is."
        ),
        examples=[["instruction_like_text"]],
    )


class WatchChangeDocument(CamelSchema):
    """A source page of a change as every bank reads it. Library fact. The fetched text
    itself is never in this response: a reader gets the address and the hash and opens the
    publisher's own page."""

    model_config = ConfigDict(json_schema_extra={"examples": [DOCUMENT_EXAMPLE]})

    id: uuid.UUID = Field(description="The document row's identifier.")
    url: str = Field(description="The page's public address.", examples=["https://www.fi.se/en/published/news/2026/reporting/"])
    title: str | None = Field(description="The page's own headline, or null.", examples=["FI adopts amended rules on paying for investment research"])
    publisher: str | None = Field(description="Who published it, as the page says.", examples=["Finansinspektionen"])
    fetched_at: datetime.datetime | None = Field(
        description="When it was fetched, as a UTC date-time, or null when the run did not say.",
        examples=["2026-09-16T06:02:00Z"],
    )
    is_primary: bool = Field(description="Whether this is the page the change is chiefly about.", examples=[True])
    is_duplicate: bool = Field(
        description="Whether it arrived as a second sighting of a reform already registered (AC-WAT1).", examples=[False]
    )
    risk_flags: list[str] = Field(
        description=(
            "What the injection screen found in the fetched text. A non-empty list is a "
            "warning about the page, not about the reform, and the screen never renders the "
            "fetched text as HTML whatever this says."
        ),
        examples=[[]],
    )


class WatchObligationLinkInput(WriteBody):
    """One obligation a change affects, as an agent suggests it or a library editor sets
    it. Sent inside `POST /changes` or as the whole body of
    `PUT /changes/{changeId}/obligations`, which is capped at 200 links per call."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"obligationId": "7c1f0b3e-52a4-4f9e-8a21-6d4b2c0a9e17", "confidence": 0.82}]}
    )

    obligation_id: uuid.UUID = Field(
        description=(
            "The library obligation this change touches, as a UUID. It must already exist: a "
            "link never creates an obligation, and no key scope reaches the inventory "
            "(AC-PRO1). An unknown id answers 422 `unknown_key`."
        ),
        examples=["7c1f0b3e-52a4-4f9e-8a21-6d4b2c0a9e17"],
    )
    confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description=_CONFIDENCE + " Send it from an agent; leave it out when a person is setting the link.",
        examples=[0.82],
    )


class WatchObligationLink(LibraryResponse):
    """A link the agent suggested or a person set. `confirmed` is the library editor's
    decision; a bank's own decision lives on its case, never here (WAT-04, ruling C)."""

    model_config = ConfigDict(json_schema_extra={"examples": [OBLIGATION_LINK_EXAMPLE]})

    obligation_id: uuid.UUID = Field(
        description="The library obligation this change affects, as a UUID.",
        examples=["7c1f0b3e-52a4-4f9e-8a21-6d4b2c0a9e17"],
    )
    title: str = Field(
        description="The obligation's title in the reader's language, from the library.",
        examples=["Assess the quality of investment research paid for"],
    )
    instrument_short_name: str = Field(
        description="The short name of the instrument the obligation sits in, from the library.", examples=["FFFS 2017:2"]
    )
    ref_label: str = Field(
        description="Where in that instrument the obligation sits, as the instrument numbers it.", examples=["11 kap. 4 §"]
    )
    origin: Origin = Field(
        description=(
            "Who first drew this link, a fixed kind: `agent` (a run suggested it) or `user` (a "
            "library editor added it by hand). It never changes afterwards, so `agent` on a "
            "confirmed link means an agent found it and a person agreed."
        ),
        examples=["agent"],
    )
    confidence: float | None = Field(description=_CONFIDENCE, examples=[0.82])
    confirmed: bool = Field(
        description=(
            "Whether a library editor has confirmed the link for the shared library. False is "
            "a suggestion. A reader must not read `false` as 'not related' — only a bank's own "
            "`removed` decision on its case says that, and it changes no library row."
        ),
        examples=[False],
    )


# ---------------------------------------------------------------------------------------
# The change itself (WAT-02, WAT-03)
# ---------------------------------------------------------------------------------------
class WatchChangeInput(WriteBody):
    """`POST /changes` (AC-WAT1): `stableKey` makes the call idempotent, so posting a known
    key merges the new pages as duplicates and returns the change that exists. Written by
    an agent's key with `changes:write` or a library editor with `proposals.review`; send
    an `Idempotency-Key` as well, because a retry must not create a second row."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "stableKey": "chg-fi-2026-research-payments",
                    "title": "FI adopts amended rules on paying for investment research",
                    "changeType": "adopted",
                    "authorityLabel": "Finansinspektionen",
                    "authorityCode": "fi",
                    "publishedOn": "2026-09-15",
                    "publishedPrecision": "day",
                    "summary": (
                        "FI's board decided on 15 September 2026 to amend three regulations in the "
                        "securities area following changed EU rules."
                    ),
                    "suggestedUrgency": "act_now",
                    "keyDate": "2026-10-01",
                    "keyDatePrecision": "day",
                    "keyDateLabel": "In force",
                    "flags": ["advice_perimeter"],
                    "sourceLabel": "Finansinspektionen",
                    "sourceUrl": "https://www.fi.se/",
                    "events": [{"label": "Consultation closed", "eventDate": "2026-06-01", "datePrecision": "day", "occurred": True, "sortOrder": 1}],
                    "documents": [{"url": "https://www.fi.se/en/published/news/2026/reporting/", "isPrimary": True}],
                    "obligationLinks": [{"obligationId": "7c1f0b3e-52a4-4f9e-8a21-6d4b2c0a9e17", "confidence": 0.82}],
                    "agentRunId": "5b8e1a44-9c2d-4f17-b0a3-1e7c6d5f4a21",
                    "model": "agent pipeline 0.4",
                    "soWhat": {
                        "text": "Teams that pay for external research should confirm that documented criteria exist.",
                        "model": "claude-opus-5",
                        "modelVersion": "2026-05-01",
                        "promptTemplate": "watch-sweeper/so-what/v1",
                        "promptHash": "9f2a1c7d4b8e05f3",
                        "citations": [
                            {
                                "label": "Finansinspektionen, decision memorandum FI Dnr 25-12345",
                                "url": "https://www.fi.se/en/published/news/2026/reporting/",
                            }
                        ],
                    },
                }
            ]
        }
    )

    stable_key: str = Field(
        min_length=1,
        max_length=200,
        description=(
            "The reform's permanent key, at most 200 characters, chosen by the agent and never "
            "changed afterwards (playbook 4.3). It is the merge key: posting a key the library "
            "already holds adds the new pages to that change and answers 200 with it, instead "
            "of creating a second row (AC-WAT1). Two reforms never share a key."
        ),
        examples=["chg-fi-2026-research-payments"],
    )
    title: str = Field(
        min_length=1,
        max_length=LABEL_MAX,
        description=f"What the reform is called, 1 to {LABEL_MAX} characters, in the source's own words.",
        examples=["FI adopts amended rules on paying for investment research"],
    )
    change_type: str = Field(
        min_length=1,
        max_length=KEY_MAX,
        description=(
            f"The key of a row of the `change_type` library vocabulary, at most {KEY_MAX} "
            "characters and never a label. Seeded on "
            "day one: `proposal` (a draft rule or final report proposed for adoption; its dates "
            "are proposed, not decided), `adopted` (decided, application still ahead), "
            "`supervision` (surveys, thematic reviews, statements — no new rule), `enforcement` "
            "(a decision against a named firm) and `recurring_date` (a date that returns, such "
            "as a rate fixing). A platform admin may add rows without a deploy; each row carries "
            "a `change_lifecycle_kind` the rules branch on. An unknown key answers 422 "
            f"`unknown_key` with the valid keys (AC-WAT2). {_VOCABULARY}"
        ),
        examples=["adopted"],
    )
    authority_label: str = Field(
        min_length=1,
        max_length=LABEL_MAX,
        description=(
            f"Who issued the change, as the source writes it, 1 to {LABEL_MAX} characters. "
            "Always present, even when the authority is not in the library's authority list "
            "yet, so a reader always sees who is behind a change."
        ),
        examples=["Finansinspektionen"],
    )
    authority_code: str | None = Field(
        default=None,
        max_length=KEY_MAX,
        description=(
            f"The key of the library authority, at most {KEY_MAX} characters, when the agent "
            "recognised it. Null means the authority is unknown to the library, and a change "
            "with no authority is not restricted by jurisdiction — it reaches every bank's feed "
            "(FP-S15, D-29). A key the authority list does not hold answers 422 `unknown_key`."
        ),
        examples=["fi"],
    )
    published_on: datetime.date | None = Field(
        default=None,
        description=(
            "The date the source published this, as a plain calendar date (`2026-09-15`) and "
            "never a timestamp, with `publishedPrecision` saying how exact it is. Null when the "
            "source states none."
        ),
        examples=["2026-09-15"],
    )
    published_precision: DatePrecision | None = Field(default=None, description=_PRECISION, examples=["day"])
    summary: str = Field(
        min_length=1,
        max_length=TEXT_MAX,
        description=(
            f"What the change says, 1 to {TEXT_MAX} characters, drawn from the public source. "
            "Facts only: it is a library row every bank reads, so it must contain no bank's "
            "name, footprint or judgement."
        ),
        examples=["FI's board decided on 15 September 2026 to amend three regulations in the securities area."],
    )
    so_what: WatchSoWhatInput | None = Field(
        default=None,
        description=(
            "The drafted “So what?” this run wrote for the change, with the model "
            "and the sources behind it (WAT-05, AUD-02, D-66). Optional: a run that only "
            "sighted the reform, and a library editor filing one by hand, send none and the "
            "change carries no draft until a run files one through "
            "`PATCH /changes/{changeId}`. Sending it stores the words on the shared change, "
            "copies them unconfirmed into every bank's case and writes one row in the AI "
            "output log. Words with no model, no version or no citation answer 422."
        ),
    )
    suggested_urgency: str | None = Field(
        default=None,
        max_length=KEY_MAX,
        description=(
            f"The key of a row of the `urgency` library vocabulary, at most {KEY_MAX} "
            "characters, the agent's suggestion for "
            "how soon this needs work. Seeded on day one, in severity order: `act_now` "
            "(something must change within weeks), `within_3_months` (work must start this "
            "quarter), `six_months_plus` (plan it, no rush), `monitor` (nothing to do yet) and "
            "`no_action` (noted, nothing changes). An admin may add rows. A suggestion, not a "
            "decision: each bank triages its own case and may disagree. The row's tone is the "
            f"row's, never sent here and never chosen by a caller (NFR-03). {_VOCABULARY}"
        ),
        examples=["act_now"],
    )
    key_date: datetime.date | None = Field(
        default=None,
        description=(
            "The one date that drives 'coming up': in force, applies, transition ends. Null "
            "when no date is known yet. The roadmap and the feed order read this date."
        ),
        examples=["2026-10-01"],
    )
    key_date_precision: DatePrecision | None = Field(default=None, description=_PRECISION, examples=["day"])
    key_date_label: str | None = Field(
        default=None,
        max_length=LABEL_MAX,
        description=(
            f"What that date is, in the source's words, at most {LABEL_MAX} characters: "
            "'In force', 'Applies', 'Transition ends'."
        ),
        examples=["In force"],
    )
    recurrence_rule: str | None = Field(
        default=None,
        max_length=LABEL_MAX,
        description=(
            f"For a date that returns (a quarterly rate fixing), how it returns, in words, at "
            f"most {LABEL_MAX} characters. Null for a one-off reform."
        ),
        examples=["Every 30 November"],
    )
    flags: list[str] = Field(
        default_factory=list,
        max_length=50,
        description=(
            "Keys of rows of the `flag` library vocabulary, at most 50, marking what a change "
            "is about across subject areas. Seeded on day one: `ai` (artificial intelligence in "
            "financial services, including the AI Act) and `advice_perimeter` (the change moves "
            "the line between advice and non-advised services). An admin may add rows without a "
            "deploy, which is why this is a list of keys and never a `text[]` of phrases "
            "(INPUT_DELTAS §1). An unknown key answers 422 `unknown_key` with the valid keys. "
            f"{_VOCABULARY}"
        ),
        examples=[["advice_perimeter"]],
    )
    source_label: str = Field(
        min_length=1,
        max_length=LABEL_MAX,
        description=f"Where the change was found, in words a reader recognises, 1 to {LABEL_MAX} characters.",
        examples=["Finansinspektionen"],
    )
    source_url: HttpUrl = Field(
        description=(
            "The public page the change was found on, so a reviewer can open it: a URL of at "
            "most 2083 characters. Required, because a change always says where it came from."
        ),
        examples=["https://www.fi.se/"],
    )
    term_ids: list[uuid.UUID] = Field(
        default_factory=list,
        max_length=100,
        description=(
            "Taxonomy terms that scope the change — its regime, product or service — each a "
            "UUID, at most 100 of them. Terms are library rows an admin may extend; the ids "
            "come from "
            "`GET /taxonomy/terms`, which an agent reads at run start. Every change needs at "
            "least one regime term or the call answers 422 `regime_required`, and a standard's "
            "term is accepted only when the authority's jurisdiction is international, else 422 "
            "`standard_term_only_on_standards` (AC-AGT1). A term that list marks `mirrored` "
            "answers 422 `jurisdiction_term_mirrored`: a change's market comes from "
            "`authorityCode`, never from a term."
        ),
        examples=[["a4e1c07b-9d52-4f83-8b10-2c7e5a9f4d68"]],
    )
    events: list[WatchChangeEventInput] = Field(
        default_factory=list, max_length=50, description="The reform's timeline, at most 50 entries in one call."
    )
    documents: list[WatchChangeDocumentInput] = Field(
        default_factory=list, max_length=50, description="The pages the change was found on, at most 50 in one call."
    )
    obligation_links: list[WatchObligationLinkInput] = Field(
        default_factory=list,
        max_length=LINKS_MAX,
        description=f"The obligations the change affects, at most {LINKS_MAX} in one call, each a suggestion until a library editor confirms it.",
    )
    agent_run_id: uuid.UUID | None = Field(
        default=None,
        description=(
            f"The run that found this, as {_UUID}, so every library row an agent wrote points at the run "
            "that wrote it (AGT-01). Required from a key, and it must be a run that same key has "
            "open: naming none, or a closed one, answers 422 `run_not_open`, and a run of another "
            "key answers 404 `not_found`. Null when a library editor registers a change by hand."
        ),
        examples=["5b8e1a44-9c2d-4f17-b0a3-1e7c6d5f4a21"],
    )
    model: str | None = Field(
        default=None,
        max_length=120,
        description=(
            "The model and pipeline version behind the agent's reading of the source, at most "
            "120 characters, recorded so AI output stays labelled (WAT-03, AUD-02)."
        ),
        examples=["agent pipeline 0.4"],
    )


class WatchChangePatch(WriteBody):
    """`PATCH /changes/{changeId}` (WAT-03): the library facts of a change. What a key may
    move, and that a suggestion stays a suggestion until a library editor confirms it, is
    `watch/curation.py:update_change_facts`. Every field is optional; a field left out is
    left alone, and no field here is ever nulled by omission."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"keyDate": "2026-10-01", "keyDateLabel": "In force", "flags": ["advice_perimeter"]}]})

    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=LABEL_MAX,
        description=f"A corrected title, in the source's words, 1 to {LABEL_MAX} characters.",
        examples=["FI adopts amended rules on paying for investment research"],
    )
    change_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=KEY_MAX,
        description=(
            f"A key of the `change_type` library vocabulary, at most {KEY_MAX} characters (see "
            f"`POST /changes` for the keys seeded on day one). An unknown key answers 422 "
            f"`unknown_key`. {_VOCABULARY}"
        ),
        examples=["adopted"],
    )
    summary: str | None = Field(
        default=None,
        min_length=1,
        max_length=TEXT_MAX,
        description=f"A corrected summary, at most {TEXT_MAX} characters, from the public source and holding no bank's judgement.",
        examples=["FI's board decided on 15 September 2026 to amend three regulations in the securities area."],
    )
    key_date: datetime.date | None = Field(default=None, description="The date that drives 'coming up', once the source states it.", examples=["2026-10-01"])
    key_date_precision: DatePrecision | None = Field(default=None, description=_PRECISION, examples=["day"])
    key_date_label: str | None = Field(
        default=None,
        max_length=LABEL_MAX,
        description=f"What that date is, in the source's words, at most {LABEL_MAX} characters.",
        examples=["In force"],
    )
    flags: list[str] | None = Field(
        default=None,
        max_length=50,
        description="The whole set of `flag` keys for this change, replacing what is stored. Send the full set, not a delta.",
        examples=[["advice_perimeter"]],
    )
    status: ChangeStatus | None = Field(
        default=None,
        description=(
            "The reform's lifecycle stage in the library, a fixed kind: `active` (the feed "
            "shows it), `superseded` (another change replaced it, named by `supersededBy`) or "
            "`withdrawn` (the issuer took it back). A superseded or withdrawn change is never "
            "deleted and its cases stay."
        ),
        examples=["superseded"],
    )
    superseded_by: uuid.UUID | None = Field(
        default=None,
        description=(
            "The change that replaced this one, as a UUID. A change may not supersede itself; "
            "the database refuses it."
        ),
        examples=["b41d7e08-3a5c-4e92-9f16-0d8c2b7a5e43"],
    )
    term_ids: list[uuid.UUID] | None = Field(
        default=None,
        max_length=100,
        description=(
            "The whole set of taxonomy term ids for this change, each a UUID and at most 100 "
            "of them, replacing what is stored. The regime rule of AC-AGT1 applies to the new "
            "set, and a term `GET /taxonomy/terms` marks `mirrored` answers 422 "
            "`jurisdiction_term_mirrored`."
        ),
        examples=[["a4e1c07b-9d52-4f83-8b10-2c7e5a9f4d68"]],
    )
    so_what: WatchSoWhatInput | None = Field(
        default=None,
        description=(
            "A drafted “So what?” for this change, with the model and the sources "
            "behind it, replacing whatever draft is stored (WAT-05, AUD-02, D-66). Send it "
            "when the run that re-read the source can say what the change means and the "
            "change carries no draft, or a worse one; leave it out to keep what is there. "
            "Each send writes one more row in the AI output log, so the earlier draft stays "
            "on the record. Every bank whose copy is still the unedited draft is brought up "
            "to the new wording; a bank that confirmed or rewrote its own keeps it, because "
            "a bank's words are its own. Words with no model, no version or no citation "
            "answer 422."
        ),
    )


class WatchChange(CamelSchema):
    """A library record: sourced facts, shared by every tenant. No tenant judgement, no
    case and no "So what?" confirmation is here; those sit on the tenant's own case."""

    model_config = ConfigDict(json_schema_extra={"examples": [CHANGE_EXAMPLE]})

    id: uuid.UUID = Field(description="The change's identifier in the shared library.", examples=["c3a6e1f0-7b42-4d8e-95a1-2f0b6c8d4e19"])
    stable_key: str = Field(
        description="The reform's permanent key. It never changes, so it is safe to store in a filter or a report.",
        examples=["chg-fi-2026-research-payments"],
    )
    title: str = Field(
        description="What the reform is called, in the source's words.",
        examples=["FI adopts amended rules on paying for investment research"],
    )
    change_type: LibraryRef = Field(
        description=(
            "The kind of change, as `{key, kind, label}` from the `change_type` library "
            "vocabulary; the label is in the reader's language. The `kind` member is the "
            "`change_lifecycle_kind` the rules branch on. Never a phrase to match and never a "
            f"tone. {_VOCABULARY}"
        )
    )
    authority_label: str = Field(description="Who issued it, as the source writes it.", examples=["Finansinspektionen"])
    authority_id: uuid.UUID | None = Field(
        description=(
            f"The library authority, as {_UUID}, when the change names one the library knows. Null means "
            "the authority is unknown, and such a change is not restricted by jurisdiction "
            "(FP-S15, D-29) — a reader must not read null as 'not relevant to us'."
        ),
        examples=["3a1c94c2-3f41-4f0e-9a4e-5b2a1d0c7e11"],
    )
    published_on: datetime.date | None = Field(
        description=(
            "When the source published it, as a plain calendar date (`2026-09-15`) and never a "
            "timestamp, with `publishedPrecision` beside it. Null when the source states none."
        ),
        examples=["2026-09-15"],
    )
    published_precision: DatePrecision | None = Field(description=_PRECISION, examples=["day"])
    summary: str = Field(
        description="What the change says, from the public source. Library text: it holds no bank's judgement.",
        examples=["FI's board decided on 15 September 2026 to amend three regulations."],
    )
    so_what_draft: str | None = Field(
        description=(
            "The library's drafted 'So what?', written once per change from library facts "
            "only. It is AI-drafted until a person confirms it, and each bank confirms its own "
            "copy on its case — never this one (WAT-05, D-32)."
        ),
        examples=["Teams that pay for external research should confirm that documented criteria exist."],
    )
    suggested_urgency: LibraryRef | None = Field(
        description=(
            "The agent's suggested urgency as `{key, kind, label}` from the `urgency` library "
            "vocabulary, `act_now`, `within_3_months`, `six_months_plus`, `monitor` or "
            "`no_action` on day one. A suggestion for every bank; the bank's own decision is on "
            "its case. The tone follows the row's ordinal and is never in this response "
            f"(NFR-03). {_VOCABULARY}"
        )
    )
    key_date: datetime.date | None = Field(description="The date that drives 'coming up', or null when none is known.", examples=["2026-10-01"])
    key_date_precision: DatePrecision | None = Field(description=_PRECISION, examples=["day"])
    key_date_label: str | None = Field(description="What that date is, in the source's words.", examples=["In force"])
    recurrence_rule: str | None = Field(description="How a returning date returns, in words. Null for a one-off reform.", examples=[None])
    flags: list[LibraryRef] = Field(
        description=(
            "What the change is about across subject areas, as `{key, kind, label}` rows of the "
            "`flag` library vocabulary, `ai` and `advice_perimeter` on day one. An empty list "
            f"means no flag applies, not that nobody looked. {_VOCABULARY}"
        )
    )
    source_label: str = Field(description="Where the change was found, in words.", examples=["Finansinspektionen"])
    source_url: str = Field(description="The public page it was found on.", examples=["https://www.fi.se/"])
    status: ChangeStatus = Field(
        description=(
            "The reform's lifecycle stage, a fixed kind: `active`, `superseded` or `withdrawn` "
            "(see the patch shape). This is the library's status, never a bank's case status."
        ),
        examples=["active"],
    )
    terms: list[LibraryRef] = Field(
        description=(
            "The taxonomy terms that scope the change — regime, market, product, service — as "
            "`{key, kind, label}` rows of the taxonomy vocabulary, `securities`, `banking`, "
            "`payments`, `insurance`, `aml`, `tax`, `data_protection` and `ai_ict` among the "
            "regimes seeded on day one. A term's `kind` is null: its dimension is its kind. This "
            "is what the footprint is matched against; it is not a bank's footprint. "
            f"{_VOCABULARY}"
        )
    )
    events: list[WatchChangeEvent] = Field(description="The reform's timeline, in `sortOrder`.")
    documents: list[WatchChangeDocument] = Field(description="The pages the change was found on, the primary page first.")
    duplicate_count: int = Field(
        description="How many of those pages arrived as second sightings of the same reform (AC-WAT1). Computed by the server.",
        examples=[1],
    )
    obligations: list[WatchObligationLink] = Field(
        description="The library obligations the change affects, most confident first. A bank's own decision about each is on its case."
    )
    origin: Origin = Field(
        description="Who created the record, a fixed kind: `agent` (a run registered it) or `user` (a library editor did). It never changes.",
        examples=["agent"],
    )
    model: str | None = Field(
        description="The model and pipeline version behind the agent's reading, or null when a person registered it.",
        examples=["agent pipeline 0.4"],
    )
    agent_run_id: uuid.UUID | None = Field(
        description=(
            f"The run that registered it, as {_UUID}: the provenance anchor of every fact above. "
            "Null when a library editor registered the change by hand."
        ),
        examples=["5b8e1a44-9c2d-4f17-b0a3-1e7c6d5f4a21"],
    )
    first_seen_at: datetime.datetime = Field(
        description=(
            "When bleqq first saw this reform, as an RFC 3339 timestamp in UTC "
            "(`2026-09-16T06:02:00Z`). Not the date it was published, which is `publishedOn`."
        ),
        examples=["2026-09-16T06:02:00Z"],
    )


# ---------------------------------------------------------------------------------------
# The tenant-facing reads (WAT-02, WAT-03, WAT-04, CAS-01, FP-03, FP-04)
# ---------------------------------------------------------------------------------------
class WatchFact(LibraryResponse):
    """A classification fact on a change — its type, a flag or a scope term — with how it
    got there.

    Two things that are not the same thing, kept apart: `ref` is the library vocabulary row
    itself, exactly `{key, kind, label}` like every other vocabulary reference in this API,
    and the two fields beside it say how the row came to be on this change. Flattening the
    provenance into the reference would make this the one reference shape a client has to
    read differently, which is what the presentation guard refuses (NFR-S10)."""

    model_config = ConfigDict(json_schema_extra={"examples": [FACT_EXAMPLE]})

    ref: LibraryRef = Field(
        description=(
            "The vocabulary row or taxonomy term itself, as `{key, kind, label}`: a row of the "
            "`change_type` library vocabulary (`proposal`, `adopted`, `supervision`, "
            "`enforcement`, `recurring_date` on day one), of the `flag` vocabulary (`ai`, "
            "`advice_perimeter`) or of the taxonomy (`securities` and the other regimes). "
            f"{_VOCABULARY}"
        )
    )
    confidence: float | None = Field(description=_CONFIDENCE, examples=[0.74])
    suggested: bool = Field(description=_SUGGESTED, examples=[True])


class WatchCaseObligationDecision(LibraryResponse):
    """What this bank decided about one suggested obligation link. The bank's own zone: it
    is invisible to bleqq, to every other bank and to every model endpoint, and it changes
    no library row (WAT-04, ruling C)."""

    model_config = ConfigDict(json_schema_extra={"examples": [LINK_DECISION_EXAMPLE]})

    obligation_id: uuid.UUID = Field(
        description=(
            f"The library obligation the decision is about, as {_UUID}. The decision is this "
            "bank's alone and changes no library row."
        ),
        examples=["7c1f0b3e-52a4-4f9e-8a21-6d4b2c0a9e17"],
    )
    decision: CaseLinkDecision = Field(
        description=(
            "What this bank said, a fixed kind: `accepted` (the link is real for us and the "
            "case works it) or `removed` (not related to us). `removed` hides the link on this "
            "bank's case and leaves the shared library exactly as it was."
        ),
        examples=["accepted"],
    )
    decided_at: datetime.datetime = Field(
        description=(
            "When this bank decided, as an RFC 3339 timestamp in UTC (`2026-09-17T09:12:00Z`). "
            "Set by the server when the decision was stored; a caller never sends it."
        ),
        examples=["2026-09-17T09:12:00Z"],
    )


class WatchChangeCase(LibraryResponse):
    """This bank's own case for the change: its judgement and its work. Everything here is
    in the bank's zone under row-level security. No other bank and no bleqq person sees it,
    and none of it reaches a model endpoint (NFR-01, NFR-04, D-07)."""

    model_config = ConfigDict(json_schema_extra={"examples": [CASE_EXAMPLE]})

    id: uuid.UUID = Field(
        description=(
            f"This bank's case for the change, as {_UUID}. One per bank per change (CAS-01), and "
            "never another bank's."
        ),
        examples=["9d0b5a3c-6e14-4f27-8c93-5a1e7b0d2f46"],
    )
    category: CaseCategory = Field(
        description=(
            "Where the case stands, one of the seven fixed categories the state machine reads "
            "(D-13): `new` (registered, nobody has looked — the screen reads 'Needs triage'), "
            "`assigned` (triaged with an urgency and an owner), `assessing` (the owner is "
            "working out what it means), `implementing` (actions are open), `signoff` (waiting "
            "for a second person), `closed` and `dismissed` (not for us, with a reason, and "
            "restorable). A bank may name sub-statuses inside a category; the guards read the "
            "category alone. In R1 every case is `new`: triage onwards is chunk 9."
        ),
        examples=["new"],
    )
    urgency: LibraryRef | None = Field(
        description=(
            "How soon this bank must act, as `{key, kind, label}` from the `urgency` library "
            "vocabulary, `act_now`, `within_3_months`, `six_months_plus`, `monitor` or "
            "`no_action` on day one. It starts as the change's suggested urgency and stays a "
            "suggestion until `urgencyConfirmed` is true. Null only where no suggestion was "
            f"made. {_VOCABULARY}"
        )
    )
    urgency_confirmed: bool = Field(
        description=(
            "Whether a person in this bank confirmed the urgency at triage. False means the "
            "value above is still the agent's suggestion; the screen says so. A reader must not "
            "report an unconfirmed urgency as this bank's decision."
        ),
        examples=[False],
    )
    owner_id: uuid.UUID | None = Field(
        description=(
            f"The person in this bank who owns the case, as {_UUID}, once triage names one. Null "
            "before triage, which is where every case sits in R1. Never a person of another bank."
        ),
        examples=[None],
    )
    footprint_match: bool = Field(
        description=(
            "Whether the change's scope terms match this bank's footprint, computed by the "
            "server when the case was created and recomputed when either side moves. It says "
            "the change is in scope to look at; it does not say the obligation applies or that "
            "the bank complies — those are separate facts (REG-01, REG-02)."
        ),
        examples=[True],
    )
    so_what_text: str | None = Field(
        description=(
            f"This bank's copy of the 'So what?', at most {TEXT_MAX} characters. It starts as "
            "the library's draft and is this bank's to rewrite. Null when no draft exists yet."
        ),
        examples=["Teams that pay for external research should confirm that documented criteria exist."],
    )
    so_what_confirmed: bool = Field(
        description=(
            "Whether a person in this bank confirmed or rewrote the wording. False means it is "
            "still an AI draft and the screen labels it so (WAT-05). Another bank's copy is "
            "unaffected either way."
        ),
        examples=[False],
    )
    so_what_confirmed_at: datetime.datetime | None = Field(
        description=(
            "When a person in this bank confirmed the wording, as an RFC 3339 timestamp in UTC "
            "(`2026-09-17T09:12:00Z`). Null while it is still an AI draft."
        ),
        examples=[None],
    )
    obligation_decisions: list[WatchCaseObligationDecision] = Field(
        description="What this bank decided about the suggested obligation links. An empty list means it has decided nothing yet."
    )
    allowed_transitions: list[CaseCategory] = Field(
        description=(
            "The categories this case may move to next, computed by the server from the state "
            "machine's guards. A fixed kind in code, not a vocabulary an admin extends, and the "
            "seven members are: `new`, registered and nobody has looked; `assigned`, triaged "
            "with an urgency and an owner; `assessing`, the owner is working out what it means "
            "for the bank; `implementing`, actions are open; `signoff`, waiting for a second "
            "person to sign it off with a passkey; `closed`, signed off or closed with a reason; "
            "and `dismissed`, not for this bank, with a reason, and restorable. Always empty in "
            "R1, because the workflow that would move a case is chunk 9; empty means 'no move is "
            "offered here yet', never 'the case is stuck'."
        ),
        examples=[[]],
    )


class WatchChangeRow(LibraryResponse):
    """One line of the watch feed: the library's facts about a reform beside this bank's
    own case for it. The library half is the same for every bank; the `case` half is this
    bank's alone and never leaves it."""

    model_config = ConfigDict(json_schema_extra={"examples": [CHANGE_ROW_EXAMPLE]})

    id: uuid.UUID = Field(description="The change's identifier in the shared library.", examples=["c3a6e1f0-7b42-4d8e-95a1-2f0b6c8d4e19"])
    stable_key: str = Field(description="The reform's permanent key.", examples=["chg-fi-2026-research-payments"])
    title: str = Field(
        description="What the reform is called, in the source's words.",
        examples=["FI adopts amended rules on paying for investment research"],
    )
    change_type: WatchFact = Field(description="The kind of change, with the agent's confidence and whether it is still a suggestion.")
    authority_label: str = Field(description="Who issued it, as the source writes it.", examples=["Finansinspektionen"])
    authority_id: uuid.UUID | None = Field(
        description=(
            f"The library authority that issued it, as {_UUID}, or null when the library does not "
            "know the authority. A change with no authority is not restricted by jurisdiction "
            "(FP-S15, D-29), so null must not be read as 'not relevant to us'."
        ),
        examples=["3a1c94c2-3f41-4f0e-9a4e-5b2a1d0c7e11"],
    )
    published_on: datetime.date | None = Field(
        description=(
            "When the source published it, as a plain calendar date (`2026-09-15`) and never a "
            "timestamp, with `publishedPrecision` beside it. Null when the source states none."
        ),
        examples=["2026-09-15"],
    )
    published_precision: DatePrecision | None = Field(description=_PRECISION, examples=["day"])
    key_date: datetime.date | None = Field(
        description=(
            "The date that drives 'coming up', as a plain calendar date (`2026-10-01`) with "
            "`keyDatePrecision` beside it. Null when no date is known yet."
        ),
        examples=["2026-10-01"],
    )
    key_date_precision: DatePrecision | None = Field(description=_PRECISION, examples=["day"])
    key_date_label: str | None = Field(description="What that date is, in the source's words.", examples=["In force"])
    status: ChangeStatus = Field(description="The library's lifecycle stage: `active`, `superseded` or `withdrawn`.", examples=["active"])
    flags: list[WatchFact] = Field(description="The change's flags, each with its confidence and suggestion marker.")
    terms: list[WatchFact] = Field(description="The change's scope terms, each with its confidence and suggestion marker.")
    suggested_urgency: LibraryRef | None = Field(
        description=(
            "The agent's suggested urgency as `{key, kind, label}` from the `urgency` library "
            "vocabulary, `act_now`, `within_3_months`, `six_months_plus`, `monitor` or "
            "`no_action` on day one. A library fact, the same for every bank; this bank's own "
            f"decision is inside `case`. {_VOCABULARY}"
        )
    )
    in_footprint: bool = Field(
        description=(
            "Whether the change's scope matches this bank's footprint, computed by the server. "
            "A row outside the footprint is still answered when the caller asked for it "
            "(`footprint=all`), because an address always resolves (FP-03)."
        ),
        examples=[True],
    )
    first_seen_at: datetime.datetime = Field(
        description=(
            "When bleqq first saw the reform, as an RFC 3339 timestamp in UTC "
            "(`2026-09-16T06:02:00Z`). Not the date it was published, which is `publishedOn`."
        ),
        examples=["2026-09-16T06:02:00Z"],
    )
    case: WatchChangeCase | None = Field(
        description=(
            "This bank's own case for the change, or null when it has none yet. Never another "
            "bank's case: a platform console session has no tenant and always reads null here, "
            "which is why the console has a list of its own."
        )
    )


class WatchChangeDetail(WatchChange):
    """`GET /changes/{changeId}`: the whole change page. The library record as `WatchChange`
    answers it, plus the two facts that are the reader's own — whether it is in their
    footprint and their bank's case — and with the classification answered the way the feed
    answers it.

    `flags` and `terms` are `WatchFact` here and `LibraryRef` on `WatchChange`, because the
    write shapes answer the record as stored and this is the page a person judges a change
    on: an agent's suggestion has to be visible as a suggestion where the decision is taken
    (WAT-03). The change page used to flatten each fact to its `ref` and lose the
    provenance the feed row carries (2026-09-21).

    `changeType` stays a `LibraryRef` here, where a feed row answers a fact. It is not the
    same gap: the library stores no confidence and no confirmation for the type itself, so
    the row's fact derives `suggested` from the change's own `origin` — and this response
    already carries `origin`, `model` and `agentRunId` at the top level. An individual flag
    or scope term has no such field to be read off, which is why those two had to carry
    their own.
    """

    model_config = ConfigDict(json_schema_extra={"examples": [CHANGE_DETAIL_EXAMPLE]})

    flags: list[WatchFact] = Field(  # type: ignore[assignment]  # narrower than WatchChange's: see the docstring
        description=(
            "What the change is about across subject areas, each as a fact rather than a bare "
            "reference. `ref` is the row of the `flag` library vocabulary itself, as "
            "`{key, kind, label}` — `ai` and `advice_perimeter` on day one. `confidence` is how "
            "sure the agent that put the flag there was, 0 to 1, or null when a library editor "
            "set it by hand; it orders nothing on this screen and says nothing about whether "
            "the flag is right. `suggested` is true while no library editor has confirmed the "
            "flag, and the change page marks such a flag as the agent's reading rather than a "
            "checked fact — a reader deciding from this page must not treat it as checked. A "
            "library editor confirms a flag in the console queue and never here, and a bank "
            "never confirms one at all: it is a library fact behind `proposals.review` "
            f"(WAT-03, PRO-01). An empty list means no flag applies, not that nobody looked. {_VOCABULARY}"
        )
    )
    terms: list[WatchFact] = Field(  # type: ignore[assignment]  # narrower than WatchChange's: see the docstring
        description=(
            "The taxonomy terms that scope the change — regime, market, product, service — each "
            "as a fact rather than a bare reference. `ref` is the taxonomy row itself, as "
            "`{key, kind, label}` with `securities`, `banking`, `payments`, `insurance`, `aml`, "
            "`tax`, `data_protection` and `ai_ict` among the regimes seeded on day one; a term's "
            "`kind` is null because its dimension is its kind. `confidence` is the agent's own "
            "number, 0 to 1, or null when a person set the term. `suggested` is true until a "
            "library editor confirms it, and the change page shows such a term as a suggestion. "
            "This is what the footprint is matched against, and `inFootprint` is computed from "
            "every term whether or not it is still suggested; it is not this bank's footprint "
            f"and it never says the bank complies (REG-01, REG-02). {_VOCABULARY}"
        )
    )
    in_footprint: bool = Field(
        description="Whether the change's scope matches the reader's footprint, computed by the server (FP-03).", examples=[True]
    )
    case: WatchChangeCase | None = Field(
        description="The reader's own bank's case, or null when there is none. Never another bank's, and never present for a console session."
    )


class WatchChangePage(LibraryResponse):
    """`GET /changes`: one page of the watch feed."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [CHANGE_ROW_EXAMPLE], "total": 42}]})

    items: list[WatchChangeRow] = Field(
        description=(
            "The rows of this page, ordered by key date then by when the reform was first "
            "seen, both newest first, with the row id as a stable tiebreak so a page boundary "
            "never drops or repeats a row. A change with no key date sorts last, not first."
        )
    )
    total: int = Field(
        description=(
            "How many rows match the filters, across every page. An empty page with a total of "
            "zero is a 200 and a real answer, not an error."
        ),
        examples=[42],
    )


class WatchChangeQuery(PageQuery, CamelSchema):
    """The filters of `GET /changes`, carrying its own `limit` and `offset` from
    `PageQuery`: 20 by default, 100 at most, and a larger `limit` is a 422 rather than a
    clamp. Every value is a key or a fixed kind, never a label, so a filter a bank saves
    keeps working when someone relabels a vocabulary row.

    A parameter this schema does not name is a 422, not a silently dropped one. That is
    what makes the departure of INPUT_DELTAS §7 visible: a client written against the
    designed `inFootprint` pair is told, instead of quietly receiving the default feed.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"tab": "all", "footprint": "in", "urgency": "act_now", "limit": 20, "offset": 0}]},
    )

    tab: FeedTab = Field(
        default="all",
        description=(
            "Which case category to show, a fixed kind: `all`, or one of the seven categories "
            "`new`, `assigned`, `assessing`, `implementing`, `signoff`, `closed`, `dismissed`. "
            "It filters on this bank's own cases, so a tab other than `all` answers nothing for "
            "a caller with no case. In R1 every case is `new`."
        ),
        examples=["all"],
    )
    status: ChangeStatus | None = Field(
        default=None,
        description="The library's lifecycle stage: `active`, `superseded` or `withdrawn`. Omit for every stage.",
        examples=["active"],
    )
    urgency: str | None = Field(
        default=None,
        max_length=KEY_MAX,
        description=(
            f"A key of the `urgency` library vocabulary, at most {KEY_MAX} characters — "
            "`act_now`, `within_3_months`, `six_months_plus`, `monitor`, `no_action` on day one. "
            "It matches this bank's case urgency where there is one and the change's suggestion "
            f"otherwise. {_VOCABULARY}"
        ),
        examples=["act_now"],
    )
    term_id: list[uuid.UUID] = Field(
        default_factory=list,
        max_length=50,
        description=(
            f"Taxonomy term ids to filter by, each {_UUID} from `GET /taxonomy/terms`, at most 50 "
            "per call; a change matches when it carries any one of them. Repeat the parameter "
            "for each term."
        ),
        examples=[["a4e1c07b-9d52-4f83-8b10-2c7e5a9f4d68"]],
    )
    change_type: str | None = Field(
        default=None,
        max_length=KEY_MAX,
        description=(
            f"A key of the `change_type` library vocabulary, at most {KEY_MAX} characters: "
            "`proposal`, `adopted`, `supervision`, `enforcement` or `recurring_date` on day one. "
            f"{_VOCABULARY}"
        ),
        examples=["adopted"],
    )
    owner_id: uuid.UUID | None = Field(
        default=None,
        description=(
            f"Show only the cases this person in your bank owns, named by {_UUID}. A person of "
            "another bank matches nothing rather than answering a 403, because no id may be "
            "probed across banks."
        ),
        examples=[None],
    )
    in_footprint: None = Field(
        default=None,
        deprecated=True,
        description=(
            "Not accepted: send `footprint` instead. The designed contract had a boolean pair "
            "here and the build has one value (INPUT_DELTAS §7). Any value answers 422, "
            "because ignoring it would hand a client that asked for `inFootprint=false` the "
            "opposite feed without a word. Declared only so that refusal happens, and named "
            "in the published contract so a client sees what to send."
        ),
        examples=[None],
    )
    footprint: FootprintFilter = Field(
        default="in",
        description=(
            "Which changes to show against the bank's footprint, a fixed kind and a single "
            "value (INPUT_DELTAS §7 replaces the designed `inFootprint` pair): `in` (the "
            "default — only what matches the footprint), `all` (everything the library holds) "
            "or `watched` (everything from a market this bank watches, whether or not the rest "
            "of the scope matches, FP-04). Sending the designed `inFootprint` answers 422."
        ),
        examples=["in"],
    )
    week: datetime.date | None = Field(
        default=None,
        description=(
            "Any date inside the week to show, resolved to that week in the bank's own time "
            "zone. Used by the briefing; omit for every week."
        ),
        examples=["2026-09-14"],
    )
    unconfirmed_so_what: bool | None = Field(
        default=None,
        description="True shows only the cases whose 'So what?' is still an AI draft in this bank. Omit for both.",
        examples=[True],
    )
    q: str | None = Field(
        default=None,
        max_length=QUERY_MAX,
        description=(
            f"A phrase to look for in the title and the summary, at most {QUERY_MAX} "
            "characters. It is what someone in the bank typed, so it is tenant content: it "
            "never appears in a log, in Sentry or in a model prompt (playbook 4.7)."
        ),
        examples=["research payments"],
    )


class WatchConsoleChangeRow(LibraryResponse):
    """One line of the console's Change facts queue: a library change and the facts an
    agent proposed for it. Library only — a platform console session has no tenant, so no
    bank's case, footprint, owner or 'So what?' is joined or answered here (NFR-01)."""

    model_config = ConfigDict(json_schema_extra={"examples": [CONSOLE_ROW_EXAMPLE]})

    id: uuid.UUID = Field(description="The change's identifier in the shared library.", examples=["c3a6e1f0-7b42-4d8e-95a1-2f0b6c8d4e19"])
    stable_key: str = Field(description="The reform's permanent key.", examples=["chg-fi-2026-research-payments"])
    title: str = Field(description="What the reform is called.", examples=["FI adopts amended rules on paying for investment research"])
    change_type: WatchFact = Field(description="The kind of change, with the agent's confidence and whether it is still a suggestion.")
    authority_label: str = Field(description="Who issued it, as the source writes it.", examples=["Finansinspektionen"])
    authority_id: uuid.UUID | None = Field(
        description=(
            f"The library authority that issued it, as {_UUID}, or null when the library does not "
            "know the authority."
        ),
        examples=["3a1c94c2-3f41-4f0e-9a4e-5b2a1d0c7e11"],
    )
    published_on: datetime.date | None = Field(
        description=(
            "When the source published it, as a plain calendar date (`2026-09-15`) and never a "
            "timestamp, with `publishedPrecision` beside it. Null when the source states none."
        ),
        examples=["2026-09-15"],
    )
    published_precision: DatePrecision | None = Field(description=_PRECISION, examples=["day"])
    status: ChangeStatus = Field(description="The library's lifecycle stage: `active`, `superseded` or `withdrawn`.", examples=["active"])
    flags: list[WatchFact] = Field(description="The flags an agent proposed, each with its confidence and suggestion marker.")
    terms: list[WatchFact] = Field(description="The scope terms an agent proposed, each with its confidence and suggestion marker.")
    obligations: list[WatchObligationLink] = Field(description="The obligation links an agent proposed, most confident first.")
    unconfirmed_count: int = Field(
        description=(
            "How many facts on this change — its type, its flags, its scope terms and its "
            "obligation links — no library editor has confirmed yet. Computed by the server; it "
            "is the queue's own count and says nothing about whether the facts are wrong."
        ),
        examples=[2],
    )
    first_seen_at: datetime.datetime = Field(
        description=(
            "When bleqq first saw the reform, as an RFC 3339 timestamp in UTC "
            "(`2026-09-16T06:02:00Z`); the queue is ordered by it, newest first."
        ),
        examples=["2026-09-16T06:02:00Z"],
    )


class WatchConsoleChangePage(LibraryResponse):
    """`GET /console/changes`: one page of the console's Change facts queue."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [CONSOLE_ROW_EXAMPLE], "total": 7}]})

    items: list[WatchConsoleChangeRow] = Field(description="The rows of this page, newest first by when the reform was first seen.")
    total: int = Field(description="How many changes match the filters, across every page. Zero is a 200.", examples=[7])


class WatchConsoleChangeQuery(PageQuery, CamelSchema):
    """The filters of `GET /console/changes`, the queue a library editor works, carrying
    its own `limit` and `offset` from `PageQuery`: 20 by default, 100 at most, and a larger
    `limit` is a 422. A parameter this schema does not name is a 422 as well."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"confirmed": "false", "limit": 20, "offset": 0}]},
    )

    confirmed: Literal["false", "all"] = Field(
        default="false",
        description=(
            "Which changes to list, a fixed kind with two members: `false` (the default — only "
            "changes carrying at least one fact nobody has confirmed, which is the queue) or "
            "`all` (every change, for looking something up). There is no `true`: a change with "
            "nothing left to confirm is simply not in the queue."
        ),
        examples=["false"],
    )
    authority_id: uuid.UUID | None = Field(
        default=None,
        description=(
            f"Show only the changes of one authority, named by {_UUID} from `GET /authorities`. "
            "Omit it for every authority."
        ),
        examples=["3a1c94c2-3f41-4f0e-9a4e-5b2a1d0c7e11"],
    )
    q: str | None = Field(
        default=None,
        max_length=QUERY_MAX,
        description=(
            f"A phrase to look for in the title and the summary, at most {QUERY_MAX} "
            "characters. A library editor's search over library rows; it names no bank."
        ),
        examples=["research"],
    )


class WatchObligationChangePage(CamelSchema):
    """`GET /obligations/{obligationId}/changes`: the related-changes panel of an
    obligation, and the open-change count the inventory shows beside it."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"items": [CHANGE_ROW_EXAMPLE], "total": 3, "openCount": 1}]}
    )

    items: list[WatchChangeRow] = Field(
        description=(
            "The changes linked to this obligation, with the reader's own case on each. The "
            "links a library editor has confirmed come first, because they are the ones "
            "somebody has checked; inside each group the rows are ordered by key date, newest "
            "first. An unconfirmed link is a suggestion, never a statement that the change "
            "does not affect the duty."
        )
    )
    total: int = Field(description="How many changes are linked to the obligation, across every page. Zero is a 200.", examples=[3])
    open_count: int = Field(
        description=(
            "How many of those changes still have work open for this bank — a case that is "
            "neither closed nor dismissed. Computed by the server from the reader's own cases, "
            "so another bank reading the same obligation sees its own number. It counts cases, "
            "not gaps: it says nothing about whether the bank complies (REG-02)."
        ),
        examples=[1],
    )
