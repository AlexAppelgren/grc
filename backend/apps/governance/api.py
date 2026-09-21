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


@router.get("/audit-events", response=AuditEventPage, auth=SessionAuth(), operation_id="listAuditEvents", by_alias=True)
@requires_permission(perms.AUDIT_READ)
def list_audit_events(request: HttpRequest, filters: Query[AuditEventQuery], page: PageQuery = Query(...)) -> AuditEventPage:
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
    carry. What a bank sees is its own rows plus the shared library's; another bank's rows
    are kept out by row-level security in the database rather than by a filter here, so no
    query written later can widen it.

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
