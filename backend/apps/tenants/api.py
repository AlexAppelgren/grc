"""Routes of the tenants app (playbook 4.1): the tenant profile (TEN-01), the platform
console's tenants (ADM-02) and its last-admin recovery (ID-05, ID-S13). No business logic
here.

Each route's docstring is its published `description` (django-ninja reads it), so it is
written for an integrator at a bank who has never seen this codebase: when to call it,
what it changes, the permission or scope it needs, what it leaves in the audit log and
which RFC 9457 `code` to branch on. The standard is
`docs/plans/briefs/API_DOCUMENTATION.md`.
"""

import uuid
from typing import cast

from django.http import HttpRequest
from ninja import Path, Query, Router

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


@router.get(
    "/tenant",
    response=TenantOut,
    auth=SessionAuth(),
    operation_id="getTenant",
    by_alias=True,
    summary="Read your own bank's profile and setup progress",
)
def get_tenant(request: HttpRequest) -> TenantOut:
    """Returns the organisation the caller is signed in to: its name, short name, timezone,
    status, the language it reads and writes in first, the languages it keeps content in,
    and how far it has got through first-run setup. Call it when a screen opens and needs
    the bank's own settings, or to show an administrator what is left to configure.

    Any member of the bank may call it; beyond a session no permission is needed, and the
    answer is always that member's own organisation — there is no way to ask about another
    one, and nothing here is ever shared with another bank. It changes nothing and writes
    nothing to the audit log.

    Errors: `unauthenticated` when there is no session; `not_found` when the session
    belongs to no organisation, which is what a platform console session gets here.
    """
    # Ungated by design: capability (any member of the tenant).
    return TenantOut.model_validate(logic.tenant_out(logic.get_tenant(_principal(request).tenant_id)))


@router.patch(
    "/tenant",
    response=TenantOut,
    auth=SessionAuth(),
    operation_id="updateTenant",
    by_alias=True,
    summary="Change your bank's name, timezone or languages",
)
@requires_permission(perms.SECURITY_MANAGE)
def update_tenant(request: HttpRequest, body: TenantPatch) -> TenantOut:
    """Updates the organisation's own profile and returns it as it now stands. Send only
    the fields you are changing: an omitted field is left alone, and `contentLanguages`
    replaces the whole list rather than adding to it. Call it from the bank's settings
    screen once an administrator has edited the profile.

    Needs the `security.manage` permission, which the bank's administrator role carries; a
    member without it is refused. No passkey step-up is asked for, because this is the
    bank's own profile and not a security, footprint or export action. The change is
    recorded in the audit log as `tenant.updated` with the name, timezone, default
    language and content languages both before and after, so the edit is answerable years
    later. Nothing here leaves the bank.

    Errors: a 422 for a field the caller can fix — a blank name, an empty content-language
    list — each carrying its own `code` and a message to show; `unknown_key` for a
    timezone the IANA database does not hold or a language key that is not an active
    language row; `permission_denied` without `security.manage`; `unauthenticated`
    without a session.
    """
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
    summary="Send a bank's stranded administrator a fresh enrolment code",
    openapi_extra={
        # The key is the int 202, the same key `response={202: Empty}` registers under:
        # a string "202" here adds a second entry beside it, and the contract then has
        # two keys of two types in one dict, which a sorted dump refuses (VOC-S2).
        "responses": {
            202: {
                "content": {
                    "application/json": {
                        "examples": {
                            "accepted": {
                                "summary": "Accepted; the code goes out by email and is never returned here",
                                "value": {},
                            }
                        }
                    }
                }
            }
        }
    },
)
@requires_permission(perms.SUPPORT_ACCESS_GRANT)
@requires_step_up
def console_reissue_enrolment(
    request: HttpRequest,
    body: ConsoleReissueBody,
    tenant_id: uuid.UUID = Path(
        ...,
        description=(
            "The identifier of the bank being helped, the UUID the console's tenant list "
            "returns as `id`. A bank that does not exist answers `not_found`, and a bank that "
            "does grants the caller nothing beyond this single action."
        ),
    ),
    user_id: uuid.UUID = Path(
        ...,
        description=(
            "The identifier of the member whose enrolment is being re-issued, a UUID. It must "
            "be an active member of the bank named earlier in the path; somebody who belongs "
            "to another bank, or who has been deactivated, answers `not_found` without saying "
            "which of the two it was."
        ),
    ),
) -> tuple[int, Empty]:
    """The recovery of last resort. When a bank's only administrator has lost every passkey
    and nobody inside the bank can re-invite her, platform support uses this to send that
    person a fresh enrolment code by email. There is no self-service path to it and there
    is no password anywhere in the product, so this call is the whole of the fallback.

    Needs the platform permission `support_access.grant` and a fresh passkey step-up on
    the support engineer's own credential; without the assertion the call is refused. The
    body must say why the recovery is happening and how the person was proved to be who
    they claim away from this system. Both are required and a blank one is refused.

    What it writes, in one transaction: a support-access record in the bank's own zone,
    which the bank can read afterwards, naming the engineer, the reason, the ticket and the
    out-of-band check; an audit event `support_access.recorded` carrying the step-up
    assertion; and the re-issue itself, which revokes every session that person has open,
    retires every passkey they hold and puts them back to awaiting enrolment. Platform
    staff have no bypass: the support record is written first and the bank is opened only
    for this one action. The answer is 202 with an empty body — the code travels by email
    and is never returned here.

    Errors: a 422 when the reason or the out-of-band check is blank; `not_found` when the
    bank does not exist or the person is not an active member of it; `step_up_required`
    when no fresh passkey assertion accompanies the call; `permission_denied` without
    `support_access.grant`.
    """
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
@router.get(
    "/console/tenants",
    response=ConsoleTenantPage,
    auth=SessionAuth(),
    operation_id="listConsoleTenants",
    by_alias=True,
    summary="List the banks on the platform",
)
@requires_permission(perms.TENANTS_MANAGE)
def list_console_tenants(request: HttpRequest, page: PageQuery = Query(...)) -> ConsoleTenantPage:
    """Returns every organisation on the platform, one page at a time, ordered by short
    name. Call it from the platform console to find a bank before opening it, creating one
    or running a support action against it.

    Needs the platform permission `tenants.manage`, which only a platform administrator
    holds; no session inside a bank can reach it. What comes back is the tenant row and
    nothing underneath it — no members, no obligations, no cases, no counts — because a
    platform session reads a bank's identity and never its work. It changes nothing and
    writes nothing to the audit log. An empty list is a 200 with `total` 0, never an error.

    Errors: a 422 when `limit` is above 100 or `offset` beyond the accepted depth;
    `permission_denied` without `tenants.manage`; `unauthenticated` without a session.
    """
    tenants, total = logic.console_tenants(limit=page.limit, offset=page.offset)
    return ConsoleTenantPage(items=[ConsoleTenantRow.model_validate(logic.console_tenant_row(tenant)) for tenant in tenants], total=total)


@router.post(
    "/console/tenants",
    response={201: ConsoleTenantRow},
    auth=SessionAuth(),
    operation_id="createConsoleTenant",
    by_alias=True,
    summary="Open a new bank and invite its first administrator",
)
@requires_permission(perms.TENANTS_MANAGE)
def create_console_tenant(request: HttpRequest, body: ConsoleTenantCreateBody) -> tuple[int, ConsoleTenantRow]:
    """Creates an organisation and, in the same transaction, invites the person who will
    run it. Call it once per bank, when a new customer is being onboarded; there is no
    second step that turns the bank on.

    Needs the platform permission `tenants.manage`. One call writes the organisation with
    its name, short name, timezone and languages; gives it the system roles and the
    starting set of its own lists, which its administrator may extend afterwards; and
    sends the first administrator an enrolment invitation carrying the system role that
    can invite everyone else. That person receives a one-time code by email, which stops
    working the moment their first passkey exists; no password is ever created. The
    creation is recorded in the audit log as `tenant.created` with the whole profile, and
    the invitation is recorded against the new bank. If anything in the call is refused,
    nothing at all is written.

    The address must belong to the bank. Platform staff are separate accounts, and an
    address that already carries a platform role is refused, because a console account
    invited into a bank would carry the console's permissions into a bank session.

    Answers 201 with the new bank's console row. Errors: `duplicate_key` when the short
    name is already taken; `unknown_key` for a timezone the IANA database does not hold or
    a language key that is not an active language row; a 422 for a blank name, an empty
    language list, a short name that is not lower-case letters, digits and hyphens, or an
    address that belongs to platform staff, each with its own `code` and a message to
    show; `permission_denied` without `tenants.manage`.
    """
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
