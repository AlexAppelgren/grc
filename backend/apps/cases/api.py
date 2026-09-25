"""Routes of the cases app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1).

Chunk 5 declares the two things a bank does with a case in R1: it says what a change means
for it, and it decides which of the suggested obligation links are real for it. Both are
the bank's own judgement, both are written by a person with `cases.work` in their own bank,
and neither touches a library row (WAT-04, WAT-05, ruling C).

Every route is addressed by the library change's id, not by the case's: a bank has exactly
one case per change (CAS-01), so the change is the address a screen already has and the
case is resolved from the caller's own tenant. A change nobody has a case for answers 404,
and so does a change another bank has a case for, because a case is never addressed across
tenants.

No step-up and no `If-Match` here: sign-off and the case's own version arrive with the rest
of the workflow in chunk 9. The rest of CAS-02 to CAS-08 — triage, dismissal, assessment,
actions, evidence, sign-off and the case file — is not declared here at all.
"""

import uuid

from django.http import HttpRequest
from ninja import Path, Router
from typing import Any

from apps.cases import links, so_what
from apps.cases.schemas import CasesObligationLink, CasesObligationLinkBody, CasesSoWhat, CasesSoWhatBody
from apps.shared import permissions as perms
from apps.shared.authentication import SessionAuth
from apps.shared.permissions import requires_permission
from apps.taxonomy.http import actor_for, answers_problems, caller_tenant, caller_user
from apps.taxonomy.reading import language_order

router = Router(tags=["Cases"])

SESSION = SessionAuth()

# What each path parameter means to a caller, hoisted out of the signatures so a route
# body stays one line of gate, schema and call (playbook 4.1).
_CHANGE_ID = (
    "The library change whose case this is, as a UUID. A bank has exactly one case per "
    "change (CAS-01), so the change is the address and the case is resolved from the "
    "caller's own tenant. Another bank's case is never reachable from here."
)
_OBLIGATION_ID = (
    "The obligation whose link decision to remove from this bank's case, as a UUID. It "
    "removes the bank's own decision row and never the library's link."
)


# ---------------------------------------------------------------------------------------
# The bank's own "So what?" (WAT-05)
# ---------------------------------------------------------------------------------------
@router.put(
    "/changes/{change_id}/so-what",
    response=CasesSoWhat,
    auth=SESSION,
    operation_id="saveSoWhat",
    by_alias=True,
    summary="Say in your own words what a change means for your bank",
)
@requires_permission(perms.CASES_WORK)
@answers_problems
def save_so_what(
    request: HttpRequest, body: CasesSoWhatBody, change_id: uuid.UUID = Path(..., description=_CHANGE_ID)
) -> Any:
    """Replaces the AI draft on this bank's case with the bank's own wording, at most 4000
    characters. Call it when the drafted "So what?" is wrong, incomplete or written for
    somebody else's business; call `POST /changes/{changeId}/so-what/confirm` instead when
    the draft is right as it stands.

    A person's session holding `cases.work` in their own bank. It writes one column of that
    bank's case and nothing else: no library row moves, and another bank reading the same
    change still sees its own copy, still an AI draft. Saving marks the wording confirmed and
    names the person and the time, because somebody who rewrote it has already decided. The
    text is tenant content: it stays in the bank's zone and never reaches a log, Sentry or a
    model endpoint. The save is recorded in the audit log with the person named.

    No `If-Match` and no step-up: the case carries no version in R1, so the last save wins
    until the case workflow lands. Errors: `not_found` when no change has that id or this
    bank has no case for it; `permission_denied` without `cases.work`; `unauthenticated`
    without a session; `validation_error` for empty text or text over the cap.
    """
    tenant = caller_tenant(request)
    return so_what.save_so_what(
        tenant=tenant, actor=actor_for(request), user=caller_user(request), change_id=change_id, text=body.text
    )


@router.post(
    "/changes/{change_id}/so-what/confirm",
    response=CasesSoWhat,
    auth=SESSION,
    operation_id="confirmSoWhat",
    by_alias=True,
    summary="Confirm the drafted wording as your bank's own",
)
@requires_permission(perms.CASES_WORK)
@answers_problems
def confirm_so_what(
    request: HttpRequest, change_id: uuid.UUID = Path(..., description=_CHANGE_ID)
) -> Any:
    """Accepts the AI draft on this bank's case as it stands, so the screen stops labelling
    it "AI draft" and the case file can quote it as the bank's position. Call it when the
    drafted "So what?" is right; use `PUT /changes/{changeId}/so-what` when it needs
    rewriting.

    A person's session holding `cases.work` in their own bank. It changes the confirmation
    on that bank's case and not the text: the words stay the model's, now stood behind by a
    named person at a named time, which is what keeps AI output labelled until somebody
    confirms it (WAT-05). No library row moves, and another bank's copy is untouched. The
    confirmation is recorded in the audit log with the person named.

    No request body, no `If-Match` and no step-up. Errors: `not_found` when no change has
    that id, this bank has no case for it, or the case holds no draft to confirm;
    `permission_denied` without `cases.work`; `unauthenticated` without a session.
    """
    tenant = caller_tenant(request)
    return so_what.confirm_so_what(
        tenant=tenant, actor=actor_for(request), user=caller_user(request), change_id=change_id
    )


# ---------------------------------------------------------------------------------------
# The bank's own decision about a suggested obligation link (WAT-04)
# ---------------------------------------------------------------------------------------
@router.post(
    "/changes/{change_id}/case/obligation-links",
    response={201: CasesObligationLink},
    auth=SESSION,
    operation_id="acceptCaseObligationLink",
    by_alias=True,
    summary="Confirm that a suggested obligation really is affected for your bank",
)
@requires_permission(perms.CASES_WORK)
@answers_problems
def accept_case_obligation_link(
    request: HttpRequest,
    body: CasesObligationLinkBody,
    change_id: uuid.UUID = Path(..., description=_CHANGE_ID),
) -> Any:
    """Records, on this bank's own case, that one of the obligations an agent or a library
    editor linked to the change really is affected here, so the case works it. Call it from
    the "Obligations affected" panel; call the matching `DELETE` when the link is not
    relevant to this bank.

    A person's session holding `cases.work` in their own bank. It writes one row in that
    bank's zone and changes no library row: the shared link, its origin and its confidence
    stay exactly as they were, a library editor's confirmation is a separate decision, and
    another bank still sees the link undecided. One decision per obligation per case, so
    accepting one already accepted is not a second row. The decision is recorded in the audit
    log with the person named.

    Answers 201 with the stored decision. No `If-Match` and no step-up. Errors: `not_found`
    when no change has that id, this bank has no case for it, or the obligation is not one
    the caller may see; `permission_denied` without `cases.work`; `unauthenticated` without a
    session; `validation_error` for a body the schema refuses.
    """
    tenant = caller_tenant(request)
    return links.accept_obligation_link(
        tenant=tenant,
        actor=actor_for(request),
        user=caller_user(request),
        order=language_order(request, tenant=tenant),
        change_id=change_id,
        obligation_id=body.obligation_id,
    )


@router.delete(
    "/changes/{change_id}/case/obligation-links/{obligation_id}",
    response=CasesObligationLink,
    auth=SESSION,
    operation_id="removeCaseObligationLink",
    by_alias=True,
    summary="Say that a suggested obligation is not related to your bank",
)
@requires_permission(perms.CASES_WORK)
@answers_problems
def remove_case_obligation_link(
    request: HttpRequest,
    change_id: uuid.UUID = Path(..., description=_CHANGE_ID),
    obligation_id: uuid.UUID = Path(..., description=_OBLIGATION_ID),
) -> Any:
    """Records, on this bank's own case, that a suggested obligation link is not related
    here, so the change page stops showing it. Call it from the "Obligations affected" panel
    when a link an agent proposed does not apply to this bank's business.

    A person's session holding `cases.work` in their own bank. Despite the method, nothing is
    deleted: the decision is stored as `removed`, so the case file can say the bank looked at
    the link and said no, and the same call can be reversed by accepting it again. No library
    row moves — the shared link stays, still there for every other bank — and an obligation
    removed here is not an obligation that does not apply, which is a separate fact in the
    register (REG-01). The decision is recorded in the audit log with the person named.

    Answers 200 with the stored decision. No `If-Match` and no step-up. Errors: `not_found`
    when no change has that id, this bank has no case for it, or the obligation is not one
    the caller may see; `permission_denied` without `cases.work`; `unauthenticated` without a
    session.

    """
    tenant = caller_tenant(request)
    return links.remove_obligation_link(
        tenant=tenant,
        actor=actor_for(request),
        user=caller_user(request),
        order=language_order(request, tenant=tenant),
        change_id=change_id,
        obligation_id=obligation_id,
    )
