"""Request and response schemas of the cases app: camelCase through CamelSchema, app-prefixed
class names where a shape is specific to this app (playbook 4.1).

Everything in this file is one bank's own zone. A case is a bank's judgement about a
library change: its wording of the "So what?", its owner, its urgency and its decision
about each suggested obligation link. Those rows carry a `tenant_id` under enabled and
forced row-level security, so no other bank and no bleqq person reads them, and none of
their text reaches a log, Sentry, analytics or a model endpoint (NFR-01, NFR-04, D-07).
Nothing here writes a library row: confirming a link on a case leaves `change_obligation`
exactly as it was (WAT-04, ruling C).

Limits, in words as well as in the keywords: the "So what?" is at most 4000 characters,
the same bound the library's draft carries. No route in this app is versioned in R1, so
none takes `If-Match` and none can answer a stale write — the case's own concurrency
arrives with the rest of CAS-08 in chunk 9, and until then the last save wins. No route
here takes a passkey step-up: sign-off, which does, is chunk 9. No route here takes an
idempotency key: these are a person's clicks, not an agent's retries.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Literal

from ninja import Field
from pydantic import ConfigDict

from apps.shared.schemas import CamelSchema, WriteBody

__all__ = ["CamelSchema"]

# The longest "So what?" a bank may store: the same bound as the library's draft, so
# confirming a draft can never be refused for length.
SO_WHAT_MAX = 4000

CaseLinkDecision = Literal["accepted", "removed"]


class CasesSoWhatBody(WriteBody):
    """`PUT /changes/{changeId}/so-what` (WAT-05): this bank's own wording. Written by a
    person with `cases.work` in their own bank; saving it marks the text confirmed, because
    a person who rewrote it has already decided."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "text": (
                        "Self-directed trading and Guided investing both pay for external research. "
                        "Confirm with the desk that the annual quality criteria are documented before 1 October."
                    )
                }
            ]
        }
    )

    text: str = Field(
        min_length=1,
        max_length=SO_WHAT_MAX,
        description=(
            f"What this change means for this bank, 1 to {SO_WHAT_MAX} characters, in the "
            "bank's own words. It replaces the AI draft copied from the library. It is tenant "
            "content: it stays in this bank's zone, never reaches another bank, a log or a "
            "model endpoint, and it changes nothing in the shared library."
        ),
        examples=["Confirm with the desk that the annual research quality criteria are documented before 1 October."],
    )


class CasesSoWhat(CamelSchema):
    """The "So what?" as this bank holds it, answered by both the save and the confirm.
    A bank's own zone: another bank reading the same change sees its own copy, still an AI
    draft until its own person acts (WAT-05)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "caseId": "9d0b5a3c-6e14-4f27-8c93-5a1e7b0d2f46",
                    "changeId": "c3a6e1f0-7b42-4d8e-95a1-2f0b6c8d4e19",
                    "text": "Confirm with the desk that the annual research quality criteria are documented before 1 October.",
                    "confirmed": True,
                    "confirmedAt": "2026-09-17T09:12:00Z",
                    "confirmedByName": "Sara Lind",
                    "isAiDraft": False,
                }
            ]
        }
    )

    case_id: uuid.UUID = Field(
        description=(
            "This bank's case for the change, as a UUID. One per bank per change (CAS-01), and "
            "never another bank's."
        ),
        examples=["9d0b5a3c-6e14-4f27-8c93-5a1e7b0d2f46"],
    )
    change_id: uuid.UUID = Field(
        description=(
            "The library change the case is about, as a UUID. The change is shared by every "
            "bank; the case is not."
        ),
        examples=["c3a6e1f0-7b42-4d8e-95a1-2f0b6c8d4e19"],
    )
    text: str | None = Field(
        description=(
            "The wording this bank holds. It starts as the library's AI draft, copied in when "
            "the case was created, and becomes the bank's own the moment someone saves over it. "
            "Null when no draft has been written for the change yet."
        ),
        examples=["Confirm with the desk that the annual research quality criteria are documented before 1 October."],
    )
    confirmed: bool = Field(
        description=(
            "Whether a person in this bank has confirmed or rewritten the wording. False means "
            "the text above is still an AI draft, which is how the screen labels it. A reader "
            "must not quote an unconfirmed 'So what?' as this bank's position."
        ),
        examples=[True],
    )
    confirmed_at: datetime.datetime | None = Field(
        description=(
            "When a person in this bank confirmed the wording, as an RFC 3339 timestamp in UTC "
            "(`2026-09-17T09:12:00Z`). Null while it is still an AI draft."
        ),
        examples=["2026-09-17T09:12:00Z"],
    )
    confirmed_by_name: str | None = Field(
        description=(
            "The name of the person in this bank who confirmed it, for the screen and the case "
            "file. Null while it is a draft. A name and an id are the only personal data this "
            "API carries about a confirmation (playbook 4.7)."
        ),
        examples=["Sara Lind"],
    )
    is_ai_draft: bool = Field(
        description=(
            "Computed by the server: true when the text is still the model's words, which is "
            "exactly `confirmed` being false with text present. Sent as its own field because "
            "the label 'AI draft' is what the screen shows and AI output stays labelled until a "
            "person confirms it (WAT-05, AUD-02)."
        ),
        examples=[False],
    )


class CasesObligationLinkBody(WriteBody):
    """`POST /changes/{changeId}/case/obligation-links` (WAT-04): this bank accepts a
    suggested library link as real for itself. Written by a person with `cases.work`. It
    writes one row in this bank's zone and changes no library row."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"obligationId": "7c1f0b3e-52a4-4f9e-8a21-6d4b2c0a9e17"}]})

    obligation_id: uuid.UUID = Field(
        description=(
            "The obligation this bank accepts as affected by the change, as a UUID. It must be an "
            "obligation the library already links to the change, or already in this bank's "
            "inventory; an unknown obligation answers 404, and this call never creates a "
            "library row (AC-PRO1)."
        ),
        examples=["7c1f0b3e-52a4-4f9e-8a21-6d4b2c0a9e17"],
    )


class CasesObligationLink(CamelSchema):
    """One obligation-link decision of this bank. The bank's own zone: the shared library's
    own link, its origin and its confidence are unchanged by anything here, and another
    bank's decision about the same link is invisible (WAT-04, ruling C)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "obligationId": "7c1f0b3e-52a4-4f9e-8a21-6d4b2c0a9e17",
                    "title": "Assess the quality of investment research paid for",
                    "instrumentShortName": "FFFS 2017:2",
                    "refLabel": "11 kap. 4 §",
                    "decision": "accepted",
                    "decidedAt": "2026-09-17T09:12:00Z",
                    "decidedByName": "Sara Lind",
                }
            ]
        }
    )

    obligation_id: uuid.UUID = Field(
        description=(
            "The library obligation the decision is about, as a UUID. The decision is this "
            "bank's alone and changes no library row."
        ),
        examples=["7c1f0b3e-52a4-4f9e-8a21-6d4b2c0a9e17"],
    )
    title: str = Field(
        description="The obligation's title in the reader's language, from the shared library.",
        examples=["Assess the quality of investment research paid for"],
    )
    instrument_short_name: str = Field(
        description="The short name of the instrument the obligation sits in, from the shared library.", examples=["FFFS 2017:2"]
    )
    ref_label: str = Field(
        description="Where in that instrument the obligation sits, as the instrument numbers it.", examples=["11 kap. 4 §"]
    )
    decision: CaseLinkDecision = Field(
        description=(
            "What this bank said, a fixed kind with two members: `accepted` (the link is real "
            "for us, and the case works it) and `removed` (not related to us, so the case hides "
            "it). `removed` is stored, not deleted, so the case file says the bank looked and "
            "said no. Neither value touches the library's own link."
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
    decided_by_name: str | None = Field(
        description="The name of the person in this bank who decided, for the case file. Null only for a decision the system made.",
        examples=["Sara Lind"],
    )
