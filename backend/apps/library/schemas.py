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

from apps.shared.schemas import CamelSchema
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
