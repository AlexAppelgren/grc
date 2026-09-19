"""Models of the identity app (PRD ID-01 to ID-11, INPUT_DELTAS §2, schema v0.3 section 1 as
corrected by the chunk 1 brief).

Nobody has a password: `User` carries none (apps/shared/tests_no_passwords.py). Tokens,
codes and keys are stored hashed (SHA-256 for random tokens, a salted SHA-256 for the
six-digit code) in `apps/identity/tokens.py`, never here.

Zones: `User`, `PlatformRole`, `PlatformRoleAssignment`, `OtpCode`, `AuthChallenge`,
`WebAuthnCredential` and `StepUpAssertion` belong to no tenant. `TenantRole`,
`Membership` (and the two through tables) are tenant tables under forced RLS.
`Invitation`, `UserSession`, `ApiKey` and `LoginEvent` have a nullable tenant (platform
invitations, platform sessions, platform keys, platform events) and carry the mixed
policy; the first three also carry the identity-lookup clause because the auth layer
reads them before a tenant is known (apps/shared/tenancy.py).
"""

from __future__ import annotations

import enum
import uuid

from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.shared.audit import AppendOnlyModel
from apps.shared.fields import CIEmailField
from apps.shared.tenancy import TenantModel
from apps.shared.vocabulary import TenantVocabulary, Vocabulary, VocabularyLabel


def _choices(kind: type[enum.StrEnum]) -> list[tuple[str, str]]:
    return [(member.value, member.value) for member in kind]


# ---------------------------------------------------------------------------------------
# Kinds (tier one, apps/shared/kinds.py)
# ---------------------------------------------------------------------------------------
class UserStatus(enum.StrEnum):
    INVITED = "invited"
    ACTIVE = "active"
    DEACTIVATED = "deactivated"


class InvitationKind(enum.StrEnum):
    INVITE = "invite"
    REENROLMENT = "reenrolment"


class ChallengeKind(enum.StrEnum):
    REGISTRATION = "registration"
    AUTHENTICATION = "authentication"
    STEP_UP = "step_up"


class PasskeyDeviceType(enum.StrEnum):
    SINGLE_DEVICE = "single_device"
    MULTI_DEVICE = "multi_device"


class SessionKind(enum.StrEnum):
    ENROLMENT = "enrolment"
    FULL = "full"


class LoginMethod(enum.StrEnum):
    EMAIL_CODE = "email_code"
    PASSKEY = "passkey"
    API_KEY = "api_key"


class LoginEventKind(enum.StrEnum):
    CODE_SENT = "code_sent"
    CODE_REFUSED_ENROLLED = "code_refused_enrolled"
    CODE_FAILED = "code_failed"
    CODE_LOCKED = "code_locked"
    ENROLLED = "enrolled"
    SIGNIN = "signin"
    SIGNIN_FAILED = "signin_failed"
    STEP_UP = "step_up"
    STEP_UP_FAILED = "step_up_failed"
    REFRESH_REPLAY = "refresh_replay"
    SESSION_REVOKED = "session_revoked"
    REENROLMENT_ISSUED = "reenrolment_issued"
    KEY_USED = "key_used"
    KEY_REVOKED = "key_revoked"


# ---------------------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------------------
class User(models.Model):
    """A person (table `app_user`). Not Django's auth user; no password field anywhere."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = CIEmailField(max_length=254, unique=True)
    name = models.CharField(max_length=200)
    locale = models.ForeignKey("library.Language", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=16, choices=_choices(UserStatus), default=UserStatus.INVITED.value)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "app_user"
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return self.name


class PlatformRole(Vocabulary):
    """A platform role (PRD §6): `platform_admin`, `library_editor`. Rows composed of
    permission constants; seeded by seed_reference from SYSTEM_ROLES."""

    permissions = ArrayField(models.CharField(max_length=64), default=list, blank=True)

    class Meta:
        db_table = "platform_role"
        ordering = ["sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["key"], name="platform_role_key_unique")]


class PlatformRoleLabel(VocabularyLabel):
    vocabulary = models.ForeignKey(PlatformRole, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "platform_role_label"
        ordering = ["language"]
        constraints = [
            models.UniqueConstraint(fields=["vocabulary", "language"], name="platform_role_label_unique"),
        ]


class PlatformRoleAssignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="platform_role_assignments")
    role = models.ForeignKey(PlatformRole, on_delete=models.PROTECT, related_name="assignments")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "platform_role_assignment"
        ordering = ["created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["user", "role"], name="platform_role_assignment_unique")]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.role_id}"


# ---------------------------------------------------------------------------------------
# Roles and memberships (tenant zone)
# ---------------------------------------------------------------------------------------
class TenantRole(TenantVocabulary):
    """A tenant role (ID-09): system rows seeded per tenant from PRD §6 plus the tenant's
    own, each an array of permission constants. Nothing compares a role's key."""

    permissions = ArrayField(models.CharField(max_length=64), default=list, blank=True)

    class Meta:
        db_table = "tenant_role"
        ordering = ["sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["tenant", "key"], name="tenant_role_key_unique")]


class TenantRoleLabel(VocabularyLabel):
    tenant = models.ForeignKey("shared.Tenant", on_delete=models.PROTECT, related_name="+")
    vocabulary = models.ForeignKey(TenantRole, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "tenant_role_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["vocabulary", "language"], name="tenant_role_label_unique")]


class Membership(TenantModel):
    """One person in one tenant with roles (ID-01). `delegate` and `out_of_office_until`
    are R2 (TEN-04); they exist now so the column set matches schema v0.3."""

    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="memberships")
    roles = models.ManyToManyField(TenantRole, through="identity.MembershipRole", related_name="memberships")
    title = models.CharField(max_length=200, blank=True)
    notification_prefs = models.JSONField(default=dict, blank=True)  # schema: MembershipNotificationPrefs
    last_visit_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    deactivated_at = models.DateTimeField(null=True, blank=True)
    out_of_office_until = models.DateField(null=True, blank=True)
    delegate = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "membership"
        ordering = ["created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["tenant", "user"], name="membership_tenant_user_unique")]

    def __str__(self) -> str:
        return f"{self.user_id}@{self.tenant_id}"


class MembershipRole(TenantModel):
    """The membership-role link, explicit so it carries the tenant and sits under RLS."""

    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="role_links")
    role = models.ForeignKey(TenantRole, on_delete=models.PROTECT, related_name="membership_links")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "membership_role"
        ordering = ["created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["membership", "role"], name="membership_role_unique")]

    def __str__(self) -> str:
        return f"{self.membership_id}:{self.role_id}"


# ---------------------------------------------------------------------------------------
# Invitations and codes
# ---------------------------------------------------------------------------------------
class Invitation(models.Model):
    """A single-use, hashed, 72-hour token that opens the emailed-code path (ID-01, ID-05).
    `tenant` is null for a platform invitation (bootstrap_platform); the mixed policy with
    the identity-lookup clause lets the auth layer find it by token or address."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("shared.Tenant", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    email = CIEmailField(max_length=254)
    roles = models.ManyToManyField(TenantRole, through="identity.InvitationRole", related_name="+")
    title = models.CharField(max_length=200, blank=True)
    token_hash = models.CharField(max_length=64, unique=True)
    kind = models.CharField(max_length=16, choices=_choices(InvitationKind), default=InvitationKind.INVITE.value)
    invited_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "invitation"
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.kind} {self.id}"


class InvitationRole(models.Model):
    """The invitation-role link; tenant nullable like its invitation, under the mixed policy."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("shared.Tenant", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    invitation = models.ForeignKey(Invitation, on_delete=models.CASCADE, related_name="role_links")
    role = models.ForeignKey(TenantRole, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "invitation_role"
        ordering = ["created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["invitation", "role"], name="invitation_role_unique")]

    def __str__(self) -> str:
        return f"{self.invitation_id}:{self.role_id}"


class OtpCode(models.Model):
    """One emailed six-digit code (ID-02): salted hash, attempts, expiry, consumed."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name="otp_codes")
    email = CIEmailField(max_length=254)
    code_hash = models.CharField(max_length=64)
    salt = models.CharField(max_length=64)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField()
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "otp_code"
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return str(self.id)


# ---------------------------------------------------------------------------------------
# WebAuthn
# ---------------------------------------------------------------------------------------
class AuthChallenge(models.Model):
    """A short-lived challenge for one ceremony (registration, sign-in, step-up)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=16, choices=_choices(ChallengeKind))
    challenge = models.CharField(max_length=128, unique=True)  # base64url of the random bytes
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name="challenges")
    session = models.ForeignKey(
        "identity.UserSession", null=True, blank=True, on_delete=models.CASCADE, related_name="challenges"
    )
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "auth_challenge"
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.kind} {self.id}"


class WebAuthnCredential(models.Model):
    """A passkey (ID-03, ID-04): the fields playbook 4.2 lists. Retired, never deleted."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="credentials")
    credential_id = models.CharField(max_length=1024, unique=True)  # base64url
    public_key = models.TextField()  # base64url COSE
    sign_count = models.PositiveBigIntegerField(default=0)
    transports = ArrayField(models.CharField(max_length=32), default=list, blank=True)
    aaguid = models.CharField(max_length=36, blank=True)
    backup_eligible = models.BooleanField(default=False)
    backed_up = models.BooleanField(default=False)
    device_type = models.CharField(max_length=16, choices=_choices(PasskeyDeviceType))
    nickname = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "webauthn_credential"
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return self.nickname or str(self.id)


# ---------------------------------------------------------------------------------------
# Sessions, step-up, keys
# ---------------------------------------------------------------------------------------
class UserSession(models.Model):
    """One signed-in device (D-06, ADR 0006). A row behind every refresh so a person or an
    admin can revoke at once. `tenant` is null for a platform session."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions")
    tenant = models.ForeignKey("shared.Tenant", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=16, choices=_choices(SessionKind))
    refresh_token_hash = models.CharField(max_length=64, unique=True)
    previous_refresh_hash = models.CharField(max_length=64, null=True, blank=True)
    rotated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=64, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = "user_session"
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.kind} {self.id}"


class StepUpAssertion(models.Model):
    """A fresh passkey assertion on a session (ID-06). `record()` stores its id on the
    audit event of the action it unlocked."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(UserSession, on_delete=models.CASCADE, related_name="step_up_assertions")
    credential = models.ForeignKey(WebAuthnCredential, on_delete=models.PROTECT, related_name="+")
    challenge = models.ForeignKey(AuthChallenge, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "step_up_assertion"
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return str(self.id)


class ApiKey(models.Model):
    """A scoped key for agents and integrations (ID-10). `tenant` null is a platform key.
    `agent_id` becomes a foreign key in chunk 5."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("shared.Tenant", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    agent_id = models.UUIDField(null=True, blank=True)
    name = models.CharField(max_length=200)
    key_prefix = models.CharField(max_length=8, unique=True)
    key_hash = models.CharField(max_length=64)
    scopes = ArrayField(models.CharField(max_length=32), default=list, blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "api_key"
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return self.name


class LoginEvent(AppendOnlyModel):
    """The security log (ID-11): sign-ins, failures, enrolments, recoveries and key use.
    Append-only in Python and by trigger; the mixed policy shows platform rows
    (tenant null) to platform staff and tenant rows to their tenant."""

    id = models.BigAutoField(primary_key=True)
    occurred_at = models.DateTimeField(auto_now_add=True)
    tenant = models.ForeignKey("shared.Tenant", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="login_events")
    api_key = models.ForeignKey(ApiKey, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    email = CIEmailField(max_length=254, blank=True)
    method = models.CharField(max_length=16, choices=_choices(LoginMethod))
    event = models.CharField(max_length=32, choices=_choices(LoginEventKind))
    success = models.BooleanField()
    failure_reason = models.CharField(max_length=100, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = "login_event"
        ordering = ["occurred_at", "id"]
        indexes = [models.Index(fields=["tenant", "occurred_at"], name="login_event_tenant_time")]

    def __str__(self) -> str:
        return f"{self.event} {self.id}"
