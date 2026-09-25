"""Request and response schemas of the reports app: camelCase through CamelSchema, app-prefixed
class names where a shape is specific to this app (playbook 4.1).

The export half (REP-02, CAS-07): what a person asks for, the filters every exporter shares,
and the job the worker reports on. `ExportFilters` is the one typed shape every builder reads
(CHUNK12_TASKS ruling 7), so a new exporter never changes the contract.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Literal

from django.conf import settings
from pydantic import ConfigDict, Field
from pydantic.json_schema import JsonDict

from apps.shared.schemas import CamelSchema, WriteBody

ExportKindValue = Literal[
    "case_file", "cases", "committee_pack", "inventory", "changes", "audit_log", "configuration", "tenant_export"
]
ExportFormatValue = Literal["pdf", "txt", "json", "xlsx", "csv"]
JobStatusValue = Literal["queued", "running", "succeeded", "failed"]

STATUS_KEYS_MAX = 20
STABLE_KEY_MAX = 128

_KIND = (
    "What the export contains. One of: `case_file` — one case's whole record, from what "
    "happened to sign-off, named by `subjectId`; `cases` — the bank's cases as a list; "
    "`committee_pack` — the dashboard's figures, the roadmap, the coverage and the open cases "
    "for a committee; `inventory` — the obligations inventory with the bank's applicability "
    "and status, the dated Statement of Applicability when filtered by a standard's edition "
    "and a legal entity; `changes` — the regulatory changes in the bank's scope; `audit_log` "
    "— the bank's audit trail; `configuration` — the bank's lists, roles and policies as a "
    "snapshot; `tenant_export` — everything the bank holds, taken when it leaves. A kind whose "
    "file is not built yet is refused with 501 `not_built`."
)
_FORMAT = (
    "The file format. One of: `pdf` — a document to read or print; `txt` — plain text; "
    "`json` — structured data for another system; `xlsx` — a spreadsheet; `csv` — "
    "comma-separated rows. Each kind offers only some of these, and a format its kind does "
    "not offer is refused with 422."
)
_STATUS = (
    "Where the job is. One of: `queued` — accepted and waiting for the worker; `running` — "
    "the worker is building the file; `succeeded` — the file is ready to download until "
    "`expiresAt`; `failed` — the file could not be built and `error` says why. Poll "
    "`GET /exports/{exportId}` until it is `succeeded` or `failed`; neither of those changes "
    "again."
)

EXPORT_JOB_EXAMPLE: JsonDict = {
    "id": "5b0f7c1e-2f5a-4d7e-9a51-3c1f0d9e8a42",
    "kind": "case_file",
    "subjectId": "0c9a4a57-8a55-4c43-9c8e-6f1a2b3c4d5e",
    "format": "json",
    "status": "succeeded",
    "createdAt": "2026-09-25T08:14:03Z",
    "completedAt": "2026-09-25T08:14:05Z",
    "expiresAt": "2026-10-02T08:14:05Z",
    "contentHash": "9f2c4b7a0d1e3f5a6b8c9d0e1f2a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c",
    "downloadedAt": None,
    "error": None,
}


class ExportFilters(WriteBody):
    """What narrows an export. Every field is optional and each exporter reads the ones that
    mean something for its kind and ignores the rest; no filter ever widens an export past
    the bank's own records and its regulatory scope."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"standardEdition": "iso-27001-2022", "entityId": "7d4e1f20-3a5b-4c6d-8e9f-0a1b2c3d4e5f"}
            ]
        },
    )

    instrument_key: str | None = Field(
        default=None,
        max_length=STABLE_KEY_MAX,
        description=(
            "Only records under this instrument, named by its stable key from the library, for "
            f"example `eu-2019-2088`. At most {STABLE_KEY_MAX} characters. A key that names no "
            "instrument gives an empty file, not an error."
        ),
    )
    entity_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Only this legal entity of the bank, by its UUID. The Statement of Applicability is "
            "one standard's edition for one entity, so it needs both this and `standardEdition`."
        ),
    )
    standard_edition: str | None = Field(
        default=None,
        max_length=STABLE_KEY_MAX,
        description=(
            "Only the units of this edition of a standard, named by the edition's stable key "
            f"from the library, for example `iso-27001-2022`. At most {STABLE_KEY_MAX} "
            "characters."
        ),
    )
    from_: datetime.date | None = Field(
        default=None,
        alias="from",
        description=(
            "The first day included, as a plain date (YYYY-MM-DD) in the bank's own time zone. "
            "Left out, the export starts at the earliest record."
        ),
    )
    to: datetime.date | None = Field(
        default=None,
        description=(
            "The last day included, as a plain date (YYYY-MM-DD) in the bank's own time zone. "
            "Left out, the export runs to today."
        ),
    )
    status_keys: list[str] | None = Field(
        default=None,
        max_length=STATUS_KEYS_MAX,
        description=(
            "Only records in these compliance statuses, by key. The values are rows of the "
            "bank's `compliance_status` vocabulary, whose kinds are `compliant`, `partly`, "
            "`gap` and `not_assessed`; an admin may extend the vocabulary, so read "
            "`GET /vocab/compliance_status` for the live set and never match on a label. At "
            f"most {STATUS_KEYS_MAX} keys."
        ),
    )


class ExportInput(WriteBody):
    """What a person asks to export."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [{"kind": "case_file", "subjectId": "0c9a4a57-8a55-4c43-9c8e-6f1a2b3c4d5e", "format": "json"}]
        },
    )

    kind: ExportKindValue = Field(description=_KIND)
    subject_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "The UUID of the one record the export is about, for a kind that is about one record: "
            "the case for `case_file`. Left out for every other kind."
        ),
    )
    format: ExportFormatValue = Field(description=_FORMAT)
    filters: ExportFilters | None = Field(
        default=None,
        description="What narrows the export. Left out, the export holds everything of its kind in the bank's scope.",
    )


class ExportJobOut(CamelSchema):
    """One export job and where it is. The file is not in here: it is fetched from
    `GET /exports/{exportId}/download` once the status is `succeeded`."""

    model_config = ConfigDict(json_schema_extra={"examples": [EXPORT_JOB_EXAMPLE]})

    id: uuid.UUID = Field(description="The job's identifier, for polling its status and downloading its file.")
    kind: ExportKindValue = Field(description=_KIND)
    subject_id: uuid.UUID | None = Field(
        description="The UUID of the one record the export is about, for a `case_file`; null for every other kind."
    )
    format: ExportFormatValue = Field(description=_FORMAT)
    status: JobStatusValue = Field(description=_STATUS)
    created_at: datetime.datetime = Field(description="When the person asked for the export, as a UTC timestamp.")
    completed_at: datetime.datetime | None = Field(
        description="When the worker finished, as a UTC timestamp, whether the file was built or not; null while queued or running."
    )
    expires_at: datetime.datetime | None = Field(
        description=(
            "When the file stops being available, as a UTC timestamp: "
            f"{settings.EXPORT_RETENTION_DAYS} days after it was built. After that a download "
            "answers 409 `export_expired` and a new export is needed. Null until the job succeeds."
        )
    )
    content_hash: str | None = Field(
        description=(
            "The SHA-256 of the file, as 64 lowercase hexadecimal characters, so whoever "
            "receives it can check it is the file the server built. Null until the job succeeds."
        )
    )
    downloaded_at: datetime.datetime | None = Field(
        description=(
            "When the file was first downloaded, as a UTC timestamp. A later download does not move it. "
            "Null until someone downloads it."
        )
    )
    error: str | None = Field(
        description=(
            "Why the file could not be built, written for the person who asked, when the status "
            "is `failed`; null otherwise."
        )
    )


class ExportJobPage(CamelSchema):
    """`{items, total}` with `limit` and `offset` (playbook 10)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [EXPORT_JOB_EXAMPLE], "total": 1}]})

    items: list[ExportJobOut] = Field(
        description=(
            "The bank's export jobs on this page, newest first. Only the caller's own bank's "
            "jobs are ever listed. An empty list is a 200 and means nobody has exported yet."
        )
    )
    total: int = Field(description="How many export jobs the bank has in total, not how many are on this page.")
