"""The WebAuthn ceremonies (ID-02 to ID-06) on py_webauthn 3.0.0, whose surface is
recorded in docs/plans/Verification_Log.md (fetched 2026-09-19, never recalled):

- `generate_registration_options(rp_id, rp_name, user_name, user_id, user_display_name,
  authenticator_selection, exclude_credentials, timeout)` and
  `generate_authentication_options(rp_id, allow_credentials, user_verification, timeout)`
  return dataclasses; `options_to_json_dict` turns them into the camelCase dict the
  browser's `navigator.credentials` takes, bytes base64url-encoded.
- `verify_registration_response(credential=<dict>, expected_challenge=<bytes>,
  expected_rp_id, expected_origin=<list>, require_user_verification=True)` parses the
  browser's JSON dict itself (`parse_registration_credential_json`) and returns
  `VerifiedRegistration(credential_id, credential_public_key, sign_count, aaguid,
  credential_device_type, credential_backed_up, user_verified, ...)`.
- `verify_authentication_response(credential=<dict>, expected_challenge, expected_rp_id,
  expected_origin, credential_public_key, credential_current_sign_count,
  require_user_verification=True)` returns `VerifiedAuthentication(new_sign_count, ...)`.
- `parse_client_data_json(bytes)` gives the challenge the browser signed, which is how a
  stored challenge row is found for a discoverable sign-in (no user is known yet).

User verification is required and credentials are discoverable (resident key required);
the user handle is the user's id bytes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import (
    base64url_to_bytes,
    bytes_to_base64url,
    options_to_json_dict,
    parse_client_data_json,
)
from webauthn.helpers.exceptions import (
    InvalidAuthenticationResponse,
    InvalidJSONStructure,
    InvalidRegistrationResponse,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from apps.identity import invitation_logic, passkey_names, rate_limit, session_logic
from apps.identity.models import (
    AuthChallenge,
    ChallengeKind,
    LoginEventKind,
    LoginMethod,
    SessionKind,
    StepUpAssertion,
    User,
    UserSession,
    UserStatus,
    WebAuthnCredential,
)
from apps.identity.security_log import client_ip, log_event, user_agent
from apps.shared import tenancy
from apps.shared.audit import Actor, record
from apps.shared.authentication import Principal, PrincipalKind


class SignInFailed(ValidationError):
    """The assertion did not verify (401 signin_failed)."""


class StepUpFailed(ValidationError):
    """The step-up assertion did not verify (400 step_up_failed)."""


def _session_of(principal: Principal) -> UserSession:
    if principal.session_id is None:
        raise ValidationError("Sign in again.", code="unauthenticated")
    return UserSession.objects.get(pk=principal.session_id)


def _live_credentials(user: User) -> list[WebAuthnCredential]:
    return list(WebAuthnCredential.objects.filter(user=user, retired_at__isnull=True).order_by("created_at", "id"))


def _descriptors(credentials: list[WebAuthnCredential]) -> list[PublicKeyCredentialDescriptor]:
    return [PublicKeyCredentialDescriptor(id=base64url_to_bytes(row.credential_id)) for row in credentials]


def _store_challenge(kind: ChallengeKind, challenge: bytes, *, user: User | None, session: UserSession | None) -> AuthChallenge:
    return AuthChallenge.objects.create(
        kind=kind.value,
        challenge=bytes_to_base64url(challenge),
        user=user,
        session=session,
        expires_at=timezone.now() + timedelta(seconds=settings.CHALLENGE_TTL_SECONDS),
    )


def _challenge_from_credential(credential: dict[str, Any]) -> bytes:
    try:
        client_data = parse_client_data_json(base64url_to_bytes(credential["response"]["clientDataJSON"]))
    except (KeyError, TypeError, ValueError, InvalidJSONStructure) as exc:
        raise ValidationError("The credential is malformed.", code="invalid_credential") from exc
    return client_data.challenge


def _open_challenge(kind: ChallengeKind, challenge: bytes, *, user: User | None, session: UserSession | None, now: datetime) -> AuthChallenge | None:
    queryset = AuthChallenge.objects.filter(
        kind=kind.value, challenge=bytes_to_base64url(challenge), consumed_at__isnull=True, expires_at__gt=now
    )
    if user is not None:
        queryset = queryset.filter(user=user)
    if session is not None:
        queryset = queryset.filter(session=session)
    return queryset.first()  # ordering: the challenge column is unique, at most one row


def _consume_challenge(kind: ChallengeKind, challenge: bytes, *, user: User | None = None, session: UserSession | None = None) -> AuthChallenge:
    """Single use: the row is claimed with one conditional UPDATE, so two copies of the
    same assertion in flight cannot both pass (a read-then-save let them; security review
    2026-09-19, finding F3). Consumed before the signature is checked, so a failed attempt
    spends the challenge too."""
    now = timezone.now()
    row = _open_challenge(kind, challenge, user=user, session=session, now=now)
    if row is None or AuthChallenge.objects.filter(pk=row.pk, consumed_at__isnull=True).update(consumed_at=now) != 1:
        raise ValidationError("The challenge has expired. Start again.", code="challenge_expired")
    row.consumed_at = now
    return row


def _user_handle_matches(credential: dict[str, Any], user: User, *, required: bool) -> bool:
    """WebAuthn §7.2: for a discoverable sign-in the user is identified by the assertion's
    userHandle, which must name the account that owns the credential (finding F4). At
    step-up the account is already known, so the handle is checked only when present."""
    handle = credential.get("response", {}).get("userHandle")
    if handle in (None, ""):
        return not required
    if not isinstance(handle, str):
        return False
    try:
        return base64url_to_bytes(handle) == user.id.bytes
    except (ValueError, TypeError):
        return False


def _record_challenge(row: AuthChallenge, tenant_id: uuid.UUID | None, actor: Actor) -> None:
    record(
        action="auth.challenge_issued",
        actor=actor,
        subject_type="auth_challenge",
        subject_id=row.id,
        subject_title=row.kind,
        summary=f"{row.kind} challenge issued.",
        tenant_id=tenant_id,
    )


def passkey_out(row: WebAuthnCredential) -> dict[str, Any]:
    return {
        "id": row.id,
        "nickname": row.nickname,
        "device_type": row.device_type,
        "backed_up": row.backed_up,
        "transports": list(row.transports),
        "created_at": row.created_at,
        "last_used_at": row.last_used_at,
    }


# ---------------------------------------------------------------------------------------
# Registration (enrolment or an added passkey)
# ---------------------------------------------------------------------------------------
def registration_options(principal: Principal) -> dict[str, Any]:
    user = User.objects.get(pk=principal.subject_id)
    session = _session_of(principal)
    options = generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=user.id.bytes,
        user_name=user.email,
        user_display_name=user.name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            require_resident_key=True,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=_descriptors(_live_credentials(user)),
        timeout=settings.CHALLENGE_TTL_SECONDS * 1000,
    )
    row = _store_challenge(ChallengeKind.REGISTRATION, options.challenge, user=user, session=session)
    _record_challenge(row, principal.tenant_id, session_logic.actor_of(user))
    return options_to_json_dict(options)


@dataclass(frozen=True)
class RegistrationResult:
    credential: WebAuthnCredential
    bundle: session_logic.SessionBundle | None  # a full session when enrolment just completed


def _nickname_for(user: User, supplied: str | None, credential: dict[str, Any], aaguid: str, transports: list[str], request: HttpRequest | None) -> passkey_names.DerivedName:
    """A name the person gave is kept as given; a blank or missing one is derived from the
    device (ID-04; apps/identity/passkey_names.py), unique among their live passkeys."""
    chosen = (supplied or "").strip()[: passkey_names.NICKNAME_MAX_LENGTH]
    if chosen:
        return passkey_names.DerivedName(nickname=chosen, source=passkey_names.SOURCE_SUPPLIED)
    attachment = credential.get("authenticatorAttachment")
    return passkey_names.derive_nickname(
        aaguid=aaguid,
        user_agent=user_agent(request),
        transports=transports,
        attachment=attachment if isinstance(attachment, str) else None,
        taken=[row.nickname for row in _live_credentials(user)],
    )


def verify_registration(principal: Principal, credential: dict[str, Any], nickname: str | None, request: HttpRequest | None) -> RegistrationResult:
    user = User.objects.get(pk=principal.subject_id)
    session = _session_of(principal)
    now = timezone.now()
    enrolling = principal.kind is PrincipalKind.ENROLMENT
    invitation = None
    if enrolling:
        # The invitation this enrolment session came from: the one open for the address
        # in the session's tenant, never whichever tenant invited the address last
        # (finding F8).
        invitation = invitation_logic.find_open_for_tenant(user.email, session.tenant_id)
        if invitation is not None and invitation.tenant_id is not None:
            # A platform role granted after the invitation was sent, refused here and not
            # at acceptance below: a ValidationError becomes a 422 inside the view and the
            # request's transaction still commits, so a refusal after the credential
            # insert would leave a credential row with no audit row, an account holding a
            # live passkey it cannot sign in with, and an emailed code already closed
            # (hardening H13, review 2026-09-20).
            invitation_logic.refuse_platform_account(user)
    challenge = _consume_challenge(ChallengeKind.REGISTRATION, _challenge_from_credential(credential), user=user, session=session)
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge.challenge),
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=list(settings.WEBAUTHN_ORIGINS),
            require_user_verification=True,
        )
    except (InvalidRegistrationResponse, InvalidJSONStructure) as exc:
        raise ValidationError("The passkey could not be registered. Try again.", code="registration_failed") from exc
    transports = [str(item) for item in credential.get("response", {}).get("transports") or []]
    device_type = verified.credential_device_type.value
    name = _nickname_for(user, nickname, credential, verified.aaguid, transports, request)
    try:
        # A savepoint: the credential id is unique across every account (WebAuthn §7.1
        # step 22), and a duplicate must answer 400, not break the request transaction.
        with transaction.atomic():
            row = WebAuthnCredential.objects.create(
                user=user,
                credential_id=bytes_to_base64url(verified.credential_id),
                public_key=bytes_to_base64url(verified.credential_public_key),
                sign_count=verified.sign_count,
                transports=transports,
                aaguid=verified.aaguid,
                backup_eligible=device_type == "multi_device",
                backed_up=verified.credential_backed_up,
                device_type=device_type,
                nickname=name.nickname,
                last_used_at=now,
            )
    except IntegrityError as exc:
        raise ValidationError("The passkey could not be registered. Try again.", code="registration_failed") from exc
    bundle: session_logic.SessionBundle | None = None
    if enrolling:
        if invitation is not None:
            invitation_logic.accept_invitation(invitation, user, now)
        user.status = UserStatus.ACTIVE.value
        user.last_seen_at = now
        user.save(update_fields=["status", "last_seen_at"])
        session_logic.revoke_session(session, reason="enrolment_completed", actor=session_logic.actor_of(user), request=request)
        tenant_id = session.tenant_id if session.tenant_id is not None else session_logic.choose_tenant(user)
        # No step-up assertion (F9, narrowed): the second-passkey prompt rides on the new
        # session's age; every `@requires_step_up` action still needs its own ceremony.
        bundle = session_logic.create_session(user=user, kind=SessionKind.FULL, tenant_id=tenant_id, request=request, now=now)
    log_event(event=LoginEventKind.ENROLLED, method=LoginMethod.PASSKEY, success=True, request=request, user=user, tenant_id=principal.tenant_id)
    record(
        action="passkey.registered",
        actor=session_logic.actor_of(user),
        subject_type="webauthn_credential",
        subject_id=row.id,
        subject_title=user.name,
        summary="Passkey enrolled; account activated." if enrolling else "Passkey added.",
        tenant_id=principal.tenant_id,
        after={"nickname": row.nickname, "nicknameSource": name.source, "deviceType": row.device_type, "aaguid": row.aaguid},
    )
    return RegistrationResult(credential=row, bundle=bundle)


# ---------------------------------------------------------------------------------------
# Sign-in (discoverable)
# ---------------------------------------------------------------------------------------
def authentication_options(request: HttpRequest | None) -> dict[str, Any]:
    # Unauthenticated and a write (a challenge row plus its audit row): bounded per IP
    # like every other ceremony step (finding F5).
    rate_limit.enforce("auth:ip", client_ip(request) or "", settings.AUTH_RATE_PER_IP_PER_MINUTE, 60, e2e_exempt=True)
    options = generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        allow_credentials=[],
        user_verification=UserVerificationRequirement.REQUIRED,
        timeout=settings.CHALLENGE_TTL_SECONDS * 1000,
    )
    row = _store_challenge(ChallengeKind.AUTHENTICATION, options.challenge, user=None, session=None)
    _record_challenge(row, None, Actor.system("sign-in"))
    return options_to_json_dict(options)


def _find_credential(credential: dict[str, Any]) -> WebAuthnCredential | None:
    credential_id = credential.get("id")
    if not isinstance(credential_id, str):
        return None
    return (
        WebAuthnCredential.objects.select_related("user")
        .filter(credential_id=credential_id, retired_at__isnull=True)
        .first()
    )  # ordering: credential_id is unique, at most one row


SIGN_COUNT_REGRESSION_IGNORED_E2E = "sign_count_regression_ignored_e2e"


def _e2e_sign_count_leniency() -> bool:
    """Playwright's virtual authenticator restarts its counter per browser context, so a
    seeded login's second sign-in in a run presents a count at or below the stored one,
    which WebAuthn treats as a cloned authenticator. Under E2E_MODE only, that regression
    is accepted and logged; the flag is refused when deployed at boot (rule 4), in
    `tokens.new_code` and here again."""
    if not settings.E2E_MODE:
        return False
    if settings.IS_DEPLOYED_ENVIRONMENT:
        raise ImproperlyConfigured("E2E_MODE sign-count leniency is refused on a deployed environment (playbook 8.3).")
    return True


def _verify_assertion(row: WebAuthnCredential, credential: dict[str, Any], challenge: AuthChallenge) -> tuple[int, bool]:
    """Returns (new sign count, regression ignored). Outside E2E a non-increasing counter
    is refused by py_webauthn (verified in the installed source: it raises when either
    count is above zero and the new one is not greater)."""
    lenient = _e2e_sign_count_leniency()
    verified = verify_authentication_response(
        credential=credential,
        expected_challenge=base64url_to_bytes(challenge.challenge),
        expected_rp_id=settings.WEBAUTHN_RP_ID,
        expected_origin=list(settings.WEBAUTHN_ORIGINS),
        credential_public_key=base64url_to_bytes(row.public_key),
        credential_current_sign_count=0 if lenient else row.sign_count,
        require_user_verification=True,
    )
    new_count = verified.new_sign_count
    regressed = (new_count > 0 or row.sign_count > 0) and new_count <= row.sign_count
    return new_count, regressed


def verify_authentication(credential: dict[str, Any], request: HttpRequest | None) -> session_logic.SessionBundle:
    rate_limit.enforce("auth:ip", client_ip(request) or "", settings.AUTH_RATE_PER_IP_PER_MINUTE, 60, e2e_exempt=True)
    now = timezone.now()
    row = _find_credential(credential)
    if row is None or row.user.status != UserStatus.ACTIVE.value:
        log_event(event=LoginEventKind.SIGNIN_FAILED, method=LoginMethod.PASSKEY, success=False, request=request, user=row.user if row else None, failure_reason="unknown_credential")
        raise SignInFailed("Sign-in failed.", code="signin_failed")
    try:
        challenge = _consume_challenge(ChallengeKind.AUTHENTICATION, _challenge_from_credential(credential))
        if not _user_handle_matches(credential, row.user, required=True):
            raise ValidationError("The passkey does not belong to this account.", code="user_handle_mismatch")
        new_sign_count, regressed = _verify_assertion(row, credential, challenge)
    except (ValidationError, InvalidAuthenticationResponse, InvalidJSONStructure) as exc:
        log_event(event=LoginEventKind.SIGNIN_FAILED, method=LoginMethod.PASSKEY, success=False, request=request, user=row.user, failure_reason=getattr(exc, "code", "") or "assertion_failed")
        raise SignInFailed("Sign-in failed.", code="signin_failed") from exc
    row.sign_count = max(row.sign_count, new_sign_count)
    row.last_used_at = now
    row.save(update_fields=["sign_count", "last_used_at"])
    user = row.user
    user.last_seen_at = now
    user.save(update_fields=["last_seen_at"])
    tenant_id = session_logic.choose_tenant(user)
    if tenant_id is not None:
        tenancy.activate(tenant_id)
    # A sign-in is not a step-up (F9, narrowed; ID-S14): no assertion on the new session.
    bundle = session_logic.create_session(user=user, kind=SessionKind.FULL, tenant_id=tenant_id, request=request, now=now)
    log_event(event=LoginEventKind.SIGNIN, method=LoginMethod.PASSKEY, success=True, request=request, user=user, tenant_id=tenant_id)
    if regressed:
        log_event(event=LoginEventKind.SIGNIN, method=LoginMethod.PASSKEY, success=True, request=request, user=user, tenant_id=tenant_id, failure_reason=SIGN_COUNT_REGRESSION_IGNORED_E2E)
    return bundle


# ---------------------------------------------------------------------------------------
# Step-up (ID-06)
# ---------------------------------------------------------------------------------------
def step_up_options(principal: Principal) -> dict[str, Any]:
    user = User.objects.get(pk=principal.subject_id)
    session = _session_of(principal)
    options = generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        allow_credentials=_descriptors(_live_credentials(user)),
        user_verification=UserVerificationRequirement.REQUIRED,
        timeout=settings.CHALLENGE_TTL_SECONDS * 1000,
    )
    row = _store_challenge(ChallengeKind.STEP_UP, options.challenge, user=user, session=session)
    _record_challenge(row, principal.tenant_id, session_logic.actor_of(user))
    return options_to_json_dict(options)


def verify_step_up(principal: Principal, credential: dict[str, Any], request: HttpRequest | None) -> StepUpAssertion:
    user = User.objects.get(pk=principal.subject_id)
    session = _session_of(principal)
    now = timezone.now()
    row = _find_credential(credential)
    if row is None or row.user_id != user.id:
        log_event(event=LoginEventKind.STEP_UP_FAILED, method=LoginMethod.PASSKEY, success=False, request=request, user=user, tenant_id=principal.tenant_id, failure_reason="unknown_credential")
        raise StepUpFailed("The passkey could not be verified.", code="step_up_failed")
    try:
        challenge = _consume_challenge(ChallengeKind.STEP_UP, _challenge_from_credential(credential), user=user, session=session)
        if not _user_handle_matches(credential, user, required=False):
            raise ValidationError("The passkey does not belong to this account.", code="user_handle_mismatch")
        new_sign_count, regressed = _verify_assertion(row, credential, challenge)
    except (ValidationError, InvalidAuthenticationResponse, InvalidJSONStructure) as exc:
        log_event(event=LoginEventKind.STEP_UP_FAILED, method=LoginMethod.PASSKEY, success=False, request=request, user=user, tenant_id=principal.tenant_id, failure_reason=getattr(exc, "code", "") or "assertion_failed")
        raise StepUpFailed("The passkey could not be verified.", code="step_up_failed") from exc
    row.sign_count = max(row.sign_count, new_sign_count)
    row.last_used_at = now
    row.save(update_fields=["sign_count", "last_used_at"])
    assertion = StepUpAssertion.objects.create(session=session, credential=row, challenge=challenge)
    log_event(event=LoginEventKind.STEP_UP, method=LoginMethod.PASSKEY, success=True, request=request, user=user, tenant_id=principal.tenant_id)
    if regressed:
        log_event(event=LoginEventKind.STEP_UP, method=LoginMethod.PASSKEY, success=True, request=request, user=user, tenant_id=principal.tenant_id, failure_reason=SIGN_COUNT_REGRESSION_IGNORED_E2E)
    record(
        action="step_up.asserted",
        actor=session_logic.actor_of(user),
        subject_type="step_up_assertion",
        subject_id=assertion.id,
        subject_title=user.name,
        summary="Fresh passkey assertion recorded.",
        tenant_id=principal.tenant_id,
    )
    return assertion


def step_up_valid_until(assertion: StepUpAssertion) -> Any:
    return assertion.created_at + timedelta(minutes=settings.STEP_UP_FRESHNESS_MINUTES)


# ---------------------------------------------------------------------------------------
# My passkeys (ID-04)
# ---------------------------------------------------------------------------------------
def list_passkeys(user_id: uuid.UUID) -> list[WebAuthnCredential]:
    return list(WebAuthnCredential.objects.filter(user_id=user_id, retired_at__isnull=True).order_by("created_at", "id"))


def _own_passkey(user_id: uuid.UUID, passkey_id: uuid.UUID) -> WebAuthnCredential:
    row = WebAuthnCredential.objects.filter(pk=passkey_id, user_id=user_id, retired_at__isnull=True).first()  # ordering: pk lookup, at most one row
    if row is None:
        raise ValidationError("Not found.", code="not_found")
    return row


def rename_passkey(principal: Principal, passkey_id: uuid.UUID, nickname: str) -> WebAuthnCredential:
    row = _own_passkey(principal.subject_id, passkey_id)
    before = row.nickname
    row.nickname = nickname.strip()[:100]
    row.save(update_fields=["nickname"])
    record(
        action="passkey.renamed",
        actor=session_logic.actor_of(row.user),
        subject_type="webauthn_credential",
        subject_id=row.id,
        subject_title=row.user.name,
        summary="Passkey renamed.",
        tenant_id=principal.tenant_id,
        before={"nickname": before},
        after={"nickname": row.nickname},
    )
    return row


def remove_passkey(principal: Principal, passkey_id: uuid.UUID) -> None:
    # Locked before they are counted: two removals at once would otherwise each count the
    # other's passkey as the one left and leave the person with none, which only re-enrolment
    # may do (ID-04, ID-05; the calendar feed reads that moment as a re-enrolment).
    live = set(
        WebAuthnCredential.objects.select_for_update()
        .filter(user_id=principal.subject_id, retired_at__isnull=True)
        .values_list("pk", flat=True)
    )
    row = _own_passkey(principal.subject_id, passkey_id)
    if not live - {row.pk}:
        raise ValidationError("You cannot remove your last passkey.", code="last_passkey")
    row.retired_at = timezone.now()
    row.save(update_fields=["retired_at"])
    record(
        action="passkey.retired",
        actor=session_logic.actor_of(row.user),
        subject_type="webauthn_credential",
        subject_id=row.id,
        subject_title=row.user.name,
        summary="Passkey removed.",
        tenant_id=principal.tenant_id,
        before={"nickname": row.nickname},
    )
