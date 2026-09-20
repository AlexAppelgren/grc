"""Routes of the identity app (playbook 4.1: auth class, permission, step-up, nothing
else). Operation ids are explicit and camelCase so the audit-on-write guard can find
each mutating route by name in tests_scenarios.py."""

import uuid
from typing import cast

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from ninja import Query, Router

from apps.identity import (
    api_keys_logic,
    code_logic,
    invitation_logic,
    me_logic,
    members_logic,
    passkey_logic,
    roles_logic,
    security_log,
    session_logic,
)
from apps.identity.models import User
from apps.identity.schemas import (
    AgentKeyCreate,
    AgentKeyCreated,
    AgentKeyOut,
    AgentKeysPage,
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    ApiKeysPage,
    CodeRequestBody,
    CodeVerifyBody,
    Empty,
    InvitationCodeVerifyBody,
    InvitationOpenBody,
    InvitationOut,
    InvitationsPage,
    Me,
    MemberInvite,
    MemberOut,
    MemberPatch,
    MembersPage,
    MePatch,
    PasskeyAssertBody,
    PasskeyOut,
    PasskeyPatch,
    PasskeyRegisterBody,
    PasskeyRegistered,
    PermissionOut,
    RefreshResult,
    RoleCreate,
    RoleOut,
    RolePatch,
    SecurityEventOut,
    SecurityLogPage,
    SessionOut,
    SessionTokens,
    StepUpResult,
    WebAuthnCreationOptions,
    WebAuthnRequestOptions,
)
from apps.shared import permissions as perms
from apps.shared.authentication import EnrolmentAuth, Principal, PrincipalKind, SessionAuth
from apps.shared.models import Tenant
from apps.shared.permissions import enforce_recent_sign_in_or_step_up, enforce_step_up, requires_permission, requires_step_up
from apps.shared.schemas import PageQuery

router = Router(tags=["Identity"])


def _principal(request: HttpRequest) -> Principal:
    return cast(Principal, request.auth)  # type: ignore[attr-defined]


def _tenant_id(request: HttpRequest) -> uuid.UUID:
    """The session's tenant; a platform session has none and every tenant route is a 404 for it."""
    tenant_id = _principal(request).tenant_id
    if tenant_id is None:
        raise ValidationError("Not found.", code="not_found")
    return tenant_id


def _tenant(request: HttpRequest) -> Tenant:
    return Tenant.objects.select_related("default_language").get(pk=_tenant_id(request))


def _actor_user(request: HttpRequest) -> User:
    return User.objects.select_related("locale").get(pk=_principal(request).subject_id)


def _order(request: HttpRequest) -> list[str]:
    principal = _principal(request)
    user = User.objects.select_related("locale").get(pk=principal.subject_id)
    tenant = Tenant.objects.select_related("default_language").filter(pk=principal.tenant_id).first() if principal.tenant_id else None  # ordering: pk lookup, at most one row
    return roles_logic.language_order(user, tenant)


def _session_response(bundle: session_logic.SessionBundle, response: HttpResponse) -> SessionTokens:
    session_logic.set_refresh_cookie(response, bundle.refresh_value)
    return SessionTokens(access_token=bundle.access_token, session_kind=bundle.session.kind, expires_in=bundle.expires_in)


# ---------------------------------------------------------------------------------------
# Invitation, code, enrolment (ID-01, ID-02)
# ---------------------------------------------------------------------------------------
@router.post("/auth/invitations/open", response={202: Empty}, auth=None, operation_id="openInvitation", by_alias=True)
def open_invitation(request: HttpRequest, body: InvitationOpenBody) -> tuple[int, Empty]:
    # Ungated by design: public-token (the single-use token is the grant). It rides in the
    # body, never the path, so no request line holds it (security review F29).
    invitation_logic.open_invitation(body.token, request)
    return 202, Empty()


@router.post("/auth/invitations/verify", response=SessionTokens, auth=None, operation_id="verifyInvitationCode", by_alias=True)
def verify_invitation_code(request: HttpRequest, body: InvitationCodeVerifyBody, response: HttpResponse) -> SessionTokens:
    # Ungated by design: public-token (the single-use token and the code are the grant).
    return _session_response(code_logic.verify_invitation_code(body.token, body.code, request), response)


@router.post("/auth/code/request", response={202: Empty}, auth=None, operation_id="requestCode", by_alias=True)
def request_code(request: HttpRequest, body: CodeRequestBody) -> tuple[int, Empty]:
    # Ungated by design: bootstrap. Neutral answer whatever the address (AC-ID1).
    code_logic.request_code(body.email, request)
    return 202, Empty()


@router.post("/auth/code/verify", response=SessionTokens, auth=None, operation_id="verifyCode", by_alias=True)
def verify_code(request: HttpRequest, body: CodeVerifyBody, response: HttpResponse) -> SessionTokens:
    # Ungated by design: bootstrap.
    return _session_response(code_logic.verify_code(body.email, body.code, request), response)


# ---------------------------------------------------------------------------------------
# Passkeys (ID-02, ID-03, ID-04)
# ---------------------------------------------------------------------------------------
@router.post(
    "/auth/passkeys/register/options",
    response=WebAuthnCreationOptions,
    auth=[SessionAuth(), EnrolmentAuth()],
    operation_id="passkeyRegisterOptions",
    by_alias=True,
)
def passkey_register_options(request: HttpRequest) -> WebAuthnCreationOptions:
    # Ungated by design: capability (the enrolment or full session is the grant).
    return WebAuthnCreationOptions.model_validate(passkey_logic.registration_options(_principal(request)))


@router.post(
    "/auth/passkeys/register/verify",
    response={201: PasskeyRegistered},
    auth=[SessionAuth(), EnrolmentAuth()],
    operation_id="passkeyRegisterVerify",
    by_alias=True,
)
def passkey_register_verify(request: HttpRequest, body: PasskeyRegisterBody, response: HttpResponse) -> tuple[int, PasskeyRegistered]:
    # Ungated by design: capability. From a full session, adding an authentication factor
    # needs a session younger than the step-up window or a fresh assertion (security
    # review F9, narrowed); the enrolment session needs neither, its code is the proof.
    if _principal(request).kind is PrincipalKind.USER:
        enforce_recent_sign_in_or_step_up(request)
    result = passkey_logic.verify_registration(
        _principal(request), body.credential.model_dump(by_alias=True, exclude_none=True), body.nickname, request
    )
    bundle = result.bundle
    if bundle is not None:
        session_logic.set_refresh_cookie(response, bundle.refresh_value)
    return 201, PasskeyRegistered(
        passkey=PasskeyOut.model_validate(passkey_logic.passkey_out(result.credential)),
        access_token=bundle.access_token if bundle else None,
        session_kind="full",
        expires_in=bundle.expires_in if bundle else None,
    )


@router.post("/auth/passkeys/authenticate/options", response=WebAuthnRequestOptions, auth=None, operation_id="passkeyAuthenticateOptions", by_alias=True)
def passkey_authenticate_options(request: HttpRequest) -> WebAuthnRequestOptions:
    # Ungated by design: bootstrap.
    return WebAuthnRequestOptions.model_validate(passkey_logic.authentication_options(request))


@router.post("/auth/passkeys/authenticate/verify", response=SessionTokens, auth=None, operation_id="passkeyAuthenticateVerify", by_alias=True)
def passkey_authenticate_verify(request: HttpRequest, body: PasskeyAssertBody, response: HttpResponse) -> SessionTokens:
    # Ungated by design: bootstrap.
    bundle = passkey_logic.verify_authentication(body.credential.model_dump(by_alias=True, exclude_none=True), request)
    return _session_response(bundle, response)


@router.post("/auth/step-up/options", response=WebAuthnRequestOptions, auth=SessionAuth(), operation_id="stepUpOptions", by_alias=True)
def step_up_options(request: HttpRequest) -> WebAuthnRequestOptions:
    # Ungated by design: self.
    return WebAuthnRequestOptions.model_validate(passkey_logic.step_up_options(_principal(request)))


@router.post("/auth/step-up/verify", response=StepUpResult, auth=SessionAuth(), operation_id="stepUpVerify", by_alias=True)
def step_up_verify(request: HttpRequest, body: PasskeyAssertBody) -> StepUpResult:
    # Ungated by design: self.
    assertion = passkey_logic.verify_step_up(_principal(request), body.credential.model_dump(by_alias=True, exclude_none=True), request)
    return StepUpResult(assertion_id=assertion.id, expires_at=passkey_logic.step_up_valid_until(assertion))


# ---------------------------------------------------------------------------------------
# Sessions (D-06)
# ---------------------------------------------------------------------------------------
@router.post("/auth/refresh", response=RefreshResult, auth=None, operation_id="refreshSession", by_alias=True)
def refresh_session(request: HttpRequest, response: HttpResponse) -> RefreshResult:
    # Ungated by design: bootstrap (the cookie is the credential).
    access_token, expires_in, new_refresh = session_logic.refresh(request.COOKIES.get(settings.REFRESH_COOKIE_NAME), request)
    if new_refresh is not None:
        session_logic.set_refresh_cookie(response, new_refresh)
    return RefreshResult(access_token=access_token, expires_in=expires_in)


@router.post("/auth/sign-out", response={204: None}, auth=None, operation_id="signOut", by_alias=True)
def sign_out(request: HttpRequest, response: HttpResponse) -> tuple[int, None]:
    # Ungated by design: bootstrap.
    session_logic.sign_out(request.COOKIES.get(settings.REFRESH_COOKIE_NAME), request)
    session_logic.clear_refresh_cookie(response)
    return 204, None


# ---------------------------------------------------------------------------------------
# /me (self)
# ---------------------------------------------------------------------------------------
@router.get("/me", response=Me, auth=[SessionAuth(), EnrolmentAuth()], operation_id="getMe", by_alias=True)
def get_me(request: HttpRequest) -> Me:
    # Ungated by design: self. The enrolment session may call it (AC-ID2).
    return Me.model_validate(me_logic.me(_principal(request)))


@router.patch("/me", response=Me, auth=SessionAuth(), operation_id="updateMe", by_alias=True)
def update_me(request: HttpRequest, body: MePatch) -> Me:
    # Ungated by design: self.
    return Me.model_validate(me_logic.update_me(_principal(request), name=body.name, locale=body.locale))


@router.post("/me/visit", response={204: None}, auth=SessionAuth(), operation_id="markVisit", by_alias=True)
def mark_visit(request: HttpRequest) -> tuple[int, None]:
    # Ungated by design: self. Moves the caller's own "seen the library" bookmark; a
    # session with no tenant has no membership to move and answers 404.
    me_logic.mark_visit(_principal(request))
    return 204, None


@router.get("/me/passkeys", response=list[PasskeyOut], auth=SessionAuth(), operation_id="listMyPasskeys", by_alias=True)
def list_my_passkeys(request: HttpRequest) -> list[PasskeyOut]:
    # Ungated by design: self.
    return [PasskeyOut.model_validate(passkey_logic.passkey_out(row)) for row in passkey_logic.list_passkeys(_principal(request).subject_id)]


@router.patch("/me/passkeys/{passkey_id}", response=PasskeyOut, auth=SessionAuth(), operation_id="renameMyPasskey", by_alias=True)
def rename_my_passkey(request: HttpRequest, passkey_id: uuid.UUID, body: PasskeyPatch) -> PasskeyOut:
    # Ungated by design: self.
    return PasskeyOut.model_validate(passkey_logic.passkey_out(passkey_logic.rename_passkey(_principal(request), passkey_id, body.nickname)))


@router.delete("/me/passkeys/{passkey_id}", response={204: None}, auth=SessionAuth(), operation_id="removeMyPasskey", by_alias=True)
def remove_my_passkey(request: HttpRequest, passkey_id: uuid.UUID) -> tuple[int, None]:
    # Ungated by design: self. Removing an authentication factor needs a session younger
    # than the step-up window or a fresh assertion (F9, narrowed).
    # 409 last_passkey when it is the last live one.
    enforce_recent_sign_in_or_step_up(request)
    passkey_logic.remove_passkey(_principal(request), passkey_id)
    return 204, None


def _session_out(row: session_logic.UserSession, current_id: uuid.UUID | None) -> SessionOut:
    return SessionOut(id=row.id, current=row.id == current_id, created_at=row.created_at, last_seen_at=row.last_seen_at, ip=row.ip, user_agent=row.user_agent)


@router.get("/me/sessions", response=list[SessionOut], auth=SessionAuth(), operation_id="listMySessions", by_alias=True)
def list_my_sessions(request: HttpRequest) -> list[SessionOut]:
    # Ungated by design: self.
    principal = _principal(request)
    user = _actor_user(request)
    return [_session_out(row, principal.session_id) for row in session_logic.live_sessions(user, tenant_id=None)]


@router.delete("/me/sessions/{session_id}", response={204: None}, auth=SessionAuth(), operation_id="revokeMySession", by_alias=True)
def revoke_my_session(request: HttpRequest, session_id: uuid.UUID) -> tuple[int, None]:
    # Ungated by design: self.
    session_logic.revoke_own_session(_principal(request), session_id, request)
    return 204, None


# ---------------------------------------------------------------------------------------
# Tenant admin: members (members.manage)
# ---------------------------------------------------------------------------------------
@router.get("/tenant/members", response=MembersPage, auth=SessionAuth(), operation_id="listMembers", by_alias=True)
@requires_permission(perms.MEMBERS_MANAGE)
def list_members(request: HttpRequest, page: PageQuery = Query(...)) -> MembersPage:
    items, total = members_logic.list_members(_tenant_id(request), _order(request), limit=page.limit, offset=page.offset)
    return MembersPage(items=[MemberOut.model_validate(item) for item in items], total=total)


@router.post("/tenant/members", response={201: InvitationOut}, auth=SessionAuth(), operation_id="inviteMember", by_alias=True)
@requires_permission(perms.MEMBERS_MANAGE)
def invite_member(request: HttpRequest, body: MemberInvite) -> tuple[int, InvitationOut]:
    actor_user = _actor_user(request)
    invitation = members_logic.invite_member(
        tenant=_tenant(request), actor=session_logic.actor_of(actor_user), invited_by=actor_user, email=body.email, role_keys=body.role_keys, title=body.title
    )
    return 201, InvitationOut.model_validate(members_logic.invitation_out(invitation, _order(request)))


@router.patch("/tenant/members/{user_id}", response=MemberOut, auth=SessionAuth(), operation_id="updateMember", by_alias=True)
@requires_permission(perms.MEMBERS_MANAGE)
def update_member(request: HttpRequest, user_id: uuid.UUID, body: MemberPatch) -> MemberOut:
    # Step-up when the roles change (playbook 4.2: role and permission changes).
    assertion_id = enforce_step_up(request) if body.role_keys is not None else None
    membership = members_logic.update_member(
        tenant=_tenant(request),
        actor=session_logic.actor_of(_actor_user(request)),
        user_id=user_id,
        role_keys=body.role_keys,
        title=body.title,
        step_up_assertion_id=assertion_id,
    )
    return MemberOut.model_validate(members_logic.member_detail(membership.tenant_id, membership.user_id, _order(request)))


@router.delete("/tenant/members/{user_id}", response={204: None}, auth=SessionAuth(), operation_id="deactivateMember", by_alias=True)
@requires_permission(perms.MEMBERS_MANAGE)
def deactivate_member(request: HttpRequest, user_id: uuid.UUID) -> tuple[int, None]:
    members_logic.deactivate_member(tenant=_tenant(request), actor=session_logic.actor_of(_actor_user(request)), user_id=user_id, request=request)
    return 204, None


@router.get("/tenant/members/{user_id}/sessions", response=list[SessionOut], auth=SessionAuth(), operation_id="listMemberSessions", by_alias=True)
@requires_permission(perms.MEMBERS_MANAGE)
def list_member_sessions(request: HttpRequest, user_id: uuid.UUID) -> list[SessionOut]:
    return [_session_out(row, None) for row in members_logic.member_sessions(_tenant_id(request), user_id)]


@router.delete("/tenant/members/{user_id}/sessions", response={204: None}, auth=SessionAuth(), operation_id="revokeMemberSessions", by_alias=True)
@requires_permission(perms.MEMBERS_MANAGE)
def revoke_member_sessions(request: HttpRequest, user_id: uuid.UUID) -> tuple[int, None]:
    members_logic.revoke_member_sessions(tenant=_tenant(request), actor=session_logic.actor_of(_actor_user(request)), user_id=user_id, request=request)
    return 204, None


@router.post("/tenant/members/{user_id}/reissue-enrolment", response={202: Empty}, auth=SessionAuth(), operation_id="reissueEnrolment", by_alias=True)
@requires_permission(perms.MEMBERS_MANAGE)
@requires_step_up
def reissue_enrolment(request: HttpRequest, user_id: uuid.UUID) -> tuple[int, Empty]:
    actor_user = _actor_user(request)
    members_logic.reissue_enrolment(
        tenant=_tenant(request),
        actor=session_logic.actor_of(actor_user),
        actor_user=actor_user,
        user_id=user_id,
        request=request,
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
    )
    return 202, Empty()


@router.get("/tenant/invitations", response=InvitationsPage, auth=SessionAuth(), operation_id="listInvitations", by_alias=True)
@requires_permission(perms.MEMBERS_MANAGE)
def list_invitations(request: HttpRequest, page: PageQuery = Query(...)) -> InvitationsPage:
    items, total = members_logic.list_invitations(_tenant_id(request), _order(request), limit=page.limit, offset=page.offset)
    return InvitationsPage(items=[InvitationOut.model_validate(item) for item in items], total=total)


@router.post("/tenant/invitations/{invitation_id}/resend", response=InvitationOut, auth=SessionAuth(), operation_id="resendInvitation", by_alias=True)
@requires_permission(perms.MEMBERS_MANAGE)
def resend_invitation(request: HttpRequest, invitation_id: uuid.UUID) -> InvitationOut:
    tenant = _tenant(request)
    invitation = members_logic.tenant_invitation(tenant.id, invitation_id)
    issued = invitation_logic.resend_invitation(tenant=tenant, invitation=invitation, actor=session_logic.actor_of(_actor_user(request)))
    return InvitationOut.model_validate(members_logic.invitation_out(issued.invitation, _order(request)))


@router.delete("/tenant/invitations/{invitation_id}", response={204: None}, auth=SessionAuth(), operation_id="revokeInvitation", by_alias=True)
@requires_permission(perms.MEMBERS_MANAGE)
def revoke_invitation(request: HttpRequest, invitation_id: uuid.UUID) -> tuple[int, None]:
    tenant = _tenant(request)
    invitation = members_logic.tenant_invitation(tenant.id, invitation_id)
    invitation_logic.revoke_invitation(tenant=tenant, invitation=invitation, actor=session_logic.actor_of(_actor_user(request)))
    return 204, None


# ---------------------------------------------------------------------------------------
# Roles (ID-09)
# ---------------------------------------------------------------------------------------
@router.get("/tenant/roles", response=list[RoleOut], auth=SessionAuth(), operation_id="listRoles", by_alias=True)
def list_roles(request: HttpRequest) -> list[RoleOut]:
    # Ungated by design: capability (any member; pickers need labels).
    order = _order(request)
    return [RoleOut.model_validate(roles_logic.role_out(role, order)) for role in roles_logic.tenant_roles(_tenant_id(request))]


@router.post("/tenant/roles", response={201: RoleOut}, auth=SessionAuth(), operation_id="createRole", by_alias=True)
@requires_permission(perms.ROLES_MANAGE)
@requires_step_up
def create_role(request: HttpRequest, body: RoleCreate) -> tuple[int, RoleOut]:
    role = roles_logic.create_role(
        tenant=_tenant(request),
        actor=session_logic.actor_of(_actor_user(request)),
        key=body.key,
        labels=body.labels,
        usage_note=body.usage_note,
        permissions=body.permissions,
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
    )
    role = roles_logic.tenant_roles(role.tenant_id).get(pk=role.pk)
    return 201, RoleOut.model_validate(roles_logic.role_out(role, _order(request)))


@router.patch("/tenant/roles/{key}", response=RoleOut, auth=SessionAuth(), operation_id="updateRole", by_alias=True)
@requires_permission(perms.ROLES_MANAGE)
def update_role(request: HttpRequest, key: str, body: RolePatch) -> RoleOut:
    # Step-up when the permissions change (playbook 4.2).
    assertion_id = enforce_step_up(request) if body.permissions is not None else None
    tenant = _tenant(request)
    role = roles_logic.tenant_role_by_key(tenant.id, key)
    role = roles_logic.update_role(
        tenant=tenant,
        actor=session_logic.actor_of(_actor_user(request)),
        role=role,
        labels=body.labels,
        usage_note=body.usage_note,
        permissions=body.permissions,
        step_up_assertion_id=assertion_id,
    )
    return RoleOut.model_validate(roles_logic.role_out(role, _order(request)))


@router.post("/tenant/roles/{key}/retire", response=RoleOut, auth=SessionAuth(), operation_id="retireRole", by_alias=True)
@requires_permission(perms.ROLES_MANAGE)
def retire_role(request: HttpRequest, key: str) -> RoleOut:
    tenant = _tenant(request)
    role = roles_logic.tenant_role_by_key(tenant.id, key)
    role = roles_logic.retire_role(tenant=tenant, actor=session_logic.actor_of(_actor_user(request)), role=role)
    return RoleOut.model_validate(roles_logic.role_out(role, _order(request)))


@router.get("/reference/permissions", response=list[PermissionOut], auth=SessionAuth(), operation_id="listPermissions", by_alias=True)
def list_permissions(request: HttpRequest) -> list[PermissionOut]:
    # Ungated by design: capability (any session; the role editor lists the constants).
    return [
        PermissionOut(key=key, group=perms.permission_group(key), description=perms.PERMISSION_DESCRIPTIONS[key])
        for key in sorted(perms.TENANT_PERMISSIONS)
    ]


# ---------------------------------------------------------------------------------------
# API keys (ID-10) and the security log (ID-11)
# ---------------------------------------------------------------------------------------
@router.get("/tenant/api-keys", response=ApiKeysPage, auth=SessionAuth(), operation_id="listApiKeys", by_alias=True)
@requires_permission(perms.INTEGRATIONS_MANAGE)
def list_api_keys(request: HttpRequest, page: PageQuery = Query(...)) -> ApiKeysPage:
    items, total = api_keys_logic.list_api_keys(_tenant_id(request), limit=page.limit, offset=page.offset)
    return ApiKeysPage(items=[ApiKeyOut.model_validate(row) for row in items], total=total)


@router.post("/tenant/api-keys", response={201: ApiKeyCreated}, auth=SessionAuth(), operation_id="createApiKey", by_alias=True)
@requires_permission(perms.INTEGRATIONS_MANAGE)
@requires_step_up
def create_api_key(request: HttpRequest, body: ApiKeyCreate) -> tuple[int, ApiKeyCreated]:
    actor_user = _actor_user(request)
    key, plain = api_keys_logic.create_api_key(
        tenant=_tenant(request),
        actor=session_logic.actor_of(actor_user),
        created_by=actor_user,
        name=body.name,
        scopes=body.scopes,
        expires_at=body.expires_at,
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
    )
    return 201, ApiKeyCreated(
        id=key.id, name=key.name, key_prefix=key.key_prefix, scopes=list(key.scopes), created_at=key.created_at, expires_at=key.expires_at, plain_key=plain
    )


@router.delete("/tenant/api-keys/{key_id}", response={204: None}, auth=SessionAuth(), operation_id="revokeApiKey", by_alias=True)
@requires_permission(perms.INTEGRATIONS_MANAGE)
def revoke_api_key(request: HttpRequest, key_id: uuid.UUID) -> tuple[int, None]:
    api_keys_logic.revoke_api_key(tenant=_tenant(request), actor=session_logic.actor_of(_actor_user(request)), key_id=key_id)
    return 204, None


# ---------------------------------------------------------------------------------------
# Platform agent keys (ID-10, AGT-01, chunk 5): keys bound to an agent, under
# `agent_definitions.manage` and a fresh passkey assertion. They are the platform's alone —
# bleqq's agents are platform-owned and platform-run — so a tenant session holds no
# permission that reaches them and no tenant route creates a key bound to an agent.
# `c5-platform-agent-keys` serves all three; until then each answers 501 behind its gate.
# ---------------------------------------------------------------------------------------
@router.get("/agent-keys", response=AgentKeysPage, auth=SessionAuth(), operation_id="listAgentKeys", by_alias=True)
@requires_permission(perms.AGENT_DEFINITIONS_MANAGE)
def list_agent_keys(request: HttpRequest, page: PageQuery = Query(...)) -> AgentKeysPage:
    return api_keys_logic.list_agent_keys()


@router.post("/agent-keys", response={201: AgentKeyCreated}, auth=SessionAuth(), operation_id="createAgentKey", by_alias=True)
@requires_permission(perms.AGENT_DEFINITIONS_MANAGE)
@requires_step_up
def create_agent_key(request: HttpRequest, body: AgentKeyCreate) -> tuple[int, AgentKeyCreated]:
    return api_keys_logic.create_agent_key()


@router.post("/agent-keys/{key_id}/revoke", response=AgentKeyOut, auth=SessionAuth(), operation_id="revokeAgentKey", by_alias=True)
@requires_permission(perms.AGENT_DEFINITIONS_MANAGE)
def revoke_agent_key(request: HttpRequest, key_id: uuid.UUID) -> AgentKeyOut:
    return api_keys_logic.revoke_agent_key()


@router.get("/tenant/security-log", response=SecurityLogPage, auth=SessionAuth(), operation_id="listSecurityLog", by_alias=True)
@requires_permission(perms.SECURITY_MANAGE)
def list_security_log(request: HttpRequest, page: PageQuery = Query(...)) -> SecurityLogPage:
    items, total = security_log.list_events(_tenant_id(request), limit=page.limit, offset=page.offset)
    return SecurityLogPage(items=[SecurityEventOut.model_validate(row) for row in items], total=total)
