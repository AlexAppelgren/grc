"""Request and response schemas of the identity app (chunk 1 brief, API contract):
camelCase through CamelSchema. The WebAuthn shapes mirror what py_webauthn's
`options_to_json_dict` emits and what `navigator.credentials` returns, with the two
field names whose casing the alias generator cannot derive (`clientDataJSON`, `rpId`
is fine) pinned by explicit aliases."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from apps.shared import permissions as perms
from apps.shared.schemas import CamelSchema, WriteBody

__all__ = ["CamelSchema"]


class Empty(CamelSchema):
    """`{}`: the neutral answer of the code request and the accepted re-issue."""


class RoleRef(CamelSchema):
    """A pointer to a row in one of the platform's managed lists — a role, a language, an
    agent — as key, kind and label together, so a screen can show a name while an
    integration stores something that never moves under it."""

    key: str = Field(
        description=(
            "The stable key of the row being pointed at: a role such as `admin`, a language "
            "such as `sv`, an agent definition such as `watch-sweeper`. Store and compare this "
            "and never the label — a key is issued once and never changes, while a label is "
            "reworded and translated freely. Some of the lists behind a reference are "
            "vocabularies whose rows a bank's admin may extend or retire, so an unfamiliar key "
            "is new data and not an error; others, such as the content languages, are library "
            "reference rows that only an approved proposal adds to. Read the endpoint that "
            "owns the list for the live set."
        )
    )
    kind: str | None = Field(
        default=None,
        description=(
            "Which list the key belongs to, where one shape carries rows from more than one "
            "list — the name of the vocabulary, for instance. It is null wherever the field "
            "holding the reference already settles the question, as it does for a language or "
            "a role, and a reader should then take the kind from that field rather than "
            "guessing from the key."
        ),
    )
    label: str = Field(
        description=(
            "The row's name in the reader's language, for showing on screen and for nothing "
            "else. It is reworded whenever the bank prefers different wording and it is "
            "translated, so storing it or matching on it will break; keep the key instead."
        )
    )


# ---------------------------------------------------------------------------------------
# /auth
# ---------------------------------------------------------------------------------------
class CodeRequestBody(CamelSchema):
    email: str = Field(max_length=254)


class CodeVerifyBody(CamelSchema):
    email: str = Field(max_length=254)
    code: str = Field(max_length=12)


class InvitationOpenBody(CamelSchema):
    """Opening the emailed link. The token rides in the body, never a path, so no server
    that logs request lines ever holds it (security review F29)."""

    token: str = Field(max_length=128)


class InvitationCodeVerifyBody(CamelSchema):
    """The invitation path: the link's token names the account, so no address travels.
    The token rides in the body, never the path, so no access log holds it (F6, F29)."""

    token: str = Field(max_length=128)
    code: str = Field(max_length=12)


class SessionTokens(CamelSchema):
    access_token: str
    session_kind: str
    expires_in: int


class RefreshResult(CamelSchema):
    access_token: str
    expires_in: int


class WebAuthnRpEntity(CamelSchema):
    name: str
    id: str | None = None


class WebAuthnUserEntity(CamelSchema):
    id: str
    name: str
    display_name: str


class WebAuthnPubKeyCredParam(CamelSchema):
    type: str
    alg: int


class WebAuthnCredentialDescriptor(CamelSchema):
    id: str
    type: str
    transports: list[str] | None = None


class WebAuthnAuthenticatorSelection(CamelSchema):
    authenticator_attachment: str | None = None
    resident_key: str | None = None
    require_resident_key: bool | None = None
    user_verification: str | None = None


class WebAuthnCreationOptions(CamelSchema):
    """`navigator.credentials.create({publicKey: ...})`, bytes as base64url."""

    rp: WebAuthnRpEntity
    user: WebAuthnUserEntity
    challenge: str
    pub_key_cred_params: list[WebAuthnPubKeyCredParam]
    timeout: int | None = None
    exclude_credentials: list[WebAuthnCredentialDescriptor] | None = None
    authenticator_selection: WebAuthnAuthenticatorSelection | None = None
    attestation: str | None = None
    hints: list[str] | None = None


class WebAuthnRequestOptions(CamelSchema):
    """`navigator.credentials.get({publicKey: ...})`, bytes as base64url."""

    challenge: str
    timeout: int | None = None
    rp_id: str | None = None
    allow_credentials: list[WebAuthnCredentialDescriptor] | None = None
    user_verification: str | None = None


class WebAuthnAttestationResponse(CamelSchema):
    client_data_json: str = Field(alias="clientDataJSON")
    attestation_object: str = Field(alias="attestationObject")
    transports: list[str] | None = None


class PasskeyRegistrationCredential(CamelSchema):
    """What the browser returns from `create()`, serialised with base64url fields."""

    id: str
    raw_id: str = Field(alias="rawId")
    type: str
    response: WebAuthnAttestationResponse
    authenticator_attachment: str | None = Field(default=None, alias="authenticatorAttachment")
    client_extension_results: dict[str, Any] | None = Field(default=None, alias="clientExtensionResults")


class WebAuthnAssertionResponse(CamelSchema):
    client_data_json: str = Field(alias="clientDataJSON")
    authenticator_data: str = Field(alias="authenticatorData")
    signature: str
    user_handle: str | None = Field(default=None, alias="userHandle")


class PasskeyAuthenticationCredential(CamelSchema):
    """What the browser returns from `get()`, serialised with base64url fields."""

    id: str
    raw_id: str = Field(alias="rawId")
    type: str
    response: WebAuthnAssertionResponse
    authenticator_attachment: str | None = Field(default=None, alias="authenticatorAttachment")
    client_extension_results: dict[str, Any] | None = Field(default=None, alias="clientExtensionResults")


class PasskeyRegisterBody(CamelSchema):
    credential: PasskeyRegistrationCredential
    # Optional (ID-04): absent or blank, the server names the passkey from the device
    # (apps/identity/passkey_names.py). Renaming stays on PATCH /me/passkeys/{id}.
    nickname: str | None = Field(default=None, max_length=100)


class PasskeyAssertBody(CamelSchema):
    credential: PasskeyAuthenticationCredential


class PasskeyOut(CamelSchema):
    id: uuid.UUID
    nickname: str
    device_type: str
    backed_up: bool
    transports: list[str]
    created_at: datetime
    last_used_at: datetime | None


class PasskeyRegistered(CamelSchema):
    passkey: PasskeyOut
    access_token: str | None
    session_kind: str
    expires_in: int | None


class PasskeyPatch(CamelSchema):
    nickname: str = Field(max_length=100)


class StepUpResult(CamelSchema):
    assertion_id: uuid.UUID
    expires_at: datetime


# ---------------------------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------------------------
class MeUser(CamelSchema):
    id: uuid.UUID
    email: str
    name: str
    locale: str | None


class MeTenant(CamelSchema):
    id: uuid.UUID
    name: str
    slug: str
    timezone: str


class Me(CamelSchema):
    user: MeUser
    tenant: MeTenant | None
    roles: list[RoleRef]
    permissions: list[str]
    platform_roles: list[RoleRef]
    enrolment_pending: bool
    passkey_count: int
    step_up_valid_until: datetime | None


class MePatch(CamelSchema):
    name: str | None = Field(default=None, max_length=200)
    locale: str | None = Field(default=None, max_length=8)


class SessionOut(CamelSchema):
    id: uuid.UUID
    current: bool
    created_at: datetime
    last_seen_at: datetime
    ip: str | None
    user_agent: str


# ---------------------------------------------------------------------------------------
# Tenant admin: members, invitations, roles, keys, security log
# ---------------------------------------------------------------------------------------
class MemberOut(CamelSchema):
    user_id: uuid.UUID
    email: str
    name: str
    status: str
    roles: list[RoleRef]
    title: str
    last_seen_at: datetime | None
    passkey_count: int
    active_sessions: int


class MembersPage(CamelSchema):
    items: list[MemberOut]
    total: int


class MemberInvite(CamelSchema):
    email: str = Field(max_length=254)
    role_keys: list[str] = Field(min_length=1)
    title: str = Field(default="", max_length=200)


class MemberPatch(CamelSchema):
    role_keys: list[str] | None = None
    title: str | None = Field(default=None, max_length=200)


class InvitationOut(CamelSchema):
    id: uuid.UUID
    email: str
    roles: list[RoleRef]
    title: str
    kind: str
    status: str
    created_at: datetime
    expires_at: datetime


class InvitationsPage(CamelSchema):
    items: list[InvitationOut]
    total: int


class RoleOut(CamelSchema):
    key: str
    kind: str | None
    label: str
    labels: dict[str, str]
    usage_note: str
    permissions: list[str]
    is_system: bool
    active: bool


class RoleCreate(CamelSchema):
    key: str = Field(max_length=80)
    labels: dict[str, str]
    usage_note: str = Field(default="", max_length=1000)
    permissions: list[str]


class RolePatch(CamelSchema):
    labels: dict[str, str] | None = None
    usage_note: str | None = Field(default=None, max_length=1000)
    permissions: list[str] | None = None


class PermissionOut(CamelSchema):
    key: str
    group: str
    description: str


class ApiKeyOut(CamelSchema):
    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None


class ApiKeysPage(CamelSchema):
    items: list[ApiKeyOut]
    total: int


class ApiKeyCreate(CamelSchema):
    name: str = Field(max_length=200)
    scopes: list[str] = Field(min_length=1)
    expires_at: datetime | None = None


class ApiKeyCreated(CamelSchema):
    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime | None
    plain_key: str


# ---------------------------------------------------------------------------------------
# Platform agent keys (ID-10, AGT-01). A key bound to an agent is the platform's: bleqq's
# agents are platform-owned and platform-run, so `agentId` sits on this request and never
# on the tenant's `POST /tenant/api-keys` (chunk 5 plan rule 13).
# ---------------------------------------------------------------------------------------
class AgentKeyOut(CamelSchema):
    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[str]
    agent_id: uuid.UUID | None
    agent: RoleRef | None
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None


class AgentKeysPage(CamelSchema):
    items: list[AgentKeyOut]
    total: int


class AgentKeyCreate(WriteBody):
    name: str = Field(min_length=1, max_length=200)
    agent_id: uuid.UUID
    scopes: list[str] = Field(min_length=1, max_length=len(perms.ALL_SCOPES))
    expires_at: datetime | None = None


class AgentKeyCreated(CamelSchema):
    """The secret appears here and nowhere else: no log, no audit value, no outbox payload."""

    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[str]
    agent_id: uuid.UUID
    created_at: datetime
    expires_at: datetime | None
    plain_key: str


class SecurityEventOut(CamelSchema):
    id: int
    occurred_at: datetime
    method: str
    event: str
    success: bool
    failure_reason: str
    user_id: uuid.UUID | None
    email: str
    ip: str | None
    user_agent: str


class SecurityLogPage(CamelSchema):
    items: list[SecurityEventOut]
    total: int
