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
the same bound the library's draft carries. Chunk 9 adds the workflow (CAS-02 to CAS-08):
every write that moves a case or changes its assessment takes `If-Match` with the case's
`version` and answers 409 `stale_write` without it or with an old one; the "So what?" takes
none and still bumps `version`, so a screen holding an older copy is told. Only the sign-off approval takes a passkey step-up (playbook 4.2). No route here
takes an idempotency key: these are a person's clicks, not an agent's retries.

A vocabulary value is a key on a write and `{key, kind, label}` on a read (`CasesVocabularyRef`),
drawn from one of the bank's own lists — sub-statuses, dismissal and close reasons, effort
sizes — which the bank's admin extends without a deploy; an unknown key answers 422
`unknown_key`.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Literal

from ninja import Field
from pydantic import ConfigDict
from pydantic.json_schema import JsonDict

from apps.library.schemas import LibraryRef
from apps.shared.schemas import CamelSchema, LibraryResponse, WriteBody
from apps.taxonomy.schemas import PersonRef

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


# =======================================================================================
# The case workflow (CAS-02 to CAS-08, chunk 9)
# =======================================================================================
# The longest texts a person types into the workflow. The assessment's two texts carry the
# "So what?"'s own bound; a note and an action's title are a sentence or two.
ASSESSMENT_TEXT_MAX = SO_WHAT_MAX
NOTE_MAX = 2000
ACTION_TITLE_MAX = 500
EVIDENCE_NAME_MAX = 500
EVIDENCE_URL_MAX = 2000
KEY_MAX = 64

CaseCategory = Literal["new", "assigned", "assessing", "implementing", "signoff", "closed", "dismissed"]
AssessmentApplies = Literal["yes", "partly", "no"]
EvidenceKind = Literal["file", "link", "reference"]
ScanState = Literal["pending", "clean", "infected", "error"]

_CATEGORIES = (
    "`new` (registered, nobody has looked yet; the screen reads 'Needs triage'), `assigned` "
    "(triaged with an urgency and an owner), `assessing` (the owner is working out what the "
    "change means for the bank), `implementing` (actions are being done), `signoff` (waiting "
    "for a second person to sign it off with a passkey), `closed` (signed off, or closed by "
    "one person with a reason that needs no work) and `dismissed` (not for this bank, with a "
    "reason, and restorable)"
)
_TENANT_LIST = (
    "The values are rows of the bank's own vocabulary, which the bank's admin may extend, "
    "relabel or retire without a deploy, so read `GET /vocab/{listName}` for the live set "
    "and match on the key, never on the label."
)
_PERSON = "A person in this bank, as their id and display name; the only personal data a case carries about them."
_TIMESTAMP = "an RFC 3339 timestamp in UTC (`2026-09-17T09:12:00Z`)"

PERSON_EXAMPLE: JsonDict = {"id": "8a3c1e5f-2d4b-4f60-9e7a-1b2c3d4e5f60", "name": "Sara Lind"}
ASSESSMENT_EXAMPLE: JsonDict = {
    "applies": "yes",
    "why": "Self-directed trading and Guided investing both pay for external research.",
    "whatMustChange": "Document the annual research quality criteria and have the desk sign them.",
    "internalDeadline": "2026-10-15",
    "effort": {"key": "m", "kind": None, "label": "M"},
    "saved": True,
    "savedBy": PERSON_EXAMPLE,
    "savedAt": "2026-09-18T10:04:00Z",
    "version": 2,
}
CASE_EXAMPLE: JsonDict = {
    "id": "9d0b5a3c-6e14-4f27-8c93-5a1e7b0d2f46",
    "changeId": "c3a6e1f0-7b42-4d8e-95a1-2f0b6c8d4e19",
    "status": "assessing",
    "subStatus": None,
    "urgency": {"key": "within_3_months", "kind": None, "label": "Within 3 months"},
    "urgencyConfirmed": True,
    "footprintMatch": True,
    "owner": PERSON_EXAMPLE,
    "triagedBy": {"id": "5b7e2c1a-9d3f-4e8b-a6c4-0f1e2d3c4b5a", "name": "Johan Berg"},
    "triagedAt": "2026-09-17T08:40:00Z",
    "dismissedReason": None,
    "dismissedBy": None,
    "dismissedAt": None,
    "signoffRequestedBy": None,
    "signoffRequestedAt": None,
    "signedOffBy": None,
    "closeReason": None,
    "closedNote": None,
    "closedAt": None,
    "assessment": ASSESSMENT_EXAMPLE,
    "openActionCount": 0,
    "canRequestSignoff": False,
    "allowedTransitions": ["implementing", "closed"],
    "version": 4,
}
ACTION_EXAMPLE: JsonDict = {
    "id": "2f4a6c8e-1b3d-4f5a-8c7e-9d0b1a2c3e4f",
    "changeId": "c3a6e1f0-7b42-4d8e-95a1-2f0b6c8d4e19",
    "title": "Document the annual research quality criteria",
    "owner": PERSON_EXAMPLE,
    "dueDate": "2026-10-10",
    "done": False,
    "doneAt": None,
    "doneBy": None,
    "createdAt": "2026-09-18T10:12:00Z",
    "version": 1,
}
EVIDENCE_EXAMPLE: JsonDict = {
    "id": "7e9c1a3b-5d2f-4a6e-8b0c-1d3f5a7c9e2b",
    "kind": "file",
    "name": "Research quality criteria 2026.pdf",
    "url": None,
    "sizeBytes": 184320,
    "mimeType": "application/pdf",
    "contentHash": "sha256:9f2c4e6a8b0d1f3e5a7c9b1d3f5e7a9c2b4d6f8a0c2e4b6d8f0a2c4e6b8d0f2a",
    "scanState": "clean",
    "uploadedBy": PERSON_EXAMPLE,
    "uploadedAt": "2026-09-19T13:20:00Z",
}


class CasesVocabularyRef(LibraryResponse):
    """A value from one of the bank's own lists as a read answers it: key and kind, and the
    label in the reader's language. The bank's own zone: its admin manages these rows, and
    no other bank sees them."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"key": "out_of_scope", "kind": None, "label": "Out of scope"}]})

    key: str = Field(
        description=(
            "The row's immutable key, and the only part of this reference to store, compare or "
            "send back. It is drawn from the bank's own vocabulary that the field carrying it "
            "names; an admin may extend, relabel or retire those rows without a deploy, so a "
            "key you have not seen before is new data and not an error."
        ),
        examples=["out_of_scope"],
    )
    kind: str | None = Field(
        description=(
            "The fixed category the row sits in, where its list has one: a sub-status names "
            "the case category it belongs to (`new`, `assigned`, `assessing`, `implementing`, "
            "`signoff`, `closed` or `dismissed`), and a close reason one of `signed_off`, "
            "`no_action` or `not_applicable`. Null for a list without categories, such as "
            "dismissal reasons and effort sizes. Never a tone: a pill's tone follows its slot."
        ),
        examples=[None],
    )
    label: str = Field(
        description=(
            "The value's name in the reader's language, falling back to the bank's default "
            "language and then to the key. For display only: an admin may reword it at any "
            "time, so nothing may match on it."
        ),
        examples=["Out of scope"],
    )


class CasesAssessment(CamelSchema):
    """The case's impact assessment (CAS-03): whether the change applies to the bank, why,
    what must change, the bank's own deadline and the effort. The bank's own zone, never
    shared and never sent to a model endpoint. There are no contributors here: the teams
    that contribute are the case's team participants (D-20)."""

    model_config = ConfigDict(json_schema_extra={"examples": [ASSESSMENT_EXAMPLE]})

    applies: AssessmentApplies = Field(
        description=(
            "Whether the change applies to the bank, a fixed kind: `yes` (it applies and work "
            "follows), `partly` (it applies to part of the business) or `no` (it does not "
            "apply; the case can be closed by one person with that reason). It says the change "
            "applies; it never says the bank complies, which is a separate fact in the register "
            "(REG-01, REG-02)."
        ),
        examples=["yes"],
    )
    why: str | None = Field(
        description=(
            f"Why the change matters to the bank, in its own words, at most {ASSESSMENT_TEXT_MAX} "
            "characters. Tenant content. Null until someone writes it; a saved assessment always "
            "has one, and the case cannot move to implementing without it."
        ),
        examples=["Self-directed trading and Guided investing both pay for external research."],
    )
    what_must_change: str | None = Field(
        description=(
            f"What the bank must change, in its own words, at most {ASSESSMENT_TEXT_MAX} "
            "characters. Tenant content. Null when nobody has written it."
        ),
        examples=["Document the annual research quality criteria and have the desk sign them."],
    )
    internal_deadline: datetime.date | None = Field(
        description=(
            "The bank's own deadline for the work, as a plain calendar date (`2026-10-15`). The "
            "bank's judgement, not the regulator's date, which is the change's key date. Null "
            "when none is set."
        ),
        examples=["2026-10-15"],
    )
    effort: CasesVocabularyRef | None = Field(
        description=(
            "How big the work is, from the bank's `effort_size` vocabulary, `s`, `m` and `l` "
            f"on day one. {_TENANT_LIST} Null when nobody has sized it."
        )
    )
    saved: bool = Field(
        description=(
            "Whether a person has saved the assessment. False while it is an empty form the "
            "case opened with when the assessment started."
        ),
        examples=[True],
    )
    saved_by: PersonRef | None = Field(description=f"Who last saved it. {_PERSON} Null until it is saved.")
    saved_at: datetime.datetime | None = Field(
        description=f"When it was last saved, as {_TIMESTAMP}. Null until it is saved.",
        examples=["2026-09-18T10:04:00Z"],
    )
    version: int = Field(
        description=(
            "The assessment's own version, starting at 1 and raised by every save. Informational: "
            "a save sends the case's `version` in `If-Match`, never this one."
        ),
        examples=[2],
    )


class CasesCase(CamelSchema):
    """One bank's case for one regulatory change, as every workflow move answers it
    (CAS-02 to CAS-08). The bank's own zone under row-level security: no other bank and no
    bleqq person sees it, and none of it reaches a model endpoint. The actions and the
    evidence are read from their own lists."""

    model_config = ConfigDict(json_schema_extra={"examples": [CASE_EXAMPLE]})

    id: uuid.UUID = Field(
        description="This bank's case, as a UUID. One per bank per change (CAS-01), and never another bank's.",
        examples=["9d0b5a3c-6e14-4f27-8c93-5a1e7b0d2f46"],
    )
    change_id: uuid.UUID = Field(
        description=(
            "The library change the case is about, as a UUID, and the address of every "
            "workflow route: the change is shared by every bank, the case is not."
        ),
        examples=["c3a6e1f0-7b42-4d8e-95a1-2f0b6c8d4e19"],
    )
    status: CaseCategory = Field(
        description=(
            f"Where the case stands, one of seven fixed categories the state machine reads: {_CATEGORIES}. "
            "A bank's sub-status sits inside a category and changes nothing a guard decides."
        ),
        examples=["assessing"],
    )
    sub_status: CasesVocabularyRef | None = Field(
        description=(
            "The bank's own finer step inside the category, from its `case_sub_status` "
            f"vocabulary, whose `kind` is the category it sits in; day one seeds one per category, keyed like it. {_TENANT_LIST} "
            "Null when the bank uses none here."
        )
    )
    urgency: LibraryRef = Field(
        description=(
            "How soon this bank must act, as `{key, kind, label}` from the `urgency` library "
            "vocabulary, `act_now`, `within_3_months`, `six_months_plus`, `monitor` or "
            "`no_action` on day one, a vocabulary a platform admin may extend. It is the "
            "agent's suggestion until `urgencyConfirmed` is true."
        )
    )
    urgency_confirmed: bool = Field(
        description=(
            "Whether a person in this bank confirmed the urgency at triage. False means the "
            "value is still the agent's suggestion and must not be reported as the bank's decision."
        ),
        examples=[True],
    )
    footprint_match: bool = Field(
        description=(
            "Whether the change's scope matches this bank's footprint, computed by the server. It "
            "says the change is in scope to look at, never that it applies or that the bank complies."
        ),
        examples=[True],
    )
    owner: PersonRef | None = Field(description=f"Who owns the case, named at triage. {_PERSON} Null before triage.")
    triaged_by: PersonRef | None = Field(description=f"Who triaged the case. {_PERSON} Null before triage.")
    triaged_at: datetime.datetime | None = Field(
        description=f"When the case was triaged, as {_TIMESTAMP}. Null before triage.", examples=["2026-09-17T08:40:00Z"]
    )
    dismissed_reason: CasesVocabularyRef | None = Field(
        description=(
            "Why the bank dismissed the change, from its `dismissal_reason` vocabulary, "
            f"`out_of_scope`, `duplicate` and `already_covered` on day one. {_TENANT_LIST} "
            "Null unless the case is or was dismissed."
        )
    )
    dismissed_by: PersonRef | None = Field(description=f"Who dismissed it. {_PERSON} Null unless it was dismissed.")
    dismissed_at: datetime.datetime | None = Field(
        description=f"When it was dismissed, as {_TIMESTAMP}. Null unless it was dismissed.", examples=[None]
    )
    signoff_requested_by: PersonRef | None = Field(
        description=f"Who asked for sign-off; this person can never sign it off. {_PERSON} Null until someone asks."
    )
    signoff_requested_at: datetime.datetime | None = Field(
        description=f"When sign-off was asked for, as {_TIMESTAMP}. Null until someone asks.", examples=[None]
    )
    signed_off_by: PersonRef | None = Field(
        description=(
            f"The second person who signed the case off with a passkey. {_PERSON} Never the "
            "person who asked, which the database itself refuses. Null until it is signed off."
        )
    )
    close_reason: CasesVocabularyRef | None = Field(
        description=(
            "Why the case was closed, from the bank's `close_reason` vocabulary, whose `kind` is "
            "one of `signed_off` (a second person signed it off), `no_action` or `not_applicable` "
            f"(one person closed it, audited). {_TENANT_LIST} Null while the case is open."
        )
    )
    closed_note: str | None = Field(
        description=f"The note written at the close, at most {NOTE_MAX} characters. Tenant content. Null when none was written.",
        examples=[None],
    )
    closed_at: datetime.datetime | None = Field(
        description=f"When the case was closed, as {_TIMESTAMP}. Null while it is open.", examples=[None]
    )
    assessment: CasesAssessment | None = Field(
        description="The impact assessment, once it has started. Null before the case reaches assessing."
    )
    open_action_count: int = Field(
        description=(
            "How many live actions are not done yet, counted by the server. Sign-off can be "
            "requested only at 0. A removed action is not counted."
        ),
        examples=[0],
    )
    can_request_signoff: bool = Field(
        description=(
            "Computed by the server: true when the case is implementing, no action is open and at "
            "least one piece of evidence has passed the malware scan. It is the same rule the "
            "sign-off request itself checks, so a screen never guesses it."
        ),
        examples=[False],
    )
    allowed_transitions: list[CaseCategory] = Field(
        description=(
            "The categories this case may move to next for the person reading it, computed by the "
            f"server from the state machine and its guards; each is one of {_CATEGORIES}. Empty "
            "means no move is open to this reader now. A move that needs something the request "
            "supplies (an owner, a reason) is listed, and refused if the request leaves it out."
        ),
        examples=[["implementing", "closed"]],
    )
    version: int = Field(
        description=(
            "The case's version, starting at 1 and raised by every write to it, including the "
            "'So what?'. Send it back in `If-Match` on every workflow "
            "write; an older value answers 409 `stale_write` with the current one."
        ),
        examples=[4],
    )


class CasesTriageBody(WriteBody):
    """`POST /changes/{changeId}/triage` (CAS-02): the bank decides how urgent the change is
    and who owns it."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"urgency": "within_3_months", "ownerId": "8a3c1e5f-2d4b-4f60-9e7a-1b2c3d4e5f60", "subStatus": None}]
        }
    )

    urgency: str = Field(
        min_length=1,
        max_length=KEY_MAX,
        description=(
            "The urgency the bank confirms, as a key of the `urgency` library vocabulary, "
            "`act_now`, `within_3_months`, `six_months_plus`, `monitor` or `no_action` on day "
            "one, a vocabulary a platform admin may extend; read `GET /vocab/urgency` for the "
            f"live set. At most {KEY_MAX} characters; an unknown key answers 422 `unknown_key`."
        ),
        examples=["within_3_months"],
    )
    owner_id: uuid.UUID = Field(
        description=(
            "The person in this bank who will own the case, as a UUID. It must be a member of "
            "this bank who may work a case; anyone else is refused."
        ),
        examples=["8a3c1e5f-2d4b-4f60-9e7a-1b2c3d4e5f60"],
    )
    sub_status: str | None = Field(
        default=None,
        max_length=KEY_MAX,
        description=(
            "An optional sub-status inside `assigned`, as a key of the bank's `case_sub_status` "
            f"vocabulary, whose rows the bank's admin may extend. {_TENANT_LIST} At most {KEY_MAX} "
            "characters. Null or left out for none; an unknown key, or one of another category, "
            "answers 422 `unknown_key`."
        ),
        examples=[None],
    )


class CasesReasonBody(WriteBody):
    """`POST /changes/{changeId}/dismiss` (CAS-02): why the bank is not taking the change on."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"reasonKey": "out_of_scope"}]})

    reason_key: str = Field(
        min_length=1,
        max_length=KEY_MAX,
        description=(
            "Why the change is dismissed, as a key of the bank's `dismissal_reason` vocabulary, "
            f"`out_of_scope`, `duplicate` and `already_covered` on day one. {_TENANT_LIST} "
            f"At most {KEY_MAX} characters; an unknown key answers 422 `unknown_key`."
        ),
        examples=["out_of_scope"],
    )


class CasesCloseBody(WriteBody):
    """`POST /changes/{changeId}/close` (CAS-02, CAS-03): one person closes a case that needs
    no work, with a reason, audited (D-92)."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"reasonKey": "no_action", "note": "Covered by the 2025 research policy review."}]}
    )

    reason_key: str = Field(
        min_length=1,
        max_length=KEY_MAX,
        description=(
            "Why the case closes, as a key of the bank's `close_reason` vocabulary. Only a row "
            "whose kind is `no_action` or `not_applicable` closes on one person's word; one of "
            "kind `signed_off` needs the sign-off route and answers 409 `four_eyes_violation` "
            f"here. {_TENANT_LIST} At most {KEY_MAX} characters; an unknown key answers 422 "
            "`unknown_key`."
        ),
        examples=["no_action"],
    )
    note: str = Field(
        default="",
        max_length=NOTE_MAX,
        description=(
            f"An optional note for the case file, at most {NOTE_MAX} characters. Tenant content: "
            "it stays in the bank's zone and never reaches the audit values, a log or a model."
        ),
        examples=["Covered by the 2025 research policy review."],
    )


class CasesNoteBody(WriteBody):
    """`POST /changes/{changeId}/signoff/approve` and `/signoff/send-back` (CAS-06): the
    second person's optional word on the decision."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"note": "Criteria checked against the desk's sign-off."}]})

    note: str = Field(
        default="",
        max_length=NOTE_MAX,
        description=(
            f"An optional note stored with the move, at most {NOTE_MAX} characters. Tenant "
            "content: it stays in the bank's zone and never reaches the audit values, a log or a model."
        ),
        examples=["Criteria checked against the desk's sign-off."],
    )


class CasesAssessmentBody(WriteBody):
    """`PUT /changes/{changeId}/assessment` (CAS-03): the whole assessment, replacing what
    was saved. It moves the case to no other category."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "applies": "yes",
                    "why": "Self-directed trading and Guided investing both pay for external research.",
                    "whatMustChange": "Document the annual research quality criteria and have the desk sign them.",
                    "internalDeadline": "2026-10-15",
                    "effort": "m",
                    "subStatus": None,
                }
            ]
        }
    )

    applies: AssessmentApplies = Field(
        description=(
            "Whether the change applies to the bank, a fixed kind: `yes` (it applies and work "
            "follows), `partly` (it applies to part of the business) or `no` (it does not apply, "
            "and saving it closes a case being assessed on one person's word, which needs "
            "`cases.work`). It never says the bank complies."
        ),
        examples=["yes"],
    )
    why: str = Field(
        min_length=1,
        max_length=ASSESSMENT_TEXT_MAX,
        description=(
            f"Why the change matters to the bank, 1 to {ASSESSMENT_TEXT_MAX} characters, in its "
            "own words. Tenant content: never logged, audited as text or sent to a model."
        ),
        examples=["Self-directed trading and Guided investing both pay for external research."],
    )
    what_must_change: str = Field(
        default="",
        max_length=ASSESSMENT_TEXT_MAX,
        description=(
            f"What the bank must change, at most {ASSESSMENT_TEXT_MAX} characters, empty by "
            "default. Tenant content, kept like `why`."
        ),
        examples=["Document the annual research quality criteria and have the desk sign them."],
    )
    internal_deadline: datetime.date | None = Field(
        default=None,
        description="The bank's own deadline for the work, as a plain calendar date (`2026-10-15`), or null for none.",
        examples=["2026-10-15"],
    )
    effort: str | None = Field(
        default=None,
        max_length=KEY_MAX,
        description=(
            "How big the work is, as a key of the bank's `effort_size` vocabulary, `s`, `m` and "
            f"`l` on day one. {_TENANT_LIST} At most {KEY_MAX} characters; null for unsized, and "
            "an unknown key answers 422 `unknown_key`."
        ),
        examples=["m"],
    )
    sub_status: str | None = Field(
        default=None,
        max_length=KEY_MAX,
        description=(
            "An optional sub-status inside the case's current category, as a key of the bank's "
            f"`case_sub_status` vocabulary. {_TENANT_LIST} At most {KEY_MAX} characters. Null or "
            "left out for none; an unknown key, or one of another category, answers 422 `unknown_key`."
        ),
        examples=[None],
    )


class CasesAction(CamelSchema):
    """One thing that must be done for a case, with an owner and a due date (CAS-04). The
    bank's own zone. Removed actions are not listed; they stay in the case file."""

    model_config = ConfigDict(json_schema_extra={"examples": [ACTION_EXAMPLE]})

    id: uuid.UUID = Field(description="The action, as a UUID; the address of `PATCH` and `DELETE /actions/{actionId}`.", examples=["2f4a6c8e-1b3d-4f5a-8c7e-9d0b1a2c3e4f"])
    change_id: uuid.UUID = Field(
        description="The library change whose case the action belongs to, as a UUID.", examples=["c3a6e1f0-7b42-4d8e-95a1-2f0b6c8d4e19"]
    )
    title: str = Field(
        description=f"What must be done, at most {ACTION_TITLE_MAX} characters. Tenant content.",
        examples=["Document the annual research quality criteria"],
    )
    owner: PersonRef = Field(description=f"Who must do it. {_PERSON}")
    due_date: datetime.date = Field(
        description="When it is due, as a plain calendar date (`2026-10-10`) the bank chose. Overdue is judged in the bank's own time zone.",
        examples=["2026-10-10"],
    )
    done: bool = Field(description="Whether the action is done. Sign-off waits until every live action is.", examples=[False])
    done_at: datetime.datetime | None = Field(description=f"When it was marked done, as {_TIMESTAMP}. Null while open.", examples=[None])
    done_by: PersonRef | None = Field(description=f"Who marked it done. {_PERSON} Null while open.")
    created_at: datetime.datetime = Field(description=f"When it was added, as {_TIMESTAMP}. Set by the server.", examples=["2026-09-18T10:12:00Z"])
    version: int = Field(
        description="The action's version, starting at 1 and raised by every edit. Send it in `If-Match` on `PATCH /actions/{actionId}`.",
        examples=[1],
    )


class CasesActionPage(CamelSchema):
    """`GET /changes/{changeId}/actions`: one page of the case's live actions."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [ACTION_EXAMPLE], "total": 1}]})

    items: list[CasesAction] = Field(
        description="The actions of this page, earliest due date first, removed ones left out. An empty page is a 200."
    )
    total: int = Field(description="How many live actions the case has, across every page.", examples=[1])


class CasesActionBody(WriteBody):
    """`POST /changes/{changeId}/actions` (CAS-04): a new action. Adding the first one
    moves an assessing case to implementing."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "title": "Document the annual research quality criteria",
                    "ownerId": "8a3c1e5f-2d4b-4f60-9e7a-1b2c3d4e5f60",
                    "dueDate": "2026-10-10",
                }
            ]
        }
    )

    title: str = Field(
        min_length=1,
        max_length=ACTION_TITLE_MAX,
        description=f"What must be done, 1 to {ACTION_TITLE_MAX} characters. Tenant content.",
        examples=["Document the annual research quality criteria"],
    )
    owner_id: uuid.UUID = Field(
        description="Who must do it, as a UUID of a member of this bank; anyone else is refused.",
        examples=["8a3c1e5f-2d4b-4f60-9e7a-1b2c3d4e5f60"],
    )
    due_date: datetime.date = Field(description="When it is due, as a plain calendar date (`2026-10-10`).", examples=["2026-10-10"])


class CasesActionPatch(WriteBody):
    """`PATCH /actions/{actionId}` (CAS-04): change what is sent and leave the rest.
    Marking done and reopening are `done: true` and `done: false`."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"done": True}]})

    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=ACTION_TITLE_MAX,
        description=f"A new title, 1 to {ACTION_TITLE_MAX} characters, or left out to keep it.",
        examples=["Document and sign the research quality criteria"],
    )
    owner_id: uuid.UUID | None = Field(
        default=None,
        description="A new owner, as a UUID of a member of this bank, or left out to keep the owner.",
        examples=["8a3c1e5f-2d4b-4f60-9e7a-1b2c3d4e5f60"],
    )
    due_date: datetime.date | None = Field(
        default=None, description="A new due date, as a plain calendar date (`2026-10-17`), or left out to keep it.", examples=["2026-10-17"]
    )
    done: bool | None = Field(
        default=None,
        description="True marks the action done in the caller's name, false reopens it; left out keeps it as it is.",
        examples=[True],
    )


class CasesEvidence(CamelSchema):
    """One piece of evidence on a case (CAS-05): a file, a link or a reference to an
    internal document. The bank's own zone. A file is invisible to a download until the
    malware scan passes; removed evidence is not listed and stays in the case file."""

    model_config = ConfigDict(json_schema_extra={"examples": [EVIDENCE_EXAMPLE]})

    id: uuid.UUID = Field(description="The evidence, as a UUID; the address of its download and its removal.", examples=["7e9c1a3b-5d2f-4a6e-8b0c-1d3f5a7c9e2b"])
    kind: EvidenceKind = Field(
        description=(
            "What the evidence is, a fixed kind: `file` (bytes the bank uploaded, scanned and "
            "hashed, downloadable once clean), `link` (an address the bank recorded, never "
            "fetched by the server) or `reference` (the name of an internal document, with no "
            "bytes and no address)."
        ),
        examples=["file"],
    )
    name: str = Field(description=f"What the evidence is called, at most {EVIDENCE_NAME_MAX} characters. Tenant content.", examples=["Research quality criteria 2026.pdf"])
    url: str | None = Field(description="The address a link points at. Null for a file or a reference. The server never fetches it.", examples=[None])
    size_bytes: int | None = Field(description="A file's size in bytes. Null for a link or a reference.", examples=[184320])
    mime_type: str | None = Field(description="A file's type as the server identified it, such as `application/pdf`. Null for a link or a reference.", examples=["application/pdf"])
    content_hash: str | None = Field(
        description="A file's SHA-256, computed by the server from the bytes it stored, as `sha256:` and 64 hex digits. Null for a link or a reference.",
        examples=["sha256:9f2c4e6a8b0d1f3e5a7c9b1d3f5e7a9c2b4d6f8a0c2e4b6d8f0a2c4e6b8d0f2a"],
    )
    scan_state: ScanState = Field(
        description=(
            "Where the malware scan stands, a fixed kind: `pending` (not scanned yet; a download "
            "is refused), `clean` (passed; downloadable and counted for sign-off), `infected` "
            "(malware found; the bytes are deleted and the row stays) or `error` (the scan "
            "failed; a download is refused). A link or a reference has no bytes and reads `clean`."
        ),
        examples=["clean"],
    )
    uploaded_by: PersonRef = Field(description=f"Who added it. {_PERSON}")
    uploaded_at: datetime.datetime = Field(description=f"When it was added, as {_TIMESTAMP}. Set by the server.", examples=["2026-09-19T13:20:00Z"])


class CasesEvidencePage(CamelSchema):
    """`GET /changes/{changeId}/evidence`: one page of the case's live evidence."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [EVIDENCE_EXAMPLE], "total": 1}]})

    items: list[CasesEvidence] = Field(description="The evidence of this page, newest first, removed pieces left out. An empty page is a 200.")
    total: int = Field(description="How many live pieces of evidence the case has, across every page.", examples=[1])


class CasesEvidenceForm(WriteBody):
    """The form fields of `POST /changes/{changeId}/evidence` (CAS-05), sent as
    `multipart/form-data` beside the `file` part when the kind is `file`."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"kind": "link", "name": "FI decision memo", "url": "https://intranet.example.com/memo/42"}]})

    kind: EvidenceKind = Field(
        description=(
            "What is being added, a fixed kind: `file` (send the bytes in the `file` part), "
            "`link` (send `url`) or `reference` (the name of an internal document, nothing else)."
        ),
        examples=["link"],
    )
    name: str = Field(
        min_length=1,
        max_length=EVIDENCE_NAME_MAX,
        description=f"What the evidence is called, 1 to {EVIDENCE_NAME_MAX} characters. Tenant content.",
        examples=["FI decision memo"],
    )
    url: str = Field(
        default="",
        max_length=EVIDENCE_URL_MAX,
        description=(
            f"The address of a link, an https URL of at most {EVIDENCE_URL_MAX} characters; "
            "empty by default and for the other kinds. The server stores it and never fetches it."
        ),
        examples=["https://intranet.example.com/memo/42"],
    )


class CasesEvidenceCreated(CamelSchema):
    """What `POST /changes/{changeId}/evidence` answers: the stored evidence. There is no
    upload address: the bytes arrive in the same request, and a file starts `pending`."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"evidence": {**EVIDENCE_EXAMPLE, "scanState": "pending"}}]})

    evidence: CasesEvidence = Field(description="The evidence as stored. A file is `pending` until the scan finishes, and cannot be downloaded until it is `clean`.")
