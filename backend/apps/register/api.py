"""Routes of the register app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1).

The register is one bank's judgement laid over the shared library (REG-01 to REG-05, REG-07,
REG-08). Every chunk 8 operation is declared here once, behind the gate it keeps, and calls a
named function in the module of the package that builds it (chunk 8 plan rule 3); until then
that function answers 501 `not_built`. A logic package fills its own module and never this
file.

Every route takes a person's session in their own bank; no agent key reaches the register.
Reads take `register.read`; status, links, interpretations, units and duties take
`register.edit`; gaps take `gaps.edit`. Setting applicability takes `applicability.approve`
and nothing more: one person, a confirmation dialog, an audit event, no step-up (D-75).
Approving a risk acceptance is the one register action behind four eyes and a passkey
step-up. Versioned rows take `If-Match`.
"""

import uuid
from typing import Any

from django.http import HttpRequest
from ninja import Path, Query, Router

from apps.register import applicability, duties, gaps, history, links, soa, status_logic, units
from apps.register.schemas import (
    RegisterApplicability,
    RegisterApplicabilityBody,
    RegisterApplicabilityMany,
    RegisterApplicabilityManyBody,
    RegisterAssessmentPage,
    RegisterDutyCompleteBody,
    RegisterDutyCompletion,
    RegisterDutyPage,
    RegisterEntityPatch,
    RegisterEntityStatus,
    RegisterEntry,
    RegisterGap,
    RegisterGapBody,
    RegisterGapPage,
    RegisterGapPatch,
    RegisterGapQuery,
    RegisterInternalLink,
    RegisterInternalLinkBody,
    RegisterInternalLinkPage,
    RegisterInterpretation,
    RegisterInterpretationBody,
    RegisterPatch,
    RegisterRiskAcceptanceBody,
    RegisterStatementOfApplicability,
    RegisterStatementQuery,
    RegisterUnit,
    RegisterUnitBody,
    RegisterUnitPage,
    RegisterUnitPaste,
    RegisterUnitPasteBody,
    RegisterUnitPatch,
    RegisterUnitQuery,
)
from apps.shared import permissions as perms
from apps.shared.authentication import SessionAuth
from apps.shared.permissions import requires_permission, requires_step_up
from apps.shared.schemas import PageQuery
from apps.taxonomy.http import actor_for, answers_problems, caller_tenant, if_match
from apps.taxonomy.reading import language_order

router = Router(tags=["Register"])

SESSION = SessionAuth()

# What each path parameter means to a caller, hoisted out of the signatures so a route
# body stays one line of gate, schema and call (playbook 4.1).
_OBLIGATION_ID = (
    "The library obligation whose register row this is, as a UUID. The obligation is a shared "
    "library fact; everything this route reads or writes about it is the caller's bank's own."
)
_ORG_UNIT_ID = "The bank's own legal entity to write for, as a UUID from its organisation."
_GAP_ID = "The gap, as a UUID. Another bank's gap answers 404, never 403."
_LINK_ID = "The internal link, as a UUID. Another bank's link answers 404, never 403."
_UNIT_ID = "The Statement of Applicability unit, as a UUID. Another bank's unit answers 404, never 403."
_OCCURRENCE_ID = "The dated duty occurrence, as a UUID. Another bank's occurrence answers 404, never 403."


# ---------------------------------------------------------------------------------------
# The register entry and its legal entities (REG-02)
# ---------------------------------------------------------------------------------------
@router.get(
    "/obligations/{obligation_id}/register",
    response=RegisterEntry,
    auth=SESSION,
    operation_id="getRegisterEntry",
    by_alias=True,
    summary="See whether an obligation applies to your bank and how you comply",
)
@requires_permission(perms.REGISTER_READ)
@answers_problems
def get_register_entry(request: HttpRequest, obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID)) -> Any:
    """The bank's register entry for one obligation: its applicability with the reason, the
    compliance status, note, risk, owners, process, system, evidence location and next review,
    and a row per legal entity where the obligation spans several. Applicability and status
    are separate facts and neither is derived from the other.

    A person's session holding `register.read`, which every role of a bank carries. A read: it
    writes nothing, not even an empty entry, so an obligation nobody has answered for reads as
    "under assessment" with version 0.

    Where legal entities the obligation applies to have rows, `complianceStatus` is the worst
    of theirs by category: gap, then partly, then not assessed, then compliant.

    Errors: `unauthenticated` (401) without a session; `permission_denied` (403) without
    `register.read`; `not_found` (404) for an obligation the bank cannot see.
    """
    tenant = caller_tenant(request)
    return status_logic.read_register(tenant=tenant, order=language_order(request, tenant=tenant), obligation_id=obligation_id)


@router.patch(
    "/obligations/{obligation_id}/register",
    response=RegisterEntry,
    auth=SESSION,
    operation_id="updateRegister",
    by_alias=True,
    summary="Record how your bank complies with an obligation",
)
@requires_permission(perms.REGISTER_EDIT)
@answers_problems
def update_register(
    request: HttpRequest, body: RegisterPatch, obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID)
) -> Any:
    """Changes the fields the body sends on the bank's register entry: compliance status,
    status note, risk, first-line owner, compliance contact, process, system, evidence
    location, owner team and next review. Applicability is not here; it has its own route. A
    status outside the not assessed category needs applicability `applies` first. A
    status change also writes an assessment row with the rationale, so the history has it.
    The first write creates the entry.

    A person's session holding `register.edit`. `If-Match` is required: the `version` last
    read, 0 for an entry nobody has written; a row changed in between is refused and nothing
    is merged. Records one audit event naming the person with keys, ids and dates before and
    after, and the names of the text fields that changed, never their words. No step-up.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `register.edit`;
    `not_found` (404) for an obligation the bank cannot see; `stale_write` (409) when
    `If-Match` is not the current version; `invalid_transition` (409) for a status outside the not
    assessed category while the obligation does not apply or is still under assessment;
    `unknown_key` (422) for a status, risk or team key that is not an active row of the bank's
    list, with `validKeys` listing those that are; `unknown_member` (422) for an owner or
    contact who is not an active member of the bank; `validation_error` (422) for a missing
    `If-Match`, one that is not a version, or a body the schema refuses.
    """
    tenant = caller_tenant(request)
    return status_logic.update_register(
        tenant=tenant,
        actor=actor_for(request),
        order=language_order(request, tenant=tenant),
        obligation_id=obligation_id,
        body=body,
        expected_version=if_match(request),
    )


@router.patch(
    "/obligations/{obligation_id}/register/entities/{org_unit_id}",
    response=RegisterEntityStatus,
    auth=SESSION,
    operation_id="updateRegisterEntity",
    by_alias=True,
    summary="Record how one of your legal entities complies with an obligation",
)
@requires_permission(perms.REGISTER_EDIT)
@answers_problems
def update_register_entity(
    request: HttpRequest,
    body: RegisterEntityPatch,
    obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID),
    org_unit_id: uuid.UUID = Path(..., description=_ORG_UNIT_ID),
) -> Any:
    """Changes the fields the body sends on one legal entity's row under an obligation that
    spans several: status, note, risk, owner or owner team, process, system, evidence location
    and next review. The entity's row is created in the same transaction when it does not
    exist yet; the obligation's own status then reads the worst of the entities it applies to.
    A person or a team owns the row, never both: setting one clears the other. A status other
    than the not assessed category needs the entity's applicability `applies` first.

    A person's session holding `register.edit`. `If-Match` is required: the row's `version`,
    0 for a row not written yet. Records one audit event naming the person with keys, ids and
    dates before and after, and the names of the text fields that changed, never their words.
    No step-up.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `register.edit`;
    `not_found` (404) for an obligation the bank cannot see, or an org unit that is not one of
    its active legal entities; `stale_write` (409); `invalid_transition` (409) for a status
    outside the not assessed category while the entity's applicability is not `applies`;
    `unknown_key` (422) for a status, risk or team key the bank's list does not hold, with
    `validKeys`; `unknown_member` (422) for an owner who is not an active member;
    `validation_error` (422) for a missing `If-Match`, an owner and a team sent together, or a
    body the schema refuses.
    """
    tenant = caller_tenant(request)
    return status_logic.update_entity_status(
        tenant=tenant,
        actor=actor_for(request),
        order=language_order(request, tenant=tenant),
        obligation_id=obligation_id,
        org_unit_id=org_unit_id,
        body=body,
        expected_version=if_match(request),
    )


# ---------------------------------------------------------------------------------------
# Applicability (REG-01, D-75)
# ---------------------------------------------------------------------------------------
@router.put(
    "/obligations/{obligation_id}/applicability",
    response=RegisterApplicability,
    auth=SESSION,
    operation_id="setApplicability",
    by_alias=True,
    summary="Say whether an obligation applies to your bank, a legal entity or a unit",
)
@requires_permission(perms.APPLICABILITY_APPROVE)
@answers_problems
def set_applicability(
    request: HttpRequest, body: RegisterApplicabilityBody, obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID)
) -> Any:
    """Stores the answer to "Does it apply to us?" at once, with its reason: for the
    obligation as a whole, for one legal entity (`orgUnitId`) or for one unit of a standard
    (`unitId`). Call it after the person confirmed the answer in a dialog; nothing is
    requested and nobody else approves it (D-75). An entity's scope row is created in the same
    transaction when it does not exist yet. The compliance status and the gaps are untouched:
    "applies" and "we comply" are separate facts.

    A person's session holding `applicability.approve`. No step-up. Send `If-Match` with the
    row's `version`. Records one audit event naming the person, the value before and after,
    and the reason.

    Errors: `unauthenticated` (401); `permission_denied` (403) without
    `applicability.approve`; `not_found` (404) for an obligation, entity or unit the bank
    cannot see; `stale_write` (409); `validation_error` (422) for an unknown value, an empty
    reason, or both `orgUnitId` and `unitId`. Published ahead of the logic that will fill it,
    and answering 501 `not_built` until that ships.
    """
    tenant = caller_tenant(request)
    return applicability.set_applicability(
        tenant=tenant,
        actor=actor_for(request),
        order=language_order(request, tenant=tenant),
        obligation_id=obligation_id,
        body=body,
        expected_version=if_match(request),
    )


@router.post(
    "/applicability",
    response=RegisterApplicabilityMany,
    auth=SESSION,
    operation_id="setApplicabilityMany",
    by_alias=True,
    summary="Set many applicability answers at once after confirming them",
)
@requires_permission(perms.APPLICABILITY_APPROVE)
@answers_problems
def set_applicability_many(request: HttpRequest, body: RegisterApplicabilityManyBody) -> Any:
    """Stores many confirmed answers in one call, such as the decisions of a pasted Statement
    of Applicability: each row names an obligation and, optionally, a legal entity or a unit,
    with its answer and reason (AC-REG1). Call it after the person confirmed every row in one
    dialog. All rows are stored in one transaction or none is.

    A person's session holding `applicability.approve`. No step-up and no `If-Match`: the
    confirmation covers the rows as the dialog showed them. At most `REGISTER_BULK_MAX` rows,
    100 by default. Records one audit event per row naming the person, the value before and
    after, and the reason.

    Errors: `unauthenticated` (401); `permission_denied` (403) without
    `applicability.approve`; `not_found` (404) when any row names an obligation, entity or unit
    the bank cannot see; `validation_error` (422) for an empty list, a list over the cap or a
    row the schema refuses. Published ahead of the logic that will fill it, and answering 501
    `not_built` until that ships.
    """
    tenant = caller_tenant(request)
    return applicability.set_applicability_many(
        tenant=tenant, actor=actor_for(request), order=language_order(request, tenant=tenant), body=body
    )


# ---------------------------------------------------------------------------------------
# Gaps and risk acceptance (REG-03)
# ---------------------------------------------------------------------------------------
@router.get(
    "/obligations/{obligation_id}/gaps",
    response=RegisterGapPage,
    auth=SESSION,
    operation_id="listObligationGaps",
    by_alias=True,
    summary="See the gaps your bank has recorded on an obligation",
)
@requires_permission(perms.REGISTER_READ)
@answers_problems
def list_obligation_gaps(
    request: HttpRequest, page: PageQuery = Query(...), obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID)
) -> Any:
    """The bank's gaps on one obligation, open and closed, each with its owner, severity,
    source, status, target date, plan and any risk acceptance. Gaps stay visible whatever the
    obligation's applicability, because a gap is a fact about how the bank complies.

    A person's session holding `register.read`. A read. Pages with `limit` and `offset`, 20 by
    default and 100 at most; an obligation with no gaps is a 200 with an empty page.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `register.read`;
    `not_found` (404) for an obligation the bank cannot see; `validation_error` (422) for a
    page out of range.
    """
    tenant = caller_tenant(request)
    return gaps.list_obligation_gaps(
        tenant=tenant,
        order=language_order(request, tenant=tenant),
        obligation_id=obligation_id,
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "/obligations/{obligation_id}/gaps",
    response={201: RegisterGap},
    auth=SESSION,
    operation_id="createGap",
    by_alias=True,
    summary="Record a gap with an owner, a severity, a target date and a plan",
)
@requires_permission(perms.GAPS_EDIT)
@answers_problems
def create_gap(
    request: HttpRequest, body: RegisterGapBody, obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID)
) -> Any:
    """Records how the bank falls short of an obligation, on the obligation as a whole or one
    legal entity, with its title, severity, source, owner (a person or a team), target date
    and remediation plan. The gap starts in the gap status list's open row, and its target
    date appears on the roadmap as our own deadline. The bank's register entry on the
    obligation is created with it when nobody has worked on the obligation yet.

    A person's session holding `gaps.edit`. No step-up. Records one audit event naming the
    person, with ids and keys and never the text they typed. Answers 201 with the gap.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `gaps.edit`;
    `not_found` (404) for an obligation or legal entity the bank cannot see;
    `does_not_apply` (409) when the obligation, or its answer for that legal entity, is
    "does not apply": a gap is a fact about how the bank complies with a rule that applies;
    `unknown_key` (422) for a severity, source or team key the bank's list does not hold;
    `unknown_member` (422) for an owner who is not an active member of the bank;
    `validation_error` (422) for a body the schema refuses or a person and a team as owner
    together; `not_built` (501) for a gap on a Statement of Applicability unit, which is not
    built yet.
    """
    tenant = caller_tenant(request)
    return 201, gaps.create_gap(
        tenant=tenant,
        actor=actor_for(request),
        order=language_order(request, tenant=tenant),
        obligation_id=obligation_id,
        body=body,
    )


@router.get(
    "/gaps",
    response=RegisterGapPage,
    auth=SESSION,
    operation_id="listRegisterGaps",
    by_alias=True,
    summary="See every gap across your register",
)
@requires_permission(perms.REGISTER_READ)
@answers_problems
def list_register_gaps(request: HttpRequest, filters: Query[RegisterGapQuery], page: PageQuery = Query(...)) -> Any:
    """Every gap the bank has recorded, across all obligations, by target date then id, with
    filters for status, severity, owner, legal entity and a target-date range, each combined
    with AND. This is the gaps screen's list.

    A person's session holding `register.read`. A read. Pages with `limit` and `offset`, 20 by
    default and 100 at most; filters matching nothing are a 200 with an empty page. A query
    parameter the list does not name is ignored.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `register.read`;
    `validation_error` (422) for an owner or entity that is not a UUID, a date that is not a
    date, a key longer than 64 characters or a page out of range.
    """
    tenant = caller_tenant(request)
    return gaps.list_gaps(
        tenant=tenant, order=language_order(request, tenant=tenant), filters=filters, limit=page.limit, offset=page.offset
    )


@router.patch(
    "/gaps/{gap_id}",
    response=RegisterGap,
    auth=SESSION,
    operation_id="updateGap",
    by_alias=True,
    summary="Amend a gap or move it on",
)
@requires_permission(perms.GAPS_EDIT)
@answers_problems
def update_gap(request: HttpRequest, body: RegisterGapPatch, gap_id: uuid.UUID = Path(..., description=_GAP_ID)) -> Any:
    """Changes the fields the body sends on a gap: title, description, severity, owner, target
    date, plan, or its status, between the open and remediating categories and on to closed.
    Closing a gap clears a risk acceptance still waiting on it. Accepting a risk is not a
    status change here, and neither is reopening a closed gap; each has its own route.

    A person's session holding `gaps.edit`. Send `If-Match` with the gap's `version`; it is
    required. No step-up. Records one audit event naming the person with the keys, ids and
    dates before and after, and the names (never the text) of the typed fields it changed.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `gaps.edit`;
    `not_found` (404) for a gap the bank does not have; `stale_write` (409) for an `If-Match`
    that is absent or not the current version; `invalid_transition` (409) for a status the gap
    cannot move to here; `unknown_key` (422) for a key the bank's list does not hold;
    `unknown_member` (422) for an owner who is not an active member; `validation_error`
    (422) for a body the schema refuses or a person and a team as owner together.
    """
    tenant = caller_tenant(request)
    return gaps.update_gap(
        tenant=tenant,
        actor=actor_for(request),
        order=language_order(request, tenant=tenant),
        gap_id=gap_id,
        body=body,
        expected_version=if_match(request),
    )


@router.post(
    "/gaps/{gap_id}/accept-risk",
    response=RegisterGap,
    auth=SESSION,
    operation_id="requestRiskAcceptance",
    by_alias=True,
    summary="Ask for a gap's risk to be accepted",
)
@requires_permission(perms.GAPS_EDIT)
@answers_problems
def request_risk_acceptance(
    request: HttpRequest, body: RegisterRiskAcceptanceBody, gap_id: uuid.UUID = Path(..., description=_GAP_ID)
) -> Any:
    """Asks for the gap's risk to be accepted, with a reason key from the bank's
    risk-acceptance list and a note. The gap then shows "Waiting for approval" and its status
    does not move until a second person approves.

    A person's session holding `gaps.edit`. No step-up. Records one audit event naming the
    person and the reason key; the note stays on the gap and never enters the audit row.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `gaps.edit`;
    `not_found` (404) for a gap the bank does not have; `invalid_transition` (409) for a gap
    that is closed or already accepted; `request_pending` (409) when an acceptance is already
    waiting for approval; `unknown_key` (422) for a reason the bank's list does not hold,
    naming the keys it does; `validation_error` (422) for a body the schema refuses.
    """
    tenant = caller_tenant(request)
    return gaps.request_risk_acceptance(
        tenant=tenant, actor=actor_for(request), order=language_order(request, tenant=tenant), gap_id=gap_id, body=body
    )


@router.post(
    "/gaps/{gap_id}/accept-risk/approve",
    response=RegisterGap,
    auth=SESSION,
    operation_id="approveRiskAcceptance",
    by_alias=True,
    summary="Approve accepting a gap's risk as the second person",
)
@requires_permission(perms.RISK_ACCEPT_APPROVE)
@requires_step_up
@answers_problems
def approve_risk_acceptance(request: HttpRequest, gap_id: uuid.UUID = Path(..., description=_GAP_ID)) -> Any:
    """Approves a waiting risk acceptance, which moves the gap to the gap status list's
    risk-accepted row and stores the approver and the time. Four eyes: the approver is never
    the person who asked for the acceptance, which a check constraint enforces as well.

    A person's session holding `risk.accept.approve`, with a passkey step-up younger than the
    configured freshness window. No body. Records one audit event naming both people, the
    reason key and the step-up assertion, and never the requester's note.

    Errors: `unauthenticated` (401); `permission_denied` (403) without
    `risk.accept.approve`; `step_up_required` (403) without a fresh step-up, which the screen
    answers by opening the passkey prompt and retrying; `not_found` (404) for a gap the bank
    does not have; `four_eyes_violation` (409) when the caller asked for the acceptance,
    before anything is written; `invalid_transition` (409) when no acceptance is waiting.
    """
    tenant = caller_tenant(request)
    return gaps.approve_risk_acceptance(
        tenant=tenant,
        actor=actor_for(request),
        order=language_order(request, tenant=tenant),
        gap_id=gap_id,
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
    )


@router.post(
    "/gaps/{gap_id}/reopen",
    response=RegisterGap,
    auth=SESSION,
    operation_id="reopenGap",
    by_alias=True,
    summary="Reopen a closed or risk-accepted gap",
)
@requires_permission(perms.GAPS_EDIT)
@answers_problems
def reopen_gap(request: HttpRequest, gap_id: uuid.UUID = Path(..., description=_GAP_ID)) -> Any:
    """Moves a closed or risk-accepted gap back to the gap status list's open row and clears
    its acceptance; the earlier acceptance stays readable in the audit log.

    A person's session holding `gaps.edit`. No body and no step-up. Records one audit event
    naming the person.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `gaps.edit`;
    `not_found` (404) for a gap the bank does not have; `invalid_transition` (409) for a gap
    that is open or remediating.
    """
    tenant = caller_tenant(request)
    return gaps.reopen_gap(
        tenant=tenant, actor=actor_for(request), order=language_order(request, tenant=tenant), gap_id=gap_id
    )


# ---------------------------------------------------------------------------------------
# Assessment history and "How we read this rule" (REG-04)
# ---------------------------------------------------------------------------------------
@router.get(
    "/obligations/{obligation_id}/assessments",
    response=RegisterAssessmentPage,
    auth=SESSION,
    operation_id="listAssessments",
    by_alias=True,
    summary="See every earlier assessment of an obligation, with who and when",
)
@requires_permission(perms.REGISTER_READ)
@answers_problems
def list_assessments(
    request: HttpRequest, page: PageQuery = Query(...), obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID)
) -> Any:
    """The bank's assessment history of one obligation, newest first: each status assessed,
    with its author, time, method, risk, rationale and the legal entity it was about. The
    history is append-only; nothing in it is ever edited.

    A person's session holding `register.read`. A read. Pages with `limit` and `offset`, 20 by
    default and 100 at most; no assessments is a 200 with an empty page.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `register.read`;
    `not_found` (404) for an obligation the bank cannot see; `validation_error` (422) for a
    page out of range.
    """
    tenant = caller_tenant(request)
    return history.list_assessments(
        tenant=tenant,
        order=language_order(request, tenant=tenant),
        obligation_id=obligation_id,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/obligations/{obligation_id}/interpretation",
    response=RegisterInterpretation,
    auth=SESSION,
    operation_id="getInterpretation",
    by_alias=True,
    summary="Read how your bank reads a rule, and how it read it before",
)
@requires_permission(perms.REGISTER_READ)
@answers_problems
def get_interpretation(request: HttpRequest, obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID)) -> Any:
    """"How we read this rule": the bank's current reading of the obligation with its author
    and date, and every earlier reading unchanged. Internal legal judgement that never leaves
    the bank. An obligation with no reading is a 200 with `current` null.

    A person's session holding `register.read`. A read.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `register.read`;
    `not_found` (404) for an obligation the bank cannot see.
    """
    return history.read_interpretation(tenant=caller_tenant(request), obligation_id=obligation_id)


@router.put(
    "/obligations/{obligation_id}/interpretation",
    response=RegisterInterpretation,
    auth=SESSION,
    operation_id="saveInterpretation",
    by_alias=True,
    summary="Write down how your bank reads a rule",
)
@requires_permission(perms.REGISTER_EDIT)
@answers_problems
def save_interpretation(
    request: HttpRequest, body: RegisterInterpretationBody, obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID)
) -> Any:
    """Writes a new version of the bank's reading of the rule. The previous version is kept,
    marked as earlier, and stays readable; nothing is edited in place. A version has no
    approval step.

    A person's session holding `register.edit`. Send `If-Match` with the current `versionNo`,
    0 when there is none. No step-up. Records one audit event naming the person.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `register.edit`;
    `not_found` (404) for an obligation the bank cannot see; `stale_write` (409) when somebody
    wrote a version in between; `validation_error` (422) for empty or over-long text.
    """
    return history.save_interpretation(
        tenant=caller_tenant(request),
        actor=actor_for(request),
        obligation_id=obligation_id,
        body=body,
        expected_version=if_match(request),
    )


# ---------------------------------------------------------------------------------------
# Linked internal items (REG-05)
# ---------------------------------------------------------------------------------------
@router.get(
    "/obligations/{obligation_id}/internal-links",
    response=RegisterInternalLinkPage,
    auth=SESSION,
    operation_id="listInternalLinks",
    by_alias=True,
    summary="See the policies, procedures and controls linked to an obligation",
)
@requires_permission(perms.REGISTER_READ)
@answers_problems
def list_internal_links(
    request: HttpRequest, page: PageQuery = Query(...), obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID)
) -> Any:
    """The bank's own items linked to one obligation, each with its kind, name, link and the
    reference an outside GRC system knows it by, so that system can read the links. Removed
    links are not listed.

    A person's session holding `register.read`. A read. Pages with `limit` and `offset`, 20 by
    default and 100 at most; no links is a 200 with an empty page.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `register.read`;
    `not_found` (404) for an obligation the bank cannot see; `validation_error` (422) for a
    page out of range.
    """
    tenant = caller_tenant(request)
    return links.list_links(
        tenant=tenant,
        order=language_order(request, tenant=tenant),
        obligation_id=obligation_id,
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "/obligations/{obligation_id}/internal-links",
    response={201: RegisterInternalLink},
    auth=SESSION,
    operation_id="addInternalLink",
    by_alias=True,
    summary="Link one of your policies, procedures or controls to an obligation",
)
@requires_permission(perms.REGISTER_EDIT)
@answers_problems
def add_internal_link(
    request: HttpRequest, body: RegisterInternalLinkBody, obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID)
) -> Any:
    """Links an item of the bank's own to an obligation: picked from its organisation's
    internal items, or created from this same call with its kind, name, reference, link,
    owner, part of the organisation, external system and reference, and review dates. The url
    is an http or https address, stored as given and never fetched.

    A person's session holding `register.edit`. No step-up. Records one audit event for the
    link, and one more for the item when the call creates it, each naming the person.
    Answers 201 with the link.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `register.edit`;
    `not_found` (404) for an obligation or internal item the bank cannot see; `already_linked`
    (409) when the item is already linked to this obligation; `duplicate_key` (409) when a new
    item's kind and name are taken, so pick that item instead; `unknown_key` (422) for a kind
    that is not an active row of the bank's link kind list; `validation_error` (422) for a
    url that is not a web address, a picked item of another kind, an item picked and
    described at once, or an owner who is not a member.
    """
    tenant = caller_tenant(request)
    return 201, links.add_link(
        tenant=tenant,
        actor=actor_for(request),
        order=language_order(request, tenant=tenant),
        obligation_id=obligation_id,
        body=body,
    )


@router.delete(
    "/internal-links/{link_id}",
    response={204: None},
    auth=SESSION,
    operation_id="removeInternalLink",
    by_alias=True,
    summary="Unlink an item from an obligation",
)
@requires_permission(perms.REGISTER_EDIT)
@answers_problems
def remove_internal_link(request: HttpRequest, link_id: uuid.UUID = Path(..., description=_LINK_ID)) -> Any:
    """Removes a link between an obligation and one of the bank's items. A soft removal: the
    link is marked removed and kept for the history, and the item itself survives. Answers 204
    with no body.

    A person's session holding `register.edit`. No step-up. Records one audit event naming
    the person.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `register.edit`;
    `not_found` (404) for a link the bank does not have or one already removed.
    """
    links.remove_link(tenant=caller_tenant(request), actor=actor_for(request), link_id=link_id)


# ---------------------------------------------------------------------------------------
# Statement of Applicability units (REG-08)
# ---------------------------------------------------------------------------------------
@router.get(
    "/obligations/{obligation_id}/units",
    response=RegisterUnitPage,
    auth=SESSION,
    operation_id="listUnits",
    by_alias=True,
    summary="See the clauses and controls a legal entity lists under a standard",
)
@requires_permission(perms.REGISTER_READ)
@answers_problems
def list_units(
    request: HttpRequest,
    filters: Query[RegisterUnitQuery],
    page: PageQuery = Query(...),
    obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID),
) -> Any:
    """The units the bank lists under a standard's conformance obligation, by reference, each
    with its own applicability, reason, status and whether it has history; `entity` narrows
    them to one legal entity. Removed units are not listed. The units are the bank's own
    words; nothing here is indexed or sent to a model.

    A person's session holding `register.read`. A read. Pages with `limit` and `offset`, 20 by
    default and 100 at most; no units is a 200 with an empty page.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `register.read`;
    `not_found` (404) for an obligation the bank cannot see; `validation_error` (422) for an
    entity that is not a UUID or a page out of range. Published ahead of the logic that will
    fill it, and answering 501 `not_built` until that ships.
    """
    tenant = caller_tenant(request)
    return units.list_units(
        tenant=tenant,
        order=language_order(request, tenant=tenant),
        obligation_id=obligation_id,
        entity=filters.entity,
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "/obligations/{obligation_id}/units",
    response={201: RegisterUnit},
    auth=SESSION,
    operation_id="createUnit",
    by_alias=True,
    summary="List one clause or control under a standard, in your own words",
)
@requires_permission(perms.REGISTER_EDIT)
@answers_problems
def create_unit(
    request: HttpRequest, body: RegisterUnitBody, obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID)
) -> Any:
    """Adds one unit for a legal entity under a standard's conformance obligation, by the
    bank's own reference and title. A unit exists only under a standard the library admitted,
    for an entity whose conformance row applies. It starts undecided.

    A person's session holding `register.edit`. No step-up. Records one audit event naming
    the person. Answers 201 with the unit.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `register.edit`;
    `not_found` (404) for an obligation or entity the bank cannot see; `validation_error`
    (422) for an empty or over-long reference or title. Published ahead of the logic that
    will fill it, and answering 501 `not_built` until that ships.
    """
    tenant = caller_tenant(request)
    return 201, units.create_unit(
        tenant=tenant,
        actor=actor_for(request),
        order=language_order(request, tenant=tenant),
        obligation_id=obligation_id,
        body=body,
    )


@router.patch(
    "/units/{unit_id}",
    response=RegisterUnit,
    auth=SESSION,
    operation_id="updateUnit",
    by_alias=True,
    summary="Rename a unit that has no history yet",
)
@requires_permission(perms.REGISTER_EDIT)
@answers_problems
def update_unit(request: HttpRequest, body: RegisterUnitPatch, unit_id: uuid.UUID = Path(..., description=_UNIT_ID)) -> Any:
    """Changes a unit's reference or title. Once the unit has an applicability decision, a
    status or a gap, both are fixed, so a decision can never be moved to another control by a
    rename.

    A person's session holding `register.edit`. Send `If-Match` with the unit's `version`. No
    step-up. Records one audit event naming the person with the values before and after.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `register.edit`;
    `not_found` (404) for a unit the bank does not have; `stale_write` (409);
    `validation_error` (422). Published ahead of the logic that will fill it, and answering
    501 `not_built` until that ships.
    """
    tenant = caller_tenant(request)
    return units.update_unit(
        tenant=tenant,
        actor=actor_for(request),
        order=language_order(request, tenant=tenant),
        unit_id=unit_id,
        body=body,
        expected_version=if_match(request),
    )


@router.delete(
    "/units/{unit_id}",
    response={204: None},
    auth=SESSION,
    operation_id="removeUnit",
    by_alias=True,
    summary="Remove a unit that has no history yet",
)
@requires_permission(perms.REGISTER_EDIT)
@answers_problems
def remove_unit(request: HttpRequest, unit_id: uuid.UUID = Path(..., description=_UNIT_ID)) -> Any:
    """Removes a unit from the entity's list. A soft removal: the unit is marked removed and
    kept, never deleted, and a unit with history cannot be removed. Answers 204 with no body.

    A person's session holding `register.edit`. Send `If-Match` with the unit's `version`. No
    step-up. Records one audit event naming the person.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `register.edit`;
    `not_found` (404) for a unit the bank does not have; `stale_write` (409). Published ahead
    of the logic that will fill it, and answering 501 `not_built` until that ships.
    """
    units.remove_unit(
        tenant=caller_tenant(request), actor=actor_for(request), unit_id=unit_id, expected_version=if_match(request)
    )


@router.post(
    "/obligations/{obligation_id}/units/paste",
    response=RegisterUnitPaste,
    auth=SESSION,
    operation_id="pasteUnits",
    by_alias=True,
    summary="Paste a legal entity's clauses and controls, checking them first",
)
@requires_permission(perms.REGISTER_EDIT)
@answers_problems
def paste_units(
    request: HttpRequest, body: RegisterUnitPasteBody, obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID)
) -> Any:
    """Lists many units for one legal entity from pasted lines of reference and title. With
    `dryRun` true, the default, it answers what each line would become and stores nothing;
    with `dryRun` false it creates every unit in one transaction, only when no line is
    refused. Set their applicability afterwards with `POST /applicability`.

    A person's session holding `register.edit`. At most `REGISTER_BULK_MAX` lines, 100 by
    default. No step-up. A commit records one audit event per unit naming the person.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `register.edit`;
    `not_found` (404) for an obligation or entity the bank cannot see; `validation_error`
    (422) for no lines, too many lines or a line longer than the paste allows. Published ahead
    of the logic that will fill it, and answering 501 `not_built` until that ships.
    """
    return units.paste_units(tenant=caller_tenant(request), actor=actor_for(request), obligation_id=obligation_id, body=body)


@router.get(
    "/obligations/{obligation_id}/statement-of-applicability",
    response=RegisterStatementOfApplicability,
    auth=SESSION,
    operation_id="getStatementOfApplicability",
    by_alias=True,
    summary="Read a legal entity's Statement of Applicability for a standard",
)
@requires_permission(perms.REGISTER_READ)
@answers_problems
def get_statement_of_applicability(
    request: HttpRequest,
    filters: Query[RegisterStatementQuery],
    page: PageQuery = Query(...),
    obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID),
) -> Any:
    """The register filtered by a standard and one legal entity: the entity's conformance row
    with its own assessed status, and each unit with its reference, the bank's title, its
    applicability and reason, its status, who set it and when. No status is computed from the
    units.

    A person's session holding `register.read`. A read. `entity` is required. Units page with
    `limit` and `offset`, 20 by default and 100 at most.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `register.read`;
    `not_found` (404) for an obligation or entity the bank cannot see; `validation_error`
    (422) without `entity` or with a page out of range. Published ahead of the logic that
    will fill it, and answering 501 `not_built` until that ships.
    """
    tenant = caller_tenant(request)
    return soa.statement_of_applicability(
        tenant=tenant,
        order=language_order(request, tenant=tenant),
        obligation_id=obligation_id,
        entity=filters.entity,
        limit=page.limit,
        offset=page.offset,
    )


# ---------------------------------------------------------------------------------------
# Recurring duties (REG-07)
# ---------------------------------------------------------------------------------------
@router.get(
    "/obligations/{obligation_id}/duties",
    response=RegisterDutyPage,
    auth=SESSION,
    operation_id="listDuties",
    by_alias=True,
    summary="See the recurring duties of an obligation and when each is next due",
)
@requires_permission(perms.REGISTER_READ)
@answers_problems
def list_duties(
    request: HttpRequest, page: PageQuery = Query(...), obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID)
) -> Any:
    """The duties the law repeats on one obligation, from the library, each with the bank's
    next dated occurrence, its owner and its status. The occurrence dates appear on the
    roadmap as our own deadlines.

    A person's session holding `register.read`. Pages with `limit` and `offset`, 20 by
    default and 100 at most; an obligation with no recurring duty is a 200 with an empty page.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `register.read`;
    `not_found` (404) for an obligation the bank cannot see; `validation_error` (422) for a
    page out of range. Published ahead of the logic that will fill it, and answering 501
    `not_built` until that ships.
    """
    tenant = caller_tenant(request)
    return duties.list_duties(
        tenant=tenant,
        order=language_order(request, tenant=tenant),
        obligation_id=obligation_id,
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "/duty-occurrences/{occurrence_id}/complete",
    response=RegisterDutyCompletion,
    auth=SESSION,
    operation_id="completeDutyOccurrence",
    by_alias=True,
    summary="Mark a dated duty done",
)
@requires_permission(perms.REGISTER_EDIT)
@answers_problems
def complete_duty_occurrence(
    request: HttpRequest, body: RegisterDutyCompleteBody, occurrence_id: uuid.UUID = Path(..., description=_OCCURRENCE_ID)
) -> Any:
    """Marks an occurrence done with an optional note and generates only the next one, from
    the duty's recurrence rule in the bank's time zone. Completing it again writes nothing
    twice.

    A person's session holding `register.edit`. No step-up. Records one audit event naming
    the person.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `register.edit`;
    `not_found` (404) for an occurrence the bank does not have; `validation_error` (422) for a
    note over the limit. Published ahead of the logic that will fill it, and answering 501
    `not_built` until that ships.
    """
    return duties.complete_occurrence(
        tenant=caller_tenant(request), actor=actor_for(request), occurrence_id=occurrence_id, body=body
    )
