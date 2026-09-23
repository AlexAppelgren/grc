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
from typing import Any
from uuid import UUID

from pydantic import ConfigDict, Field

from apps.shared.schemas import CamelSchema, VocabularyExtra, WriteBody

__all__ = ["CamelSchema"]


# ---------------------------------------------------------------------------------------
# References: what every picker, pill and filter reads (playbook 15: key and kind, never a
# phrase the client must string-match).
# ---------------------------------------------------------------------------------------
class TermRef(CamelSchema):
    key: str
    kind: str | None = None
    label: str


class PersonRef(CamelSchema):
    """A person on a record: id and name, the only personal data a screen or a log may carry
    about them (playbook 4.7)."""

    id: UUID
    name: str


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

    key: str
    kind: str | None = None
    label: str
    parent_key: str | None = None
    default_language: TermRef | None = None


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
            "through the API (`instrument_level` and `jurisdiction`): a create, suggestion, change, retire, "
            "restore or merge on it answers 422 `validation_error`. True for every other list, a bank's own "
            "lists included, which change directly rather than by proposal."
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
            "not counted yet answers: today only a bank's tags (`tenant_tag`) and the taxonomy dimensions "
            "(`term_dimension`) count theirs, so 0 on any other list means not counted, not unused."
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


class VocabularyRowDetail(VocabularyRow):
    """`GET /vocab/{list}/{key}`: the value plus which label is the original and which are
    machine translations (I18N-01, D-12)."""

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
    id: UUID
    key: str
    kind: str | None = None
    label: str
    labels: dict[str, str] = Field(default_factory=dict)
    dimension: TaxonomyDimensionRef
    parent_key: str | None = None
    usage_note: str = ""
    sort_order: int = 0
    active: bool = True
    is_system: bool = False
    version: int = 1
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


class TaxonomyTermPage(CamelSchema):
    items: list[TaxonomyTermRow]
    total: int


class TaxonomyTermCreateBody(WriteBody):
    dimension: str
    key: str | None = None
    labels: dict[str, str]
    usage_note: str = ""
    parent: str | None = None


class TaxonomyDimensionPage(CamelSchema):
    items: list[VocabularyRow]
    total: int


# ---------------------------------------------------------------------------------------
# Footprint (FP-01, FP-02, FP-03)
# ---------------------------------------------------------------------------------------
class FootprintPreviewCount(CamelSchema):
    """What a change would hide and reveal for one record kind. `available` is false while
    the table does not exist yet (chunk 2 has no obligations or cases): zeros with
    `available:false` say "not counted", never "none" (playbook 4.4)."""

    hidden: int = 0
    revealed: int = 0
    available: bool = False


class FootprintPreview(CamelSchema):
    """The named schema behind `footprint_change_request.preview` (JSONField)."""

    obligations: FootprintPreviewCount = Field(default_factory=FootprintPreviewCount)
    cases: FootprintPreviewCount = Field(default_factory=FootprintPreviewCount)


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
    dimension: str


class FootprintRequestRow(CamelSchema):
    id: UUID
    status: str
    requested_by: PersonRef | None = None
    requested_at: datetime
    adds: list[FootprintTermRef] = Field(default_factory=list)
    removes: list[FootprintTermRef] = Field(default_factory=list)
    preview: FootprintPreview
    decided_by: PersonRef | None = None
    decided_at: datetime | None = None
    decision_note: str = ""
    version: int = 1


class MarketRow(CamelSchema):
    """One active country's market level (FP-04), computed fresh on every read and never
    stored: operating when the jurisdiction's mirrored term sits in the tenant's footprint,
    set only through a footprint change request (FP-02); watching when a `watched_market`
    row names it, a direct write that hides nothing. Both false reads as not followed."""

    jurisdiction: TermRef = Field(
        description=(
            "The country: its key, kind (always `country`) and label in the caller's language. A row of "
            "the jurisdiction vocabulary; an admin may add more without a deploy, and `GET /reference/jurisdictions` "
            "lists the live set."
        )
    )
    operating: bool = Field(
        description=(
            "True when this country's mirrored jurisdiction term is in the tenant's footprint. Changes "
            "only through a footprint change request with its preview, second person and step-up."
        )
    )
    watching: bool = Field(
        description=(
            "True when the tenant has a `watched_market` row naming this country. Set directly with "
            "`POST /tenant/footprint/watching`, with no preview, no second person and no step-up, "
            "because watching hides nothing."
        )
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
    dimensions: list[FootprintDimension]
    pending_request: FootprintRequestRow | None = None
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
    dimension: str
    key: str


class FootprintRequestBody(CamelSchema):
    adds: list[FootprintTermSelector] = Field(default_factory=list)
    removes: list[FootprintTermSelector] = Field(default_factory=list)


class FootprintDecisionBody(CamelSchema):
    note: str = ""


class FootprintDryRun(CamelSchema):
    """`POST /tenant/footprint/requests?dryRun=true` (playbook 15: dry run, preview,
    commit): what the change would hide and reveal, with nothing persisted, no audit event
    and no approval started. The same `adds`, `removes` and `preview` the created request
    would carry, so the screen renders the preview and the request from one shape."""

    adds: list[FootprintTermRef] = Field(default_factory=list)
    removes: list[FootprintTermRef] = Field(default_factory=list)
    preview: FootprintPreview
    dry_run: bool = True


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
    dimension: str | None = None
    include_retired: bool = False


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
