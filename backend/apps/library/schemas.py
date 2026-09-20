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
    the reader's language (playbook 15). A term's kind is null: its dimension is its kind."""

    key: str
    kind: str | None
    label: str


class LocalizedText(LibraryResponse):
    """One text in one language (INV-05, D-12): which language it is in, whether it is the
    original and whether a machine translated it, so the screen can label it."""

    text: str
    language: str
    is_original: bool
    is_machine: bool


class PartialDate(LibraryResponse):
    """A legal date with its precision: day, month, quarter or year (playbook 4.3, INV-S10)."""

    date: datetime.date
    precision: str


class ObligationVersionRef(LibraryResponse):
    """A summary version by number and the date it takes effect; null means since the
    obligation began (INV-04)."""

    version_number: int
    effective_from: PartialDate | None


class ScopeDimension(LibraryResponse):
    """The record's terms in one dimension (FP-01). An empty list means no restriction in
    that dimension; `allSelected` means every active term of it is carried."""

    dimension: LibraryRef
    terms: list[LibraryRef]
    all_selected: bool


class OutsideReason(LibraryResponse):
    """A dimension in which none of the record's terms is in the footprint (FP-03)."""

    dimension: LibraryRef
    terms: list[LibraryRef]


class ObligationInstrumentRef(LibraryResponse):
    key: str
    short_name: str


class ObligationRow(LibraryResponse):
    """One row of `GET /obligations` (INV-03). `version` is the one in force on the read's
    date and `upcomingVersion` the next one after it. The register overlay arrives later:
    `openChangeCount` with the watch feed (chunk 5), `pendingApplicability` and
    `complianceStatus` with the register (chunk 8)."""

    id: UUID
    stable_key: str
    ref_label: str
    title: LocalizedText | None
    instrument: ObligationInstrumentRef
    binding_level: LibraryRef
    binding: bool
    duty_type: LibraryRef
    tags: list[LibraryRef]
    scope: list[ScopeDimension]
    version: ObligationVersionRef | None
    upcoming_version: ObligationVersionRef | None
    in_footprint: bool
    outside_reason: list[OutsideReason]
    last_verified_at: datetime.datetime | None
    open_change_count: int
    pending_applicability: bool | None
    compliance_status: LibraryRef | None

    # A row is validated again when the page takes it, so a row built any other way than
    # through this constructor still never reaches the wire unchecked.
    model_config = ConfigDict(revalidate_instances="always")


class ObligationPage(LibraryResponse):
    items: list[ObligationRow]
    total: int


class ObligationVersionRow(LibraryResponse):
    """One summary version on the card's version list (INV-04): when it took effect,
    `effectiveTo` derived as the day before the next version did, and when a library editor
    approved it. The approver is not named: the card names none."""

    version_number: int
    effective_from: PartialDate | None
    effective_to: PartialDate | None
    approved_at: datetime.datetime | None


class ObligationInstrumentSummary(LibraryResponse):
    """The instrument an obligation belongs to, as "Where it comes from" reads it (INV-01).
    Its provisions and lineage live on the instrument's own read."""

    key: str
    short_name: str
    name: LocalizedText | None
    official_ref: str
    implements_note: str


class ObligationProvisionRef(LibraryResponse):
    """A provision the obligation cites (INV-02, INV-03), by reference and path. The
    verbatim text is the provision tree's, never this read's."""

    id: UUID
    ref_label: str
    path: str


class RelatedObligation(LibraryResponse):
    """An obligation a reader should see beside this one (INV-03), with the relation as a
    vocabulary row."""

    id: UUID
    title: LocalizedText | None
    instrument: ObligationInstrumentRef
    binding: bool
    relation: LibraryRef


class ObligationProvenance(LibraryResponse):
    """Where the record came from and when it was last checked against its source (INV-06).
    `verifiedBy` is a platform person or null: a seeded record has never been re-verified."""

    created_origin: str
    created_model: str
    created_at: datetime.datetime
    verified_by: PersonRef | None
    last_verified_at: datetime.datetime | None
    source_url: str
    source_label: str


class ObligationDetail(LibraryResponse):
    """`GET /obligations/{obligationId}` (INV-03..INV-06): the duty as of a date, with its
    facets, every version, the provisions it cites, the obligations beside it and its
    provenance. The register overlay lands with chunk 8, the related changes with chunk 5."""

    id: UUID
    stable_key: str
    ref_label: str
    title: LocalizedText | None
    instrument: ObligationInstrumentSummary
    regime: LibraryRef | None
    binding_level: LibraryRef
    binding: bool
    duty_type: LibraryRef
    trigger_frequency: str
    retention: str
    sanction_exposure: str
    product_scope: str
    tags: list[LibraryRef]
    scope: list[ScopeDimension]
    in_footprint: bool
    outside_reason: list[OutsideReason]
    summary: LocalizedText | None
    translations: list[LocalizedText]
    version: ObligationVersionRow | None
    versions: list[ObligationVersionRow]
    provisions: list[ObligationProvisionRef]
    related: list[RelatedObligation]
    provenance: ObligationProvenance


class DiffSegment(LibraryResponse):
    """One sentence of a diff and what happened to it (AC-INV1)."""

    op: str
    text: str


class VersionDiff(LibraryResponse):
    """"Show what changed" between two versions (INV-04, AC-INV1, INV-05): the two version
    numbers and the dates they took effect, the language both versions have and whether a
    machine translated it, and the sentences. Serves obligations now and provisions next."""

    from_version: int
    to_version: int
    from_effective: PartialDate | None
    to_effective: PartialDate | None
    language: str
    is_machine: bool
    segments: list[DiffSegment]


class ObligationAsOfQuery(CamelSchema):
    """`asOf` on the obligation read: the version in force on that date, today in the
    tenant's time zone by default (AC-INV1)."""

    as_of: datetime.date | None = None


class ObligationDiffQuery(CamelSchema):
    """`from` and `to` are version numbers, defaulting to the latest version against the one
    before it. `lang` asks for a language; the diff falls back to the reader's language
    order when neither version has it (INV-05)."""

    from_version: int | None = Field(default=None, alias="from", ge=1)
    to_version: int | None = Field(default=None, alias="to", ge=1)
    lang: str | None = Field(default=None, max_length=MAX_LANGUAGE_LENGTH)


class ObligationQuery(CamelSchema):
    """The filters of `GET /obligations`. `instrument` and `dutyType` are keys; `term` is
    `dimension:key` and repeats, every term must be in the obligation's scope. `asOf`
    defaults to today in the tenant's time zone. `outsideFootprint=true` lifts the
    footprint filter and reports why each hidden row would be hidden."""

    instrument: str | None = None
    duty_type: str | None = None
    term: list[str] = Field(default_factory=list, max_length=settings.LIBRARY_TERM_FILTER_MAX)
    q: str | None = Field(default=None, max_length=MAX_QUERY_LENGTH)
    as_of: datetime.date | None = None
    outside_footprint: bool = False


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
