"""Tokens, codes and keys (playbook 4.2, chunk 1 brief): every secret is minted from
`secrets`, stored hashed (SHA-256 for random tokens, a per-row salted SHA-256 for the
six-digit code), and compared in constant time. The access token is the one exception to
"hashed in a table": it is an HMAC over its own claims (session id, kind, expiry) signed
with SECRET_KEY, so resolving it costs one signature check and one row read.

Nothing here logs a value (playbook 4.7)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

ACCESS_TOKEN_VERSION = "v1"  # noqa: S105 a format version, not a credential
API_KEY_PREFIX = "cw"
API_KEY_PREFIX_LENGTH = 8


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def hash_token(token: str) -> str:
    """SHA-256 of a random token (invitation tokens, refresh tokens, API key secrets)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def constant_equal(left: str, right: str) -> bool:
    return secrets.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


# ---------------------------------------------------------------------------------------
# The emailed code (ID-02)
# ---------------------------------------------------------------------------------------
def new_code() -> str:
    """Six random digits (a setting). Under E2E_MODE the one fixed code, refused on a
    deployed environment on this second leg (the first is the boot guard, rule 4)."""
    if settings.E2E_MODE:
        if settings.IS_DEPLOYED_ENVIRONMENT:
            raise ImproperlyConfigured("E2E_MODE fixed codes are refused on a deployed environment (playbook 8.3).")
        return settings.E2E_FIXED_CODE
    digits = settings.ENROLMENT_CODE_DIGITS
    return str(secrets.randbelow(10**digits)).zfill(digits)


def new_salt() -> str:
    return secrets.token_hex(16)


def hash_code(code: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{code}".encode()).hexdigest()


# ---------------------------------------------------------------------------------------
# Access tokens (D-06): `v1.<session id hex>.<kind>.<expiry epoch>.<hmac>`
# ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class AccessClaims:
    session_id: uuid.UUID
    kind: str
    expires_at: int


def _sign(payload: str) -> str:
    digest = hmac.new(settings.SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return b64url(digest)


def issue_access_token(session_id: uuid.UUID, kind: str, now: datetime) -> tuple[str, int]:
    ttl = timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES)
    expires_at = int((now + ttl).timestamp())
    payload = f"{ACCESS_TOKEN_VERSION}.{session_id.hex}.{kind}.{expires_at}"
    return f"{payload}.{_sign(payload)}", int(ttl.total_seconds())


def parse_access_token(token: str, now: datetime) -> AccessClaims | None:
    parts = token.split(".")
    if len(parts) != 5 or parts[0] != ACCESS_TOKEN_VERSION:
        return None
    version, sid, kind, expiry, signature = parts
    payload = f"{version}.{sid}.{kind}.{expiry}"
    if not constant_equal(_sign(payload), signature):
        return None
    try:
        expires_at = int(expiry)
        session_id = uuid.UUID(hex=sid)
    except ValueError:
        return None
    if expires_at <= int(now.timestamp()):
        return None
    return AccessClaims(session_id=session_id, kind=kind, expires_at=expires_at)


# ---------------------------------------------------------------------------------------
# Refresh tokens: `<session id hex>.<random>`; the row stores the hash of the random part.
# ---------------------------------------------------------------------------------------
def new_refresh_token(session_id: uuid.UUID) -> tuple[str, str]:
    secret = new_token(32)
    return f"{session_id.hex}.{secret}", hash_token(secret)


def parse_refresh_token(value: str) -> tuple[uuid.UUID, str] | None:
    sid, sep, secret = value.partition(".")
    if not sep or not secret:
        return None
    try:
        return uuid.UUID(hex=sid), hash_token(secret)
    except ValueError:
        return None


# ---------------------------------------------------------------------------------------
# API keys (ID-10): `cw_<prefix>_<secret>`; the row stores the prefix and the secret's hash.
# ---------------------------------------------------------------------------------------
def new_api_key() -> tuple[str, str, str]:
    """Returns (plain key, prefix, hash). The plain key is shown once and never stored."""
    prefix = secrets.token_hex(API_KEY_PREFIX_LENGTH // 2)
    secret = new_token(32)
    return f"{API_KEY_PREFIX}_{prefix}_{secret}", prefix, hash_token(secret)


def parse_api_key(plain: str) -> tuple[str, str] | None:
    parts = plain.strip().split("_", 2)
    if len(parts) != 3 or parts[0] != API_KEY_PREFIX or len(parts[1]) != API_KEY_PREFIX_LENGTH or not parts[2]:
        return None
    return parts[1], hash_token(parts[2])
