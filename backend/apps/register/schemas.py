"""Request and response schemas of the register app: camelCase through CamelSchema, app-prefixed
class names where a shape is specific to this app (playbook 4.1).

Everything here is one bank's own zone: its judgement laid over the shared library. Whether
an obligation applies, how the bank complies, its gaps, its reading of the rule, its links to
its own policies and controls, its Statement of Applicability units and its dated duties all
sit in tenant tables under enabled and forced row-level security. None of it reaches another
bank, a log, Sentry, analytics or a model endpoint, and nothing here writes a library row.

"Applies" and "we comply" are separate facts (CLAUDE.md section 5): applicability is a kind
set by one person holding `applicability.approve` after a confirmation dialog (D-75), and a
compliance status is a row of the bank's own `compliance_status` list. Neither is derived from
the other, and a status survives a "does not apply".

Vocabulary values are `{key, kind, label}` on reads and a bare key on writes: store and compare
the key, show the label. Lists page with `limit` (default 20, at most 100) and `offset`.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Literal

from ninja import Field
from pydantic import ConfigDict, model_validator

from apps.shared.schemas import CamelSchema, WriteBody

__all__ = ["CamelSchema"]

# The longest texts a bank may store on a register row. Status notes, rationales, gap
# descriptions and remediation plans are paragraphs; process, system and references are names.
NOTE_MAX = 4000
NAME_MAX = 500
REASON_MAX = 2000
TITLE_MAX = 300
INTERPRETATION_MAX = 8000
URL_MAX = 2000
EXTERNAL_REF_MAX = 200
KEY_MAX = 64
# A unit's reference and title, fixed once the unit has history (D-41).
UNIT_REFERENCE_MAX = 64
UNIT_TITLE_MAX = 300
# A pasted line is bounded generously so an over-long one is reported on its row by the dry
# run rather than refusing the whole paste; the unit limits above decide what is created.
PASTE_FIELD_MAX = 1000

Applicability = Literal["applies", "not_applicable", "under_assessment"]
AssessmentMethod = Literal["self_assessment", "second_line_review", "internal_audit", "external_audit", "regulator"]
DutyStatus = Literal["upcoming", "in_progress", "done", "missed", "not_applicable"]
PasteOutcome = Literal["will_create", "created", "refused"]
PasteProblem = Literal["duplicate_reference", "reference_exists", "reference_too_long", "title_too_long", "empty_line"]

_APPLICABILITY = (
    "Whether the obligation applies to the bank here: `applies` when it binds this bank, "
    "legal entity or unit; `not_applicable` when a compliance person decided it does not, "
    "with the reason beside it; `under_assessment` until anyone has decided. A fixed kind, "
    "not a list the bank edits. It says nothing about whether the bank complies, which is "
    "the separate compliance status."
)
_APPLICABILITY_WRITE = (
    "The answer to store: `applies`, `not_applicable`, or `under_assessment` to take a "
    "decision back to undecided. It is stored at once, after the person confirmed it in a "
    "dialog, with no second approver and no step-up (D-75), and it leaves the compliance "
    "status and the gaps untouched."
)
_COMPLIANCE_KEY = (
    "The key of a row in the bank's own `compliance_status` vocabulary, at most 64 "
    "characters. Seeded as `compliant`, `partly_compliant`, `gap` and `not_assessed`; the "
    "bank's admin may add or relabel rows, each under one fixed category, so read "
    "`GET /vocab/compliance_status` for the live set. A status other than the "
    "`not_assessed` row needs applicability `applies` first."
)
_RISK_KEY = (
    "The key of a row in the bank's own `risk_rating` vocabulary, at most 64 characters. "
    "Seeded as `low`, `medium` and `high`, each with a fixed ordinal; the bank's admin may "
    "add or relabel rows, so read `GET /vocab/risk_rating` for the live set."
)
_TEAM_KEY = (
    "The key of a row in the bank's own `team` vocabulary, at most 64 characters, such as "
    "`compliance`; the bank's admin adds, renames and retires teams, so read `GET /vocab/team` "
    "for the live set. A key that is not an active team of this bank is refused; null or "
    "absent leaves the field as it is on a patch."
)
_TEAM_REF = (
    "The team that owns the obligation here, as a row of the bank's own `team` vocabulary, "
    "which its admin may extend; read `GET /vocab/team` for the live set. The key is stable "
    "and the label is for showing. Null when no team owns it."
)
_PERSON_ID = (
    "A member of the bank, by their user UUID. Someone who is not an active member of "
    "this bank is refused; null or absent leaves the field as it is on a patch."
)
_OBLIGATION_ID = (
    "The library obligation this register row is about, as a UUID. The obligation is a "
    "shared library fact; the register row is this bank's alone."
)
_ORG_UNIT_ID = (
    "The bank's own legal entity this row is about, as a UUID from its organisation. Null "
    "when the row is about the obligation as a whole rather than one entity."
)
_VERSION = (
    "The row's version, 0 for a row nobody has written yet and one higher after every "
    "write. Send it back as `If-Match` on the next write; a row changed in between is "
    "refused rather than overwritten."
)
_DECIDED_AT = (
    "The UTC timestamp at which the applicability answer was last set, null while it is "
    "`under_assessment` and nobody has answered. Set by the server."
)
_DECIDED_BY = (
    "The person who last set the applicability answer, named in the audit event with the "
    "value before and after. Null while nobody has answered."
)
_APPLICABILITY_REASON = (
    "Why the answer is what it is, in the bank's own words, such as `Certified` or `No "
    "client money held`. Tenant content that never leaves the bank. Null while nobody has "
    "answered."
)

_PERSON_EXAMPLE: dict[str, Any] = {"id": "8f3b6a0e-2c71-4d95-b8e4-1a7c9d2f5e30", "name": "Sara Lind"}
_STATUS_EXAMPLE: dict[str, Any] = {"key": "partly_compliant", "kind": "partly", "label": "Partly compliant"}
_RISK_EXAMPLE: dict[str, Any] = {"key": "medium", "kind": None, "label": "Medium"}
_TEAM_EXAMPLE: dict[str, Any] = {"key": "compliance", "kind": None, "label": "Compliance"}
_GAP_STATUS_EXAMPLE: dict[str, Any] = {"key": "open", "kind": "open", "label": "Open"}
_ENTITY_EXAMPLE: dict[str, Any] = {
    "orgUnitId": "55555555-5555-4555-8555-555555555555",
    "orgUnitName": "Example Bank AB",
    "applicability": "applies",
    "applicabilityReason": "Holds client assets under the securities licence",
    "applicabilityDecidedAt": "2026-09-14T08:30:00Z",
    "applicabilityDecidedBy": _PERSON_EXAMPLE,
    "complianceStatus": _STATUS_EXAMPLE,
    "statusNote": "Reconciliation runs daily; the evidence log is still manual.",
    "riskRating": _RISK_EXAMPLE,
    "owner": _PERSON_EXAMPLE,
    "ownerTeam": None,
    "process": "Client asset reconciliation",
    "system": "Custody ledger",
    "evidenceLocation": "Compliance share / Client assets / 2026",
    "nextReviewDate": "2027-03-31",
    "version": 4,
}


# ---------------------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------------------
class RegisterVocabRef(CamelSchema):
    """A value of one of the bank's own lists as the register shows it: key, kind and label
    together, so a screen shows a name while an integration stores what never moves."""

    key: str = Field(
        description=(
            "The stable key of the row in the bank's own vocabulary, such as `partly_compliant` "
            "in `compliance_status`, `high` in `risk_rating`, `open` in `gap_status` or "
            "`policy` in `link_kind`. The bank's admin may add, relabel or retire rows, so an "
            "unfamiliar key is new data and not an error; read `GET /vocab/{listName}` for the "
            "live set. Store and compare the key, never the label."
        )
    )
    kind: str | None = Field(
        description=(
            "The fixed category the row belongs to, which decides the pill's tone and every rule "
            "the server applies: for `compliance_status` one of `compliant`, `partly`, `gap` or "
            "`not_assessed`; for `gap_status` one of `open`, `remediating`, `risk_accepted` or "
            "`closed`. Null for a list whose rows carry no category, such as `risk_rating` or "
            "`link_kind`."
        )
    )
    label: str = Field(
        description=(
            "The row's name in the reader's language, for showing and for nothing else. The bank "
            "may reword and translate it at any time, so never store it or match on it."
        )
    )


class RegisterPersonRef(CamelSchema):
    """A member of the bank named on a register row."""

    id: uuid.UUID = Field(description="The person's user UUID in this bank; stable for as long as they are a member.")
    name: str = Field(description="The person's display name, for showing beside the row. It may change; keep the id.")


# ---------------------------------------------------------------------------------------
# Compliance status on the register entry and per legal entity (REG-02)
# ---------------------------------------------------------------------------------------
class RegisterEntityStatus(CamelSchema):
    """One legal entity's row under an obligation that spans several: its own applicability
    and reason, and its own compliance status and details (REG-01, REG-02, D-42)."""

    model_config = ConfigDict(json_schema_extra={"examples": [_ENTITY_EXAMPLE]})

    org_unit_id: uuid.UUID = Field(description="The bank's legal entity this row is about, as a UUID from its organisation.")
    org_unit_name: str = Field(description="The legal entity's name as the bank's organisation holds it, for showing.")
    applicability: Applicability = Field(description=_APPLICABILITY)
    applicability_reason: str | None = Field(description=_APPLICABILITY_REASON)
    applicability_decided_at: datetime.datetime | None = Field(description=_DECIDED_AT)
    applicability_decided_by: RegisterPersonRef | None = Field(description=_DECIDED_BY)
    compliance_status: RegisterVocabRef = Field(
        description=(
            "How this entity complies, as a row of the bank's own `compliance_status` "
            "vocabulary; its admin may add rows under the fixed categories, so read "
            "`GET /vocab/compliance_status` for the live set. Kept even while the entity's "
            "applicability is `not_applicable`, so nothing is lost when it applies again."
        )
    )
    status_note: str | None = Field(description="The bank's note on the status, in its own words; null when none was written.")
    risk_rating: RegisterVocabRef | None = Field(
        description=(
            "The bank's risk rating for this entity, as a row of its own `risk_rating` "
            "vocabulary, which its admin may extend; read `GET /vocab/risk_rating` for the live "
            "set. Null until rated."
        )
    )
    owner: RegisterPersonRef | None = Field(
        description="The member who owns the obligation for this entity; null when nobody does, or when a team owns it instead."
    )
    owner_team: RegisterVocabRef | None = Field(description=f"{_TEAM_REF} An entity's row is owned by a person or a team, never both.")
    process: str | None = Field(description="The bank's own business process the obligation is met in, by its name; null when not recorded.")
    system: str | None = Field(description="The bank's own system the obligation is met in, by its name; null when not recorded.")
    evidence_location: str | None = Field(
        description="Where the bank keeps the evidence for this entity, such as a folder or a document system path; null when not recorded."
    )
    next_review_date: datetime.date | None = Field(
        description="The plain date the bank next reviews this entity's status, shown on the roadmap as our own deadline; null when not set."
    )
    version: int = Field(description=_VERSION)


class RegisterEntry(CamelSchema):
    """The bank's register entry for one obligation: its applicability and its compliance
    status, kept as separate facts, and a row per legal entity where it spans several."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "obligationId": "44444444-4444-4444-8444-444444444444",
                    "applicability": "applies",
                    "applicabilityReason": "Holds client assets under the securities licence",
                    "applicabilityDecidedAt": "2026-09-14T08:30:00Z",
                    "applicabilityDecidedBy": _PERSON_EXAMPLE,
                    "complianceStatus": _STATUS_EXAMPLE,
                    "statusNote": "Reconciliation runs daily; the evidence log is still manual.",
                    "riskRating": _RISK_EXAMPLE,
                    "firstLineOwner": _PERSON_EXAMPLE,
                    "complianceContact": {"id": "2b9e4c71-5a3d-4f08-9c6e-7d1a0b3f5e82", "name": "Johan Berg"},
                    "ownerTeam": _TEAM_EXAMPLE,
                    "process": "Client asset reconciliation",
                    "system": "Custody ledger",
                    "evidenceLocation": "Compliance share / Client assets / 2026",
                    "nextReviewDate": "2027-03-31",
                    "entities": [_ENTITY_EXAMPLE],
                    "version": 7,
                    "updatedAt": "2026-09-18T13:05:00Z",
                }
            ]
        }
    )

    obligation_id: uuid.UUID = Field(description=_OBLIGATION_ID)
    applicability: Applicability = Field(description=_APPLICABILITY)
    applicability_reason: str | None = Field(description=_APPLICABILITY_REASON)
    applicability_decided_at: datetime.datetime | None = Field(description=_DECIDED_AT)
    applicability_decided_by: RegisterPersonRef | None = Field(description=_DECIDED_BY)
    compliance_status: RegisterVocabRef = Field(
        description=(
            "How the bank complies, as a row of its own `compliance_status` vocabulary, which "
            "its admin may extend under fixed categories; read `GET /vocab/compliance_status` "
            "for the live set. Where legal entities the obligation applies to have rows, it is the "
            "worst of their statuses by category, computed by the server: `gap`, then `partly`, "
            "then `not_assessed`, then `compliant`; the label and the bank's ordinal never decide. "
            "The `gap` category means a gap exists, which applicability never hides."
        )
    )
    status_note: str | None = Field(description="The bank's note on the status, in its own words; null when none was written.")
    risk_rating: RegisterVocabRef | None = Field(
        description=(
            "The bank's risk rating for the obligation, as a row of its own `risk_rating` "
            "vocabulary, which its admin may extend; read `GET /vocab/risk_rating` for the live "
            "set. Null until rated."
        )
    )
    first_line_owner: RegisterPersonRef | None = Field(description="The first-line member who owns meeting the obligation; null when nobody does yet.")
    compliance_contact: RegisterPersonRef | None = Field(description="The compliance member who follows the obligation; null when nobody does yet.")
    owner_team: RegisterVocabRef | None = Field(description=_TEAM_REF)
    process: str | None = Field(description="The bank's own business process the obligation is met in, by its name; null when not recorded.")
    system: str | None = Field(description="The bank's own system the obligation is met in, by its name; null when not recorded.")
    evidence_location: str | None = Field(
        description="Where the bank keeps the evidence, such as a folder or a document system path; null when not recorded."
    )
    next_review_date: datetime.date | None = Field(
        description="The plain date the bank next reviews the obligation, shown on the roadmap as our own deadline; null when not set."
    )
    entities: list[RegisterEntityStatus] = Field(
        description=(
            "One row per legal entity the bank has answered for, in the order of its "
            "organisation. Empty for an obligation the bank treats as a whole. Reading never "
            "creates a row; a row appears with the first write that needs it."
        )
    )
    version: int = Field(description=_VERSION)
    updated_at: datetime.datetime | None = Field(
        description="The UTC timestamp of the last write to the entry, null for an entry nobody has written yet."
    )


class RegisterStatusFields(WriteBody):
    """The fields a status write may change; only the fields sent change."""

    compliance_status: str | None = Field(default=None, max_length=KEY_MAX, description=_COMPLIANCE_KEY)
    status_note: str | None = Field(
        default=None,
        max_length=NOTE_MAX,
        description=f"The bank's note on the status, at most {NOTE_MAX} characters. Tenant content that never leaves the bank.",
    )
    risk_rating: str | None = Field(default=None, max_length=KEY_MAX, description=_RISK_KEY)
    owner_team: str | None = Field(default=None, max_length=KEY_MAX, description=_TEAM_KEY)
    process: str | None = Field(
        default=None, max_length=NAME_MAX, description=f"The business process the obligation is met in, by name, at most {NAME_MAX} characters."
    )
    system: str | None = Field(
        default=None, max_length=NAME_MAX, description=f"The system the obligation is met in, by name, at most {NAME_MAX} characters."
    )
    evidence_location: str | None = Field(
        default=None, max_length=NAME_MAX, description=f"Where the evidence is kept, at most {NAME_MAX} characters."
    )
    next_review_date: datetime.date | None = Field(
        default=None, description="The plain date of the next review, shown on the roadmap as our own deadline."
    )
    rationale: str | None = Field(
        default=None,
        max_length=NOTE_MAX,
        description=(
            f"Why the status is what it is, at most {NOTE_MAX} characters. Stored on the "
            "assessment row a status change writes, so the history says who assessed what and why."
        ),
    )


class RegisterPatch(RegisterStatusFields):
    """`PATCH /obligations/{obligationId}/register`: the bank's status and details on the
    obligation as a whole. Applicability is absent on purpose: it has its own route (D-75)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "complianceStatus": "partly_compliant",
                    "statusNote": "Reconciliation runs daily; the evidence log is still manual.",
                    "riskRating": "medium",
                    "rationale": "Second-line review of September found the manual log.",
                }
            ]
        }
    )

    first_line_owner_id: uuid.UUID | None = Field(default=None, description=f"The first-line owner. {_PERSON_ID}")
    compliance_contact_id: uuid.UUID | None = Field(default=None, description=f"The compliance contact. {_PERSON_ID}")


class RegisterEntityPatch(RegisterStatusFields):
    """`PATCH /obligations/{obligationId}/register/entities/{orgUnitId}`: one legal entity's
    own status and details (REG-02). Applicability is absent on purpose: it has its own route."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"complianceStatus": "compliant", "ownerId": "8f3b6a0e-2c71-4d95-b8e4-1a7c9d2f5e30", "nextReviewDate": "2027-03-31"}]
        }
    )

    owner_id: uuid.UUID | None = Field(
        default=None,
        description=(
            f"The entity's owner of the obligation. {_PERSON_ID} A person and a team never own "
            "the same row: setting one clears the other, and sending both is refused."
        ),
    )

    @model_validator(mode="after")
    def _one_owner_kind(self) -> RegisterEntityPatch:
        if self.owner_id is not None and self.owner_team is not None:
            raise ValueError("Send an owner or an owner team, not both.")
        return self


# ---------------------------------------------------------------------------------------
# Applicability (REG-01, D-75)
# ---------------------------------------------------------------------------------------
class RegisterApplicabilityTarget(WriteBody):
    """What an applicability answer is about: the obligation as a whole, one legal entity, or
    one unit of a standard. At most one of `orgUnitId` and `unitId`."""

    org_unit_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "The legal entity to answer for, as a UUID from the bank's organisation. Absent, "
            "together with `unitId`, answers for the obligation as a whole. Its scope row is "
            "created in the same transaction when it does not exist yet (D-42)."
        ),
    )
    unit_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "The Statement of Applicability unit to answer for, as a UUID from "
            "`GET /obligations/{obligationId}/units`. Sending it with `orgUnitId` is refused, "
            "because a unit already belongs to one entity."
        ),
    )
    applicability: Applicability = Field(description=_APPLICABILITY_WRITE)
    reason: str = Field(
        min_length=1,
        max_length=REASON_MAX,
        description=(
            f"Why, in the bank's own words, 1 to {REASON_MAX} characters, such as `Certified`. "
            "Stored beside the answer and in the audit event. Tenant content that never leaves the bank."
        ),
    )

    @model_validator(mode="after")
    def _one_target(self) -> RegisterApplicabilityTarget:
        if self.org_unit_id is not None and self.unit_id is not None:
            raise ValueError("Name a legal entity or a unit, not both.")
        return self


class RegisterApplicabilityBody(RegisterApplicabilityTarget):
    """`PUT /obligations/{obligationId}/applicability`: one confirmed answer."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"orgUnitId": "55555555-5555-4555-8555-555555555555", "applicability": "applies", "reason": "Certified"}
            ]
        }
    )


class RegisterApplicabilityRow(RegisterApplicabilityTarget):
    """One row of a confirmed batch: the obligation it is about, then the same target and answer."""

    obligation_id: uuid.UUID = Field(description=_OBLIGATION_ID)


class RegisterApplicabilityManyBody(WriteBody):
    """`POST /applicability`: many confirmed answers in one call, such as a pasted Statement
    of Applicability (AC-REG1)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "rows": [
                        {
                            "obligationId": "44444444-4444-4444-8444-444444444444",
                            "unitId": "66666666-6666-4666-8666-666666666666",
                            "applicability": "not_applicable",
                            "reason": "No outsourced cloud services",
                        }
                    ]
                }
            ]
        }
    )

    rows: list[RegisterApplicabilityRow] = Field(
        min_length=1,
        description=(
            "The answers, at least 1, each stored with its own audit event naming the person, "
            "the value before and after and the reason. A call holds at most the configured "
            "`REGISTER_BULK_MAX` rows, 100 by default; a longer call, or one with any row "
            "refused, stores nothing."
        ),
    )


class RegisterApplicability(CamelSchema):
    """An applicability answer as stored."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "obligationId": "44444444-4444-4444-8444-444444444444",
                    "orgUnitId": "55555555-5555-4555-8555-555555555555",
                    "unitId": None,
                    "applicability": "applies",
                    "reason": "Certified",
                    "decidedAt": "2026-09-24T09:12:00Z",
                    "decidedBy": _PERSON_EXAMPLE,
                    "version": 2,
                }
            ]
        }
    )

    obligation_id: uuid.UUID = Field(description=_OBLIGATION_ID)
    org_unit_id: uuid.UUID | None = Field(description=_ORG_UNIT_ID)
    unit_id: uuid.UUID | None = Field(description="The Statement of Applicability unit answered for, as a UUID; null for an obligation or entity answer.")
    applicability: Applicability = Field(description=_APPLICABILITY)
    reason: str = Field(description="Why, in the bank's own words, as the person gave it. Tenant content that never leaves the bank.")
    decided_at: datetime.datetime = Field(description="The UTC timestamp at which the answer was stored, set by the server.")
    decided_by: RegisterPersonRef = Field(description="The person who set the answer after confirming it, as the audit event names them.")
    version: int = Field(description=_VERSION)


class RegisterApplicabilityMany(CamelSchema):
    """What a confirmed batch stored, in the order sent."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "obligationId": "44444444-4444-4444-8444-444444444444",
                            "orgUnitId": "55555555-5555-4555-8555-555555555555",
                            "unitId": "66666666-6666-4666-8666-666666666666",
                            "applicability": "not_applicable",
                            "reason": "No outsourced cloud services",
                            "decidedAt": "2026-09-24T09:12:00Z",
                            "decidedBy": _PERSON_EXAMPLE,
                            "version": 1,
                        }
                    ]
                }
            ]
        }
    )

    items: list[RegisterApplicability] = Field(description="Each stored answer, one per row sent and in the same order.")


# ---------------------------------------------------------------------------------------
# Gaps and risk acceptance (REG-03)
# ---------------------------------------------------------------------------------------
_GAP_SOURCE = (
    "The key of a row in the bank's own `gap_source` vocabulary, at most 64 characters: "
    "where the gap was found. Seeded as `assessment` in the bank's own status assessment, "
    "`change_case` while working a regulatory change, `audit` by internal or external audit, "
    "`incident` after something went wrong and `regulator` raised by a supervisor; the bank's "
    "admin may add or relabel rows, so read `GET /vocab/gap_source` for the live set."
)
_TEAM_KEY = (
    "The key of a row in the bank's own `team` vocabulary, at most 64 characters, for a gap "
    "a team owns rather than one person. A gap has one owner kind: sending a team clears the "
    "person and sending a person clears the team, and sending both is refused. Read "
    "`GET /vocab/team` for the live set; null or absent leaves the owner as it is on a patch."
)
_GAP_STATUS_KEY = (
    "The key of a row in the bank's own `gap_status` vocabulary, at most 64 characters, "
    "under one of the fixed categories `open`, `remediating`, `risk_accepted` and `closed`. "
    "The bank's admin may add or relabel rows, so read `GET /vocab/gap_status` for the live "
    "set. A risk is accepted only through the acceptance routes, never by setting the status."
)

_RISK_ACCEPTANCE_EXAMPLE: dict[str, Any] = {
    "reason": {"key": "compensating_control", "kind": None, "label": "Compensating control"},
    "note": "Automation is planned with the ledger replacement in 2027.",
    "requestedBy": _PERSON_EXAMPLE,
    "requestedAt": "2026-09-20T10:00:00Z",
    "approvedBy": None,
    "approvedAt": None,
}
_GAP_EXAMPLE: dict[str, Any] = {
    "id": "66666666-6666-4666-8666-666666666666",
    "obligationId": "44444444-4444-4444-8444-444444444444",
    "orgUnitId": "55555555-5555-4555-8555-555555555555",
    "unitId": None,
    "title": "Evidence of reconciliation is manual",
    "description": "The daily reconciliation is run, but its evidence is a hand-kept log.",
    "severity": {"key": "high", "kind": None, "label": "High"},
    "source": {"key": "assessment", "kind": None, "label": "Assessment"},
    "status": _GAP_STATUS_EXAMPLE,
    "owner": _PERSON_EXAMPLE,
    "ownerTeam": None,
    "targetDate": "2026-12-31",
    "remediation": "Automate the daily reconciliation report.",
    "identifiedAt": "2026-09-18T13:05:00Z",
    "identifiedBy": {"id": "2b9e4c71-5a3d-4f08-9c6e-7d1a0b3f5e82", "name": "Johan Berg"},
    "riskAcceptance": _RISK_ACCEPTANCE_EXAMPLE,
    "version": 3,
}


class RegisterRiskAcceptance(CamelSchema):
    """A request to accept a gap's risk, and its approval by a second person with a step-up."""

    reason: RegisterVocabRef = Field(
        description=(
            "Why the risk is accepted, as a row of the bank's own risk-acceptance reason "
            "vocabulary, which its admin may extend; read the vocabulary endpoint for the live set."
        )
    )
    note: str | None = Field(description="The requester's note in their own words; null when none was written.")
    requested_by: RegisterPersonRef = Field(description="The person who asked for the risk to be accepted.")
    requested_at: datetime.datetime = Field(description="The UTC timestamp of the request, set by the server.")
    approved_by: RegisterPersonRef | None = Field(
        description=(
            "The second person who approved it with a passkey step-up, never the person who "
            "asked for it. Null while the acceptance is waiting for approval."
        )
    )
    approved_at: datetime.datetime | None = Field(description="The UTC timestamp of the approval, null while waiting for approval.")


class RegisterGap(CamelSchema):
    """A gap: how the bank falls short of an obligation, with an owner, a severity, a target
    date and a plan (REG-03). A fact about how the bank complies, never about whether the rule
    applies."""

    model_config = ConfigDict(json_schema_extra={"examples": [_GAP_EXAMPLE]})

    id: uuid.UUID = Field(description="The gap's UUID in this bank.")
    obligation_id: uuid.UUID = Field(description=_OBLIGATION_ID)
    org_unit_id: uuid.UUID | None = Field(description="The legal entity the gap is in, as a UUID; null for a gap in the obligation as a whole.")
    unit_id: uuid.UUID | None = Field(description="The Statement of Applicability unit the gap is in, as a UUID; null when it is not about one unit.")
    title: str = Field(description="What falls short, in a line of the bank's own words.")
    description: str | None = Field(description="The longer account of the gap in the bank's own words; null when none was written.")
    severity: RegisterVocabRef = Field(
        description=(
            "How serious the gap is, as a row of the bank's own `risk_rating` vocabulary, which "
            "its admin may extend; read `GET /vocab/risk_rating` for the live set."
        )
    )
    source: RegisterVocabRef = Field(
        description=(
            "Where the gap was found, as a row of the bank's own `gap_source` vocabulary, which "
            "its admin may extend; read `GET /vocab/gap_source` for the live set."
        )
    )
    status: RegisterVocabRef = Field(
        description=(
            "Where the gap stands, as a row of the bank's own `gap_status` vocabulary, which its "
            "admin may extend under the fixed categories; the kind is one of `open`, "
            "`remediating`, `risk_accepted` or `closed` and decides the pill's tone."
        )
    )
    owner: RegisterPersonRef | None = Field(
        description="The member who owns closing the gap; null when a team owns it or nobody does yet."
    )
    owner_team: RegisterVocabRef | None = Field(
        description=(
            "The team that owns closing the gap, as a row of the bank's own `team` vocabulary, "
            "which its admin may extend; read `GET /vocab/team` for the live set. Null when a "
            "person owns it or nobody does yet; never set together with `owner`."
        )
    )
    target_date: datetime.date | None = Field(
        description="The plain date the bank means to close the gap by, shown on the roadmap as our own deadline; null when not set."
    )
    remediation: str | None = Field(description="The bank's plan for closing the gap, in its own words; null when none was written.")
    identified_at: datetime.datetime = Field(description="The UTC timestamp at which the gap was recorded, set by the server.")
    identified_by: RegisterPersonRef = Field(description="The person who recorded the gap.")
    risk_acceptance: RegisterRiskAcceptance | None = Field(
        description="The request to accept the gap's risk and its approval, null when nobody has asked."
    )
    version: int = Field(description=_VERSION)


class RegisterGapPage(CamelSchema):
    """`{items, total}` with `limit` and `offset` (playbook 10)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_GAP_EXAMPLE], "total": 1}]})

    items: list[RegisterGap] = Field(description="The gaps on this page, by target date then id; a gap with no target date comes last.")
    total: int = Field(description="How many gaps match in total, not how many are on this page; use it to size a pager.")


class RegisterGapBody(WriteBody):
    """`POST /obligations/{obligationId}/gaps`: record a gap."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "title": "Evidence of reconciliation is manual",
                    "severity": "high",
                    "source": "assessment",
                    "orgUnitId": "55555555-5555-4555-8555-555555555555",
                    "ownerId": "8f3b6a0e-2c71-4d95-b8e4-1a7c9d2f5e30",
                    "targetDate": "2026-12-31",
                    "remediation": "Automate the daily reconciliation report.",
                }
            ]
        }
    )

    title: str = Field(min_length=1, max_length=TITLE_MAX, description=f"What falls short, 1 to {TITLE_MAX} characters.")
    description: str | None = Field(default=None, max_length=NOTE_MAX, description=f"The longer account, at most {NOTE_MAX} characters.")
    severity: str = Field(max_length=KEY_MAX, description=f"How serious the gap is. {_RISK_KEY}")
    source: str = Field(max_length=KEY_MAX, description=_GAP_SOURCE)
    org_unit_id: uuid.UUID | None = Field(
        default=None, description="The legal entity the gap is in, as a UUID; absent for the obligation as a whole."
    )
    unit_id: uuid.UUID | None = Field(
        default=None, description="The Statement of Applicability unit the gap is in, as a UUID; absent when it is not about one unit."
    )
    owner_id: uuid.UUID | None = Field(default=None, description=f"The gap's owner. {_PERSON_ID}")
    owner_team: str | None = Field(default=None, max_length=KEY_MAX, description=f"The team that owns the gap. {_TEAM_KEY}")
    target_date: datetime.date | None = Field(default=None, description="The plain date the bank means to close the gap by.")
    remediation: str | None = Field(default=None, max_length=NOTE_MAX, description=f"The plan, at most {NOTE_MAX} characters.")


class RegisterGapPatch(WriteBody):
    """`PATCH /gaps/{gapId}`: amend a gap or move its status; only the fields sent change."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"status": "remediating", "remediation": "Automate the daily reconciliation report."}]}
    )

    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX, description=f"What falls short, 1 to {TITLE_MAX} characters.")
    description: str | None = Field(default=None, max_length=NOTE_MAX, description=f"The longer account, at most {NOTE_MAX} characters.")
    severity: str | None = Field(default=None, max_length=KEY_MAX, description=f"How serious the gap is. {_RISK_KEY}")
    status: str | None = Field(default=None, max_length=KEY_MAX, description=_GAP_STATUS_KEY)
    owner_id: uuid.UUID | None = Field(default=None, description=f"The gap's owner. {_PERSON_ID}")
    owner_team: str | None = Field(default=None, max_length=KEY_MAX, description=f"The team that owns the gap. {_TEAM_KEY}")
    target_date: datetime.date | None = Field(default=None, description="The plain date the bank means to close the gap by.")
    remediation: str | None = Field(default=None, max_length=NOTE_MAX, description=f"The plan, at most {NOTE_MAX} characters.")


class RegisterRiskAcceptanceBody(WriteBody):
    """`POST /gaps/{gapId}/accept-risk`: ask for the gap's risk to be accepted."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"reason": "compensating_control", "note": "The weekly custody review covers the risk until 2027."}]})

    reason: str = Field(
        max_length=KEY_MAX,
        description=(
            "The key of a row in the bank's own risk-acceptance reason vocabulary, at most 64 "
            "characters. The bank's admin may add or relabel rows, so read the vocabulary "
            "endpoint for the live set."
        ),
    )
    note: str | None = Field(default=None, max_length=REASON_MAX, description=f"A note in the requester's own words, at most {REASON_MAX} characters.")


class RegisterGapQuery(CamelSchema):
    """Filters of the gaps list, each optional and combined with AND."""

    status: str | None = Field(default=None, max_length=KEY_MAX, description=f"Only gaps in this status. {_GAP_STATUS_KEY}")
    severity: str | None = Field(default=None, max_length=KEY_MAX, description=f"Only gaps of this severity. {_RISK_KEY}")
    owner: uuid.UUID | None = Field(default=None, description="Only gaps this member owns, by their user UUID.")
    entity: uuid.UUID | None = Field(default=None, description="Only gaps in this legal entity, by its UUID from the bank's organisation.")
    target_from: datetime.date | None = Field(default=None, description="Only gaps whose target date is on or after this plain date.")
    target_to: datetime.date | None = Field(default=None, description="Only gaps whose target date is on or before this plain date.")


# ---------------------------------------------------------------------------------------
# Assessment history and "How we read this rule" (REG-04)
# ---------------------------------------------------------------------------------------
_ASSESSMENT_EXAMPLE: dict[str, Any] = {
    "id": "7a1c3e5f-9b2d-4f6a-8c0e-1d3f5a7b9c20",
    "orgUnitId": "55555555-5555-4555-8555-555555555555",
    "orgUnitName": "Example Bank AB",
    "assessedAt": "2026-09-18T13:05:00Z",
    "assessedBy": _PERSON_EXAMPLE,
    "method": "second_line_review",
    "status": _STATUS_EXAMPLE,
    "riskRating": _RISK_EXAMPLE,
    "rationale": "Second-line review of September found the manual log.",
    "nextReviewDate": "2027-03-31",
}


class RegisterAssessment(CamelSchema):
    """One status assessment, kept unchanged for ever (append-only)."""

    model_config = ConfigDict(json_schema_extra={"examples": [_ASSESSMENT_EXAMPLE]})

    id: uuid.UUID = Field(description="The assessment's UUID in this bank.")
    org_unit_id: uuid.UUID | None = Field(description="The legal entity assessed, as a UUID; null for the obligation as a whole.")
    org_unit_name: str | None = Field(description="The legal entity's name for showing; null for the obligation as a whole.")
    assessed_at: datetime.datetime = Field(description="The UTC timestamp of the assessment, set by the server.")
    assessed_by: RegisterPersonRef = Field(description="The person who assessed the status.")
    method: AssessmentMethod = Field(
        description=(
            "How the status was assessed: `self_assessment` by the first line, "
            "`second_line_review` by compliance, `internal_audit`, `external_audit`, or "
            "`regulator` in a supervisory review. A fixed kind."
        )
    )
    status: RegisterVocabRef = Field(
        description=(
            "The status assessed, as a row of the bank's own `compliance_status` vocabulary, "
            "which its admin may extend; the label is read today, the key as it was then."
        )
    )
    risk_rating: RegisterVocabRef | None = Field(
        description="The risk rated at the time, as a row of the bank's own `risk_rating` vocabulary, which its admin may extend; null when not rated."
    )
    rationale: str = Field(description="Why the status was what it was, in the assessor's own words.")
    next_review_date: datetime.date | None = Field(description="The plain date of the next review set at the time; null when none was set.")


class RegisterAssessmentPage(CamelSchema):
    """`{items, total}` with `limit` and `offset` (playbook 10)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_ASSESSMENT_EXAMPLE], "total": 1}]})

    items: list[RegisterAssessment] = Field(description="The assessments on this page, newest first.")
    total: int = Field(description="How many assessments the obligation has in total, not how many are on this page.")


_INTERPRETATION_VERSION_EXAMPLE: dict[str, Any] = {
    "versionNo": 2,
    "text": "We read this as covering every client account the bank holds, custody included.",
    "author": _PERSON_EXAMPLE,
    "writtenAt": "2026-09-18T13:05:00Z",
}


class RegisterInterpretationVersion(CamelSchema):
    """One version of the bank's reading of a rule, never edited once written."""

    version_no: int = Field(description="The version number, 1 for the first reading and one higher for every later one.")
    text: str = Field(description="How the bank reads the rule, in its own words. Internal legal judgement that never leaves the bank.")
    author: RegisterPersonRef = Field(description="The person who wrote this version.")
    written_at: datetime.datetime = Field(description="The UTC timestamp at which this version was written, set by the server.")


class RegisterInterpretation(CamelSchema):
    """"How we read this rule": the current reading and every earlier one (REG-04)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "obligationId": "44444444-4444-4444-8444-444444444444",
                    "current": _INTERPRETATION_VERSION_EXAMPLE,
                    "earlier": [{**_INTERPRETATION_VERSION_EXAMPLE, "versionNo": 1, "text": "We read this as covering client accounts."}],
                }
            ]
        }
    )

    obligation_id: uuid.UUID = Field(description=_OBLIGATION_ID)
    current: RegisterInterpretationVersion | None = Field(
        description=(
            "The reading in force, null when the bank has written none. Its `versionNo` is what "
            "the next save sends as `If-Match`, 0 when there is none."
        )
    )
    earlier: list[RegisterInterpretationVersion] = Field(description="Every superseded reading, newest first, unchanged; empty when there is none.")


class RegisterInterpretationBody(WriteBody):
    """`PUT /obligations/{obligationId}/interpretation`: write a new version."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"text": "We read this as covering every client account the bank holds, custody included."}]}
    )

    text: str = Field(
        min_length=1,
        max_length=INTERPRETATION_MAX,
        description=(
            f"How the bank reads the rule, 1 to {INTERPRETATION_MAX} characters. Stored as a "
            "new version; the previous one is kept and shown as earlier."
        ),
    )


# ---------------------------------------------------------------------------------------
# Linked internal items (REG-05)
# ---------------------------------------------------------------------------------------
_LINK_EXAMPLE: dict[str, Any] = {
    "id": "3d5f7a9b-1c2e-4a6b-8d0f-2e4a6c8b0d13",
    "kind": {"key": "policy", "kind": None, "label": "Policy"},
    "label": "Client asset policy",
    "url": "https://intranet.example-bank.test/policies/client-assets",
    "externalRef": "POL-014",
    "internalItemId": None,
    "createdBy": _PERSON_EXAMPLE,
    "createdAt": "2026-09-18T13:05:00Z",
}


class RegisterInternalLink(CamelSchema):
    """A policy, procedure, control, process or system of the bank's own linked to an
    obligation, with the reference an outside GRC system knows it by."""

    model_config = ConfigDict(json_schema_extra={"examples": [_LINK_EXAMPLE]})

    id: uuid.UUID = Field(description="The link's UUID in this bank.")
    kind: RegisterVocabRef = Field(
        description=(
            "What the linked item is, as a row of the bank's own `link_kind` vocabulary, seeded "
            "as `policy`, `procedure` and `control`; its admin may add rows such as a process or "
            "a system, so read `GET /vocab/link_kind` for the live set."
        )
    )
    label: str = Field(description="The item's name as the bank calls it, such as `Client asset policy`.")
    url: str | None = Field(description="Where the item lives in the bank's own systems; null when none was given. Never fetched by the server.")
    external_ref: str | None = Field(description="The item's reference in the bank's GRC or document system, such as `POL-014`; null when none was given.")
    internal_item_id: uuid.UUID | None = Field(
        description="The bank's internal item this link points at, as a UUID, when it was picked from the organisation; null for an ad hoc link."
    )
    created_by: RegisterPersonRef = Field(description="The person who made the link.")
    created_at: datetime.datetime = Field(description="The UTC timestamp at which the link was made, set by the server.")


class RegisterInternalLinkPage(CamelSchema):
    """`{items, total}` with `limit` and `offset` (playbook 10)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_LINK_EXAMPLE], "total": 1}]})

    items: list[RegisterInternalLink] = Field(description="The links on this page, oldest first; removed links are not listed.")
    total: int = Field(description="How many links the obligation has in total, not how many are on this page.")


class RegisterInternalLinkBody(WriteBody):
    """`POST /obligations/{obligationId}/internal-links`: link an item of the bank's own."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"kind": "policy", "label": "Client asset policy", "externalRef": "POL-014"}]}
    )

    kind: str = Field(
        max_length=KEY_MAX,
        description=(
            "The key of a row in the bank's own `link_kind` vocabulary, at most 64 characters, "
            "seeded as `policy`, `procedure` and `control`. The bank's admin may add rows, so "
            "read `GET /vocab/link_kind` for the live set."
        ),
    )
    label: str = Field(min_length=1, max_length=TITLE_MAX, description=f"The item's name as the bank calls it, 1 to {TITLE_MAX} characters.")
    url: str | None = Field(default=None, max_length=URL_MAX, description=f"Where the item lives, a link of at most {URL_MAX} characters. Never fetched by the server.")
    external_ref: str | None = Field(
        default=None, max_length=EXTERNAL_REF_MAX, description=f"The item's reference in the bank's GRC system, at most {EXTERNAL_REF_MAX} characters."
    )
    internal_item_id: uuid.UUID | None = Field(default=None, description="An internal item of the bank's organisation to link, as a UUID; absent for an ad hoc link.")


# ---------------------------------------------------------------------------------------
# Statement of Applicability units (REG-08, D-41)
# ---------------------------------------------------------------------------------------
_UNIT_EXAMPLE: dict[str, Any] = {
    "id": "66666666-6666-4666-8666-666666666666",
    "obligationId": "44444444-4444-4444-8444-444444444444",
    "orgUnitId": "55555555-5555-4555-8555-555555555555",
    "reference": "A.5.1",
    "title": "Our information security policies",
    "applicability": "applies",
    "applicabilityReason": "Required by our certification scope",
    "applicabilityDecidedAt": "2026-09-24T09:12:00Z",
    "applicabilityDecidedBy": _PERSON_EXAMPLE,
    "complianceStatus": {"key": "compliant", "kind": "compliant", "label": "Compliant"},
    "hasHistory": True,
    "version": 2,
}
_UNIT_REFERENCE = (
    f"The bank's own reference for the clause or control, such as `A.5.1`, at most "
    f"{UNIT_REFERENCE_MAX} characters, unique per legal entity. Fixed once the unit has history."
)
_UNIT_TITLE = (
    f"The bank's own name for the clause or control, in its own words and never the "
    f"standard's text, at most {UNIT_TITLE_MAX} characters. Fixed once the unit has history."
)


class RegisterUnit(CamelSchema):
    """One clause or control of a standard a legal entity follows, listed by the bank in its
    own words, with its own applicability and status (REG-08)."""

    model_config = ConfigDict(json_schema_extra={"examples": [_UNIT_EXAMPLE]})

    id: uuid.UUID = Field(description="The unit's UUID in this bank.")
    obligation_id: uuid.UUID = Field(description="The standard's conformance obligation the unit sits under, as a UUID.")
    org_unit_id: uuid.UUID = Field(description="The legal entity the unit belongs to, as a UUID from the bank's organisation.")
    reference: str = Field(description="The bank's own reference for the clause or control, such as `A.5.1`.")
    title: str = Field(description="The bank's own name for the clause or control, never the standard's text.")
    applicability: Applicability = Field(description=_APPLICABILITY)
    applicability_reason: str | None = Field(description=_APPLICABILITY_REASON)
    applicability_decided_at: datetime.datetime | None = Field(description=_DECIDED_AT)
    applicability_decided_by: RegisterPersonRef | None = Field(description=_DECIDED_BY)
    compliance_status: RegisterVocabRef = Field(
        description=(
            "How the bank complies with the unit, as a row of its own `compliance_status` "
            "vocabulary, which its admin may extend. The conformance row's status is never "
            "computed from its units."
        )
    )
    has_history: bool = Field(
        description="True once the unit has an applicability decision, a status or a gap, after which its reference and title are fixed; false before."
    )
    version: int = Field(description=_VERSION)


class RegisterUnitPage(CamelSchema):
    """`{items, total}` with `limit` and `offset` (playbook 10)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_UNIT_EXAMPLE], "total": 1}]})

    items: list[RegisterUnit] = Field(description="The units on this page, by reference; removed units are not listed.")
    total: int = Field(description="How many units match in total, not how many are on this page.")


class RegisterUnitQuery(CamelSchema):
    """Filters of the units list."""

    entity: uuid.UUID | None = Field(default=None, description="Only the units of this legal entity, by its UUID from the bank's organisation.")


class RegisterUnitBody(WriteBody):
    """`POST /obligations/{obligationId}/units`: list one unit."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"orgUnitId": "55555555-5555-4555-8555-555555555555", "reference": "A.5.1", "title": "Our information security policies"}]
        }
    )

    org_unit_id: uuid.UUID = Field(description="The legal entity the unit belongs to, as a UUID; its conformance row must apply.")
    reference: str = Field(min_length=1, max_length=UNIT_REFERENCE_MAX, description=_UNIT_REFERENCE)
    title: str = Field(min_length=1, max_length=UNIT_TITLE_MAX, description=_UNIT_TITLE)


class RegisterUnitPatch(WriteBody):
    """`PATCH /units/{unitId}`: rename a unit that has no history yet."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"title": "Our information security policy set"}]})

    reference: str | None = Field(default=None, min_length=1, max_length=UNIT_REFERENCE_MAX, description=_UNIT_REFERENCE)
    title: str | None = Field(default=None, min_length=1, max_length=UNIT_TITLE_MAX, description=_UNIT_TITLE)


class RegisterUnitPasteLine(WriteBody):
    """One pasted line: a reference and a title."""

    reference: str = Field(
        max_length=PASTE_FIELD_MAX,
        description=(
            f"The reference as pasted, at most {PASTE_FIELD_MAX} characters. One longer than a "
            "unit's reference may be is reported on its row, not refused for the whole paste."
        ),
    )
    title: str = Field(
        max_length=PASTE_FIELD_MAX,
        description=(
            f"The title as pasted, in the bank's own words, at most {PASTE_FIELD_MAX} characters. "
            "One longer than a unit's title may be is reported on its row."
        ),
    )


class RegisterUnitPasteBody(WriteBody):
    """`POST /obligations/{obligationId}/units/paste`: many units for one entity, with a dry run."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "orgUnitId": "55555555-5555-4555-8555-555555555555",
                    "lines": [{"reference": "A.5.1", "title": "Our information security policies"}],
                    "dryRun": True,
                }
            ]
        }
    )

    org_unit_id: uuid.UUID = Field(description="The legal entity the units belong to, as a UUID; its conformance row must apply.")
    lines: list[RegisterUnitPasteLine] = Field(
        min_length=1,
        description=(
            "The pasted lines, at least 1, in the order pasted. A call holds at most the "
            "configured `REGISTER_BULK_MAX` lines, 100 by default."
        ),
    )
    dry_run: bool = Field(
        default=True,
        description=(
            "True, the default, answers what would be created and stores nothing; false creates "
            "the units, only when no line is refused, with one audit event per unit."
        ),
    )


class RegisterUnitPasteRow(CamelSchema):
    """What happens to one pasted line."""

    line: int = Field(description="The line's position in the paste, counting from 1.")
    reference: str = Field(description="The reference as pasted, trimmed of surrounding spaces.")
    title: str = Field(description="The title as pasted, trimmed of surrounding spaces.")
    outcome: PasteOutcome = Field(
        description=(
            "`will_create` on a dry run for a line that would become a unit, `created` when it "
            "did, `refused` for a line that cannot become one, with the problem beside it."
        )
    )
    problem: PasteProblem | None = Field(
        description=(
            "Why a line is refused: `duplicate_reference` when the paste repeats a reference, "
            "`reference_exists` when the entity already has a unit with it, "
            "`reference_too_long` or `title_too_long` past the unit limits, `empty_line` for a "
            "line with no reference or title. Null when the line is not refused."
        )
    )
    unit_id: uuid.UUID | None = Field(description="The created unit's UUID, null on a dry run and for a refused line.")


class RegisterUnitPaste(CamelSchema):
    """The dry run's or the commit's answer, one row per pasted line."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "dryRun": True,
                    "rows": [{"line": 1, "reference": "A.5.1", "title": "Our information security policies", "outcome": "will_create", "problem": None, "unitId": None}],
                    "created": 0,
                }
            ]
        }
    )

    dry_run: bool = Field(description="True when nothing was stored, as asked; false when the units were created.")
    rows: list[RegisterUnitPasteRow] = Field(description="One row per pasted line, in the order pasted.")
    created: int = Field(description="How many units were created, 0 on a dry run and whenever any line was refused.")


class RegisterStatementOfApplicability(CamelSchema):
    """The register filtered by a standard and a legal entity: the conformance row and the
    entity's units, each with its decision (REG-08, REG-S15)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "obligationId": "44444444-4444-4444-8444-444444444444",
                    "conformance": _ENTITY_EXAMPLE,
                    "units": [_UNIT_EXAMPLE],
                    "total": 1,
                }
            ]
        }
    )

    obligation_id: uuid.UUID = Field(description="The standard's conformance obligation, as a UUID.")
    conformance: RegisterEntityStatus = Field(
        description="The entity's conformance row with its own assessed status, never computed from the units."
    )
    units: list[RegisterUnit] = Field(description="The entity's units on this page, by reference.")
    total: int = Field(description="How many units the entity has under the standard, not how many are on this page.")


class RegisterStatementQuery(CamelSchema):
    """The one filter the Statement of Applicability needs."""

    entity: uuid.UUID = Field(description="The legal entity whose statement to read, by its UUID from the bank's organisation. Required.")


# ---------------------------------------------------------------------------------------
# Recurring duties (REG-07)
# ---------------------------------------------------------------------------------------
_OCCURRENCE_EXAMPLE: dict[str, Any] = {
    "id": "9e1a3c5b-7d2f-4b8a-9c0e-4f6a8b0c2d35",
    "dueDate": "2026-12-31",
    "status": "upcoming",
    "orgUnitId": None,
    "owner": _PERSON_EXAMPLE,
    "completedAt": None,
    "completedBy": None,
    "note": None,
}


class RegisterDutyOccurrence(CamelSchema):
    """One dated instance of a recurring duty in the bank's calendar."""

    model_config = ConfigDict(json_schema_extra={"examples": [_OCCURRENCE_EXAMPLE]})

    id: uuid.UUID = Field(description="The occurrence's UUID in this bank.")
    due_date: datetime.date = Field(description="The plain date the duty is due, in the bank's own time zone; shown on the roadmap as our own deadline.")
    status: DutyStatus = Field(
        description=(
            "Where the occurrence stands: `upcoming` before work starts, `in_progress` while it "
            "is worked, `done` once completed, `missed` past its date without completion, "
            "`not_applicable` when the obligation no longer applies. A fixed kind."
        )
    )
    org_unit_id: uuid.UUID | None = Field(description="The legal entity the occurrence is for, as a UUID; null for the bank as a whole.")
    owner: RegisterPersonRef | None = Field(description="The member who owns the occurrence; null when nobody does yet.")
    completed_at: datetime.datetime | None = Field(description="The UTC timestamp of completion, null until completed.")
    completed_by: RegisterPersonRef | None = Field(description="The person who completed it, null until completed.")
    note: str | None = Field(description="The completer's note in their own words; null when none was written.")


class RegisterDuty(CamelSchema):
    """A duty the law repeats on this obligation, with its next occurrence."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "1f3a5c7e-9b0d-4e2a-8c4f-6a8b0d2e4f57",
                    "title": "Quarterly client asset report",
                    "recurrenceNote": "Every quarter, on the last day of the quarter",
                    "nextOccurrence": _OCCURRENCE_EXAMPLE,
                }
            ]
        }
    )

    id: uuid.UUID = Field(description="The library's recurring duty, as a UUID. A shared library fact.")
    title: str = Field(description="The duty's title in the reader's language, from the library.")
    recurrence_note: str | None = Field(description="How often the duty recurs, in words, from the library; null when the library states none.")
    next_occurrence: RegisterDutyOccurrence | None = Field(
        description="The next occurrence in the bank's calendar, null when the obligation does not apply to the bank."
    )


class RegisterDutyPage(CamelSchema):
    """`{items, total}` with `limit` and `offset` (playbook 10)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "id": "1f3a5c7e-9b0d-4e2a-8c4f-6a8b0d2e4f57",
                            "title": "Quarterly client asset report",
                            "recurrenceNote": "Every quarter, on the last day of the quarter",
                            "nextOccurrence": _OCCURRENCE_EXAMPLE,
                        }
                    ],
                    "total": 1,
                }
            ]
        }
    )

    items: list[RegisterDuty] = Field(description="The obligation's recurring duties on this page, by next due date.")
    total: int = Field(description="How many recurring duties the obligation has in total, not how many are on this page.")


class RegisterDutyCompleteBody(WriteBody):
    """`POST /duty-occurrences/{occurrenceId}/complete`."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"note": "Filed with the authority on 20 December."}]})

    note: str | None = Field(default=None, max_length=REASON_MAX, description=f"A note on the completion, at most {REASON_MAX} characters.")


class RegisterDutyCompletion(CamelSchema):
    """The completed occurrence and the next one it generated."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "completed": {**_OCCURRENCE_EXAMPLE, "status": "done", "completedAt": "2026-12-20T10:00:00Z", "completedBy": _PERSON_EXAMPLE},
                    "next": {**_OCCURRENCE_EXAMPLE, "id": "0a2c4e6f-8b1d-4f3a-9c5e-7b9d1f3a5c68", "dueDate": "2027-03-31"},
                }
            ]
        }
    )

    completed: RegisterDutyOccurrence = Field(description="The occurrence as completed.")
    next: RegisterDutyOccurrence | None = Field(
        description="The next occurrence, generated from the recurrence rule in the bank's time zone; null when the duty does not recur again."
    )
