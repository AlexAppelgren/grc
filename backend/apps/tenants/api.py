"""Routes of the tenants app (playbook 4.1): the tenant profile (TEN-01), the platform
console's tenants (ADM-02) and its last-admin recovery (ID-05, ID-S13). No business logic
here."""

import uuid
from typing import cast

from django.http import HttpRequest
from ninja import Query, Router

from apps.identity.models import User
from apps.identity.schemas import Empty
from apps.identity.session_logic import actor_of
from apps.shared import permissions as perms
from apps.shared.authentication import Principal, SessionAuth
from apps.shared.permissions import requires_permission, requires_step_up
from apps.shared.schemas import PageQuery
from apps.tenants import logic
from apps.tenants.schemas import (
    ConsoleReissueBody,
    ConsoleTenantCreateBody,
    ConsoleTenantPage,
    ConsoleTenantRow,
    TenantOut,
    TenantPatch,
)

router = Router(tags=["Tenants"])


def _principal(request: HttpRequest) -> Principal:
    return cast(Principal, request.auth)  # type: ignore[attr-defined]


@router.get("/tenant", response=TenantOut, auth=SessionAuth(), operation_id="getTenant", by_alias=True)
def get_tenant(request: HttpRequest) -> TenantOut:
    # Ungated by design: capability (any member of the tenant).
    return TenantOut.model_validate(logic.tenant_out(logic.get_tenant(_principal(request).tenant_id)))


@router.patch("/tenant", response=TenantOut, auth=SessionAuth(), operation_id="updateTenant", by_alias=True)
@requires_permission(perms.SECURITY_MANAGE)
def update_tenant(request: HttpRequest, body: TenantPatch) -> TenantOut:
    principal = _principal(request)
    tenant = logic.update_tenant(
        tenant=logic.get_tenant(principal.tenant_id),
        actor=actor_of(User.objects.get(pk=principal.subject_id)),
        name=body.name,
        timezone_name=body.timezone,
        default_language=body.default_language,
        content_language_keys=body.content_languages,
    )
    return TenantOut.model_validate(logic.tenant_out(tenant))


@router.post(
    "/console/tenants/{tenant_id}/members/{user_id}/reissue-enrolment",
    response={202: Empty},
    auth=SessionAuth(),
    operation_id="consoleReissueEnrolment",
    by_alias=True,
)
@requires_permission(perms.SUPPORT_ACCESS_GRANT)
@requires_step_up
def console_reissue_enrolment(request: HttpRequest, tenant_id: uuid.UUID, user_id: uuid.UUID, body: ConsoleReissueBody) -> tuple[int, Empty]:
    platform_user = User.objects.get(pk=_principal(request).subject_id)
    logic.console_reissue_enrolment(
        tenant_id=tenant_id,
        user_id=user_id,
        platform_user=platform_user,
        actor=actor_of(platform_user),
        reason=body.reason,
        ticket_ref=body.ticket_ref,
        out_of_band_check=body.out_of_band_check,
        request=request,
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
    )
    return 202, Empty()


# ---------------------------------------------------------------------------------------
# Console: the tenants (ADM-02). Creation invites the first administrator in the same
# transaction; no step-up, as on the tenant-side invite (playbook 4.2).
# ---------------------------------------------------------------------------------------
@router.get("/console/tenants", response=ConsoleTenantPage, auth=SessionAuth(), operation_id="listConsoleTenants", by_alias=True)
@requires_permission(perms.TENANTS_MANAGE)
def list_console_tenants(request: HttpRequest, page: PageQuery = Query(...)) -> ConsoleTenantPage:
    tenants, total = logic.console_tenants(limit=page.limit, offset=page.offset)
    return ConsoleTenantPage(items=[ConsoleTenantRow.model_validate(logic.console_tenant_row(tenant)) for tenant in tenants], total=total)


@router.post("/console/tenants", response={201: ConsoleTenantRow}, auth=SessionAuth(), operation_id="createConsoleTenant", by_alias=True)
@requires_permission(perms.TENANTS_MANAGE)
def create_console_tenant(request: HttpRequest, body: ConsoleTenantCreateBody) -> tuple[int, ConsoleTenantRow]:
    platform_user = User.objects.get(pk=_principal(request).subject_id)
    tenant = logic.create_tenant(
        actor=actor_of(platform_user),
        name=body.name,
        slug=body.slug,
        timezone_name=body.timezone,
        default_language=body.default_language,
        content_language_keys=body.content_languages,
        first_admin_email=body.first_admin_email,
        first_admin_title=body.first_admin_title,
    )
    return 201, ConsoleTenantRow.model_validate(logic.console_tenant_row(tenant))
