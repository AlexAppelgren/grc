"""Routes of the governance app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1)."""

from typing import Any, cast

from django.http import HttpRequest
from ninja import Query, Router

from apps.governance import ai_log, logic
from apps.governance.schemas import (
    AiGenerationPage,
    AiGenerationQuery,
    AuditEventPage,
    AuditEventQuery,
)
from apps.shared import permissions as perms
from apps.shared.authentication import Principal, SessionAuth
from apps.shared.permissions import requires_permission
from apps.shared.schemas import PageQuery

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
