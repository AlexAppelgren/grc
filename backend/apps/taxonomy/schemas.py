"""Request and response schemas of the taxonomy app: camelCase through CamelSchema, app-prefixed
class names where a shape is specific to this app (playbook 4.1).

Nothing here declares an enum of vocabulary values (VOC-01, AC-VOC1): `kind` and `key` are
plain strings, so adding a change type or a tag never moves `openapi.json`. The tier-one
kinds stay in apps/shared/kinds.py and never reach the contract as an `enum` either, because
the rules read them off the row, not off the wire.
"""

from __future__ import annotations

import builtins
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from apps.shared.schemas import CamelSchema, LibraryResponse, VocabularyExtra, WriteBody

__all__ = ["CamelSchema"]


# ---------------------------------------------------------------------------------------
# References: what every picker, pill and filter reads (playbook 15: key and kind, never a
# phrase the client must string-match).
# ---------------------------------------------------------------------------------------
class TermRef(CamelSchema):
    """A vocabulary value as every picker, pill and filter reads it: the key to store and
    compare, the kind when the value's list has one, and a label to show (playbook 15)."""

    key: str = Field(
        description=(
            "The value's immutable key, such as `advice` for a taxonomy term, `no` for Norway or `sv` for "
            "Swedish, and the only part of this reference to store, compare or send back. It is a row of "
            "a vocabulary: a taxonomy term (the shared library's terms, which an administrator may extend "
            "through an approved proposal; `GET /taxonomy/terms`), a jurisdiction (which the platform seeds "
            "and its library editors relabel, retire and restore by proposal; `GET /reference/jurisdictions`), a language (the platform's own "
            "list, which no bank admin can extend) or an urgency (the shared library's `urgency` "
            "vocabulary, which an administrator may extend through an approved proposal; "
            "`GET /vocab/urgency`). A key you have not seen before is new data, not an error. A key never "
            "changes once issued."
        ),
        examples=["advice"],
    )
    kind: str | None = Field(
        default=None,
        description=(
            "The fixed kind of the value, when its list has one, so a screen can branch or pick a pill "
            "tone without reading the label; null by default, when the list has no kind. By list: a "
            "taxonomy term is always null, because its dimension is its kind; a language is always null; "
            "a jurisdiction is `supranational` (the European Union, whose rules reach its members and the "
            "EEA), `country` (one national market, such as Sweden) or `international` (a standards body "
            "such as ISO/IEC, which is no bank's market); an urgency is its pill tone, one of "
            "`information`, `notice`, `positive`, `warning`, `negative` and `brand`. Kinds are fixed in "
            "code and never added by an administrator."
        ),
        examples=[None],
    )
    label: str = Field(
        description=(
            "The value's name in the reader's language: the caller's own language first, then the "
            "organisation's default language, then English, then any label the value has, and the key "
            "itself when it has none. A language is the exception and reads in itself, such as `Svenska`. "
            "For display only: a person wrote it and may reword or translate it at any time, so nothing "
            "may match on it."
        ),
        examples=["Advice"],
    )


class PersonRef(CamelSchema):
    """A person on a record: id and name, the only personal data a screen or a log may carry
    about them (playbook 4.7)."""

    id: UUID = Field(
        description=(
            "The person's identifier, a UUID that never changes, the same one a member list and the audit "
            "log carry. Store and compare this, never the name."
        ),
        examples=["8a3c1e5f-2d4b-4f60-9e7a-1b2c3d4e5f60"],
    )
    name: str = Field(
        description=(
            "The person's name as they gave it, for display only. It may change when they edit their "
            "profile and two people may share it, so nothing may match on it. A person's name and id are "
            "the only personal data a record carries about them."
        ),
        examples=["Sara Lindqvist"],
    )


# Declared here beside `PersonRef`, not in apps/library/schemas.py, because that module
# imports its references from this one: a list row and an obligation version name an agent
# with the same shape, and importing it the other way round would be a cycle.
class AgentRef(LibraryResponse):
    """One of the platform's research agents, named the way a screen may label it: its
    definition key, which never changes, and never its internal id alone (AUD-02)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"id": "6d1e4f8a-9c3b-4a7e-8f21-1b6d4c8a2e05", "key": "watch-sweeper"}]})

    id: UUID = Field(description="The agent definition, as a UUID.")
    key: str = Field(description="The agent definition's own key, stable and never changed, for example `watch-sweeper`.", examples=["watch-sweeper"])


# Machine-confirmed provenance on a library list row or a taxonomy term (INV-05, PRO-02,
# D-62, D-79): the three facts `VersionConfirmation` gives an obligation version, about the
# wording the row carries. Declared once so the two row shapes cannot describe the same
# fact two ways.
RowVerifiedOrigin = Annotated[
    str,
    Field(
        description=(
            "Who confirmed the wording this row carries, its labels and its usage note. `agent` "
            "while any of it is wording a second, independent agent confirmed, which a screen "
            "labels machine-confirmed and never as a person's verification. `user` when a "
            "person approved the last change to its wording and nothing an agent confirmed is "
            "left on it; the person is not named here. A row is reworded a piece at a time, so "
            "a person's approval of part of the agents' wording leaves `agent` standing until a "
            "person has approved every label they wrote and the usage note; on a list row, each "
            "label an agent wrote is also in `machineLanguages` (`GET /vocab/{list}/{key}`) "
            "until a person confirms it. Empty for a row the library was seeded with or last "
            "worded before this was recorded, which reads the same as `user`, and on every row "
            "of a bank's own list, which its admin writes without a proposal. An approval that "
            "changes no wording, such as a new sort order, a retire, a restore or a merge, "
            "leaves it as it was. A fixed kind, not a vocabulary: decide the machine-confirmed "
            "label from this field alone, never from which agent fields are present."
        ),
        examples=["agent"],
    ),
]
RowConfirmedByAgent = Annotated[
    AgentRef | None,
    Field(
        description=(
            "The independent agent that confirmed the approval `verifiedOrigin` describes, by "
            "its definition key, when `verifiedOrigin` is `agent`: the latest agent approval "
            "that reworded the row. Null whenever `verifiedOrigin` is not `agent`, which is a "
            "row a person approved, a seeded row and every row of a bank's own list. It names "
            "a platform agent definition, never a person or a bank."
        )
    ),
]
RowProposedByAgent = Annotated[
    AgentRef | None,
    Field(
        description=(
            "The agent that proposed the approval `verifiedOrigin` describes, by its "
            "definition key, read from the approved proposal. Null whenever the proposer was "
            "not a key bound to an agent, which is every proposal a person made, whoever "
            "confirmed it; whenever a bank made the proposal, since who proposed on a bank's "
            "behalf is never shown; and on a seeded row or a bank's own list. It is independent "
            "of `verifiedOrigin`: an agent's proposal a person approved names the agent here "
            "beside `verifiedOrigin` `user`."
        )
    ),
]


class TaxonomyDimensionRef(CamelSchema):
    """A taxonomy dimension as a reference: the group a term or a regulatory scope group
    belongs to (FP-01)."""

    key: str = Field(
        description=(
            "The dimension's immutable key, such as `service_type` or `standard`, and the only part of this "
            "reference to store, compare or send back. Dimensions are rows of the shared library's "
            "`term_dimension` vocabulary, which an administrator may extend through an approved proposal, "
            "so a key you have not seen before is new data and not an error; `GET /taxonomy/dimensions` "
            "lists the live set."
        ),
        examples=["service_type"],
    )
    kind: str | None = Field(
        default=None,
        description=(
            "How the dimension's terms act on a bank's regulatory scope, one of three fixed values. "
            "`scope`: the dimension says who or what a rule covers, and a scope group with no term chosen "
            "restricts nothing. `classification`: the dimension only describes a record and never narrows "
            "the scope. `opt_in`: the standards a bank follows, where a record carrying one of the "
            "dimension's terms shows only to a bank whose scope names that term, so a group with no term "
            "chosen means none followed rather than no restriction. Every dimension carries a kind, so the "
            "default of null never reaches a reader. It is a kind in code, so the rules branch on it; an "
            "administrator never adds a value."
        ),
        examples=["scope"],
    )
    label: str = Field(
        description=(
            "The dimension's name in the reader's language, for display only. It is a phrase a person wrote "
            "and may be reworded or translated at any time, so nothing may match on it."
        ),
        examples=["Service"],
    )


class JurisdictionRow(CamelSchema):
    """`GET /reference/jurisdictions` (I18N-01). A reference read: a short fixed list that
    never paginates, like `GET /reference/languages` (INPUT_DELTAS §7)."""

    key: str = Field(
        description=(
            "The jurisdiction's immutable key, the lowercased code a record, a market and a filter carry: "
            "seeded on day one are `eu` (the European Union), `se`, `dk`, `no`, `fi` and `intl` "
            "(international standards bodies). Jurisdictions are rows of the shared library's "
            "`jurisdiction` vocabulary, which the platform's library editors may extend without a deploy; "
            "a bank's admin cannot add one. This endpoint lists the live set, and a key never changes."
        ),
        examples=["se"],
    )
    kind: str | None = Field(
        default=None,
        description=(
            "What sort of jurisdiction this is, one of three fixed values: `supranational` for the "
            "European Union, whose rules reach its member states and, through the EEA Agreement, Norway; "
            "`country` for one national market, the only kind a bank can operate in or watch; "
            "`international` for the issuer of a standard such as ISO/IEC, which is no bank's market and "
            "never appears among the markets. Every jurisdiction carries a kind, so the default of null "
            "never reaches a reader. A kind in code; an administrator never adds one."
        ),
        examples=["country"],
    )
    label: str = Field(
        description=(
            "The jurisdiction's name in the reader's language, such as `Sweden` or `Sverige`, for display "
            "only. It may be reworded or translated at any time, so nothing may match on it."
        ),
        examples=["Sweden"],
    )
    parent_key: str | None = Field(
        default=None,
        description=(
            "The key of the jurisdiction whose rules also reach this one, such as `eu` for Sweden and for "
            "Norway, which is outside the Union but bound by its financial rules through the EEA "
            "Agreement. It says whose law reaches here, not membership. Null by default, for a "
            "jurisdiction nothing reaches (`eu`, `intl`). A row of the same `jurisdiction` vocabulary, "
            "which the platform's library editors may extend and a bank's admin may not."
        ),
        examples=["eu"],
    )
    default_language: TermRef | None = Field(
        default=None,
        description=(
            "The language this jurisdiction's legal texts are written in, such as Swedish (`sv`) for "
            "Sweden and English (`en`) for the European Union: the original a translation is made from. "
            "Its key is a row of the platform's language vocabulary (`en`, `sv`, `da`, `nb`, `fi` on day "
            "one), which only the platform adds to and no bank admin can extend; its kind is always null. "
            "Every jurisdiction names one, so the default of null never reaches a reader."
        ),
    )


# ---------------------------------------------------------------------------------------
# Vocabularies (VOC-01, VOC-02, VOC-03, VOC-07)
# ---------------------------------------------------------------------------------------
# What several vocabulary shapes say in the same words, written once.
_VOCABULARY_KEY = (
    "The value's stable key, such as `custody`, and the only part of the row to store, compare or send "
    "back: it never changes, whatever happens to the labels. The rows are a vocabulary and not a fixed set: "
    "a bank's admin extends its own lists with `vocab.manage`, and a library list is extended through a "
    "proposal a second person approves, so a key you have not seen before is new data and not an error. "
    "`GET /vocab/{list}` gives the live set."
)
_KINDS_BY_LIST = (
    "`term_dimension` takes `scope`, `classification` or `opt_in`; `instrument_level` `standard` or none; "
    "`provision_kind` `division`, `unit` or `annex`; `change_type` `pre_adoption`, `adopted`, `in_force`, "
    "`supervisory` or `recurring`; `urgency` the tone its pill shows, `information`, `notice`, `positive`, "
    "`warning`, `negative` or `brand`; `jurisdiction` `supranational`, `country` or `international`; "
    "`compliance_status` `compliant`, `partly`, `gap` or `not_assessed`; `case_sub_status` the case "
    "category it sits inside, `new`, `assigned`, `assessing`, `implementing`, `signoff`, `closed` or "
    "`dismissed`; and `close_reason` `signed_off`, `not_applicable` or `no_action`. Every other list's "
    "rows carry no kind."
)
_LABELS_WRITE = (
    "The value's name per content language, as a map from language key to text, such as "
    '`{"en": "Custody", "sv": "Förvaring"}`. The keys are the platform\'s content languages, `en`, `sv`, '
    "`da`, `nb` and `fi`, a set a bank's admin cannot extend (`GET /reference/languages` lists it); any "
    "other key answers 422 `unknown_key` with the valid ones. Surrounding spaces are trimmed and an empty "
    "text is ignored, and at least one label must be left or the write answers 422 `validation_error`."
)
_KEY_WRITE = (
    "Optional: left out, the server makes it from the English label, or from the first label given, as "
    "lower-case words joined by underscores (`Custody services` becomes `custody_services`), and a key you "
    "give is normalised the same way; one that normalises to nothing answers 422 `validation_error`. A key "
    "the list already holds in any letter case, retired values included, answers 409 `duplicate_key` with "
    "the existing value in `candidates`. The key never changes once the value exists."
)
_EXTRA_COLUMNS = (
    "`urgency` has `ordinal` (its place on the urgency scale, 1 the most urgent) and `slaDays` (the days "
    "a bank has to act); `term_dimension` `restrictsFootprint`; `instrument_level` `bindingDefault` and "
    "`rank`; `provision_kind` `jurisdiction`, the key of a row of the `jurisdiction` list; and "
    "`compliance_status` and `risk_rating` `ordinal`, their place on the bank's own scale. Every other "
    "list has none."
)
_EXTRA_WRITE = (
    "Keyed as a row's `extra` reads them (`slaDays`) or by column name (`sla_days`); a key the list does "
    "not have is ignored, never stored. Each value is checked like the column it fills, so a wrong one "
    "answers 422 `validation_error`, and a reference to a row that does not exist answers 422 "
    "`unknown_key` with the valid keys. `tone`, `colour` and `color` are refused with 422 "
    "`validation_error`: a value's tone follows its kind and is never chosen."
)


class VocabularyListEntry(CamelSchema):
    """One row of `GET /vocab`: one list a picker, a filter or an agent reads its values
    from, with how many values it holds. The list itself is fixed by the product; its rows
    are the data."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "list": "urgency",
                    "tier": 2,
                    "kind": "pill_tone",
                    "kinds": ["information", "notice", "positive", "warning", "negative", "brand"],
                    "count": 4,
                    "retiredCount": 0,
                    "proposable": True,
                }
            ]
        }
    )

    list: str = Field(
        description=(
            "The list's name, which every other vocabulary path takes as `{list}`. The set of lists is fixed "
            "by the product and never by an admin, who adds values to a list and never a list. The shared "
            "library's lists are `term_dimension`, `instrument_level`, `provision_kind`, `change_type`, "
            "`duty_type`, `relation_type`, `source_kind`, `urgency`, `library_tag`, `flag`, "
            "`rejection_reason` and `jurisdiction`; a bank's own lists are `tenant_tag`, `link_kind`, "
            "`effort_size`, `compliance_status`, `risk_rating`, `case_sub_status`, `dismissal_reason` and "
            "`close_reason`."
        ),
        examples=["urgency"],
    )
    tier: int = Field(
        description=(
            "Who owns the list's values, one of two numbers. `2`: a library list shared by every bank, "
            "changed only through a proposal that a second, independent person or agent approves, so every "
            "write to it answers 202 with that proposal and changes nothing yet. `3`: the bank's own list, "
            "never shared and never seen by another bank, which a person holding `vocab.manage` changes "
            "directly. The first tier, the fixed kinds, lives in code and is never a list here."
        ),
        examples=[2],
    )
    kind: str | None = Field(
        default=None,
        description=(
            "The name of the fixed kind the list's values carry, such as `change_lifecycle_kind` for "
            "`change_type` or `pill_tone` for `urgency`, and null for a list whose values carry none. It "
            "names the set that `kinds` spells out."
        ),
        examples=["pill_tone"],
    )
    kinds: builtins.list[str] = Field(
        default_factory=builtins.list,
        description=(
            "Every value a row of this list may carry in its `kind`, and so the full set for this release: "
            "kinds are fixed in code and an admin never adds one. Empty for a list whose values carry no "
            f"kind. Per list, {_KINDS_BY_LIST}"
        ),
        examples=[["information", "notice", "positive", "warning", "negative", "brand"]],
    )
    count: int = Field(
        description=(
            "How many of the list's values are active now and offered by pickers, counting only the "
            "caller's bank for a bank's own list. Retired values are counted in `retiredCount` instead."
        ),
        examples=[4],
    )
    retired_count: int = Field(
        description=(
            "How many of the list's values were retired or merged away. They stay so the records that carry "
            "them remain readable, but no picker offers them."
        ),
        examples=[0],
    )
    proposable: bool = Field(
        description=(
            "False for a library list that is reference data, seeded with every deploy and never changed "
            "through the API: a create, suggestion, change, retire, restore or merge on it answers 422 "
            "`validation_error`. True for every other list, a bank's own lists included, which change "
            "directly rather than by proposal. `jurisdiction` is true with fixed keys: a proposal relabels, "
            "retires or restores a jurisdiction, and a create or a merge on it answers 422 `validation_error`."
        ),
        examples=[True],
    )


class VocabularyListPage(CamelSchema):
    """`GET /vocab`: every vocabulary list the caller can read, in one answer."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "list": "change_type",
                            "tier": 2,
                            "kind": "change_lifecycle_kind",
                            "kinds": ["pre_adoption", "adopted", "in_force", "supervisory", "recurring"],
                            "count": 9,
                            "retiredCount": 0,
                            "proposable": True,
                        },
                        {
                            "list": "tenant_tag",
                            "tier": 3,
                            "kind": None,
                            "kinds": [],
                            "count": 3,
                            "retiredCount": 1,
                            "proposable": True,
                        },
                    ],
                    "total": 2,
                }
            ]
        }
    )

    items: list[VocabularyListEntry] = Field(
        description=(
            "Every list the caller can read: the library's lists first, then, for a caller signed in to a "
            "bank, the bank's own lists, in an order that never changes. Not paginated, because the set is "
            "short and fixed by the product; a platform session outside any bank gets the library's lists only."
        )
    )
    total: int = Field(description="How many lists `items` holds; the whole set always arrives on this one page.")


class VocabularyRow(CamelSchema):
    """One value of a vocabulary list as every picker, filter, pill and agent reads it: the
    key to store and the labels to show. `extra` carries the list's own columns (an
    urgency's ordinal and SLA days, a dimension's `restrictsFootprint`), so one shape serves
    every list and the contract does not grow a shape per list."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "key": "act_now",
                    "kind": "negative",
                    "label": "Act now",
                    "labels": {"en": "Act now", "sv": "Agera nu"},
                    "usageNote": "Something must change within weeks.",
                    "sortOrder": 0,
                    "active": True,
                    "isSystem": False,
                    "isDefault": False,
                    "usageCount": 0,
                    "version": 1,
                    "extra": {"ordinal": 1, "slaDays": 14},
                }
            ]
        }
    )

    key: str = Field(description=_VOCABULARY_KEY, examples=["act_now"])
    kind: str | None = Field(
        default=None,
        description=(
            "The fixed kind the value belongs to, on the lists whose values carry one, and null on the others. "
            "A kind in code, never a vocabulary value: the rules branch on it and an admin never adds one, and "
            f"`kinds` on the list's entry in `GET /vocab` gives the list's set. Per list, {_KINDS_BY_LIST}"
        ),
        examples=["negative"],
    )
    label: str = Field(
        description=(
            "The value's name in the reader's language: the label in the first of the caller's languages "
            "that has one (their own, then their bank's, then English), otherwise the original, otherwise "
            "the key. For display only: a person wrote it and may reword or translate it at any time, so "
            "nothing may match on it."
        ),
        examples=["Act now"],
    )
    labels: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Every label the value has, as a map from content language (`en`, `sv`, `da`, `nb` or `fi`) to "
            "text; a language with no label is absent. `GET /vocab/{list}/{key}` says which one is the "
            "original and which a machine translated. For display and editing, never for matching."
        ),
        examples=[{"en": "Act now", "sv": "Agera nu"}],
    )
    usage_note: str = Field(
        default="",
        description=(
            "When to use the value, in the words of whoever added it, shown beside the picker so two people "
            'choose alike. Guidance, not a rule the server applies; the default "" means nobody wrote one.'
        ),
        examples=["Something must change within weeks."],
    )
    sort_order: int = Field(
        default=0,
        description=(
            "Where the value sits in its list's pickers and filters, lowest first, with the key settling a tie; "
            "0 by default. It orders the list and ranks nothing: an urgency's rank is `extra.ordinal`. "
            "`POST /vocab/{list}/reorder` moves values."
        ),
        examples=[0],
    )
    active: bool = Field(
        default=True,
        description=(
            "True, the default, while pickers offer the value. False once it was retired or merged away: the "
            "records that carry it keep it and still show its label, but no picker offers it and "
            "`GET /vocab/{list}` leaves it out unless `includeRetired` is true."
        ),
        examples=[True],
    )
    is_system: bool = Field(
        default=False,
        description=(
            "True for a value the product relies on, seeded with the platform: it can be relabelled but never "
            "retired or merged away, which answers 409 `system_row`. False, the default, for a value an admin "
            "or an approved proposal added."
        ),
        examples=[True],
    )
    is_default: bool = Field(
        default=False,
        description=(
            "True for the value the list preselects when nobody chooses one. Set by the platform's seed and not changed through this API; false, the default, for every "
            "other value."
        ),
        examples=[False],
    )
    usage_count: int = Field(
        default=0,
        description=(
            "How many records carry the value, counted when the call is answered, so the reach of a rename, "
            "retire or merge is known before it is made. The default of 0 is also what a list whose users are "
            "not counted yet answers: today the library's shared lists count theirs, except `rejection_reason` "
            "and `jurisdiction`, and of a bank's own lists only its tags (`tenant_tag`) do, so 0 on any other "
            "list means not counted, not unused."
        ),
        examples=[0],
    )
    version: int = Field(
        default=1,
        description=(
            "The value's version: 1 when it was added, the default, and one higher with every change to it, a "
            "relabel, a retire, a restore or a merge. Send it back as `If-Match` on `PATCH /vocab/{list}/{key}` "
            "so a change someone made in between is refused with 409 `stale_write` rather than overwritten."
        ),
        examples=[1],
    )
    extra: dict[str, Any] = Field(  # schema: VocabularyExtra
        default_factory=dict,
        description=(
            f"The list's own columns, camelCased, which only some lists have: {_EXTRA_COLUMNS} An empty object "
            "for those. Never a tone or a colour: a value's pill tone follows its kind."
        ),
        examples=[{"ordinal": 1, "slaDays": 14}],
    )
    verified_origin: RowVerifiedOrigin = ""
    confirmed_by_agent: RowConfirmedByAgent = None
    proposed_by_agent: RowProposedByAgent = None


class VocabularyRowDetail(VocabularyRow):
    """`GET /vocab/{list}/{key}`: the value plus which label is the original and which are
    machine-made (I18N-01, D-12): a translation no person confirmed, and every label an
    agent's approval wrote, the original included, until a person's approval rewrites it
    (INV-05, D-62)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "key": "custody",
                    "kind": None,
                    "label": "Custody",
                    "labels": {"en": "Custody", "sv": "Förvaring"},
                    "usageNote": "Safekeeping and administration of clients' financial instruments.",
                    "sortOrder": 2,
                    "active": True,
                    "isSystem": False,
                    "isDefault": False,
                    "usageCount": 12,
                    "version": 3,
                    "extra": {},
                    "originalLanguage": "en",
                    "machineLanguages": ["sv"],
                }
            ]
        }
    )

    original_language: str | None = Field(
        default=None,
        description=(
            "The content language the value was first named in (`en`, `sv`, `da`, `nb` or `fi`), which every "
            "other label translates: English when English was among its first labels, otherwise the language "
            "they were written in. Null for a value whose labels name no original."
        ),
        examples=["en"],
    )
    machine_languages: list[str] = Field(
        default_factory=list,
        description=(
            "The content languages whose label a machine translated and no person has confirmed since, so a "
            "screen can label them as machine output. A person's edit to a label takes its language off this "
            "list. Empty when a person wrote every label."
        ),
        examples=[["sv"]],
    )


class VocabularyRowPage(CamelSchema):
    """The values of one list, in list order, in one answer."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "key": "custody",
                            "kind": None,
                            "label": "Custody",
                            "labels": {"en": "Custody", "sv": "Förvaring"},
                            "usageNote": "Safekeeping and administration of clients' financial instruments.",
                            "sortOrder": 0,
                            "active": True,
                            "isSystem": False,
                            "isDefault": False,
                            "usageCount": 12,
                            "version": 3,
                            "extra": {},
                        }
                    ],
                    "total": 1,
                }
            ]
        }
    )

    items: list[VocabularyRow] = Field(
        description=(
            "The list's values in list order (`sortOrder`, then key), active ones only unless `includeRetired` "
            "asked for the retired ones too. They are vocabulary rows, which a bank's admin adds to its own "
            "lists and a proposal adds to a library list, so read this endpoint for the live set rather than "
            "keeping a copy. Not paginated: a list is short enough to arrive whole, and a list with no values "
            "is a 200 with an empty list."
        )
    )
    total: int = Field(description="How many values `items` holds; the whole list always arrives on this one page.")


class VocabularyCreateBody(WriteBody):
    """The body of `POST /vocab/{list}`: a new value for a list. `key` is optional because a
    person types a label and never a key; `force` is how a holder of vocab.manage insists
    past the near-duplicate hint (VOC-03, AC-VOC3). A field this body does not name answers
    422 rather than being dropped."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "labels": {"en": "Custody services", "sv": "Förvaringstjänster"},
                    "usageNote": "Safekeeping of client assets, including sub-custody arrangements.",
                    "force": False,
                }
            ]
        }
    )

    key: str | None = Field(
        default=None,
        description=(
            "The new value's stable key, which every record, filter, saved search and export will store. "
            f"{_KEY_WRITE} The values are rows of the vocabulary the path names, which an admin may extend, so "
            "`GET /vocab/{list}` gives the live set."
        ),
        examples=["custody_services"],
    )
    labels: dict[str, str] = Field(
        description=(
            f"{_LABELS_WRITE} The first labels a value gets name its original language: English when English "
            "is among them, otherwise the one given."
        ),
        examples=[{"en": "Custody services", "sv": "Förvaringstjänster"}],
    )
    usage_note: str = Field(
        default="",
        description=(
            "When to use the new value, in the writer's words, shown beside the picker; surrounding spaces are "
            'trimmed. The default "" leaves it without one.'
        ),
        examples=["Safekeeping of client assets, including sub-custody arrangements."],
    )
    kind: str | None = Field(
        default=None,
        description=(
            "The fixed kind the new value belongs to, on the lists whose values carry one. A kind in code and "
            "not a vocabulary value: an admin may add values to a list but never a kind, and `kinds` on the "
            f"list's entry in `GET /vocab` gives the set. Per list, {_KINDS_BY_LIST} A list with kinds needs "
            "one, except `instrument_level`, and leaving it out or naming another answers 422 `unknown_key` "
            "with the valid values; a list without kinds ignores this field."
        ),
        examples=["supervisory"],
    )
    sort_order: int | None = Field(
        default=None,
        description=(
            "Where to place the value in the list, lowest first. Left out, it goes last, one after the "
            "highest place the list holds."
        ),
        examples=[3],
    )
    extra: VocabularyExtra = Field(
        default_factory=dict,
        description=f"The list's own columns for the new value, where the list has any: {_EXTRA_COLUMNS} {_EXTRA_WRITE}",
        examples=[{"ordinal": 2, "slaDays": 30}],
    )
    force: bool = Field(
        default=False,
        description=(
            "True creates the value even though its label is close to one the list already holds. False, the "
            "default, refuses such a value with 422 `near_duplicate` and the close matches in `candidates`, so "
            "a typo like `Custdy` beside `Custody` is caught before it splits the records. It never overrides "
            "`duplicate_key`: two values never share a key."
        ),
        examples=[False],
    )


class VocabularyPatchBody(WriteBody):
    """The body of `PATCH /vocab/{list}/{key}` and `PATCH /taxonomy/terms/{termId}`: only
    what changes. A field left out or null keeps its value; the key never changes."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"labels": {"en": "Custody services"}, "usageNote": "Safekeeping of client assets."}]}
    )

    labels: dict[str, str] | None = Field(
        default=None,
        description=(
            "The labels to set, per content language (`en`, `sv`, `da`, `nb` or `fi`), merged into those the "
            "value has: a language named here gets this text and counts as a person's from now on, and a "
            "language left out keeps its label. Null or absent changes no label. An unknown language answers "
            "422 `unknown_key`, and a map whose every text is empty 422 `validation_error`. The key stays what "
            "it was, whatever the labels now say."
        ),
        examples=[{"en": "Custody services"}],
    )
    usage_note: str | None = Field(
        default=None,
        description=(
            "The new usage note, with surrounding spaces trimmed; an empty string clears it. Null or absent "
            "leaves it as it is."
        ),
        examples=["Safekeeping of client assets."],
    )
    sort_order: int | None = Field(
        default=None,
        description=(
            "The value's new place in the list, lowest first. Null or absent leaves it; "
            "`POST /vocab/{list}/reorder` moves several values at once."
        ),
        examples=[1],
    )
    extra: VocabularyExtra | None = Field(
        default=None,
        description=(
            f"The list's own columns to change, where the list has any: {_EXTRA_COLUMNS} A column not named "
            f"keeps its value, and null or absent changes none; a taxonomy term has no such columns and ignores it. "
            f"{_EXTRA_WRITE}"
        ),
        examples=[{"slaDays": 21}],
    )


class VocabularyReorderBody(WriteBody):
    """The body of `POST /vocab/{list}/reorder`: the order a person dragged the values into."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"keys": ["custody", "advice", "pension_transfers"]}]})

    keys: list[str] = Field(
        description=(
            "The keys of the list's values in the order the screen now shows them, first to last. Values not "
            "named keep their order after the ones named, and a key named twice counts at its first place. A "
            "key the list does not hold answers 422 `unknown_key` and nothing moves."
        ),
        examples=[["custody", "advice", "pension_transfers"]],
    )


class VocabularyRetireBody(WriteBody):
    """The body of `POST /vocab/{list}/{key}/retire`."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"confirm": True}]})

    confirm: bool = Field(
        default=False,
        description=(
            "True retires the value even though records carry it. False, the default, retires a value nothing "
            "carries but refuses a used one with 409 `in_use` and its `usageCount`, so the person decides "
            "knowing how many records keep it. Retiring never touches those records: they keep the value and "
            "still show its label."
        ),
        examples=[True],
    )


class VocabularyRetired(CamelSchema):
    """What `POST /vocab/{list}/{key}/retire` answers for a bank's own list."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"key": "custody", "usageCount": 12, "retired": True}]})

    key: str = Field(description="The key of the value just retired; it never changes and a restore brings it back.", examples=["custody"])
    usage_count: int = Field(
        description=(
            "How many records carry the value. They keep it and still show its label; only the pickers stop "
            "offering it."
        ),
        examples=[12],
    )
    retired: bool = Field(
        description="Always true in this answer: the value is retired and no picker offers it any more.",
        examples=[True],
    )


class VocabularyRestored(CamelSchema):
    """What `POST /vocab/{list}/{key}/restore` answers for a bank's own list."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"key": "custody", "usageCount": 12, "restored": True}]})

    key: str = Field(description="The key of the value just restored, the same key it had before it was retired.", examples=["custody"])
    usage_count: int = Field(
        description="How many records carry the value, which kept it all the while it was retired.",
        examples=[12],
    )
    restored: bool = Field(
        description="Always true in this answer: the value is active again and pickers offer it.",
        examples=[True],
    )


class VocabularyMergeBody(WriteBody):
    """The body of `POST /vocab/{list}/{key}/merge`: the value to keep."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"into": "custody"}]})

    into: str = Field(
        description=(
            "The key of the value to keep, on the same list; the records that carry the value in the path move "
            "to it. Naming that same value answers 422 `validation_error`, and a key the list does not hold "
            "404 `not_found`."
        ),
        examples=["custody"],
    )


class VocabularyMerged(CamelSchema):
    """Both the dry run and the commit answer this shape, so the screen renders one
    preview and one result from the same fields (playbook 15: dry run, preview, commit)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"from": "custody_services", "into": "custody", "usageCount": 5, "repointed": 4, "dryRun": True}]
        }
    )

    from_: str = Field(
        alias="from",
        description=(
            "The key of the value merged away. After the merge it is retired, kept only so history stays "
            "readable, and the records counted in `repointed` carry `into` instead."
        ),
        examples=["custody_services"],
    )
    into: str = Field(description="The key of the value kept, which the records the merge moved now carry.", examples=["custody"])
    usage_count: int = Field(
        description="How many records carried the merged-away value when the call was answered.",
        examples=[5],
    )
    repointed: int = Field(
        description=(
            "How many records move to `into` in a preview, or moved in a merge. It can be lower than "
            "`usageCount`: a record that already carried both values keeps a single link to `into`, so "
            "nothing is counted twice."
        ),
        examples=[4],
    )
    dry_run: bool = Field(
        description=(
            "True when this is a preview: nothing changed and no audit event was written. False when the merge "
            "was made."
        ),
        examples=[True],
    )


class VocabularySuggestBody(WriteBody):
    """The body of `POST /vocab/{list}/suggest`: a value a member without `vocab.manage`
    wants added."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "labels": {"en": "Pension transfers"},
                    "usageNote": "Moving an occupational pension from one provider to another.",
                }
            ]
        }
    )

    key: str | None = Field(
        default=None,
        description=f"The key the value would get. {_KEY_WRITE}",
        examples=["pension_transfers"],
    )
    labels: dict[str, str] = Field(description=_LABELS_WRITE, examples=[{"en": "Pension transfers"}])
    usage_note: str = Field(
        default="",
        description=(
            "Why the value is needed, in the member's words, which the admin reads in the inbox; surrounding "
            'spaces are trimmed. The default "" sends none.'
        ),
        examples=["Moving an occupational pension from one provider to another."],
    )


class VocabularySuggestionRow(CamelSchema):
    """One suggestion in a bank's own inbox: a value a member asked an admin to add. The
    bank's own data, never shared with another bank or with the platform."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "6d2f9a14-8b3e-4c71-a5d0-3e9b1f7c2a58",
                    "list": "tenant_tag",
                    "key": "pension_transfers",
                    "labels": {"en": "Pension transfers"},
                    "usageNote": "Moving an occupational pension from one provider to another.",
                    "suggestedBy": {"id": "0b7e4c2d-9f61-4a38-b5e2-7c1d8a3f6e90", "name": "Oskar Lund"},
                    "status": "pending",
                    "createdAt": "2026-09-18T10:12:00Z",
                }
            ]
        }
    )

    id: UUID = Field(
        description=(
            "The suggestion, as `POST /vocab/{list}/suggestions/{suggestionId}/decline` addresses it: a UUID "
            "the server assigns once and never changes."
        ),
        examples=["6d2f9a14-8b3e-4c71-a5d0-3e9b1f7c2a58"],
    )
    list: str = Field(
        description="The name of the bank's own list the suggestion is for, such as `tenant_tag`.",
        examples=["tenant_tag"],
    )
    key: str = Field(
        description=(
            "The key the value would get. An admin who creates a value with this key on the list answers the "
            "suggestion, and every other waiting suggestion for the same key, at once."
        ),
        examples=["pension_transfers"],
    )
    labels: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "The labels the member suggested, per content language (`en`, `sv`, `da`, `nb` or `fi`), as they "
            "typed them apart from surrounding spaces."
        ),
        examples=[{"en": "Pension transfers"}],
    )
    usage_note: str = Field(
        default="",
        description='Why the member wants the value, in their own words; the default "" means they gave no reason.',
        examples=["Moving an occupational pension from one provider to another."],
    )
    suggested_by: PersonRef | None = Field(
        default=None,
        description=(
            "The member who suggested it, by id and name, the only personal data a suggestion carries. Always "
            "set on a suggestion this API returns."
        ),
    )
    status: str = Field(
        description=(
            "Where the suggestion stands, a fixed kind and not a vocabulary: `pending` while it waits in the "
            "admin's inbox, `accepted` once an admin created a value with its key, and `declined` once an admin "
            "turned it down. Only a `pending` suggestion is listed in the inbox."
        ),
        examples=["pending"],
    )
    created_at: datetime = Field(
        description="When the member sent it: a UTC timestamp, date and time together. The inbox is worked oldest first by it.",
        examples=["2026-09-18T10:12:00Z"],
    )


class VocabularySuggestionPage(CamelSchema):
    """`GET /vocab/{list}/suggestions`: one page of the suggestions waiting in one of the
    organisation's own lists, oldest first."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "id": "6d2f9a14-8b3e-4c71-a5d0-3e9b1f7c2a58",
                            "list": "tenant_tag",
                            "key": "pension_transfers",
                            "labels": {"en": "Pension transfers"},
                            "usageNote": "Moving an occupational pension from one provider to another.",
                            "suggestedBy": {"id": "0b7e4c2d-9f61-4a38-b5e2-7c1d8a3f6e90", "name": "Oskar Lund"},
                            "status": "pending",
                            "createdAt": "2026-09-18T10:12:00Z",
                        }
                    ],
                    "total": 1,
                }
            ]
        }
    )

    items: list[VocabularySuggestionRow] = Field(
        description=(
            "This page of the list's waiting suggestions, oldest first, at most `limit` of them. Only a "
            "suggestion an admin has not answered yet is here: one whose row was created, or that was "
            "declined, has left the inbox."
        )
    )
    total: int = Field(
        description="How many suggestions wait in this list across every page, counted at the moment of the call."
    )


# ---------------------------------------------------------------------------------------
# Taxonomy terms (library; every write is a proposal, VOC-07)
# ---------------------------------------------------------------------------------------
class TaxonomyTermRow(CamelSchema):
    """One term of the shared library's taxonomy (FP-01): the values a bank chooses in its
    regulatory scope and a record is tagged with, one dimension each. A library fact,
    changed only through an approved proposal (VOC-07)."""

    id: UUID = Field(
        description=(
            "The term's identifier, a UUID that never changes; `PATCH /taxonomy/terms/{termId}` takes it. "
            "Filters, scopes and records name a term by its dimension and key instead."
        ),
        examples=["3f6a2c18-9b4d-4e27-8c51-7d0e2a9b6f34"],
    )
    key: str = Field(
        description=(
            "The term's immutable key, unique within its dimension, such as `advice` in `service_type`: "
            "the part to store, compare and send back, together with the dimension's key. Terms are rows "
            "of the shared library's taxonomy vocabulary, which an administrator may extend through an "
            "approved proposal (`POST /taxonomy/terms`); this list is the live set. A key never changes "
            "and is never reused, a retired term's included."
        ),
        examples=["advice"],
    )
    kind: str | None = Field(
        default=None,
        description=(
            "Always null by default and in every row: a term carries no kind of its own, because its "
            "dimension is its kind (`dimension.kind`). Present so one pill component reads a term like any "
            "other vocabulary value."
        ),
        examples=[None],
    )
    label: str = Field(
        description=(
            "The term's name in the reader's language (the caller's language, the organisation's default "
            "language, then English), for display only. It may be reworded or translated at any time, so "
            "nothing may match on it."
        ),
        examples=["Advice"],
    )
    labels: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Every label the term has, by language key (`en`, `sv`, `da`, `nb`, `fi`), for an editor "
            "showing all translations at once. A language with no label is absent rather than empty; "
            "defaults to an empty map only for a term nobody labelled."
        ),
        examples=[{"en": "Advice", "sv": "Rådgivning"}],
    )
    dimension: TaxonomyDimensionRef = Field(
        description=(
            "The dimension the term belongs to: its key, its kind (`scope`, `classification` or `opt_in`) "
            "and its label. Dimensions are rows of the shared library's `term_dimension` vocabulary, which "
            "an administrator may extend through an approved proposal; `GET /taxonomy/dimensions` lists the "
            "live set."
        ),
    )
    parent_key: str | None = Field(
        default=None,
        description=(
            "The key of the broader term this one sits under, in the same dimension, for a picker that "
            "shows a tree; null by default, for a term at the top. A row of the same taxonomy vocabulary, "
            "which an administrator may extend through an approved proposal."
        ),
        examples=[None],
    )
    usage_note: str = Field(
        default="",
        description=(
            "When to use the term, one or two sentences an editor wrote for whoever tags a record or sets "
            "a scope; empty when there is none. Guidance only, never a rule the server applies."
        ),
        examples=["Personal recommendations on financial instruments."],
    )
    sort_order: int = Field(
        default=0,
        description=(
            "The term's place in its dimension's picker, ascending, with the key settling a tie; 0 by "
            "default. The list already comes back in this order."
        ),
        examples=[1],
    )
    active: bool = Field(
        default=True,
        description=(
            "True, the default, for a term a scope or a record can use today. False for a retired term, "
            "which only `includeRetired=true` returns: it stays on the records that carry it and in history, "
            "is offered in no picker, and its key is never reused."
        ),
        examples=[True],
    )
    is_system: bool = Field(
        default=False,
        description=(
            "True for a term the platform seeded with the reference data; false, the default, for one "
            "added later through an approved proposal. Either way the key never changes."
        ),
        examples=[True],
    )
    version: int = Field(
        default=1,
        description=(
            "The term's version, 1 when created and one higher with every approved change. Send it as "
            "`If-Match` on `PATCH /taxonomy/terms/{termId}` to be told with 409 `stale_write` when someone "
            "changed the term first."
        ),
        examples=[1],
    )
    mirrored: bool = Field(
        default=False,
        description=(
            "True for a term of the dimension that mirrors the markets the platform covers: "
            "the reference data keeps those terms in step with the jurisdiction list, so none "
            "is proposed, renamed or put on a change or an obligation, and a write that names "
            "one answers 422 `jurisdiction_term_mirrored`. A record's market comes from its "
            "instrument or its authority instead. False for every other term."
        ),
        examples=[False],
    )
    verified_origin: RowVerifiedOrigin = ""
    confirmed_by_agent: RowConfirmedByAgent = None
    proposed_by_agent: RowProposedByAgent = None


class TaxonomyTermPage(CamelSchema):
    """`GET /taxonomy/terms`: every term asked for, in picker order. A reference list, not a
    page: it is short and never paginates."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "id": "3f6a2c18-9b4d-4e27-8c51-7d0e2a9b6f34",
                            "key": "advice",
                            "kind": None,
                            "label": "Advice",
                            "labels": {"en": "Advice", "sv": "Rådgivning"},
                            "dimension": {"key": "service_type", "kind": "scope", "label": "Service"},
                            "parentKey": None,
                            "usageNote": "",
                            "sortOrder": 1,
                            "active": True,
                            "isSystem": True,
                            "version": 1,
                            "mirrored": False,
                        },
                        {
                            "id": "a81d4f60-2c7e-4b93-9e05-6f3b1c8d2a47",
                            "key": "execution_only",
                            "kind": None,
                            "label": "Execution only",
                            "labels": {"en": "Execution only", "sv": "Endast utförande"},
                            "dimension": {"key": "service_type", "kind": "scope", "label": "Service"},
                            "parentKey": None,
                            "usageNote": "",
                            "sortOrder": 3,
                            "active": True,
                            "isSystem": True,
                            "version": 1,
                            "mirrored": False,
                        },
                    ],
                    "total": 2,
                }
            ]
        }
    )

    items: list[TaxonomyTermRow] = Field(
        description=(
            "The terms, ordered by dimension, then by each term's place in its picker, then by key; only "
            "active ones unless `includeRetired=true`. Terms are rows of the shared library's taxonomy "
            "vocabulary, which an administrator may extend through an approved proposal, so the set grows "
            "without a deploy. Empty when the dimension has no terms."
        )
    )
    total: int = Field(
        description="How many terms `items` holds: the whole answer, since this list never paginates."
    )


class TaxonomyTermCreateBody(WriteBody):
    """`POST /taxonomy/terms`: what a new term should be. Sending it files a proposal and
    changes nothing in the library until a second person approves it (VOC-07)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "dimension": "service_type",
                    "key": "investment_research",
                    "labels": {"en": "Investment research", "sv": "Investeringsanalys"},
                    "usageNote": "Research and recommendations published to clients at large, not personal advice.",
                    "parent": None,
                }
            ]
        }
    )

    dimension: str = Field(
        description=(
            "The key of the dimension the term joins, such as `service_type` or `client_category`. "
            "Dimensions are rows of the shared library's `term_dimension` vocabulary, which an "
            "administrator may extend through an approved proposal; `GET /taxonomy/dimensions` lists the "
            "live set. An unknown or retired dimension answers 422 `unknown_key`, and the `jurisdiction` "
            "dimension, whose terms mirror the jurisdiction list, answers 422 `jurisdiction_term_mirrored`."
        ),
        examples=["service_type"],
    )
    key: str | None = Field(
        default=None,
        description=(
            "The key the term should have, lowercase words joined by underscores such as "
            "`investment_research`; anything else is turned into that form. Leave it out, the default, and "
            "the key is made the same way from the English label, or from the first label given. A key "
            "already taken in the dimension, by a retired term too, answers 409 `duplicate_key`; one that "
            "makes no key answers 422 `validation_error`. Once approved the key never changes."
        ),
        examples=["investment_research"],
    )
    labels: dict[str, str] = Field(
        description=(
            "The term's name by language key, at least one: `en`, `sv`, `da`, `nb` or `fi`, the platform's "
            "content languages. Blank labels are dropped; none left answers 422 `validation_error`, and a "
            "language the platform does not hold answers 422 `unknown_key` with the valid ones."
        ),
        examples=[{"en": "Investment research", "sv": "Investeringsanalys"}],
    )
    usage_note: str = Field(
        default="",
        description=(
            "When to use the term, a sentence or two for whoever tags a record or sets a scope; empty by "
            "default. Surrounding whitespace is trimmed."
        ),
        examples=["Research and recommendations published to clients at large, not personal advice."],
    )
    parent: str | None = Field(
        default=None,
        description=(
            "The key of an existing active term of the same dimension to sit under, for a term that "
            "narrows a broader one; null by default, for a term at the top. Anything else answers 422 "
            "`unknown_key` with the valid keys."
        ),
        examples=[None],
    )


class TaxonomyDimensionPage(CamelSchema):
    """`GET /taxonomy/dimensions`: every active dimension of the taxonomy, in picker order.
    A reference list, not a page: it is short and never paginates."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "key": "service_type",
                            "kind": "scope",
                            "label": "Service",
                            "labels": {"en": "Service", "sv": "Tjänst"},
                            "usageNote": "The investment or insurance service offered.",
                            "sortOrder": 4,
                            "active": True,
                            "isSystem": True,
                            "isDefault": False,
                            "usageCount": 6,
                            "version": 1,
                            "extra": {"restrictsFootprint": True},
                        },
                        {
                            "key": "theme",
                            "kind": "classification",
                            "label": "Theme",
                            "labels": {"en": "Theme", "sv": "Tema"},
                            "usageNote": "What the rule is about, for browsing and briefings. Never narrows the footprint.",
                            "sortOrder": 9,
                            "active": True,
                            "isSystem": True,
                            "isDefault": False,
                            "usageCount": 0,
                            "version": 1,
                            "extra": {"restrictsFootprint": False},
                        },
                    ],
                    "total": 2,
                }
            ]
        }
    )

    items: list[VocabularyRow] = Field(
        description=(
            "The dimensions, each a row of the shared library's `term_dimension` vocabulary, which an "
            "administrator may extend through an approved proposal. Its `kind` is `scope` (the dimension "
            "says who or what a rule covers), `classification` (it only describes a record and never "
            "narrows a regulatory scope) or `opt_in` (the standards a bank follows: a record carrying one "
            "shows only to a bank whose scope names it). `extra.restrictsFootprint` says whether the terms "
            "chosen in it narrow what a bank sees. Only active dimensions, in picker order."
        )
    )
    total: int = Field(
        description="How many dimensions `items` holds: the whole answer, since this list never paginates."
    )


# ---------------------------------------------------------------------------------------
# Footprint (FP-01, FP-02, FP-03)
# ---------------------------------------------------------------------------------------
class FootprintPreviewCount(CamelSchema):
    """What a regulatory scope change would hide and reveal for one record kind: the
    obligations this bank can see, or this bank's open cases. Zeros with `available:false`
    say "not counted", never "none" (playbook 4.4)."""

    hidden: int = Field(
        default=0,
        ge=0,
        description=(
            "How many records of this kind are inside the bank's regulatory scope today and would fall "
            "outside it once the change is approved. For obligations these are the library obligations "
            "the bank can see; for cases, the bank's own open cases (every case not closed or dismissed), "
            "judged by the scope of the regulatory change each case follows. Computed by the server with "
            "the same scope rule every list uses, including the opt-in rule for the standards a bank "
            "follows. A hidden record is not deleted and a case keeps its owner and its decisions; it only "
            "leaves the screens filtered by the scope. Never negative; 0 when nothing would be hidden."
        ),
    )
    revealed: int = Field(
        default=0,
        ge=0,
        description=(
            "How many records of this kind are outside the bank's regulatory scope today and would come "
            "inside it once the change is approved, counted over the same records and by the same rule "
            "as `hidden`. A record with no scope terms is inside every scope, so it is never hidden or "
            "revealed. Never negative; 0 when nothing would appear."
        ),
    )
    available: bool = Field(
        default=False,
        description=(
            "Whether the server counted this record kind at all. True: `hidden` and `revealed` are real "
            "counts, and zeros mean none. False: nothing was counted and the zeros say nothing, which a "
            "screen shows as not counted rather than as none. Obligations and cases are both counted "
            "today; a request decided before cases were counted keeps the counts it was decided against, "
            "so its cases may still read false."
        ),
    )


class FootprintPreview(CamelSchema):
    """The named schema behind `footprint_change_request.preview` (JSONField)."""

    obligations: FootprintPreviewCount = Field(
        default_factory=FootprintPreviewCount,
        description=(
            "What the change would hide and reveal among the shared library's obligations this bank can "
            "see. Computed by the server; by default nothing counted."
        ),
    )
    cases: FootprintPreviewCount = Field(
        default_factory=FootprintPreviewCount,
        description=(
            "What the change would hide and reveal among this bank's own open cases, judged by the scope "
            "of the regulatory change each follows. Computed by the server; by default nothing counted. "
            "Hiding a case never closes it or takes it from its owner."
        ),
    )


class FootprintDimension(CamelSchema):
    """One group of the regulatory scope (FP-01): a taxonomy dimension, whether it narrows
    the scope, and the terms this bank has chosen in it. The dimension's kind says how an
    empty group reads: no restriction for a scope dimension, none followed for an opt-in one."""

    dimension: TaxonomyDimensionRef = Field(
        description=(
            "The taxonomy dimension this group covers: its key, its kind and its label in the caller's "
            "language. The kind is `scope` for a dimension that says who or what a rule covers, "
            "`classification` for one that only describes a record and never narrows the scope, and "
            "`opt_in` for the standards a bank follows, where a record carrying one of the dimension's "
            "terms shows only when this group names that term, so an empty group means none followed "
            "rather than no restriction. Dimensions are rows of the shared library's `term_dimension` "
            "vocabulary, which an administrator may extend through an approved proposal; "
            "`GET /taxonomy/dimensions` lists the live set."
        )
    )
    restricts_footprint: bool = Field(
        description=(
            "True when the terms chosen in this group narrow what the bank sees. False for a dimension "
            "that only describes records, which never hides anything. Always true for an `opt_in` "
            "dimension, whatever its own flag says. A library fact, changed only through an approved "
            "proposal."
        )
    )
    terms: list[TermRef] = Field(
        default_factory=list,
        description=(
            "The terms this bank has chosen in the group, each its key and its label in the caller's "
            "language, in picker order; empty when it has chosen none. Terms are rows of the shared "
            "library's taxonomy vocabulary, which an administrator may extend through an approved "
            "proposal; `GET /taxonomy/terms` lists the live set. Changed only through a regulatory "
            "scope change request with its preview, second person and step-up."
        )
    )
    all_selected: bool = Field(
        default=False,
        description=(
            "True when the bank has chosen every active term of the dimension, which the screen reads "
            "as all selected. Defaults to false, also for a dimension that has no active terms."
        ),
    )


class FootprintTermRef(TermRef):
    """A taxonomy term in a regulatory scope change: the term as a reference, plus the key of
    the dimension it belongs to, since a term key is unique only within its dimension."""

    dimension: str = Field(
        description=(
            "The key of the term's dimension, such as `service_type`; with `key` it names the term. "
            "Dimensions are rows of the shared library's `term_dimension` vocabulary, which an "
            "administrator may extend through an approved proposal; `GET /taxonomy/dimensions` lists them."
        ),
        examples=["service_type"],
    )


_FOOTPRINT_REQUEST_EXAMPLE: dict[str, Any] = {
    "id": "5b0c7e1a-3f2d-4c8e-9a61-2d7f0e4b9c13",
    "status": "pending",
    "requestedBy": {"id": "8a3c1e5f-2d4b-4f60-9e7a-1b2c3d4e5f60", "name": "Sara Lindqvist"},
    "requestedAt": "2026-09-18T07:40:00Z",
    "adds": [{"key": "insurance_distribution", "kind": None, "label": "Insurance distribution", "dimension": "service_type"}],
    "removes": [{"key": "advice", "kind": None, "label": "Advice", "dimension": "service_type"}],
    "preview": {"obligations": {"hidden": 2, "revealed": 2, "available": True}, "cases": {"hidden": 0, "revealed": 1, "available": True}},
    "decidedBy": None,
    "decidedAt": None,
    "decisionNote": "",
    "version": 1,
}


class FootprintRequestRow(CamelSchema):
    """One request to change the organisation's regulatory scope (FP-02): what it adds and
    removes, what that would hide and reveal, who asked and who decided. The scope changes
    only when a second person approves it with a passkey."""

    model_config = ConfigDict(json_schema_extra={"examples": [_FOOTPRINT_REQUEST_EXAMPLE]})

    id: UUID = Field(
        description=(
            "The request's identifier, a UUID that never changes; the approve, reject and withdraw calls "
            "take it in their path."
        ),
        examples=["5b0c7e1a-3f2d-4c8e-9a61-2d7f0e4b9c13"],
    )
    status: str = Field(
        description=(
            "Where the request stands, one of four fixed values. `pending`: waiting for a second person; "
            "the scope is unchanged, and an organisation has at most one pending request. `approved`: a "
            "second person approved it with a passkey and the scope changed at that moment. `rejected`: a "
            "second person turned it down and the scope is unchanged. `withdrawn`: the requester took it "
            "back before anyone decided and the scope is unchanged. Only `pending` can still change; the "
            "other three are final. A kind in code, never extended by an administrator."
        ),
        examples=["pending"],
    )
    requested_by: PersonRef | None = Field(
        default=None,
        description=(
            "The member who asked for the change, by id and name. Every request has one, so the default "
            "of null never reaches a reader."
        ),
    )
    requested_at: datetime = Field(
        description="When the request was sent, a UTC timestamp set by the server.",
        examples=["2026-09-18T07:40:00Z"],
    )
    adds: list[FootprintTermRef] = Field(
        default_factory=list,
        description=(
            "The terms the change puts into the regulatory scope, each with its dimension; empty by "
            "default, when it only removes. Terms are rows of the shared library's taxonomy vocabulary, "
            "which an administrator may extend through an approved proposal."
        ),
    )
    removes: list[FootprintTermRef] = Field(
        default_factory=list,
        description=(
            "The terms the change takes out of the regulatory scope, each with its dimension; empty by "
            "default, when it only adds. Terms are rows of the shared library's taxonomy vocabulary, which "
            "an administrator may extend through an approved proposal."
        ),
    )
    preview: FootprintPreview = Field(
        description=(
            "What the change hides and reveals, computed by the server. A pending request is counted "
            "again on every read, against today's library, so the approver decides on the effect now; a "
            "decided request keeps the counts it was decided against, the same ones its audit event holds."
        )
    )
    decided_by: PersonRef | None = Field(
        default=None,
        description=(
            "The second person who approved or rejected the request, by id and name; never the requester, "
            "which the database itself refuses. Null by default: while the request is pending, and when it "
            "was withdrawn, since withdrawing is not a decision."
        ),
    )
    decided_at: datetime | None = Field(
        default=None,
        description=(
            "When the request was approved, rejected or withdrawn, a UTC timestamp set by the server; null "
            "by default, while it is pending."
        ),
        examples=[None],
    )
    decision_note: str = Field(
        default="",
        description=(
            "What the person deciding wrote about it, such as why a change was turned down; empty by "
            "default, when they wrote nothing and always for a withdrawn request. The organisation's own "
            "text, never shared outside it."
        ),
        examples=[""],
    )
    version: int = Field(
        default=1,
        description=(
            "The request's version: 1 while pending, 2 once decided. Send it as `If-Match` when approving, "
            "rejecting or withdrawing to be told with 409 `stale_write` if the request moved on since you "
            "read it."
        ),
        examples=[1],
    )


MarketLevel = Literal["operating", "watching", "not_followed"]


class MarketRow(CamelSchema):
    """One active country's market level (FP-04), computed fresh on every read and never
    stored, so it cannot drift from the two facts it is read from: the tenant's regulatory
    scope, which only a footprint change request changes (FP-02), and the tenant's watch
    list, a direct write that hides nothing."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"jurisdiction": {"key": "no", "kind": "country", "label": "Norway"}, "level": "watching"}]}
    )

    jurisdiction: TermRef = Field(
        description=(
            "The country: its key, kind (always `country`) and label in the caller's language. A row of "
            "the jurisdiction vocabulary; an admin may add more without a deploy, and `GET /reference/jurisdictions` "
            "lists the live set."
        )
    )
    level: MarketLevel = Field(
        description=(
            "How closely the tenant follows this country, computed by the server on every read and never stored. "
            "Operating comes first, then watching:\n"
            "- `operating`: the country's mirrored jurisdiction term is in the tenant's regulatory scope, so its "
            "rules are part of what applies. Changes only through a footprint change request with its preview, "
            "second person and step-up.\n"
            "- `watching`: not operating, and the tenant has a `watched_market` row naming the country, set directly "
            "with `POST /tenant/footprint/watching` with no second person and no step-up, because watching hides "
            "nothing. A country watched before it started operating reads as `watching` again once operating stops.\n"
            "- `not_followed`: neither; approving or reversing a scope change never writes a watch row, so a country "
            "never watched drops back here when operating stops.\n"
            "Operating or watching says nothing about whether the tenant complies with anything there."
        ),
        examples=["operating"],
    )


class MarketWatchBody(WriteBody):
    """`POST /tenant/footprint/watching` and `POST /tenant/footprint/watching/remove`
    (FP-04): the jurisdiction key rides in the body on both routes, never in the path or a
    query string, because the tenant's watch list is sensitive and does not belong on an
    access log line."""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"jurisdiction": "no"}]})

    jurisdiction: str = Field(
        min_length=1,
        max_length=80,
        description=(
            "The key of a row of the jurisdiction vocabulary naming a country, at most 80 characters, "
            "such as `no` for Norway (`GET /reference/jurisdictions` lists the live rows; an admin may "
            "add more without a deploy). The union itself, an unknown or inactive key, or a supranational "
            "key answers 422 `unknown_key` or `not_a_country`."
        ),
        examples=["no"],
    )


class FootprintView(CamelSchema):
    """`GET /tenant/footprint`: the organisation's regulatory scope, group by group, the
    change waiting for a second person, and the markets it operates in and watches (FP-01,
    FP-04)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "dimensions": [
                        {
                            "dimension": {"key": "service_type", "kind": "scope", "label": "Service"},
                            "restrictsFootprint": True,
                            "terms": [
                                {"key": "advice", "kind": None, "label": "Advice"},
                                {"key": "custody", "kind": None, "label": "Custody"},
                            ],
                            "allSelected": False,
                        },
                        {
                            "dimension": {"key": "standard", "kind": "opt_in", "label": "Standards followed"},
                            "restrictsFootprint": True,
                            "terms": [],
                            "allSelected": False,
                        },
                    ],
                    "pendingRequest": _FOOTPRINT_REQUEST_EXAMPLE,
                    "markets": [
                        {"jurisdiction": {"key": "se", "kind": "country", "label": "Sweden"}, "level": "operating"},
                        {"jurisdiction": {"key": "no", "kind": "country", "label": "Norway"}, "level": "watching"},
                    ],
                }
            ]
        }
    )

    dimensions: list[FootprintDimension] = Field(
        description=(
            "One group per active taxonomy dimension, in picker order, each with the terms this "
            "organisation has chosen in it. Every active dimension is here, also one with no term chosen, "
            "which reads as no restriction, or as none followed for an opt-in dimension."
        )
    )
    pending_request: FootprintRequestRow | None = Field(
        default=None,
        description=(
            "The change to the scope waiting for a second person, with a preview counted against today's "
            "library; null by default, when none waits. There is at most one at a time, and the scope "
            "above does not include it until it is approved."
        ),
    )
    markets: list[MarketRow] = Field(
        default_factory=list,
        description="Every active country's operating and watching level, one row per country, in jurisdiction sort order (FP-04).",
    )


class FootprintRequestPage(CamelSchema):
    """`GET /tenant/footprint/requests`: one page of the organisation's regulatory scope
    change requests, newest first."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "id": "5b0c7e1a-3f2d-4c8e-9a61-2d7f0e4b9c13",
                            "status": "pending",
                            "requestedBy": {"id": "8a3c1e5f-2d4b-4f60-9e7a-1b2c3d4e5f60", "name": "Sara Lindqvist"},
                            "requestedAt": "2026-09-18T07:40:00Z",
                            "adds": [
                                {"key": "insurance_distribution", "kind": None, "label": "Insurance distribution", "dimension": "service_type"},
                                {"key": "retail", "kind": None, "label": "Retail", "dimension": "client_category"},
                            ],
                            "removes": [{"key": "advice", "kind": None, "label": "Advice", "dimension": "service_type"}],
                            "preview": {
                                "obligations": {"hidden": 2, "revealed": 2, "available": True},
                                "cases": {"hidden": 0, "revealed": 0, "available": False},
                            },
                            "decidedBy": None,
                            "decidedAt": None,
                            "decisionNote": "",
                            "version": 1,
                        },
                        {
                            "id": "e41f7b2c-6a95-4d08-b3c1-9f2e8d7a6b54",
                            "status": "rejected",
                            "requestedBy": {"id": "8a3c1e5f-2d4b-4f60-9e7a-1b2c3d4e5f60", "name": "Sara Lindqvist"},
                            "requestedAt": "2026-09-01T13:20:00Z",
                            "adds": [],
                            "removes": [{"key": "tax", "kind": None, "label": "Tax", "dimension": "regime"}],
                            "preview": {
                                "obligations": {"hidden": 3, "revealed": 0, "available": True},
                                "cases": {"hidden": 0, "revealed": 0, "available": False},
                            },
                            "decidedBy": {"id": "c7d2e9a1-4b6f-4c83-a0e5-6f1b9d2c8e47", "name": "Maria Ek"},
                            "decidedAt": "2026-09-02T07:40:00Z",
                            "decisionNote": "ISK tax reporting is ours.",
                            "version": 2,
                        },
                    ],
                    "total": 2,
                }
            ]
        }
    )

    items: list[FootprintRequestRow] = Field(
        description=(
            "This page of the organisation's regulatory scope change requests, newest first, at most "
            "`limit` of them: the one waiting for a second person, if there is one, and every request "
            "already approved, rejected or withdrawn. A decided request is never deleted."
        )
    )
    total: int = Field(
        description="How many change requests the organisation has sent in all, across every page, counted at the moment of the call."
    )


class FootprintTermSelector(CamelSchema):
    """One taxonomy term named by its dimension and key, as a scope change sends it."""

    dimension: str = Field(
        description=(
            "The key of the term's dimension, such as `service_type`. Dimensions are rows of the shared "
            "library's `term_dimension` vocabulary, which an administrator may extend through an approved "
            "proposal; `GET /taxonomy/dimensions` lists them. An unknown or retired one answers 422 "
            "`unknown_key` with the valid keys."
        ),
        examples=["service_type"],
    )
    key: str = Field(
        description=(
            "The key of the term within that dimension, such as `insurance_distribution`. Terms are rows of "
            "the shared library's taxonomy vocabulary, which an administrator may extend through an approved "
            "proposal; `GET /taxonomy/terms?dimension=…` lists them. An unknown or retired term answers 422 "
            "`unknown_key` with the valid keys."
        ),
        examples=["insurance_distribution"],
    )


class FootprintRequestBody(CamelSchema):
    """`POST /tenant/footprint/requests`: the terms to put into and take out of the
    organisation's regulatory scope, previewed with `dryRun=true` or sent for approval."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "adds": [{"dimension": "service_type", "key": "insurance_distribution"}],
                    "removes": [{"dimension": "service_type", "key": "advice"}],
                }
            ]
        }
    )

    adds: list[FootprintTermSelector] = Field(
        default_factory=list,
        description=(
            "The terms to put into the regulatory scope; empty by default. A term already in the scope "
            "changes nothing when approved. With `removes`, at least one term in all, and no term in both; "
            "otherwise 422 `validation_error`."
        ),
    )
    removes: list[FootprintTermSelector] = Field(
        default_factory=list,
        description=(
            "The terms to take out of the regulatory scope; empty by default. A term not in the scope "
            "changes nothing when approved. With `adds`, at least one term in all, and no term in both; "
            "otherwise 422 `validation_error`."
        ),
    )


class FootprintDecisionBody(CamelSchema):
    """What the second person sends with an approval or a rejection."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"note": "Matches the new insurance distribution licence."}]})

    note: str = Field(
        default="",
        description=(
            "Why the change was approved or rejected, kept on the request and in its audit event for "
            "whoever reads the history; empty by default. The organisation's own text, never shared outside it."
        ),
        examples=["Matches the new insurance distribution licence."],
    )


class FootprintDryRun(CamelSchema):
    """`POST /tenant/footprint/requests?dryRun=true` (playbook 15: dry run, preview,
    commit): what the change would hide and reveal, with nothing persisted, no audit event
    and no approval started. The same `adds`, `removes` and `preview` the created request
    would carry, so the screen renders the preview and the request from one shape."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "adds": _FOOTPRINT_REQUEST_EXAMPLE["adds"],
                    "removes": _FOOTPRINT_REQUEST_EXAMPLE["removes"],
                    "preview": _FOOTPRINT_REQUEST_EXAMPLE["preview"],
                    "dryRun": True,
                }
            ]
        }
    )

    adds: list[FootprintTermRef] = Field(
        default_factory=list,
        description=(
            "The terms the change would put into the regulatory scope, as sent, each with its label and "
            "dimension; empty by default. Terms are rows of the shared library's taxonomy vocabulary, which "
            "an administrator may extend through an approved proposal."
        ),
    )
    removes: list[FootprintTermRef] = Field(
        default_factory=list,
        description=(
            "The terms the change would take out of the regulatory scope, as sent, each with its label and "
            "dimension; empty by default. Terms are rows of the shared library's taxonomy vocabulary, which "
            "an administrator may extend through an approved proposal."
        ),
    )
    preview: FootprintPreview = Field(
        description=(
            "What the change would hide and reveal if it were approved now, counted by the server with the "
            "same rule every list uses. Nothing is stored; a request sent afterwards is counted again."
        )
    )
    dry_run: bool = Field(
        default=True,
        description=(
            "Always true, the default: this answer is a preview, and no request, approval or audit event "
            "exists because of it."
        ),
        examples=[True],
    )


# ---------------------------------------------------------------------------------------
# Query parameters: camelCase on the wire like every other name (`includeRetired`, `dryRun`)
# ---------------------------------------------------------------------------------------
class VocabularyQuery(CamelSchema):
    include_retired: bool = Field(
        default=False,
        description=(
            "True also returns the values that were retired or merged away, each with `active` false, which "
            "an admin screen needs to restore one. False, the default, returns only what pickers offer."
        ),
        examples=[True],
    )


class TaxonomyTermQuery(CamelSchema):
    dimension: str | None = Field(
        default=None,
        description=(
            "Only the terms of this dimension, by its key, such as `service_type`; left out by default, "
            "every dimension's terms. Dimensions are rows of the shared library's `term_dimension` "
            "vocabulary, which an administrator may extend through an approved proposal; "
            "`GET /taxonomy/dimensions` lists them. An unknown or retired dimension answers 422 "
            "`unknown_key` with the valid keys."
        ),
    )
    include_retired: bool = Field(
        default=False,
        description=(
            "True also returns retired terms, marked `active: false`, for an editor or for reading an old "
            "record. False, the default, returns only the terms a scope or a record can use today."
        ),
    )


class VocabularyMergeQuery(CamelSchema):
    dry_run: bool = Field(
        default=False,
        description=(
            "True previews the merge and changes nothing: the answer is a 200 with how many records would "
            "move, no proposal is filed and no audit event is written, on a library list as on a bank's own. "
            "False, the default, makes the merge on a bank's own list (200) or files it as a proposal on a "
            "library list (202)."
        ),
        examples=[True],
    )


class FootprintRequestQuery(CamelSchema):
    dry_run: bool = Field(
        default=False,
        description=(
            "True previews the change and stores nothing: the answer is a 200 with what it would hide "
            "and reveal, no request is created, no second person is asked and no audit event is written. "
            "False, the default, sends the request for approval and answers 201."
        ),
    )
