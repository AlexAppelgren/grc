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
from typing import Any, cast

from django.http import HttpRequest
from ninja import Path, Query, Router

from apps.identity.models import User
from apps.identity.schemas import Empty, SessionTokens
from apps.identity.session_logic import actor_of
from apps.shared import permissions as perms
from apps.shared.authentication import Principal, SessionAuth
from apps.shared.permissions import requires_permission, requires_step_up
from apps.shared.schemas import PageQuery
from apps.taxonomy.http import actor_for, caller_tenant, if_match
from apps.taxonomy.reading import language_order
from apps.taxonomy.schemas import PersonRef
from apps.tenants import logic, organisation, people, products, reassignment, support_access, teams
from apps.tenants.schemas import (
    ConsoleReissueBody,
    ConsoleSupportAccessBody,
    ConsoleSupportAccessGrant,
    ConsoleSupportAccessPage,
    ConsoleTenantCreateBody,
    ConsoleTenantPage,
    ConsoleTenantRow,
    SupportAccessGrant,
    SupportAccessPage,
    TenantAiBody,
    TenantLicence,
    TenantLicenceBody,
    TenantLicencePage,
    TenantLicencePatch,
    TenantMemberOpenWork,
    TenantMemberRemoveBody,
    TenantOrgUnit,
    TenantOrgUnitBody,
    TenantOrgUnitPage,
    TenantOrgUnitPatch,
    TenantOut,
    TenantPatch,
    TenantPeoplePage,
    TenantProductBody,
    TenantProductOut,
    TenantProductPage,
    TenantProductPatch,
    TenantTeamPage,
    TenantWorkflowPatch,
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


@router.patch(
    "/tenant/workflow",
    response=TenantOut,
    auth=SessionAuth(),
    operation_id="updateTenantWorkflow",
    by_alias=True,
    summary="Change your bank's reminders, escalation, digest day or triage target",
)
@requires_permission(perms.WORKFLOW_MANAGE)
def update_tenant_workflow(request: HttpRequest, body: TenantWorkflowPatch) -> TenantOut:
    """Updates the bank's workflow policy and returns the whole profile as it now stands,
    with the policy under `workflow`. Send only the fields you are changing: an omitted
    field is left alone, and each list replaces the current one rather than adding to it.
    Call it from the bank's workflow settings once an administrator has edited them.

    The policy decides how many days before a due date or a review the owner is reminded,
    how many days overdue work waits before it escalates and to which of the bank's roles,
    the weekday the digest goes out and the triage target in hours. A new bank starts at
    the platform defaults. It is separate from the profile edit, `PATCH /tenant`, which
    needs `security.manage` and ignores these fields.

    Needs the `workflow.manage` permission, which the bank's administrator and compliance
    officer roles carry; a member without it is refused and nothing is written. No passkey
    step-up is asked for: this is a workflow control, not a security one. The change is
    recorded in the audit log as `tenant.workflow_updated` with every policy value before
    and after, in the same transaction as the write.

    Errors: `validation_error` (422) with the field named in `errors` for a number or a day
    out of range, an empty or over-long list, or a field the body does not name;
    `unknown_key` (422) with the field named in `errors` for a role that is not an active
    role of this bank or a weekday that is not one of the seven; `permission_denied` (403)
    without `workflow.manage`, naming it in `requiredPermission`; `unauthenticated` (401)
    without a session.
    """
    principal = _principal(request)
    tenant = logic.update_workflow(
        tenant=logic.get_tenant(principal.tenant_id),
        actor=actor_of(User.objects.get(pk=principal.subject_id)),
        reminder_days_before=body.reminder_days_before,
        review_reminder_days_before=body.review_reminder_days_before,
        escalate_after_days=body.escalate_after_days,
        escalate_to_role=body.escalate_to_role,
        digest_weekday=body.digest_weekday,
        triage_target_hours=body.triage_target_hours,
    )
    return TenantOut.model_validate(logic.tenant_out(tenant))


@router.put(
    "/tenant/ai",
    response=TenantOut,
    auth=SessionAuth(),
    operation_id="setTenantAi",
    by_alias=True,
    summary="Switch your bank's AI features on or off",
)
@requires_permission(perms.SECURITY_MANAGE)
@requires_step_up
def set_tenant_ai(request: HttpRequest, body: TenantAiBody) -> TenantOut:
    """Switches the bank's own AI features off or back on and returns the profile as it now
    stands, with `aiEnabled` showing the new state. Call it from the bank's Organisation
    screen when an administrator decides that no question or text of the bank's should go
    to a model, or that it may again.

    Off means Ask and the drafts a model writes for the bank's members answer
    `feature_off` (403) before any model is reached, and a search, by a member or by the
    bank's own key, sends what was typed to no embedding model and no reranker and finds
    records by their words alone. It does not stop the research agents
    that keep the shared library and the watch feed current: they run for every bank, read
    only public sources and never see this bank's own words. The profile edit,
    `PATCH /tenant`, never changes this switch.

    Needs the `security.manage` permission and a fresh passkey step-up, because deciding
    whether the bank's words may leave it for a model is a security change. The change is
    recorded in the audit log as `tenant.ai_switched` with the state before and after and
    the step-up assertion, in the same transaction as the switch. Sending the state the
    bank already has leaves it as it is and is still recorded.

    Errors: `validation_error` (422) for a body without a boolean `enabled` or with any
    other field; `step_up_required` (403) without a fresh passkey assertion;
    `permission_denied` (403) without `security.manage`, naming it in
    `requiredPermission`; `unauthenticated` (401) without a session.
    """
    principal = _principal(request)
    tenant = logic.set_ai_enabled(
        tenant=logic.get_tenant(principal.tenant_id),
        actor=actor_of(User.objects.get(pk=principal.subject_id)),
        enabled=body.enabled,
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
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
    its name and a short name derived from it; gives it the system roles and the starting
    set of its own lists, which its administrator may extend afterwards; and sends the
    first administrator an enrolment invitation carrying the system role that can invite
    everyone else. That person receives a one-time code by email, which stops working the
    moment their first passkey exists; no password is ever created. The timezone, default
    language and content languages are the bank's own to set afterwards, on its
    Organisation profile screen (D-68): platform staff are never asked to guess at them,
    and the onboarding "profile" step stays open until the bank's administrator sets them.
    The creation is recorded in the audit log as `tenant.created` with the whole profile,
    and the invitation is recorded against the new bank. If anything in the call is
    refused, nothing at all is written.

    The address must belong to the bank. Platform staff are separate accounts, and an
    address that already carries a platform role is refused, because a console account
    invited into a bank would carry the console's permissions into a bank session.

    Answers 201 with the new bank's console row. Errors: a 422 for a blank name or an
    address that belongs to platform staff, each with its own `code` and a message to
    show; `permission_denied` without `tenants.manage`.
    """
    platform_user = User.objects.get(pk=_principal(request).subject_id)
    tenant = logic.create_tenant(
        actor=actor_of(platform_user),
        name=body.name,
        first_admin_email=body.first_admin_email,
        first_admin_title=body.first_admin_title,
    )
    return 201, ConsoleTenantRow.model_validate(logic.console_tenant_row(tenant))


# ---------------------------------------------------------------------------------------
# c8-tenants-contract: the bank's organisation, teams and people, member removal and
# support access (TEN-02, TEN-03, TEN-05, TEN-06, COL-04, HOM-05, ADM-01). Each route is
# declared behind the gate it keeps and calls a named function in the module of the package
# that builds it; until then that function loads the record the route names in the caller's
# bank, so another bank's id answers 404, and answers 501 `not_built`.
# ---------------------------------------------------------------------------------------
_ORG_UNIT_ID = (
    "The unit of the bank's organisation, as a UUID. Another bank's unit answers 404, never 403."
)
_LICENCE_ID = "The licence or certificate, as a UUID. Another bank's licence answers 404, never 403."
_PRODUCT_ID = "The product, as a UUID. Another bank's product answers 404, never 403."
_TEAM_KEY = (
    "The team's key, a row of the bank's `team` vocabulary, which an administrator may extend at "
    "`GET /vocab/team`, such as `compliance`. A key the bank has no team for answers 404."
)
_USER_ID = (
    "The member, as the UUID a member list returns as `id`. Somebody who is not an active member "
    "of the caller's bank answers 404, never 403."
)
_GRANT_ID = "The support access request, as a UUID. Another bank's request answers 404, never 403."
_PEOPLE_EXAMPLE = [{"id": "8a3c1e5f-2d4b-4f60-9e7a-1b2c3d4e5f60", "name": "Karin Holm"}]


@router.get(
    "/tenant/org-units",
    response=TenantOrgUnitPage,
    auth=SessionAuth(),
    operation_id="listOrgUnits",
    by_alias=True,
    summary="See your bank's groups, legal entities and departments",
)
def list_org_units(request: HttpRequest, page: PageQuery = Query(...)) -> Any:
    """Every unit of the bank's organisation, one page at a time by name: the group, the legal
    entities with their registration number, LEI, country and legal-entity term, and the
    business areas, units and functions with their head. Call it to draw the organisation
    screen, to fill an entity or department picker, or to learn which legal entities an
    obligation can be assessed for. Deactivated units are listed and marked.

    Any member of the bank may call it; beyond a session no permission is needed. It changes
    nothing and writes no audit event. An empty organisation is a 200 with `total` 0.

    Errors: `unauthenticated` (401) without a session; `not_found` (404) for a session that
    belongs to no bank, which is what a console session gets; `validation_error` (422) for a
    page size above 100. Published ahead of the logic that will fill it, and answering 501
    `not_built` until that ships.
    """
    # Ungated by design: capability (any member of the tenant).
    tenant = caller_tenant(request)
    return organisation.list_org_units(tenant=tenant, order=language_order(request, tenant=tenant), limit=page.limit, offset=page.offset)


@router.post(
    "/tenant/org-units",
    response={201: TenantOrgUnit},
    auth=SessionAuth(),
    operation_id="createOrgUnit",
    by_alias=True,
    summary="Add a legal entity or department to your bank's organisation",
)
@requires_permission(perms.VOCAB_MANAGE)
def create_org_unit(request: HttpRequest, body: TenantOrgUnitBody) -> Any:
    """Adds one unit under the parent the body names and answers 201 with it. A legal entity
    carries the legal-entity term obligations are scoped with and may then hold licences; a
    business area, unit or function with a head is a department, whose head sees its work.

    Needs `vocab.manage`, the business-configuration permission, kept apart from member
    administration (ADM-03). No step-up. Recorded in the audit log as `org_unit.created` with
    the new unit, in the same transaction as the write.

    Errors: `validation_error` (422) for a blank or multi-line name, an unknown kind or a field
    the body does not name; `unknown_key` (422) for a term that is not a legal-entity term,
    and `not_found` (404) for a parent or head that is not the bank's own;
    `permission_denied` (403) without `vocab.manage`, naming it in `requiredPermission`;
    `unauthenticated` (401) without a session. Published ahead of the logic that will fill
    it, and answering 501 `not_built` until that ships.
    """
    tenant = caller_tenant(request)
    return organisation.create_org_unit(tenant=tenant, actor=actor_for(request), order=language_order(request, tenant=tenant), body=body)


@router.patch(
    "/tenant/org-units/{org_unit_id}",
    response=TenantOrgUnit,
    auth=SessionAuth(),
    operation_id="updateOrgUnit",
    by_alias=True,
    summary="Rename, move, re-head or deactivate a unit of your bank",
)
@requires_permission(perms.VOCAB_MANAGE)
def update_org_unit(
    request: HttpRequest, body: TenantOrgUnitPatch, org_unit_id: uuid.UUID = Path(..., description=_ORG_UNIT_ID)
) -> Any:
    """Changes the fields the body sends and answers with the unit as it now stands. A unit's
    kind never changes; deactivating is `active: false`, and a unit is never deleted, so its
    licences and register rows stay readable.

    Needs `vocab.manage`. Send `If-Match` with the `version` last read; a unit changed in
    between is refused and nothing is merged. Recorded in the audit log as `org_unit.updated`
    with every changed field before and after. No step-up.

    Errors: `not_found` (404) for a unit, parent or head that is not the bank's own;
    `stale_write` (409) when `If-Match` is not the current version; `validation_error` (422)
    for an `If-Match` that is not a version or a body the schema refuses; `unknown_key` (422)
    for an unknown term; `permission_denied` (403) without `vocab.manage`; `unauthenticated`
    (401). Published ahead of the logic that will fill it, and answering 501 `not_built`
    until that ships.
    """
    tenant = caller_tenant(request)
    return organisation.update_org_unit(
        tenant=tenant,
        actor=actor_for(request),
        order=language_order(request, tenant=tenant),
        org_unit_id=org_unit_id,
        body=body,
        expected_version=if_match(request),
    )


@router.get(
    "/tenant/org-units/{org_unit_id}/licences",
    response=TenantLicencePage,
    auth=SessionAuth(),
    operation_id="listLicences",
    by_alias=True,
    summary="See the licences and certificates a legal entity holds",
)
def list_licences(
    request: HttpRequest, org_unit_id: uuid.UUID = Path(..., description=_ORG_UNIT_ID), page: PageQuery = Query(...)
) -> Any:
    """The licences and certificates one legal entity holds, withdrawn ones included and
    marked: the type as a term, the authority's reference, the grant and withdrawal dates,
    and a certificate's issuer, number, scope, validity, next audit and owner. A certificate's
    validity and next audit are the bank's own deadlines on its roadmap; they carry no term
    and change no obligation's scope.

    Any member of the bank may call it. It changes nothing and writes no audit event. A unit
    that holds none is a 200 with `total` 0.

    Errors: `not_found` (404) for a unit that is not the bank's own; `validation_error` (422)
    for a page size above 100; `unauthenticated` (401). Published ahead of the logic that will
    fill it, and answering 501 `not_built` until that ships.
    """
    # Ungated by design: capability (any member of the tenant).
    tenant = caller_tenant(request)
    return organisation.list_licences(
        tenant=tenant, order=language_order(request, tenant=tenant), org_unit_id=org_unit_id, limit=page.limit, offset=page.offset
    )


@router.post(
    "/tenant/org-units/{org_unit_id}/licences",
    response={201: TenantLicence},
    auth=SessionAuth(),
    operation_id="createLicence",
    by_alias=True,
    summary="Record a licence or certificate a legal entity holds",
)
@requires_permission(perms.VOCAB_MANAGE)
def create_licence(
    request: HttpRequest, body: TenantLicenceBody, org_unit_id: uuid.UUID = Path(..., description=_ORG_UNIT_ID)
) -> Any:
    """Records a licence an authority granted, or a certificate such as ISO/IEC 27001 with its
    issuer, number, scope statement, validity, next audit and owner, on one legal entity, and
    answers 201 with it. Nothing about the bank's scope, its obligations or their
    applicability changes.

    Needs `vocab.manage`. No step-up. Recorded in the audit log as `licence.created` with the
    new row, in the same transaction as the write.

    Errors: `not_found` (404) for a unit or owner that is not the bank's own;
    `validation_error` (422) for a unit that is not a legal entity, a missing type or a field
    the body does not name; `unknown_key` (422) for a type or service term the library does
    not hold; `permission_denied` (403) without `vocab.manage`; `unauthenticated` (401).
    Published ahead of the logic that will fill it, and answering 501 `not_built` until that
    ships.
    """
    tenant = caller_tenant(request)
    return organisation.create_licence(
        tenant=tenant, actor=actor_for(request), order=language_order(request, tenant=tenant), org_unit_id=org_unit_id, body=body
    )


@router.patch(
    "/tenant/licences/{licence_id}",
    response=TenantLicence,
    auth=SessionAuth(),
    operation_id="updateLicence",
    by_alias=True,
    summary="Change or withdraw a licence or certificate",
)
@requires_permission(perms.VOCAB_MANAGE)
def update_licence(
    request: HttpRequest, body: TenantLicencePatch, licence_id: uuid.UUID = Path(..., description=_LICENCE_ID)
) -> Any:
    """Changes the fields the body sends and answers with the row as it now stands. A licence
    is withdrawn by setting `withdrawnOn`, never deleted, and the withdrawn row stays in the
    history.

    Needs `vocab.manage`. Send `If-Match` with the `version` last read; a row changed in
    between is refused. Recorded in the audit log as `licence.updated` with every changed
    field before and after. No step-up.

    Errors: `not_found` (404) for a licence or owner that is not the bank's own;
    `stale_write` (409) when `If-Match` is not the current version; `validation_error` (422)
    for an `If-Match` that is not a version or a body the schema refuses; `unknown_key` (422)
    for an unknown term; `permission_denied` (403) without `vocab.manage`; `unauthenticated`
    (401). Published ahead of the logic that will fill it, and answering 501 `not_built`
    until that ships.
    """
    tenant = caller_tenant(request)
    return organisation.update_licence(
        tenant=tenant,
        actor=actor_for(request),
        order=language_order(request, tenant=tenant),
        licence_id=licence_id,
        body=body,
        expected_version=if_match(request),
    )


@router.get(
    "/tenant/products",
    response=TenantProductPage,
    auth=SessionAuth(),
    operation_id="listProducts",
    by_alias=True,
    summary="See the products your bank offers and how each is scoped",
)
def list_products(request: HttpRequest, page: PageQuery = Query(...)) -> Any:
    """The bank's products, one page at a time by name, planned, live and retired, each with
    its scope in the terms obligations are scoped with, the unit that offers it and its owner.
    Call it to draw the products screen or to fill a product picker.

    Any member of the bank may call it. It changes nothing and writes no audit event. A bank
    with no product is a 200 with `total` 0.

    Errors: `validation_error` (422) for a page size above 100; `not_found` (404) for a session
    that belongs to no bank; `unauthenticated` (401). Published ahead of the logic that will
    fill it, and answering 501 `not_built` until that ships.
    """
    # Ungated by design: capability (any member of the tenant).
    tenant = caller_tenant(request)
    return products.list_products(tenant=tenant, order=language_order(request, tenant=tenant), limit=page.limit, offset=page.offset)


@router.post(
    "/tenant/products",
    response={201: TenantProductOut},
    auth=SessionAuth(),
    operation_id="createProduct",
    by_alias=True,
    summary="Add a product and describe its scope",
)
@requires_permission(perms.VOCAB_MANAGE)
def create_product(request: HttpRequest, body: TenantProductBody) -> Any:
    """Adds a product with its scope in the library's terms and answers 201 with it. A product
    is how an obligation's scope meets what the bank actually sells, so a planned product can
    be scoped before it launches.

    Needs `vocab.manage`. No step-up. Recorded in the audit log as `product.created` with the
    new row, in the same transaction as the write.

    Errors: `validation_error` (422) for a blank or multi-line name, a name the bank already
    uses, an unknown status or a field the body does not name; `unknown_key` (422) for a term
    the library does not hold; `not_found` (404) for a unit or owner that is not the bank's
    own; `permission_denied` (403) without `vocab.manage`; `unauthenticated` (401). Published
    ahead of the logic that will fill it, and answering 501 `not_built` until that ships.
    """
    tenant = caller_tenant(request)
    return products.create_product(tenant=tenant, actor=actor_for(request), order=language_order(request, tenant=tenant), body=body)


@router.patch(
    "/tenant/products/{product_id}",
    response=TenantProductOut,
    auth=SessionAuth(),
    operation_id="updateProduct",
    by_alias=True,
    summary="Change, rescope or retire a product",
)
@requires_permission(perms.VOCAB_MANAGE)
def update_product(
    request: HttpRequest, body: TenantProductPatch, product_id: uuid.UUID = Path(..., description=_PRODUCT_ID)
) -> Any:
    """Changes the fields the body sends and answers with the product as it now stands. A
    product is retired with `status: retired`, never deleted, and a retired product scopes
    nothing.

    Needs `vocab.manage`. Send `If-Match` with the `version` last read; a product changed in
    between is refused. Recorded in the audit log as `product.updated` with every changed
    field before and after. No step-up.

    Errors: `not_found` (404) for a product, unit or owner that is not the bank's own;
    `stale_write` (409) when `If-Match` is not the current version; `validation_error` (422)
    for an `If-Match` that is not a version or a body the schema refuses; `unknown_key` (422)
    for an unknown term; `permission_denied` (403) without `vocab.manage`; `unauthenticated`
    (401). Published ahead of the logic that will fill it, and answering 501 `not_built`
    until that ships.
    """
    tenant = caller_tenant(request)
    return products.update_product(
        tenant=tenant,
        actor=actor_for(request),
        order=language_order(request, tenant=tenant),
        product_id=product_id,
        body=body,
        expected_version=if_match(request),
    )


@router.get(
    "/tenant/teams",
    response=TenantTeamPage,
    auth=SessionAuth(),
    operation_id="listTeams",
    by_alias=True,
    summary="See your bank's teams and how many people are in each",
)
def list_teams(request: HttpRequest, page: PageQuery = Query(...)) -> Any:
    """The bank's teams in the list's order, active and retired, each with its department,
    its shared mailbox and how many active members it has. A team can own work and take part
    in it, so ownership survives a person leaving. Creating, renaming and retiring a team is
    the bank's `team` list at `/vocab/team`, under `vocab.manage`; putting people in a team
    is the member's own route, under `members.manage`.

    Any member of the bank may call it. It changes nothing and writes no audit event.

    Errors: `validation_error` (422) for a page size above 100; `not_found` (404) for a
    session that belongs to no bank; `unauthenticated` (401). Published ahead of the logic
    that will fill it, and answering 501 `not_built` until that ships.
    """
    # Ungated by design: capability (any member of the tenant).
    tenant = caller_tenant(request)
    return teams.list_teams(tenant=tenant, order=language_order(request, tenant=tenant), limit=page.limit, offset=page.offset)


@router.get(
    "/tenant/teams/{key}/members",
    response=TenantPeoplePage,
    auth=SessionAuth(),
    operation_id="listTeamMembers",
    by_alias=True,
    summary="See who is in a team",
)
def list_team_members(
    request: HttpRequest, key: str = Path(..., max_length=80, description=_TEAM_KEY + " At most 80 characters."), page: PageQuery = Query(...)
) -> Any:
    """The active members of one team, by name, as ids and names only. Call it to show a team
    on the organisation screen or to preview what a member's removal ends.

    Any member of the bank may call it. It changes nothing and writes no audit event. A team
    with nobody in it is a 200 with `total` 0.

    Errors: `not_found` (404) for a team key the bank does not have; `validation_error` (422)
    for a page size above 100; `unauthenticated` (401). Published ahead of the logic that will
    fill it, and answering 501 `not_built` until that ships.
    """
    # Ungated by design: capability (any member of the tenant).
    return teams.list_team_members(tenant=caller_tenant(request), key=key, limit=page.limit, offset=page.offset)


@router.get(
    "/reference/people",
    response=list[PersonRef],
    auth=SessionAuth(),
    operation_id="listPeople",
    by_alias=True,
    summary="Pick a person from your bank",
    openapi_extra={"responses": {200: {"content": {"application/json": {"example": _PEOPLE_EXAMPLE}}}}},
)
def list_people(
    request: HttpRequest,
    permission: str | None = Query(
        None,
        max_length=64,
        description=(
            "A permission key, at most 64 characters, such as `cases.signoff`: only the active "
            "members whose roles hold it are listed, so an approver picker offers only people "
            "who may approve. Omitted by default, which lists every active member. A key that is "
            "not one of a bank's permissions (`GET /reference/permissions`) answers `unknown_key`."
        ),
    ),
) -> Any:
    """The bank's active members as ids and names, by name, and nothing else about them: no
    address, no role, no title. Every owner and participant picker, the mention control and
    the approver picker read it. `GET /tenant/members`, with everything about a member, stays
    under `members.manage`.

    Any member's session may call it; an enrolment session may not. It changes nothing and
    writes no audit event. Nobody matching is a 200 with an empty list.

    Errors: `unknown_key` (422) for a permission that is not one of a bank's;
    `validation_error` (422) for a permission longer than 64 characters; `not_found` (404) for
    a session that belongs to no bank; `unauthenticated` (401) without a member session.
    Published ahead of the logic that will fill it, and answering 501 `not_built` until that
    ships.
    """
    # Ungated by design: capability (a member session, never an enrolment session).
    return people.list_people(tenant=caller_tenant(request), permission=permission)


@router.get(
    "/tenant/members/{user_id}/open-work",
    response=TenantMemberOpenWork,
    auth=SessionAuth(),
    operation_id="getMemberOpenWork",
    by_alias=True,
    summary="See what a member owns before you remove them",
)
@requires_permission(perms.MEMBERS_MANAGE)
def get_member_open_work(request: HttpRequest, user_id: uuid.UUID = Path(..., description=_USER_ID)) -> Any:
    """What a member holds, counted by kind: the register entries, entity rows, gaps, dated
    duties, internal items, cases and actions they own, which a removal moves to a new owner,
    and the items they take part in and the teams they are in, which a removal ends. Call it
    when an administrator opens a member's removal, so the screen can ask for a new owner per
    kind before anything changes.

    Needs `members.manage`. It changes nothing and writes no audit event. A member who holds
    nothing is a 200 with an empty `items`.

    Errors: `not_found` (404) for somebody who is not an active member of the bank;
    `permission_denied` (403) without `members.manage`; `unauthenticated` (401). Published
    ahead of the logic that will fill it, and answering 501 `not_built` until that ships.
    """
    return reassignment.open_work(tenant=caller_tenant(request), user_id=user_id)


@router.post(
    "/tenant/members/{user_id}/remove",
    response={204: None},
    auth=SessionAuth(),
    operation_id="removeMember",
    by_alias=True,
    summary="Remove a member and hand their work to new owners",
)
@requires_permission(perms.MEMBERS_MANAGE)
@requires_step_up
def remove_member(
    request: HttpRequest, body: TenantMemberRemoveBody, user_id: uuid.UUID = Path(..., description=_USER_ID)
) -> Any:
    """Removes a member from the bank in one transaction: every kind of work they own moves to
    the person or team the body names for it, their participations and team memberships end,
    their sessions are revoked and their membership is deactivated. The participations of
    their teams are untouched. Answers 204 with no body.

    Needs `members.manage` and a fresh passkey step-up. Recorded in the audit log as one event
    per item moved or ended and `member.deactivated`, each carrying the step-up assertion, in
    the same transaction. If any of it is refused, nothing changes.

    Errors: `validation_error` (422) for a kind the member owns with no new owner, an owner
    named twice or as both a person and a team, or a field the body does not name;
    `not_found` (404) for a member, new owner or team that is not the bank's own;
    `last_admin` (409) when the member is the bank's last administrator; `step_up_required`
    (403) without a fresh passkey assertion; `permission_denied` (403) without
    `members.manage`; `unauthenticated` (401). Published ahead of the logic that will fill it,
    and answering 501 `not_built` until that ships.
    """
    tenant = caller_tenant(request)
    return reassignment.remove_member(
        tenant=tenant,
        actor=actor_for(request),
        user_id=user_id,
        body=body,
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
    )


@router.get(
    "/tenant/support-access",
    response=SupportAccessPage,
    auth=SessionAuth(),
    operation_id="listTenantSupportAccess",
    by_alias=True,
    summary="See who from platform support asked to look in, and who was let in",
)
def list_tenant_support_access(request: HttpRequest, page: PageQuery = Query(...)) -> Any:
    """Every support access request the bank has had, newest first: pending requests waiting
    for a decision, the live grant with its window, and the past ones, each with its purpose,
    ticket, the platform person, who decided and when, and the one-off administrator
    recoveries platform support carried out. Every read under a grant is in the bank's own
    audit log as `support_access.read`.

    Any member of the bank may call it; platform staff have no bypass, and the bank sees
    everything they asked for. It changes nothing and writes no audit event. A bank support
    never asked is a 200 with `total` 0.

    Errors: `validation_error` (422) for a page size above 100; `not_found` (404) for a
    session that belongs to no bank; `unauthenticated` (401). Published ahead of the logic
    that will fill it, and answering 501 `not_built` until that ships.
    """
    # Ungated by design: capability (any member of the tenant).
    return support_access.list_for_tenant(tenant=caller_tenant(request), limit=page.limit, offset=page.offset)


@router.post(
    "/tenant/support-access/{grant_id}/approve",
    response=SupportAccessGrant,
    auth=SessionAuth(),
    operation_id="approveSupportAccess",
    by_alias=True,
    summary="Let platform support read your bank for the window it asked for",
)
@requires_permission(perms.SECURITY_MANAGE)
@requires_step_up
def approve_support_access(request: HttpRequest, grant_id: uuid.UUID = Path(..., description=_GRANT_ID)) -> Any:
    """Approves a pending request and answers with it, now `active`: the window of the hours it
    asked for starts now, and the platform person may enter the bank read-only until it ends
    or the bank revokes it. They can never write, search, ask, or download evidence or an
    export.

    Needs `security.manage` and a fresh passkey step-up. The approver is never the platform
    person who asked. Recorded in the audit log as `support_access.approved` with the step-up
    assertion, in the same transaction.

    Errors: `not_found` (404) for a request that is not the bank's own; `four_eyes_violation`
    (409) when the approver is the person who asked; `step_up_required` (403) without a fresh
    passkey assertion;
    `permission_denied` (403) without `security.manage`; `unauthenticated` (401). Published
    ahead of the logic that will fill it, and answering 501 `not_built` until that ships.
    """
    tenant = caller_tenant(request)
    return support_access.approve(
        tenant=tenant,
        actor=actor_for(request),
        grant_id=grant_id,
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
    )


@router.post(
    "/tenant/support-access/{grant_id}/decline",
    response=SupportAccessGrant,
    auth=SessionAuth(),
    operation_id="declineSupportAccess",
    by_alias=True,
    summary="Refuse platform support's request to read your bank",
)
@requires_permission(perms.SECURITY_MANAGE)
def decline_support_access(request: HttpRequest, grant_id: uuid.UUID = Path(..., description=_GRANT_ID)) -> Any:
    """Declines a pending request and answers with it, now `declined`; nothing was ever
    granted. No step-up, because a refusal never needs one.

    Needs `security.manage`. Recorded in the audit log as `support_access.declined`.

    Errors: `not_found` (404) for a request that is not the bank's own;
    `permission_denied` (403) without `security.manage`;
    `unauthenticated` (401). Published ahead of the logic that will fill it, and answering 501
    `not_built` until that ships.
    """
    tenant = caller_tenant(request)
    return support_access.decline(tenant=tenant, actor=actor_for(request), grant_id=grant_id)


@router.post(
    "/tenant/support-access/{grant_id}/revoke",
    response=SupportAccessGrant,
    auth=SessionAuth(),
    operation_id="revokeSupportAccess",
    by_alias=True,
    summary="End platform support's access to your bank now",
)
@requires_permission(perms.SECURITY_MANAGE)
def revoke_support_access(request: HttpRequest, grant_id: uuid.UUID = Path(..., description=_GRANT_ID)) -> Any:
    """Ends an active grant at once and answers with it, now `revoked`: the support session's
    next request answers 401 and the ones after it 404. No step-up, because ending access never
    needs one.

    Needs `security.manage`. Recorded in the audit log as `support_access.revoked`.

    Errors: `not_found` (404) for a request that is not the bank's own;
    `permission_denied` (403) without `security.manage`;
    `unauthenticated` (401). Published ahead of the logic that will fill it, and answering 501
    `not_built` until that ships.
    """
    tenant = caller_tenant(request)
    return support_access.revoke(tenant=tenant, actor=actor_for(request), grant_id=grant_id)


@router.post(
    "/console/tenants/{tenant_id}/support-access",
    response={201: ConsoleSupportAccessGrant},
    auth=SessionAuth(),
    operation_id="requestConsoleSupportAccess",
    by_alias=True,
    summary="Ask a bank to let you read its data for a stated purpose",
)
@requires_permission(perms.SUPPORT_ACCESS_GRANT)
def request_console_support_access(
    request: HttpRequest,
    body: ConsoleSupportAccessBody,
    tenant_id: uuid.UUID = Path(
        ..., description="The bank being asked, the UUID the console's tenant list returns as `id`; a bank that does not exist answers 404."
    ),
) -> Any:
    """Asks one bank for read-only access for a purpose, an optional ticket and a window of at
    most `SUPPORT_ACCESS_MAX_HOURS` hours, and answers 201 with the request, `pending`. The
    request grants nothing: every read of the bank still answers 404 until one of its
    administrators approves it, and the holders of `security.manage` are told. A request
    nobody decides lapses.

    Needs the platform permission `support_access.grant`. No step-up, because a request grants
    nothing; entering an approved grant takes one. Recorded in the bank's own audit log as
    `support_access.requested`.

    Errors: `validation_error` (422) for a blank purpose, a window under an hour or above the
    maximum, or a field the body does not name; `not_found` (404) for a bank that does not
    exist; `permission_denied` (403) without `support_access.grant`; `unauthenticated` (401).
    Published ahead of the logic that will fill it, and answering 501 `not_built` until that
    ships.
    """
    return support_access.request_access(tenant_id=tenant_id, actor=actor_for(request), body=body)


@router.get(
    "/console/support-access",
    response=ConsoleSupportAccessPage,
    auth=SessionAuth(),
    operation_id="listConsoleSupportAccess",
    by_alias=True,
    summary="See your own support access requests and grants",
)
@requires_permission(perms.SUPPORT_ACCESS_GRANT)
def list_console_support_access(request: HttpRequest, page: PageQuery = Query(...)) -> Any:
    """The caller's own requests across banks, newest first, each with the bank's organisation
    name, the purpose, the ticket, the window, the state and the time of the bank's decision.
    Never another platform person's request, and never the name of anyone at a bank.

    Needs the platform permission `support_access.grant`. It changes nothing and writes no
    audit event. A caller who never asked is a 200 with `total` 0.

    Errors: `validation_error` (422) for a page size above 100; `permission_denied` (403)
    without `support_access.grant`; `unauthenticated` (401). Published ahead of the logic that
    will fill it, and answering 501 `not_built` until that ships.
    """
    return support_access.my_grants(actor=actor_for(request), limit=page.limit, offset=page.offset)


@router.post(
    "/console/support-access/{grant_id}/enter",
    response=SessionTokens,
    auth=SessionAuth(),
    operation_id="enterConsoleSupportAccess",
    by_alias=True,
    summary="Enter a bank read-only under a grant it approved",
)
@requires_permission(perms.SUPPORT_ACCESS_GRANT)
@requires_step_up
def enter_console_support_access(
    request: HttpRequest,
    grant_id: uuid.UUID = Path(
        ..., description="One of the caller's own approved grants, as a UUID; anybody else's, or one that is not active, answers 404."
    ),
) -> Any:
    """Replaces the caller's console session with a support session in the bank that approved
    the grant, and answers with its access token. The session reads under the bank's own
    row-level security, never writes, and ends with the grant's window or the bank's
    revocation; every request under it is written to the bank's audit log as
    `support_access.read`.

    Needs the platform permission `support_access.grant` and a fresh passkey step-up.
    Recorded in the bank's audit log as `support_access.entered` with the step-up assertion.

    Errors: `not_found` (404) for a grant that is not the caller's own or not active;
    `step_up_required` (403) without a fresh passkey assertion; `permission_denied` (403)
    without `support_access.grant`; `unauthenticated` (401). Published ahead of the logic that
    will fill it, and answering 501 `not_built` until that ships.
    """
    return support_access.enter(
        actor=actor_for(request),
        grant_id=grant_id,
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
    )
