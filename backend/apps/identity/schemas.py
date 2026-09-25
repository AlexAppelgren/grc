"""Request and response schemas of the identity app (chunk 1 brief, API contract):
camelCase through CamelSchema. The WebAuthn shapes mirror what py_webauthn's
`options_to_json_dict` emits and what `navigator.credentials` returns, with the two
field names whose casing the alias generator cannot derive (`clientDataJSON`, `rpId`
is fine) pinned by explicit aliases."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from django.conf import settings
from pydantic import ConfigDict, Field, JsonValue

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
#
# Written for an integrator who has never seen this codebase
# (docs/plans/briefs/API_DOCUMENTATION.md). The WebAuthn meanings are the W3C's, read from
# Web Authentication Level 3 (Recommendation, 25 August 2026) and logged in
# docs/plans/Verification_Log.md; what this server sends in each member is read from
# apps/identity/passkey_logic.py.
#
# The examples are the prototype's bank (Example Bank AB, seeded as tenant A for the
# journeys) and its compliance officer Sara Lindqvist, on the product's own host, never a
# real customer. The WebAuthn values are well formed — the client data decodes, the
# attestation object is CBOR — and were made with a throwaway key for these docs alone, so
# none of them opens anything; the tokens carry a placeholder signature no server accepts.
# ---------------------------------------------------------------------------------------
_EXAMPLE_ACCESS_TOKEN = "v1.5c0d2a1e7b3f4c8e9a6d1b2c3e4f5a6b.full.1790150400.ExampleSignatureThatNoServerWillAccept00000"  # noqa: S105 a documentation example no server accepts
_EXAMPLE_ENROLMENT_TOKEN = "v1.5c0d2a1e7b3f4c8e9a6d1b2c3e4f5a6b.enrolment.1790150400.ExampleSignatureThatNoServerWillAccept00000"  # noqa: S105 a documentation example no server accepts
_EXAMPLE_CREDENTIAL_ID = "cGAj7tm8-pSeo4if4t4UZw"
_EXAMPLE_USER_HANDLE = "AAAAAAAAQACAAAAAAAABAg"  # Sara Lindqvist's account id, 16 bytes
_EXAMPLE_RP: dict[str, JsonValue] = {"name": "Compliance Watch", "id": "compliance.bleqq.com"}
_EXAMPLE_REGISTRATION_CHALLENGE = "BqOwQC6lHBNmyZ4zHF6elkvGZbLYkjFAiy0U0_1tSvx_Bh1qcD1E8F3kx2JNoPwOOHwMjfLI0U22_mQWkR6xDw"
_EXAMPLE_SIGN_IN_CHALLENGE = "17VoHXgjAFgx-a7KvEKYOGhID_jY6qtdxVWbbqlYnpYZUevP1U9KO-7YdzF428z81RchpdXMzymHYrb-g5LI4g"
_EXAMPLE_DESCRIPTOR: dict[str, JsonValue] = {"id": _EXAMPLE_CREDENTIAL_ID, "type": "public-key"}
_EXAMPLE_ATTESTATION_RESPONSE: dict[str, JsonValue] = {
    "clientDataJSON": (
        "eyJ0eXBlIjoid2ViYXV0aG4uY3JlYXRlIiwiY2hhbGxlbmdlIjoiQnFPd1FDNmxIQk5teVo0ekhGNmVsa3ZHWmJMWWtqRkFpeTBVMF8xdFN2eF9C"
        "aDFxY0QxRThGM2t4MkpOb1B3T09Id01qZkxJMFUyMl9tUVdrUjZ4RHciLCJvcmlnaW4iOiJodHRwczovL2NvbXBsaWFuY2UuYmxlcXEuY29tIiwi"
        "Y3Jvc3NPcmlnaW4iOmZhbHNlfQ"
    ),
    "attestationObject": (
        "o2NmbXRkbm9uZWdhdHRTdG10oGhhdXRoRGF0YViUx1ybolFRp_Yvz904eABUWO9MpIEWkReG-jUXymg8hkBdAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        "EHBgI-7ZvPqUnqOIn-LeFGelAQIDJiABIVggPrL3_N-yJVIgitm_kE9S0YkZxNJLzXlhV_C3NrWbXl4iWCCRvpVJLG06C1S4j5i7pPvcRbu8Jyrw"
        "5hW-eZh8dfzDUg"
    ),
    "transports": ["hybrid", "internal"],
}
_EXAMPLE_ASSERTION_RESPONSE: dict[str, JsonValue] = {
    "clientDataJSON": (
        "eyJ0eXBlIjoid2ViYXV0aG4uZ2V0IiwiY2hhbGxlbmdlIjoiMTdWb0hYZ2pBRmd4LWE3S3ZFS1lPR2hJRF9qWTZxdGR4VldiYnFsWW5wWVpVZXZQ"
        "MVU5S08tN1lkekY0Mjh6ODFSY2hwZFhNenltSFlyYi1nNUxJNGciLCJvcmlnaW4iOiJodHRwczovL2NvbXBsaWFuY2UuYmxlcXEuY29tIiwiY3Jv"
        "c3NPcmlnaW4iOmZhbHNlfQ"
    ),
    "authenticatorData": "x1ybolFRp_Yvz904eABUWO9MpIEWkReG-jUXymg8hkAdAAAAAA",
    "signature": "MEUCIFP6eeLo2Wx1xFw1uT8xSjydMQ8NBmCaeqLY-urHgqPYAiEApk3FBKiW0c_dwtT64nidwrSJdAxJiIR_O7jEfU-WTVo",
    "userHandle": _EXAMPLE_USER_HANDLE,
}
_EXAMPLE_REGISTRATION_CREDENTIAL: dict[str, JsonValue] = {
    "id": _EXAMPLE_CREDENTIAL_ID,
    "rawId": _EXAMPLE_CREDENTIAL_ID,
    "type": "public-key",
    "response": _EXAMPLE_ATTESTATION_RESPONSE,
    "authenticatorAttachment": "platform",
    "clientExtensionResults": {},
}
_EXAMPLE_AUTHENTICATION_CREDENTIAL: dict[str, JsonValue] = {
    "id": _EXAMPLE_CREDENTIAL_ID,
    "rawId": _EXAMPLE_CREDENTIAL_ID,
    "type": "public-key",
    "response": _EXAMPLE_ASSERTION_RESPONSE,
    "authenticatorAttachment": "platform",
    "clientExtensionResults": {},
}
_EXAMPLE_PASSKEY: dict[str, JsonValue] = {
    "id": "3b6f1d2e-8a4c-4f0b-9e7d-2c1a5b8f6e30",
    "nickname": "iCloud Keychain",
    "deviceType": "multi_device",
    "backedUp": True,
    "transports": ["hybrid", "internal"],
    "createdAt": "2026-09-14T08:12:31Z",
    "lastUsedAt": "2026-09-22T06:58:04Z",
}
_EXAMPLE_SECURITY_KEY: dict[str, JsonValue] = {
    "id": "a41c7e90-2f5b-4d8a-b3e6-91d0c4f7a852",
    "nickname": "YubiKey 5 NFC",
    "deviceType": "single_device",
    "backedUp": False,
    "transports": ["nfc", "usb"],
    "createdAt": "2026-09-14T08:20:02Z",
    "lastUsedAt": "2026-09-14T08:20:02Z",
}
_EXAMPLE_SESSION: dict[str, JsonValue] = {
    "id": "5c0d2a1e-7b3f-4c8e-9a6d-1b2c3e4f5a6b",
    "current": True,
    "createdAt": "2026-09-22T06:58:04Z",
    "lastSeenAt": "2026-09-22T09:41:17Z",
    "ip": "192.0.2.41",
    "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
}
_EXAMPLE_OTHER_SESSION: dict[str, JsonValue] = {
    "id": "e8a2f4c6-1d3b-4a7e-8c5f-0b9d2e6a4f13",
    "current": False,
    "createdAt": "2026-09-19T12:03:55Z",
    "lastSeenAt": "2026-09-19T15:27:40Z",
    "ip": "198.51.100.7",
    "userAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 Mobile/15E148 Safari/604.1",
}

# A list answer has no component schema of its own to carry an example, so api.py hangs these
# on the operations that return them.
MY_PASSKEYS_EXAMPLE: list[JsonValue] = [_EXAMPLE_PASSKEY, _EXAMPLE_SECURITY_KEY]
MY_SESSIONS_EXAMPLE: list[JsonValue] = [_EXAMPLE_SESSION, _EXAMPLE_OTHER_SESSION]
_EXAMPLE_EXPIRES_IN = settings.ACCESS_TOKEN_TTL_MINUTES * 60
_EXAMPLE_TIMEOUT = settings.CHALLENGE_TTL_SECONDS * 1000
ENROLMENT_SESSION_EXAMPLE: dict[str, JsonValue] = {"accessToken": _EXAMPLE_ENROLMENT_TOKEN, "sessionKind": "enrolment", "expiresIn": _EXAMPLE_EXPIRES_IN}
# Step-up lists the caller's own passkeys, where sign-in lists none; its challenge is the one
# the assertion example above answers.
STEP_UP_OPTIONS_EXAMPLE: dict[str, JsonValue] = {
    "challenge": _EXAMPLE_SIGN_IN_CHALLENGE,
    "timeout": _EXAMPLE_TIMEOUT,
    "rpId": "compliance.bleqq.com",
    "allowCredentials": [_EXAMPLE_DESCRIPTOR],
    "userVerification": "required",
}

# What every bytes value in the WebAuthn shapes is, said once.
_BASE64URL = "base64url-encoded without padding, the encoding WebAuthn's own JSON form uses"


class CodeRequestBody(CamelSchema):
    """Asking for a one-time enrolment code by email, the "First time here?" path. The code
    opens only an enrolment session that can register a passkey, never a full sign-in."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"email": "anna@example-bank.test"}]})

    email: str = Field(
        max_length=254,
        description=(
            "The address the invitation was sent to, at most 254 characters. Case and "
            "surrounding spaces are ignored. Any text is accepted and answered alike: a code "
            "goes out only when the address has an open invitation and no passkey yet, and "
            "the answer never says whether it did, so it never tells who holds an account."
        ),
    )


class CodeVerifyBody(CamelSchema):
    """Trading the emailed code for an enrolment session, on the "First time here?" path."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"email": "anna@example-bank.test", "code": "482915"}]})

    email: str = Field(
        max_length=254,
        description=(
            "The address the code was sent to, at most 254 characters, the same one given to "
            "`POST /auth/code/request`. Case and surrounding spaces are ignored. It names the "
            "code being checked and, through its newest open invitation, the bank the "
            "enrolment session will belong to."
        ),
    )
    code: str = Field(
        max_length=12,
        description=(
            f"The code from the email: {settings.ENROLMENT_CODE_DIGITS} digits by default, at "
            "most 12 characters, surrounding spaces ignored. It works once, for "
            f"{settings.ENROLMENT_CODE_TTL_MINUTES} minutes after it was sent, and "
            f"{settings.ENROLMENT_CODE_MAX_ATTEMPTS} wrong tries lock it (all three are settings). Only "
            "the newest code sent to the address counts; asking again retires the earlier one."
        ),
    )


class InvitationOpenBody(CamelSchema):
    """Opening the emailed link. The token rides in the body, never a path, so no server
    that logs request lines ever holds it."""

    # Security review F29: the token moved out of the path.

    model_config = ConfigDict(json_schema_extra={"examples": [{"token": "Tq3xExampleInvitationToken0fTheEmailedLinkA"}]})

    token: str = Field(
        max_length=128,
        description=(
            "The invitation token, at most 128 characters: the part after `#` in the emailed "
            "link (`/invite#<token>`). The fragment is never sent to any server by a browser, "
            "so the page reads it and posts it here. The token is single use and stops "
            f"working {settings.INVITATION_TTL_HOURS} hours after it was sent (a setting), "
            "once the invitee has enrolled, or when an administrator revokes or resends the "
            "invitation; the server keeps only its hash."
        ),
    )


class InvitationCodeVerifyBody(CamelSchema):
    """The invitation path: the link's token names the account, so no address travels.
    The token rides in the body, never the path, so no access log holds it."""

    # Security review F6 and F29: no address on this path, and the token out of the path.

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"token": "Tq3xExampleInvitationToken0fTheEmailedLinkA", "code": "482915"}]}
    )

    token: str = Field(
        max_length=128,
        description=(
            "The same invitation token that was posted to `POST /auth/invitations/open`, at "
            "most 128 characters. It names the invitation, and through it the address and the "
            "bank, so no email address travels on this path. A token that is unknown, used, "
            "expired or revoked is refused before the code is looked at."
        ),
    )
    code: str = Field(
        max_length=12,
        description=(
            f"The code the invitee received after opening the link: {settings.ENROLMENT_CODE_DIGITS} "
            "digits by default, at most 12 characters, surrounding spaces ignored. Only a code "
            "sent to the invitation's own address verifies; it works once, for "
            f"{settings.ENROLMENT_CODE_TTL_MINUTES} minutes, and "
            f"{settings.ENROLMENT_CODE_MAX_ATTEMPTS} wrong tries lock it (settings)."
        ),
    )


class SessionTokens(CamelSchema):
    """A session has just started. The access token is in the body; the refresh token is
    set as an `HttpOnly` cookie by the same response and never appears in a body."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"accessToken": _EXAMPLE_ACCESS_TOKEN, "sessionKind": "full", "expiresIn": _EXAMPLE_EXPIRES_IN}]}
    )

    access_token: str = Field(
        description=(
            "The bearer token for every other call: send it as `Authorization: Bearer "
            "<token>`. Treat it as opaque, keep it in memory and never in browser storage, "
            "and expect it to stop working after `expiresIn` seconds "
            f"({settings.ACCESS_TOKEN_TTL_MINUTES} minutes by default); `POST /auth/refresh` "
            "then issues the next one from the refresh cookie this response set. Revoking the "
            "session stops it at once, whatever its expiry."
        )
    )
    session_kind: str = Field(
        description=(
            "Which kind of session the token opens. `enrolment`: the first sign-in by emailed "
            "code, which may call only the passkey registration ceremony and `GET /me`; every "
            "other route answers 403 `enrolment_only` until a passkey is registered, and that "
            "registration replaces it with a full session. `full`: a normal signed-in session "
            "with the person's own permissions in their bank, or on the platform for platform "
            "staff."
        )
    )
    expires_in: int = Field(
        description=(
            "How many seconds the access token is good for from now: "
            f"{settings.ACCESS_TOKEN_TTL_MINUTES * 60} by default (a setting). Refresh a little "
            "before it runs out. The session itself lasts longer: it ends after "
            f"{settings.SESSION_IDLE_MINUTES_DEFAULT} minutes without a refresh or "
            f"{settings.SESSION_ABSOLUTE_HOURS_DEFAULT} hours after sign-in, whichever comes "
            "first."
        )
    )


class RefreshResult(CamelSchema):
    """The next access token for a live session. The rotated refresh token arrives as a
    cookie in the same response, never in the body."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"accessToken": _EXAMPLE_ACCESS_TOKEN, "expiresIn": _EXAMPLE_EXPIRES_IN}]})

    access_token: str = Field(
        description=(
            "A fresh bearer token for the same session, replacing the one the caller held: "
            "send it as `Authorization: Bearer <token>` and keep it in memory only. It carries "
            "the same session kind as before; refreshing never upgrades an enrolment session "
            "into a full one."
        )
    )
    expires_in: int = Field(
        description=(
            "How many seconds the new access token is good for: "
            f"{settings.ACCESS_TOKEN_TTL_MINUTES * 60} by default (a setting). It never "
            "outlives the session, which still ends after "
            f"{settings.SESSION_IDLE_MINUTES_DEFAULT} idle minutes or "
            f"{settings.SESSION_ABSOLUTE_HOURS_DEFAULT} hours after sign-in."
        )
    )


class WebAuthnRpEntity(CamelSchema):
    """The service the passkey belongs to (WebAuthn `PublicKeyCredentialRpEntity`)."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_RP]})

    name: str = Field(
        description=(
            f"The product's name, `{settings.PRODUCT_NAME}` by default (a setting), which some "
            "browsers show while the person creates the passkey. WebAuthn Level 3 deprecates "
            "this member because many "
            "browsers no longer display it, but it is still required, so it is always sent. "
            "For display only; nothing is decided on it."
        )
    )
    id: str | None = Field(
        default=None,
        description=(
            "The relying party identifier (RP ID): the domain the new passkey is bound to, "
            "such as `compliance.bleqq.com`. A passkey made for one RP ID never works for "
            "another, which is why the host is fixed before anybody enrols. This server always "
            "sends it; WebAuthn would read a missing value as the calling page's own domain."
        ),
    )


class WebAuthnUserEntity(CamelSchema):
    """The account the new passkey is for (WebAuthn `PublicKeyCredentialUserEntity`)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"id": _EXAMPLE_USER_HANDLE, "name": "compliance_officer@example-bank.test", "displayName": "Sara Lindqvist"}]
        }
    )

    id: str = Field(
        description=(
            f"The user handle, {_BASE64URL}: the 16 bytes of the person's account identifier, "
            "22 characters once encoded. It holds no name or address, as WebAuthn requires "
            "of a handle (at most 64 bytes, never personally identifying), and the "
            "authenticator hands it back as `userHandle` when the passkey later signs in, "
            "which is how a sign-in with no username finds the account."
        )
    )
    name: str = Field(
        description=(
            "The account name the browser and authenticator show when the person later picks "
            "among their passkeys: the email address they were invited with. For display "
            "only; WebAuthn never returns it to the server, and nothing is decided on it."
        )
    )
    display_name: str = Field(
        description=(
            "The person's name as their profile holds it, such as `Sara Lindqvist`, shown next "
            "to the account name in the passkey picker. For display only, never returned to "
            "the server, and never an identifier."
        )
    )


class WebAuthnPubKeyCredParam(CamelSchema):
    """One kind of key the server accepts (WebAuthn `PublicKeyCredentialParameters`)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"type": "public-key", "alg": -7}]})

    type: str = Field(
        description=(
            "The credential type, always `public-key`: the only credential type WebAuthn "
            "defines. A browser ignores an entry with a type it does not know."
        )
    )
    alg: int = Field(
        description=(
            "A signature algorithm the server accepts, as a COSE algorithm identifier. This "
            "server offers -8 (EdDSA), -7 (ES256) and -257 (RS256), the three WebAuthn "
            "recommends, in that order of preference. The authenticator creates a key with "
            "the first one it supports and fails the ceremony if it supports none."
        )
    )


class WebAuthnCredentialDescriptor(CamelSchema):
    """One existing passkey, named so the browser can find or avoid it (WebAuthn
    `PublicKeyCredentialDescriptor`)."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_DESCRIPTOR]})

    id: str = Field(
        description=(
            f"The credential ID of one of the person's live passkeys, {_BASE64URL}, exactly "
            "as the authenticator issued it (WebAuthn caps it at 1023 bytes before encoding). "
            "It is the authenticator's identifier for the passkey, not this product's `id` "
            "for it in `GET /me/passkeys`."
        )
    )
    type: str = Field(
        description=(
            "The credential type, always `public-key`. WebAuthn tells a browser to skip a "
            "descriptor whose type it does not know."
        )
    )
    transports: list[str] | None = Field(
        default=None,
        description=(
            "How the browser might reach the authenticator holding this passkey, a hint and "
            "not a restriction: `usb`, `nfc`, `ble` (Bluetooth), `smart-card`, `hybrid` (a "
            "phone reached from another device) or `internal` (built into the device). This "
            "server leaves it out today, so the browser tries every way it has."
        ),
    )


class WebAuthnAuthenticatorSelection(CamelSchema):
    """What the new passkey's authenticator must do (WebAuthn
    `AuthenticatorSelectionCriteria`)."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"residentKey": "required", "requireResidentKey": True, "userVerification": "required"}]}
    )

    authenticator_attachment: str | None = Field(
        default=None,
        description=(
            "Which kind of authenticator may be used: `platform` (built into the device, such "
            "as Windows Hello, Touch ID or an Android phone's screen lock) or `cross-platform` "
            "(a roaming authenticator, such as a security key or a phone reached from another "
            "device). This server leaves it out, so either kind is welcome."
        ),
    )
    resident_key: str | None = Field(
        default=None,
        description=(
            "Whether the passkey must be discoverable, meaning the authenticator itself "
            "remembers the account and can offer it with no username typed: `required`, "
            "`preferred` or `discouraged`. This server always sends `required`, because "
            "sign-in starts with no username; a browser that cannot create a discoverable "
            "credential fails the ceremony rather than make another kind."
        ),
    )
    require_resident_key: bool | None = Field(
        default=None,
        description=(
            "The WebAuthn Level 1 spelling of the same requirement, kept for older browsers: "
            "true exactly when `residentKey` is `required`, which is why this server always "
            "sends true. A browser that understands `residentKey` reads that instead."
        ),
    )
    user_verification: str | None = Field(
        default=None,
        description=(
            "Whether the authenticator must check that the person is who they say, by PIN, "
            "fingerprint or face, rather than only that somebody is present: `required`, "
            "`preferred` or `discouraged`. This server always sends `required` and refuses a "
            "response whose user-verified flag is not set."
        ),
    )


class WebAuthnCreationOptions(CamelSchema):
    """`navigator.credentials.create({publicKey: ...})`, bytes as base64url: WebAuthn's
    `PublicKeyCredentialCreationOptions` in its JSON form. Decode the byte members
    (`challenge`, `user.id`, each `excludeCredentials[].id`) to ArrayBuffers, or hand the
    whole object to `PublicKeyCredential.parseCreationOptionsFromJSON()`."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "rp": _EXAMPLE_RP,
                    "user": {"id": _EXAMPLE_USER_HANDLE, "name": "compliance_officer@example-bank.test", "displayName": "Sara Lindqvist"},
                    "challenge": _EXAMPLE_REGISTRATION_CHALLENGE,
                    "pubKeyCredParams": [{"type": "public-key", "alg": -8}, {"type": "public-key", "alg": -7}, {"type": "public-key", "alg": -257}],
                    "timeout": _EXAMPLE_TIMEOUT,
                    "excludeCredentials": [_EXAMPLE_DESCRIPTOR],
                    "authenticatorSelection": {"residentKey": "required", "requireResidentKey": True, "userVerification": "required"},
                    "attestation": "none",
                }
            ]
        }
    )

    rp: WebAuthnRpEntity = Field(
        description="The service the passkey will belong to: the product's name and the domain the passkey is bound to."
    )
    user: WebAuthnUserEntity = Field(
        description=(
            "The account the passkey is for: the caller's own, never anybody else's. Its `id` "
            "is what the authenticator returns as `userHandle` at every later sign-in."
        )
    )
    challenge: str = Field(
        description=(
            f"The server's random challenge, {_BASE64URL}: 64 random bytes, well above the 16 "
            "WebAuthn asks for. The authenticator signs it, which proves the response is fresh. "
            "It works once, only for the person and session that asked for it, and expires "
            f"{settings.CHALLENGE_TTL_SECONDS} seconds after it was issued (a setting); after "
            "that the verify call answers `challenge_expired` and the ceremony starts again."
        )
    )
    pub_key_cred_params: list[WebAuthnPubKeyCredParam] = Field(
        description=(
            "The kinds of key the server accepts, most preferred first: EdDSA, ES256 and "
            "RS256. The authenticator uses the first it supports."
        )
    )
    timeout: int | None = Field(
        default=None,
        description=(
            "How long, in milliseconds, the browser should wait for the person: "
            f"{settings.CHALLENGE_TTL_SECONDS * 1000} by default, the challenge's own "
            "lifetime. WebAuthn makes it a hint a browser may override, for example to give "
            "the person more time, but the server stops accepting the challenge when it "
            "expires, whatever the browser waited."
        ),
    )
    exclude_credentials: list[WebAuthnCredentialDescriptor] | None = Field(
        default=None,
        description=(
            "The person's passkeys that are already registered, so the browser does not "
            "create a second one on an authenticator that holds one; it asks the person to "
            "use a different authenticator instead. Empty at first enrolment, when there are "
            "none."
        ),
    )
    authenticator_selection: WebAuthnAuthenticatorSelection | None = Field(
        default=None,
        description=(
            "What the authenticator must do: always a discoverable passkey with user "
            "verification required, from any kind of authenticator."
        )
    )
    attestation: str | None = Field(
        default=None,
        description=(
            "How much proof of the authenticator's make and model the server wants back: "
            "`none` (no proof; a browser replaces any it is given with none, unless the "
            "authenticator only vouched for itself), `indirect` (a "
            "verifiable proof the browser may anonymise), `direct` (the authenticator's own "
            "proof) or `enterprise` (a proof that may identify the individual device, only "
            "where a managed deployment allows it). This server always sends `none`, so no "
            "prompt asks the person to share device details."
        ),
    )
    hints: list[str] | None = Field(
        default=None,
        description=(
            "Hints to the browser about how the person will most likely answer, first one "
            "wins: `security-key` (a physical security key), `client-device` (the device's "
            "own authenticator) or `hybrid` (a phone or similar general-purpose "
            "authenticator). This server sends none today, so the browser offers every way "
            "it has."
        ),
    )


class WebAuthnRequestOptions(CamelSchema):
    """`navigator.credentials.get({publicKey: ...})`, bytes as base64url: WebAuthn's
    `PublicKeyCredentialRequestOptions` in its JSON form, for signing in and for step-up.
    Decode `challenge` and each `allowCredentials[].id` to ArrayBuffers, or hand the whole
    object to `PublicKeyCredential.parseRequestOptionsFromJSON()`."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "challenge": _EXAMPLE_SIGN_IN_CHALLENGE,
                    "timeout": _EXAMPLE_TIMEOUT,
                    "rpId": "compliance.bleqq.com",
                    "allowCredentials": [],
                    "userVerification": "required",
                }
            ]
        }
    )

    challenge: str = Field(
        description=(
            f"The server's random challenge, {_BASE64URL}: 64 random bytes. The passkey signs "
            f"it. It works once and expires {settings.CHALLENGE_TTL_SECONDS} seconds after it "
            "was issued (a setting); a step-up challenge is further bound to the person and "
            "session that asked for it."
        )
    )
    timeout: int | None = Field(
        default=None,
        description=(
            "How long, in milliseconds, the browser should wait for the person: "
            f"{settings.CHALLENGE_TTL_SECONDS * 1000} by default, the challenge's own "
            "lifetime. A hint the browser may override; the challenge still expires on the "
            "server."
        ),
    )
    rp_id: str | None = Field(
        default=None,
        description=(
            "The domain the passkey must have been made for, such as `compliance.bleqq.com`. "
            "The browser checks that the page is on it, and the authenticator offers only "
            "passkeys bound to exactly this domain."
        ),
    )
    allow_credentials: list[WebAuthnCredentialDescriptor] | None = Field(
        default=None,
        description=(
            "Which passkeys may answer. Empty when signing in: the person has typed no "
            "username, so the authenticator offers whichever of its passkeys for this domain "
            "the person picks, and the account is found from the `userHandle` it returns. At "
            "step-up it lists the caller's own live passkeys, so no other account's passkey "
            "can confirm the action."
        ),
    )
    user_verification: str | None = Field(
        default=None,
        description=(
            "Whether the authenticator must verify the person by PIN, fingerprint or face: "
            "`required`, `preferred` or `discouraged`. This server always sends `required` and "
            "refuses an assertion whose user-verified flag is not set."
        ),
    )


class WebAuthnAttestationResponse(CamelSchema):
    """The authenticator's answer to `create()` (WebAuthn `AuthenticatorAttestationResponse`),
    in the JSON form `PublicKeyCredential.toJSON()` produces."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_ATTESTATION_RESPONSE]})

    client_data_json: str = Field(
        alias="clientDataJSON",
        description=(
            f"The browser's client data, {_BASE64URL}: a small JSON document naming the "
            "ceremony (`webauthn.create`), the challenge and the page's origin. The server "
            "checks all three, so a response made for another challenge or another site is "
            "refused."
        ),
    )
    attestation_object: str = Field(
        alias="attestationObject",
        description=(
            f"The authenticator's attestation object, CBOR {_BASE64URL}. It carries the new "
            "passkey's credential ID and public key, the authenticator's model identifier "
            "(AAGUID), the flags saying whether the person was verified and whether the "
            "passkey can be and is backed up, and the attestation statement, normally empty "
            "here because the server asks for none."
        ),
    )
    transports: list[str] | None = Field(
        default=None,
        description=(
            "How the browser believes the authenticator can be reached, from the response's "
            "`getTransports()`: any of `usb`, `nfc`, `ble`, `smart-card`, `hybrid` and "
            "`internal`. Stored with the passkey and shown under My passkeys; an absent or "
            "empty list is accepted."
        ),
    )


class PasskeyRegistrationCredential(CamelSchema):
    """What the browser returns from `create()`, serialised with base64url fields: the
    `RegistrationResponseJSON` that WebAuthn Level 3's `PublicKeyCredential.toJSON()`
    produces."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_REGISTRATION_CREDENTIAL]})

    id: str = Field(
        description=(
            f"The new passkey's credential ID, {_BASE64URL}. It becomes the passkey's "
            "identifier at every later sign-in and must be unique across every account: one "
            "already registered anywhere is refused with `registration_failed`."
        )
    )
    raw_id: str = Field(
        alias="rawId",
        description=f"The same credential ID as `id`, from the credential's raw bytes, {_BASE64URL}.",
    )
    type: str = Field(description="The credential type, always `public-key`, the only one WebAuthn defines.")
    response: WebAuthnAttestationResponse = Field(
        description="The authenticator's signed answer: the client data and the attestation object, with its transports."
    )
    authenticator_attachment: str | None = Field(
        default=None,
        alias="authenticatorAttachment",
        description=(
            "Which kind of authenticator made the passkey, as the browser reports it: "
            "`platform` (built into this device) or `cross-platform` (a security key or a "
            "phone). Null when the browser does not say. Used only to name the passkey when "
            "no name is given; nothing is allowed or refused on it."
        ),
    )
    client_extension_results: dict[str, Any] | None = Field(
        default=None,
        alias="clientExtensionResults",
        description=(
            "The outputs of any WebAuthn extensions, from `getClientExtensionResults()`. The "
            "server requests no extension and ignores what arrives here, so an empty object "
            "`{}` is what a browser normally sends."
        ),
    )


class WebAuthnAssertionResponse(CamelSchema):
    """The authenticator's answer to `get()` (WebAuthn `AuthenticatorAssertionResponse`), in
    the JSON form `PublicKeyCredential.toJSON()` produces."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_ASSERTION_RESPONSE]})

    client_data_json: str = Field(
        alias="clientDataJSON",
        description=(
            f"The browser's client data, {_BASE64URL}: a small JSON document naming the "
            "ceremony (`webauthn.get`), the challenge and the page's origin. The server finds "
            "the stored challenge from it and checks the origin and the ceremony type."
        ),
    )
    authenticator_data: str = Field(
        alias="authenticatorData",
        description=(
            f"The authenticator data, {_BASE64URL}: a hash of the domain the passkey is bound "
            "to, the flags saying the person was present and verified and whether the passkey "
            "is backed up, and the signature counter, which the server uses to spot a cloned "
            "authenticator."
        ),
    )
    signature: str = Field(
        description=(
            "The passkey's signature over the authenticator data and a hash of the client "
            f"data, {_BASE64URL}. The server verifies it with the public key stored at "
            "registration; this is the proof, and the private key never leaves the "
            "authenticator."
        )
    )
    user_handle: str | None = Field(
        default=None,
        alias="userHandle",
        description=(
            f"The user handle the passkey was registered with, {_BASE64URL}, or null when the "
            "authenticator returns none. At sign-in it is required and must name the "
            "passkey's own account; at step-up it may be null and is checked when present."
        ),
    )


class PasskeyAuthenticationCredential(CamelSchema):
    """What the browser returns from `get()`, serialised with base64url fields: the
    `AuthenticationResponseJSON` that WebAuthn Level 3's `PublicKeyCredential.toJSON()`
    produces."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_AUTHENTICATION_CREDENTIAL]})

    id: str = Field(
        description=(
            f"The credential ID of the passkey that answered, {_BASE64URL}. The server looks "
            "the passkey up by it; a retired passkey, or one it has never seen, is refused."
        )
    )
    raw_id: str = Field(
        alias="rawId",
        description=f"The same credential ID as `id`, from the credential's raw bytes, {_BASE64URL}.",
    )
    type: str = Field(description="The credential type, always `public-key`, the only one WebAuthn defines.")
    response: WebAuthnAssertionResponse = Field(
        description="The authenticator's signed answer: client data, authenticator data, signature and user handle."
    )
    authenticator_attachment: str | None = Field(
        default=None,
        alias="authenticatorAttachment",
        description=(
            "Which kind of authenticator answered, as the browser reports it: `platform` "
            "(built into this device) or `cross-platform` (a security key or a phone). Null "
            "when the browser does not say. Accepted and not used."
        ),
    )
    client_extension_results: dict[str, Any] | None = Field(
        default=None,
        alias="clientExtensionResults",
        description=(
            "The outputs of any WebAuthn extensions, from `getClientExtensionResults()`. The "
            "server requests none and ignores what arrives, so a browser normally sends `{}`."
        ),
    )


class PasskeyRegisterBody(CamelSchema):
    """Finishing a passkey registration: the browser's credential, and optionally a name."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"credential": _EXAMPLE_REGISTRATION_CREDENTIAL}]})

    credential: PasskeyRegistrationCredential = Field(
        description=(
            "The credential `navigator.credentials.create()` returned for the options from "
            "`POST /auth/passkeys/register/options`, in its JSON form, byte fields base64url."
        )
    )
    # Optional (ID-04): absent or blank, the server names the passkey from the device
    # (apps/identity/passkey_names.py). Renaming stays on PATCH /me/passkeys/{id}.
    nickname: str | None = Field(
        default=None,
        max_length=100,
        description=(
            "A name for the passkey, at most 100 characters, kept as given apart from "
            "surrounding spaces. Usually left out: the server then names it from the device — "
            "the authenticator's own name where it is known (\"iCloud Keychain\"), else the "
            "browser and platform (\"Chrome on Windows\"), else \"Security key\", \"Phone\" or "
            "\"Passkey\" — and adds a counter when the person already has one of that name. "
            "It can be renamed later."
        ),
    )


class PasskeyAssertBody(CamelSchema):
    """A passkey's answer to a sign-in or step-up challenge."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"credential": _EXAMPLE_AUTHENTICATION_CREDENTIAL}]})

    credential: PasskeyAuthenticationCredential = Field(
        description=(
            "The credential `navigator.credentials.get()` returned for the options the matching "
            "options call issued, in its JSON form, byte fields base64url."
        )
    )


class PasskeyOut(CamelSchema):
    """One of the person's own live passkeys. The public key and the signature counter stay
    on the server; nothing here is enough to sign in with."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_PASSKEY]})

    id: uuid.UUID = Field(
        description=(
            "This product's identifier for the passkey, a UUID, used to rename or remove it. "
            "It is not the WebAuthn credential ID, which the server never returns here."
        )
    )
    nickname: str = Field(
        description=(
            "The passkey's name as the person sees it under My passkeys, at most 100 "
            "characters: the one they gave, or the one the server derived from the device at "
            "registration. The person may rename it at any time, so show it and never key on "
            "it."
        )
    )
    device_type: str = Field(
        description=(
            "Whether the passkey may leave the device it was made on, fixed at registration "
            "from the authenticator's backup-eligible flag: `single_device` (bound to one "
            "authenticator, such as a security key; losing it loses the passkey) or "
            "`multi_device` (a synced passkey that a platform such as iCloud Keychain or "
            "Google Password Manager can copy to the person's other devices)."
        )
    )
    backed_up: bool = Field(
        description=(
            "Whether a synced passkey was backed up when it was registered, from the "
            "authenticator's backup-state flag. Always false for a `single_device` passkey. "
            "Recorded at registration and not refreshed at later sign-ins, so read it as how "
            "things stood then."
        )
    )
    transports: list[str] = Field(
        description=(
            "How the browser said the authenticator can be reached, at registration: any of "
            "`usb`, `nfc`, `ble`, `smart-card`, `hybrid` (a phone reached from another device) "
            "and `internal` (built into the device). Empty when the browser did not say."
        )
    )
    created_at: datetime = Field(description="When the passkey was registered, as a UTC timestamp.")
    last_used_at: datetime | None = Field(
        description=(
            "When the passkey last signed in or confirmed a step-up, as a UTC timestamp. A "
            "registration through this API sets it to the moment of registration; null means a "
            "passkey provisioned some other way that has not been used since."
        )
    )


class PasskeyRegistered(CamelSchema):
    """A passkey was stored. When it was the first one, the enrolment session has ended and
    a full session begins with this response."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"passkey": _EXAMPLE_PASSKEY, "accessToken": _EXAMPLE_ACCESS_TOKEN, "sessionKind": "full", "expiresIn": _EXAMPLE_EXPIRES_IN}]
        }
    )

    passkey: PasskeyOut = Field(description="The passkey just stored, with the name the server gave it or kept.")
    access_token: str | None = Field(
        description=(
            "Present only when this registration finished an enrolment: the bearer token of "
            "the new full session, which replaces the enrolment session (now revoked) and "
            "whose refresh cookie this response set. Null when a passkey was added from a "
            "full session, which carries on with the tokens it already holds."
        )
    )
    session_kind: str = Field(
        description=(
            "Always `full`: after this call the person holds a normal session, either the new "
            "one that `accessToken` opens or the full session they already had."
        )
    )
    expires_in: int | None = Field(
        description=(
            "How many seconds the new access token is good for, "
            f"{settings.ACCESS_TOKEN_TTL_MINUTES * 60} by default; null whenever "
            "`accessToken` is null."
        )
    )


class PasskeyPatch(CamelSchema):
    """Renaming one of your own passkeys."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"nickname": "Work laptop"}]})

    nickname: str = Field(
        max_length=100,
        description=(
            "The new name, at most 100 characters; surrounding spaces are trimmed. It is only "
            "a label for the person's own list and changes nothing about how the passkey "
            "signs in."
        ),
    )


class StepUpResult(CamelSchema):
    """A fresh passkey assertion, recorded on the caller's session."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"assertionId": "9f2e6c1a-4b7d-4e3f-a8c0-5d1b7e9a2c64", "expiresAt": "2026-09-22T09:46:17Z"}]}
    )

    assertion_id: uuid.UUID = Field(
        description=(
            "The identifier of the recorded assertion, a UUID. Every sensitive action taken "
            "on this session before `expiresAt` writes it onto its own audit event, so the "
            "audit trail shows which passkey confirmation stood behind which action."
        )
    )
    expires_at: datetime = Field(
        description=(
            "Until when, as a UTC timestamp, the assertion counts as fresh: "
            f"{settings.STEP_UP_FRESHNESS_MINUTES} minutes after it was made by default (a "
            "setting). Until then every sensitive action on this session may proceed; after "
            "it they answer 403 `step_up_required` again. It belongs to this session only."
        )
    )


# ---------------------------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------------------------
class MeUser(CamelSchema):
    """The signed-in person's own account. One account serves every bank the person belongs
    to, so these facts are the person's and not any one bank's."""

    id: uuid.UUID = Field(
        description=(
            "The person's account identifier, a UUID that never changes and is the same in "
            "every bank they belong to. Its bytes are also their passkeys' user handle."
        )
    )
    email: str = Field(
        description=(
            "The address the person was invited with, lower-cased. It is where codes and "
            "notices go and the account name their passkeys show, and it cannot be changed "
            "through the API."
        )
    )
    name: str = Field(
        description=(
            "The person's name as they chose it, shown to colleagues wherever the product says "
            "who did something. It belongs to the account, so every bank the person is in "
            "sees the same name; `PATCH /me` changes it."
        )
    )
    locale: str | None = Field(
        description=(
            "The language the person chose to read the product in, as a language key such as "
            "`en` or `sv`, or null when they have not chosen one and screens fall back to the "
            "bank's default language. Languages are library reference rows, read "
            "`GET /reference/languages` for the set."
        )
    )


class MeTenant(CamelSchema):
    """The bank the session is signed in to."""

    id: uuid.UUID = Field(
        description=(
            "The bank's permanent identifier, a UUID. Every tenant-zone record the session "
            "reads or writes belongs to this bank and no other."
        )
    )
    name: str = Field(description="The bank's own name for itself, such as `Example Bank AB`, for display.")
    slug: str = Field(
        description=(
            "The bank's short name, lower-case letters, digits and hyphens, such as "
            "`example-bank`: unique across the platform and fixed when the bank was created."
        )
    )
    timezone: str = Field(
        description=(
            "The IANA timezone the bank works in, such as `Europe/Stockholm`: the one a screen "
            "uses to turn a stored UTC instant into the bank's local day."
        )
    )


class MeCounts(CamelSchema):
    """The queue counts behind Today's "Decide now" panel: three independent reads, each
    filtered by the caller's own permissions rather than refused, so a reader without a
    permission sees a true zero and not a 403 that would take the whole panel away."""

    # HOM-01, D-23.

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
    """Who the caller is and what this session may do: the one read every screen makes
    first. The enrolment session may make it too, and sees `enrolmentPending` true."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "user": {
                        "id": "00000000-0000-4000-8000-000000000102",
                        "email": "compliance_officer@example-bank.test",
                        "name": "Sara Lindqvist",
                        "locale": "en",
                    },
                    "tenant": {
                        "id": "00000000-0000-4000-8000-00000000000a",
                        "name": "Example Bank AB",
                        "slug": "example-bank",
                        "timezone": "Europe/Stockholm",
                    },
                    "roles": [{"key": "compliance_officer", "kind": None, "label": "Compliance officer"}],
                    "permissions": [
                        "ai_log.read",
                        "applicability.approve",
                        "audit.read",
                        "cases.contribute",
                        "cases.read",
                        "cases.triage",
                        "cases.work",
                        "comments.write",
                        "exports.create",
                        "footprint.approve",
                        "footprint.request",
                        "gaps.edit",
                        "library.read",
                        "problems.report",
                        "proposals.create",
                        "register.edit",
                        "register.read",
                        "reports.read",
                        "risk.accept.approve",
                        "roadmap.read",
                        "search.use",
                        "vocab.manage",
                        "watch.read",
                        "workflow.manage",
                    ],
                    "platformRoles": [],
                    "enrolmentPending": False,
                    "passkeyCount": 2,
                    "stepUpValidUntil": None,
                    "counts": {"triage": 3, "proposals": 2, "assignedToMe": 1},
                    "lastVisitAt": "2026-09-18T07:00:00Z",
                }
            ]
        }
    )

    user: MeUser = Field(
        description=(
            "The signed-in person's own account: identifier, address, name and chosen "
            "language. Present for every session, the enrolment session included."
        )
    )
    tenant: MeTenant | None = Field(
        description=(
            "The bank this session is signed in to, or null for a platform session, which "
            "belongs to no bank. A person in several banks is signed in to the one they "
            "joined first; there is no bank switcher yet. An enrolment session already names "
            "the bank whose invitation it came from."
        )
    )
    roles: list[RoleRef] = Field(
        description=(
            "The person's roles in this bank, as key, kind and label: the seeded `admin`, "
            "`compliance_officer`, `owner`, `approver`, `contributor`, `reader` and `auditor`, "
            "plus any role the bank's own administrators added. Roles are rows of the bank's "
            "role vocabulary, which an admin may extend in the role editor (`GET /tenant/roles` "
            "lists the live set), so an unfamiliar key is new data and not an error. Never "
            "decide what to show from a role key; read `permissions`. Empty for a platform "
            "session and for an enrolment session."
        )
    )
    permissions: list[str] = Field(
        description=(
            "Everything this session may do, as permission keys such as `cases.triage` or "
            "`footprint.approve`: the union of the permissions of the person's roles in this "
            "bank, or of their platform roles on a platform session. Permissions are constants "
            "in code, not rows, so the set changes only with a release; "
            "`GET /reference/permissions` lists the bank-side ones with their meanings. Screens "
            "decide what to offer from these, never from a role. Empty for an enrolment session."
        )
    )
    platform_roles: list[RoleRef] = Field(
        description=(
            "The platform roles of platform staff, as key, kind and label: the seeded "
            "`platform_admin` and `library_editor`. Always empty for a member of a bank, "
            "because platform staff sign in with accounts of their own and a bank session "
            "never carries a platform grant. They are a platform vocabulary that only the "
            "platform's own administrators manage; a bank's admin cannot extend it."
        )
    )
    enrolment_pending: bool = Field(
        description=(
            "True while the person has not finished enrolling: the session is an enrolment "
            "session, which reaches only passkey registration and this call, or the account is "
            "not yet active. A screen that reads true sends the person to register a passkey. "
            "False for every full session of an active account."
        )
    )
    passkey_count: int = Field(
        description=(
            "How many live passkeys the person holds: 0 during first enrolment and at least 1 "
            "afterwards, because the last one cannot be removed. Retired passkeys are not "
            "counted. A screen uses it to suggest adding a second passkey."
        )
    )
    step_up_valid_until: datetime | None = Field(
        description=(
            "Until when the latest passkey step-up on this session stays fresh, as a UTC "
            "timestamp, or null when there is none or it has lapsed. While it lies ahead, a "
            "sensitive action — an approval, a sign-off, a footprint change, an export, a key, "
            "a role or security change, a re-enrolment — goes through without a new passkey "
            "prompt. Signing in never counts as a step-up."
        )
    )
    # The counts are D-23's; zero rather than refused is f03-T48.
    counts: MeCounts | None = Field(
        description=(
            "The caller's own queue counts for 'Decide now', or null for a platform session, "
            "which has no tenant to count against. Each of the three counts is 0 rather than "
            "refused when the caller's permissions do not unlock it."
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
    """Changing your own name or reading language. Send only what changes."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"name": "Sara Lindqvist", "locale": "sv"}]})

    name: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Your new name, at most 200 characters, surrounding spaces trimmed. Omit it or send "
            "null to leave the name as it is; a blank one is refused with `name_required`. "
            "Every bank you belong to shows the same name."
        ),
    )
    locale: str | None = Field(
        default=None,
        max_length=8,
        description=(
            "The language to read the product in, as a language key such as `sv` or `en`, at "
            "most 8 characters. Omit it or send null to leave it as it is; a key that is not an "
            "active language is refused with `unknown_key`. `GET /reference/languages` lists "
            "the keys on offer."
        ),
    )


class SessionOut(CamelSchema):
    """One signed-in device: when it signed in, when it was last active and from where."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_SESSION]})

    id: uuid.UUID = Field(
        description=(
            "The session's identifier, a UUID. A person signs one of their own devices out "
            "by passing it to `DELETE /me/sessions/{session_id}`."
        )
    )
    current: bool = Field(
        description=(
            "True for the session making this call, so a screen can mark this device and "
            "warn before the person signs it out. Always false in an administrator's list of "
            "a member's sessions."
        )
    )
    created_at: datetime = Field(
        description=(
            "When the person signed in on this device, as a UTC timestamp. The session ends "
            f"{settings.SESSION_ABSOLUTE_HOURS_DEFAULT} hours after it at the latest (a "
            "setting)."
        )
    )
    last_seen_at: datetime = Field(
        description=(
            "When the session last refreshed its access token, as a UTC timestamp: a sign of "
            "recent use that lags real activity by up to the access token's "
            f"{settings.ACCESS_TOKEN_TTL_MINUTES}-minute lifetime. After "
            f"{settings.SESSION_IDLE_MINUTES_DEFAULT} minutes without a refresh the session "
            "ends."
        )
    )
    ip: str | None = Field(
        description=(
            "The network address the person signed in from, IPv4 or IPv6 as text, or null "
            "when it was not known. Behind the product's own proxy it is the address that "
            "proxy saw the request come from. It is the person's data, shown to them and to "
            "their bank's administrators."
        )
    )
    user_agent: str = Field(
        description=(
            "The browser's own description of itself at sign-in (its User-Agent header), "
            "stored up to 500 characters and empty when the browser sent none. Screens turn "
            "it into a label such as \"Chrome on Windows\". It is the browser's claim and "
            "proves nothing about the device."
        )
    )


# ---------------------------------------------------------------------------------------
# Tenant admin: members, invitations, roles, keys, security log. Every example is the
# prototype's Example Bank AB, never a real bank or person.
# ---------------------------------------------------------------------------------------
_MEMBER_STATUS_TEXT = (
    "`invited` means an administrator re-issued the person's enrolment and they have not "
    "enrolled a new passkey yet, so they cannot sign in until they do; `active` means they "
    "hold a passkey and can sign in; `deactivated` means the bank removed them, their sessions "
    "here were ended and they can no longer sign in to this bank, though the record stays for "
    "the audit trail."
)
_ROLE_KEYS_TEXT = (
    "Role keys come from the bank's own role list, a vocabulary its administrators extend with "
    "`POST /tenant/roles`: the system roles seeded on day one are `admin`, `compliance_officer`, "
    "`owner`, `approver`, `contributor`, `reader` and `auditor`, and a bank may have added more. "
    "Read `GET /tenant/roles` for the live set and store keys, never labels."
)
_INVITATION_STATUS_TEXT = (
    "`pending` means the link still works and nobody has enrolled with it; `accepted` means the "
    "person enrolled their first passkey with it; `revoked` means an administrator withdrew it, "
    "a newer invitation to the same address replaced it, or the member was removed; `expired` "
    "means nobody used the link within its lifetime. Only a pending or expired invitation can be "
    "resent."
)
_EXAMPLE_ROLE_OFFICER: dict[str, JsonValue] = {"key": "compliance_officer", "kind": None, "label": "Compliance officer"}
_EXAMPLE_ROLE_READER: dict[str, JsonValue] = {"key": "reader", "kind": None, "label": "Reader"}
_EXAMPLE_MEMBER: dict[str, JsonValue] = {
    "userId": "00000000-0000-4000-8000-000000000102",
    "email": "compliance_officer@example-bank.test",
    "name": "Sara Lindqvist",
    "status": "active",
    "roles": [_EXAMPLE_ROLE_OFFICER],
    "title": "Head of Regulatory Compliance",
    "lastSeenAt": "2026-09-22T06:58:04Z",
    "passkeyCount": 2,
    "activeSessions": 1,
}
_EXAMPLE_INVITATION: dict[str, JsonValue] = {
    "id": "7d2e9b14-6a3c-4f58-b1d0-3e8c5a7f2b96",
    "email": "anna@example-bank.test",
    "roles": [_EXAMPLE_ROLE_READER],
    "title": "Compliance analyst",
    "kind": "invite",
    "status": "pending",
    "createdAt": "2026-09-22T08:15:00Z",
    "expiresAt": "2026-09-25T08:15:00Z",
}
_EXAMPLE_ROLE: dict[str, JsonValue] = {
    "key": "dora_reviewer",
    "kind": None,
    "label": "DORA reviewer",
    "labels": {"en": "DORA reviewer", "sv": "DORA-granskare"},
    "usageNote": "Reads the register and works the ICT-risk cases it is asked to help with.",
    "permissions": ["cases.contribute", "cases.read", "library.read", "register.read"],
    "isSystem": False,
    "active": True,
}
_EXAMPLE_API_KEY: dict[str, JsonValue] = {
    "id": "c4a81e5f-3b92-4d07-8e6a-2f1b9d5c7a30",
    "name": "Policy portal sync",
    "keyPrefix": "9a1f3c7e",
    "scopes": ["library:read", "search:read"],
    "createdAt": "2026-09-15T09:30:00Z",
    "expiresAt": "2027-09-15T23:59:59Z",
    "revokedAt": None,
    "lastUsedAt": "2026-09-22T05:00:12Z",
}
_EXAMPLE_API_KEY_CREATED: dict[str, JsonValue] = {
    key: value for key, value in _EXAMPLE_API_KEY.items() if key not in ("revokedAt", "lastUsedAt")
} | {"plainKey": "cw_9a1f3c7e_<secret-shown-once>"}
_EXAMPLE_SECURITY_EVENT: dict[str, JsonValue] = {
    "id": 48213,
    "occurredAt": "2026-09-22T06:58:04Z",
    "method": "passkey",
    "event": "signin",
    "success": True,
    "failureReason": "",
    "userId": "00000000-0000-4000-8000-000000000102",
    "email": "compliance_officer@example-bank.test",
    "ip": "192.0.2.41",
    "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
}
_EXAMPLE_FAILED_CODE_EVENT: dict[str, JsonValue] = {
    "id": 48207,
    "occurredAt": "2026-09-22T06:41:39Z",
    "method": "email_code",
    "event": "code_failed",
    "success": False,
    "failureReason": "wrong_code",
    "userId": "9f3b2c1d-4e5a-4b6c-8d7e-0a1b2c3d4e5f",
    "email": "anna@example-bank.test",
    "ip": "198.51.100.7",
    "userAgent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 Mobile/15E148 Safari/604.1",
}

# A list answer has no component schema of its own to carry an example, so api.py hangs these
# on the operations that return them.
ROLES_EXAMPLE: list[JsonValue] = [
    {
        "key": "reader",
        "kind": None,
        "label": "Reader",
        "labels": {"en": "Reader", "sv": "Läsare"},
        "usageNote": "Reads everything, changes nothing.",
        "permissions": [
            "audit.read",
            "cases.read",
            "comments.write",
            "library.read",
            "problems.report",
            "register.read",
            "reports.read",
            "roadmap.read",
            "search.use",
            "watch.read",
        ],
        "isSystem": True,
        "active": True,
    },
    _EXAMPLE_ROLE,
]
PERMISSIONS_EXAMPLE: list[JsonValue] = [
    {"key": "cases.signoff", "group": "cases", "description": "Sign off a case worked by someone else."},
    {"key": "members.manage", "group": "members", "description": "Invite, change and deactivate members; re-issue enrolment; revoke sessions."},
]
MEMBER_SESSIONS_EXAMPLE: list[JsonValue] = [_EXAMPLE_SESSION | {"current": False}]


class MemberOut(CamelSchema):
    """One person in this bank as the members screen lists them: who they are, what they
    may do here, and whether they can still sign in."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_MEMBER]})

    user_id: uuid.UUID = Field(
        description=(
            "The person's permanent account identifier, a UUID. Pass it to the member routes "
            "under `/tenant/members/{user_id}`. One account may belong to several banks; the "
            "identifier is the same in each, while everything else here is this bank's alone."
        )
    )
    email: str = Field(
        description=(
            "The person's work email address, lowercased, where their enrolment mail went. It is "
            "their identity across the platform and cannot be changed here."
        )
    )
    name: str = Field(
        description=(
            "The person's display name, as they set it on their own profile. Until they set one "
            "it is the part of the email address before the `@`."
        )
    )
    status: str = Field(
        description=(
            "Where the person stands in this bank, one of three values. "
            + _MEMBER_STATUS_TEXT
            + " Deactivated members stay in the list so the bank can see who was removed."
        )
    )
    roles: list[RoleRef] = Field(
        description=(
            "The roles the person holds in this bank, each as its stable key with a label in the "
            "reader's language; what they may do is the union of the permissions of these roles. "
            + _ROLE_KEYS_TEXT
        )
    )
    title: str = Field(
        description=(
            "The person's job title in this bank, such as `Head of Regulatory Compliance`, shown "
            "beside their name. Free text, empty when none was given, and never read by any rule."
        )
    )
    last_seen_at: datetime | None = Field(
        description=(
            "When the person last enrolled or signed in with a passkey, to any bank, as a UTC "
            "timestamp. Null for someone who has never enrolled. It moves at sign-in, not on "
            "every call, so it says whether the account is in use rather than what they did."
        )
    )
    passkey_count: int = Field(
        description=(
            "How many live passkeys the person holds. Zero means they cannot sign in until they "
            "enrol, which is the state after an invitation or a re-issued enrolment."
        )
    )
    active_sessions: int = Field(
        description=(
            "How many signed-in sessions the person has open in this bank right now; their "
            "sessions in any other bank are not counted and not visible here. See them with "
            "`GET /tenant/members/{user_id}/sessions`."
        )
    )


class MembersPage(CamelSchema):
    """`{items, total}` with `limit` and `offset` (playbook 10)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_EXAMPLE_MEMBER], "total": 1}]})

    items: list[MemberOut] = Field(
        description=(
            "The bank's members on this page, the earliest to join first, deactivated members "
            "included. People who were invited but have not enrolled yet are listed under "
            "`GET /tenant/invitations` instead."
        )
    )
    total: int = Field(description="How many members the bank has in total, not how many are on this page; use it to size a pager.")


class MemberInvite(CamelSchema):
    """`POST /tenant/members`: invite a person by work email with the roles they will hold."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"email": "anna@example-bank.test", "roleKeys": ["reader"], "title": "Compliance analyst"}]}
    )

    email: str = Field(
        max_length=254,
        description=(
            "The work email address to invite, at most 254 characters. Surrounding spaces are "
            "trimmed and it is lowercased; an address without an `@` is refused with "
            "`invalid_email`. The invitation link goes to this address and nowhere else."
        ),
    )
    role_keys: list[str] = Field(
        min_length=1,
        description=(
            "The roles the person will hold once they enrol, at least one key, each counted once. "
            + _ROLE_KEYS_TEXT
            + " A key the bank does not have, or a role it retired, is refused with `unknown_key`."
        ),
    )
    title: str = Field(
        default="",
        max_length=200,
        description=(
            "The person's job title in this bank, at most 200 characters, surrounding spaces "
            "trimmed. Leave it out or send an empty string (the default) for none."
        ),
    )


class MemberPatch(CamelSchema):
    """`PATCH /tenant/members/{user_id}`: send only what changes."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"roleKeys": ["compliance_officer", "approver"]}]})

    role_keys: list[str] | None = Field(
        default=None,
        description=(
            "The member's complete new set of roles, which replaces the old set rather than adding "
            "to it; leave it out, or send null (the default), to keep the roles as they are. "
            "Sending it needs a fresh passkey step-up. "
            + _ROLE_KEYS_TEXT
            + " An empty list is refused with `roles_required` and a key the bank does not have "
            "with `unknown_key`; a change that would leave the bank with nobody holding "
            "`members.manage` is refused with `last_admin`."
        ),
    )
    title: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "The member's new job title in this bank, at most 200 characters, surrounding spaces "
            "trimmed; an empty string clears it. Leave it out, or send null (the default), to keep "
            "it as it is. Changing only the title needs no step-up."
        ),
    )


class InvitationOut(CamelSchema):
    """One invitation or re-issued enrolment for this bank. The link's token is never here:
    it exists only in the mail the person received."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_INVITATION]})

    id: uuid.UUID = Field(
        description=(
            "The invitation's identifier, a UUID. Pass it to "
            "`POST /tenant/invitations/{invitation_id}/resend` or "
            "`DELETE /tenant/invitations/{invitation_id}`; it is not the token in the link and "
            "cannot open it."
        )
    )
    email: str = Field(description="The lowercased address the invitation was sent to, the only address its code will go to.")
    roles: list[RoleRef] = Field(
        description=(
            "The roles the person receives when they enrol with this invitation, each as its "
            "stable key with a label in the reader's language. " + _ROLE_KEYS_TEXT
        )
    )
    title: str = Field(
        description="The job title the person will carry in this bank once they enrol, empty when none was given."
    )
    kind: str = Field(
        description=(
            "Why the invitation exists, one of two values. `invite` is a first invitation to "
            "join the bank. `reenrolment` is an administrator's re-issued enrolment for an "
            "existing member whose passkeys were retired; enrolling with it keeps their "
            "membership and roles rather than creating new ones."
        )
    )
    status: str = Field(
        description=(
            "Where the invitation stands, computed by the server at the moment of the call, one "
            "of four values. " + _INVITATION_STATUS_TEXT
        )
    )
    created_at: datetime = Field(description="When the invitation was first sent, as a UTC timestamp set by the server.")
    expires_at: datetime = Field(
        description=(
            "When the link stops working, as a UTC timestamp: "
            f"{settings.INVITATION_TTL_HOURS} hours after it was sent or last resent (a setting). "
            "Resending moves it forward."
        )
    )


class InvitationsPage(CamelSchema):
    """`{items, total}` with `limit` and `offset` (playbook 10)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_EXAMPLE_INVITATION], "total": 1}]})

    items: list[InvitationOut] = Field(
        description=(
            "The bank's invitations on this page, newest first, in every status, re-issued "
            "enrolments included, so the list is the whole history. An empty list is a 200."
        )
    )
    total: int = Field(description="How many invitations the bank has sent in total, not how many are on this page.")


class RoleOut(CamelSchema):
    """One role of this bank: a named set of permissions a member can be given."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_ROLE]})

    key: str = Field(
        description=(
            "The role's stable key, lowercase, such as `compliance_officer`: a row of the bank's "
            "role vocabulary, which its administrators extend. The system roles seeded on day "
            "one are `admin`, `compliance_officer`, `owner`, `approver`, `contributor`, `reader` "
            "and `auditor`; any other key is one the bank added. It never changes once issued, so "
            "store and compare it and never the label. Nothing in the product decides anything "
            "by a role's key: what counts is its `permissions`."
        )
    )
    kind: str | None = Field(
        description="The kind of row within the role list. Roles have no kinds, so it is null for every role today."
    )
    label: str = Field(
        description=(
            "The role's name in the reader's language: the label in their own language if the "
            "role has one, then in the bank's default language, then in English, then the "
            "original, then the key itself. For display only."
        )
    )
    labels: dict[str, str] = Field(
        description=(
            "Every label the role has, keyed by content-language key such as `en` or `sv`, so a "
            "role editor can show and change each one. The bank may reword them freely."
        )
    )
    usage_note: str = Field(
        description=(
            "A sentence telling an administrator who the role is for, shown in the role picker, "
            "such as `Reads everything, changes nothing.` Empty when none was written."
        )
    )
    permissions: list[str] = Field(
        description=(
            "The permission keys the role grants, sorted, such as `cases.signoff`. The complete "
            "set, each with its meaning, is `GET /reference/permissions`; the set is fixed by the "
            "product and a bank cannot add to it. A person's permissions are the union of their "
            "roles' permissions."
        )
    )
    is_system: bool = Field(
        description=(
            "True for one of the seven roles the product seeds in every bank. A system role can "
            "be relabelled and its usage note rewritten, but its permissions follow the product "
            "and it cannot be retired. False for a role the bank added."
        )
    )
    active: bool = Field(
        description=(
            "True while the role can be given to members. A retired role is false; it is no longer "
            "listed or offered, and it cannot be brought back through the API."
        )
    )


class RoleCreate(CamelSchema):
    """`POST /tenant/roles`: a new role the bank composes from the product's permissions."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "key": "dora_reviewer",
                    "labels": {"en": "DORA reviewer", "sv": "DORA-granskare"},
                    "usageNote": "Reads the register and works the ICT-risk cases it is asked to help with.",
                    "permissions": ["cases.contribute", "cases.read", "library.read", "register.read"],
                }
            ]
        }
    )

    key: str = Field(
        max_length=80,
        description=(
            "The new role's stable key, at most 80 characters, such as `dora_reviewer`; "
            "surrounding spaces are trimmed and it is lowercased. Use lowercase letters, digits "
            "and underscores. It can never be changed afterwards. A blank key is refused with "
            "`key_required`, and a key the bank already has, retired roles included, with "
            "`duplicate_key`."
        ),
    )
    labels: dict[str, str] = Field(
        description=(
            "The role's name per content language, keyed by language key such as `en` or `sv`, at "
            "least one non-blank. Blank entries are dropped; a map with none left is refused with "
            "`label_required`, and a language the product does not offer with `unknown_key`."
        )
    )
    usage_note: str = Field(
        default="",
        max_length=1000,
        description=(
            "A sentence telling administrators who the role is for, at most 1000 characters, "
            "surrounding spaces trimmed; empty (the default) for none."
        ),
    )
    permissions: list[str] = Field(
        description=(
            "The permission keys the role grants, from `GET /reference/permissions`; duplicates "
            "count once and an empty list makes a role that grants nothing. A key that is not a "
            "bank permission is refused with `unknown_key`."
        )
    )


class RolePatch(CamelSchema):
    """`PATCH /tenant/roles/{key}`: send only what changes. The key never changes."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"labels": {"sv": "DORA-granskare"}}]})

    labels: dict[str, str] | None = Field(
        default=None,
        description=(
            "Labels to set, keyed by language key such as `sv`. Each language sent replaces that "
            "language's label and the others are kept; blank entries are ignored. Leave it out, or "
            "send null (the default), to keep every label. A map with only blank labels is "
            "refused with `label_required`, and a language the product does not offer with "
            "`unknown_key`."
        ),
    )
    usage_note: str | None = Field(
        default=None,
        max_length=1000,
        description=(
            "The new usage note, at most 1000 characters, surrounding spaces trimmed; an empty "
            "string clears it. Leave it out, or send null (the default), to keep it."
        ),
    )
    permissions: list[str] | None = Field(
        default=None,
        description=(
            "The role's complete new set of permission keys, which replaces the old set. Sending "
            "it needs a fresh passkey step-up, and a system role refuses it with `system_role`, "
            "because its permissions follow the product. A key that is not a bank permission is "
            "refused with `unknown_key`. Leave it out, or send null (the default), to keep them."
        ),
    )


class PermissionOut(CamelSchema):
    """One permission a bank's role can grant."""

    model_config = ConfigDict(json_schema_extra={"examples": [PERMISSIONS_EXAMPLE[0]]})

    key: str = Field(
        description=(
            "The permission's stable key, such as `cases.signoff`: what a role's `permissions` "
            "lists and what every route checks. The set is fixed by the product, not a vocabulary "
            "a bank extends; a new release may add keys."
        )
    )
    group: str = Field(
        description=(
            "The area the permission belongs to, the part of its key before the first dot, such "
            "as `cases`, so a role editor can group the list."
        )
    )
    description: str = Field(
        description="What holding the permission lets a person do, in one English sentence for the role editor to show."
    )


# What a bank's key may hold, in words, beside the set that enforces it
# (perms.TENANT_KEY_SCOPES). Shared by the three ApiKey* shapes so the list cannot drift.
_TENANT_KEY_SCOPES_TEXT = (
    "`library:read` reads the shared library's instruments, provisions and obligations; "
    "`search:read` searches it; `upcoming:read` reads the public regulatory dates coming up; "
    "`tenant:read` is set aside for reading the bank's own profile, and no route reads with it "
    "yet; and `proposals:write` files a proposal to the shared library, which changes nothing "
    "until someone independent approves it. No scope "
    "writes a library record. `agent-runs:write`, `sources:write`, `changes:write` and "
    "`proposals:review` belong to the platform's own agents and are refused on a bank's key."
)


class ApiKeyOut(CamelSchema):
    """One of the bank's own API keys as the keys screen lists it. The secret is never here,
    only its prefix."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_API_KEY]})

    id: uuid.UUID = Field(
        description=(
            "The key's permanent identifier, a UUID the server issues. Pass it to "
            "`DELETE /tenant/api-keys/{key_id}`; it is not the key itself and cannot sign a request."
        )
    )
    name: str = Field(
        description=(
            "The name an administrator gave the key, such as `Policy portal sync`, to tell keys "
            "apart on screen. A label only; nothing reads it."
        )
    )
    key_prefix: str = Field(
        description=(
            "The first part of the key, eight hexadecimal characters such as `9a1f3c7e`, kept in "
            "the clear so a key found in a log or a vault can be matched to this row. It is not a "
            "secret and is not enough to call the API: the rest was shown once, at creation, and "
            "only its hash is stored."
        )
    )
    scopes: list[str] = Field(
        description=(
            "What this key may do, as scope keys. A bank's key holds only these: "
            + _TENANT_KEY_SCOPES_TEXT
            + " A key created before that rule may still list a platform scope here; it works "
            "without it, and the security log records `key_scopes_withheld` when it is used."
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
            "When an administrator revoked the key, as a UTC timestamp in ISO 8601; from that "
            "moment every call with it answers `unauthenticated`. A revoked key stays listed and "
            "cannot be turned back on. Null while it is live."
        )
    )
    last_used_at: datetime | None = Field(
        description=(
            "When the key last authenticated a call, as a UTC timestamp in ISO 8601. It moves at "
            f"most once every {settings.API_KEY_LAST_USED_THROTTLE_SECONDS} seconds by default (a "
            "setting), so it says a key is in use rather than counting its calls. Null for a key "
            "that has never been used."
        )
    )


class ApiKeysPage(CamelSchema):
    """`{items, total}` with `limit` and `offset` (playbook 10)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_EXAMPLE_API_KEY], "total": 1}]})

    items: list[ApiKeyOut] = Field(
        description=(
            "The bank's own keys on this page, newest first, revoked and expired ones included so "
            "that the list is the whole history. The platform's agent keys are never here. An "
            "empty list is a 200 and means the bank has no key yet."
        )
    )
    total: int = Field(description="How many keys the bank has in total, not how many are on this page; use it to size a pager.")


class ApiKeyCreate(CamelSchema):
    """`POST /tenant/api-keys`: a new key for one of the bank's integrations."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"name": "Policy portal sync", "scopes": ["library:read", "search:read"], "expiresAt": "2027-09-15T23:59:59Z"}]
        }
    )

    name: str = Field(
        max_length=200,
        description=(
            "A name to tell the key apart on screen, at most 200 characters, such as `Policy "
            "portal sync`. Surrounding spaces are trimmed, and a name of spaces alone is refused "
            "with `name_required`."
        ),
    )
    scopes: list[str] = Field(
        min_length=1,
        description=(
            "What the new key may do, at least one scope key, each counted once. A bank's key "
            "may hold only these: "
            + _TENANT_KEY_SCOPES_TEXT
            + " Anything else is refused with `unknown_key`, and the message lists the valid scopes."
        ),
    )
    expires_at: datetime | None = Field(
        default=None,
        description=(
            "When the key should stop working on its own, as a UTC timestamp in ISO 8601 that "
            "must lie in the future, or `expiry_in_past` is answered. Leave it out or send null "
            "(the default) for a key that lives until it is revoked."
        ),
    )


class ApiKeyCreated(CamelSchema):
    """The secret appears here and nowhere else: no log, no audit value, no outbox payload."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_API_KEY_CREATED]})

    id: uuid.UUID = Field(description="The new key's permanent identifier, a UUID: the handle to revoke it by, never the key itself.")
    name: str = Field(description="The name the key was given, trimmed, exactly as it will be listed.")
    key_prefix: str = Field(
        description=(
            "The eight hexadecimal characters the key begins with after `cw_`, kept in the clear "
            "so the key can be recognised in the list later without the secret."
        )
    )
    scopes: list[str] = Field(description="What the new key may do, as scope keys, sorted. " + _TENANT_KEY_SCOPES_TEXT)
    created_at: datetime = Field(description="When the key was created, as a UTC timestamp in ISO 8601, set by the server.")
    expires_at: datetime | None = Field(
        description="When the key stops working on its own, as a UTC timestamp in ISO 8601, or null for a key with no expiry."
    )
    plain_key: str = Field(
        description=(
            "The key itself, `cw_<prefix>_<secret>`, to be sent as `X-API-Key` or as a bearer "
            "token. This answer is the only time it exists outside the caller: the server keeps "
            "only a hash of the secret, never logs it and never shows it again, so put it straight "
            "into the integration's secret store. A lost key is revoked and replaced, not recovered."
        )
    )


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
    "`tenant:read` is set aside for reading a bank's profile, no route reads with it yet, and a "
    "key that belongs to no bank has no profile to read. No scope writes a library record: a "
    "finding becomes a change or a proposal, never an edit."
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
            "refused with `unknown_key`, and a definition that is retired or switched off, rather "
            "than active or a draft being evaluated, with `agent_inactive`."
        )
    )
    scopes: list[str] = Field(
        min_length=1,
        max_length=len(perms.ALL_SCOPES),
        description=(
            f"What the key may do: at least one and at most {len(perms.ALL_SCOPES)} scope keys, "
            "each counted once. Give the key the least its agent needs. "
            + _AGENT_KEY_SCOPES_TEXT
            + " A review agent's key may not hold `sources:write`, `changes:write` or `proposals:write`, "
            "and no other agent's key may hold `proposals:review`; either is refused with "
            "`scope_not_for_kind`, naming the scope."
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
    """One entry of the bank's security log: a sign-in, a failure, an enrolment, a recovery
    or the use of a key. Entries are append-only and are never edited or removed."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_SECURITY_EVENT]})

    id: int = Field(
        description=(
            "The entry's number, issued by the server in increasing order across the platform. "
            "Numbers are not contiguous within one bank, since other banks' entries sit between."
        )
    )
    occurred_at: datetime = Field(description="When the event happened, as a UTC timestamp set by the server.")
    method: str = Field(
        description=(
            "Which credential the event concerned, one of three values. `email_code` is the "
            "one-time enrolment code sent by email, and an enrolment session ending; `passkey` is "
            "a passkey sign-in, step-up or enrolment, and a signed-in session ending; `api_key` "
            "is one of the bank's API keys or a person's calendar feed link."
        )
    )
    event: str = Field(
        description=(
            "What happened, one of these values. `code_sent`: an enrolment code was emailed. "
            "`code_refused_enrolled`: a code was asked for an address that already holds a "
            "passkey, and none was sent. `code_failed`: a code did not verify. `code_locked`: too "
            "many wrong codes, so the code stopped working. `enrolled`: a person registered their "
            "first passkey. `signin` and `signin_failed`: a passkey sign-in succeeded or failed. "
            "`step_up` and `step_up_failed`: a passkey confirmation of a protected action "
            "succeeded or failed. `refresh_replay`: a used refresh token was presented again, so "
            "the session was ended as possibly stolen. `session_revoked`: a session ended before "
            "its time. `reenrolment_issued`: an administrator re-issued a member's enrolment. "
            "`key_used`: an API key authenticated a call, logged at most once every "
            f"{settings.API_KEY_LAST_USED_THROTTLE_SECONDS} seconds per key by default (a setting). "
            "`key_revoked`: an API key was revoked. `key_created`: a platform agent key was "
            "created, which never appears in a bank's log. `key_scopes_withheld`: a key created "
            "before the platform-only scopes rule presented one and worked without it. "
            "`feed_used`: a calendar client fetched a person's subscribed feed. A new release may "
            "add events, so treat an unfamiliar value as new data and not an error."
        )
    )
    success: bool = Field(
        description=(
            "True when the event is something that worked, false for a failure or a refusal. "
            "`key_scopes_withheld` is false: the key worked, but without the scopes it listed."
        )
    )
    failure_reason: str = Field(
        description=(
            "A short snake_case reason, empty when there is none. On a failure it says why, such "
            "as `wrong_code`, `too_many_attempts`, `no_open_code`, `already_consumed`, "
            "`no_open_invitation`, `unknown_credential` or `passkey_enrolled`. On "
            "`session_revoked` it says why the session ended: `sign_out`, `idle`, "
            "`revoked_by_user`, `revoked_by_admin`, `member_deactivated`, `reenrolment`, "
            "`enrolment_completed` or `refresh_replay`. On `key_scopes_withheld` it lists the "
            "scopes that were withheld, comma-separated."
        )
    )
    user_id: uuid.UUID | None = Field(
        description=(
            "The account identifier of the person the event concerns, a UUID, or null when no "
            "known person was involved, such as an API key's use or a code typed for an unknown "
            "address."
        )
    )
    email: str = Field(
        description=(
            "The email address the event concerns: the person's address, or for a code event the "
            "address that was typed, which may belong to nobody. Empty for a key's events."
        )
    )
    ip: str | None = Field(
        description=(
            "The network address the request came from, IPv4 or IPv6 as text, or null when the "
            "event had no request of its own, such as a key's use or revocation."
        )
    )
    user_agent: str = Field(
        description=(
            "The browser's own description of itself (its User-Agent header), stored up to 500 "
            "characters and empty when there was none. It is the browser's claim and proves "
            "nothing about the device."
        )
    )


class SecurityLogPage(CamelSchema):
    """`{items, total}` with `limit` and `offset` (playbook 10)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_EXAMPLE_SECURITY_EVENT, _EXAMPLE_FAILED_CODE_EVENT], "total": 2}]})

    items: list[SecurityEventOut] = Field(
        description=(
            "The bank's security log entries on this page, newest first. Only this bank's entries "
            "appear; the platform's own entries and other banks' never do. An empty list is a 200."
        )
    )
    total: int = Field(description="How many entries the bank's security log holds in total, not how many are on this page.")
