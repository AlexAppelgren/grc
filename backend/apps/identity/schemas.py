"""Request and response schemas of the identity app (chunk 1 brief, API contract):
camelCase through CamelSchema. The WebAuthn shapes mirror what py_webauthn's
`options_to_json_dict` emits and what `navigator.credentials` returns, with the two
field names whose casing the alias generator cannot derive (`clientDataJSON`, `rpId`
is fine) pinned by explicit aliases.

Every field carries the description and the example the reader of openapi.json needs
(CONVENTIONS 1.8, gated by scripts/openapi_quality.py). Examples come from the
prototype's bank, Example Bank AB; a credential-shaped field carries none, so no example
can ever be mistaken for a live secret."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from apps.shared.schemas import CamelSchema

__all__ = ["CamelSchema"]


class Empty(CamelSchema):
    """`{}`: the neutral answer of the code request and the accepted re-issue."""


class RoleRef(CamelSchema):
    """A row of an admin-managed list as the API hands it out: the key to store and the
    label to show. Used for roles and for languages."""

    key: str = Field(
        description="What to store, compare and send back; it never changes, while labels are relabelled and translated. A key from the roles or languages list, which an admin manages.",
        examples=["compliance_officer"],
    )
    kind: str | None = Field(
        default=None,
        description="Groups rows that behave alike where the list has such groups, and is null where it has none. A key from the list's own groups, which an admin manages.",
        examples=[None],
    )
    label: str = Field(
        description="What to print on screen, already in the caller's language; two banks may name the same key differently, so never branch on it.",
        examples=["Compliance officer"],
    )


# ---------------------------------------------------------------------------------------
# /auth
# ---------------------------------------------------------------------------------------
class CodeRequestBody(CamelSchema):
    email: str = Field(
        max_length=254,
        description="Where to send the one-time enrolment code. The answer is the same whether or not anyone holds this address, so an outsider cannot learn who banks here.",
        examples=["anna@example-bank.test"],
    )


class CodeVerifyBody(CamelSchema):
    email: str = Field(
        max_length=254,
        description="The address the code was asked for, compared trimmed and lower-cased.",
        examples=["anna@example-bank.test"],
    )
    code: str = Field(
        max_length=12,
        description="What the email said. It buys one enrolment and stops working the moment the person's first passkey exists.",
    )


class InvitationOpenBody(CamelSchema):
    """Opening the emailed link. The token rides in the body, never a path, so no server
    that logs request lines ever holds it (security review F29)."""

    token: str = Field(
        max_length=128,
        description="What the emailed link carries. Single use, and it names the account, so no address has to travel with it.",
    )


class InvitationCodeVerifyBody(CamelSchema):
    """The invitation path: the link's token names the account, so no address travels.
    The token rides in the body, never the path, so no access log holds it (F6, F29)."""

    token: str = Field(
        max_length=128,
        description="The same single-use value the opened link carried, proving which invitation is being answered.",
    )
    code: str = Field(
        max_length=12,
        description="What the second email said, so a link alone, forwarded or intercepted, enrols nobody.",
    )


class SessionTokens(CamelSchema):
    access_token: str = Field(
        description="Send it as `Authorization: Bearer …` on every later call. Short-lived on purpose; the refresh cookie set beside it buys the next one.",
    )
    session_kind: str = Field(
        description="`enrolment` while the person has only the emailed code and may do nothing but add a passkey, `full` once a passkey has signed them in. The pair is fixed in code.",
        examples=["full"],
    )
    expires_in: int = Field(
        description="Seconds of life left in the bearer token. Refresh before it runs out or the next call answers 401 `unauthenticated`.",
        examples=[600],
    )


class RefreshResult(CamelSchema):
    access_token: str = Field(description="The replacement bearer token for the `Authorization` header of every later call.")
    expires_in: int = Field(description="Seconds of life left in the replacement, counted from this answer.", examples=[600])


class WebAuthnRpEntity(CamelSchema):
    """The relying party the browser shows the person while they create a passkey."""

    name: str = Field(description="What the browser and the operating system show for this site while somebody creates a passkey, so they can see who it is for.", examples=["bleqq"])
    id: str | None = Field(
        default=None,
        description="The domain the passkey is bound to. A passkey made here works on this domain and no other, which is what stops a lookalike site from using it.",
        examples=["app.bleqq.com"],
    )


class WebAuthnUserEntity(CamelSchema):
    """Who the browser is making the passkey for."""

    id: str = Field(description="The account handle, base64url, opaque to the browser. It is a random per-account value, never an address.")
    name: str = Field(description="What the operating system lists beside the passkey when the person is asked to pick one.", examples=["anna@example-bank.test"])
    display_name: str = Field(description="The person's own name, shown beside the account in the same prompt.", examples=["Anna Lindgren"])


class WebAuthnPubKeyCredParam(CamelSchema):
    """One signature algorithm the server will accept from the authenticator."""

    type: str = Field(description="Always `public-key`: WebAuthn defines no other credential family, and the browser rejects anything else.", examples=["public-key"])
    alg: int = Field(description="The COSE algorithm the new key may sign with: -7 is ECDSA on P-256, -257 is RSA. The server lists what it accepts, best first.", examples=[-7])


class WebAuthnCredentialDescriptor(CamelSchema):
    """One passkey named to the browser: to exclude on registration, to offer on sign-in."""

    id: str = Field(description="The credential handle, base64url, as the authenticator issued it.")
    type: str = Field(description="Always `public-key`, the only credential family WebAuthn defines.", examples=["public-key"])
    transports: list[str] | None = Field(
        default=None,
        description="How this passkey can be reached, so the browser offers the right prompt instead of every one: `internal` for the device itself, `hybrid` for a phone, `usb` or `nfc` for a security key.",
        examples=[["internal", "hybrid"]],
    )


class WebAuthnAuthenticatorSelection(CamelSchema):
    """What the server demands of the authenticator before it accepts the new passkey."""

    authenticator_attachment: str | None = Field(
        default=None,
        description="Whether the passkey must live on this device (`platform`) or may be a security key carried between them (`cross-platform`); absent leaves the person free to choose.",
        examples=["platform"],
    )
    resident_key: str | None = Field(
        default=None,
        description="Whether the passkey must be stored on the authenticator itself, which is what lets a person sign in without first typing who they are.",
        examples=["required"],
    )
    require_resident_key: bool | None = Field(default=None, description="The same demand in the wording older browsers understand; kept so they behave the same.", examples=[True])
    user_verification: str | None = Field(
        default=None,
        description="Whether the authenticator must prove the person is present and is themselves, by biometric or device PIN. A bank keeps this `required`: it is the second factor.",
        examples=["required"],
    )


class WebAuthnCreationOptions(CamelSchema):
    """`navigator.credentials.create({publicKey: ...})`, bytes as base64url."""

    rp: WebAuthnRpEntity = Field(description="Who the passkey is being made for, and the one domain it will ever work on.")
    user: WebAuthnUserEntity = Field(description="The account the new passkey signs in, as the operating system will list it.")
    challenge: str = Field(description="Random bytes, base64url, that the authenticator has to sign. It is good once and for a few minutes, so a captured answer cannot be replayed.")
    pub_key_cred_params: list[WebAuthnPubKeyCredParam] = Field(description="The signature algorithms the server accepts, best first.")
    timeout: int | None = Field(default=None, description="How long the browser should wait for the person, in milliseconds, before giving up on the prompt; it matches the life of the challenge.", examples=[120000])
    exclude_credentials: list[WebAuthnCredentialDescriptor] | None = Field(
        default=None,
        description="The passkeys this account already has. The authenticator refuses to make a second one for the same device, so nobody ends up with duplicates they cannot tell apart.",
    )
    authenticator_selection: WebAuthnAuthenticatorSelection | None = Field(default=None, description="What the new passkey must satisfy before the server will take it.")
    attestation: str | None = Field(
        default=None,
        description="How much the authenticator must say about itself. `none` is what a bank asks for here: the device model is not worth the privacy cost.",
        examples=["none"],
    )
    hints: list[str] | None = Field(
        default=None,
        description="What the browser should suggest first, so the prompt matches how this bank enrols people: `client-device`, `hybrid` or `security-key`.",
        examples=[["client-device"]],
    )


class WebAuthnRequestOptions(CamelSchema):
    """`navigator.credentials.get({publicKey: ...})`, bytes as base64url."""

    challenge: str = Field(description="Random bytes, base64url, for the authenticator to sign. Good once and for a few minutes, so a captured answer proves nothing later.")
    timeout: int | None = Field(default=None, description="How long the browser should wait for the person, in milliseconds, before giving up on the prompt; it matches the life of the challenge.", examples=[120000])
    rp_id: str | None = Field(
        default=None,
        description="The domain whose passkeys may answer. The browser will not hand a passkey to any other site, which is what makes a phishing page useless.",
        examples=["app.bleqq.com"],
    )
    allow_credentials: list[WebAuthnCredentialDescriptor] | None = Field(
        default=None,
        description="Which passkeys may answer. Empty on sign-in, so no list of a person's devices leaks before anyone has proved who they are; filled on a step-up, where the session already says who is asking.",
    )
    user_verification: str | None = Field(
        default=None,
        description="Whether the authenticator must check the person by biometric or device PIN before it signs. A bank keeps this `required`.",
        examples=["required"],
    )


class WebAuthnAttestationResponse(CamelSchema):
    """The authenticator's answer to `create()`, passed through untouched."""

    client_data_json: str = Field(
        alias="clientDataJSON",
        description="What the browser saw, base64url: the challenge, the origin and the operation. The server checks it against what it asked for, which is how a relayed prompt is caught.",
    )
    attestation_object: str = Field(alias="attestationObject", description="The new public key and the authenticator's own data, base64url, for the server to store and verify against.")
    transports: list[str] | None = Field(
        default=None,
        description="How this authenticator can be reached, so a later sign-in prompt offers the right option first.",
        examples=[["internal", "hybrid"]],
    )


class PasskeyRegistrationCredential(CamelSchema):
    """What the browser returns from `create()`, serialised with base64url fields."""

    id: str = Field(description="The credential handle the authenticator issued, base64url; it names this passkey in every later call.")
    raw_id: str = Field(alias="rawId", description="The same handle as raw bytes, base64url, exactly as the browser produced it.")
    type: str = Field(description="Always `public-key`, the only credential family WebAuthn defines.", examples=["public-key"])
    response: WebAuthnAttestationResponse = Field(description="The authenticator's signed answer, which the server verifies before it trusts the new key.")
    authenticator_attachment: str | None = Field(
        default=None,
        alias="authenticatorAttachment",
        description="Where the passkey ended up: `platform` on this device, `cross-platform` on a key carried between devices. It is what the suggested name is derived from.",
        examples=["platform"],
    )
    client_extension_results: dict[str, Any] | None = Field(
        default=None,
        alias="clientExtensionResults",
        description="Whatever WebAuthn extensions the browser ran, passed through as the specification defines them. Nothing here changes the decision.",
    )


class WebAuthnAssertionResponse(CamelSchema):
    """The authenticator's answer to `get()`, passed through untouched."""

    client_data_json: str = Field(
        alias="clientDataJSON",
        description="What the browser saw, base64url: the challenge, the origin and the operation, for the server to compare with what it asked for.",
    )
    authenticator_data: str = Field(
        alias="authenticatorData",
        description="What the authenticator did, base64url: whether it checked the person, and its signature counter, which a cloned device betrays.",
    )
    signature: str = Field(description="The authenticator's signature over the challenge, base64url. It is the whole proof: it verifies against the stored public key or the attempt is refused.")
    user_handle: str | None = Field(
        default=None,
        alias="userHandle",
        description="Which account the authenticator thinks it just signed for. The server compares it and refuses a passkey that belongs to somebody else (422 `user_handle_mismatch`).",
    )


class PasskeyAuthenticationCredential(CamelSchema):
    """What the browser returns from `get()`, serialised with base64url fields."""

    id: str = Field(description="The credential handle of the passkey that answered, base64url.")
    raw_id: str = Field(alias="rawId", description="The same handle as raw bytes, base64url, exactly as the browser produced it.")
    type: str = Field(description="Always `public-key`, the only credential family WebAuthn defines.", examples=["public-key"])
    response: WebAuthnAssertionResponse = Field(description="The signed answer the server verifies against the stored public key.")
    authenticator_attachment: str | None = Field(
        default=None,
        alias="authenticatorAttachment",
        description="Where the passkey that answered lives: `platform` on this device, `cross-platform` on a key carried between them.",
        examples=["platform"],
    )
    client_extension_results: dict[str, Any] | None = Field(
        default=None,
        alias="clientExtensionResults",
        description="Whatever WebAuthn extensions the browser ran, as the specification defines them. Nothing here changes the decision.",
    )


class PasskeyRegisterBody(CamelSchema):
    credential: PasskeyRegistrationCredential = Field(description="What `navigator.credentials.create()` returned, passed through untouched for the server to verify.")
    # Optional (ID-04): absent or blank, the server names the passkey from the device
    # (apps/identity/passkey_names.py). Renaming stays on PATCH /me/passkeys/{id}.
    nickname: str | None = Field(
        default=None,
        max_length=100,
        description="What this passkey should be called in the person's own list. Leave it out and the server names it after the device, so the list stays readable without anyone typing.",
        examples=["Work laptop"],
    )


class PasskeyAssertBody(CamelSchema):
    credential: PasskeyAuthenticationCredential = Field(description="What `navigator.credentials.get()` returned, passed through untouched for the server to verify.")


class PasskeyOut(CamelSchema):
    """One passkey as its owner and a bank's administrator see it: enough to recognise a
    device and retire the one that was lost, and nothing that could be used to sign in."""

    id: uuid.UUID = Field(description="Name this passkey in the rename and remove calls.")
    nickname: str = Field(description="What the person calls this device, or what the server named it from the device when they did not.", examples=["Work laptop"])
    device_type: str = Field(
        description="`single_device` for a passkey that lives on one authenticator, `multi_device` for one a provider syncs between the person's devices. The pair is fixed in code.",
        examples=["multi_device"],
    )
    backed_up: bool = Field(description="Whether the provider holds a copy, so losing the device does not lock the person out. A bank reads it when it judges how many passkeys someone needs.")
    transports: list[str] = Field(description="How this passkey is reached: `internal`, `hybrid`, `usb` or `nfc`, as the authenticator reported at registration.", examples=[["internal", "hybrid"]])
    created_at: datetime = Field(description="When the passkey was enrolled, UTC. A bank's security review reads it beside the security log.", examples=["2026-09-14T08:12:31Z"])
    last_used_at: datetime | None = Field(
        description="When it last signed anything, UTC; null until it is first used. It is how a bank spots the device nobody carries any more.",
        examples=["2026-09-20T06:41:02Z"],
    )


class PasskeyRegistered(CamelSchema):
    """The answer to enrolling a passkey: the new device, and the full session it earns
    when the emailed code is what got the person this far."""

    passkey: PasskeyOut = Field(description="The device as it now appears in the person's own list.")
    access_token: str | None = Field(
        description="The bearer token of the full session the enrolment earned, or null when the caller already had one and simply added another device.",
    )
    session_kind: str = Field(description="Always `full` here: from this passkey on, the emailed code is dead and the person signs in with the device. Fixed in code.", examples=["full"])
    expires_in: int | None = Field(description="Seconds of life in that bearer token, or null when no new session was issued.", examples=[600])


class PasskeyPatch(CamelSchema):
    nickname: str = Field(
        max_length=100,
        description="What this device should be called from now on, so a person can tell their laptop from their phone when they retire one.",
        examples=["Work laptop"],
    )


class StepUpResult(CamelSchema):
    """The proof of a fresh passkey check, which the sensitive calls demand (ID-06)."""

    assertion_id: uuid.UUID = Field(description="The proof itself, which the audit row of the action it unlocks carries, so an assurance pack can tie a decision to the moment somebody confirmed it with a passkey. The session now counts as stepped up, so the call that asked simply runs again.")
    expires_at: datetime = Field(
        description="When the proof stops counting, UTC. After it, the same call answers 403 `step_up_required` and the person is asked for their passkey again.",
        examples=["2026-09-20T09:05:00Z"],
    )


# ---------------------------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------------------------
class MeUser(CamelSchema):
    """The signed-in person."""

    id: uuid.UUID = Field(description="The account, as every audit row and assignment in the bank refers to it.")
    email: str = Field(description="Where this person's invitations and enrolment codes go; it is also how a bank recognises them in the member list.", examples=["sara@example-bank.test"])
    name: str = Field(description="What the bank's own screens show beside this person's decisions and comments.", examples=["Sara Lindqvist"])
    locale: str | None = Field(
        description="Which language the interface answers in, or null while the person has not chosen and the bank's default applies. A key from the languages list, which an admin manages.",
        examples=["sv"],
    )


class MeTenant(CamelSchema):
    """The bank this session is inside. Null on a platform session, which is inside none."""

    id: uuid.UUID = Field(description="The bank whose rows this session may touch; every tenant record answers 404 outside it.")
    name: str = Field(description="The bank as it names itself, shown in the shell so nobody works in the wrong one.", examples=["Example Bank AB"])
    slug: str = Field(description="The bank's short name in links and support conversations; lower-case letters, digits and hyphens.", examples=["example-bank"])
    timezone: str = Field(
        description="The zone the bank's own days are counted in, so a deadline falls where its compliance officers sit rather than where a server does.",
        examples=["Europe/Stockholm"],
    )


class Me(CamelSchema):
    """Everything the shell needs about the caller in one read: who they are, which bank
    they are inside, what they may do, and how far their enrolment has got."""

    user: MeUser = Field(description="Who is signed in: the account the audit trail will name for everything done in this session.")
    tenant: MeTenant | None = Field(description="The bank this session is inside, or null for the platform staff, who sit in none of them.")
    roles: list[RoleRef] = Field(description="The roles the bank has given this person, for showing; what they may actually do is the permission list below.")
    permissions: list[str] = Field(
        description="What this session may do, flattened from those roles. Screens and buttons branch on these keys, never on a role name, so a bank can rename or rebuild its roles freely.",
        examples=[["cases.work", "register.read", "search.use"]],
    )
    platform_roles: list[RoleRef] = Field(description="The bleqq roles this account holds, empty for everyone at a bank. They govern the console, never a bank's own records.")
    enrolment_pending: bool = Field(description="True while the person has come in on an emailed code and has no passkey yet: the only thing they may do is add one.")
    passkey_count: int = Field(description="How many live devices can sign this person in. At one, removing it is refused, so nobody locks themselves out.", examples=[2])
    step_up_valid_until: datetime | None = Field(
        description="How long a fresh passkey check still counts, UTC, or null when the next sensitive action will ask for one.",
        examples=["2026-09-20T09:05:00Z"],
    )


class MePatch(CamelSchema):
    name: str | None = Field(
        default=None,
        max_length=200,
        description="What the bank's screens should show beside this person's work; leave it out to keep what is there.",
        examples=["Sara Lindqvist"],
    )
    locale: str | None = Field(
        default=None,
        max_length=8,
        description="Which language to answer in from now on. A key from the languages list, which an admin manages; an unknown one answers 422 `unknown_key`.",
        examples=["sv"],
    )


class SessionOut(CamelSchema):
    """One live sign-in. A person reviews their own; an administrator reviews a member's
    when they suspect a device was lost."""

    id: uuid.UUID = Field(description="Name this sign-in when revoking it.")
    current: bool = Field(description="Whether this is the session making the call, so a person does not sign themselves out while clearing the others.")
    created_at: datetime = Field(description="When the person signed in, UTC.", examples=["2026-09-20T07:02:11Z"])
    last_seen_at: datetime = Field(description="When this sign-in last called the API, UTC. It is what makes a forgotten browser somewhere obvious.", examples=["2026-09-20T08:44:57Z"])
    ip: str | None = Field(description="Where the sign-in came from, or null where the deployment does not pass it through. Kept for the security review and nothing else.", examples=["81.229.14.7"])
    user_agent: str = Field(description="The browser and operating system as they identified themselves, so a person recognises their own device in the list.", examples=["Chrome 141 on macOS"])


# ---------------------------------------------------------------------------------------
# Tenant admin: members, invitations, roles, keys, security log
# ---------------------------------------------------------------------------------------
class MemberOut(CamelSchema):
    """One person at the bank as its administrator sees them, with the two counts an
    administrator acts on: how many devices can sign them in, and how many sessions are live."""

    user_id: uuid.UUID = Field(description="The account, as every audit row, case and assignment refers to it.")
    email: str = Field(description="Where this person's invitations and re-enrolments go, and how an administrator recognises them.", examples=["owner@example-bank.test"])
    name: str = Field(description="What the bank's screens show beside their decisions.", examples=["Johan Berg"])
    status: str = Field(
        description="`invited` while they have not enrolled, `active` once they have, `deactivated` when the bank has ended their access. The three are fixed in code.",
        examples=["active"],
    )
    roles: list[RoleRef] = Field(description="The roles this person holds at the bank, which is what their permissions are flattened from.")
    title: str = Field(description="What the person does at the bank, in the bank's own words; it sits beside their name so a reader knows who signed off.", examples=["Obligation owner, digital investing"])
    last_seen_at: datetime | None = Field(description="When they last called the API, UTC, or null if never. It is how a bank finds the accounts nobody uses.", examples=["2026-09-19T15:20:03Z"])
    passkey_count: int = Field(description="How many live devices can sign this person in; zero means they are still waiting to enrol.", examples=[1])
    active_sessions: int = Field(description="How many sign-ins are live right now, so an administrator can see what revoking them would end.", examples=[2])


class MembersPage(CamelSchema):
    items: list[MemberOut] = Field(description="The members on this page, in the order they joined the bank.")
    total: int = Field(description="How many members the bank has in all, so a screen can show how much is left to page through.", examples=[42])


class MemberInvite(CamelSchema):
    email: str = Field(
        max_length=254,
        description="Where the invitation goes. It must be the person's own address: an invitation is how someone joins the bank, and it is traceable to them alone.",
        examples=["anna@example-bank.test"],
    )
    role_keys: list[str] = Field(
        min_length=1,
        description="What the person will be able to do once they enrol; at least one is required. Keys from the bank's own roles list, which an admin manages.",
        examples=[["compliance_officer", "reader"]],
    )
    title: str = Field(
        default="",
        max_length=200,
        description="What they do at the bank, shown beside their name. Leave it empty if the bank does not track titles.",
        examples=["Compliance officer"],
    )


class MemberPatch(CamelSchema):
    role_keys: list[str] | None = Field(
        default=None,
        description="The roles the person should hold from now on, replacing the ones they have; changing them needs a fresh passkey check. Keys from the bank's own roles list, which an admin manages. Leave it out to change only the title.",
        examples=[["approver"]],
    )
    title: str | None = Field(
        default=None,
        max_length=200,
        description="What they do at the bank from now on; leave it out to keep what is there.",
        examples=["Approver, head of compliance"],
    )


class InvitationOut(CamelSchema):
    """One outstanding invitation or re-enrolment, so an administrator can see who has
    not come in yet and resend or withdraw it."""

    id: uuid.UUID = Field(description="Name this invitation when resending or revoking it.")
    email: str = Field(description="Where the invitation was sent, which is also the address the person will sign in with.", examples=["anna@example-bank.test"])
    roles: list[RoleRef] = Field(description="What the person will hold the moment they enrol.")
    title: str = Field(description="What they will do at the bank, as the invitation recorded it.", examples=["Compliance officer"])
    kind: str = Field(
        description="`invite` for somebody joining the bank, `reenrolment` for a member who lost every device and was verified again out of band. Both are fixed in code.",
        examples=["invite"],
    )
    status: str = Field(
        description="`pending` while it can still be used, `accepted` once the person enrolled, `revoked` when the bank withdrew it, `expired` when its window closed. The four are fixed in code.",
        examples=["pending"],
    )
    created_at: datetime = Field(description="When it was sent, UTC; resending moves it.", examples=["2026-09-18T09:00:00Z"])
    expires_at: datetime = Field(description="When it stops working, UTC. After this the link answers 410 `invitation_expired` and an administrator has to resend.", examples=["2026-09-25T09:00:00Z"])


class InvitationsPage(CamelSchema):
    items: list[InvitationOut] = Field(description="The invitations on this page, newest first.")
    total: int = Field(description="How many the bank has outstanding in all.", examples=[3])


class RoleOut(CamelSchema):
    """One role of the bank's own list: a named bundle of permissions, seeded with the
    product's seven and extended by the bank itself (ID-09)."""

    key: str = Field(
        description="What every member row and audit entry stores; it never changes, while the labels are translated and relabelled. A key from the bank's roles list, which an admin manages.",
        examples=["compliance_officer"],
    )
    kind: str | None = Field(
        default=None,
        description="Groups roles that behave alike where the bank uses such groups, null where it does not. A key from the list's own groups, which an admin manages.",
        examples=[None],
    )
    label: str = Field(description="The role's name in the caller's language, for screens and pickers.", examples=["Compliance officer"])
    labels: dict[str, str] = Field(
        description="The name in every language the bank has, keyed by language, so the role editor can show them all at once.",
        examples=[{"en": "Compliance officer", "sv": "Compliance officer"}],
    )
    usage_note: str = Field(
        description="When to give somebody this role, in the bank's own words, shown under it in the picker so two administrators choose alike.",
        examples=["Triages changes, assesses, proposes to the library, manages vocabularies."],
    )
    permissions: list[str] = Field(
        description="What holding this role lets a person do. A session's rights are these, flattened across the roles it holds.",
        examples=[["cases.triage", "proposals.create", "vocab.manage"]],
    )
    is_system: bool = Field(description="True for the seven roles the product ships. A bank relabels them but cannot change what they may do or retire them, so an upgrade never changes who can approve.")
    active: bool = Field(description="False once the bank has retired the role: it stays for the audit trail and for old rows, and nobody can be given it again.")


class RoleCreate(CamelSchema):
    key: str = Field(
        max_length=80,
        description="The stable name this role is stored under, chosen by the bank and never changed afterwards, since every member row and audit entry keeps it.",
        examples=["outsourcing_officer"],
    )
    labels: dict[str, str] = Field(
        description="What to call the role, in at least one of the bank's languages; the others fall back to it.",
        examples=[{"en": "Outsourcing officer", "sv": "Outsourcingansvarig"}],
    )
    usage_note: str = Field(
        default="",
        max_length=1000,
        description="When to give somebody this role, so a second administrator makes the same call a year from now.",
        examples=["Owns the obligations that come with outsourced operations."],
    )
    permissions: list[str] = Field(
        description="What the role may do; an unknown key answers 422 `unknown_key`, and nothing a bank cannot hold is accepted.",
        examples=[["register.read", "cases.contribute"]],
    )


class RolePatch(CamelSchema):
    labels: dict[str, str] | None = Field(
        default=None,
        description="What to call the role from now on; leave it out to keep the names it has.",
        examples=[{"en": "Outsourcing officer"}],
    )
    usage_note: str | None = Field(default=None, max_length=1000, description="When to give somebody the role, rewritten; leave it out to keep what is there.")
    permissions: list[str] | None = Field(
        default=None,
        description="What the role may do from now on, replacing what it may do today; changing this needs a fresh passkey check, and a system role refuses it (422 `system_role`).",
        examples=[["register.read", "cases.work"]],
    )


class PermissionOut(CamelSchema):
    """One thing a role can be given. The role editor lists these; nothing else in the
    product decides anything from a role's name."""

    key: str = Field(
        description="What a role stores and what a screen branches on. The set is fixed in code, one per capability the product has.",
        examples=["cases.signoff"],
    )
    group: str = Field(description="The area this belongs to, taken from the part before the dot, so the editor can show permissions in sections.", examples=["cases"])
    description: str = Field(description="What holding it lets a person do, in the words the role editor shows.", examples=["Sign off a case worked by someone else."])


class ApiKeyOut(CamelSchema):
    """One key a bank's integration or agent authenticates with. The secret itself is
    shown once, at creation, and never again."""

    id: uuid.UUID = Field(description="Name this key when revoking it.")
    name: str = Field(description="What the key is for, in the bank's own words, so a year later somebody knows what revoking it would break.", examples=["Nightly watch agent"])
    key_prefix: str = Field(description="The middle part of the key, which reads `cw_<prefix>_<secret>`: enough to match a key in a log or a configuration file against this row, and useless on its own.", examples=["9f2c1a7b"])
    scopes: list[str] = Field(
        description="What the key may reach; each is narrow by design, and none of them reaches the shared library or a person's own records.",
        examples=[["changes:write", "library:read"]],
    )
    created_at: datetime = Field(description="When the bank issued this key, UTC; the security log carries the same moment.", examples=["2026-09-01T10:15:00Z"])
    expires_at: datetime | None = Field(description="When it stops working, UTC, or null where the bank set no expiry.", examples=["2027-09-01T10:15:00Z"])
    revoked_at: datetime | None = Field(description="When the bank withdrew it, UTC, or null while it is live. A revoked row stays for the audit trail.", examples=[None])
    last_used_at: datetime | None = Field(description="When it last authenticated a call, UTC, or null if never. It is how a bank finds the integration nobody runs any more.", examples=["2026-09-20T02:00:11Z"])


class ApiKeysPage(CamelSchema):
    items: list[ApiKeyOut] = Field(description="The keys on this page, newest first.")
    total: int = Field(description="How many keys the bank has in all, revoked ones included.", examples=[4])


class ApiKeyCreate(CamelSchema):
    name: str = Field(
        max_length=200,
        description="What this key is for, so a later administrator can tell what revoking it would break.",
        examples=["Nightly watch agent"],
    )
    scopes: list[str] = Field(
        min_length=1,
        description="What the key may reach; at least one, and an unknown one answers 422 `unknown_key`. The set is fixed in code, and none of them reaches the shared library.",
        examples=[["changes:write", "library:read"]],
    )
    expires_at: datetime | None = Field(
        default=None,
        description="When it should stop working, UTC; a moment already past answers 422 `expiry_in_past`. Leave it out for a key the bank will revoke by hand.",
        examples=["2027-09-01T10:15:00Z"],
    )


class ApiKeyCreated(CamelSchema):
    """The one answer that carries the secret. It is shown once, so a bank stores it in
    its own vault there and then; nothing can hand it out again."""

    id: uuid.UUID = Field(description="Name this key when revoking it.")
    name: str = Field(description="What the bank said the key is for.", examples=["Nightly watch agent"])
    key_prefix: str = Field(description="The middle part of the key, for matching one in a log or a configuration file against this row later.", examples=["9f2c1a7b"])
    scopes: list[str] = Field(description="What the key may reach, as it was created with.", examples=[["changes:write", "library:read"]])
    created_at: datetime = Field(description="When the bank issued this key, UTC; the security log carries the same moment.", examples=["2026-09-01T10:15:00Z"])
    expires_at: datetime | None = Field(description="When it stops working, UTC, or null where the bank set no expiry.", examples=["2027-09-01T10:15:00Z"])
    plain_key: str = Field(description="The secret itself, in the only answer that will ever carry it. Put it straight into the bank's vault; nothing can show it again.")


class SecurityEventOut(CamelSchema):
    """One line of the bank's own sign-in and key record (ID-11). It is what a bank's
    security review and a vendor assessment read, so it holds attempts as well as successes."""

    id: int = Field(description="Where this line sits in the ledger; the numbers only ever climb, so a gap means a row was never written, not removed.", examples=[10482])
    occurred_at: datetime = Field(description="When the attempt was made, UTC, as the bank's own security review reads it.", examples=["2026-09-20T07:02:11Z"])
    method: str = Field(
        description="How the person or system authenticated: `email_code` for the one-time enrolment code, `passkey` for a device, `api_key` for an integration. The three are fixed in code.",
        examples=["passkey"],
    )
    event: str = Field(
        description="What happened, from `code_sent` and `signin` to `signin_failed`, `code_locked`, `session_revoked` and `key_revoked`. The set is fixed in code, one per thing worth reviewing.",
        examples=["signin"],
    )
    success: bool = Field(description="Whether the attempt worked, so a reviewer can count failures against one address or one key.")
    failure_reason: str = Field(description="Why it did not, in a few fixed words, and empty when it did. It never says whether an address is known here.", examples=["wrong_code"])
    user_id: uuid.UUID | None = Field(description="Which account it concerned, or null when the attempt matched nobody at the bank.")
    email: str = Field(description="The address the attempt was made with, as typed. It is what makes a run of failures against one person visible.", examples=["anna@example-bank.test"])
    ip: str | None = Field(description="Where it came from, or null where the deployment does not pass it through.", examples=["81.229.14.7"])
    user_agent: str = Field(description="The browser or client as it identified itself, empty where there was none.", examples=["Chrome 141 on macOS"])


class SecurityLogPage(CamelSchema):
    items: list[SecurityEventOut] = Field(description="The lines on this page, newest first.")
    total: int = Field(description="How many lines the bank's record holds in all.", examples=[10482])
