"""Routes of the governance app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1)."""

import uuid
from typing import Annotated, Any, cast

from django.http import HttpRequest
from ninja import Path, Query, Router

from apps.governance import ai_log, logic, problem_reports_logic
from apps.governance.schemas import (
    AiGenerationPage,
    AiGenerationQuery,
    AuditEventPage,
    AuditEventQuery,
    ProblemReportClose,
    ProblemReportPage,
    ProblemReportQuery,
    ProblemReportRow,
)
from apps.shared import permissions as perms
from apps.shared.authentication import Principal, SessionAuth
from apps.shared.permissions import requires_permission
from apps.shared.schemas import PageQuery
from apps.taxonomy.http import actor_for, answers_problems, caller_user
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

    Pages with `limit` and `offset`, 20 rows by default and 100 at most. A bank with no
    rows, or a filter matching none, is a 200 with an empty `items` and a `total` of 0.
    Errors: `permission_denied` without `ai_log.read`, with `requiredPermission` named;
    `unauthenticated` without a session.
    """
    rows, total = ai_log.generations_for(
        purpose=filters.purpose, status=filters.status, limit=page.limit, offset=page.offset
    )
    tenant_id = cast(Principal, request.auth).tenant_id  # type: ignore[attr-defined]
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
        "than the three or a note that is missing or too long, and `note_required` (422) for "
        "a note that is only whitespace."
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
