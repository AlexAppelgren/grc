"""Routes of the cases app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1).

Chunk 5 declares the two things a bank does with a case in R1: it says what a change means
for it, and it decides which of the suggested obligation links are real for it. Both are
the bank's own judgement, both are written by a person with `cases.work` in their own bank,
and neither touches a library row (WAT-04, WAT-05, ruling C).

Every route is addressed by the library change's id, not by the case's (an action and a
piece of evidence by their own ids, each loaded with its case): a bank has exactly
one case per change (CAS-01), so the change is the address a screen already has and the
case is resolved from the caller's own tenant. A change nobody has a case for answers 404,
and so does a change another bank has a case for, because a case is never addressed across
tenants.

The chunk 5 routes take neither `If-Match` nor a step-up. Saving or confirming the "So what?" still raises the
case's `version`, so a screen holding an older copy of the case is told on its next
workflow write.

Chunk 9 declares the rest of the workflow (CAS-02 to CAS-08) below, every operation behind
its final gate: triage, dismissal, restore, the assessment, the one-person close, actions,
evidence, sign-off and the case file. Each route sends its call to the module that builds
it (`triage.py`, `assessment.py`, `actions.py`, `evidence.py`, `signoff.py`,
`case_file.py`), which loads the caller's case first and answers 501 `not_built` until its
logic lands. Every write that moves a case or changes its assessment reads `If-Match`; only
the sign-off approval takes a step-up (playbook 4.2). No route here takes an API key,
whatever its scopes: a case is a bank's judgement (AGT-01).
"""

import uuid
from inspect import cleandoc

from django.http import HttpRequest, HttpResponse
from ninja import File, Form, Path, Query, Router, UploadedFile
from typing import Any

from apps.cases import actions, assessment, case_file, evidence, links, signoff, so_what, triage
from apps.cases.schemas import (
    CasesAction,
    CasesActionBody,
    CasesActionPage,
    CasesActionPatch,
    CasesAssessmentBody,
    CasesCase,
    CasesCloseBody,
    CasesEvidenceCreated,
    CasesEvidenceForm,
    CasesEvidencePage,
    CasesNoteBody,
    CasesObligationLink,
    CasesObligationLinkBody,
    CasesReasonBody,
    CasesSoWhat,
    CasesSoWhatBody,
    CasesTriageBody,
)
from apps.shared import permissions as perms
from apps.shared.authentication import SessionAuth
from apps.shared.permissions import requires_permission, requires_step_up
from apps.shared.schemas import PageQuery
from apps.taxonomy.http import actor_for, answers_problems, caller_tenant, caller_user, if_match, principal
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

    No `If-Match` and no step-up: the last save wins. The save still raises the case's
    `version`, so a workflow write made from an older copy of the case is refused with
    `stale_write` and reloads. Errors: `not_found` when no change has that id or this
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

    No request body, no `If-Match` and no step-up; the confirmation still raises the case's
    `version`, like a save. Errors: `not_found` when no change has
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


# =======================================================================================
# The case workflow (CAS-02 to CAS-08, chunk 9)
# =======================================================================================
# The text every description here shares, so the eighteen operations say the same thing
# the same way (API_DOCUMENTATION §4b).
_ACTION_ID = (
    "The action, as a UUID. It is loaded with its case in the caller's own bank, so an action "
    "of another bank, and one already removed, answer 404."
)
_EVIDENCE_ID = (
    "The piece of evidence, as a UUID. It is loaded with its case in the caller's own bank, so "
    "evidence of another bank, and a piece already removed, answer 404."
)
_FILE_PART = (
    "The evidence's bytes, as the `file` part of the multipart form: required when `kind` is "
    "`file` and refused for the other kinds. Checked for its type and size before a byte is "
    "stored, hashed with SHA-256, kept privately and scanned for malware before it can be "
    "downloaded. Tenant content: its contents never reach a log, the audit values or a model."
)
_AHEAD = "Published ahead of the logic that will fill it, and answering 501 `not_built` until that ships."
_IF_MATCH = (
    "Send the case's `version` in `If-Match`: without it, or with an older one, the write is "
    "refused with 409 `stale_write` carrying `currentVersion`, and nothing changes."
)
_CASE_ERRORS = (
    "`not_found` when no change has that id, this bank has no case for it, or the case is "
    "another bank's; `permission_denied` without the permission above, naming it in "
    "`requiredPermission`; `unauthenticated` without a session, including any API key"
)
_MOVE_ERRORS = (
    "`invalid_transition` when the case is not in a category this move leaves from; "
    "`stale_write` for a missing or old `If-Match`"
)
_CASE_FILE_EXAMPLE = {
    "responses": {
        200: {
            "description": "The case file, as UTF-8 plain text.",
            "content": {
                "text/plain": {
                    "schema": {"type": "string"},
                    "example": (
                        "Case file: FI adopts amended rules on paying for investment research\n"
                        "Status: closed (signed off)\nOwner: Sara Lind\n"
                        "Signed off by Johan Berg on 2026-10-02, requested by Sara Lind on 2026-10-01\n"
                    ),
                }
            },
        }
    }
}
_DOWNLOAD_EXAMPLE = {
    "responses": {
        200: {
            "description": "The file's bytes, as an attachment of the type the server identified.",
            "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}, "example": "%PDF-1.7 …"}},
        }
    }
}
_EVIDENCE_FORM_EXAMPLE = {
    "requestBody": {
        "content": {
            "multipart/form-data": {
                "example": {"kind": "link", "name": "FI decision memo", "url": "https://intranet.example.com/memo/42"}
            }
        }
    }
}


def _stated(request: HttpRequest) -> dict[str, Any]:
    """Who is writing, in which bank, and the case version they read."""
    return {
        "tenant": caller_tenant(request),
        "actor": actor_for(request),
        "user": caller_user(request),
        "expected_version": if_match(request),
    }


def _stated_in_language(request: HttpRequest) -> dict[str, Any]:
    """As `_stated`, with the reader's language order for the case's labels."""
    stated = _stated(request)
    stated["order"] = language_order(request, tenant=stated["tenant"])
    return stated


# ---------------------------------------------------------------------------------------
# Triage, dismissal and restore (CAS-02)
# ---------------------------------------------------------------------------------------
@router.post(
    "/changes/{change_id}/triage",
    response=CasesCase,
    auth=SESSION,
    operation_id="triageChange",
    by_alias=True,
    description=cleandoc(
        """Moves this bank's case from `new` to `assigned`: the urgency becomes the bank's own
        decision rather than the agent's suggestion, and the named owner takes the case on. Call
        it from the triage panel of a change that needs triage.

        A person's session holding `cases.triage` in their own bank. It writes that bank's case,
        one row in the case's transition ledger and one audit row naming the person, and notifies the owner.
        No library row moves. An optional `subStatus` places the case inside `assigned`.
        """ + _IF_MATCH + """

        Errors: """ + _CASE_ERRORS + """; """ + _MOVE_ERRORS + """; `owner_required` when the
        owner named is not an active member of this bank whose roles hold `cases.work`;
        `unknown_key` for an urgency or sub-status key the lists do not hold, with the valid
        keys in `validKeys`; `validation_error` for a body the schema refuses, including a
        missing `ownerId`, which the error names."""
    ),
    summary="Decide how urgent a change is for your bank and who owns it",
)
@requires_permission(perms.CASES_TRIAGE)
@answers_problems
def triage_change(request: HttpRequest, body: CasesTriageBody, change_id: uuid.UUID = Path(..., description=_CHANGE_ID)) -> Any:
    return triage.triage_change(**_stated_in_language(request), change_id=change_id, body=body)


@router.post(
    "/changes/{change_id}/dismiss",
    response=CasesCase,
    auth=SESSION,
    operation_id="dismissChange",
    by_alias=True,
    description=cleandoc(
        """Moves this bank's case from `new` to `dismissed` with a reason from the bank's own
        dismissal reasons. Call it when the change does not concern the bank; the case stays and
        can be restored with `POST /changes/{changeId}/restore`.

        A person's session holding `cases.triage` in their own bank. It writes that bank's case,
        one row in the case's transition ledger and one audit row naming the person and the reason's key. A
        dismissal says the bank looked and decided; it never says an obligation does not apply,
        which is a separate fact in the register. """ + _IF_MATCH + """

        Errors: """ + _CASE_ERRORS + """; """ + _MOVE_ERRORS + """; `reason_required` when no
        reason is given; `unknown_key` for a reason key the list does not hold, with the valid
        keys in `validKeys`; `validation_error` for a body the schema refuses."""
    ),
    summary="Set a change aside as not relevant to your bank, with a reason",
)
@requires_permission(perms.CASES_TRIAGE)
@answers_problems
def dismiss_change(request: HttpRequest, body: CasesReasonBody, change_id: uuid.UUID = Path(..., description=_CHANGE_ID)) -> Any:
    return triage.dismiss_change(**_stated_in_language(request), change_id=change_id, body=body)


@router.post(
    "/changes/{change_id}/restore",
    response=CasesCase,
    auth=SESSION,
    operation_id="restoreChange",
    by_alias=True,
    description=cleandoc(
        """Moves a dismissed case, or one a single person closed without action, back to `new`
        so it is triaged again. Call it when a dismissal or a one-person close was wrong. A case
        a second person signed off stays closed.

        A person's session holding `cases.triage` in their own bank. No request body. It writes
        that bank's case, one row in the case's transition ledger and one audit row naming the person; the
        earlier decision stays in the case's history. """ + _IF_MATCH + """

        Errors: """ + _CASE_ERRORS + """; """ + _MOVE_ERRORS + """, including a case that was
        signed off."""
    ),
    summary="Bring a dismissed change back to triage",
)
@requires_permission(perms.CASES_TRIAGE)
@answers_problems
def restore_change(request: HttpRequest, change_id: uuid.UUID = Path(..., description=_CHANGE_ID)) -> Any:
    return triage.restore_change(**_stated_in_language(request), change_id=change_id)


# ---------------------------------------------------------------------------------------
# The impact assessment and the one-person close (CAS-03, D-92)
# ---------------------------------------------------------------------------------------
@router.post(
    "/changes/{change_id}/assessment/start",
    response=CasesCase,
    auth=SESSION,
    operation_id="startAssessment",
    by_alias=True,
    description=cleandoc(
        """Moves this bank's case from `assigned` to `assessing` and opens an empty impact
        assessment. Call it when the owner begins the assessment; saving it is
        `PUT /changes/{changeId}/assessment`.

        A person's session holding `cases.work` in their own bank. No request body. It writes
        that bank's case and its assessment, one row in the case's transition ledger and one audit row naming
        the person. """ + _IF_MATCH + """

        Errors: """ + _CASE_ERRORS + """; """ + _MOVE_ERRORS + """."""
    ),
    summary="Start working out what a change means for your bank",
)
@requires_permission(perms.CASES_WORK)
@answers_problems
def start_assessment(request: HttpRequest, change_id: uuid.UUID = Path(..., description=_CHANGE_ID)) -> Any:
    return assessment.start_assessment(**_stated_in_language(request), change_id=change_id)


@router.put(
    "/changes/{change_id}/assessment",
    response=CasesCase,
    auth=SESSION,
    operation_id="saveAssessment",
    by_alias=True,
    description=cleandoc(
        """Replaces the case's impact assessment with the one sent: whether the change applies,
        why, what must change, the bank's own deadline and the effort. Call it from the
        assessment panel of a case being assessed or implemented. Saving moves the case to no
        other category; adding the first action does that.

        A person's session holding `cases.contribute` in their own bank. It writes that bank's
        assessment and one audit row naming the person, never the texts, which are tenant
        content and never reach a log or a model. `applies: no` closes a case being assessed on
        this one person's word, with the bank's close reason of the "not_applicable" kind, and
        only for a person who also holds `cases.work` (D-92); the close writes one row in the
        case's transition ledger and can be undone with `POST /changes/{changeId}/restore`. An
        optional `subStatus` places the case inside the category it is in after the save.
        """ + _IF_MATCH + """

        Errors: """ + _CASE_ERRORS + """; `permission_denied` naming `cases.work` in
        `requiredPermission` for `applies: no` without it; `invalid_transition` when the case is
        not being assessed or implemented, or for `applies: no` on a case being implemented;
        `stale_write` for a missing or old `If-Match`, which is what the second of two people
        saving the same version gets, and nothing is merged; `unknown_key` for an effort or
        sub-status key the lists do not hold, or a sub-status of another category, with the
        valid keys in `validKeys`; `validation_error` for a body the schema refuses, including
        an empty `why`."""
    ),
    summary="Save whether a change applies to your bank, why, and what must change",
)
@requires_permission(perms.CASES_CONTRIBUTE)
@answers_problems
def save_assessment(request: HttpRequest, body: CasesAssessmentBody, change_id: uuid.UUID = Path(..., description=_CHANGE_ID)) -> Any:
    may_close = principal(request).has_permission(perms.CASES_WORK)
    return assessment.save_assessment(**_stated_in_language(request), change_id=change_id, body=body, may_close=may_close)


@router.post(
    "/changes/{change_id}/close",
    response=CasesCase,
    auth=SESSION,
    operation_id="closeWithoutAction",
    by_alias=True,
    description=cleandoc(
        """Closes an assigned or assessing case on one person's word, with a close reason whose
        kind is "no_action" or "not_applicable" (D-92). Call it when the change applies but
        nothing has to change, or the assessment found it does not apply. A case that needed
        work is closed by a second person through sign-off instead.

        A person's session holding `cases.work` in their own bank. It writes that bank's case,
        one row in the case's transition ledger carrying the note, and one audit row naming the person and the
        reason's key, never the note. The close can be undone with
        `POST /changes/{changeId}/restore`. """ + _IF_MATCH + """

        Errors: """ + _CASE_ERRORS + """; """ + _MOVE_ERRORS + """, including a case waiting for
        sign-off, which only a second person closes; `four_eyes_violation` for a reason of the
        "signed_off" kind, which needs a second person; `reason_required` when no reason is
        given; `unknown_key` for a reason key the list does not hold, with the valid keys in
        `validKeys`; `validation_error` for a body the schema refuses."""
    ),
    summary="Close a case that needs no work, with a reason",
)
@requires_permission(perms.CASES_WORK)
@answers_problems
def close_without_action(request: HttpRequest, body: CasesCloseBody, change_id: uuid.UUID = Path(..., description=_CHANGE_ID)) -> Any:
    return triage.close_without_action(**_stated_in_language(request), change_id=change_id, body=body)


# ---------------------------------------------------------------------------------------
# Actions (CAS-04)
# ---------------------------------------------------------------------------------------
@router.get(
    "/changes/{change_id}/actions",
    response=CasesActionPage,
    auth=SESSION,
    operation_id="listActions",
    by_alias=True,
    description=cleandoc(
        """One page of the case's live actions, earliest due date first, each with its owner, due
        date and whether it is done. Call it for the actions panel.

        A read: it changes nothing and writes no audit row. A person's session holding
        `cases.read` in their own bank. A removed action is not listed; it stays in the case
        file. A case with no actions answers 200 with an empty page.

        Errors: """ + _CASE_ERRORS + """; `validation_error` for a page size or offset outside
        its limits."""
    ),
    summary="See what must be done for a case, and by whom",
)
@requires_permission(perms.CASES_READ)
@answers_problems
def list_actions(request: HttpRequest, page: Query[PageQuery], change_id: uuid.UUID = Path(..., description=_CHANGE_ID)) -> Any:
    return actions.list_actions(tenant=caller_tenant(request), change_id=change_id, page=page)


@router.post(
    "/changes/{change_id}/actions",
    response={201: CasesAction},
    auth=SESSION,
    operation_id="addAction",
    by_alias=True,
    description=cleandoc(
        """Adds an action to the case. The first action added to an assessing case moves it to
        `implementing`, which needs the assessment's `why` saved; an implementing case takes more.
        Without an `ownerId` the case's owner owns the action. Actions cannot be added while the
        case waits for sign-off or once it is closed.

        A person's session holding `cases.work` in their own bank. It writes one action and one
        audit row naming the person, and a row in the case's transition ledger when the case moves. Answers
        201 with the stored action. """ + _IF_MATCH + """

        Errors: """ + _CASE_ERRORS + """; """ + _MOVE_ERRORS + """ (actions are added in
        `assessing` and `implementing` only); `actions_locked` (409) while the case waits for
        sign-off or once it is closed; `too_many_actions` (409) when the case already holds its
        maximum of live actions, 200 by default (`CASE_ACTIONS_MAX`); `why_required` (422) when
        the move to implementing finds no saved `why`; `unknown_member` (422) for an owner who is
        not an active member of this bank; `validation_error` for a body the schema refuses."""
    ),
    summary="Add something that must be done for a case, with an owner and a due date",
)
@requires_permission(perms.CASES_WORK)
@answers_problems
def add_action(request: HttpRequest, body: CasesActionBody, change_id: uuid.UUID = Path(..., description=_CHANGE_ID)) -> Any:
    return actions.add_action(**_stated(request), change_id=change_id, body=body)


@router.patch(
    "/actions/{action_id}",
    response=CasesAction,
    auth=SESSION,
    operation_id="updateAction",
    by_alias=True,
    description=cleandoc(
        """Changes the fields sent and leaves the rest: the title, the owner, the due date, or
        `done` to complete or reopen it. Call it from the actions panel. Actions cannot be
        changed while the case waits for sign-off or once it is closed.

        A person's session holding `cases.contribute` in their own bank. It writes the action and
        one audit row naming the person. Send the action's own `version` in `If-Match`: without
        it, or with an older one, the write is refused with 409 `stale_write`.

        Errors: `not_found` when no live action of this bank has that id; `permission_denied`
        without `cases.contribute`; `unauthenticated` without a session, including any API key;
        `stale_write` for a missing or old `If-Match`; `actions_locked` (409) while the case waits
        for sign-off or once it is closed; `invalid_transition` (409) while the case is not being
        worked; `unknown_member` (422) for an owner who is not an active member of this bank;
        `validation_error` for a body the schema refuses."""
    ),
    summary="Change, complete or reopen an action",
)
@requires_permission(perms.CASES_CONTRIBUTE)
@answers_problems
def update_action(request: HttpRequest, body: CasesActionPatch, action_id: uuid.UUID = Path(..., description=_ACTION_ID)) -> Any:
    return actions.update_action(**_stated(request), action_id=action_id, body=body)


@router.delete(
    "/actions/{action_id}",
    response={204: None},
    auth=SESSION,
    operation_id="deleteAction",
    by_alias=True,
    description=cleandoc(
        """Removes an action from the case's work. Despite the method nothing is deleted: the
        action is marked removed with the person and the time, drops out of the list and the open
        count, and stays in the case file and the audit trail. Actions cannot be removed while the
        case waits for sign-off or once it is closed.

        A person's session holding `cases.work` in their own bank. No request body. It writes the
        action and one audit row naming the person, and answers 204 with no content. Send the
        action's own `version` in `If-Match`: without it, or with an older one, the removal is
        refused with 409 `stale_write`.

        Errors: `not_found` when no live action of this bank has that id; `permission_denied`
        without `cases.work`; `unauthenticated` without a session, including any API key;
        `stale_write` for a missing or old `If-Match`; `actions_locked` (409) while the case waits
        for sign-off or once it is closed; `invalid_transition` (409) while the case is not being
        worked."""
    ),
    summary="Remove an action that is no longer needed",
)
@requires_permission(perms.CASES_WORK)
@answers_problems
def delete_action(request: HttpRequest, action_id: uuid.UUID = Path(..., description=_ACTION_ID)) -> Any:
    return actions.delete_action(**_stated(request), action_id=action_id)


# ---------------------------------------------------------------------------------------
# Evidence (CAS-05, D-11, D-101)
# ---------------------------------------------------------------------------------------
@router.get(
    "/changes/{change_id}/evidence",
    response=CasesEvidencePage,
    auth=SESSION,
    operation_id="listEvidence",
    by_alias=True,
    description=cleandoc(
        """One page of the case's live evidence, newest first, each with its kind, its hash and
        where the malware scan stands. Call it for the evidence panel.

        A read: it changes nothing and writes no audit row. A person's session holding
        `cases.read` in their own bank. Removed evidence is not listed; it stays in the case file
        with its hash. A case with no evidence answers 200 with an empty page.

        Errors: """ + _CASE_ERRORS + """; `validation_error` for a page size or offset outside
        its limits. """ + _AHEAD
    ),
    summary="See the evidence attached to a case, and whether each file passed the scan",
)
@requires_permission(perms.CASES_READ)
@answers_problems
def list_evidence(request: HttpRequest, page: Query[PageQuery], change_id: uuid.UUID = Path(..., description=_CHANGE_ID)) -> Any:
    return evidence.list_evidence(tenant=caller_tenant(request), change_id=change_id, page=page)


@router.post(
    "/changes/{change_id}/evidence",
    response={201: CasesEvidenceCreated},
    auth=SESSION,
    operation_id="addEvidence",
    by_alias=True,
    description=cleandoc(
        """Attaches evidence to the case, sent as `multipart/form-data`: the fields `kind`,
        `name` and `url`, and for a file the bytes in the `file` part. There is no separate upload
        address: the server checks the file's type and size before storing a byte, hashes it,
        stores it privately and queues the malware scan before it answers, and the file cannot be
        downloaded until the scan passes.

        A person's session holding `cases.contribute` in their own bank. It writes one evidence
        row and one audit row naming the person and the file's hash, never its contents. Answers
        201 with the stored evidence, a file `pending` its scan. Evidence can be added in every
        open category; sign-off counts only clean evidence.

        Errors: """ + _CASE_ERRORS + """; `validation_error` for fields the schema refuses, a
        file part missing for `file` or sent for another kind, a file type outside the allowed
        list or a file over the size limit — each refused before anything is stored. When the
        malware scanner is unavailable the request is refused with 503 and nothing is stored.
        """ + _AHEAD
    ),
    summary="Attach a file, a link or a reference to a case as evidence",
    openapi_extra=_EVIDENCE_FORM_EXAMPLE,
)
@requires_permission(perms.CASES_CONTRIBUTE)
@answers_problems
def add_evidence(
    request: HttpRequest,
    form: Form[CasesEvidenceForm],
    file: File[UploadedFile] | None = File(None, description=_FILE_PART),
    change_id: uuid.UUID = Path(..., description=_CHANGE_ID),
) -> Any:
    return evidence.add_evidence(
        tenant=caller_tenant(request), actor=actor_for(request), user=caller_user(request), change_id=change_id, form=form, file=file
    )


@router.get(
    "/evidence/{evidence_id}/download",
    response={200: None},
    auth=SESSION,
    operation_id="downloadEvidence",
    by_alias=True,
    description=cleandoc(
        """Streams the bytes of a file that passed the malware scan, as an attachment of its
        stored type and marked `no-store`. There is no presigned address: every download passes
        this permission check (D-11).

        A person's session holding `cases.read` in their own bank, which every role holds, so a
        reader and an auditor download like everyone else. Every download writes one audit row
        naming the person and the evidence. A file whose scan is still running is refused with
        409, one that failed the scan with 422, and a link or a reference has no bytes to download.

        Errors: `not_found` when no live evidence of this bank has that id; `permission_denied`
        without `cases.read`; `unauthenticated` without a session, including any API key. """ + _AHEAD
    ),
    summary="Download a file attached to a case as evidence",
    openapi_extra=_DOWNLOAD_EXAMPLE,
)
@requires_permission(perms.CASES_READ)
@answers_problems
def download_evidence(request: HttpRequest, evidence_id: uuid.UUID = Path(..., description=_EVIDENCE_ID)) -> Any:
    return evidence.download_evidence(
        tenant=caller_tenant(request), actor=actor_for(request), user=caller_user(request), evidence_id=evidence_id
    )


@router.delete(
    "/evidence/{evidence_id}",
    response={204: None},
    auth=SESSION,
    operation_id="removeEvidence",
    by_alias=True,
    description=cleandoc(
        """Removes a piece of evidence from the case's work. Despite the method nothing is
        deleted: the row is marked removed and keeps its name and hash for the case file and the
        audit trail, and it no longer counts towards sign-off.

        A person's session holding `cases.work` in their own bank. No request body. It writes the
        evidence row and one audit row naming the person, and answers 204 with no content.

        Errors: `not_found` when no live evidence of this bank has that id; `permission_denied`
        without `cases.work`; `unauthenticated` without a session, including any API key. """ + _AHEAD
    ),
    summary="Remove a piece of evidence from a case",
)
@requires_permission(perms.CASES_WORK)
@answers_problems
def remove_evidence(request: HttpRequest, evidence_id: uuid.UUID = Path(..., description=_EVIDENCE_ID)) -> Any:
    return evidence.remove_evidence(
        tenant=caller_tenant(request), actor=actor_for(request), user=caller_user(request), evidence_id=evidence_id
    )


# ---------------------------------------------------------------------------------------
# Sign-off (CAS-06)
# ---------------------------------------------------------------------------------------
@router.post(
    "/changes/{change_id}/signoff/request",
    response=CasesCase,
    auth=SESSION,
    operation_id="requestSignoff",
    by_alias=True,
    description=cleandoc(
        """Moves an implementing case to `signoff`, naming the caller as the requester, and
        notifies the people who may sign off. Call it when every action is done and the evidence
        is attached; `canRequestSignoff` on the case says whether it will be accepted. The
        actions are locked while the case waits.

        A person's session holding `cases.work` in their own bank. No request body. It writes
        that bank's case, one row in the case's transition ledger and one audit row naming the person. The
        requester can never be the person who signs off. """ + _IF_MATCH + """

        Errors: """ + _CASE_ERRORS + """; """ + _MOVE_ERRORS + """; `open_actions` while an
        action is not done; `evidence_missing` without at least one piece of evidence that passed
        the scan. """ + _AHEAD
    ),
    summary="Ask a second person to sign off a case",
)
@requires_permission(perms.CASES_WORK)
@answers_problems
def request_signoff(request: HttpRequest, change_id: uuid.UUID = Path(..., description=_CHANGE_ID)) -> Any:
    return signoff.request_signoff(**_stated_in_language(request), change_id=change_id)


@router.post(
    "/changes/{change_id}/signoff/approve",
    response=CasesCase,
    auth=SESSION,
    operation_id="approveSignoff",
    by_alias=True,
    description=cleandoc(
        """Closes a case waiting for sign-off with the close reason "signed_off", in the name of
        a second person. Call it from the sign-off panel after reading the case file.

        A person's session holding `cases.signoff` in their own bank, with a passkey assertion
        younger than the step-up window. It writes that bank's case, one row in the case's transition ledger
        carrying the note and one audit row naming the person and the step-up, never the note.
        The approver is never the requester: the state machine refuses it and the database's
        check constraint refuses it again. Signing off changes no inventory row and says nothing
        about whether the bank complies (REG-02). """ + _IF_MATCH + """

        Errors: """ + _CASE_ERRORS + """; `step_up_required` without a fresh passkey assertion,
        answered before anything is read; """ + _MOVE_ERRORS + """; `four_eyes_violation` when
        the caller asked for the sign-off themself; `validation_error` for a body the schema
        refuses. """ + _AHEAD
    ),
    summary="Sign off a case someone else worked, confirming with your passkey",
)
@requires_permission(perms.CASES_SIGNOFF)
@requires_step_up
@answers_problems
def approve_signoff(request: HttpRequest, body: CasesNoteBody, change_id: uuid.UUID = Path(..., description=_CHANGE_ID)) -> Any:
    return signoff.approve_signoff(
        **_stated_in_language(request), change_id=change_id, body=body, step_up_assertion_id=request.step_up_assertion_id  # type: ignore[attr-defined]
    )


@router.post(
    "/changes/{change_id}/signoff/send-back",
    response=CasesCase,
    auth=SESSION,
    operation_id="sendBackSignoff",
    by_alias=True,
    description=cleandoc(
        """Moves a case waiting for sign-off back to `implementing`, unlocking its actions, with
        the second person's note on what is missing. No step-up: sending back is the safe
        direction.

        A person's session holding `cases.signoff` in their own bank. It writes that bank's case,
        one row in the case's transition ledger carrying the note and one audit row naming the person, never
        the note. """ + _IF_MATCH + """

        Errors: """ + _CASE_ERRORS + """; """ + _MOVE_ERRORS + """; `validation_error` for a body
        the schema refuses. """ + _AHEAD
    ),
    summary="Send a case back for more work instead of signing it off",
)
@requires_permission(perms.CASES_SIGNOFF)
@answers_problems
def send_back_signoff(request: HttpRequest, body: CasesNoteBody, change_id: uuid.UUID = Path(..., description=_CHANGE_ID)) -> Any:
    return signoff.send_back_signoff(**_stated_in_language(request), change_id=change_id, body=body)


# ---------------------------------------------------------------------------------------
# The case file (CAS-07)
# ---------------------------------------------------------------------------------------
@router.get(
    "/changes/{change_id}/case-file",
    response={200: None},
    auth=SESSION,
    operation_id="getCaseFile",
    by_alias=True,
    description=cleandoc(
        """The case file as UTF-8 `text/plain`: the change, the bank's confirmed "So what?", the
        assessment, the actions with their completion, the evidence with hashes and scan states,
        both sign-off names and every date. It reads without the product beside it, for an
        auditor or a file. An unconfirmed AI draft is labelled as one, never presented as the
        bank's text.

        A person's session holding `cases.read` in their own bank. It changes nothing on the
        case. The same content as a downloadable file is an export job.

        Errors: """ + _CASE_ERRORS + """. """ + _AHEAD
    ),
    summary="Read a case's whole story as one text that stands alone",
    openapi_extra=_CASE_FILE_EXAMPLE,
)
@requires_permission(perms.CASES_READ)
@answers_problems
def get_case_file(request: HttpRequest, change_id: uuid.UUID = Path(..., description=_CHANGE_ID)) -> Any:
    tenant = caller_tenant(request)
    text = case_file.case_file(
        tenant=tenant,
        actor=actor_for(request),
        user=caller_user(request),
        order=language_order(request, tenant=tenant),
        change_id=change_id,
    )
    return HttpResponse(text, content_type="text/plain; charset=utf-8")
