"""Routes of the governance app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1)."""

from typing import cast

from django.http import HttpRequest
from ninja import Query, Router

from apps.governance import logic
from apps.governance.schemas import AuditEventPage, AuditEventQuery
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
