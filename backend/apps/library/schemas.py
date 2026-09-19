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

# The longest `q` a list accepts: a phrase to look for, never a document.
MAX_QUERY_LENGTH = 200


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
