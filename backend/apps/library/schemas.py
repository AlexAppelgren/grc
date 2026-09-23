"""Request and response schemas of the library app: camelCase through CamelSchema, app-prefixed
class names where a shape is specific to this app (playbook 4.1).

Responses carry keys, kinds, counts and dates, never a phrase a screen would string-match
(pill contract): vocabulary rows and terms are `{key, kind, label}`, and the screen turns
facts such as `binding`, `inFootprint` and `openChangeCount` into its own words."""

from __future__ import annotations

import datetime
from typing import Any
from uuid import UUID

from django.conf import settings
from pydantic import ConfigDict, Field, ModelWrapValidatorHandler, ValidationInfo, model_validator

from apps.shared.schemas import CamelSchema, WriteBody
from apps.taxonomy.schemas import PersonRef

# The longest `q` a list accepts: a phrase to look for, never a document.
MAX_QUERY_LENGTH = 200
# A language key is a BCP 47 primary tag (`Language.key`, a slug of at most 8 characters);
# `?lang=` is looked up among the languages a version has, so a longer one is a 422.
MAX_LANGUAGE_LENGTH = 8

# The one sentence a reader of this app needs on every value it returns
# (docs/plans/briefs/API_DOCUMENTATION.md §1.2). Written once so the list, the card and
# the diff cannot tell a reader three versions of where the same fact came from.
LIBRARY_FACT = (
    "A shared library fact, identical for every bank: taken from the public source the "
    "record's provenance names, and changed only through a proposal a second, independent "
    "principal approved."
)


class LibraryResponse(CamelSchema):
    """A response the server builds from plain values, never from an ORM object, and
    pydantic validates natively when it is built. Ninja's own root validator wraps every
    value in its Django getter, one Python call per field of every nested object, which was
    most of a page's server time (NFR-02, measured 2026-09-19). Ninja answers a validated
    instance of the route's response type as it is, without validating it again."""

    @model_validator(mode="wrap")
    @classmethod
    def _run_root_validator(cls, values: Any, handler: ModelWrapValidatorHandler[Any], info: ValidationInfo) -> Any:
        # Replaces ninja.Schema's validator of the same name, which wraps `values` in its getter.
        return handler(values)


class LibraryRef(LibraryResponse):
    """A vocabulary row or a term as every surface reads it: key and kind, and the label in
    the reader's language (playbook 15). A term's kind is null: its dimension is its kind.

    A shared library fact wherever it appears: the row behind it is a library vocabulary
    or a taxonomy term, which a platform admin may add to, rename or retire without a
    deploy. The key is what a filter, a report, a webhook or an export stores; the label
    is for a person to read and may change under it. A tone is never here: a pill's tone
    follows its slot or the row's own kind and is nobody's to send (NFR-03)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"key": "act_now", "kind": None, "label": "Act now"}]})

    key: str = Field(
        description=(
            "The row's immutable key, and the only part of this reference to store, compare "
            "or send back. Which list it is drawn from is settled by the field that carries "
            "the reference, and that field names its vocabulary and the endpoint that "
            "returns the live set; every one of those lists is rows rather than a closed "
            "set, so an admin may extend, relabel, reorder or retire it without a deploy "
            "and a key you have not seen before is new data and not an error. Match on the "
            "key and never on the label, and never construct one: a key the list does not "
            "hold answers 422 `unknown_key` with the valid keys."
        ),
        examples=["act_now"],
    )
    kind: str | None = Field(
        description=(
            "The row's fixed sub-kind where its list has one — a change type's lifecycle "
            "kind, a case sub-status's category — and null where it has none. A taxonomy "
            "term is always null here: its dimension is its kind. It is a kind in code, so "
            "the rules may branch on it; an admin never adds one."
        ),
        examples=[None],
    )
    label: str = Field(
        description=(
            "The row's label in the reader's language, for display only. It is a phrase a "
            "person wrote and may be reworded at any time, so nothing may match on it."
        ),
        examples=["Act now"],
    )


class LocalizedText(LibraryResponse):
    """One text in one language (INV-05, D-12): which language it is in, whether it is the
    original and whether a machine translated it, so the screen can label it."""

    text: str = Field(
        description=(
            "The wording itself, in the one language this block names. "
            f"{LIBRARY_FACT} "
            "It is never rewritten where it stands: a new wording is a new version of the "
            "record, so the same version read twice always gives the same words."
        ),
        examples=["Pay for third-party research only under the permitted models"],
    )
    language: str = Field(
        description=(
            "Which content language the wording is in, as a language key: the BCP 47 "
            "primary tag of at most 8 characters that `GET /reference/languages` lists, "
            "with `sv`, `en`, `da`, `nb` and `fi` active on day one. The languages are "
            "library reference rows a platform admin may extend or retire without a "
            "deploy, so read that endpoint for the live set and compare on the key rather "
            "than on the language's name."
        ),
        examples=["en"],
    )
    is_original: bool = Field(
        description=(
            "True when this is the language the source itself published in, which is the "
            "wording that governs wherever two languages read differently. False on every "
            "translation, whoever or whatever made it."
        ),
        examples=[False],
    )
    is_machine: bool = Field(
        description=(
            "True while a machine made this translation and no person has confirmed it, so "
            "a screen has to label it as such (INV-05). It says nothing about whether the "
            "translation is faithful, only that nobody has checked it; the original is the "
            "text that governs either way."
        ),
        examples=[True],
    )


class PartialDate(LibraryResponse):
    """A legal date with its precision: day, month, quarter or year (playbook 4.3, INV-S10)."""

    date: datetime.date = Field(
        description=(
            "A legal date — when a rule starts or stops binding the bank — as a plain "
            "calendar date such as `2026-10-01`. It is never a timestamp and carries no "
            "time zone, because a law takes effect on a day and not at an instant. Read it "
            "with `precision`: where the source named only a quarter or a year, this is the "
            "first day of that period and not a claim about the day."
        ),
        examples=["2026-10-01"],
    )
    precision: str = Field(
        description=(
            "How exactly the source dated it, and so how much of `date` may be shown or "
            "compared. `day` means the source named the day. `month` means it named the "
            "month, which a screen reads as \"October 2026\". `quarter` means it named the "
            "quarter, read as \"Q4 2026\". `year` means it named the year alone. Anything "
            "below `day` is not a missing date: it is exactly what the source gave, so a "
            "reader must not round it into a deadline."
        ),
        examples=["day"],
    )


class AgentRef(LibraryResponse):
    """One of the platform's research agents, named the way a screen may label it: its
    definition key, which never changes, and never its internal id alone (AUD-02)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"id": "6d1e4f8a-9c3b-4a7e-8f21-1b6d4c8a2e05", "key": "watch-sweeper"}]})

    id: UUID = Field(description="The agent definition, as a UUID.")
    key: str = Field(description="The agent definition's own key, stable and never changed, for example `watch-sweeper`.", examples=["watch-sweeper"])


class VersionConfirmation(LibraryResponse):
    """Who confirmed the approval that wrote a version, and which agent proposed it (INV-05,
    PRO-02, D-62), exactly as stored and never combined into a verdict.

    The proposer and the confirmer are separate facts, so all four pairings occur: `agent`
    with both agents named (an agent proposed and an independent agent confirmed), `agent`
    with only `confirmedByAgent` (a person proposed and an agent confirmed), `user` with
    only `proposedByAgent` (a person confirmed an agent's proposal) and `user` with neither.
    Decide the machine-confirmed label from `verifiedOrigin` alone, never from which agent
    fields are present. A person's re-verification of the record later than the version's
    approval is what lets that label give way; the record's provenance carries that stamp,
    and this answer applies no such rule itself."""

    verified_origin: str = Field(
        description=(
            "Who confirmed the approval that wrote this version: `agent` when the reviewer "
            "was a second, independent agent, which a screen labels machine-confirmed and "
            "never as a person's verification; `user` when a person approved it, who is not "
            "named here. An empty string on a version the library was seeded with or applied "
            "before this was recorded, which reads the same as `user`. A fixed kind, not a "
            "vocabulary."
        ),
        examples=["agent"],
    )
    confirmed_by_agent: AgentRef | None = Field(
        description=(
            "The independent agent that confirmed the approval, by its definition key, when "
            "`verifiedOrigin` is `agent`. Null whenever a person approved it. It names a "
            "platform agent definition, never a person or a bank."
        )
    )
    proposed_by_agent: AgentRef | None = Field(
        description=(
            "The agent that proposed this version, by its definition key, read from the "
            "approved proposal. Null whenever the proposer was not a key bound to an agent, "
            "which is every proposal a person made, whoever confirmed it. It is independent "
            "of `verifiedOrigin`: an agent's proposal a person approved names the agent here "
            "beside `verifiedOrigin` `user`."
        )
    )


class ObligationVersionRef(VersionConfirmation):
    """A summary version by number and the date it takes effect; null means since the
    obligation began (INV-04). It carries who confirmed its approval as well (the three
    fields of `VersionConfirmation`), so a row saying new wording is coming can say whether
    an independent agent, rather than a person, confirmed that wording (INV-05)."""

    version_number: int = Field(
        description=(
            "Which version of this duty's summary it is, numbered from 1 in the order the "
            "versions took effect. A version row is written once and never overwritten, so "
            "a number always addresses the same words; it is the number to send to the diff "
            "as `from` or `to`."
        ),
        examples=[2],
    )
    effective_from: PartialDate | None = Field(
        description=(
            "The legal date this version starts binding the bank, at the precision the "
            "source gave it. Null means the version has been in force since the obligation "
            "entered the library, never that the date is unknown. "
            f"{LIBRARY_FACT}"
        ),
    )


class ScopeDimension(LibraryResponse):
    """The record's terms in one dimension (FP-01). An empty list means no restriction in
    that dimension; `allSelected` means every active term of it is carried."""

    dimension: LibraryRef = Field(
        description=(
            "Which facet of the taxonomy this entry is about, as key, kind and label. The "
            "dimensions are vocabulary rows and never a closed set: a platform admin may "
            "extend, relabel, reorder or retire the list without a deploy, so read "
            "`GET /taxonomy/dimensions` for the live set and match on the key. Seeded on day "
            "one: `regime`, `legal_entity`, `service_type`, `account_type`, "
            "`client_category`, `channel` and `lifecycle_stage`. Every active dimension is "
            "listed on every record, including the ones a record carries no term in."
        ),
    )
    terms: list[LibraryRef] = Field(
        description=(
            "The terms this record carries in that dimension, in the picker's order. An "
            "empty list means the record puts no restriction on this facet and so reaches "
            "every bank in it — never that the facet is unknown. The terms are vocabulary "
            "rows a platform admin may extend or retire without a deploy, and a member of a "
            "bank may propose a new one, so read `GET /taxonomy/terms` for the live set and "
            "match on the key. A term's `kind` is null: its dimension is its kind."
        ),
    )
    all_selected: bool = Field(
        description=(
            "True when the record carries every active term of the dimension, which lets a "
            "screen read \"All services\" rather than listing them one by one. False both "
            "when the record carries some of the terms and when it carries none, so read "
            "`terms` to tell those two apart."
        ),
        examples=[False],
    )


class OutsideReason(LibraryResponse):
    """A dimension in which none of the record's terms is in the footprint (FP-03)."""

    dimension: LibraryRef = Field(
        description=(
            "The facet in which the record's terms and the bank's footprint have nothing in "
            "common, which is the reason the record would be hidden. The dimensions are "
            "vocabulary rows a platform admin may extend or retire without a deploy, so read "
            "`GET /taxonomy/dimensions` for the live set and match on the key. Only a "
            "dimension that narrows the footprint appears here: `channel` and "
            "`lifecycle_stage` describe a record and never hide it."
        ),
    )
    terms: list[LibraryRef] = Field(
        description=(
            "The terms the record carries in that dimension, so a reader can see what the "
            "bank's footprint would have to include for the record to appear. They are "
            "vocabulary rows a platform admin may extend or retire, matched on the key. "
            "This is the record's own scope and never the bank's footprint: nothing here "
            "says what the bank does."
        ),
    )


class ObligationInstrumentRef(LibraryResponse):
    """The instrument a duty was broken out of, as a row or a related record names it: the
    key to filter on and the short name to print."""

    key: str = Field(
        description=(
            "The instrument's stable key, the value to store and to send back as "
            "`?instrument=`. It is issued once and never changes, however the instrument is "
            "renamed or amended. "
            f"{LIBRARY_FACT}"
        ),
        examples=["fffs-2017-2"],
    )
    short_name: str = Field(
        description=(
            "How the instrument is written on a pill or in a column, in its own language. It "
            "is a label a person wrote and may be reworded, so show it and never match on "
            "it; `key` is the identifier."
        ),
        examples=["FFFS 2017:2"],
    )


# The facts a row of the list and a record's own card both carry. Written once so the two
# surfaces cannot tell a reader two stories about the same column.
_OBLIGATION_ID = (
    "The duty's identifier in the shared library, as a UUID: what every other call "
    f"addresses this obligation by. {LIBRARY_FACT}"
)
_OBLIGATION_STABLE_KEY = (
    "The duty's immutable key, issued once and readable by a person. It survives every "
    "amendment, relabelling and new version, which is what makes it safe to keep in an "
    "export, a report or a system of the bank's own. Store it beside the id and never "
    "construct one."
)
_OBLIGATION_REF_LABEL = (
    "How the duty is cited inside its instrument, in the words the source itself uses — a "
    "chapter, a section or the heading the authority gave it. It is there for a reader to "
    "recognise the place in the rule book, not a structured reference to parse."
)
_OBLIGATION_TITLE = (
    "The duty in one line, in the best language this reader can be served: their own "
    "first, then their bank's default, then English, then whatever the record has. Null "
    "only when the record carries no title in any language at all."
)
_BINDING_LEVEL = (
    "What rank of instrument the duty sits in, as key, kind and label: how much weight the "
    "rule carries. The levels are vocabulary rows and not a closed set — a platform admin "
    "may extend, relabel or retire the list without a deploy — so read "
    "`GET /vocab/instrument_level` for the live set and match on the key; "
    "`eu_regulation`, `eu_directive`, `eu_guidance`, `act` and `authority_regulation` are "
    "seeded on day one. The level is not the same fact as `binding`: the level carries a "
    "default and the instrument's own record decides."
)
_BINDING = (
    "Whether the instrument behind this duty binds the bank in law. False means guidance a "
    "bank either complies with or explains, which is what a screen says in those words. It "
    "is a fact about the rule and not about the bank: neither value says the duty applies "
    "here, and neither says whether the bank complies with it."
)
_DUTY_TYPE = (
    "What kind of duty this is, as key, kind and label. `conduct`, `disclosure`, "
    "`record_keeping`, `reporting`, `governance` and `technical` are the rows seeded on day "
    "one, and they are vocabulary rows rather than a closed enum: a platform admin may "
    "extend, relabel or retire the list without a deploy. Read `GET /vocab/duty_type` for "
    "the live set, send the key as `?dutyType=`, and never match on the label."
)
_TAGS = (
    "The library's own keywords for this duty, as key, kind and label — `research`, "
    "`inducements`, `costs` and the rest of the rows seeded on day one. They are vocabulary "
    "rows a platform admin may extend, relabel or retire without a deploy, so read "
    "`GET /vocab/library_tag` for the live set and match on the key. They describe the duty "
    "for a reader and never narrow the footprint: a tag is not a scope term."
)
_SCOPE = (
    "Which banks and which business the duty reaches, one entry per active dimension of the "
    "taxonomy. This is the record's own scope as the library states it: it is not the bank's "
    "footprint, and it is not the judgement that the duty applies to this bank."
)
_IN_FOOTPRINT = (
    "Whether the duty's scope overlaps the bank's own footprint, which is what decides "
    "whether the record appears in the default list at all. It is a filter and not a "
    "decision: inside the footprint is not \"this applies to us\", which a person judges "
    "separately and records elsewhere, and neither of those is \"we comply\"."
)
_OUTSIDE_REASON = (
    "Why the default list would have hidden this record: one entry per dimension in which "
    "the duty's terms and the bank's footprint have nothing in common. Empty on a record "
    "inside the footprint, and so filled only on the records `outsideFootprint=true` "
    "reveals."
)


class ObligationRow(LibraryResponse):
    """One row of `GET /obligations` (INV-03). `version` is the one in force on the read's
    date and `upcomingVersion` the next one after it. The register overlay arrives later:
    `openChangeCount` with the watch feed (chunk 5), `pendingApplicability` and
    `complianceStatus` with the register (chunk 8)."""

    id: UUID = Field(description=_OBLIGATION_ID, examples=["7c1f0b3e-52a4-4f9e-8a21-6d4b2c0a9e17"])
    stable_key: str = Field(description=_OBLIGATION_STABLE_KEY, examples=["obl-research-payments"])
    ref_label: str = Field(description=_OBLIGATION_REF_LABEL, examples=["Third-party payments"])
    title: LocalizedText | None = Field(description=_OBLIGATION_TITLE)
    instrument: ObligationInstrumentRef = Field(
        description=(
            "The instrument this duty was broken out of, by key and short name. The card "
            "adds the instrument's official reference and what it implements; this row "
            "carries only what a column shows."
        )
    )
    binding_level: LibraryRef = Field(description=_BINDING_LEVEL)
    binding: bool = Field(description=_BINDING, examples=[True])
    duty_type: LibraryRef = Field(description=_DUTY_TYPE)
    tags: list[LibraryRef] = Field(description=_TAGS)
    scope: list[ScopeDimension] = Field(description=_SCOPE)
    version: ObligationVersionRef | None = Field(
        description=(
            "The version of the summary in force on the date the list was read, by number "
            "and effective date. Null when every version of this duty starts after that "
            "date, which is a duty recorded before it begins to bind anyone."
        )
    )
    upcoming_version: ObligationVersionRef | None = Field(
        description=(
            "The next version due to take effect after the date the list was read, so a row "
            "can say new wording is coming. Null when none is waiting. Its presence is not "
            "work the bank owes: what to do about a change belongs to the watch feed and "
            "the case, never to the library record."
        )
    )
    in_footprint: bool = Field(description=_IN_FOOTPRINT, examples=[True])
    outside_reason: list[OutsideReason] = Field(description=_OUTSIDE_REASON)
    last_verified_at: datetime.datetime | None = Field(
        description=(
            "When a bleqq library editor last read this record against its public source "
            "and found it unchanged, as a UTC timestamp; a screen shows it as \"Verified "
            "<date>\" in the bank's own time zone. Null on a record nobody has confirmed "
            "that way. It is not the date the record last changed, and it is not the bank's "
            "own review date."
        ),
        examples=["2026-06-30T07:12:44Z"],
    )
    open_change_count: int = Field(
        description=(
            "How many regulatory changes touching this duty are still open in the bank's "
            "watch feed, so a row can carry \"N open changes\". The watch overlay is not "
            "wired into this list yet, so every row answers 0 until it is: read a 0 here as "
            "\"not counted on this row\" rather than as \"nothing open\", and read the watch "
            "feed for the real number."
        ),
        examples=[0],
    )
    pending_applicability: bool | None = Field(
        description=(
            "Whether a change to this duty's applicability is waiting for a second person in "
            "this bank to approve it. Null means the question is not answered on this row, "
            "never that the answer is no: the applicability register arrives in a later "
            "release and every row answers null until it does."
        )
    )
    compliance_status: LibraryRef | None = Field(
        description=(
            "How the bank has judged its own compliance with this duty, as key, kind and "
            "label. This is the bank's own judgement, held in its own zone and never shared "
            "with another bank, and it is a different fact from whether the duty applies at "
            "all. The statuses are vocabulary rows the bank's own admin may extend, relabel "
            "or retire without a deploy, so read `GET /vocab/compliance_status` for the live "
            "set and match on the key; `compliant`, `partly_compliant`, `gap` and "
            "`not_assessed` are seeded on day one, each carrying its fixed category as its "
            "kind. Null until the compliance register arrives in a later release."
        )
    )

    # A row is validated again when the page takes it, so a row built any other way than
    # through this constructor still never reaches the wire unchecked.
    model_config = ConfigDict(revalidate_instances="always")


# One obligation of FFFS 2017:2 as the seeded sample library holds it (the research payment
# duty, with version 2 waiting for 1 October 2026), used as the example of a row, a card and
# a diff. Sample data throughout: no bank in it is real.
_SAMPLE_SCOPE: list[Any] = [
    {
        "dimension": {"key": "regime", "kind": None, "label": "Regime"},
        "terms": [{"key": "securities", "kind": None, "label": "Securities"}],
        "allSelected": False,
    },
    {
        "dimension": {"key": "legal_entity", "kind": None, "label": "Legal entity type"},
        "terms": [{"key": "bank", "kind": None, "label": "Bank"}],
        "allSelected": False,
    },
    {
        "dimension": {"key": "service_type", "kind": None, "label": "Service"},
        "terms": [
            {"key": "advice", "kind": None, "label": "Advice"},
            {"key": "portfolio_management", "kind": None, "label": "Portfolio management"},
        ],
        "allSelected": False,
    },
    {
        "dimension": {"key": "account_type", "kind": None, "label": "Account type"},
        "terms": [
            {"key": "isk", "kind": None, "label": "ISK"},
            {"key": "af", "kind": None, "label": "AF"},
            {"key": "depa", "kind": None, "label": "Depå"},
            {"key": "kf", "kind": None, "label": "KF"},
        ],
        "allSelected": False,
    },
    {
        "dimension": {"key": "client_category", "kind": None, "label": "Client category"},
        "terms": [
            {"key": "retail", "kind": None, "label": "Retail"},
            {"key": "professional", "kind": None, "label": "Professional"},
        ],
        "allSelected": True,
    },
    {
        "dimension": {"key": "channel", "kind": None, "label": "Channel"},
        "terms": [],
        "allSelected": False,
    },
    {
        "dimension": {"key": "lifecycle_stage", "kind": None, "label": "Lifecycle stage"},
        "terms": [{"key": "ongoing", "kind": None, "label": "Ongoing"}],
        "allSelected": False,
    },
]

_SAMPLE_TITLE: dict[str, Any] = {
    "text": "Pay for third-party research only under the permitted models",
    "language": "en",
    "isOriginal": True,
    "isMachine": False,
}

_SAMPLE_TAGS: list[Any] = [
    {"key": "research", "kind": None, "label": "research"},
    {"key": "inducements", "kind": None, "label": "inducements"},
    {"key": "third_party_payments", "kind": None, "label": "third-party payments"},
]

# Version 1 was seeded; version 2 was proposed by the watch agent and confirmed by an
# independent agent, so it reads machine-confirmed wherever it appears (INV-05, D-62).
_SAMPLE_SEEDED: dict[str, Any] = {"verifiedOrigin": "", "confirmedByAgent": None, "proposedByAgent": None}
_SAMPLE_BY_AGENTS: dict[str, Any] = {
    "verifiedOrigin": "agent",
    "confirmedByAgent": {"id": "2f7a9c14-3b8e-4d61-9a05-c8e1f4b27d93", "key": "library-confirmer"},
    "proposedByAgent": {"id": "6d1e4f8a-9c3b-4a7e-8f21-1b6d4c8a2e05", "key": "watch-sweeper"},
}

_SAMPLE_ROW: dict[str, Any] = {
    "id": "7c1f0b3e-52a4-4f9e-8a21-6d4b2c0a9e17",
    "stableKey": "obl-research-payments",
    "refLabel": "Third-party payments",
    "title": _SAMPLE_TITLE,
    "instrument": {"key": "fffs-2017-2", "shortName": "FFFS 2017:2"},
    "bindingLevel": {"key": "authority_regulation", "kind": None, "label": "Supervisory regulation"},
    "binding": True,
    "dutyType": {"key": "governance", "kind": None, "label": "Governance"},
    "tags": _SAMPLE_TAGS,
    "scope": _SAMPLE_SCOPE,
    "version": {**_SAMPLE_SEEDED, "versionNumber": 1, "effectiveFrom": None},
    "upcomingVersion": {**_SAMPLE_BY_AGENTS, "versionNumber": 2, "effectiveFrom": {"date": "2026-10-01", "precision": "day"}},
    "inFootprint": True,
    "outsideReason": [],
    "lastVerifiedAt": "2026-06-30T07:12:44Z",
    "openChangeCount": 0,
    "pendingApplicability": None,
    "complianceStatus": None,
}


class ObligationPage(LibraryResponse):
    """One page of `GET /obligations`: the rows, and how many rows the filters match in
    all."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_SAMPLE_ROW], "total": 14}]})

    items: list[ObligationRow] = Field(
        description=(
            "The duties on this page, ordered by their stable key so that paging through "
            "them is repeatable. An empty list is an ordinary 200 and means nothing matched "
            "the filters, never that something went wrong."
        )
    )
    total: int = Field(
        description=(
            "How many duties match the filters in all, not how many are on this page: what a "
            "screen reads to say \"20 of 137\". It is counted at the moment of the call, so "
            "a record written between two pages can move it."
        ),
        examples=[14],
    )


class ObligationVersionRow(VersionConfirmation):
    """One summary version on the card's version list (INV-04): when it took effect,
    `effectiveTo` derived as the day before the next version did, when the proposal that
    wrote it was approved, and who confirmed that approval (the three fields of
    `VersionConfirmation`, INV-05). A person who approved is never named here; an agent
    that confirmed is named by its definition key."""

    version_number: int = Field(
        description=(
            "Which version of this duty's summary it is, numbered from 1 in the order the "
            "versions took effect. It is the number to send to the diff as `from` or `to`, "
            "and it never addresses another obligation's version."
        ),
        examples=[1],
    )
    effective_from: PartialDate | None = Field(
        description=(
            "The legal date this version started binding the bank, at the precision the "
            "source gave it. Null means it has been in force since the obligation entered "
            "the library. "
            f"{LIBRARY_FACT}"
        )
    )
    effective_to: PartialDate | None = Field(
        description=(
            "The last day this version was in force, worked out as the day before the next "
            "version took effect: nothing is stored, because a version row is written once "
            "and never touched afterwards. Null on the version still in force, on one whose "
            "successor carries no date, and on one corrected the same day it took effect."
        )
    )
    approved_at: datetime.datetime | None = Field(
        description=(
            "When the proposal that wrote this version was approved, as a UTC timestamp, by "
            "a person or by an independent agent: `verifiedOrigin` says which. Null on a "
            "version the library was seeded with rather than proposed. It is the moment of "
            "the decision, never the date the wording takes effect, which is `effectiveFrom`. "
            "A person who approved is not named on this card."
        ),
        examples=["2026-09-15T14:02:11Z"],
    )


class ObligationInstrumentSummary(LibraryResponse):
    """The instrument an obligation belongs to, as "Where it comes from" reads it (INV-01).
    Its provisions and lineage live on the instrument's own read."""

    key: str = Field(
        description=(
            "The instrument's stable key, the value to store and to send back as "
            "`?instrument=`. It is issued once and never changes, however the instrument is "
            "renamed or amended. "
            f"{LIBRARY_FACT}"
        ),
        examples=["fffs-2017-2"],
    )
    short_name: str = Field(
        description=(
            "How the instrument is written on a pill or in a column, in its own language. A "
            "label a person wrote and may reword, so show it and match on `key` instead."
        ),
        examples=["FFFS 2017:2"],
    )
    name: LocalizedText | None = Field(
        description=(
            "The instrument's full name, in the best language this reader can be served. "
            "The original is the jurisdiction's legal language, so a Swedish regulation read "
            "in English usually still answers its Swedish name rather than a translation. "
            "Null only when the record carries no name in any language."
        )
    )
    official_ref: str = Field(
        description=(
            "The reference the issuing authority itself publishes the instrument under, "
            "written as that authority writes it. It is how a lawyer cites the instrument "
            "and how a reader recognises it on the authority's own site; it is not an "
            "identifier this API accepts, which is `key`."
        ),
        examples=["FFFS 2017:2"],
    )
    implements_note: str = Field(
        description=(
            "What this instrument implements or elaborates, in the library's own words, so a "
            "reader can see where a Swedish rule comes from. Free text for a person and "
            "never a machine-readable link; an empty string when nothing was recorded, never "
            "null. The structured lineage between instruments lives on the instrument's own "
            "read."
        ),
        examples=["MiFID II delegated directive (EU) 2017/593"],
    )


class ObligationProvisionRef(LibraryResponse):
    """A provision the obligation cites (INV-02, INV-03), by reference and path. The
    verbatim text is the provision tree's, never this read's."""

    id: UUID = Field(
        description=(
            "The provision's identifier in the shared library, as a UUID: what the provision "
            "tree is read by. "
            f"{LIBRARY_FACT}"
        ),
        examples=["b6d9f0a4-1c72-4e35-9f88-0a2c4e6b8d10"],
    )
    ref_label: str = Field(
        description=(
            "How the provision is cited, in the words the source itself uses: `9 kap. 6 §` "
            "in a Swedish regulation, `Article 25(3)` in an EU one. For a reader to quote, "
            "not a reference to parse."
        ),
        examples=["9 kap. 6 §"],
    )
    path: str = Field(
        description=(
            "Where the provision sits in its instrument's structure, read from the top, so a "
            "reader can place the citation without opening the tree. It is a breadcrumb a "
            "person reads and may be relabelled; cite the provision by `id`. The verbatim "
            "legal text is not here: it belongs to the provision tree, version by version."
        ),
        examples=["FFFS 2017:2 > 9 kap. > 6 §"],
    )


class RelatedObligation(LibraryResponse):
    """An obligation a reader should see beside this one (INV-03), with the relation as a
    vocabulary row."""

    id: UUID = Field(description=_OBLIGATION_ID, examples=["1d8c5a09-6b47-4e21-8f3a-0c7e2b4d9a63"])
    title: LocalizedText | None = Field(description=_OBLIGATION_TITLE)
    instrument: ObligationInstrumentRef = Field(
        description="Which instrument the related duty was broken out of, by key and short name."
    )
    binding: bool = Field(description=_BINDING, examples=[True])
    relation: LibraryRef = Field(
        description=(
            "How the two duties are related, as key, kind and label: `implements` when this "
            "one puts the other into effect, `elaborates` when it spells the other out, and "
            "`related` when the library only says read them together. Those three are seeded "
            "on day one and they are vocabulary rows, not a closed set: a platform admin may "
            "extend, relabel or retire the list without a deploy, so read "
            "`GET /vocab/relation_type` for the live set and match on the key. A relation is "
            "the library's own cross-reference and never a statement that both duties reach "
            "this bank."
        )
    )


class ObligationProvenance(LibraryResponse):
    """Where the record came from and when it was last checked against its source (INV-06).
    `verifiedBy` is a platform person or null: a seeded record has never been re-verified.

    `verifiedOrigin`, `confirmedByAgent` and `proposedByAgent` (INV-05, PRO-02, D-62) are
    other facts: who confirmed the approval that wrote the version in force on the read's
    date, and which agent proposed it, the same three `version` carries. The proposer and
    the confirmer are independent, so all four pairings occur: `agent` with both agents
    named, `agent` with only `confirmedByAgent` (a person proposed and an agent confirmed),
    `user` with only `proposedByAgent` (a person approved an agent's proposal) and `user`
    with neither. Decide the machine-confirmed label from `verifiedOrigin` alone. This
    answer applies no rule of its own: a person's re-verification is `verifiedBy` and
    `lastVerifiedAt`, and a screen reads one later than the version's `approvedAt` as
    superseding the machine-confirmed label."""

    created_origin: str = Field(
        description=(
            "Who drafted this record: `user` when a person wrote it, `agent` when a research "
            "agent proposed it. Either way it entered the library through a proposal a "
            "second, independent principal approved, so `agent` does not mean a machine "
            "wrote straight into the library."
        ),
        examples=["agent"],
    )
    created_model: str = Field(
        description=(
            "Which model drafted the record, under the name it is published as, when an "
            "agent did. An empty string when a person wrote it, never null. It labels the "
            "draft's origin and makes no claim about how accurate the record is; a person "
            "still approved it."
        ),
        examples=["agent pipeline 0.4"],
    )
    created_at: datetime.datetime = Field(
        description=(
            "When the record was first written into the library, as a UTC timestamp. It is "
            "not the date the rule began to bind anyone: that is the version's effective "
            "date, which can be years earlier."
        ),
        examples=["2026-02-11T08:45:03Z"],
    )
    verified_by: PersonRef | None = Field(
        description=(
            "The bleqq platform person who last confirmed this record against its source, by "
            "id and name, or null when nobody has. Never a member of a bank: re-verifying a "
            "shared fact is bleqq's own check, and a bank reading the record leaves nothing "
            "here."
        )
    )
    last_verified_at: datetime.datetime | None = Field(
        description=(
            "When that check was made, as a UTC timestamp, which is what a reader's "
            "\"Verified <date>\" shows. It says the source still read the same way on that "
            "date; it does not say the record's content was re-approved, and it is not the "
            "date the record last changed."
        ),
        examples=["2026-06-30T07:12:44Z"],
    )
    source_url: str = Field(
        description=(
            "The public page this record was taken from, so a reader can open it and a "
            "re-check can fetch it again. It is the authority's own page and never a link "
            "into this product."
        ),
        examples=["https://www.fi.se/en/published/regulations/2017/fffs-20172/"],
    )
    source_label: str = Field(
        description=(
            "What that page is called, in the words a reader recognises, down to the place "
            "in it the record came from. A label for a person, not a citation a machine "
            "resolves."
        ),
        examples=["FFFS 2017:2, 9 kap. 6 §"],
    )
    verified_origin: str = Field(
        default="",
        description=(
            "Who confirmed the approval that wrote the version in force on the read's date: "
            "`agent` when the reviewer was a second, independent agent, `user` when a person "
            "approved it. Empty for a version the library was seeded with or applied before "
            "this was recorded, and when no version is in force, which reads the same as "
            "`user`: a person's approval, unlabelled. Never confuse this with `verifiedBy`, "
            "which is a later re-verification."
        ),
        examples=["agent"],
    )
    confirmed_by_agent: AgentRef | None = Field(
        default=None,
        description=(
            "The independent agent that confirmed the approval, by definition key, when "
            "`verifiedOrigin` is `agent`. Null when a person approved it."
        ),
    )
    proposed_by_agent: AgentRef | None = Field(
        default=None,
        description=(
            "The agent that proposed the version in force, by definition key, read from the "
            "approved proposal. Null whenever the proposer was not a key bound to an agent, "
            "which is every proposal a person made, whoever confirmed it. It is independent "
            "of `verifiedOrigin`: `agent` with this null means a person proposed what an "
            "agent confirmed, and `user` with this set means a person approved an agent's "
            "proposal."
        ),
    )


_SAMPLE_SUMMARY_SV = (
    "Investeringsanalys från tredje part får tas emot endast om den betalas med institutets "
    "egna medel, från ett analyskonto, eller gemensamt med orderutförande enligt de villkor "
    "som anges i reglerna."
)
_SAMPLE_SUMMARY_EN = (
    "Research from third parties may be received only if it is paid from the institution's "
    "own resources, from a research payment account, or jointly with execution under the "
    "conditions set out in the rules."
)
_SAMPLE_DETAIL: dict[str, Any] = {
    **{key: _SAMPLE_ROW[key] for key in ("id", "stableKey", "refLabel", "title")},
    "instrument": {
        "key": "fffs-2017-2",
        "shortName": "FFFS 2017:2",
        "name": {
            "text": "FFFS 2017:2 om värdepappersrörelse",
            "language": "sv",
            "isOriginal": True,
            "isMachine": False,
        },
        "officialRef": "FFFS 2017:2",
        "implementsNote": "MiFID II delegated directive (EU) 2017/593",
    },
    "regime": {"key": "securities", "kind": None, "label": "Securities"},
    "bindingLevel": _SAMPLE_ROW["bindingLevel"],
    "binding": True,
    "dutyType": _SAMPLE_ROW["dutyType"],
    "triggerFrequency": "Annual assessment from 1 October 2026",
    "retention": "5 years",
    "sanctionExposure": "FI remark, warning or sanction fee",
    "productScope": "Third-party research",
    "tags": _SAMPLE_TAGS,
    "scope": _SAMPLE_SCOPE,
    "inFootprint": True,
    "outsideReason": [],
    "summary": {"text": _SAMPLE_SUMMARY_EN, "language": "en", "isOriginal": False, "isMachine": True},
    "translations": [
        {"text": _SAMPLE_SUMMARY_SV, "language": "sv", "isOriginal": True, "isMachine": False},
        {"text": _SAMPLE_SUMMARY_EN, "language": "en", "isOriginal": False, "isMachine": True},
    ],
    "version": {
        **_SAMPLE_SEEDED,
        "versionNumber": 1,
        "effectiveFrom": None,
        "effectiveTo": {"date": "2026-09-30", "precision": "day"},
        "approvedAt": None,
    },
    "versions": [
        {
            **_SAMPLE_SEEDED,
            "versionNumber": 1,
            "effectiveFrom": None,
            "effectiveTo": {"date": "2026-09-30", "precision": "day"},
            "approvedAt": None,
        },
        {
            **_SAMPLE_BY_AGENTS,
            "versionNumber": 2,
            "effectiveFrom": {"date": "2026-10-01", "precision": "day"},
            "effectiveTo": None,
            "approvedAt": "2026-09-15T14:02:11Z",
        },
    ],
    "provisions": [
        {
            "id": "b6d9f0a4-1c72-4e35-9f88-0a2c4e6b8d10",
            "refLabel": "9 kap. 6 §",
            "path": "FFFS 2017:2 > 9 kap. > 6 §",
        }
    ],
    "related": [
        {
            "id": "1d8c5a09-6b47-4e21-8f3a-0c7e2b4d9a63",
            "title": {
                "text": "Disclose all costs and charges before and after the service",
                "language": "en",
                "isOriginal": True,
                "isMachine": False,
            },
            "instrument": {"key": "fffs-2017-2", "shortName": "FFFS 2017:2"},
            "binding": True,
            "relation": {"key": "related", "kind": None, "label": "Related"},
        }
    ],
    "provenance": {
        "createdOrigin": "agent",
        "createdModel": "agent pipeline 0.4",
        "createdAt": "2026-02-11T08:45:03Z",
        "verifiedBy": {"id": "0a2e6b81-5f4d-4a3b-9c77-1d8e3f5a6c20", "name": "Johan Ek"},
        "lastVerifiedAt": "2026-06-30T07:12:44Z",
        "sourceUrl": "https://www.fi.se/en/published/regulations/2017/fffs-20172/",
        "sourceLabel": "FFFS 2017:2, 9 kap. 6 §",
        # The version in force is version 1, which was seeded: no approval, so no one confirmed it.
        **_SAMPLE_SEEDED,
    },
}


class ObligationDetail(LibraryResponse):
    """`GET /obligations/{obligationId}` (INV-03..INV-06): the duty as of a date, with its
    facets, every version, the provisions it cites, the obligations beside it and its
    provenance. The register overlay lands with chunk 8, the related changes with chunk 5."""

    model_config = ConfigDict(json_schema_extra={"examples": [_SAMPLE_DETAIL]})

    id: UUID = Field(description=_OBLIGATION_ID, examples=["7c1f0b3e-52a4-4f9e-8a21-6d4b2c0a9e17"])
    stable_key: str = Field(description=_OBLIGATION_STABLE_KEY, examples=["obl-research-payments"])
    ref_label: str = Field(description=_OBLIGATION_REF_LABEL, examples=["Third-party payments"])
    title: LocalizedText | None = Field(description=_OBLIGATION_TITLE)
    instrument: ObligationInstrumentSummary = Field(
        description=(
            "Where the duty comes from: the instrument it was broken out of, with the "
            "reference the authority publishes it under and what it implements. Its "
            "provision tree and its lineage to other instruments live on the instrument's "
            "own read."
        )
    )
    regime: LibraryRef | None = Field(
        description=(
            "Which body of law the duty belongs to, as a term of the taxonomy's `regime` "
            "dimension: `securities`, `insurance`, `tax`, `data_protection`, `aml`, "
            "`ai_ict`, `banking` and `payments` are seeded on day one. It is inherited from "
            "the instrument, which is where the sector boundary is set, and it is null only "
            "while an instrument carries none. The terms are vocabulary rows a platform "
            "admin may extend or retire without a deploy, so read `GET /taxonomy/terms` for "
            "the live set and match on the key."
        )
    )
    binding_level: LibraryRef = Field(description=_BINDING_LEVEL)
    binding: bool = Field(description=_BINDING, examples=[True])
    duty_type: LibraryRef = Field(description=_DUTY_TYPE)
    trigger_frequency: str = Field(
        description=(
            "When the duty bites, in the library's own words. Free text for a person to "
            "read, never a schedule a machine can act on, and an empty string when nothing "
            "was recorded rather than null. It says when the rule applies, never when this "
            "bank has to do anything."
        ),
        examples=["Annual assessment from 1 October 2026"],
    )
    retention: str = Field(
        description=(
            "How long the records behind this duty have to be kept, as the source puts it. "
            "Free text, an empty string when nothing was recorded. It is the rule's own "
            "retention period and has nothing to do with how long this product keeps the "
            "bank's data."
        ),
        examples=["5 years"],
    )
    sanction_exposure: str = Field(
        description=(
            "What the authority may do where the duty is not met, in the library's words. "
            "Free text, an empty string when nothing was recorded. It describes the rule's "
            "exposure in general and is not this bank's own risk rating or an assessment of "
            "anything it has done."
        ),
        examples=["FI remark, warning or sanction fee"],
    )
    product_scope: str = Field(
        description=(
            "Which products the duty covers, in the library's words, for a reader who wants "
            "the sentence rather than the facets. Free text, an empty string when nothing "
            "was recorded; the scope a filter can act on is `scope`, and the two are written "
            "separately."
        ),
        examples=["Third-party research"],
    )
    tags: list[LibraryRef] = Field(description=_TAGS)
    scope: list[ScopeDimension] = Field(description=_SCOPE)
    in_footprint: bool = Field(description=_IN_FOOTPRINT, examples=[True])
    outside_reason: list[OutsideReason] = Field(description=_OUTSIDE_REASON)
    summary: LocalizedText | None = Field(
        description=(
            "The duty in plain language as the version in force on the read's date words "
            "it, in the best language this reader can be served. Null when that version "
            "carries no summary in any language, or when no version is in force on the date "
            "asked for."
        )
    )
    translations: list[LocalizedText] = Field(
        description=(
            "Every language the version in force holds its summary in, so a screen can offer "
            "\"Show original\" and label what a machine translated. `summary` is the one of "
            "these picked for this reader; the list is the same for everyone."
        )
    )
    version: ObligationVersionRow | None = Field(
        description=(
            "The version in force on the date the record was read, with the dates it runs "
            "between. Null when every version starts after that date."
        )
    )
    versions: list[ObligationVersionRow] = Field(
        description=(
            "Every version of this duty in version order, including the ones still to take "
            "effect, so a reader can see the whole history and ask for a diff between any "
            "two. Nothing here is ever rewritten: a correction is another version."
        )
    )
    provisions: list[ObligationProvisionRef] = Field(
        description=(
            "The provisions of the instrument this duty was drawn from, as citations. An "
            "empty list means no provision was cited, not that the duty is unsourced: "
            "`provenance` still names the page it came from. The verbatim legal text is not "
            "here; it lives in the provision tree."
        )
    )
    related: list[RelatedObligation] = Field(
        description=(
            "The duties a reader should see beside this one, as the library files them. "
            "Only records this caller may read appear: a relation to one they may not is "
            "left out silently rather than hinted at."
        )
    )
    provenance: ObligationProvenance = Field(
        description=(
            "Where this record came from and when a person last held it against its source: "
            "the sourcing a bank's own reviewer, and a vendor review, asks for."
        )
    )


class DiffSegment(LibraryResponse):
    """One sentence of a diff and what happened to it (AC-INV1)."""

    op: str = Field(
        description=(
            "What became of this sentence between the two versions. `equal` means it stands "
            "unchanged in both. `delete` means the older version had it and the newer one "
            "does not. `insert` means the newer version adds it. A reworded sentence appears "
            "twice, once as `delete` and once as `insert`; there is no \"changed\", so a "
            "reader must not take a delete on its own as a duty being dropped."
        ),
        examples=["insert"],
    )
    text: str = Field(
        description=(
            "The sentence itself, in the language the diff names, as plain text with no "
            "markup: a screen colours it by `op`. Where a summary is longer than the server "
            "will split sentence by sentence, one segment holds the whole text instead of a "
            "sentence, which is coarser but still correct."
        ),
        examples=["The institution sets criteria for an annual assessment of the research it uses."],
    )


_SAMPLE_DIFF: dict[str, Any] = {
    "fromVersion": 1,
    "toVersion": 2,
    "fromEffective": None,
    "toEffective": {"date": "2026-10-01", "precision": "day"},
    "fromConfirmation": _SAMPLE_SEEDED,
    "toConfirmation": _SAMPLE_BY_AGENTS,
    "language": "en",
    "isMachine": True,
    "segments": [
        {"op": "equal", "text": _SAMPLE_SUMMARY_EN},
        {
            "op": "insert",
            "text": (
                "The institution sets criteria for an annual assessment of the quality, "
                "usability and value of the research it uses."
            ),
        },
        {
            "op": "insert",
            "text": (
                "If the research does not contribute to better investment decisions, the "
                "institution takes corrective action."
            ),
        },
    ],
}


class VersionDiff(LibraryResponse):
    """"Show what changed" between two versions (INV-04, AC-INV1, INV-05): the two version
    numbers, the dates they took effect and who confirmed each one's approval, the language
    both versions have and whether a machine translated it, and the sentences. Serves
    obligations and provisions."""

    model_config = ConfigDict(json_schema_extra={"examples": [_SAMPLE_DIFF]})

    from_version: int = Field(
        description=(
            "The number of the version the comparison starts from. Both numbers belong to "
            "the same obligation: this call compares two versions of one record and never "
            "one record with another."
        ),
        examples=[1],
    )
    to_version: int = Field(
        description=(
            "The number of the version the comparison ends at, again a version of the same "
            "obligation."
        ),
        examples=[2],
    )
    from_effective: PartialDate | None = Field(
        description=(
            "The legal date the older version started binding the bank, so a screen can name "
            "the two dates being compared. Null when that version has been in force since "
            "the obligation entered the library."
        )
    )
    to_effective: PartialDate | None = Field(
        description=(
            "The legal date the newer version starts binding the bank. It may be in the "
            "future, which is a change already approved and not yet in force; that is not by "
            "itself work this bank owes."
        )
    )
    from_confirmation: VersionConfirmation | None = Field(
        description=(
            "Who confirmed the approval that wrote the older version, and which agent "
            "proposed it, so wording an independent agent confirmed is labelled "
            "machine-confirmed on either side of the comparison (INV-05). Null on a "
            "provision's diff: a provision's text versions record no approval of their own."
        )
    )
    to_confirmation: VersionConfirmation | None = Field(
        description=(
            "The same for the newer version, whose words are the ones a reader is weighing "
            "when a change is assessed, and which may not be in force yet. Null on a "
            "provision's diff, for the same reason."
        )
    )
    language: str = Field(
        description=(
            "Which content language the two summaries were compared in, as a language key "
            "that `GET /reference/languages` lists. It is the first language both versions "
            "hold, preferring the `lang` asked for, then the reader's own order, then an "
            "original over a translation — so it may not be the language that was asked for."
        ),
        examples=["en"],
    )
    is_machine: bool = Field(
        description=(
            "True when either side of the comparison is a machine translation nobody has "
            "confirmed, so a screen must label the whole diff as machine-made (INV-05). It "
            "does not say the difference is wrong; it says the words compared are not the "
            "ones that govern, which are the original's."
        ),
        examples=[True],
    )
    segments: list[DiffSegment] = Field(
        description=(
            "The comparison itself, sentence by sentence in reading order, so the unchanged "
            "sentences are there as well as the changed ones. Empty only when both versions' "
            "summaries are empty in that language."
        )
    )


_AS_OF = (
    "Read the record as it stood on this date, as a plain calendar date such as "
    "`2026-06-30`: the answer carries the version in force on it, which is the version with "
    "the latest effective date on or before it. It defaults to today in the bank's own time "
    "zone and not the caller's, so two people in one bank always read the same day. Reading "
    "as of a future date shows wording that does not bind yet, and is never itself a "
    "statement that the bank has something to do."
)


class ObligationAsOfQuery(CamelSchema):
    """`asOf` on the obligation read: the version in force on that date, today in the
    tenant's time zone by default (AC-INV1)."""

    as_of: datetime.date | None = Field(
        default=None,
        description=(
            f"{_AS_OF} A date before the record's first version answers the record with a "
            "null `version` and a null `summary` rather than a 404."
        ),
        examples=["2026-06-30"],
    )


class VersionDiffQuery(CamelSchema):
    """`from` and `to` are version numbers, defaulting to the latest version against the one
    before it. `lang` asks for a language; the diff falls back to the reader's language
    order when neither version has it (INV-05). Serves the obligation diff and the
    provision diff alike (chunk3-rest-T16): both compare two versions of one record and
    never one record with another."""

    from_version: int | None = Field(
        default=None,
        alias="from",
        ge=1,
        description=(
            "Which version to compare from, by its version number, 1 at the lowest. It "
            "defaults to the version before the latest one, so a plain call shows the most "
            "recent change. Both versions are versions of the same record: there is no "
            "comparison across records. A number this record has no version for is "
            "refused with 422 `unknown_key`."
        ),
        examples=[1],
    )
    to_version: int | None = Field(
        default=None,
        alias="to",
        ge=1,
        description=(
            "Which version to compare to, by its version number, 1 at the lowest. It "
            "defaults to the latest version the record has, including one that has been "
            "approved and does not take effect until later. A number this record has no "
            "version for is refused with 422 `unknown_key`."
        ),
        examples=[2],
    )
    lang: str | None = Field(
        default=None,
        max_length=MAX_LANGUAGE_LENGTH,
        description=(
            "Which content language to compare in, as a language key of at most 8 "
            "characters such as `sv` or `en`. It is a preference and never a filter: a key "
            "the two versions do not both hold is not an error, and the diff falls back to "
            "the reader's own language order and then to an original before a translation, "
            "saying in `language` what it settled on. A key longer than 8 characters is "
            "refused with 422 `validation_error`, and two versions with no language in "
            "common answer 422 because there is nothing to compare."
        ),
        examples=["en"],
    )


class ObligationQuery(CamelSchema):
    """The filters of `GET /obligations`. `instrument` and `dutyType` are keys; `term` is
    `dimension:key` and repeats, every term must be in the obligation's scope. `asOf`
    defaults to today in the tenant's time zone. `outsideFootprint=true` lifts the
    footprint filter and reports why each hidden row would be hidden."""

    instrument: str | None = Field(
        default=None,
        description=(
            "Only the duties broken out of this instrument, by the instrument's stable key: "
            "`fffs-2017-2` for FFFS 2017:2. A key no instrument has is not an error — it "
            "matches nothing, and the call answers 200 with an empty page."
        ),
        examples=["fffs-2017-2"],
    )
    duty_type: str | None = Field(
        default=None,
        description=(
            "Only the duties of this kind, by the duty type's key. `conduct`, `disclosure`, "
            "`record_keeping`, `reporting`, `governance` and `technical` are seeded on day "
            "one, and they are vocabulary rows rather than a closed set: a platform admin "
            "may extend, relabel or retire the list without a deploy. Read "
            "`GET /vocab/duty_type` for the live set and send the key, never the label. A "
            "key no duty type has matches nothing and answers 200 with an empty page."
        ),
        examples=["governance"],
    )
    term: list[str] = Field(
        default_factory=list,
        max_length=settings.LIBRARY_TERM_FILTER_MAX,
        description=(
            "Only the duties whose scope carries every one of these terms, each written "
            "`dimension:key`. Repeat the parameter for more than one; they are combined "
            "with AND, and at most 20 are accepted "
            "(`LIBRARY_TERM_FILTER_MAX`). The terms are taxonomy vocabulary rows a platform "
            "admin may extend or retire without a deploy, so read `GET /taxonomy/terms` for "
            "the live set and match on the key. A value with no colon is refused with 422 "
            "`validation_error`, and one that names no active term with 422 `unknown_key` "
            "naming every term that was not found."
        ),
        examples=[["service_type:advice", "account_type:isk"]],
    )
    q: str | None = Field(
        default=None,
        max_length=MAX_QUERY_LENGTH,
        description=(
            "Find the duties whose title or citation contains these words, ignoring case: a "
            "phrase to look for, never a document. At most 200 characters "
            "(`MAX_QUERY_LENGTH`); a longer one is refused with 422 `validation_error`. It "
            "narrows this list and is not the product's search: ranking, synonyms and the "
            "text of the summaries belong to `GET /search`."
        ),
        examples=["research"],
    )
    as_of: datetime.date | None = Field(
        default=None,
        description=(
            f"{_AS_OF} On the list it changes which wording each row carries, never which "
            "duties are listed."
        ),
        examples=["2026-06-30"],
    )
    outside_footprint: bool = Field(
        default=False,
        description=(
            "Whether to include the duties the bank's footprint would otherwise hide, each "
            "saying in `outsideReason` why it would be hidden. It is false by default, which "
            "is the working inventory: only the duties whose scope overlaps the footprint. "
            "Set it to true to review the boundary itself — a duty that appears only this "
            "way is not one the bank has decided applies to it."
        ),
        examples=[False],
    )


# ---------------------------------------------------------------------------------------
# Writes on a record (INV-06)
# ---------------------------------------------------------------------------------------
class ProblemReportBody(WriteBody):
    """"This looks wrong" (INV-06). `description` is what the reader believes is wrong;
    `versionNumber` and `language` say which words were on their screen, so a colleague
    opens the same ones. The subject is the path, and the bank is the reader's session:
    neither is ever taken from the body."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "description": (
                    "The retention line says the records are kept for five years, but FFFS 2017:2 "
                    "9 kap. 6 § says ten."
                ),
                "versionNumber": 2,
                "language": "sv",
            }
        }
    )

    description: str = Field(
        min_length=1,
        max_length=settings.LIBRARY_REPORT_TEXT_MAX_CHARS,
        description=(
            "What the reader believes is wrong with this record, in their own words. This is the "
            "bank's own content, not a library fact: it is stored inside the bank that filed it and "
            "reaches nobody outside it, bleqq included, and it is kept out of the audit row, the "
            "outbox payload, the logs and every model prompt. At most 4000 characters "
            "(`LIBRARY_REPORT_TEXT_MAX_CHARS`); a longer one is refused, and so is one that is only "
            "whitespace."
        ),
    )
    version_number: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Which version of the summary the reader had on screen, numbered from 1 in the order the "
            "versions took effect, so a colleague opens the same words rather than today's. The "
            "default is none, for a screen that showed no particular version. It records what was "
            "read and is not checked against the record, so it never changes what the server stores."
        ),
    )
    language: str | None = Field(
        default=None,
        max_length=MAX_LANGUAGE_LENGTH,
        description=(
            "Which content language the reader was reading, as a language key of at most 8 "
            "characters such as `sv` or `en`. The content languages are library vocabulary rows "
            "that a platform admin may extend or retire, so read `GET /reference/languages` for the "
            "live set, and send the key rather than the label. The default is none, for a screen "
            "that showed no particular language; a key that is not an active content language is "
            "refused."
        ),
    )


class ProblemReportCreated(LibraryResponse):
    """The acknowledgement the reader sees: the report exists, it is open, and this is when
    it was filed. What they wrote is not sent back; it is in the row, and the screen it was
    typed on still has it."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "6f4c1f3e-9a21-4c8e-9a2f-2b0d5c7a1e44",
                "status": "open",
                "createdAt": "2026-09-20T09:14:22Z",
            }
        }
    )

    id: UUID = Field(
        description=(
            "The identifier of the report that was just filed, as a UUID a colleague in the same "
            "bank can quote. It addresses a row that lives in that bank's own zone: nobody outside "
            "the bank, bleqq included, can read what it points at."
        )
    )
    status: str = Field(
        description=(
            "Where the report stands. A new one is always `open`, meaning it has been filed and "
            "nobody has answered it. The other three arrive later, when the bank works it: "
            "`answered` when a colleague replied without the library changing, `fixed` when the "
            "library record was corrected, and `rejected` when the bank decided the record was "
            "right after all."
        )
    )
    created_at: datetime.datetime = Field(
        description=(
            "When the report was filed, as a UTC timestamp. The screen shows it in the bank's own "
            "time zone; the stored value is always UTC."
        )
    )


class ReverificationBody(WriteBody):
    """A check of a record against its source (INV-06, INV-S8). `outcome` is a
    VerificationOutcome key; the note says what the checker saw, and belongs to the check
    rather than to the record."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "outcome": "no_change",
                "note": "Read against FI's published text of FFFS 2017:2; 9 kap. 6 § is unchanged.",
            }
        }
    )

    outcome: str = Field(
        min_length=1,
        max_length=64,
        description=(
            "What the checker found when they read the record against its source, as one of three "
            "fixed keys of at most 64 characters. `no_change` means the source still says what the "
            "record says, and it is the only outcome that moves the stamp. `change_found` means the "
            "source has moved on; the check is filed and the stamp is left standing, because the "
            "correction itself has to arrive as a proposal. `source_unavailable` means the source "
            "could not be reached at all, so nothing was confirmed either way. Any other value is "
            "refused and nothing is written."
        ),
    )
    note: str = Field(
        default="",
        max_length=settings.LIBRARY_REPORT_TEXT_MAX_CHARS,
        description=(
            "What the checker saw, kept with the check and never copied onto the record: it reaches "
            "no summary, no title and no version, so it cannot become library text by accident. The "
            "default is an empty string, and it holds at most 4000 characters "
            "(`LIBRARY_REPORT_TEXT_MAX_CHARS`)."
        ),
    )


class VerificationCreated(LibraryResponse):
    """What the check recorded, and the stamp the record now carries. `lastVerifiedAt` and
    `verifiedBy` move only on `no_change`; any other outcome leaves the old stamp standing
    and the correction arrives as a proposal."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "b1a7d4c2-3e55-4a90-8d17-6c9f0e2a5b38",
                "outcome": "no_change",
                "verifiedAt": "2026-09-20T09:31:07Z",
                "lastVerifiedAt": "2026-09-20T09:31:07Z",
                "verifiedBy": {"id": "0a2e6b81-5f4d-4a3b-9c77-1d8e3f5a6c20", "name": "Johan Ek"},
            }
        }
    )

    id: UUID = Field(
        description=(
            "The identifier of the check that was just recorded, as a UUID. Every check is kept, "
            "not only the most recent one, so this row stays readable after a later check has "
            "replaced the stamp below."
        )
    )
    outcome: str = Field(
        description=(
            "The outcome that was recorded, echoed back: `no_change`, `change_found` or "
            "`source_unavailable`. Only `no_change` moved the stamp; on the other two the check was "
            "filed and the record was left exactly as it was."
        )
    )
    verified_at: datetime.datetime = Field(
        description=(
            "When this check was made, as a UTC timestamp. It is the time of the check and not of "
            "the stamp: a `change_found` check carries a time here and still leaves `lastVerifiedAt` "
            "where it was."
        )
    )
    last_verified_at: datetime.datetime | None = Field(
        description=(
            "The stamp the record now carries: when a person last confirmed it against its source, "
            "as a UTC timestamp, which is what a reader's \"Verified <date>\" shows. A library fact, "
            "moved by this one call and otherwise changed only through an approved proposal. It is "
            "null on a record nobody has ever confirmed, and it does not mean the record's content "
            "was approved here, only that the source still said the same thing on that date."
        )
    )
    verified_by: PersonRef | None = Field(
        description=(
            "Who backed the stamp with their passkey: a bleqq platform person, by id and name, and "
            "never a member of a bank, because re-verifying a shared fact is bleqq's own check. Null "
            "on a record nobody has ever confirmed, and left as it was when the outcome was not "
            "`no_change`."
        )
    )


# ---------------------------------------------------------------------------------------
# GET /instruments and GET /instruments/{instrumentId} (INV-01, INV-06, FP-03)
# ---------------------------------------------------------------------------------------
class InstrumentAuthorityRef(LibraryResponse):
    """The authority behind an instrument, as the row and the card both name it: a library
    fact, the same for every bank."""

    key: str = Field(
        description=(
            "The authority's immutable key, the value to store and to send back. It never "
            "changes; the name may be relabelled around it (playbook 4.3)."
        ),
        examples=["fi"],
    )
    name: str = Field(description="The authority's full name, as it names itself.", examples=["Finansinspektionen"])
    short_name: str = Field(
        description="How the authority is abbreviated in a pill or a column, in its own language.", examples=["FI"]
    )
    url: str = Field(description="The authority's own site, so a reader can open it.", examples=["https://www.fi.se/"])


_INSTRUMENT_SHORT_NAME = (
    "How the instrument is written on a pill or in a column, in its own language. A "
    "label a person wrote and may be reworded, so show it and match on `key` instead."
)
_INSTRUMENT_NAME = (
    "The instrument's full name, in the best language this reader can be served. The "
    "original is the jurisdiction's legal language, so a Swedish regulation read in "
    "English usually still answers its Swedish name rather than a translation. Null only "
    "when the record carries no name in any language."
)
_INSTRUMENT_LEVEL = (
    "What rank of instrument this is, as key, kind and label: how much weight it carries. "
    "The levels are vocabulary rows and not a closed set — a platform admin may extend, "
    "relabel or retire the list without a deploy — so read `GET /vocab/instrument_level` "
    "for the live set and match on the key; `eu_regulation`, `eu_directive`, "
    "`eu_guidance`, `act` and `authority_regulation` are seeded on day one."
)
_INSTRUMENT_JURISDICTION = (
    "Where the instrument applies, as `{key, kind, label}` from the jurisdiction vocabulary "
    "(`se`, `dk`, `no`, `fi` and `eu` among the rows seeded on day one). The values are rows "
    "an admin manages, not a closed set: a platform admin may extend, relabel or retire one "
    "without a deploy, so read `GET /reference/jurisdictions` for the live set and match on "
    "the key, never on the label. The `kind` says whether it is a country, a union or an "
    "international body."
)
_INSTRUMENT_REGIME = (
    "Which body of law the instrument belongs to, as a term of the taxonomy's `regime` "
    "dimension: `securities`, `insurance`, `tax`, `data_protection`, `aml`, `ai_ict`, "
    "`banking` and `payments` are seeded on day one. This is the sector boundary every "
    "instrument carries (playbook 4.3), and it is what an obligation's own scope "
    "inherits. Null only while an instrument carries none. The terms are vocabulary rows "
    "a platform admin may extend or retire without a deploy, so read "
    "`GET /taxonomy/terms` for the live set and match on the key."
)
_INSTRUMENT_OFFICIAL_REF = (
    "The reference the issuing authority itself publishes the instrument under, written "
    "as that authority writes it. It is how a lawyer cites the instrument and how a "
    "reader recognises it on the authority's own site; it is not an identifier this API "
    "accepts, which is `key`."
)
_INSTRUMENT_IN_FORCE_FROM = (
    "The legal date the instrument started binding, at the precision the source gave it "
    "(playbook 4.3). Null when the source names no start date."
)
_INSTRUMENT_IN_FORCE_TO = (
    "The legal date the instrument stopped binding, at the precision the source gave it. "
    "Null on an instrument still in force, which is most of them."
)
_INSTRUMENT_IMPLEMENTS_NOTE = (
    "What this instrument implements or elaborates, in the library's own words, so a "
    "reader can see where a Swedish rule comes from. Free text for a person and never a "
    "machine-readable link; an empty string when nothing was recorded, never null. The "
    "structured lineage between instruments is `lineage` on the instrument's own read."
)
_INSTRUMENT_LAST_VERIFIED_AT = (
    "When a bleqq library editor last read this record against its public source and "
    "found it unchanged, as a UTC timestamp; a screen shows it as \"Verified <date>\" in "
    "the bank's own time zone. Null on a record nobody has confirmed that way."
)
_INSTRUMENT_SOURCE_URL = (
    "The public page this record was taken from, so a reader can open it and a re-check "
    "can fetch it again. It is the authority's own page and never a link into this "
    "product."
)


class InstrumentRow(LibraryResponse):
    """One row of `GET /instruments` (INV-01). `obligationCount` counts the obligations
    this row's reader would see: inside the footprint, or every one when
    `outsideFootprint` is set."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "3f7c1e92-6b4a-4d3e-9c8f-1a2b3c4d5e6f",
                    "stableKey": "fffs-2017-2",
                    "shortName": "FFFS 2017:2",
                    "name": {"text": "FFFS 2017:2 om värdepappersrörelse", "language": "sv", "isOriginal": True, "isMachine": False},
                    "level": {"key": "authority_regulation", "kind": None, "label": "Supervisory regulation"},
                    "binding": True,
                    "jurisdiction": {"key": "se", "kind": "country", "label": "Sweden"},
                    "authority": {"key": "fi", "name": "Finansinspektionen", "shortName": "FI", "url": "https://www.fi.se/"},
                    "regime": {"key": "securities", "kind": None, "label": "Securities"},
                    "officialRef": "FFFS 2017:2",
                    "inForceFrom": {"date": "2018-01-03", "precision": "day"},
                    "inForceTo": None,
                    "implementsNote": "MiFID II delegated directive (EU) 2017/593",
                    "obligationCount": 2,
                    "inFootprint": True,
                    "lastVerifiedAt": "2026-06-30T07:12:44Z",
                    "sourceUrl": "https://www.fi.se/en/published/regulations/2017/fffs-20172/",
                }
            ]
        }
    )

    id: UUID = Field(
        description=f"The instrument's identifier in the shared library, as a UUID. {LIBRARY_FACT}",
        examples=["3f7c1e92-6b4a-4d3e-9c8f-1a2b3c4d5e6f"],
    )
    stable_key: str = Field(
        description=(
            "The instrument's immutable key, issued once and readable by a person. It "
            "survives every amendment and relabelling, which is what makes it safe to "
            "keep in an export, a report or a system of the bank's own; it is also what "
            "`GET /obligations?instrument=` filters on."
        ),
        examples=["fffs-2017-2"],
    )
    short_name: str = Field(description=_INSTRUMENT_SHORT_NAME, examples=["FFFS 2017:2"])
    name: LocalizedText | None = Field(description=_INSTRUMENT_NAME)
    level: LibraryRef = Field(description=_INSTRUMENT_LEVEL)
    binding: bool = Field(description=_BINDING, examples=[True])
    jurisdiction: LibraryRef = Field(description=_INSTRUMENT_JURISDICTION)
    authority: InstrumentAuthorityRef | None = Field(description="Who issued the instrument, or null when the fixture carries none.")
    regime: LibraryRef | None = Field(description=_INSTRUMENT_REGIME)
    official_ref: str = Field(description=_INSTRUMENT_OFFICIAL_REF, examples=["FFFS 2017:2"])
    in_force_from: PartialDate | None = Field(description=_INSTRUMENT_IN_FORCE_FROM)
    in_force_to: PartialDate | None = Field(description=_INSTRUMENT_IN_FORCE_TO)
    implements_note: str = Field(description=_INSTRUMENT_IMPLEMENTS_NOTE, examples=["MiFID II delegated directive (EU) 2017/593"])
    obligation_count: int = Field(
        description=(
            "How many duties this instrument carries that this read would show: inside "
            "the bank's footprint by default, or every one when `outsideFootprint=true` "
            "is set. It is not the instrument's whole duty count when the footprint hides "
            "some of them."
        ),
        examples=[2],
    )
    in_footprint: bool = Field(
        description=(
            "Whether the instrument's own scope (its regime) overlaps the bank's "
            "footprint. It is a filter and not a decision: it says nothing about whether "
            "any duty of this instrument applies to this bank, which a person judges "
            "separately."
        ),
        examples=[True],
    )
    last_verified_at: datetime.datetime | None = Field(description=_INSTRUMENT_LAST_VERIFIED_AT, examples=["2026-06-30T07:12:44Z"])
    source_url: str = Field(
        description=_INSTRUMENT_SOURCE_URL, examples=["https://www.fi.se/en/published/regulations/2017/fffs-20172/"]
    )

    model_config = ConfigDict(revalidate_instances="always")


class InstrumentPage(LibraryResponse):
    """One page of `GET /instruments`: the rows, and how many rows the filters match in
    all."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "id": "3f7c1e92-6b4a-4d3e-9c8f-1a2b3c4d5e6f",
                            "stableKey": "fffs-2017-2",
                            "shortName": "FFFS 2017:2",
                            "name": {"text": "FFFS 2017:2 om värdepappersrörelse", "language": "sv", "isOriginal": True, "isMachine": False},
                            "level": {"key": "authority_regulation", "kind": None, "label": "Supervisory regulation"},
                            "binding": True,
                            "jurisdiction": {"key": "se", "kind": "country", "label": "Sweden"},
                            "authority": {"key": "fi", "name": "Finansinspektionen", "shortName": "FI", "url": "https://www.fi.se/"},
                            "regime": {"key": "securities", "kind": None, "label": "Securities"},
                            "officialRef": "FFFS 2017:2",
                            "inForceFrom": {"date": "2018-01-03", "precision": "day"},
                            "inForceTo": None,
                            "implementsNote": "MiFID II delegated directive (EU) 2017/593",
                            "obligationCount": 2,
                            "inFootprint": True,
                            "lastVerifiedAt": "2026-06-30T07:12:44Z",
                            "sourceUrl": "https://www.fi.se/en/published/regulations/2017/fffs-20172/",
                        }
                    ],
                    "total": 16,
                }
            ]
        }
    )

    items: list[InstrumentRow] = Field(
        description=(
            "The instruments on this page, ordered by their stable key so that paging "
            "through them is repeatable. An empty list is an ordinary 200 and means "
            "nothing matched the filters, never that something went wrong."
        )
    )
    total: int = Field(
        description=(
            "How many instruments match the filters in all, not how many are on this "
            "page. It is counted at the moment of the call, so a record written between "
            "two pages can move it."
        ),
        examples=[16],
    )


class InstrumentQuery(CamelSchema):
    """The filters of `GET /instruments`. Jurisdiction, level, authority and `asOf` are
    deferred (chunk3-rest defaults): the Instruments tab lists every visible instrument
    with its own in-force dates, and "as of" applies to obligations only."""

    regime: str | None = Field(
        default=None,
        description=(
            "Only the instruments of this regime, by the regime term's key: `securities`, "
            "`insurance`, `tax`, `data_protection`, `aml`, `ai_ict`, `banking` and "
            "`payments` are seeded on day one. A key no regime has matches nothing and "
            "answers 200 with an empty page."
        ),
        examples=["securities"],
    )
    q: str | None = Field(
        default=None,
        max_length=MAX_QUERY_LENGTH,
        description=(
            "Find the instruments whose name, short name or official reference contains "
            "these words, ignoring case: a phrase to look for, never a document. At most "
            "200 characters (`MAX_QUERY_LENGTH`); a longer one is refused with 422 "
            "`validation_error`."
        ),
        examples=["FFFS"],
    )
    outside_footprint: bool = Field(
        default=False,
        description=(
            "Whether to include the instruments the bank's footprint would otherwise "
            "hide. False by default, which is the working inventory: only the "
            "instruments whose own scope overlaps the footprint. It also lifts the "
            "footprint filter `obligationCount` counts obligations against."
        ),
        examples=[False],
    )


class InstrumentLineageRef(LibraryResponse):
    """One instrument-to-instrument relation, from either side (INV-01): what this
    instrument implements or elaborates, and what implements, elaborates or amends it."""

    relation: LibraryRef = Field(
        description=(
            "How the two instruments are related, as key, kind and label: `implements`, "
            "`elaborates` and `amends` are seeded on day one. The relation types are "
            "vocabulary rows a platform admin may extend, relabel or retire without a "
            "deploy, so read `GET /vocab/relation_type` for the live set and match on the "
            "key."
        )
    )
    direction: str = Field(
        description=(
            "Whether this instrument is the one doing the relating (`outgoing`, this "
            "instrument implements, elaborates or amends the other) or the one being "
            "related to (`incoming`, the other does so to this one). A card reads "
            "`outgoing` under headings such as \"Implements\" and \"incoming\" under "
            "\"Amended by\"."
        ),
        examples=["incoming"],
    )
    instrument: ObligationInstrumentRef = Field(description="The other instrument in the relation, by key and short name.")
    note: str = Field(
        description="What the relation is, in the library's own words. An empty string when nothing was recorded, never null.",
        examples=["Amends FFFS 2017:2, in force 1 October 2026."],
    )
    to_ref: str = Field(
        description=(
            "Where in the related instrument this points, in the words the source uses "
            "(\"Article 25(3) and (4)\"), whichever side of the relation this instrument "
            "is on. An empty string when the relation names no specific place, which is "
            "most of them: a whole-instrument amendment needs none."
        ),
        examples=[""],
    )


_SAMPLE_INSTRUMENT_DETAIL: dict[str, Any] = {
    "id": "3f7c1e92-6b4a-4d3e-9c8f-1a2b3c4d5e6f",
    "stableKey": "fffs-2017-2",
    "shortName": "FFFS 2017:2",
    "name": {"text": "FFFS 2017:2 om värdepappersrörelse", "language": "sv", "isOriginal": True, "isMachine": False},
    "level": {"key": "authority_regulation", "kind": None, "label": "Supervisory regulation"},
    "binding": True,
    "jurisdiction": {"key": "se", "kind": "country", "label": "Sweden"},
    "authority": {"key": "fi", "name": "Finansinspektionen", "shortName": "FI", "url": "https://www.fi.se/"},
    "regime": {"key": "securities", "kind": None, "label": "Securities"},
    "officialRef": "FFFS 2017:2",
    "eliUri": "",
    "inForceFrom": {"date": "2018-01-03", "precision": "day"},
    "inForceTo": None,
    "implementsNote": "MiFID II delegated directive (EU) 2017/593",
    "sourceUrl": "https://www.fi.se/en/published/regulations/2017/fffs-20172/",
    "lastVerifiedAt": "2026-06-30T07:12:44Z",
    "verifiedBy": None,
    "lineage": [
        {
            "relation": {"key": "amends", "kind": None, "label": "Amends"},
            "direction": "incoming",
            "instrument": {"key": "fffs-2026-11", "shortName": "FFFS 2026:11"},
            "note": "Amends FFFS 2017:2, in force 1 October 2026.",
            "toRef": "",
        }
    ],
}


class InstrumentDetail(LibraryResponse):
    """`GET /instruments/{instrumentId}` (INV-01, INV-06): the row's own facts, plus the
    ELI, the authority in full, who last re-verified it and its lineage to other
    instruments. The provision tree is its own read (chunk3-rest T16)."""

    model_config = ConfigDict(json_schema_extra={"examples": [_SAMPLE_INSTRUMENT_DETAIL]})

    id: UUID = Field(
        description=f"The instrument's identifier in the shared library, as a UUID. {LIBRARY_FACT}",
        examples=["3f7c1e92-6b4a-4d3e-9c8f-1a2b3c4d5e6f"],
    )
    stable_key: str = Field(
        description=(
            "The instrument's immutable key, issued once and readable by a person. It "
            "survives every amendment and relabelling."
        ),
        examples=["fffs-2017-2"],
    )
    short_name: str = Field(description=_INSTRUMENT_SHORT_NAME, examples=["FFFS 2017:2"])
    name: LocalizedText | None = Field(description=_INSTRUMENT_NAME)
    level: LibraryRef = Field(description=_INSTRUMENT_LEVEL)
    binding: bool = Field(description=_BINDING, examples=[True])
    jurisdiction: LibraryRef = Field(description=_INSTRUMENT_JURISDICTION)
    authority: InstrumentAuthorityRef | None = Field(description="Who issued the instrument, in full, or null when the fixture carries none.")
    regime: LibraryRef | None = Field(description=_INSTRUMENT_REGIME)
    official_ref: str = Field(description=_INSTRUMENT_OFFICIAL_REF, examples=["FFFS 2017:2"])
    eli_uri: str = Field(
        description=(
            "The European Legislation Identifier for this instrument, where the "
            "publisher gives one. An empty string when none is available, never null; "
            "the screen reads that as \"Not available\"."
        ),
        examples=[""],
    )
    in_force_from: PartialDate | None = Field(description=_INSTRUMENT_IN_FORCE_FROM)
    in_force_to: PartialDate | None = Field(description=_INSTRUMENT_IN_FORCE_TO)
    implements_note: str = Field(description=_INSTRUMENT_IMPLEMENTS_NOTE, examples=["MiFID II delegated directive (EU) 2017/593"])
    source_url: str = Field(
        description=_INSTRUMENT_SOURCE_URL, examples=["https://www.fi.se/en/published/regulations/2017/fffs-20172/"]
    )
    last_verified_at: datetime.datetime | None = Field(description=_INSTRUMENT_LAST_VERIFIED_AT, examples=["2026-06-30T07:12:44Z"])
    verified_by: PersonRef | None = Field(
        description=(
            "The bleqq platform person who last confirmed this record against its "
            "source, by id and name, or null when nobody has. Never a member of a bank: "
            "re-verifying a shared fact is bleqq's own check."
        )
    )
    lineage: list[InstrumentLineageRef] = Field(
        description=(
            "What this instrument implements or elaborates, and what implements, "
            "elaborates or amends it in turn: both directions of the library's own "
            "cross-references, so the designed `GET /instruments/{instrumentId}/relations` "
            "is served here instead. Only instruments this caller may read appear: a "
            "relation to one they may not is left out silently."
        )
    )


# ---------------------------------------------------------------------------------------
# GET /instruments/{instrumentId}/provisions and GET /provisions/{provisionId}/diff
# (INV-02, INV-04, INV-05)
# ---------------------------------------------------------------------------------------
class ProvisionVersionRow(LibraryResponse):
    """One verbatim text version of a provision (INV-02, INV-04): when it took effect,
    `effectiveTo` derived as the day before the next version did (nothing is stored,
    because a version row is written once and never touched afterwards), any
    transitional note, and the text itself in the reader's best language."""

    version_number: int = Field(
        description=(
            "Which version of this provision's text it is, numbered from 1 in the order "
            "the versions took effect. It is the number to send to the diff as `from` or "
            "`to`, and it never addresses another provision's version."
        ),
        examples=[2],
    )
    effective_from: PartialDate | None = Field(
        description=(
            "The legal date this version started binding the bank, at the precision the "
            "source gave it. Null means it has been in force since the provision entered "
            f"the library. {LIBRARY_FACT}"
        )
    )
    effective_to: PartialDate | None = Field(
        description=(
            "The last day this version was in force, worked out as the day before the "
            "next version took effect. Null on the version still in force, on one whose "
            "successor carries no date, and on one corrected the same day it took effect."
        )
    )
    transitional_note: str = Field(
        description=(
            "How the transition to this version is handled, in the library's own words "
            "(\"the annual assessment is first due for research received after 1 October "
            "2026\"). An empty string when the source gave none, never null."
        ),
        examples=["The annual assessment is first due for research received after 1 October 2026."],
    )
    text: LocalizedText | None = Field(
        description=(
            "This version's verbatim text in the best language this reader can be "
            "served. Null only when the version carries no text in any language at all."
        )
    )


class ProvisionCitedObligation(LibraryResponse):
    """An obligation the tree shows beside the provision it cites (INV-02, INV-03)."""

    id: UUID = Field(description=_OBLIGATION_ID, examples=["7c1f0b3e-52a4-4f9e-8a21-6d4b2c0a9e17"])
    title: LocalizedText | None = Field(description=_OBLIGATION_TITLE)
    ref_label: str = Field(description=_OBLIGATION_REF_LABEL, examples=["Third-party payments"])


class ProvisionNode(LibraryResponse):
    """One node of an instrument's provision tree (INV-02): a chapter, a section, a
    paragraph or whatever `kind` names, with its own text versions, its children in the
    tree and the obligations that cite it. `inForceVersion` is the version number in
    force on the read's date (null when none is); `versions` lists every one regardless,
    so a reader can choose an earlier or a future version by its own chip."""

    id: UUID = Field(
        description=f"The provision's identifier in the shared library, as a UUID. {LIBRARY_FACT}",
        examples=["b6d9f0a4-1c72-4e35-9f88-0a2c4e6b8d10"],
    )
    stable_key: str = Field(
        description=(
            "The provision's immutable key, issued once and readable by a person, of the "
            "form `<instrument>/<unit>` (`fffs-2017-2/9-6` for 9 kap. 6 §). It survives "
            "every amendment and relabelling."
        ),
        examples=["fffs-2017-2/9-6"],
    )
    kind: LibraryRef = Field(
        description=(
            "What structural kind of unit this is, as key, kind and label: `chapter`, "
            "`section`, `article`, `paragraph`, `part`, `annex` and `guideline` are seeded "
            "on day one. Here `kind` on the reference itself carries the row's own fixed "
            "structural kind (`division`, `unit` or `annex`) rather than being null, "
            "because a screen groups provisions by it. The kinds are vocabulary rows a "
            "platform admin may extend or retire without a deploy, so read "
            "`GET /vocab/provision_kind` for the live set and match on the key."
        )
    )
    ref_label: str = Field(
        description=(
            "How this unit is cited, in the words the source itself uses (`9 kap.`, "
            "`6 §`, `Article 25(3)`). For a reader to quote, not a reference to parse."
        ),
        examples=["6 §"],
    )
    heading: str = Field(
        description="The unit's own heading, in the library's words. An empty string when the source gives none, never null.",
        examples=["Betalning för analys"],
    )
    path: str = Field(
        description="Where this unit sits in its instrument's structure, read from the top, as a breadcrumb a person reads.",
        examples=["FFFS 2017:2 > 9 kap. > 6 §"],
    )
    children: list[ProvisionNode] = Field(
        description="The units nested directly under this one, in the tree's own order. An empty list on a leaf."
    )
    versions: list[ProvisionVersionRow] = Field(
        description=(
            "Every text version of this unit in version order, including ones still to "
            "take effect, so a reader can choose any of them by its own chip rather than "
            "trusting today's date. Nothing here is ever rewritten: a correction is "
            "another version."
        )
    )
    in_force_version: int | None = Field(
        description=(
            "The version number in force on the date this tree was read, or null when "
            "every version starts after that date. It says which chip a screen should "
            "select by default; the reader may still choose another one."
        ),
        examples=[2],
    )
    obligations: list[ProvisionCitedObligation] = Field(
        description=(
            "The obligations that cite this unit, so a reader can jump from the law to "
            "the duty. Only obligations this caller may read appear: one they may not is "
            "left out silently."
        )
    )


ProvisionNode.model_rebuild()

SAMPLE_PROVISION_TREE: list[dict[str, Any]] = [
    {
        "id": "e4b8f1a2-6c3d-4e5f-9a7b-1c2d3e4f5a6b",
        "stableKey": "fffs-2017-2/9",
        "kind": {"key": "chapter", "kind": "division", "label": "Chapter"},
        "refLabel": "9 kap.",
        "heading": "Skydd för investerare",
        "path": "FFFS 2017:2 > 9 kap.",
        "children": [
            {
                "id": "b6d9f0a4-1c72-4e35-9f88-0a2c4e6b8d10",
                "stableKey": "fffs-2017-2/9-6",
                "kind": {"key": "section", "kind": "unit", "label": "Section"},
                "refLabel": "6 §",
                "heading": "Betalning för analys",
                "path": "FFFS 2017:2 > 9 kap. > 6 §",
                "children": [],
                "versions": [
                    {
                        "versionNumber": 1,
                        "effectiveFrom": {"date": "2018-01-03", "precision": "day"},
                        "effectiveTo": {"date": "2026-09-30", "precision": "day"},
                        "transitionalNote": "",
                        "text": {
                            "text": (
                                "Investment research from a third party may be received only if it is paid "
                                "from the institution's own resources, from a research payment account, or "
                                "jointly with execution under the conditions set out in these regulations."
                            ),
                            "language": "en",
                            "isOriginal": False,
                            "isMachine": True,
                        },
                    },
                    {
                        "versionNumber": 2,
                        "effectiveFrom": {"date": "2026-10-01", "precision": "day"},
                        "effectiveTo": None,
                        "transitionalNote": "The annual assessment is first due for research received after 1 October 2026.",
                        "text": {
                            "text": (
                                "Investment research from a third party may be received only if it is paid "
                                "from the institution's own resources, from a research payment account, or "
                                "jointly with execution under the conditions set out in these regulations. "
                                "The institution shall assess annually the quality and value of the research "
                                "it receives."
                            ),
                            "language": "en",
                            "isOriginal": False,
                            "isMachine": True,
                        },
                    },
                ],
                "inForceVersion": 1,
                "obligations": [
                    {
                        "id": "7c1f0b3e-52a4-4f9e-8a21-6d4b2c0a9e17",
                        "title": {
                            "text": "Pay for third-party research only under the permitted models",
                            "language": "en",
                            "isOriginal": True,
                            "isMachine": False,
                        },
                        "refLabel": "Third-party payments",
                    }
                ],
            }
        ],
        "versions": [],
        "inForceVersion": None,
        "obligations": [],
    }
]


class InstrumentProvisionsQuery(CamelSchema):
    """`asOf` on the provision tree: which version of each unit `inForceVersion` names,
    today in the tenant's time zone by default (AC-INV1). `versions` always lists every
    one regardless, so a reader can choose an earlier or a future version by its own
    chip and is never limited to what was in force on this date."""

    as_of: datetime.date | None = Field(
        default=None,
        description=f"{_AS_OF} It decides `inForceVersion` alone; every version stays in `versions`.",
        examples=["2026-06-30"],
    )


# ---------------------------------------------------------------------------------------
# Chunk 5's two library reads: the authority list and a record's citations
# ---------------------------------------------------------------------------------------
class LibraryAuthority(LibraryResponse):
    """One issuing authority, as `GET /authorities` lists them. A shared library fact:
    every bank and every agent reads the same list, and it holds no bank's judgement."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "3a1c94c2-3f41-4f0e-9a4e-5b2a1d0c7e11",
                    "key": "fi",
                    "shortName": "FI",
                    "name": "Finansinspektionen",
                    "jurisdiction": {"key": "se", "kind": "country", "label": "Sweden"},
                    "url": "https://www.fi.se/",
                }
            ]
        }
    )

    id: UUID = Field(
        description="The authority's identifier in the shared library, used by the change and console filters.",
        examples=["3a1c94c2-3f41-4f0e-9a4e-5b2a1d0c7e11"],
    )
    key: str = Field(
        description=(
            "The authority's immutable key, the value a filter, a report or an export stores. "
            "It never changes; the name may be relabelled around it (playbook 4.3)."
        ),
        examples=["fi"],
    )
    short_name: str = Field(
        description="How the authority is abbreviated in a pill or a column, in its own language.", examples=["FI"]
    )
    name: str = Field(description="The authority's full name, as it names itself.", examples=["Finansinspektionen"])
    jurisdiction: LibraryRef = Field(
        description=(
            "Where the authority sits, as `{key, kind, label}` from the jurisdiction vocabulary "
            "(`se`, `dk`, `no`, `fi` and `eu` among the rows seeded on day one). The values are "
            "rows an admin manages, not a closed set: a platform admin may extend, relabel or "
            "retire one without a deploy, so read `GET /reference/jurisdictions` for the live "
            "set and match on the key, never on the label. The "
            "`kind` says whether it is a country, a union or an international body; a change "
            "takes its own jurisdiction from its authority, and a standard's term is accepted "
            "only when that kind is international (FP-04, AC-AGT1). A reader must not conclude "
            "from this alone that a change applies to a bank: applicability is a separate fact "
            "(REG-01)."
        )
    )
    url: str = Field(description="The authority's own site, so a reader can open it.", examples=["https://www.fi.se/"])


class LibraryRecordSource(LibraryResponse):
    """One citation behind a live library record: which field it backs, where it came from
    and what we have of that page. Shared library provenance (INV-06); it names no bank."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "field": "summary",
                    "url": "https://www.fi.se/en/published/regulations/2017/fffs-20172/",
                    "label": "FFFS 2017:2",
                    "contentHash": "9f2c4d0a6b1e8f37c5a90d2e4b6f8013a7c5e9d1b3f5079a2c4e6081d3f5a7c9",
                    "fetchedAt": "2026-09-16T06:02:00Z",
                    "documentId": None,
                }
            ]
        }
    )

    field: str = Field(
        description=(
            "Which field of the record this citation backs — `summary`, `key_date`, "
            "`duty_type` and so on, the record's own column names. Free text rather than a "
            "vocabulary because the set is the schema's, not an admin's."
        ),
        examples=["summary"],
    )
    url: str = Field(
        description="The public page the fact came from, so a re-check can fetch it again and a reviewer can open it.",
        examples=["https://www.fi.se/en/published/regulations/2017/fffs-20172/"],
    )
    label: str = Field(description="What that page is called, in words a reader recognises.", examples=["FFFS 2017:2"])
    content_hash: str | None = Field(
        description=(
            "A hash of the page as we last read it, so a re-check can tell whether it moved "
            "without keeping a copy of it. Null when the citation predates the hash or the "
            "publisher's terms allow no snapshot at all (WAT-07, D-45). A changed hash means "
            "the page moved, never that the record is wrong."
        ),
        examples=["9f2c4d0a6b1e8f37c5a90d2e4b6f8013a7c5e9d1b3f5079a2c4e6081d3f5a7c9"],
    )
    fetched_at: datetime.datetime | None = Field(
        description=(
            "When we last read that page, as an RFC 3339 timestamp in UTC "
            "(`2026-09-16T06:02:00Z`). Null when no agent has ever fetched it."
        ),
        examples=["2026-09-16T06:02:00Z"],
    )
    document_id: UUID | None = Field(
        description=(
            "The stored source document, as a UUID, when there is one. Null for a citation a "
            "library editor recorded by hand."
        ),
        examples=["e2b9a071-4c35-4d68-9b1f-8a0c3e5d7b24"],
    )


class LibraryRecordSources(LibraryResponse):
    """`GET /obligations/{obligationId}/sources`: everything a re-check needs to compare a
    live library record against the pages it came from, and nothing that needs a write
    scope. It is how an agent key holding `library:read` alone re-checks a record (AGT-01,
    item 3); the correction it proposes goes through the proposal door, never a direct
    edit (PRO-01)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "obligationId": "7c1f0b3e-52a4-4f9e-8a21-6d4b2c0a9e17",
                    "versionNumber": 2,
                    "items": [
                        {
                            "field": "summary",
                            "url": "https://www.fi.se/en/published/regulations/2017/fffs-20172/",
                            "label": "FFFS 2017:2",
                            "contentHash": "9f2c4d0a6b1e8f37c5a90d2e4b6f8013a7c5e9d1b3f5079a2c4e6081d3f5a7c9",
                            "fetchedAt": "2026-09-16T06:02:00Z",
                            "documentId": None,
                        }
                    ],
                }
            ]
        }
    )

    obligation_id: UUID = Field(
        description=(
            "The library obligation these citations belong to, as a UUID: the same id the caller "
            "asked for."
        ),
        examples=["7c1f0b3e-52a4-4f9e-8a21-6d4b2c0a9e17"],
    )
    version_number: int = Field(
        description=(
            "The version of the obligation the citations describe: the one in force today, "
            "because that is what a re-check compares. An older version's citations are not "
            "rewritten when a new version lands (INV-04)."
        ),
        examples=[2],
    )
    items: list[LibraryRecordSource] = Field(
        description=(
            "The citations, one per sourced field. An empty list means the record carries no "
            "field-level citation yet, not that it is unsourced: the record's own `provenance` "
            "still names where it came from."
        )
    )
