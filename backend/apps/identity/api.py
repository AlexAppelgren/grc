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
    """Opens the emailed invitation link and sends the person their one-time code. Needs no
    permission: the single-use token in the body is the grant, and it travels in the body so no
    access log or proxy ever holds it. A link already used, withdrawn or out of date answers 410
    `invitation_expired`, and too many attempts answer 429 `rate_limited`. Everyone at a bank
    starts here."""
    # Ungated by design: public-token (the single-use token is the grant). It rides in the
    # body, never the path, so no request line holds it (security review F29).
    invitation_logic.open_invitation(body.token, request)
    return 202, Empty()


@router.post("/auth/invitations/verify", response=SessionTokens, auth=None, operation_id="verifyInvitationCode", by_alias=True)
def verify_invitation_code(request: HttpRequest, body: InvitationCodeVerifyBody, response: HttpResponse) -> SessionTokens:
    """Turns the invitation's token and the code from the email into an enrolment session, whose
    only power is to add the person's first passkey. Needs no permission: the token and the code
    together are the grant. A wrong code answers 400 `invalid_code`, too many wrong ones 400
    `code_locked`, an invitation that has run out 410 `invitation_expired`, and a flood 429
    `rate_limited`."""
    # Ungated by design: public-token (the single-use token and the code are the grant).
    return _session_response(code_logic.verify_invitation_code(body.token, body.code, request), response)


@router.post("/auth/code/request", response={202: Empty}, auth=None, operation_id="requestCode", by_alias=True)
def request_code(request: HttpRequest, body: CodeRequestBody) -> tuple[int, Empty]:
    """Asks for a one-time code by address, for the one case that needs it: somebody who was
    invited and has no passkey yet. Needs no permission. The answer is 202 whatever the address,
    so nobody learns from it who banks here, and a person who already holds a passkey is sent
    nothing at all. Too many attempts answer 429 `rate_limited`."""
    # Ungated by design: bootstrap. Neutral answer whatever the address (AC-ID1).
    code_logic.request_code(body.email, request)
    return 202, Empty()


@router.post("/auth/code/verify", response=SessionTokens, auth=None, operation_id="verifyCode", by_alias=True)
def verify_code(request: HttpRequest, body: CodeVerifyBody, response: HttpResponse) -> SessionTokens:
    """Turns an emailed code into an enrolment session that may do one thing: add the person's
    first passkey. Needs no permission. A wrong code answers 400 `invalid_code`, too many wrong
    ones 400 `code_locked`, and a flood 429 `rate_limited`. Once a passkey exists this path is
    closed for good: a bank has no password and no self-service way back in."""
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
    """Starts enrolling a passkey: the challenge and the rules the new device must satisfy, to hand
    straight to `navigator.credentials.create()`. Needs no permission; the enrolment session
    from the emailed code, or a full session adding another device, is the grant. It names the
    devices the person already has, so an authenticator does not quietly make a second passkey
    for the same one."""
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
    """Finishes enrolling the passkey the browser just made and, for somebody who came in on an
    emailed code, hands back the full session it earns. Needs no permission, but adding an
    authentication factor from a full session needs a recent sign-in or a fresh passkey check
    (403 `step_up_required`). A challenge that timed out answers 400 `challenge_expired`, and
    anything that does not verify 400 `registration_failed`."""
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
    """Starts a sign-in: the challenge for `navigator.credentials.get()`. Needs no permission,
    since nobody has proved who they are yet. It names no credentials at all, so nothing about a
    person's devices leaks before anything has been signed."""
    # Ungated by design: bootstrap.
    return WebAuthnRequestOptions.model_validate(passkey_logic.authentication_options(request))


@router.post("/auth/passkeys/authenticate/verify", response=SessionTokens, auth=None, operation_id="passkeyAuthenticateVerify", by_alias=True)
def passkey_authenticate_verify(request: HttpRequest, body: PasskeyAssertBody, response: HttpResponse) -> SessionTokens:
    """Signs a person in with their passkey and opens a full session, with the refresh cookie
    beside it. Needs no permission: the signed challenge is the proof. Anything that does not
    verify answers 401 `signin_failed` and says no more than that; a passkey belonging to
    another account answers 422 `user_handle_mismatch`. This is how everyone at a bank signs in
    after their first day."""
    # Ungated by design: bootstrap.
    bundle = passkey_logic.verify_authentication(body.credential.model_dump(by_alias=True, exclude_none=True), request)
    return _session_response(bundle, response)


@router.post("/auth/step-up/options", response=WebAuthnRequestOptions, auth=SessionAuth(), operation_id="stepUpOptions", by_alias=True)
def step_up_options(request: HttpRequest) -> WebAuthnRequestOptions:
    """Starts the fresh passkey check that the sensitive actions demand: the challenge for
    `navigator.credentials.get()`, limited to the caller's own devices. Needs no permission
    beyond a session, since it acts on the caller alone. Approvals, sign-off, footprint changes,
    exports, key creation and role changes all begin here (ID-06)."""
    # Ungated by design: self.
    return WebAuthnRequestOptions.model_validate(passkey_logic.step_up_options(_principal(request)))


@router.post("/auth/step-up/verify", response=StepUpResult, auth=SessionAuth(), operation_id="stepUpVerify", by_alias=True)
def step_up_verify(request: HttpRequest, body: PasskeyAssertBody) -> StepUpResult:
    """Records that the person has just proved themselves with a passkey, so the session counts as
    stepped up and the call that demanded it can simply be made again. Needs no permission beyond
    a session. A check that does not verify answers 400 `step_up_failed`, and a passkey from
    another account 422 `user_handle_mismatch`. The proof lasts one short window, and the answer
    says until when."""
    # Ungated by design: self.
    assertion = passkey_logic.verify_step_up(_principal(request), body.credential.model_dump(by_alias=True, exclude_none=True), request)
    return StepUpResult(assertion_id=assertion.id, expires_at=passkey_logic.step_up_valid_until(assertion))


# ---------------------------------------------------------------------------------------
# Sessions (D-06)
# ---------------------------------------------------------------------------------------
@router.post("/auth/refresh", response=RefreshResult, auth=None, operation_id="refreshSession", by_alias=True)
def refresh_session(request: HttpRequest, response: HttpResponse) -> RefreshResult:
    """Exchanges the refresh cookie for a new bearer token, so somebody working through the day
    stays signed in without proving themselves again. Needs no permission: the cookie is the
    credential. A missing, spent or revoked cookie answers 401 `unauthenticated`; a replayed one
    ends the whole session and is written to the bank's security log."""
    # Ungated by design: bootstrap (the cookie is the credential).
    access_token, expires_in, new_refresh = session_logic.refresh(request.COOKIES.get(settings.REFRESH_COOKIE_NAME), request)
    if new_refresh is not None:
        session_logic.set_refresh_cookie(response, new_refresh)
    return RefreshResult(access_token=access_token, expires_in=expires_in)


@router.post("/auth/sign-out", response={204: None}, auth=None, operation_id="signOut", by_alias=True)
def sign_out(request: HttpRequest, response: HttpResponse) -> tuple[int, None]:
    """Ends this sign-in and clears the refresh cookie. Needs no permission. It answers 204 whether
    or not a live session was found, so a browser can always finish signing out, and the bank's
    security log keeps the line."""
    # Ungated by design: bootstrap.
    session_logic.sign_out(request.COOKIES.get(settings.REFRESH_COOKIE_NAME), request)
    session_logic.clear_refresh_cookie(response)
    return 204, None


# ---------------------------------------------------------------------------------------
# /me (self)
# ---------------------------------------------------------------------------------------
@router.get("/me", response=Me, auth=[SessionAuth(), EnrolmentAuth()], operation_id="getMe", by_alias=True)
def get_me(request: HttpRequest) -> Me:
    """Everything the interface needs about the caller in one read: the person, the bank they are
    inside, the roles they hold, the permissions their screens branch on, and whether they still
    owe an enrolment. Needs no permission beyond a session, since it only ever describes the
    caller. An enrolment session may call it too, and sees `enrolmentPending` true."""
    # Ungated by design: self. The enrolment session may call it (AC-ID2).
    return Me.model_validate(me_logic.me(_principal(request)))


@router.patch("/me", response=Me, auth=SessionAuth(), operation_id="updateMe", by_alias=True)
def update_me(request: HttpRequest, body: MePatch) -> Me:
    """Changes the caller's own name and interface language. Needs no permission beyond a session.
    An empty name answers 422 `name_required`, and a language the product does not hold 422
    `unknown_key`."""
    # Ungated by design: self.
    return Me.model_validate(me_logic.update_me(_principal(request), name=body.name, locale=body.locale))


@router.get("/me/passkeys", response=list[PasskeyOut], auth=SessionAuth(), operation_id="listMyPasskeys", by_alias=True)
def list_my_passkeys(request: HttpRequest) -> list[PasskeyOut]:
    """The caller's own devices, with when each was last used, so somebody can spot the one they no
    longer carry. Needs no permission beyond a session. Nothing here can sign anyone in: it is a
    list to recognise devices by, and to retire them from."""
    # Ungated by design: self.
    return [PasskeyOut.model_validate(passkey_logic.passkey_out(row)) for row in passkey_logic.list_passkeys(_principal(request).subject_id)]


@router.patch("/me/passkeys/{passkey_id}", response=PasskeyOut, auth=SessionAuth(), operation_id="renameMyPasskey", by_alias=True)
def rename_my_passkey(request: HttpRequest, passkey_id: uuid.UUID, body: PasskeyPatch) -> PasskeyOut:
    """Renames one of the caller's own devices, so a list of three reads as a laptop, a phone and a
    security key. Needs no permission beyond a session; another person's device answers 404
    `not_found`."""
    # Ungated by design: self.
    return PasskeyOut.model_validate(passkey_logic.passkey_out(passkey_logic.rename_passkey(_principal(request), passkey_id, body.nickname)))


@router.delete("/me/passkeys/{passkey_id}", response={204: None}, auth=SessionAuth(), operation_id="removeMyPasskey", by_alias=True)
def remove_my_passkey(request: HttpRequest, passkey_id: uuid.UUID) -> tuple[int, None]:
    """Retires one of the caller's own devices, which is the first thing to do when one is lost.
    Needs no permission beyond a session, but a recent sign-in or a fresh passkey check (403
    `step_up_required`), since it removes an authentication factor. The last live passkey is
    refused with 409 `last_passkey`: with no password anywhere, removing it would lock the
    person out."""
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
    """Where the caller is signed in right now, with the browser, the time last seen and which row
    is this very session. Needs no permission beyond a session. It is how somebody notices a
    sign-in they do not recognise."""
    # Ungated by design: self.
    principal = _principal(request)
    user = _actor_user(request)
    return [_session_out(row, principal.session_id) for row in session_logic.live_sessions(user, tenant_id=None)]


@router.delete("/me/sessions/{session_id}", response={204: None}, auth=SessionAuth(), operation_id="revokeMySession", by_alias=True)
def revoke_my_session(request: HttpRequest, session_id: uuid.UUID) -> tuple[int, None]:
    """Ends one of the caller's own sign-ins, on a device they no longer have with them. Needs no
    permission beyond a session; a session that is not theirs answers 404 `not_found`."""
    # Ungated by design: self.
    session_logic.revoke_own_session(_principal(request), session_id, request)
    return 204, None


# ---------------------------------------------------------------------------------------
# Tenant admin: members (members.manage)
# ---------------------------------------------------------------------------------------
@router.get("/tenant/members", response=MembersPage, auth=SessionAuth(), operation_id="listMembers", by_alias=True)
@requires_permission(perms.MEMBERS_MANAGE)
def list_members(request: HttpRequest, page: PageQuery = Query(...)) -> MembersPage:
    """The bank's people, with the roles they hold, how many devices can sign them in, and how many
    sessions are live. Needs `members.manage`, or the answer is 403 `permission_denied`. It is
    the administrator's working list: who is still to enrol, who has left, and who holds what."""
    items, total = members_logic.list_members(_tenant_id(request), _order(request), limit=page.limit, offset=page.offset)
    return MembersPage(items=[MemberOut.model_validate(item) for item in items], total=total)


@router.post("/tenant/members", response={201: InvitationOut}, auth=SessionAuth(), operation_id="inviteMember", by_alias=True)
@requires_permission(perms.MEMBERS_MANAGE)
def invite_member(request: HttpRequest, body: MemberInvite) -> tuple[int, InvitationOut]:
    """Invites somebody to the bank with the roles they will hold, and sends the invitation. Needs
    `members.manage`. An address that is already a member answers 409 `already_member`, a
    malformed one 422 `invalid_email`, no roles 422 `roles_required`, and an unknown role 422
    `unknown_key`. The invited person enrols their own passkey; nobody here ever sets a
    password."""
    actor_user = _actor_user(request)
    invitation = members_logic.invite_member(
        tenant=_tenant(request), actor=session_logic.actor_of(actor_user), invited_by=actor_user, email=body.email, role_keys=body.role_keys, title=body.title
    )
    return 201, InvitationOut.model_validate(members_logic.invitation_out(invitation, _order(request)))


@router.patch("/tenant/members/{user_id}", response=MemberOut, auth=SessionAuth(), operation_id="updateMember", by_alias=True)
@requires_permission(perms.MEMBERS_MANAGE)
def update_member(request: HttpRequest, user_id: uuid.UUID, body: MemberPatch) -> MemberOut:
    """Changes a member's roles or their title. Needs `members.manage`, and changing roles needs a
    fresh passkey check (403 `step_up_required`), because it changes what somebody may do.
    Taking `members.manage` from the last administrator answers 409 `last_admin`, an unknown
    role 422 `unknown_key`, and a person who is not a member 404 `not_found`."""
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
    """Ends a person's access to the bank and revokes every session they hold, for the day they
    leave. Needs `members.manage`, and the last administrator answers 409 `last_admin`. Their
    work, decisions and audit trail stay exactly as they are: nothing is deleted."""
    members_logic.deactivate_member(tenant=_tenant(request), actor=session_logic.actor_of(_actor_user(request)), user_id=user_id, request=request)
    return 204, None


@router.get("/tenant/members/{user_id}/sessions", response=list[SessionOut], auth=SessionAuth(), operation_id="listMemberSessions", by_alias=True)
@requires_permission(perms.MEMBERS_MANAGE)
def list_member_sessions(request: HttpRequest, user_id: uuid.UUID) -> list[SessionOut]:
    """Where one member is signed in right now, for the administrator asked whether a lost laptop
    still has a live session. Needs `members.manage`; somebody who is not a member of this bank
    answers 404 `not_found`."""
    return [_session_out(row, None) for row in members_logic.member_sessions(_tenant_id(request), user_id)]


@router.delete("/tenant/members/{user_id}/sessions", response={204: None}, auth=SessionAuth(), operation_id="revokeMemberSessions", by_alias=True)
@requires_permission(perms.MEMBERS_MANAGE)
def revoke_member_sessions(request: HttpRequest, user_id: uuid.UUID) -> tuple[int, None]:
    """Signs one member out everywhere in a single call, when a device is lost or somebody leaves.
    Needs `members.manage`. Their passkeys stay, so they can sign in again on a device they
    still hold, unless the bank has also ended their access."""
    members_logic.revoke_member_sessions(tenant=_tenant(request), actor=session_logic.actor_of(_actor_user(request)), user_id=user_id, request=request)
    return 204, None


@router.post("/tenant/members/{user_id}/reissue-enrolment", response={202: Empty}, auth=SessionAuth(), operation_id="reissueEnrolment", by_alias=True)
@requires_permission(perms.MEMBERS_MANAGE)
@requires_step_up
def reissue_enrolment(request: HttpRequest, user_id: uuid.UUID) -> tuple[int, Empty]:
    """Puts a member who has lost every device back on a one-time code, so they can enrol a new
    passkey. Needs `members.manage` and a fresh passkey check (403 `step_up_required`): this is
    the way back in, so an administrator confirms it with their own device. Somebody who is not
    a member answers 404 `not_found`. Every re-issue is audited and shows in the bank's security
    log."""
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
    """The invitations and re-enrolments still outstanding, with when each one runs out. Needs
    `members.manage`. It answers the administrator's question of who has been asked to join and
    has not come in yet."""
    items, total = members_logic.list_invitations(_tenant_id(request), _order(request), limit=page.limit, offset=page.offset)
    return InvitationsPage(items=[InvitationOut.model_validate(item) for item in items], total=total)


@router.post("/tenant/invitations/{invitation_id}/resend", response=InvitationOut, auth=SessionAuth(), operation_id="resendInvitation", by_alias=True)
@requires_permission(perms.MEMBERS_MANAGE)
def resend_invitation(request: HttpRequest, invitation_id: uuid.UUID) -> InvitationOut:
    """Sends the invitation again, with a fresh link and a fresh window, for the mail that never
    arrived. Needs `members.manage`. An invitation already accepted, withdrawn or out of date
    answers 409 `invitation_closed`, and one belonging to another bank 404 `not_found`."""
    tenant = _tenant(request)
    invitation = members_logic.tenant_invitation(tenant.id, invitation_id)
    issued = invitation_logic.resend_invitation(tenant=tenant, invitation=invitation, actor=session_logic.actor_of(_actor_user(request)))
    return InvitationOut.model_validate(members_logic.invitation_out(issued.invitation, _order(request)))


@router.delete("/tenant/invitations/{invitation_id}", response={204: None}, auth=SessionAuth(), operation_id="revokeInvitation", by_alias=True)
@requires_permission(perms.MEMBERS_MANAGE)
def revoke_invitation(request: HttpRequest, invitation_id: uuid.UUID) -> tuple[int, None]:
    """Withdraws an outstanding invitation, so its link stops working. Needs `members.manage`; an
    invitation belonging to another bank answers 404 `not_found`. The row itself stays, for the
    audit trail."""
    tenant = _tenant(request)
    invitation = members_logic.tenant_invitation(tenant.id, invitation_id)
    invitation_logic.revoke_invitation(tenant=tenant, invitation=invitation, actor=session_logic.actor_of(_actor_user(request)))
    return 204, None


# ---------------------------------------------------------------------------------------
# Roles (ID-09)
# ---------------------------------------------------------------------------------------
@router.get("/tenant/roles", response=list[RoleOut], auth=SessionAuth(), operation_id="listRoles", by_alias=True)
def list_roles(request: HttpRequest) -> list[RoleOut]:
    """The bank's roles with their labels, usage notes and permissions. Needs no permission beyond
    a session: every picker and every screen that names a role needs the labels. What a person
    may actually do is the permission list on `GET /me`, never a role's name."""
    # Ungated by design: capability (any member; pickers need labels).
    order = _order(request)
    return [RoleOut.model_validate(roles_logic.role_out(role, order)) for role in roles_logic.tenant_roles(_tenant_id(request))]


@router.post("/tenant/roles", response={201: RoleOut}, auth=SessionAuth(), operation_id="createRole", by_alias=True)
@requires_permission(perms.ROLES_MANAGE)
@requires_step_up
def create_role(request: HttpRequest, body: RoleCreate) -> tuple[int, RoleOut]:
    """Adds a role of the bank's own beside the seven the product ships, for a bank whose structure
    needs one. Needs `roles.manage` and a fresh passkey check (403 `step_up_required`), since it
    creates a bundle of permissions. A key already taken answers 409 `duplicate_key`, an empty
    key 422 `key_required`, no label 422 `label_required`, and an unknown permission or language
    422 `unknown_key`."""
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
    """Relabels a role, rewrites its usage note, or changes what it may do. Needs `roles.manage`,
    and changing the permissions needs a fresh passkey check (403 `step_up_required`). A system
    role's permissions answer 422 `system_role`: a bank relabels those but cannot change what
    they may do, so an upgrade never quietly changes who can approve. An unknown permission or
    language answers 422 `unknown_key`."""
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
    """Retires one of the bank's own roles, so nobody can be given it again while the audit trail
    keeps it. Needs `roles.manage`. A role somebody still holds answers 409 `role_in_use`, so
    the bank reassigns those people first, and a system role answers 422 `system_role`."""
    tenant = _tenant(request)
    role = roles_logic.tenant_role_by_key(tenant.id, key)
    role = roles_logic.retire_role(tenant=tenant, actor=session_logic.actor_of(_actor_user(request)), role=role)
    return RoleOut.model_validate(roles_logic.role_out(role, _order(request)))


@router.get("/reference/permissions", response=list[PermissionOut], auth=SessionAuth(), operation_id="listPermissions", by_alias=True)
def list_permissions(request: HttpRequest) -> list[PermissionOut]:
    """Every permission a role can be given, grouped by area and described in the words the role
    editor shows. Needs no permission beyond a session. The set is fixed in code, one per
    capability the product has, and a bank composes its roles from it."""
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
    """The bank's API keys, with what each may reach and when it was last used, revoked ones
    included. Needs `integrations.manage`. The secret itself is not here: it was shown once,
    when the key was created."""
    items, total = api_keys_logic.list_api_keys(_tenant_id(request), limit=page.limit, offset=page.offset)
    return ApiKeysPage(items=[ApiKeyOut.model_validate(row) for row in items], total=total)


@router.post("/tenant/api-keys", response={201: ApiKeyCreated}, auth=SessionAuth(), operation_id="createApiKey", by_alias=True)
@requires_permission(perms.INTEGRATIONS_MANAGE)
@requires_step_up
def create_api_key(request: HttpRequest, body: ApiKeyCreate) -> tuple[int, ApiKeyCreated]:
    """Issues an API key for one of the bank's own integrations or agents, and hands back the
    secret in the only answer that will ever carry it. Needs `integrations.manage` and a fresh
    passkey check (403 `step_up_required`). No name answers 422 `name_required`, no scope 422
    `scopes_required`, an unknown scope 422 `unknown_key`, and an expiry already past 422
    `expiry_in_past`. No scope reaches the shared library: an agent proposes, it never writes."""
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
    """Stops a key working, the moment an integration is retired or a secret may have leaked. Needs
    `integrations.manage`; a key of another bank answers 404 `not_found`. The row stays,
    revoked, for the audit trail."""
    api_keys_logic.revoke_api_key(tenant=_tenant(request), actor=session_logic.actor_of(_actor_user(request)), key_id=key_id)
    return 204, None


@router.get("/tenant/security-log", response=SecurityLogPage, auth=SessionAuth(), operation_id="listSecurityLog", by_alias=True)
@requires_permission(perms.SECURITY_MANAGE)
def list_security_log(request: HttpRequest, page: PageQuery = Query(...)) -> SecurityLogPage:
    """The bank's own record of sign-ins, failures, code requests, revocations and key use, newest
    first. Needs `security.manage`. It is what a bank's security review and a vendor assessment
    read, so it holds the attempts that failed as well as the ones that worked."""
    items, total = security_log.list_events(_tenant_id(request), limit=page.limit, offset=page.offset)
    return SecurityLogPage(items=[SecurityEventOut.model_validate(row) for row in items], total=total)
