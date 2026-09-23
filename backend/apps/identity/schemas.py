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
ENROLMENT_SESSION_EXAMPLE: dict[str, JsonValue] = {"accessToken": _EXAMPLE_ENROLMENT_TOKEN, "sessionKind": "enrolment", "expiresIn": 600}

# What every bytes value in the WebAuthn shapes is, said once.
_BASE64URL = "base64url-encoded without padding, the encoding WebAuthn's own JSON form uses"


class CodeRequestBody(CamelSchema):
    """Asking for a one-time sign-in code by email, the "First time here?" path."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"email": "anna@example-bank.test"}]})

    email: str = Field(
        max_length=254,
        description=(
            "The address the invitation was sent to, at most 254 characters. Case and "
            "surrounding spaces are ignored. Any text is accepted and answered alike: a code "
            "goes out only when the address has an open invitation and no passkey yet, and "
            "the answer never says whether it did, so it cannot be used to learn who holds "
            "an account."
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
    that logs request lines ever holds it (security review F29)."""

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
    The token rides in the body, never the path, so no access log holds it (F6, F29)."""

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
        json_schema_extra={"examples": [{"accessToken": _EXAMPLE_ACCESS_TOKEN, "sessionKind": "full", "expiresIn": 600}]}
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

    model_config = ConfigDict(json_schema_extra={"examples": [{"accessToken": _EXAMPLE_ACCESS_TOKEN, "expiresIn": 600}]})

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
                    "timeout": 120000,
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
                    "timeout": 120000,
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
            "examples": [{"passkey": _EXAMPLE_PASSKEY, "accessToken": _EXAMPLE_ACCESS_TOKEN, "sessionKind": "full", "expiresIn": 600}]
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
                        "applicability.request",
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
