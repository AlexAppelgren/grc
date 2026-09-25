"""A software authenticator for the identity scenarios (playbook 8.1): builds the exact
`navigator.credentials` JSON a browser hands back, signed with a P-256 key it holds,
so `verify_registration_response` and `verify_authentication_response` run for real.
Attestation is `none`; user presence and user verification flags are set; the backup
flags mark a synced passkey. Not a test module itself (no TestCase), but named
`tests_*` so coverage and the production-module guards leave it out.

Registration: authData = rpIdHash | flags | signCount | aaguid | credIdLen | credId |
COSE key; attestationObject = CBOR {fmt: "none", attStmt: {}, authData}.
Authentication: authData = rpIdHash | flags | signCount; signature = ECDSA-SHA256 over
authData || sha256(clientDataJSON)."""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings

from apps.identity.tokens import b64url, b64url_decode

FLAG_UP = 0x01
FLAG_UV = 0x04
FLAG_BE = 0x08
FLAG_BS = 0x10
FLAG_AT = 0x40


class SoftwareAuthenticator:
    def __init__(
        self,
        *,
        rp_id: str | None = None,
        origin: str | None = None,
        aaguid: bytes = b"\x00" * 16,
        transports: tuple[str, ...] = ("internal", "hybrid"),
        attachment: str | None = "platform",
    ) -> None:
        self.rp_id = rp_id or settings.WEBAUTHN_RP_ID
        self.origin = origin or settings.WEBAUTHN_ORIGINS[0]
        self.aaguid = aaguid
        # What the browser reports beside the attestation; they name the passkey when the
        # AAGUID does not (apps/identity/passkey_names.py).
        self.transports = transports
        self.attachment = attachment
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = secrets.token_bytes(16)
        self.user_handle: bytes | None = None
        self.sign_count = 0
        # The backup flags it reports, a synced passkey by default; a test flips them to
        # play an authenticator whose eligibility or backup state changed.
        self.backup_eligible = True
        self.backed_up = True

    # --- pieces ---------------------------------------------------------------------------
    @property
    def credential_id_b64(self) -> str:
        return b64url(self.credential_id)

    def cose_public_key(self) -> bytes:
        numbers = self.key.public_key().public_numbers()
        return cbor2.dumps({1: 2, 3: -7, -1: 1, -2: numbers.x.to_bytes(32, "big"), -3: numbers.y.to_bytes(32, "big")})

    def _client_data(self, kind: str, challenge_b64: str) -> bytes:
        return json.dumps({"type": kind, "challenge": challenge_b64, "origin": self.origin, "crossOrigin": False}).encode()

    def _backup_flags(self) -> int:
        return (FLAG_BE if self.backup_eligible else 0) | (FLAG_BS if self.backed_up else 0)

    def _rp_hash(self) -> bytes:
        return hashlib.sha256(self.rp_id.encode()).digest()

    # --- ceremonies -----------------------------------------------------------------------
    def register(self, options: dict[str, Any]) -> dict[str, Any]:
        """Answer `navigator.credentials.create()` for the given creation options."""
        self.user_handle = b64url_decode(options["user"]["id"])
        flags = FLAG_UP | FLAG_UV | FLAG_AT | self._backup_flags()
        auth_data = (
            self._rp_hash()
            + bytes([flags])
            + self.sign_count.to_bytes(4, "big")
            + self.aaguid
            + len(self.credential_id).to_bytes(2, "big")
            + self.credential_id
            + self.cose_public_key()
        )
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        client_data = self._client_data("webauthn.create", options["challenge"])
        return {
            "id": self.credential_id_b64,
            "rawId": self.credential_id_b64,
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(client_data),
                "attestationObject": b64url(attestation),
                "transports": list(self.transports),
            },
            "authenticatorAttachment": self.attachment,
            "clientExtensionResults": {},
        }

    def assert_(self, options: dict[str, Any], *, wrong_key: bool = False) -> dict[str, Any]:
        """Answer `navigator.credentials.get()` for the given request options."""
        self.sign_count += 1
        flags = FLAG_UP | FLAG_UV | self._backup_flags()
        auth_data = self._rp_hash() + bytes([flags]) + self.sign_count.to_bytes(4, "big")
        client_data = self._client_data("webauthn.get", options["challenge"])
        signer = ec.generate_private_key(ec.SECP256R1()) if wrong_key else self.key
        signature = signer.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        return {
            "id": self.credential_id_b64,
            "rawId": self.credential_id_b64,
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(client_data),
                "authenticatorData": b64url(auth_data),
                "signature": b64url(signature),
                "userHandle": b64url(self.user_handle) if self.user_handle else None,
            },
            "authenticatorAttachment": "platform",
            "clientExtensionResults": {},
        }
