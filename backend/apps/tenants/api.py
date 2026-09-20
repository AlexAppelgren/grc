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
    """The bank's profile: its name, short name, time zone, languages, and how far its setting-up
    has got. Needs no permission beyond a session, since the whole shell is built from it. A
    platform session, which is inside no bank, answers 404 `not_found`."""
    # Ungated by design: capability (any member of the tenant).
    return TenantOut.model_validate(logic.tenant_out(logic.get_tenant(_principal(request).tenant_id)))


@router.patch("/tenant", response=TenantOut, auth=SessionAuth(), operation_id="updateTenant", by_alias=True)
@requires_permission(perms.SECURITY_MANAGE)
def update_tenant(request: HttpRequest, body: TenantPatch) -> TenantOut:
    """Changes the bank's name, time zone, default language or the languages it keeps its own
    content in. Needs `security.manage`. An empty name answers 422 `name_required`, an unknown
    time zone or language 422 `unknown_key`, and an empty language list 422
    `languages_required`. The time zone is what decides where the bank's deadlines fall."""
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
    """bleqq's last way back in for a bank that has lost every administrator (ID-05): it puts one
    named member back on a one-time code. Needs `support_access.grant` and a fresh passkey check
    (403 `step_up_required`), and the caller has to write down why and how the person was
    verified away from the product, or the answer is 422 `check_required`. A bank or member that
    does not exist answers 404 `not_found`. Every use is audited and shows in the bank's own
    security log."""
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
    """Every bank on the platform, in order of their short name, for bleqq's own console. Needs `tenants.manage`.
    It carries the tenant row and nothing under it: no member counts and no bank content,
    because a platform session reads no bank's records."""
    tenants, total = logic.console_tenants(limit=page.limit, offset=page.offset)
    return ConsoleTenantPage(items=[ConsoleTenantRow.model_validate(logic.console_tenant_row(tenant)) for tenant in tenants], total=total)


@router.post("/console/tenants", response={201: ConsoleTenantRow}, auth=SessionAuth(), operation_id="createConsoleTenant", by_alias=True)
@requires_permission(perms.TENANTS_MANAGE)
def create_console_tenant(request: HttpRequest, body: ConsoleTenantCreateBody) -> tuple[int, ConsoleTenantRow]:
    """Creates a bank and invites its first administrator in one action, which is how every
    customer starts. Needs `tenants.manage`. A short name already taken answers 409
    `duplicate_key`, a malformed one 422 `invalid_slug`, an empty name 422 `name_required`, and
    an unknown language or time zone 422 `unknown_key`. An address belonging to platform staff
    answers 422 `platform_account`: the first administrator is always somebody at the bank."""
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
