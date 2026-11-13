"""Routes of the register app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1).

The register is one bank's judgement laid over the shared library (REG-01 to REG-05, REG-07,
REG-08). Every chunk 8 operation is declared here once, behind the gate it keeps, and calls a
named function in the module that owns its logic (chunk 8 plan rule 3); a logic change goes
in that module, never in this file.

Every route takes a person's session in their own bank, except the two agent reads at the
end: a credential of an agent access entry with `tenant:read` and tenant reach on reads the
settled decisions D-76 lists, and nothing else (acc-register-read, ACC-04).
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

from apps.register import agent_read, applicability, company_view, decide_all, duties, gaps, history, links, panels, reason_draft, soa, status_logic, units
from apps.register.schemas import (
    RegisterInternalItemPage,
    RegisterInternalItemQuery,
    RegisterApplicability,
    RegisterApplicabilityAnswerPage,
    RegisterApplicabilityAnswerQuery,
    RegisterApplicabilityBody,
    RegisterApplicabilityCompany,
    RegisterApplicabilityMany,
    RegisterApplicabilityManyBody,
    RegisterApplicabilityRegulationPage,
    RegisterApplicabilityRegulationQuery,
    RegisterAssessmentPage,
    RegisterDecideAll,
    RegisterDecideAllBody,
    RegisterDecision,
    RegisterDecisionPage,
    RegisterDutyCompleteBody,
    RegisterDutyCompletion,
    RegisterDutyPage,
    RegisterEntityPatch,
    RegisterEntityStatus,
    RegisterEntry,
    RegisterEntryWithPanels,
    RegisterGap,
    RegisterGapBody,
    RegisterGapPage,
    RegisterGapPatch,
    RegisterGapQuery,
    RegisterInstrumentApplicability,
    RegisterInternalLink,
    RegisterInternalLinkBody,
    RegisterInternalLinkPage,
    RegisterInterpretation,
    RegisterInterpretationBody,
    RegisterPatch,
    RegisterReasonDraft,
    RegisterReasonDraftBody,
    RegisterRiskAcceptanceBody,
    RegisterSpannedEntity,
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
from apps.shared.authentication import ApiKeyAuth, SessionAuth
from apps.shared.permissions import requires_permission, requires_scope, requires_step_up
from apps.shared.schemas import PageQuery
from apps.taxonomy.http import actor_for, answers_problems, caller_tenant, caller_user, if_match, principal
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
_INSTRUMENT_ID = (
    "The regulation to roll up, as its UUID in the library, the `id` the instruments list gives. "
    "A regulation the bank cannot see answers 404, never 403."
)


# ---------------------------------------------------------------------------------------
# The register entry and its legal entities (REG-02)
# ---------------------------------------------------------------------------------------
@router.get(
    "/obligations/{obligation_id}/register",
    response=RegisterEntryWithPanels,
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

    `panels` carries what the obligation page shows beside the entry when it opens, so the page
    asks once: the legal entities the obligation spans, the gaps, the newest assessments, the
    linked internal items, a standard's units, the participants, the problem reports, the
    related changes and the comments. Each part is the first page its own route reads, and
    later pages come from that route. A part behind a permission this route does not demand is
    null for a caller without it: `problemReports` without `problems.report`, `changes`
    without `watch.read`, `comments` without `library.read`.

    A person's session holding `register.read`, which every role of a bank carries. A read: it
    writes nothing, not even an empty entry, so an obligation nobody has answered for reads as
    "under assessment" with version 0. It costs a fixed number of queries however many rows
    each part holds.

    Where legal entities the obligation applies to have rows, `complianceStatus` is the worst
    of theirs by category: gap, then partly, then not assessed, then compliant.

    Errors: `not_found` (404) for an obligation the bank cannot see.
    """
    tenant = caller_tenant(request)
    return panels.read_with_panels(
        who=principal(request),
        user=caller_user(request),
        tenant=tenant,
        order=language_order(request, tenant=tenant),
        obligation_id=obligation_id,
    )


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

    Errors: `not_found` (404) for an obligation the bank cannot see; `invalid_transition`
    (409) for a status outside the not assessed category while the obligation does not apply
    or is still under assessment; `unknown_key` (422) for a status, risk or team key that is
    not an active row of the bank's list, with `validKeys` listing those that are;
    `unknown_member` (422) for an owner or contact who is not an active member of the bank;
    `validation_error` (422) for a missing `If-Match`, one that is not a version, or a body
    the schema refuses.
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

    Errors: `not_found` (404) for an obligation the bank cannot see, or an org unit that is
    not one of its active legal entities; `invalid_transition` (409) for a status outside
    the not assessed category while the entity's applicability is not `applies`;
    `unknown_key` (422) for a status, risk or team key the bank's list does not hold, with
    `validKeys`; `unknown_member` (422) for an owner who is not an active member;
    `validation_error` (422) for a missing `If-Match`, an owner and a team sent together, or
    a body the schema refuses.
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
    and the reason. When the reason began as an AI draft, send its id as `reasonDraftId`: the
    draft's AI log row then reads confirmed or edited, and the audit event records the draft's
    id and that review.

    Errors: `not_found` (404) for an obligation, entity or unit the bank cannot see, a
    legal entity the obligation does not span, or a `reasonDraftId` that is not a draft the
    caller was given in this bank; `validation_error` (422) for an unknown
    value, an empty reason, or both `orgUnitId` and `unitId`; `scope_not_applicable` (422)
    for a unit whose legal entity no longer follows the standard. A unit's answer is stored
    on the unit, never on its entity's conformance row, and joins the unit's history in the
    Statement of Applicability.
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
    100 by default; to decide everything a legal entity is offered, however many, with one
    answer and one reason, use `POST /applicability/decide-all`. Records one audit event per
    row naming the person, the value before and after, and the reason.

    Errors: `not_found` (404) when any row names an obligation, entity or unit the bank
    cannot see, or a legal entity its obligation does not span; `validation_error` (422) for
    an empty list, a list over the cap, the same target twice or a row the schema refuses;
    `scope_not_applicable` (422) for a unit whose legal entity no longer follows the
    standard.
    """
    tenant = caller_tenant(request)
    return applicability.set_applicability_many(
        tenant=tenant, actor=actor_for(request), order=language_order(request, tenant=tenant), body=body
    )


# c8-ui-applicability-status: the legal entities an obligation spans (REG-01, D-42).
@router.get(
    "/obligations/{obligation_id}/register/entities",
    response=list[RegisterSpannedEntity],
    auth=SESSION,
    operation_id="listSpannedEntities",
    by_alias=True,
    summary="See which of your legal entities an obligation spans",
    openapi_extra={
        "responses": {
            200: {"content": {"application/json": {"example": [{"orgUnitId": "55555555-5555-4555-8555-555555555555", "orgUnitName": "Example Bank AB"}]}}}
        }
    },
)
@requires_permission(perms.REGISTER_READ)
@answers_problems
def list_spanned_entities(request: HttpRequest, obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID)) -> Any:
    """Every active legal entity of the bank that the obligation spans, by name, whether or
    not anyone has answered for it yet: those whose legal-entity term the obligation carries,
    or all of them when it carries none in that dimension, as a standard's conformance
    obligation does (D-42). These are exactly the entities `setApplicability` accepts as
    `orgUnitId`; the obligation page offers one answer per entity where there are several.

    A person's session holding `register.read`, which every role of a bank carries. A read: it
    writes nothing, not even a scope row, and no audit event. A bank with no legal entity
    recorded gets an empty list with 200. The list is the bank's legal entities, a handful, so
    it is not paged.

    Errors: `not_found` (404) for an obligation the bank cannot see.
    """
    caller_tenant(request)
    return applicability.list_spanned(obligation_id=obligation_id)


# ---------------------------------------------------------------------------------------
# What applies, company by company (REG-01, FP-05; company_view.py)
# ---------------------------------------------------------------------------------------
@router.get(
    "/applicability/companies",
    response=list[RegisterApplicabilityCompany],
    auth=SESSION,
    operation_id="listApplicabilityCompanies",
    by_alias=True,
    summary="See, company by company, how many obligations still await an answer",
    openapi_extra={
        "responses": {
            200: {
                "content": {
                    "application/json": {
                        "example": [
                            {
                                "orgUnit": {"id": "55555555-5555-4555-8555-555555555555", "name": "Example Bank AB"},
                                "offered": 14,
                                "applies": 9,
                                "notApplicable": 2,
                                "underAssessment": 3,
                            }
                        ]
                    }
                }
            }
        }
    },
)
@requires_permission(perms.REGISTER_READ)
@answers_problems
def list_applicability_companies(request: HttpRequest) -> Any:
    """Every active legal entity of the bank, by name, with how many obligations the register
    offers for it and how its answers to "Does it apply to us?" stand: how many apply, how many
    do not, how many are under assessment and, of those, how many nobody has answered at all
    (`toDecide`, what `POST /applicability/decide-all` would decide for the entity). Call it to
    open the "What applies" page, then read one company's regulations and obligations with its
    id.

    An obligation is offered for a legal entity when it is in the bank's working inventory,
    the rows `GET /obligations` lists by default, and it spans the entity: it is scoped to
    the entity's type or to no type, and an approved regulatory scope request has not taken
    every term it carries in some dimension out of the entity's own scope. These are the
    entities `GET /obligations/{obligationId}/register/entities` names. Being offered
    decides nothing, and nothing here suggests an answer: a person answers each obligation.
    The answer counted for an entity is its own where the obligation spans two or more of
    the bank's legal entities, and the obligation's own where it spans fewer, as the
    obligation page asks it.

    A person's session holding `register.read`, which every role of a bank carries. A read: it
    writes nothing and no audit event. The list is the bank's legal entities, a handful, so it
    is not paged. A bank with no active legal entity gets an empty list with 200.
    """
    return company_view.list_companies(tenant=caller_tenant(request))


@router.get(
    "/applicability/regulations",
    response=RegisterApplicabilityRegulationPage,
    auth=SESSION,
    operation_id="listApplicabilityRegulations",
    by_alias=True,
    summary="See the regulations that reach one of your companies",
)
@requires_permission(perms.REGISTER_READ)
@answers_problems
def list_applicability_regulations(request: HttpRequest, page: Query[PageQuery], filters: Query[RegisterApplicabilityRegulationQuery]) -> Any:
    """The regulations with at least one obligation the register offers for one legal entity,
    by the regulation's stable key, each with how the entity's answers stand over its offered
    obligations. `state` keeps the regulations with an obligation nobody has answered, or with
    one a person has, and `q` those whose name, short name or official reference holds a
    phrase, as the instruments list matches it; a regulation kept carries its whole counts
    either way. Its `toDecide` is how many obligations a Decide all run narrowed to it would
    decide.

    `through` says what brings the regulation into the entity's scope: the regulation's regime,
    and the lines of the entity's own public register entry that give it that regime, such as
    its business or a licence. No line means no register fact gives it, not that it does not
    reach the entity. It is a fact about scope and never an answer.

    A person's session holding `register.read`. A read: it writes nothing and no audit event.
    Pages with `limit` and `offset`, 20 by default and 100 at most; an entity the register
    offers nothing for, or filters matching nothing, is a 200 with an empty page.

    Errors: `not_found` (404) for an `orgUnitId` that is not one of the bank's active legal
    entities, another bank's included; `validation_error` (422) for a missing `orgUnitId` or
    one that is not a UUID, a `state` outside its two values, a `q` longer than 200
    characters or holding a NUL character, or a page out of range.
    """
    tenant = caller_tenant(request)
    return company_view.list_regulations(
        tenant=tenant, order=language_order(request, tenant=tenant), query=filters, limit=page.limit, offset=page.offset
    )


@router.get(
    "/applicability/rows",
    response=RegisterApplicabilityAnswerPage,
    auth=SESSION,
    operation_id="listApplicabilityRows",
    by_alias=True,
    summary="See one regulation's obligations for one company, with the answer so far",
)
@requires_permission(perms.REGISTER_READ)
@answers_problems
def list_applicability_rows(request: HttpRequest, page: Query[PageQuery], filters: Query[RegisterApplicabilityAnswerQuery]) -> Any:
    """The obligations of one regulation the register offers for one legal entity, in the
    inventory's order, each with the answer so far, its reason, who set it and when. Call it
    to list what a person can decide for the company under that regulation.

    Each row says what an answer for it must name: `orgUnitId` is the entity where the
    obligation spans two or more of the bank's legal entities, and null, for the obligation as
    a whole, where it spans fewer. Send it back with `obligationId` to
    `PUT /obligations/{obligationId}/applicability`, with the row's `version` as `If-Match`,
    or to `POST /applicability` for many rows at once. `matchedTerms` lists which of the
    obligation's own scope terms the entity carries, by its type or its register entry. No
    row ever carries a suggested answer: whether an obligation applies is a person's decision.
    `state` keeps the rows nobody has answered, whose `decidedBy` is null and which
    `POST /applicability/decide-all` would decide, or those a person has answered.

    A person's session holding `register.read`. A read: it writes nothing and no audit event.
    Pages with `limit` and `offset`, 20 by default and 100 at most. A regulation that offers
    the entity nothing, and a key no regulation the bank can see has, is a 200 with an empty
    page. The reason is tenant content that never leaves the bank.

    Errors: `not_found` (404) for an `orgUnitId` that is not one of the bank's active legal
    entities, another bank's included; `validation_error` (422) for a missing `orgUnitId` or
    `instrument`, an `orgUnitId` that is not a UUID, an `instrument` that is not a stable key
    (letters, digits, hyphens and underscores, at most 120 characters), a `state` outside
    its two values or a page out of range.
    """
    tenant = caller_tenant(request)
    return company_view.list_rows(
        tenant=tenant, order=language_order(request, tenant=tenant), query=filters, limit=page.limit, offset=page.offset
    )


@router.get(
    "/instruments/{instrument_id}/applicability",
    response=RegisterInstrumentApplicability,
    auth=SESSION,
    operation_id="getInstrumentApplicability",
    by_alias=True,
    summary="See how a regulation stands for your bank and for each company",
)
@requires_permission(perms.REGISTER_READ)
@answers_problems
def get_instrument_applicability(request: HttpRequest, instrument_id: uuid.UUID = Path(..., description=_INSTRUMENT_ID)) -> Any:
    """One regulation rolled up for the bank, for the regulation's own page: how many of its
    obligations are in the bank's working inventory, how many of those apply, do not apply
    and are still under assessment, and, for those that apply, how the bank complies, counted
    by compliance status in the order of the bank's scale.

    The counts are the bank-level answers the inventory shows, so each equals the total of
    `GET /obligations` for the same regulation under the same applicability or compliance
    status filter: an obligation applies when the bank answered so for the obligation or for
    any legal entity, and its status is the worst of the entities it applies to. "Applies"
    and "we comply" stay separate facts. `companies` carries the rows of
    `GET /applicability/companies` narrowed to this regulation, leaving out a legal entity it
    offers nothing for.

    A person's session holding `register.read`. A read: it writes nothing and no audit event.
    A regulation with no obligation in the working inventory reads as zeros and empty lists.

    Errors: `not_found` (404) for a regulation the bank cannot see, another bank's own
    included; `validation_error` (422) for an id that is not a UUID.
    """
    tenant = caller_tenant(request)
    return company_view.instrument_applicability(tenant=tenant, order=language_order(request, tenant=tenant), instrument_id=instrument_id)


# ---------------------------------------------------------------------------------------
# Decide all (REG-01, D-75, D-128; decide_all.py)
# ---------------------------------------------------------------------------------------
@router.post(
    "/applicability/decide-all",
    response={202: RegisterDecideAll},
    auth=SESSION,
    operation_id="decideAllApplicability",
    by_alias=True,
    summary="Decide everything still unanswered for one company at once, in the background",
)
@requires_permission(perms.APPLICABILITY_APPROVE)
@answers_problems
def decide_all_applicability(request: HttpRequest, body: RegisterDecideAllBody) -> Any:
    """Decide all: call it once a person has confirmed, in one dialog, that the obligations
    the register offers for one legal entity and that nobody has answered apply, or do not:
    all of them, those of one regulation (`instrument`), or the rows they ticked
    (`obligationIds`). One answer and one reason for all, and no limit on how many. The count
    to print on the button is `toDecide` in `GET /applicability/companies` and
    `GET /applicability/regulations`.

    It reads the targets at that moment and answers 202 at once with the run's state. The
    worker then sets each one through the same logic as
    `PUT /obligations/{obligationId}/applicability`, a chunk at a time, each row with its own
    audit event naming the person, the value before and after and the reason, and with its
    recurring duties scheduled when the answer is `applies`. An obligation a person has
    answered is never a target, whatever the answer, one a colleague left under assessment
    with a reason included; one answered between the call and the worker's turn is left alone
    and counted as skipped. An obligation offered after the call waits for the next decision.
    Compliance statuses and gaps are untouched.

    It writes one audit row for the decision itself, on the legal entity: how many obligations
    it lists, the regulation if any, the answer and whether rows were selected, never the
    reason. When the reason began as an AI draft, send its id as `reasonDraftId`: the draft's
    AI log row then reads confirmed or edited, and that audit row records the draft's id and
    that review. Read the progress with `GET /applicability/decide-all`. Before each chunk the
    worker checks that the person is still an active member holding `applicability.approve`,
    and otherwise stops and records why.

    A person's session holding `applicability.approve`. No step-up and no second approver
    (D-75): the confirmation covers the run as the dialog showed it. An API key never reaches
    this route.

    Errors to branch on: `decision_running` (409) while the caller's earlier run in this bank
    is still running; `not_found` (404) for an `orgUnitId` that is not one of the bank's active
    legal entities, another bank's included, an `obligationIds` entry the register does not
    offer for it, or a `reasonDraftId` that is not a draft the caller was given in this bank,
    in which case nothing starts; `validation_error` (422) for an answer other
    than the two, an empty reason or one over 2000 characters, an empty selection, an
    obligation named twice, or more ids than `REGISTER_DECIDE_ALL_SELECTED_MAX`, 1000 by
    default.
    """
    state = decide_all.start(tenant=caller_tenant(request), user=caller_user(request), body=body)
    return 202, RegisterDecideAll.model_validate(state)


@router.get(
    "/applicability/decide-all",
    response=RegisterDecideAll,
    auth=SESSION,
    operation_id="readDecideAllApplicability",
    by_alias=True,
    summary="Read how far your Decide all run has come",
)
@requires_permission(perms.APPLICABILITY_APPROVE)
@answers_problems
def read_decide_all_applicability(request: HttpRequest) -> Any:
    """The caller's latest Decide all run in this bank as the worker last wrote it: how many
    obligations it lists, how many it has set, left alone and could not set, the first 20
    refusals with their reasons, and why it stopped if it stopped early. Call it every few
    seconds while `status` is `running`, and on opening the "What applies" page to pick up a
    run started earlier; read the lists again once it has finished. With no run in the last
    day it answers 200 with `status` `idle` and zero counts, never a 404.

    A read: it changes nothing and writes no audit row. Each person reads only their own run,
    in the bank they are signed in to, and the reason is never returned. A person's session
    holding `applicability.approve`.
    """
    return RegisterDecideAll.model_validate(decide_all.state_of(caller_tenant(request).id, caller_user(request).id))


# ---------------------------------------------------------------------------------------
# A reason drafted by AI (REG-01, D-143, ADR 0069; reason_draft.py)
# ---------------------------------------------------------------------------------------
@router.post(
    "/applicability/reason-draft",
    response=RegisterReasonDraft,
    auth=SESSION,
    operation_id="draftApplicabilityReason",
    by_alias=True,
    summary="Have AI draft the reason for an applicability answer from the licence facts",
)
@requires_permission(perms.APPLICABILITY_APPROVE)
@answers_problems
def draft_applicability_reason(request: HttpRequest, body: RegisterReasonDraftBody) -> Any:
    """Drafts one to three plain sentences saying why the chosen answer holds for one legal
    entity, for the "Does it apply" dialog to put in its reason field, labelled as an AI draft
    until the person sets the answer. Call it when the person asks for a draft; it changes
    nothing, so it writes no audit event. Send the returned `generationId` back as
    `reasonDraftId` with `PUT /obligations/{obligationId}/applicability` or
    `POST /applicability/decide-all`, and the draft's log row reads confirmed or edited.

    The obligations are those of the same filters as Decide all: the rows named in
    `obligationIds`, else those of `instrument`, or of every regulation, that nobody has
    answered. The server reads every fact itself, never from the request, and the model sees
    only these: the chosen answer, the reader's language (Swedish for a Swedish locale, else
    English), the legal entity's licence facts (each supervisor's register line with the scope
    terms it brings, the licences the bank recorded as type, authority, grant date and covered
    services, and the entity's type, terms as keys and labels) and the library's shared facts
    (each regulation's short name, official reference and regime, and up to
    `REGISTER_REASON_DRAFT_FACTS`, 20 by default, obligations' reference, title, summary and
    source, each text cut to `REGISTER_REASON_DRAFT_TEXT_MAX_CHARS`, 500 by default). Never the
    company's or the bank's name, people, what anyone typed, register answers, cases or
    comments. The draft is at most `REGISTER_REASON_DRAFT_MAX_TOKENS` tokens, 300 by default,
    and 2000 characters. Every call leaves one row in the AI log naming the person who asked.

    A person's session holding `applicability.approve`. No step-up: drafting sets nothing.

    Errors to branch on: `feature_off` (403) when the bank has switched its AI features off,
    before any model is asked; `not_found` (404) for an `orgUnitId` that is not one of the
    bank's active legal entities, another bank's included, or an `obligationIds` entry the
    register does not offer for it; `draft_refused` (422) when any of the obligations is the
    bank's own record or sits under a standard, neither of which ever reaches a model;
    `validation_error` (422) for an unknown answer, an empty selection, an obligation named
    twice, more ids than `REGISTER_DECIDE_ALL_SELECTED_MAX`, 1000 by default, or nothing left
    to decide; `model_unavailable` (503) when the model failed, timed out after
    `REGISTER_REASON_DRAFT_DEADLINE_MS`, 15000 by default, or wrote nothing, in which case the
    person writes the reason themselves; `rate_limited` (429) after
    `REGISTER_REASON_DRAFT_RATE_PER_USER_PER_MINUTE` drafts, 6 by default, in one minute by
    the same person. A draft confirms one decision only: its `generationId` sent again, with
    another answer or for another legal entity is `not_found` there.
    """
    tenant = caller_tenant(request)
    return reason_draft.draft(tenant=tenant, user=caller_user(request), order=language_order(request, tenant=tenant), body=body)


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

    Errors: `not_found` (404) for an obligation the bank cannot see; `validation_error`
    (422) for a page out of range.
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

    Errors: `not_found` (404) for an obligation or legal entity the bank cannot see;
    `does_not_apply` (409) when the obligation, or its answer for that legal entity, is
    "does not apply": a gap is a fact about how the bank complies with a rule that applies;
    `unknown_key` (422) for a severity, source or team key the bank's list does not hold;
    `unknown_member` (422) for an owner who is not an active member of the bank;
    `validation_error` (422) for a body the schema refuses or a person and a team as owner
    together; `unknown_unit` (422) for a `unitId` that is not a live unit under this
    obligation, or not of the legal entity the gap names. A gap on a unit is in the unit's
    legal entity, and fixes the unit's reference and title from then on.
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

    Errors: `validation_error` (422) for an owner or entity that is not a UUID, a date that
    is not a date, a key longer than 64 characters or a page out of range.
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

    Errors: `not_found` (404) for a gap the bank does not have; `stale_write` (409) for an
    `If-Match` that is absent or not the current version; `invalid_transition` (409) for a
    status the gap cannot move to here, or for a change to the title, description, plan,
    severity or target date of a gap whose risk was accepted (reopen it first; its owner may
    still change); `request_pending` (409) for such a change while a risk acceptance waits
    for approval, so the approver decides on the gap as it was asked for; `unknown_key`
    (422) for a key the bank's list does not hold; `unknown_member` (422) for an owner who
    is not an active member; `validation_error` (422) for a body the schema refuses or a
    person and a team as owner together.
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

    Errors: `not_found` (404) for a gap the bank does not have; `invalid_transition` (409)
    for a gap that is closed or already accepted; `request_pending` (409) when an acceptance
    is already waiting for approval; `unknown_key` (422) for a reason the bank's list does
    not hold, naming the keys it does; `validation_error` (422) for a body the schema
    refuses.
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

    Errors: `not_found` (404) for a gap the bank does not have; `four_eyes_violation` (409)
    when the caller asked for the acceptance, before anything is written;
    `invalid_transition` (409) when no acceptance is waiting.
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

    Errors: `not_found` (404) for a gap the bank does not have; `invalid_transition` (409)
    for a gap that is open or remediating.
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

    Errors: `not_found` (404) for an obligation the bank cannot see; `validation_error`
    (422) for a page out of range.
    """
    tenant = caller_tenant(request)
    return history.list_assessments(
        tenant=tenant,
        order=language_order(request, tenant=tenant),
        obligation_id=obligation_id,
        limit=page.limit,
        offset=page.offset,
    )


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

    Errors: `not_found` (404) for an obligation the bank cannot see; `validation_error`
    (422) for empty or over-long text.
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

    Errors: `not_found` (404) for an obligation the bank cannot see; `validation_error`
    (422) for a page out of range.
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

    Errors: `not_found` (404) for an obligation or internal item the bank cannot see;
    `already_linked` (409) when the item is already linked to this obligation;
    `duplicate_key` (409) when a new item's kind and name are taken, so pick that item
    instead; `unknown_key` (422) for a kind that is not an active row of the bank's link
    kind list; `validation_error` (422) for a url that is not a web address, a picked item
    of another kind, an item picked and described at once, or an owner who is not a member.
    """
    tenant = caller_tenant(request)
    return 201, links.add_link(
        tenant=tenant,
        actor=actor_for(request),
        order=language_order(request, tenant=tenant),
        obligation_id=obligation_id,
        body=body,
    )


@router.get(
    "/internal-items",
    response=RegisterInternalItemPage,
    auth=SESSION,
    operation_id="listInternalItems",
    by_alias=True,
    summary="Find one of your policies, procedures or controls to link",
)
@requires_permission(perms.REGISTER_READ)
@answers_problems
def list_internal_items(request: HttpRequest, filters: Query[RegisterInternalItemQuery], page: PageQuery = Query(...)) -> Any:
    """The bank's own active internal items, by name, each with its kind and reference, so the
    link dialog can pick one instead of creating it again. `q` narrows the list to the items
    whose name or reference holds it. Another bank's items are never listed.

    A person's session holding `register.read`. A read: it changes nothing and writes no
    audit event. Pages with `limit` and `offset`, 20 by default and 100 at most; nothing
    matching is a 200 with an empty page.

    Errors: `validation_error` (422) for a `q` longer than 300 characters or a page out of
    range.
    """
    tenant = caller_tenant(request)
    return links.list_items(order=language_order(request, tenant=tenant), query=filters.q, limit=page.limit, offset=page.offset)


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

    Errors: `not_found` (404) for a link the bank does not have or one already removed.
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

    Errors: `not_found` (404) for an obligation the bank cannot see; `validation_error`
    (422) for an entity that is not a UUID or a page out of range.
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

    Errors: `not_found` (404) for an obligation or entity the bank cannot see;
    `validation_error` (422) for an empty or over-long reference or title.
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

    Errors: `not_found` (404) for a unit the bank does not have; `validation_error` (422).
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

    Errors: `not_found` (404) for a unit the bank does not have.
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
    """Lists many units for one legal entity from pasted lines of reference and title, each
    optionally with its applicability and reason. With `dryRun` true, the default, it answers
    what each line would become and stores nothing; show that to the person and ask them to
    confirm. With `dryRun` false it creates every unit and sets every answer the lines carry
    in one transaction, only when no line is refused: all of it is stored or none. A commit
    with a refused line answers like a dry run and stores nothing.

    A person's session holding `register.edit`, and `applicability.approve` as well when any
    line carries an answer (D-75). At most `REGISTER_BULK_MAX` lines, 100 by default. No
    step-up. A commit records one audit event per unit naming the person, and one per answer
    naming the person, the value before and after, and the reason.

    Errors: `permission_denied` (403) without `register.edit`, or without
    `applicability.approve` for a line with an answer; `not_found` (404) for an obligation
    or entity the bank cannot see; `units_only_under_standards` (422) under an obligation
    that is not a standard's; `scope_not_applicable` (422) for an entity that does not
    follow the standard; `duplicate_key` (409) when another write listed a reference first;
    `validation_error` (422) for no lines, too many lines, an unknown answer or a line
    longer than the paste allows.
    """
    tenant = caller_tenant(request)
    return units.paste_units(
        tenant=tenant,
        actor=actor_for(request),
        order=language_order(request, tenant=tenant),
        obligation_id=obligation_id,
        body=body,
        may_decide=principal(request).has_permission(perms.APPLICABILITY_APPROVE),
    )


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
    with its own assessed status, and each live unit with its reference, the bank's title, its
    applicability and reason, its status, who set it and when, and its history of answers.
    No status is computed from the units.

    A person's session holding `register.read`. A read. `entity` is required. Units page with
    `limit` and `offset`, 20 by default and 100 at most, by reference.

    Errors: `not_found` (404) for an obligation or entity the bank cannot see, or a standard
    outside the bank's regulatory scope, which hides the statement and deletes nothing;
    `units_only_under_standards` (422) for an obligation that is not a standard's;
    `scope_not_applicable` (422) for an entity that does not follow the standard;
    `validation_error` (422) without `entity` or with a page out of range.
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

    Errors: `not_found` (404) for an obligation the bank cannot see; `validation_error`
    (422) for a page out of range. A read writes nothing: a duty whose obligation does not
    yet apply to the bank has a null next occurrence.
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

    Errors: `not_found` (404) for an occurrence the bank does not have; `validation_error`
    (422) for a note over the limit.
    """
    return duties.complete_occurrence(
        tenant=caller_tenant(request), actor=actor_for(request), occurrence_id=occurrence_id, body=body
    )


# ---------------------------------------------------------------------------------------
# acc-register-read: the register as the bank's own agents read it (ACC-04, ACC-08, D-76)
# ---------------------------------------------------------------------------------------
KEY = ApiKeyAuth()


@router.get(
    "/register-entries",
    response=RegisterDecisionPage,
    auth=KEY,
    operation_id="listRegisterEntries",
    by_alias=True,
    summary="Read your bank's register decisions as its own agent",
)
@requires_scope(perms.SCOPE_TENANT_READ)
def list_register_entries(request: HttpRequest, page: PageQuery = Query(...)) -> Any:
    """The bank's settled decisions on every obligation in the entry's scope that it has a
    register entry for, by the obligation's stable key: applicability and its reason,
    compliance status and note, how the bank reads the rule, owner, process, system, next
    review, a row per legal entity and the internal items linked now. Never a gap, case,
    assessment, comment, evidence or its location, risk rating or audit row, and never the
    bank's own private obligations or one under a standard.

    A key of an agent access entry, or a personal access token naming one, holding
    `tenant:read`, and only while both the bank's tenant reach and the entry's own toggle
    are on. A person's session is not accepted here: a person reads
    `GET /obligations/{obligationId}/register`. A read: it writes nothing. Pages with `limit`
    and `offset`, 20 by default and 100 at most; an entry whose scope holds no decision is a
    200 with an empty page.

    Errors: `unauthenticated` (401) without a live key or token, or with a session;
    `permission_denied` (403) for a credential without `tenant:read` or bound to no entry,
    which never holds it; `tenant_reach_off` (403) while the bank's tenant reach or the
    entry's own toggle is off; `read_only_credential` (403) for any write; `rate_limited`
    (429) over the credential's rate; `validation_error` (422) for a page out of range.
    """
    tenant = caller_tenant(request)
    return agent_read.list_decisions(
        tenant=tenant, principal=principal(request), order=language_order(request, tenant=tenant), limit=page.limit, offset=page.offset
    )


@router.get(
    "/register-entries/{obligation_id}",
    response=RegisterDecision,
    auth=KEY,
    operation_id="readRegisterEntry",
    by_alias=True,
    summary="Read your bank's decisions on one obligation as its own agent",
)
@requires_scope(perms.SCOPE_TENANT_READ)
def read_register_entry(request: HttpRequest, obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID)) -> Any:
    """The bank's settled decisions on one obligation, in the same shape as a row of
    `GET /register-entries`. An obligation in the entry's scope that nobody has decided on
    reads as not yet decided, with no entities and no items.

    A key of an agent access entry, or a personal access token naming one, holding
    `tenant:read`, and only while both the bank's tenant reach and the entry's own toggle
    are on. A person's session is not accepted here: a person reads
    `GET /obligations/{obligationId}/register`. A read: it writes nothing.

    Errors: `unauthenticated` (401) without a live key or token, or with a session;
    `permission_denied` (403) for a credential without `tenant:read` or bound to no entry,
    which never holds it; `tenant_reach_off` (403) while the bank's tenant reach or the
    entry's own toggle is off; `read_only_credential` (403) for any write; `rate_limited`
    (429) over the credential's rate; `not_found` (404) for an obligation outside the entry's
    scope, a private obligation, one under a standard or one that does not exist, alike.
    """
    tenant = caller_tenant(request)
    return agent_read.read_decision(
        tenant=tenant, principal=principal(request), order=language_order(request, tenant=tenant), obligation_id=obligation_id
    )
