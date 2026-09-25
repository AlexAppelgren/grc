"""Routes of the governance app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1)."""

import uuid
from typing import Annotated, Any, cast

from django.http import HttpRequest
from ninja import Path, Query, Router

from apps.governance import ai_log, logic, problem_reports_logic, reach
from apps.governance.models import TenantReachRequest
from apps.governance.schemas import (
    AiGenerationPage,
    AiGenerationQuery,
    AuditEventPage,
    AuditEventQuery,
    ProblemReportClose,
    ProblemReportPage,
    ProblemReportQuery,
    ProblemReportRow,
    TenantReachRequestRow,
    TenantReachView,
)
from apps.shared import permissions as perms
from apps.shared.authentication import Principal, SessionAuth
from apps.shared.permissions import requires_permission, requires_step_up
from apps.shared.schemas import PageQuery
from apps.taxonomy.http import actor_for, answers_problems, caller_tenant, caller_user, if_match, uuid_or_404
from apps.taxonomy.reading import language_order

router = Router(tags=["Governance"])


@router.get(
    "/audit-events",
    response=AuditEventPage,
    auth=SessionAuth(),
    operation_id="listAuditEvents",
    by_alias=True,
    summary="See who changed what in the bank, when, and what it looked like before and after",
)
@requires_permission(perms.AUDIT_READ)
def list_audit_events(request: HttpRequest, filters: Query[AuditEventQuery], page: PageQuery = Query(...)) -> AuditEventPage:
    """The bank's audit log, newest first: every change made in this bank by a person, an
    agent or the system, with the record it touched as it was titled at the time, a
    one-line summary, the record's fields before and after, and whether a passkey step-up
    confirmed it. Call it to answer an auditor's “who did this, when, and what did it
    change”, to show one record's history beside the record (`subjectType` and
    `subjectId`), or to list everything one person or agent did (`actorId`).

    The log also carries the changes to the shared library that reach every bank: a change
    to an authority, instrument, provision, obligation, vocabulary or taxonomy term made by
    an agent, the system or bleqq's platform staff. It never carries another bank's rows,
    which are kept out by row-level security in the database and by the query itself. Of
    the rows that belong to no bank, only those library changes appear: never the review
    queue's decision on a proposal (its approval or rejection), and never a platform
    sign-in or code request, which can name a person from another bank. A proposal this
    bank made does appear, as `proposal.created`, and as `proposal.replayed` when a retried
    submission was answered with the proposal it had already made.

    Append-only: a row is written in the same transaction as the change it records and is
    never updated, so a correction is a new row and never an edit of an old one. This call
    is a read: it changes nothing and writes no audit row of its own. A person's session
    holding `audit.read`, which every role seeded for a bank carries; an agent's key is not
    accepted.

    Pages with `limit` and `offset`, 20 rows by default and 100 at most. A bank with no
    rows, or filters matching none, is a 200 with an empty `items` and a `total` of 0.

    Errors: `unauthenticated` (401) without a session, an agent's key included;
    `permission_denied` (403) without `audit.read`, with `requiredPermission` named, which
    is also what a platform console session gets, since no platform role holds
    `audit.read`; `not_found` (404) for a session that holds `audit.read` but belongs to
    no bank, because the audit log is a bank's own; `validation_error` (422) when
    `subjectId` or `actorId` is not a UUID, `from` or `to` is not a timestamp,
    `subjectType` is longer than 64 characters, or `limit` or `offset` is out of range.
    """
    tenant_id = cast(Principal, request.auth).tenant_id  # type: ignore[attr-defined]
    events, total = logic.audit_events(tenant_id, filters, limit=page.limit, offset=page.offset)
    return AuditEventPage(items=[logic.audit_row(event) for event in events], total=total)


@router.get(
    "/ai-generations",
    response=AiGenerationPage,
    auth=SessionAuth(),
    operation_id="listAiGenerations",
    by_alias=True,
    summary="See what a model wrote, which model wrote it and whether anybody has stood behind it",
)
@requires_permission(perms.AI_LOG_READ)
def list_ai_generations(
    request: HttpRequest, filters: Query[AiGenerationQuery], page: PageQuery = Query(...)
) -> Any:
    """Every model call this bank can see, newest first: the drafted “So what?” of
    each regulatory change, and this bank's own Ask answers once Ask ships. Call it to
    answer “what has a machine written for us, about what, and has anybody checked
    it” — the question an auditor asks and the one AUD-02 exists to answer.

    A read: it changes nothing and writes no audit row. A person's session holding
    `ai_log.read`, which the administrator, compliance officer, approver and auditor roles
    carry. What a bank sees is its own rows plus the shared library's, except a confirming
    agent's decisions on the proposal queue, which only the platform reads. Another bank's
    rows and those decisions are kept out by row-level security in the database rather than
    by a filter here, so no query written later can widen it.

    **The model and the version are not always bleqq's own measurement.** For a
    “So what?” the agent that read the change files the words together with the
    change and reports which model and which version produced them, so those two fields are
    that agent's account of itself rather than something bleqq observed (D-66).
    `modelMetadataReportedByAgent` says which rows are which. In R1 every agent is bleqq's
    own, so this is a reporting boundary; it becomes a trust boundary the day a bank runs
    its own agent against the write routes, which is the agent-access work in R2.

    Call it with `subjectId` to list every call about one record, such as each drafted
    “So what?” of one change. Each row carries its review state, who stood behind it
    and when, and, on an Ask answer, the reader's verdict and note. A shared “So
    what?” is one row every bank reads and none may move, so its review state here is this
    bank's own, computed from this bank's case for the change; another bank's confirmation
    never shows, and reading it writes nothing.

    Pages with `limit` and `offset`, 20 rows by default and 100 at most. A bank with no
    rows, or a filter matching none, is a 200 with an empty `items` and a `total` of 0.
    Errors: `unauthenticated` (401) without a session; `permission_denied` (403) without
    `ai_log.read`, with `requiredPermission` named; `validation_error` (422) when
    `subjectId` is not a UUID, `purpose` is longer than 32 characters, `status` longer than
    16, or `limit` or `offset` is out of range.
    """
    tenant_id = cast(Principal, request.auth).tenant_id  # type: ignore[attr-defined]
    rows, total = ai_log.generations_for(tenant_id=tenant_id, filters=filters, limit=page.limit, offset=page.offset)
    return AiGenerationPage(items=[ai_log.generation_row(row, tenant_id) for row in rows], total=total)


# ---------------------------------------------------------------------------------------
# Problem reports (AUD-03, D-50): read and closed inside the bank that filed them
# ---------------------------------------------------------------------------------------
_REPORTS_REACH = (
    "Who sees what: a member holding `proposals.create` (the compliance officer) reaches "
    "every report of their own bank; every other member reaches only the reports they "
    "filed. Both need `problems.report`, which every member of a bank holds and no platform "
    "role does, so bleqq's own staff are refused. Another bank's report is never reached: "
    "row-level security in the database hides it, so it reads as not found. A report is "
    "the bank's own content, and neither its text nor a closing note reaches the audit "
    "log, an outbox event, a log line or a model."
)


@router.get(
    "/problem-reports",
    response=ProblemReportPage,
    auth=SessionAuth(),
    operation_id="listProblemReports",
    by_alias=True,
    summary="See what your colleagues reported as looking wrong in the library, and how each report was closed",
    description=(
        "The bank's “this looks wrong” reports on library records, newest first: what was "
        "reported, on which record, by whom, and, once closed, who closed it, when and why. "
        "Call it to work the bank's open reports (`status=open`), or to show the reports on "
        "one record beside it (`subjectType` with `subjectId`).\n\n"
        f"{_REPORTS_REACH}\n\n"
        "A read: it changes nothing and writes no audit row. Pages with `limit` and `offset`, "
        "20 rows by default and 100 at most. No report, or filters matching none, is a 200 "
        "with an empty `items` and a `total` of 0.\n\n"
        "Errors: `unauthenticated` (401) without a session, an agent's key included; "
        "`permission_denied` (403) without `problems.report`, with `requiredPermission` "
        "named, which is what a platform console session gets; `not_found` (404) for a "
        "session in no bank; `validation_error` (422) when `subjectId` is not a UUID, a "
        "filter is too long, or `limit` or `offset` is out of range."
    ),
)
@requires_permission(perms.PROBLEMS_REPORT)
@answers_problems
def list_problem_reports(
    request: HttpRequest, filters: Query[ProblemReportQuery], page: PageQuery = Query(...)
) -> Any:
    principal = cast(Principal, request.auth)  # type: ignore[attr-defined]
    rows, total = problem_reports_logic.reports_for(
        principal, filters, language_order(request), limit=page.limit, offset=page.offset
    )
    return ProblemReportPage(items=rows, total=total)


@router.patch(
    "/problem-reports/{report_id}",
    response=ProblemReportRow,
    auth=SessionAuth(),
    operation_id="closeProblemReport",
    by_alias=True,
    summary="Close a problem report with a note saying what you found",
    description=(
        "Close one of the bank's problem reports as `answered`, `fixed` or `rejected`, with "
        "a note for the reporter. The reporter closes their own; a colleague holding "
        "`proposals.create` closes any of the bank's. A report closes once, and nothing but "
        "its state, the note, who closed it and when is ever written: the reporter's words, "
        "the record it names and the bank it belongs to never change. Closing a report does "
        "not change the library: a wrong record is corrected through the watch agents' "
        "re-check and a proposal. The reporter is not notified; they see the close on the "
        "report.\n\n"
        f"{_REPORTS_REACH}\n\n"
        "Records `problem_report.closed` in the audit log, with the states before and after "
        "and never the words, and emits the outbox event of the same name. No passkey "
        "step-up and no second person: the close changes nothing outside the report. "
        "Answers the closed report.\n\n"
        "Errors: `unauthenticated` (401) without a session, an agent's key included; "
        "`permission_denied` (403) without `problems.report`, or on a colleague's report "
        "without `proposals.create`, with `requiredPermission` naming the one missing; "
        "`not_found` (404) for an id this bank has no report under; `already_closed` (409) "
        "for a report that is closed already; `validation_error` (422) for a status other "
        "than the three or a note that is missing, too long or holding a NUL character, and "
        "`note_required` (422) for a note that is only whitespace; `rate_limited` (429) when "
        "this person has closed 30 reports in the last hour "
        "(`PROBLEM_REPORTS_PER_USER_PER_HOUR`), to wait out and retry."
    ),
)
@requires_permission(perms.PROBLEMS_REPORT)
@answers_problems
def close_problem_report(
    request: HttpRequest,
    report_id: Annotated[uuid.UUID, Path(description="The id of the report to close, a UUID as `GET /problem-reports` lists it; a value that is not a UUID is refused with `validation_error` (422).")],
    body: ProblemReportClose,
) -> Any:
    closer = caller_user(request)
    return problem_reports_logic.close(
        cast(Principal, request.auth),  # type: ignore[attr-defined]
        report_id,
        body,
        closer=closer,
        actor=actor_for(request, closer),
        order=language_order(request),
    )


# ---------------------------------------------------------------------------------------
# Tenant reach (acc-scope-and-reach; ACC-08, D-72, ADR 0057): two people switch it on, one
# switches it off, and every write carries a passkey step-up
# ---------------------------------------------------------------------------------------
_REACH_WHAT = (
    "Tenant reach decides whether the bank's own register decisions may reach the agents the "
    "bank runs itself. It is off for every bank until two different people holding "
    "`security.manage` switch it on: one requests it, the other approves it, each with a "
    "passkey. With it off, every agent access entry reads the shared library only, whatever "
    "the entry's own setting says."
)
_REACH_GATE = (
    "Needs `security.manage` in the caller's bank and a passkey step-up younger than the "
    "configured freshness window (`POST /auth/step-up/options`, then `POST /auth/step-up/verify`); "
    "an API key or a personal access token is refused, because neither can step up."
)
_REACH_GATE_ERRORS = (
    "`step_up_required` (403) without a fresh passkey step-up; `permission_denied` (403) "
    "without `security.manage`, with `requiredPermission` named; `unauthenticated` (401) "
    "without a session; `not_found` (404) for a principal in no bank"
)
_ReachRequestId = Annotated[
    str,
    Path(
        description=(
            "The id of the tenant reach request, a UUID as `GET /tenant/reach` shows it under "
            "`pending`. Anything else, or a request of another bank, answers `not_found` (404)."
        )
    ),
]


def _reach_request(tenant: Any, request_id: str) -> TenantReachRequest:
    found = (
        TenantReachRequest.objects.filter(tenant=tenant, pk=uuid_or_404(request_id))
        .select_related("requested_by", "decided_by")
        .first()  # ordering: pk lookup, at most one row
    )
    if found is None:
        from django.core.exceptions import ValidationError

        raise ValidationError("That request for tenant reach is not here.", code="not_found")
    return found


@router.get(
    "/tenant/reach",
    response=TenantReachView,
    auth=SessionAuth(),
    operation_id="getTenantReach",
    by_alias=True,
    summary="See whether our register may reach the agents we run ourselves",
    description=(
        f"{_REACH_WHAT}\n\n"
        "Answers whether reach is on, who last switched it and when, and the request waiting "
        "for a second person, if one does. A bank that never asked is a 200 with `enabled` "
        "false and nothing pending.\n\n"
        "A read: it changes nothing and writes no audit row. Needs `security.manage` in the "
        "caller's bank and a person's session; an API key is refused.\n\n"
        "Errors: `permission_denied` (403) without `security.manage`, with `requiredPermission` "
        "named; `unauthenticated` (401) without a session; `not_found` (404) for a principal in "
        "no bank."
    ),
)
@requires_permission(perms.SECURITY_MANAGE)
def get_tenant_reach(request: HttpRequest) -> TenantReachView:
    return reach.view(caller_tenant(request).id)


@router.post(
    "/tenant/reach/requests",
    response={201: TenantReachRequestRow},
    auth=SessionAuth(),
    operation_id="requestTenantReach",
    by_alias=True,
    summary="Ask for our register to reach the agents we run ourselves",
    description=(
        f"{_REACH_WHAT}\n\n"
        "Makes the request a second person decides; nothing reaches any agent yet. A bank has "
        "one pending request at a time, and none while reach is already on. Answers 201 with the "
        "pending request. Takes no body.\n\n"
        f"{_REACH_GATE} Records `tenant_reach.requested` in the audit log, naming the requester "
        "and the passkey assertion.\n\n"
        "Errors: `request_pending` (409) when a request already waits for a decision; "
        f"`invalid_transition` (409) when reach is already on; {_REACH_GATE_ERRORS}."
    ),
)
@requires_permission(perms.SECURITY_MANAGE)
@requires_step_up
@answers_problems
def request_tenant_reach(request: HttpRequest) -> Any:
    tenant = caller_tenant(request)
    user = caller_user(request)
    created = reach.request_reach(
        tenant=tenant,
        requester=user,
        actor=actor_for(request, user),
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
    )
    return 201, reach.request_row(created)


@router.post(
    "/tenant/reach/requests/{request_id}/approve",
    response=TenantReachRequestRow,
    auth=SessionAuth(),
    operation_id="approveTenantReach",
    by_alias=True,
    summary="Approve tenant reach as the second person",
    description=(
        f"{_REACH_WHAT}\n\n"
        "Approves a pending request: reach is on at once, for every agent access entry whose own "
        "toggle is on. The approver must be someone other than the requester, which the database "
        "enforces too. Answers the request, now `approved`. Takes no body; send `If-Match` with "
        "the version last read to be told when the request moved on.\n\n"
        f"{_REACH_GATE} Records `tenant_reach.approved` in the audit log, naming the approver, the "
        "requester and the passkey assertion.\n\n"
        "Errors: `four_eyes_violation` (409) when the requester approves their own request; "
        "`invalid_transition` (409) when it was already decided; `stale_write` (409) when "
        "`If-Match` names an old version; `validation_error` (422) for an `If-Match` that is not "
        f"a version; `not_found` (404) for a request that is not here; {_REACH_GATE_ERRORS}."
    ),
)
@requires_permission(perms.SECURITY_MANAGE)
@requires_step_up
@answers_problems
def approve_tenant_reach(request: HttpRequest, request_id: _ReachRequestId) -> Any:
    tenant = caller_tenant(request)
    user = caller_user(request)
    decided = reach.approve(
        tenant=tenant,
        request=_reach_request(tenant, request_id),
        decider=user,
        actor=actor_for(request, user),
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
        expected_version=if_match(request),
    )
    return reach.request_row(decided)


@router.post(
    "/tenant/reach/requests/{request_id}/reject",
    response=TenantReachRequestRow,
    auth=SessionAuth(),
    operation_id="rejectTenantReach",
    by_alias=True,
    summary="Turn down a request for tenant reach",
    description=(
        f"{_REACH_WHAT}\n\n"
        "Rejects a pending request: reach stays off and the request is final. The person "
        "rejecting must be someone other than the requester. Answers the request, now "
        "`rejected`. Takes no body; send `If-Match` with the version last read to be told when "
        "the request moved on.\n\n"
        f"{_REACH_GATE} Records `tenant_reach.rejected` in the audit log, naming the person, the "
        "requester and the passkey assertion.\n\n"
        "Errors: `four_eyes_violation` (409) when the requester rejects their own request; "
        "`invalid_transition` (409) when it was already decided; `stale_write` (409) when "
        "`If-Match` names an old version; `validation_error` (422) for an `If-Match` that is not "
        f"a version; `not_found` (404) for a request that is not here; {_REACH_GATE_ERRORS}."
    ),
)
@requires_permission(perms.SECURITY_MANAGE)
@requires_step_up
@answers_problems
def reject_tenant_reach(request: HttpRequest, request_id: _ReachRequestId) -> Any:
    tenant = caller_tenant(request)
    user = caller_user(request)
    decided = reach.reject(
        tenant=tenant,
        request=_reach_request(tenant, request_id),
        decider=user,
        actor=actor_for(request, user),
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
        expected_version=if_match(request),
    )
    return reach.request_row(decided)


@router.post(
    "/tenant/reach/off",
    response=TenantReachView,
    auth=SessionAuth(),
    operation_id="switchOffTenantReach",
    by_alias=True,
    summary="Switch tenant reach off for every agent at once",
    description=(
        f"{_REACH_WHAT}\n\n"
        "Switches reach off from the next read, for every agent access entry at once, whatever "
        "each entry's own toggle says. One person is enough: turning egress off never needs a "
        "second. Switching it on again takes a new request and a second person. Answers the "
        "reach state, now off. Takes no body.\n\n"
        f"{_REACH_GATE} Records `tenant_reach.switched_off` in the audit log, naming the person "
        "and the passkey assertion.\n\n"
        f"Errors: `invalid_transition` (409) when reach is already off; {_REACH_GATE_ERRORS}."
    ),
)
@requires_permission(perms.SECURITY_MANAGE)
@requires_step_up
@answers_problems
def switch_off_tenant_reach(request: HttpRequest) -> Any:
    tenant = caller_tenant(request)
    user = caller_user(request)
    reach.switch_off(
        tenant=tenant,
        user=user,
        actor=actor_for(request, user),
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
    )
    return reach.view(tenant.id)
