"""Request and response schemas of the identity app (chunk 1 brief, API contract):
camelCase through CamelSchema. The WebAuthn shapes mirror what py_webauthn's
`options_to_json_dict` emits and what `navigator.credentials` returns, with the two
field names whose casing the alias generator cannot derive (`clientDataJSON`, `rpId`
is fine) pinned by explicit aliases."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field

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


class MeCounts(CamelSchema):
    """The queue counts behind Today's "Decide now" panel (HOM-01, D-23): three
    independent reads, each filtered by the caller's own permissions rather than
    refused, so a reader without a permission sees a true zero and not a 403 that
    would take the whole panel away."""

    triage: int = Field(
        ge=0,
        description=(
            "How many of this bank's cases are waiting for triage (status `new`), never "
            "negative and 0 without `cases.triage` — a permission the caller lacks reads as "
            "nothing waiting, never as a refusal."
        ),
        examples=[3],
    )
    proposals: int = Field(
        ge=0,
        description=(
            "How many of this bank's own library proposals are still open, never negative "
            "and 0 without `proposals.create`."
        ),
        examples=[2],
    )
    assigned_to_me: int = Field(
        ge=0,
        description=(
            "How many open cases (not `closed` or `dismissed`) this caller owns, never "
            "negative. Every member sees their own, so this is 0 only when they own none."
        ),
        examples=[1],
    )


class Me(CamelSchema):
    user: MeUser
    tenant: MeTenant | None
    roles: list[RoleRef]
    permissions: list[str]
    platform_roles: list[RoleRef]
    enrolment_pending: bool
    passkey_count: int
    step_up_valid_until: datetime | None
    counts: MeCounts | None = Field(
        description=(
            "The caller's own queue counts for 'Decide now' (D-23), or null for a platform "
            "session, which has no tenant to count against. Each of the three counts is 0 "
            "rather than refused when the caller's permissions do not unlock it (f03-T48)."
        )
    )
    last_visit_at: datetime | None = Field(
        description=(
            "When this member last marked the library as seen (`POST /me/visit`), as an "
            "RFC 3339 timestamp in UTC, or null before their first visit. Null for a platform "
            "session. It is a reading habit, this bank's own, and never a judgement about a "
            "regulation."
        ),
        examples=["2026-09-18T07:00:00Z"],
    )


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


# What a bank's key may hold, in words, beside the set that enforces it
# (perms.TENANT_KEY_SCOPES). Shared by the three ApiKey* shapes so the list cannot drift.
_TENANT_KEY_SCOPES_TEXT = (
    "`library:read` reads the shared library's instruments, provisions and obligations; "
    "`search:read` searches it; `upcoming:read` reads the public regulatory dates coming up; "
    "`tenant:read` reads the bank's own profile; and `proposals:write` files a proposal to the "
    "shared library, which changes nothing until someone independent approves it. No scope "
    "writes a library record. `agent-runs:write`, `sources:write`, `changes:write` and "
    "`proposals:review` belong to the platform's own agents and are refused on a bank's key."
)


class ApiKeyOut(CamelSchema):
    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[str] = Field(
        description=(
            "What this key may do, as scope keys. A bank's key holds only these: "
            + _TENANT_KEY_SCOPES_TEXT
            + " A key created before that rule may still list a platform scope here; it works "
            "without it, and the security log records `key_scopes_withheld` when it is used."
        )
    )
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None


class ApiKeysPage(CamelSchema):
    items: list[ApiKeyOut]
    total: int


class ApiKeyCreate(CamelSchema):
    name: str = Field(max_length=200)
    scopes: list[str] = Field(
        min_length=1,
        description=(
            "What the new key may do, at least one scope key, each counted once. A bank's key "
            "may hold only these: "
            + _TENANT_KEY_SCOPES_TEXT
            + " Anything else is refused with `unknown_key`, and the message lists the valid scopes."
        ),
    )
    expires_at: datetime | None = None


class ApiKeyCreated(CamelSchema):
    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[str] = Field(description="What the new key may do, as scope keys, sorted. " + _TENANT_KEY_SCOPES_TEXT)
    created_at: datetime
    expires_at: datetime | None
    plain_key: str


# ---------------------------------------------------------------------------------------
# Platform agent keys (ID-10, AGT-01). A key bound to an agent is the platform's: bleqq's
# agents are platform-owned and platform-run, so `agentId` sits on this request and never
# on the tenant's `POST /tenant/api-keys` (chunk 5 plan rule 13). Every example is the
# prototype's nightly watch sweeper, never a real key.
# ---------------------------------------------------------------------------------------
_AGENT_KEY_SCOPES_TEXT = (
    "`agent-runs:write` opens and closes the agent's runs; `sources:write` logs which sources "
    "a run checked; `changes:write` registers a regulatory change and writes its facts on the "
    "watch feed; `proposals:write` files a proposal to the shared library; `proposals:review` "
    "reads the proposal queue and approves, corrects or rejects a proposal someone else filed, "
    "as the independent second pair of eyes; `search:read` searches the library; `library:read` "
    "reads its records and vocabularies; `upcoming:read` reads the public dates coming up; "
    "`tenant:read` reads a bank's profile, of which a key that belongs to no bank has none. No "
    "scope writes a library record: a finding becomes a change or a proposal, never an edit."
)
_EXAMPLE_AGENT_ID = "3c9e1f27-58b4-4d6a-a0e2-6f41b7c8d953"
_EXAMPLE_AGENT_KEY: dict[str, Any] = {
    "id": "0b6f4c8e-2d1a-4e7b-9c35-7a1e5d2f9b40",
    "name": "Watch sweeper, nightly",
    "keyPrefix": "5e0c9a41",
    "scopes": ["agent-runs:write", "changes:write", "library:read", "sources:write"],
    "agentId": _EXAMPLE_AGENT_ID,
    "agent": {"key": "watch-sweeper", "kind": None, "label": "watch-sweeper v1"},
    "createdAt": "2026-09-10T08:00:00Z",
    "expiresAt": "2027-09-10T23:59:59Z",
    "revokedAt": None,
    "lastUsedAt": "2026-09-19T02:00:03Z",
}
_EXAMPLE_AGENT_KEY_CREATED: dict[str, Any] = {
    key: value for key, value in _EXAMPLE_AGENT_KEY.items() if key not in ("agent", "revokedAt", "lastUsedAt")
} | {"plainKey": "cw_5e0c9a41_<secret-shown-once>"}


class AgentKeyOut(CamelSchema):
    """One platform key as the console lists it. The secret is never here, only its prefix."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_AGENT_KEY]})

    id: uuid.UUID = Field(
        description=(
            "The key's permanent identifier, a UUID the server issues. Pass it to "
            "`POST /agent-keys/{key_id}/revoke`; it is not the key itself and cannot sign a request."
        )
    )
    name: str = Field(
        description=(
            "The name a platform administrator gave the key, such as `Watch sweeper, nightly`, to "
            "tell keys apart on screen. It is a label and nothing reads it: the agent the key acts "
            "as is `agent`, not this name."
        )
    )
    key_prefix: str = Field(
        description=(
            "The first part of the key, eight hexadecimal characters such as `5e0c9a41`, kept in "
            "the clear so a key found in a log or a vault can be matched to this row. It is not "
            "a secret and is not enough to call the API: the rest of the key was shown once, at "
            "creation, and only its hash is stored."
        )
    )
    scopes: list[str] = Field(description="What the key may do, as scope keys, sorted. " + _AGENT_KEY_SCOPES_TEXT)
    agent_id: uuid.UUID | None = Field(
        description=(
            "The identifier of the agent definition the key is bound to, a UUID from "
            "`GET /agent-definitions`. Everything the key writes is recorded as that agent, so the "
            "audit trail names the agent rather than the key. Null only for a platform key bound to "
            "no agent, which is listed so that it can be seen and revoked; this API never creates "
            "one, and the review queue refuses one."
        )
    )
    agent: RoleRef | None = Field(
        description=(
            "The bound agent definition as its stable key, such as `watch-sweeper`, with a label "
            "naming its current version to show on screen, such as `watch-sweeper v1`. The kind is "
            "null because the field already says what the key points at. Agent definitions are "
            "platform rows loaded from versioned definition folders, not a vocabulary an admin "
            "may extend or add to. Null exactly when `agentId` is."
        )
    )
    created_at: datetime = Field(description="When the key was created, as a UTC timestamp in ISO 8601, set by the server.")
    expires_at: datetime | None = Field(
        description=(
            "When the key stops working on its own, as a UTC timestamp in ISO 8601; from that "
            "moment every call with it answers `unauthenticated`. Null for a key that does not "
            "expire, which stays live until it is revoked."
        )
    )
    revoked_at: datetime | None = Field(
        description=(
            "When a platform administrator revoked the key, as a UTC timestamp in ISO 8601; from "
            "that moment every call with it answers `unauthenticated`. A revoked key stays listed "
            "and in the security log, and cannot be turned back on. Null while it is live."
        )
    )
    last_used_at: datetime | None = Field(
        description=(
            "When the key last authenticated a call, as a UTC timestamp in ISO 8601. It moves at "
            "most once a minute by default, so it says a key is in use rather than counting its "
            "calls. Null for a key that has never been used."
        )
    )


class AgentKeysPage(CamelSchema):
    """`{items, total}` with `limit` and `offset` (playbook 10)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_EXAMPLE_AGENT_KEY], "total": 1}]})

    items: list[AgentKeyOut] = Field(
        description=(
            "The platform's keys on this page, newest first, revoked and expired ones included so "
            "that the list is the whole history. A bank's own keys are never here. An empty list "
            "is a 200 and means no platform key exists yet."
        )
    )
    total: int = Field(
        description="How many platform keys exist in total, not how many are on this page; use it to size a pager."
    )


class AgentKeyCreate(WriteBody):
    """`POST /agent-keys`: a field the schema does not name is refused, never dropped."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Watch sweeper, nightly",
                    "agentId": _EXAMPLE_AGENT_ID,
                    "scopes": ["agent-runs:write", "sources:write", "changes:write", "library:read"],
                    "expiresAt": "2027-09-10T23:59:59Z",
                }
            ]
        }
    )

    name: str = Field(
        min_length=1,
        max_length=200,
        description=(
            "A name to tell the key apart on screen, between 1 and 200 characters, such as "
            "`Watch sweeper, nightly`. Surrounding spaces are trimmed, and a name of spaces alone "
            "is refused with `name_required`."
        ),
    )
    agent_id: uuid.UUID = Field(
        description=(
            "The identifier of the agent definition the key will act as, a UUID taken from "
            "`GET /agent-definitions`. Everything the key writes is recorded as that agent, and a "
            "key runs that one agent and no other. An identifier that names no definition is "
            "refused with `unknown_key`."
        )
    )
    scopes: list[str] = Field(
        min_length=1,
        max_length=len(perms.ALL_SCOPES),
        description=(
            f"What the key may do: at least one and at most {len(perms.ALL_SCOPES)} scope keys, "
            "each counted once. Give the key the least its agent needs. "
            + _AGENT_KEY_SCOPES_TEXT
            + " Any other value is refused with `unknown_key`, and the message lists the valid scopes."
        ),
    )
    expires_at: datetime | None = Field(
        default=None,
        description=(
            "When the key should stop working on its own, as a UTC timestamp in ISO 8601 that must "
            "lie in the future, or `expiry_in_past` is answered. Leave it out or send null for a "
            "key that lives until it is revoked."
        ),
    )


class AgentKeyCreated(CamelSchema):
    """The secret appears here and nowhere else: no log, no audit value, no outbox payload."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_AGENT_KEY_CREATED]})

    id: uuid.UUID = Field(
        description="The new key's permanent identifier, a UUID: the handle to revoke it by, never the key itself."
    )
    name: str = Field(description="The name the key was given, trimmed, exactly as it will be listed.")
    key_prefix: str = Field(
        description=(
            "The eight hexadecimal characters the key begins with after `cw_`, kept in the clear "
            "so the key can be recognised in the list later without the secret."
        )
    )
    scopes: list[str] = Field(description="What the key may do, as scope keys, sorted. " + _AGENT_KEY_SCOPES_TEXT)
    agent_id: uuid.UUID = Field(
        description="The identifier of the agent definition the key acts as; everything it writes is recorded as that agent."
    )
    created_at: datetime = Field(description="When the key was created, as a UTC timestamp in ISO 8601, set by the server.")
    expires_at: datetime | None = Field(
        description="When the key stops working on its own, as a UTC timestamp in ISO 8601, or null for a key with no expiry."
    )
    plain_key: str = Field(
        description=(
            "The key itself, `cw_<prefix>_<secret>`, to be sent as `X-Api-Key` or as a bearer "
            "token. This answer is the only time it exists outside the caller: the server keeps "
            "only a hash of the secret, never logs it and never shows it again, so put it straight "
            "into the agent runner's secret store. A lost key is revoked and replaced, not recovered."
        )
    )


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
