"""Routes of the identity app (playbook 4.1: auth class, permission, step-up, nothing
else). Operation ids are explicit and camelCase so the audit-on-write guard can find
each mutating route by name in tests_scenarios.py."""

import string
import uuid
from collections.abc import Callable
from typing import TypeVar, cast

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from ninja import Path, Query, Router

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
from apps.identity.models import ApiKey, User
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
    ENROLMENT_SESSION_EXAMPLE,
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
    MEMBER_SESSIONS_EXAMPLE,
    MY_PASSKEYS_EXAMPLE,
    MY_SESSIONS_EXAMPLE,
    PasskeyAssertBody,
    PasskeyOut,
    PasskeyPatch,
    PasskeyRegisterBody,
    PasskeyRegistered,
    PERMISSIONS_EXAMPLE,
    PermissionOut,
    RefreshResult,
    RoleCreate,
    ROLES_EXAMPLE,
    RoleOut,
    RoleRef,
    RolePatch,
    SecurityEventOut,
    SecurityLogPage,
    SessionOut,
    SessionTokens,
    STEP_UP_OPTIONS_EXAMPLE,
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
#
# Each route's docstring is its published `description` (django-ninja reads it), written for
# an integrator who has never seen this codebase: when to call it, what it changes, what it
# needs, what it leaves in the audit and security logs, and which RFC 9457 `code` to branch
# on (docs/plans/briefs/API_DOCUMENTATION.md). Every number it quotes that is a setting is a
# `$placeholder` that `_quoting_settings` fills in, so the contract follows the setting.
# ---------------------------------------------------------------------------------------
_View = TypeVar("_View", bound=Callable[..., object])

_SETTINGS_IN_DOCS = {
    "challenge_seconds": settings.CHALLENGE_TTL_SECONDS,
    "step_up_minutes": settings.STEP_UP_FRESHNESS_MINUTES,
    "replay_grace_seconds": settings.REFRESH_REPLAY_GRACE_SECONDS,
    "idle_minutes": settings.SESSION_IDLE_MINUTES_DEFAULT,
    "absolute_hours": settings.SESSION_ABSOLUTE_HOURS_DEFAULT,
    "invitation_hours": settings.INVITATION_TTL_HOURS,
    "code_digits": settings.ENROLMENT_CODE_DIGITS,
    "code_minutes": settings.ENROLMENT_CODE_TTL_MINUTES,
    "code_attempts": settings.ENROLMENT_CODE_MAX_ATTEMPTS,
    "codes_per_address_hour": settings.ENROLMENT_CODE_RATE_PER_ADDRESS_PER_HOUR,
    "codes_per_ip_hour": settings.ENROLMENT_CODE_RATE_PER_IP_PER_HOUR,
    "auth_calls_per_ip_minute": settings.AUTH_RATE_PER_IP_PER_MINUTE,
}


def _quoting_settings(view: _View) -> _View:
    """Fill the `$placeholders` in a route's docstring from the settings. It sits under the
    route decorator, so it runs before Ninja reads the docstring; an unknown placeholder
    fails the import rather than reaching the contract."""
    view.__doc__ = string.Template(view.__doc__ or "").substitute(_SETTINGS_IN_DOCS)
    return view


def _example(status: int, value: object) -> dict[str, object]:
    """An example answer for an operation whose response schema cannot carry one itself."""
    return {"responses": {status: {"content": {"application/json": {"example": value}}}}}


@router.post(
    "/auth/invitations/open",
    response={202: Empty},
    auth=None,
    operation_id="openInvitation",
    by_alias=True,
    summary="Open your invitation link and get an enrolment code by email",
)
@_quoting_settings
def open_invitation(request: HttpRequest, body: InvitationOpenBody) -> tuple[int, Empty]:
    """Call this when an invitee opens the link in their invitation email: the page reads the
    token from the link's fragment (`/invite#<token>`) and posts it here. A valid token sends
    a one-time enrolment code to the invited address, $code_digits digits and good for
    $code_minutes minutes, which the invitee then sends with the same token to
    `POST /auth/invitations/verify`. The code is for enrolment only: it opens an enrolment
    session that can register a passkey, never a full sign-in. Opening the link again sends
    a fresh code and retires the earlier one.
    The code is never returned here: the answer is 202 with an empty body.

    No session is needed; the single-use token is the grant. It writes a code-sent entry to
    the inviting bank's security log and the audit event `invitation.opened`.

    Errors: `invitation_expired` (410) when the token is unknown, already used, past its
    $invitation_hours hours, or revoked or replaced by an administrator; `rate_limited` (429)
    past $auth_calls_per_ip_minute calls a minute from one network address, one allowance
    shared by opening an invitation, both code checks and both halves of passkey sign-in, or
    past $codes_per_address_hour codes an hour for one invited address or
    $codes_per_ip_hour an hour from one network address, counted together with
    `POST /auth/code/request`; `validation_error` (422) for a missing token or one over 128
    characters.
    """
    # Ungated by design: public-token (the single-use token is the grant). It rides in the
    # body, never the path, so no request line holds it (security review F29).
    invitation_logic.open_invitation(body.token, request)
    return 202, Empty()


@router.post(
    "/auth/invitations/verify",
    response=SessionTokens,
    auth=None,
    operation_id="verifyInvitationCode",
    by_alias=True,
    summary="Trade your invitation code for an enrolment session",
    openapi_extra=_example(200, ENROLMENT_SESSION_EXAMPLE),
)
@_quoting_settings
def verify_invitation_code(request: HttpRequest, body: InvitationCodeVerifyBody, response: HttpResponse) -> SessionTokens:
    """The second step of joining by invitation: send the token from the link and the code
    from the email. A right code opens an enrolment session in the inviting bank and answers
    with its access token (`sessionKind` `enrolment`); the refresh token arrives as an
    `HttpOnly` cookie scoped to `/api/v1/auth`. The enrolment session can do two things,
    register a passkey and read `GET /me`, and every other route answers 403
    `enrolment_only`. Registering the first passkey ends it and starts a full session.

    No session is needed: the token and the code together are the grant, so no email address
    travels on this path, and only a code sent to the invitation's own address verifies. A
    code works once; each wrong try spends one of its $code_attempts attempts, after which
    even the right code is refused. Failures are written to the bank's security log; success
    writes the audit event `session.created`.

    Errors: `invitation_expired` (410) when the token is unknown, used, expired or revoked;
    `invalid_code` (400) for a wrong or expired code or when none is waiting, one answer for
    all of them; `code_locked` (400) once the attempts are spent, when the invitee opens the
    link again for a new code; `rate_limited` (429) past $auth_calls_per_ip_minute calls a
    minute from one network address, one allowance shared by opening an invitation, both
    code checks and both halves of passkey sign-in; `validation_error` (422) for a missing
    field or one over its length.
    """
    # Ungated by design: public-token (the single-use token and the code are the grant).
    return _session_response(code_logic.verify_invitation_code(body.token, body.code, request), response)


@router.post(
    "/auth/code/request",
    response={202: Empty},
    auth=None,
    operation_id="requestCode",
    by_alias=True,
    summary="Ask for an enrolment code by email to finish joining",
)
@_quoting_settings
def request_code(request: HttpRequest, body: CodeRequestBody) -> tuple[int, Empty]:
    """The "First time here?" path, for an invitee who has their invitation but not its link
    to hand: post the invited address and, when it has an open invitation and no passkey
    yet, a one-time enrolment code is emailed to it. The invitee then sends the address and
    the code to `POST /auth/code/verify`. Asking again sends a fresh code and retires the
    earlier one.

    The answer is the same 202 with an empty body whatever the address, invited, enrolled or
    unknown, and the server does the same hashing work for each: the answer never says
    whether the address has an account, and the rate limits below bound what the response
    time could hint. An address that already holds a passkey is sent nothing: the code is
    for enrolment only and never a way around a passkey. There is no password and no
    self-service recovery; a person who has lost every passkey asks their bank's
    administrator to re-issue their enrolment.

    No session is needed. Every call writes the audit event `auth.code_requested`, which
    names the account only when the address is known; a code sent, and a code refused to an
    enrolled address, are also written to the security log.

    Errors: `rate_limited` (429) past $codes_per_address_hour requests an hour for one
    address or $codes_per_ip_hour an hour from one network address, counted together with
    opening invitation links and whether or not the address is known; `validation_error`
    (422) for a missing address or one over 254 characters.
    """
    # Ungated by design: bootstrap. Neutral answer whatever the address (AC-ID1).
    code_logic.request_code(body.email, request)
    return 202, Empty()


@router.post(
    "/auth/code/verify",
    response=SessionTokens,
    auth=None,
    operation_id="verifyCode",
    by_alias=True,
    summary="Trade the code emailed to your address for an enrolment session",
    openapi_extra=_example(200, ENROLMENT_SESSION_EXAMPLE),
)
@_quoting_settings
def verify_code(request: HttpRequest, body: CodeVerifyBody, response: HttpResponse) -> SessionTokens:
    """The second step of the "First time here?" path: send the invited address and the code
    emailed to it. A right code opens an enrolment session in the bank whose invitation is
    the newest open one for that address, and answers with its access token (`sessionKind`
    `enrolment`); the refresh token arrives as an `HttpOnly` cookie scoped to
    `/api/v1/auth`. The enrolment session reaches only passkey registration and `GET /me`;
    every other route answers 403 `enrolment_only` until the first passkey is registered.

    No session is needed. A code works once; each wrong try spends one of its $code_attempts
    attempts, after which even the right code is refused and a new one must be requested. A
    right code for an address with no open invitation, or one that already holds a passkey,
    is refused like a wrong one. Failures are written to the security log; success writes
    the audit event `session.created`.

    Errors: `invalid_code` (400) for a wrong, expired or missing code or a closed invitation,
    one answer for all of them; `code_locked` (400) once the attempts are spent;
    `rate_limited` (429) past $auth_calls_per_ip_minute calls a minute from one network
    address, one allowance shared by opening an invitation, both code checks and both halves
    of passkey sign-in; `validation_error` (422) for a missing field or one over its length.
    """
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
    summary="Start registering a passkey",
)
@_quoting_settings
def passkey_register_options(request: HttpRequest) -> WebAuthnCreationOptions:
    """The first half of the registration ceremony: returns the options to pass to
    `navigator.credentials.create({publicKey: ...})`, byte members base64url-encoded in
    WebAuthn's JSON form, which `PublicKeyCredential.parseCreationOptionsFromJSON()` reads as
    they are. Call it when a person enrols their first passkey from an enrolment session or
    adds another from a full session, then send the browser's answer to
    `POST /auth/passkeys/register/verify`.

    The options ask for a discoverable passkey with user verification required, from any
    kind of authenticator and with no attestation, and list the person's existing passkeys so
    the same authenticator is not registered twice. The challenge inside works once, only for
    this person and session, and expires after $challenge_seconds seconds.

    Needs a session of either kind and no permission: a person can only ever register a
    passkey for their own account. It stores the challenge and writes the audit event
    `auth.challenge_issued`.

    Errors: `unauthenticated` (401) without a live session.
    """
    # Ungated by design: capability (the enrolment or full session is the grant).
    return WebAuthnCreationOptions.model_validate(passkey_logic.registration_options(_principal(request)))


@router.post(
    "/auth/passkeys/register/verify",
    response={201: PasskeyRegistered},
    auth=[SessionAuth(), EnrolmentAuth()],
    operation_id="passkeyRegisterVerify",
    by_alias=True,
    summary="Finish registering a passkey",
)
@_quoting_settings
def passkey_register_verify(request: HttpRequest, body: PasskeyRegisterBody, response: HttpResponse) -> tuple[int, PasskeyRegistered]:
    """The second half of the registration ceremony: send the credential the browser returned
    from `navigator.credentials.create()`, in its JSON form, and optionally a name. The server
    checks the challenge, the page's origin, the domain and that the person was verified,
    then stores the passkey (its credential ID, public key, signature counter, transports,
    authenticator model and backup flags) and answers 201 with it. With no name given it
    names the passkey from the device; the person may rename it later.

    From an enrolment session this completes enrolment: the invitation is accepted, the
    person becomes a member of the bank with the roles they were invited with, the account
    turns active and the emailed code stops working for good, the enrolment session is
    revoked, and a full session starts with this response, its access token in the body and
    its refresh token as an `HttpOnly` cookie. A screen then offers a second passkey. From a
    full session it adds a passkey and the session carries on; adding an authentication
    factor needs a session younger than $step_up_minutes minutes or a fresh passkey step-up.

    Needs a session of either kind and no permission. It writes an enrolled entry to the
    security log and the audit event `passkey.registered` with the name, how it was chosen,
    the device type and the authenticator model; completing an enrolment also writes
    `session.revoked` and `session.created`.

    Errors: `challenge_expired` (400) when the challenge is unknown, used or older than its
    lifetime, and start again from the options call; `invalid_credential` (400) when the
    credential cannot be read; `registration_failed` (400) when it does not verify or that
    passkey is already registered; `step_up_required` (403) when a full session is older
    than the step-up window and holds no fresh assertion; `platform_account` (422) when a
    bank invitation reaches an account that has since become platform staff;
    `unauthenticated` (401) without a live session; `validation_error` (422) for a malformed
    body.
    """
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


@router.post(
    "/auth/passkeys/authenticate/options",
    response=WebAuthnRequestOptions,
    auth=None,
    operation_id="passkeyAuthenticateOptions",
    by_alias=True,
    summary="Start signing in with a passkey",
)
@_quoting_settings
def passkey_authenticate_options(request: HttpRequest) -> WebAuthnRequestOptions:
    """The first half of sign-in: returns the options to pass to
    `navigator.credentials.get({publicKey: ...})`, or to
    `PublicKeyCredential.parseRequestOptionsFromJSON()`. No username is asked for:
    `allowCredentials` is empty, so the browser offers whichever passkeys the person holds
    for this domain and the account is found from the one that answers. Then send the
    browser's answer to `POST /auth/passkeys/authenticate/verify`.

    No session is needed. Each call stores a single-use challenge that expires after
    $challenge_seconds seconds and writes the audit event `auth.challenge_issued`; no
    account is read or revealed.

    Errors: `rate_limited` (429) past $auth_calls_per_ip_minute calls a minute from one
    network address, one allowance shared by opening an invitation, both code checks and
    both halves of passkey sign-in, so each sign-in spends two.
    """
    # Ungated by design: bootstrap.
    return WebAuthnRequestOptions.model_validate(passkey_logic.authentication_options(request))


@router.post(
    "/auth/passkeys/authenticate/verify",
    response=SessionTokens,
    auth=None,
    operation_id="passkeyAuthenticateVerify",
    by_alias=True,
    summary="Sign in with your passkey",
)
@_quoting_settings
def passkey_authenticate_verify(request: HttpRequest, body: PasskeyAssertBody, response: HttpResponse) -> SessionTokens:
    """The second half of sign-in: send the credential the browser returned from
    `navigator.credentials.get()`. The server finds the passkey by its credential ID and
    checks that the user handle names its owner, that the challenge is one it issued, the
    page's origin and the domain, that the person was verified, the signature, and that the
    signature counter moved forward, since one going backwards suggests a cloned
    authenticator. It then opens a full session and answers with its access token
    (`sessionKind` `full`); the refresh token arrives as an `HttpOnly` cookie scoped to
    `/api/v1/auth`.

    A member is signed in to their bank, the one they joined first when they belong to
    several, and platform staff to the platform. Signing in is not a step-up: a sensitive
    action still asks for its own passkey confirmation through `POST /auth/step-up/options`.

    No session is needed. Success records the passkey's use and writes a sign-in entry to
    the security log and the audit event `session.created`; a refusal writes a failed
    sign-in with its reason to the security log, and tells the caller nothing more.

    Errors: `signin_failed` (401) for every refusal (an unknown or retired passkey, an
    account that is not active, a spent or expired challenge, a user handle naming someone
    else, a bad signature), one answer so a caller cannot tell them apart; `rate_limited`
    (429) past $auth_calls_per_ip_minute calls a minute from one network address, one
    allowance shared by opening an invitation, both code checks and both halves of passkey
    sign-in; `validation_error` (422) for a malformed body.
    """
    # Ungated by design: bootstrap.
    bundle = passkey_logic.verify_authentication(body.credential.model_dump(by_alias=True, exclude_none=True), request)
    return _session_response(bundle, response)


@router.post(
    "/auth/step-up/options",
    response=WebAuthnRequestOptions,
    auth=SessionAuth(),
    operation_id="stepUpOptions",
    by_alias=True,
    summary="Start confirming a sensitive action with your passkey",
    openapi_extra=_example(200, STEP_UP_OPTIONS_EXAMPLE),
)
@_quoting_settings
def step_up_options(request: HttpRequest) -> WebAuthnRequestOptions:
    """The first half of a step-up. A sensitive action (an approval, a sign-off, a footprint
    change, an export, a key, a role or security change, a re-enrolment) answers 403
    `step_up_required` unless the session holds a passkey assertion younger than
    $step_up_minutes minutes. Call this, pass the options to
    `navigator.credentials.get({publicKey: ...})`, send the answer to
    `POST /auth/step-up/verify`, then repeat the action.

    The options list the caller's own live passkeys in `allowCredentials`, so no other
    account's passkey can confirm, and require user verification. The challenge works once,
    only for this person and session, and expires after $challenge_seconds seconds.

    Needs a full session and no permission; an agent's API key can never step up. It stores
    the challenge and writes the audit event `auth.challenge_issued`.

    Errors: `unauthenticated` (401) without a live session; `enrolment_only` (403) from an
    enrolment session.
    """
    # Ungated by design: self.
    return WebAuthnRequestOptions.model_validate(passkey_logic.step_up_options(_principal(request)))


@router.post(
    "/auth/step-up/verify",
    response=StepUpResult,
    auth=SessionAuth(),
    operation_id="stepUpVerify",
    by_alias=True,
    summary="Confirm a sensitive action with your passkey",
)
@_quoting_settings
def step_up_verify(request: HttpRequest, body: PasskeyAssertBody) -> StepUpResult:
    """The second half of a step-up: send the credential the browser returned. The server
    checks that the passkey is one of the caller's own live ones, the challenge, the origin
    and the domain, user verification, the signature and the counter, then records the
    assertion on this session and answers with its identifier and until when it counts as
    fresh, $step_up_minutes minutes. Until then every sensitive action on this session may proceed, and
    each writes the assertion's identifier onto its own audit event. It covers this session
    only; another device steps up for itself.

    Needs a full session and no permission; an agent's API key can never step up. Success
    records the passkey's use and writes a step-up entry to the security log and the audit
    event `step_up.asserted`; a refusal writes a failed step-up with its reason to the
    security log.

    Errors: `step_up_failed` (400) for every refusal (a passkey that is not the caller's or
    is retired, a spent or expired challenge, a user handle naming someone else, a bad
    signature); `unauthenticated` (401) without a live session; `enrolment_only` (403) from
    an enrolment session; `validation_error` (422) for a malformed body.
    """
    # Ungated by design: self.
    assertion = passkey_logic.verify_step_up(_principal(request), body.credential.model_dump(by_alias=True, exclude_none=True), request)
    return StepUpResult(assertion_id=assertion.id, expires_at=passkey_logic.step_up_valid_until(assertion))


# ---------------------------------------------------------------------------------------
# Sessions (D-06)
# ---------------------------------------------------------------------------------------
@router.post(
    "/auth/refresh",
    response=RefreshResult,
    auth=None,
    operation_id="refreshSession",
    by_alias=True,
    summary="Keep your session going with a fresh access token",
)
@_quoting_settings
def refresh_session(request: HttpRequest, response: HttpResponse) -> RefreshResult:
    """Call this shortly before the access token expires. It takes no body and no
    `Authorization` header: the credential is the `HttpOnly` refresh cookie that sign-in set,
    scoped to `/api/v1/auth`, so a browser client calls it with credentials included. The
    answer carries a new access token, and the refresh token is rotated: the response sets a
    new cookie and the old one stops working.

    Two tabs refreshing at once are safe: the previous refresh token presented within
    $replay_grace_seconds seconds of its rotation gets a fresh access token without rotating
    again. Presented any later it is treated as stolen, the whole session is revoked and the
    replay is written to the security log. A session also ends after $idle_minutes minutes
    without a refresh or $absolute_hours hours after sign-in, and a revoked one cannot be
    refreshed.

    Writes the audit event `session.refreshed`; a session that ends here writes
    `session.revoked`.

    Errors: `unauthenticated` (401) when the cookie is missing, unreadable or replayed late,
    or its session is revoked, idle too long or past its absolute limit: sign in again.
    """
    # Ungated by design: bootstrap (the cookie is the credential).
    access_token, expires_in, new_refresh = session_logic.refresh(request.COOKIES.get(settings.REFRESH_COOKIE_NAME), request)
    if new_refresh is not None:
        session_logic.set_refresh_cookie(response, new_refresh)
    return RefreshResult(access_token=access_token, expires_in=expires_in)


@router.post(
    "/auth/sign-out",
    response={204: None},
    auth=None,
    operation_id="signOut",
    by_alias=True,
    summary="Sign out on this device",
)
def sign_out(request: HttpRequest, response: HttpResponse) -> tuple[int, None]:
    """Revokes the session behind the refresh cookie and clears the cookie, so neither token
    works again; drop the access token from memory as well. It answers 204 whatever the state
    of the cookie, present, missing, stale or already signed out, so it is always safe to
    call. It signs out this device only; `DELETE /me/sessions/{session_id}` signs out
    another.

    No `Authorization` header is needed: the refresh cookie, sent because it is scoped to
    `/api/v1/auth`, names the session and carries its secret, which is the proof. A cookie
    that names a session without holding its current secret signs nobody out. A live
    session is revoked with an entry in the security log and the audit event
    `session.revoked`; a call that proves no live session still writes the audit event
    `session.sign_out_without_session`. There is no error code to branch on.
    """
    # Ungated by design: bootstrap.
    session_logic.sign_out(request.COOKIES.get(settings.REFRESH_COOKIE_NAME), request)
    session_logic.clear_refresh_cookie(response)
    return 204, None


# ---------------------------------------------------------------------------------------
# /me (self)
# ---------------------------------------------------------------------------------------
@router.get(
    "/me",
    response=Me,
    auth=[SessionAuth(), EnrolmentAuth()],
    operation_id="getMe",
    by_alias=True,
    summary="Read who you are and what you may do",
)
def get_me(request: HttpRequest) -> Me:
    """The first call every screen makes after sign-in: the signed-in person, the bank the
    session belongs to, their roles and the permissions those roles grant, whether enrolment
    is still pending, how many passkeys they hold, whether a step-up is fresh, the counts
    behind Today's "Decide now" panel and when they last marked the library as seen. Screens
    decide what to offer from `permissions`, never from a role's key.

    Both kinds of session may call it. An enrolment session sees `enrolmentPending` true, no
    roles and no permissions, and uses it to know a passkey is still to be registered. It
    reads only the caller's own account and bank, changes nothing and writes no audit event.

    Errors: `unauthenticated` (401) without a live session. An agent's API key is not a
    session and is refused the same way.
    """
    # Ungated by design: self. The enrolment session may call it (AC-ID2).
    return Me.model_validate(me_logic.me(_principal(request)))


@router.patch(
    "/me",
    response=Me,
    auth=SessionAuth(),
    operation_id="updateMe",
    by_alias=True,
    summary="Change your name or reading language",
)
def update_me(request: HttpRequest, body: MePatch) -> Me:
    """Updates the caller's own name, preferred language or both, and answers with the whole
    of `GET /me` as it now stands. Send only what changes: an omitted or null field is left
    alone. The name belongs to the account, so every bank the person is in shows the new
    one; the language decides which language their screens and labels use.

    Self-service: it needs a full session and no permission, and reaches no one else's
    account. It writes the audit event `user.updated` with the name and language before and
    after.

    Errors: `name_required` (422) for a blank name; `unknown_key` (422) for a language key
    that is not an active language; `validation_error` (422) for a name over 200 characters
    or a language key over 8; `unauthenticated` (401) without a live session;
    `enrolment_only` (403) from an enrolment session.
    """
    # Ungated by design: self.
    return Me.model_validate(me_logic.update_me(_principal(request), name=body.name, locale=body.locale))


@router.post(
    "/me/visit",
    response={204: None},
    auth=SessionAuth(),
    operation_id="markVisit",
    by_alias=True,
    summary="Mark the library as seen, so what is new is new to you",
)
def mark_visit(request: HttpRequest) -> tuple[int, None]:
    """Move your own "seen the library" bookmark to now, so that the library updates a
    bank reads next are the ones that arrived after this moment. A screen calls it when
    the reader has actually looked at the updates, not on every page load.

    It writes one column of one row: `lastVisitAt` on the caller's own membership of the
    bank the session is signed in to. It is a reading habit and not a judgement about a
    regulation, so it stays inside that bank, never reaches the shared library, and moves
    nobody else's bookmark — not a colleague's, and not the same person's bookmark in
    another bank they belong to. There is nothing to read back here: `GET /me` and the
    library-updates list carry the bookmark.

    Self-gated, so it asks for no permission and no scope: a signed-in member may move
    their own bookmark and the route addresses no one else's. It writes one audit event,
    `member.visited`, in that bank, carrying the bookmark before and after.

    Answers 204 with no body. Platform staff read the library itself rather than a bank's
    view of it and hold no membership, so a session with no bank answers 404 `not_found`
    and writes nothing; an expired or missing session answers 401.
    """
    # Ungated by design: self. Moves the caller's own "seen the library" bookmark; a
    # session with no tenant has no membership to move and answers 404.
    me_logic.mark_visit(_principal(request))
    return 204, None


_PASSKEY_ID = Path(
    ...,
    description=(
        "The identifier of one of your own passkeys, the UUID `GET /me/passkeys` returns as "
        "`id`. Another person's passkey, a retired one or an unknown identifier all answer "
        "`not_found` alike."
    ),
)
_SESSION_ID = Path(
    ...,
    description=(
        "The identifier of one of your own sessions in the bank this session is signed in to "
        "(on a platform session, one of your platform sessions), the UUID `GET /me/sessions` "
        "returns as `id`. Another person's session, one of yours in another bank or an "
        "unknown identifier all answer `not_found` alike."
    ),
)


@router.get(
    "/me/passkeys",
    response=list[PasskeyOut],
    auth=SessionAuth(),
    operation_id="listMyPasskeys",
    by_alias=True,
    summary="List your passkeys",
    openapi_extra=_example(200, MY_PASSKEYS_EXAMPLE),
)
def list_my_passkeys(request: HttpRequest) -> list[PasskeyOut]:
    """Every live passkey the caller holds, oldest first: its name, whether it is a synced
    passkey or bound to one device, the transports the browser reported, when it was
    registered and when it was last used. Retired passkeys are not listed, and the credential
    IDs and public keys stay on the server. An empty answer is a 200 with an empty list,
    though a signed-in person normally holds at least one.

    Self-service: needs a full session and no permission, and lists only the caller's own. It
    changes nothing and writes no audit event.

    Errors: `unauthenticated` (401) without a live session; `enrolment_only` (403) from an
    enrolment session.
    """
    # Ungated by design: self.
    return [PasskeyOut.model_validate(passkey_logic.passkey_out(row)) for row in passkey_logic.list_passkeys(_principal(request).subject_id)]


@router.patch(
    "/me/passkeys/{passkey_id}",
    response=PasskeyOut,
    auth=SessionAuth(),
    operation_id="renameMyPasskey",
    by_alias=True,
    summary="Rename one of your passkeys",
)
def rename_my_passkey(request: HttpRequest, body: PasskeyPatch, passkey_id: uuid.UUID = _PASSKEY_ID) -> PasskeyOut:
    """Gives one of the caller's own passkeys a new name and answers with the passkey as it
    now stands. The name is a label for the person's own list and changes nothing about how
    the passkey signs in; surrounding spaces are trimmed.

    Self-service: needs a full session, no permission and no step-up. It writes the audit
    event `passkey.renamed` with the name before and after.

    Errors: `not_found` (404) when the passkey does not exist, is retired or belongs to
    someone else, one answer for all three; `validation_error` (422) for a name over 100
    characters; `unauthenticated` (401) without a live session; `enrolment_only` (403) from
    an enrolment session.
    """
    # Ungated by design: self.
    return PasskeyOut.model_validate(passkey_logic.passkey_out(passkey_logic.rename_passkey(_principal(request), passkey_id, body.nickname)))


@router.delete(
    "/me/passkeys/{passkey_id}",
    response={204: None},
    auth=SessionAuth(),
    operation_id="removeMyPasskey",
    by_alias=True,
    summary="Remove one of your passkeys",
)
@_quoting_settings
def remove_my_passkey(request: HttpRequest, passkey_id: uuid.UUID = _PASSKEY_ID) -> tuple[int, None]:
    """Retires one of the caller's own passkeys: it stops working for sign-in and step-up at
    once and leaves the list. It is retired and not deleted, so its record stays for the
    audit trail. Sessions already open stay open; sign them out with
    `DELETE /me/sessions/{session_id}` if the passkey was lost. The last live passkey cannot
    be removed, because without one the person could not sign in again and there is no
    self-service recovery: add another first.

    Removing an authentication factor asks for a fresh proof of presence: a session younger
    than $step_up_minutes minutes or a passkey step-up on this session. It needs a full session and no
    permission, and writes the audit event `passkey.retired` with the passkey's name.

    Errors: `last_passkey` (409) for the only live passkey; `not_found` (404) when the
    passkey does not exist, is already retired or belongs to someone else;
    `step_up_required` (403) when the session is older than the step-up window and holds no
    fresh assertion; `unauthenticated` (401) without a live session; `enrolment_only` (403)
    from an enrolment session.
    """
    # Ungated by design: self. Removing an authentication factor needs a session younger
    # than the step-up window or a fresh assertion (F9, narrowed).
    # 409 last_passkey when it is the last live one.
    enforce_recent_sign_in_or_step_up(request)
    passkey_logic.remove_passkey(_principal(request), passkey_id)
    return 204, None


def _session_out(row: session_logic.UserSession, current_id: uuid.UUID | None) -> SessionOut:
    return SessionOut(id=row.id, current=row.id == current_id, created_at=row.created_at, last_seen_at=row.last_seen_at, ip=row.ip, user_agent=row.user_agent)


@router.get(
    "/me/sessions",
    response=list[SessionOut],
    auth=SessionAuth(),
    operation_id="listMySessions",
    by_alias=True,
    summary="See where you are signed in",
    openapi_extra=_example(200, MY_SESSIONS_EXAMPLE),
)
@_quoting_settings
def list_my_sessions(request: HttpRequest) -> list[SessionOut]:
    """Every live signed-in session the caller has in the bank this session is signed in to
    (on a platform session, their platform sessions), most recently active first: when it
    began, when it last refreshed, the network address and browser it came from, and
    `current` true for the one making this call. A person who belongs to several banks sees
    here only this bank's sessions; the ones in another bank stay inside that bank and
    cannot be listed or revoked from this session. Enrolment sessions, revoked ones and
    those past their $absolute_hours-hour limit are not listed; an idle one shows until its
    next refresh attempt ends it. An empty answer is a 200 with an empty list.

    Self-service: needs a full session and no permission, and lists only the caller's own. It
    changes nothing and writes no audit event.

    Errors: `unauthenticated` (401) without a live session; `enrolment_only` (403) from an
    enrolment session.
    """
    # Ungated by design: self.
    principal = _principal(request)
    user = _actor_user(request)
    return [_session_out(row, principal.session_id) for row in session_logic.live_sessions(user, tenant_id=None)]


@router.delete(
    "/me/sessions/{session_id}",
    response={204: None},
    auth=SessionAuth(),
    operation_id="revokeMySession",
    by_alias=True,
    summary="Sign out one of your devices",
)
def revoke_my_session(request: HttpRequest, session_id: uuid.UUID = _SESSION_ID) -> tuple[int, None]:
    """Revokes one of the caller's own sessions at once: its access token stops working on
    its next call and its refresh token can no longer renew it. Use it to sign out a lost or
    forgotten device from the list `GET /me/sessions` returns; revoking the current session
    signs this device out too. A session already revoked answers 204 and changes nothing.

    Self-service: needs a full session and no permission, and reaches only the caller's own
    sessions in the bank this session is signed in to. It writes an entry to the security
    log and the audit event `session.revoked`, with the reason that the person revoked it
    themselves.

    Errors: `not_found` (404) when the session does not exist, belongs to someone else or is
    one of the caller's own in another bank, one answer for all three; `unauthenticated`
    (401) without a live session; `enrolment_only` (403) from an enrolment session.
    """
    # Ungated by design: self.
    session_logic.revoke_own_session(_principal(request), session_id, request)
    return 204, None


# ---------------------------------------------------------------------------------------
# Tenant admin: members (members.manage). Each docstring is the route's published
# description (API_DOCUMENTATION.md).
# ---------------------------------------------------------------------------------------
_MEMBER_ID = Path(
    ...,
    description=(
        "The account identifier of a current member of the bank this session is signed in to, "
        "the UUID `GET /tenant/members` lists as `userId`. A deactivated member, a member of "
        "another bank or an unknown identifier all answer `not_found` alike."
    ),
)
_INVITATION_ID = Path(
    ...,
    description=(
        "The identifier of one of this bank's invitations, the UUID `GET /tenant/invitations` "
        "lists as `id`, never the token in the emailed link. Another bank's invitation or an "
        "unknown identifier answers `not_found`."
    ),
)
_ROLE_KEY = Path(
    ...,
    description=(
        "The stable key of one of this bank's roles, such as `dora_reviewer`, as "
        "`GET /tenant/roles` lists it; matched without regard to case or surrounding spaces. A "
        "retired role is still found here. A key the bank does not have answers `not_found`."
    ),
)
_API_KEY_ID = Path(
    ...,
    description=(
        "The identifier of one of this bank's own API keys, the UUID `GET /tenant/api-keys` "
        "lists as `id`, never the key itself. A platform key, another bank's key or an unknown "
        "identifier answers `not_found`."
    ),
)


@router.get(
    "/tenant/members",
    response=MembersPage,
    auth=SessionAuth(),
    operation_id="listMembers",
    by_alias=True,
    summary="See everyone who belongs to your bank",
)
@requires_permission(perms.MEMBERS_MANAGE)
def list_members(request: HttpRequest, page: PageQuery = Query(...)) -> MembersPage:
    """Returns the bank's members one page at a time, the earliest to join first: each
    person's name, address, roles and title, whether they can still sign in, how many
    passkeys they hold and how many sessions they have open in this bank. Deactivated
    members stay in the list with the status `deactivated`; people invited who have not
    enrolled yet are in `GET /tenant/invitations`. Role labels come in the caller's language.

    Needs `members.manage` on a person's session in the bank; API keys cannot reach it. It
    changes nothing and writes no audit event. An empty page is a 200 with an empty list.

    Errors: `validation_error` (422) when `limit` is above 100 or `offset` beyond the accepted
    depth; `permission_denied` (403) without `members.manage`; `unauthenticated` (401)
    without a live session; `enrolment_only` (403) from an enrolment session.
    """
    items, total = members_logic.list_members(_tenant_id(request), _order(request), limit=page.limit, offset=page.offset)
    return MembersPage(items=[MemberOut.model_validate(item) for item in items], total=total)


@router.post(
    "/tenant/members",
    response={201: InvitationOut},
    auth=SessionAuth(),
    operation_id="inviteMember",
    by_alias=True,
    summary="Invite a person to your bank with the roles they will hold",
)
@requires_permission(perms.MEMBERS_MANAGE)
@_quoting_settings
def invite_member(request: HttpRequest, body: MemberInvite) -> tuple[int, InvitationOut]:
    """Sends an invitation to a work email address and answers it with the status
    `pending`. The mail carries a link that works for $invitation_hours hours; opening it
    emails a one-time code, and the person enrols a passkey with it. Only when that first
    passkey is stored do they become a member, with the roles and title given here. An open
    invitation already sent to the same address by this bank is replaced and stops working.
    A deactivated member can be invited back this way and returns with the new roles.

    Needs `members.manage` on a person's session in the bank. Records the audit event
    `invitation.created` with the roles and the expiry; the token is never recorded.

    Errors: `already_member` (409) when the address belongs to a current member;
    `unknown_key` (422) for a role key the bank does not have or has retired;
    `invalid_email` (422) for an address without an `@`; `platform_account` (422) when the
    address belongs to platform staff, who never hold a bank membership;
    `validation_error` (422) for an empty role list or a field over its length;
    `permission_denied` (403) without `members.manage`; `unauthenticated` (401) without a
    live session.
    """
    actor_user = _actor_user(request)
    invitation = members_logic.invite_member(
        tenant=_tenant(request), actor=session_logic.actor_of(actor_user), invited_by=actor_user, email=body.email, role_keys=body.role_keys, title=body.title
    )
    return 201, InvitationOut.model_validate(members_logic.invitation_out(invitation, _order(request)))


@router.patch(
    "/tenant/members/{user_id}",
    response=MemberOut,
    auth=SessionAuth(),
    operation_id="updateMember",
    by_alias=True,
    summary="Change a member's roles or title",
)
@requires_permission(perms.MEMBERS_MANAGE)
@_quoting_settings
def update_member(request: HttpRequest, body: MemberPatch, user_id: uuid.UUID = _MEMBER_ID) -> MemberOut:
    """Changes what a member may do in this bank, their job title, or both, and answers the
    member as they now stand. `roleKeys` replaces the whole set of roles; what is left out
    of the body is kept. The change applies from the member's next call: their open sessions
    carry the new permissions at once.

    Needs `members.manage`, and, when `roleKeys` is sent, a passkey step-up on this session
    younger than $step_up_minutes minutes; changing only the title needs none. A bank always
    keeps at least one member holding `members.manage`, so no change may take it from the
    last one. Records the audit event `member.updated` with the roles and title before and
    after, and the step-up assertion when there was one.

    Errors: `step_up_required` (403) when `roleKeys` is sent without a fresh step-up, which
    the screen answers by opening the passkey prompt and retrying; `last_admin` (409) when
    the change would leave nobody holding `members.manage`; `roles_required` (422) for an
    empty role list; `unknown_key` (422) for a role the bank does not have or has retired;
    `not_found` (404) when the person is not a current member; `validation_error` (422) for
    a title over 200 characters; `permission_denied` (403) without `members.manage`;
    `unauthenticated` (401) without a live session.
    """
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


@router.delete(
    "/tenant/members/{user_id}",
    response={204: None},
    auth=SessionAuth(),
    operation_id="deactivateMember",
    by_alias=True,
    summary="Remove a person from your bank",
)
@requires_permission(perms.MEMBERS_MANAGE)
def deactivate_member(request: HttpRequest, user_id: uuid.UUID = _MEMBER_ID) -> tuple[int, None]:
    """Deactivates a member: every session they have open in this bank ends at once, any
    invitation or re-issued enrolment still open for their address here is closed, and they
    can no longer sign in to this bank. Nothing is deleted: the member stays listed with the
    status `deactivated` and everything they did stays in the audit trail. Their account and
    passkeys are left alone, because the same person may belong to another bank. To let them
    back in, invite them again.

    Needs `members.manage`. A bank always keeps at least one member holding
    `members.manage`, so the last one cannot be removed. Writes a "session_revoked" entry to
    the security log for each ended session, and the audit events `session.revoked` for each
    and `member.deactivated` with how many sessions and invitations were closed. Answers 204.
    Removing someone already removed answers `not_found`.

    Errors: `last_admin` (409) for the last member holding `members.manage`; `not_found`
    (404) when the person is not a current member; `permission_denied` (403) without
    `members.manage`; `unauthenticated` (401) without a live session.
    """
    members_logic.deactivate_member(tenant=_tenant(request), actor=session_logic.actor_of(_actor_user(request)), user_id=user_id, request=request)
    return 204, None


@router.get(
    "/tenant/members/{user_id}/sessions",
    response=list[SessionOut],
    auth=SessionAuth(),
    operation_id="listMemberSessions",
    by_alias=True,
    summary="See where a member is signed in to your bank",
    openapi_extra=_example(200, MEMBER_SESSIONS_EXAMPLE),
)
@requires_permission(perms.MEMBERS_MANAGE)
def list_member_sessions(request: HttpRequest, user_id: uuid.UUID = _MEMBER_ID) -> list[SessionOut]:
    """Every live signed-in session a member has in this bank, most recently active first:
    when it began, when it last refreshed, and the network address and browser it came from.
    Call it before signing a member out, for instance when a device is reported lost. Their
    sessions in any other bank are not listed and cannot be reached from here; enrolment
    sessions and ended ones are not listed either. `current` is always false in this list.
    An empty answer is a 200 with an empty list.

    Needs `members.manage`. It changes nothing and writes no audit event.

    Errors: `not_found` (404) when the person is not a current member; `permission_denied`
    (403) without `members.manage`; `unauthenticated` (401) without a live session.
    """
    return [_session_out(row, None) for row in members_logic.member_sessions(_tenant_id(request), user_id)]


@router.delete(
    "/tenant/members/{user_id}/sessions",
    response={204: None},
    auth=SessionAuth(),
    operation_id="revokeMemberSessions",
    by_alias=True,
    summary="Sign a member out of your bank on every device",
)
@requires_permission(perms.MEMBERS_MANAGE)
def revoke_member_sessions(request: HttpRequest, user_id: uuid.UUID = _MEMBER_ID) -> tuple[int, None]:
    """Ends every session the member has open in this bank at once: each access token stops
    working on its next call and no refresh token can renew it. Their passkeys and
    membership stay, so they can sign in again; to stop that too, remove the member or
    re-issue their enrolment. Sessions they hold in another bank are not touched. Answers 204
    also when there was nothing to end.

    Needs `members.manage`, and no step-up: ending sessions only takes access away. Writes a
    "session_revoked" entry to the security log for each session with the reason
    "revoked_by_admin", the audit event `session.revoked` for each, and
    `member.sessions_revoked` with how many there were.

    Errors: `not_found` (404) when the person is not a current member; `permission_denied`
    (403) without `members.manage`; `unauthenticated` (401) without a live session.
    """
    members_logic.revoke_member_sessions(tenant=_tenant(request), actor=session_logic.actor_of(_actor_user(request)), user_id=user_id, request=request)
    return 204, None


@router.post(
    "/tenant/members/{user_id}/reissue-enrolment",
    response={202: Empty},
    auth=SessionAuth(),
    operation_id="reissueEnrolment",
    by_alias=True,
    summary="Let a member who lost their passkeys enrol again",
    openapi_extra=_example(202, {}),
)
@requires_permission(perms.MEMBERS_MANAGE)
@requires_step_up
@_quoting_settings
def reissue_enrolment(request: HttpRequest, user_id: uuid.UUID = _MEMBER_ID) -> tuple[int, Empty]:
    """The only way back in for a member who lost every passkey, and the way to lock out a
    passkey that may be compromised. It retires every passkey the person holds, ends every
    session they have, in this bank and in any other, sets them back to `invited`, and
    emails them a re-enrolment link that works for $invitation_hours hours, keeping their
    roles and title. Every other member holding `members.manage`, apart from the caller, is
    told by email. The person enrols a new passkey through the link exactly as at their first
    enrolment. Answers 202 with `{}` once the mails are queued.

    Needs `members.manage` and a passkey step-up on this session younger than
    $step_up_minutes minutes. Writes "reenrolment_issued" and a "session_revoked" entry per
    ended session to the security log, and the audit events `session.revoked`,
    `enrolment.reissued` for the new invitation and `member.enrolment_reissued` with how many
    sessions and passkeys were affected and the step-up assertion.

    Errors: `step_up_required` (403) without a fresh step-up, which the screen answers by
    opening the passkey prompt and retrying; `not_found` (404) when the person is not a
    current member; `platform_account` (422) when the address belongs to platform staff;
    `permission_denied` (403) without `members.manage`; `unauthenticated` (401) without a
    live session.
    """
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


@router.get(
    "/tenant/invitations",
    response=InvitationsPage,
    auth=SessionAuth(),
    operation_id="listInvitations",
    by_alias=True,
    summary="See the invitations your bank has sent and where each stands",
)
@requires_permission(perms.MEMBERS_MANAGE)
def list_invitations(request: HttpRequest, page: PageQuery = Query(...)) -> InvitationsPage:
    """Returns the bank's invitations and re-issued enrolments one page at a time, newest
    first, in every status: `pending`, `accepted`, `revoked` and `expired`. Call it to see
    who has not enrolled yet and to resend or withdraw a link. The link's token is never
    listed. Role labels come in the caller's language.

    Needs `members.manage`. It changes nothing and writes no audit event. An empty page is a
    200 with an empty list.

    Errors: `validation_error` (422) when `limit` is above 100 or `offset` beyond the accepted
    depth; `permission_denied` (403) without `members.manage`; `unauthenticated` (401)
    without a live session.
    """
    items, total = members_logic.list_invitations(_tenant_id(request), _order(request), limit=page.limit, offset=page.offset)
    return InvitationsPage(items=[InvitationOut.model_validate(item) for item in items], total=total)


@router.post(
    "/tenant/invitations/{invitation_id}/resend",
    response=InvitationOut,
    auth=SessionAuth(),
    operation_id="resendInvitation",
    by_alias=True,
    summary="Send an invitation again with a fresh link",
)
@requires_permission(perms.MEMBERS_MANAGE)
@_quoting_settings
def resend_invitation(request: HttpRequest, invitation_id: uuid.UUID = _INVITATION_ID) -> InvitationOut:
    """Emails the invitation again with a new link, which works for $invitation_hours hours
    from now; the link sent before stops working. A pending invitation and an expired one
    can both be resent, and the answer shows it `pending` with its new expiry. The roles and
    title stay as they were: to change them, revoke it and invite again.

    Needs `members.manage`. Records the audit event `invitation.resent` with the new expiry;
    the token is never recorded.

    Errors: `invitation_closed` (409) when the invitation was already accepted or revoked;
    `not_found` (404) when this bank has no such invitation; `permission_denied` (403)
    without `members.manage`; `unauthenticated` (401) without a live session.
    """
    tenant = _tenant(request)
    invitation = members_logic.tenant_invitation(tenant.id, invitation_id)
    issued = invitation_logic.resend_invitation(tenant=tenant, invitation=invitation, actor=session_logic.actor_of(_actor_user(request)))
    return InvitationOut.model_validate(members_logic.invitation_out(issued.invitation, _order(request)))


@router.delete(
    "/tenant/invitations/{invitation_id}",
    response={204: None},
    auth=SessionAuth(),
    operation_id="revokeInvitation",
    by_alias=True,
    summary="Withdraw an invitation so its link stops working",
)
@requires_permission(perms.MEMBERS_MANAGE)
def revoke_invitation(request: HttpRequest, invitation_id: uuid.UUID = _INVITATION_ID) -> tuple[int, None]:
    """Withdraws an invitation or re-issued enrolment at once: its link stops working and it
    is listed as `revoked`. An invitation already revoked, or already accepted, is left as it
    is and still answers 204, so a retry is safe; revoking an accepted invitation does not
    remove the member, which is `DELETE /tenant/members/{user_id}`.

    Needs `members.manage`. Records the audit event `invitation.revoked`, the retry included.

    Errors: `not_found` (404) when this bank has no such invitation; `permission_denied`
    (403) without `members.manage`; `unauthenticated` (401) without a live session.
    """
    tenant = _tenant(request)
    invitation = members_logic.tenant_invitation(tenant.id, invitation_id)
    invitation_logic.revoke_invitation(tenant=tenant, invitation=invitation, actor=session_logic.actor_of(_actor_user(request)))
    return 204, None


# ---------------------------------------------------------------------------------------
# Roles (ID-09)
# ---------------------------------------------------------------------------------------
@router.get(
    "/tenant/roles",
    response=list[RoleOut],
    auth=SessionAuth(),
    operation_id="listRoles",
    by_alias=True,
    summary="See the roles your bank gives its members",
    openapi_extra=_example(200, ROLES_EXAMPLE),
)
def list_roles(request: HttpRequest) -> list[RoleOut]:
    """Every active role of the bank, in the bank's order: the seven system roles and any the
    bank added, each with its labels, usage note and permissions. Retired roles are not
    listed. Call it to fill a role picker or the role editor; labels come in the caller's
    language.

    Any member's session in the bank may read it, with no permission, because every screen
    that names a role needs its label; API keys cannot. It changes nothing and writes no audit
    event.

    Errors: `not_found` (404) from a platform session, which belongs to no bank;
    `unauthenticated` (401) without a live session; `enrolment_only` (403) from an enrolment
    session.
    """
    # Ungated by design: capability (any member; pickers need labels).
    order = _order(request)
    return [RoleOut.model_validate(roles_logic.role_out(role, order)) for role in roles_logic.tenant_roles(_tenant_id(request))]


@router.post(
    "/tenant/roles",
    response={201: RoleOut},
    auth=SessionAuth(),
    operation_id="createRole",
    by_alias=True,
    summary="Add a role of your own, composed from the product's permissions",
)
@requires_permission(perms.ROLES_MANAGE)
@requires_step_up
@_quoting_settings
def create_role(request: HttpRequest, body: RoleCreate) -> tuple[int, RoleOut]:
    """Creates a role the bank can then give its members, placed after its existing roles,
    and answers it with 201. A role is a named set of the permissions
    `GET /reference/permissions` lists; the bank chooses the key once and may reword the
    labels at any time.

    Needs `roles.manage` and a passkey step-up on this session younger than $step_up_minutes
    minutes. Records the audit event `role.created` with the key, labels and permissions and
    the step-up assertion.

    Errors: `step_up_required` (403) without a fresh step-up; `duplicate_key` (409) for a
    key the bank already has, retired roles included; `key_required` (422) for a blank key;
    `label_required` (422) when no label is given; `unknown_key` (422) for a language the
    product does not offer or a key that is not a bank permission; `validation_error` (422)
    for a field over its length; `permission_denied` (403) without `roles.manage`;
    `unauthenticated` (401) without a live session.
    """
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


@router.patch(
    "/tenant/roles/{key}",
    response=RoleOut,
    auth=SessionAuth(),
    operation_id="updateRole",
    by_alias=True,
    summary="Rename a role or change what it grants",
)
@requires_permission(perms.ROLES_MANAGE)
@_quoting_settings
def update_role(request: HttpRequest, body: RolePatch, key: str = _ROLE_KEY) -> RoleOut:
    """Changes a role's labels, usage note or permissions and answers the role as it now
    stands; what is left out of the body is kept, and the key never changes. A change of
    permissions reaches every member holding the role from their next call. A system role
    can be relabelled and its note rewritten, but its permissions follow the product.

    Needs `roles.manage`, and, when `permissions` is sent, a passkey step-up on this session
    younger than $step_up_minutes minutes; relabelling needs none. Records the audit event
    `role.updated` with the permissions, note and labels before and after, and the step-up
    assertion when there was one.

    Errors: `step_up_required` (403) when `permissions` is sent without a fresh step-up;
    `system_role` (422) for a change of a system role's permissions; `label_required` (422)
    when every label sent is blank; `unknown_key` (422) for a language the product does not
    offer or a key that is not a bank permission; `not_found` (404) when the bank has no
    role with that key; `validation_error` (422) for a note over 1000 characters;
    `permission_denied` (403) without `roles.manage`; `unauthenticated` (401) without a live
    session.
    """
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


@router.post(
    "/tenant/roles/{key}/retire",
    response=RoleOut,
    auth=SessionAuth(),
    operation_id="retireRole",
    by_alias=True,
    summary="Retire a role your bank no longer uses",
)
@requires_permission(perms.ROLES_MANAGE)
def retire_role(request: HttpRequest, key: str = _ROLE_KEY) -> RoleOut:
    """Retires one of the bank's own roles and answers it with `active` false: it leaves the
    role list and the pickers and can no longer be given to anyone. Nothing is deleted, and
    its key stays taken, so it is never reused for a different role. Only a role no current
    member holds can be retired: reassign them first. The seven system roles cannot be
    retired.

    Needs `roles.manage`, and no step-up: a role nobody holds grants nothing. Records the
    audit event `role.retired`.

    Errors: `role_in_use` (409) while a current member holds the role, the message saying
    how many; `system_role` (422) for a system role; `not_found` (404) when the bank has no
    role with that key; `permission_denied` (403) without `roles.manage`; `unauthenticated`
    (401) without a live session.
    """
    tenant = _tenant(request)
    role = roles_logic.tenant_role_by_key(tenant.id, key)
    role = roles_logic.retire_role(tenant=tenant, actor=session_logic.actor_of(_actor_user(request)), role=role)
    return RoleOut.model_validate(roles_logic.role_out(role, _order(request)))


@router.get(
    "/reference/permissions",
    response=list[PermissionOut],
    auth=SessionAuth(),
    operation_id="listPermissions",
    by_alias=True,
    summary="See every permission a role of your bank can grant",
    openapi_extra=_example(200, PERMISSIONS_EXAMPLE),
)
def list_permissions(request: HttpRequest) -> list[PermissionOut]:
    """Every permission a bank's role can grant, sorted by key, each with its area and a
    sentence saying what it lets a person do. The set is fixed by the product; a bank composes
    roles from it and cannot add to it. The platform's own permissions are not listed.

    Any signed-in session may read it, with no permission; API keys cannot. It changes
    nothing and writes no audit event.

    Errors: `unauthenticated` (401) without a live session; `enrolment_only` (403) from an
    enrolment session.
    """
    # Ungated by design: capability (any session; the role editor lists the constants).
    return [
        PermissionOut(key=key, group=perms.permission_group(key), description=perms.PERMISSION_DESCRIPTIONS[key])
        for key in sorted(perms.TENANT_PERMISSIONS)
    ]


# ---------------------------------------------------------------------------------------
# API keys (ID-10) and the security log (ID-11)
# ---------------------------------------------------------------------------------------
@router.get(
    "/tenant/api-keys",
    response=ApiKeysPage,
    auth=SessionAuth(),
    operation_id="listApiKeys",
    by_alias=True,
    summary="See your bank's API keys and whether each still works",
)
@requires_permission(perms.INTEGRATIONS_MANAGE)
def list_api_keys(request: HttpRequest, page: PageQuery = Query(...)) -> ApiKeysPage:
    """Returns the bank's own API keys one page at a time, newest first: what each may do,
    when it was last used, and whether it has expired or been revoked. Revoked and expired
    keys stay in the list, so it is the whole history. The secret of a key is never shown
    again after creation: a row carries its eight-character prefix and nothing more. The
    platform's agent keys are never here.

    Needs `integrations.manage` on a person's session in the bank; an API key cannot list
    keys. It changes nothing and writes no audit event. An empty page is a 200 with `total` 0.

    Errors: `validation_error` (422) when `limit` is above 100 or `offset` beyond the accepted
    depth; `permission_denied` (403) without `integrations.manage`; `unauthenticated` (401)
    without a live session.
    """
    items, total = api_keys_logic.list_api_keys(_tenant_id(request), limit=page.limit, offset=page.offset)
    return ApiKeysPage(items=[ApiKeyOut.model_validate(row) for row in items], total=total)


@router.post(
    "/tenant/api-keys",
    response={201: ApiKeyCreated},
    auth=SessionAuth(),
    operation_id="createApiKey",
    by_alias=True,
    summary="Create an API key for one of your bank's integrations",
)
@requires_permission(perms.INTEGRATIONS_MANAGE)
@requires_step_up
@_quoting_settings
def create_api_key(request: HttpRequest, body: ApiKeyCreate) -> tuple[int, ApiKeyCreated]:
    """Creates an API key that belongs to the bank and answers it once, with 201. Put
    `plainKey` straight into the integration's secret store: the server keeps only a hash of
    the secret and never shows it again, so a lost key is revoked and replaced, never
    recovered. Everything the key does is recorded against it and the bank.

    A bank's key may hold only the reading scopes and `proposals:write`, which files a
    proposal that changes nothing until someone independent approves it. `proposals:review`
    and the agent scopes `agent-runs:write`, `sources:write` and `changes:write` belong to
    the platform's own agents and are refused here; no scope writes a library record. Give
    the key the least its integration needs.

    Needs `integrations.manage` and a passkey step-up on this session younger than
    $step_up_minutes minutes; an API key cannot create a key. Records the audit event
    `api_key.created` with the prefix, scopes and expiry, never the secret, and with the
    step-up assertion.

    Errors: `step_up_required` (403) without a fresh step-up, which the screen answers by
    opening the passkey prompt and retrying; `unknown_key` (422) for a scope a bank's key may
    not hold, the message naming the valid scopes; `name_required` (422) for a name of spaces
    alone; `expiry_in_past` (422) for an expiry that is not in the future; `validation_error`
    (422) for an empty scope list or a name over 200 characters; `permission_denied` (403)
    without `integrations.manage`; `unauthenticated` (401) without a live session.
    """
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


@router.delete(
    "/tenant/api-keys/{key_id}",
    response={204: None},
    auth=SessionAuth(),
    operation_id="revokeApiKey",
    by_alias=True,
    summary="Stop one of your bank's API keys working for good; a repeat revoke answers 204 again",
)
@requires_permission(perms.INTEGRATIONS_MANAGE)
def revoke_api_key(request: HttpRequest, key_id: uuid.UUID = _API_KEY_ID) -> tuple[int, None]:
    """Revokes one of the bank's own keys at once: from this moment every call made with it
    answers `unauthenticated`. Call it when a key may have leaked, when an integration is
    retired, or when a key is replaced. There is no way to turn a revoked key back on; create
    a new one instead. The key stays listed with its revocation time.

    Revoking a key that is already revoked changes nothing and answers 204 again, so a retry
    is safe; the retry is recorded in the audit log too, but writes no second security-log
    entry.

    Needs `integrations.manage`, and no step-up: stopping a key only takes power away. Writes
    "key_revoked" to the security log the first time and the audit event `api_key.revoked`
    each time.

    Errors: `not_found` (404) when the bank has no key with that identifier;
    `permission_denied` (403) without `integrations.manage`; `unauthenticated` (401) without
    a live session.
    """
    api_keys_logic.revoke_api_key(tenant=_tenant(request), actor=session_logic.actor_of(_actor_user(request)), key_id=key_id)
    return 204, None


# ---------------------------------------------------------------------------------------
# Platform agent keys (ID-10, AGT-01, chunk 5): keys bound to an agent, under
# `agent_definitions.manage` and, to create one, a fresh passkey assertion. They are the
# platform's alone — bleqq's agents are platform-owned and platform-run — so a tenant
# session holds no permission that reaches them and no tenant route creates a key bound to
# an agent. Each docstring is the route's published description (API_DOCUMENTATION.md).
# ---------------------------------------------------------------------------------------
def _agent_key_out(key: ApiKey) -> AgentKeyOut:
    agent = key.agent
    return AgentKeyOut(
        id=key.id,
        name=key.name,
        key_prefix=key.key_prefix,
        scopes=sorted(key.scopes),
        agent_id=key.agent_id,
        # The label names the version, as a reviewing agent's audit label does (proposals/api.py).
        agent=RoleRef(key=agent.key, kind=None, label=f"{agent.key} v{agent.current_version}") if agent is not None else None,
        created_at=key.created_at,
        expires_at=key.expires_at,
        revoked_at=key.revoked_at,
        last_used_at=key.last_used_at,
    )


@router.get(
    "/agent-keys",
    response=AgentKeysPage,
    auth=SessionAuth(),
    operation_id="listAgentKeys",
    by_alias=True,
    summary="See every key the platform's agents run on",
)
@requires_permission(perms.AGENT_DEFINITIONS_MANAGE)
def list_agent_keys(request: HttpRequest, page: PageQuery = Query(...)) -> AgentKeysPage:
    """Returns the platform's own API keys, newest first, one page at a time: which agent
    each is bound to, what it may do, when it was last used and whether it still works.
    Call it from the platform console to see which keys are live before creating another
    or revoking one; revoked and expired keys stay in the list, so it is the whole history.

    A person's session only, holding the platform permission `agent_definitions.manage`,
    which only a platform administrator holds; no session inside a bank can reach it, and
    no API key can. A bank's own keys are never here, and the secret of a key is never
    shown again after creation: a row carries its eight-character prefix and nothing more.
    It changes nothing and writes nothing to the audit log. An empty list is a 200 with
    `total` 0.

    Errors: `validation_error` when `limit` is above 100 or `offset` beyond the accepted
    depth; `permission_denied` without `agent_definitions.manage`; `unauthenticated`
    without a session.
    """
    keys, total = api_keys_logic.list_agent_keys(limit=page.limit, offset=page.offset)
    return AgentKeysPage(items=[_agent_key_out(key) for key in keys], total=total)


@router.post(
    "/agent-keys",
    response={201: AgentKeyCreated},
    auth=SessionAuth(),
    operation_id="createAgentKey",
    by_alias=True,
    summary="Mint a key for one of the platform's agents",
)
@requires_permission(perms.AGENT_DEFINITIONS_MANAGE)
@requires_step_up
def create_agent_key(request: HttpRequest, body: AgentKeyCreate) -> tuple[int, AgentKeyCreated]:
    """Creates an API key bound to one agent definition and answers it once. Call it when
    an agent's runner needs a key, and put `plainKey` straight into the runner's secret
    store: the server keeps only a hash of the secret and never shows it again, so a lost
    key is revoked and replaced, never recovered.

    Needs the platform permission `agent_definitions.manage` and a fresh passkey step-up
    on the session; an API key cannot create a key. The key belongs to no bank. Everything
    it writes is recorded as the agent it is bound to, and it runs that agent and no other.
    Its scopes follow its agent's kind: a review agent's key may hold `proposals:review`,
    which makes it a second, independent reviewer of proposals someone else filed, and none
    of the filing scopes `sources:write`, `changes:write` and `proposals:write`; every other
    kind's key may hold those and never `proposals:review`. The agent must be active, or a
    draft still being evaluated; a retired or switched-off agent takes no key, and a key of
    an agent switched off later stops working. No scope writes a library record. Give it the
    least its agent needs.

    The creation is recorded in the audit log as `agent_key.created` with the prefix, the
    agent, the scopes and the expiry, never the secret, and with the step-up assertion
    that confirmed it; the security log records the event "key_created". Answers 201 with
    the key.

    Errors: `step_up_required` without a fresh passkey assertion, which the console answers
    by opening the passkey prompt and retrying; `unknown_key` when `agentId` names no agent
    definition or a scope does not exist, the message naming the valid scopes;
    `agent_inactive` (422) when the agent is retired or switched off; `scope_not_for_kind`
    (422) for a scope the agent's kind does not take, the message naming it;
    `name_required` for a name of spaces alone; `expiry_in_past` for an expiry that is not
    in the future; `validation_error` for a field the schema refuses, a field it does not
    name among them; `permission_denied` without `agent_definitions.manage`;
    `unauthenticated` without a session.
    """
    actor_user = _actor_user(request)
    key, plain = api_keys_logic.create_agent_key(
        actor=session_logic.actor_of(actor_user),
        created_by=actor_user,
        agent_id=body.agent_id,
        name=body.name,
        scopes=body.scopes,
        expires_at=body.expires_at,
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
    )
    return 201, AgentKeyCreated(
        id=key.id,
        name=key.name,
        key_prefix=key.key_prefix,
        scopes=list(key.scopes),
        agent_id=body.agent_id,
        created_at=key.created_at,
        expires_at=key.expires_at,
        plain_key=plain,
    )


@router.post(
    "/agent-keys/{key_id}/revoke",
    response=AgentKeyOut,
    auth=SessionAuth(),
    operation_id="revokeAgentKey",
    by_alias=True,
    summary="Stop one of the platform's agent keys working, for good",
)
@requires_permission(perms.AGENT_DEFINITIONS_MANAGE)
def revoke_agent_key(
    request: HttpRequest,
    key_id: uuid.UUID = Path(
        ...,
        description=(
            "The identifier of the platform key to revoke, the UUID `GET /agent-keys` lists as "
            "`id`, never the key itself. A bank's key or an identifier that names nothing "
            "answers `not_found`."
        ),
    ),
) -> AgentKeyOut:
    """Revokes a platform key at once: from this moment every call made with it answers
    `unauthenticated`, so a run its agent has open can no longer be closed with it. Call it
    when a key may have leaked, when an agent is retired, or when a key is replaced. There
    is no way to turn a revoked key back on; create a new one instead.

    Needs the platform permission `agent_definitions.manage`, and no step-up: stopping a
    key only takes power away. A bank's own keys are revoked from the bank's own API keys
    screen and never here. The revocation is recorded in the audit log as
    `agent_key.revoked` and in the security log as the event "key_revoked", and the key
    stays listed with its revocation time. Revoking a key that is already revoked changes
    nothing and answers the key as it stands, so a retry is safe; the retry is audited too,
    as `agent_key.revoked` saying the key was already revoked and nothing changed.

    Answers 200 with the key. Errors: `not_found` when no platform key has that identifier;
    `permission_denied` without `agent_definitions.manage`; `unauthenticated` without a
    session.
    """
    actor_user = _actor_user(request)
    key = api_keys_logic.revoke_agent_key(actor=session_logic.actor_of(actor_user), revoked_by=actor_user, key_id=key_id)
    return _agent_key_out(key)


@router.get(
    "/tenant/security-log",
    response=SecurityLogPage,
    auth=SessionAuth(),
    operation_id="listSecurityLog",
    by_alias=True,
    summary="Read your bank's security log of sign-ins, failures and key use",
)
@requires_permission(perms.SECURITY_MANAGE)
def list_security_log(request: HttpRequest, page: PageQuery = Query(...)) -> SecurityLogPage:
    """Returns the bank's security log one page at a time, newest first: every enrolment code
    sent or refused, every passkey sign-in and step-up with its failures, every session ended
    early, every re-issued enrolment, and the use and revocation of the bank's API keys and
    calendar feeds. Call it to investigate a suspicious sign-in or to show a reviewer who got
    in and how. Only this bank's entries appear. The log is append-only: nothing in it is ever
    edited or removed.

    Needs `security.manage` on a person's session in the bank; API keys cannot read it.
    Reading it changes nothing and writes no audit event. An empty page is a 200 with an
    empty list.

    Errors: `validation_error` (422) when `limit` is above 100 or `offset` beyond the accepted
    depth; `permission_denied` (403) without `security.manage`; `unauthenticated` (401)
    without a live session; `enrolment_only` (403) from an enrolment session.
    """
    items, total = security_log.list_events(_tenant_id(request), limit=page.limit, offset=page.offset)
    return SecurityLogPage(items=[SecurityEventOut.model_validate(row) for row in items], total=total)
