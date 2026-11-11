"""Names a new passkey from what its registration already tells us (PRD ID-04, ID-S10):
the person types no name and renames under My passkeys.

In order of preference:

1. The authenticator's name from its AAGUID, in the vendored list
   `data/passkey_aaguid_names.tsv` (source and licence in its header). Local only. An
   all-zero AAGUID names nothing.
2. For a platform authenticator only, browser and platform from the User-Agent: "Chrome on
   Windows". A roaming authenticator is not the laptop it registered from. The raw
   User-Agent is never a name.
3. The transport: "Security key" (usb, nfc, ble), "Phone" (hybrid), else "Passkey".

The name is unique among the person's live passkeys, case-insensitively: "Windows Hello
(2)". Sync state is not part of it, since backup state can change. Names are stored in
English; the backend holds no message catalog."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

AAGUID_NAMES_FILE = Path(__file__).resolve().parent / "data" / "passkey_aaguid_names.tsv"
NICKNAME_MAX_LENGTH = 100  # WebAuthnCredential.nickname max_length
ZERO_AAGUID = "00000000-0000-0000-0000-000000000000"
_AAGUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

# Which rule named the passkey, recorded on the audit event. Plain strings, not an enum:
# nothing branches on them and they never reach the API.
SOURCE_SUPPLIED = "supplied"
SOURCE_AUTHENTICATOR = "authenticator"
SOURCE_BROWSER = "browser"
SOURCE_TRANSPORT = "transport"

SECURITY_KEY = "Security key"
PHONE = "Phone"
PASSKEY = "Passkey"
_KEY_TRANSPORTS = frozenset({"usb", "nfc", "ble"})

# The same tables, in the same order, as describeDevice() in
# frontend/src/features/identity/identity-presentation.ts. Order matters: Edge and Samsung
# Internet carry "Chrome/", Chrome on iOS "Safari/", Android "Linux", an iPhone "Mac OS X".
_BROWSERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"Edg(e|A|iOS)?/"), "Edge"),
    (re.compile(r"OPR/|Opera"), "Opera"),
    (re.compile(r"SamsungBrowser/"), "Samsung Internet"),
    (re.compile(r"Firefox/|FxiOS/"), "Firefox"),
    (re.compile(r"CriOS/"), "Chrome"),
    (re.compile(r"Chrome/"), "Chrome"),
    (re.compile(r"Safari/"), "Safari"),
)
_SYSTEMS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"iPhone"), "iPhone"),
    (re.compile(r"iPad"), "iPad"),
    (re.compile(r"Android"), "Android"),
    (re.compile(r"Windows"), "Windows"),
    (re.compile(r"Mac OS X|Macintosh"), "macOS"),
    (re.compile(r"CrOS"), "ChromeOS"),
    (re.compile(r"Linux"), "Linux"),
)


@dataclass(frozen=True)
class DerivedName:
    nickname: str
    source: str


@lru_cache(maxsize=1)
def aaguid_names() -> dict[str, str]:
    """The vendored map, read once per process. A malformed line refuses to load rather
    than naming passkeys from half a file."""
    names: dict[str, str] = {}
    for number, line in enumerate(AAGUID_NAMES_FILE.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.startswith("#"):
            continue
        aaguid, tab, name = line.partition("\t")
        name = name.strip()
        if not tab or not _AAGUID.match(aaguid) or not name or len(name) > NICKNAME_MAX_LENGTH:
            raise ImproperlyConfigured(f"{AAGUID_NAMES_FILE.name} line {number} is not '<lowercase aaguid><TAB><name>'.")
        names[aaguid] = name
    return names


def authenticator_name(aaguid: str) -> str | None:
    key = (aaguid or "").strip().lower()
    if key in ("", ZERO_AAGUID):
        return None
    return aaguid_names().get(key)


def _first(table: tuple[tuple[re.Pattern[str], str], ...], user_agent: str) -> str | None:
    return next((name for pattern, name in table if pattern.search(user_agent)), None)


def describe_browser(user_agent: str) -> str | None:
    """"Chrome on Windows", or whichever half is recognised, or None."""
    browser, system = _first(_BROWSERS, user_agent), _first(_SYSTEMS, user_agent)
    if browser is not None and system is not None:
        return f"{browser} on {system}"
    return browser or system


def _is_roaming(transports: list[str], attachment: str | None) -> bool:
    if attachment is not None:
        return attachment == "cross-platform"
    return bool(transports) and "internal" not in transports


def transport_name(transports: list[str], attachment: str | None) -> str:
    present = set(transports)
    if present & _KEY_TRANSPORTS:
        return SECURITY_KEY
    if "hybrid" in present and _is_roaming(transports, attachment):
        return PHONE
    return PASSKEY


def unique_among(name: str, taken: Iterable[str]) -> str:
    """`name`, or `name (n)` with the smallest n from 2 not already held; case-insensitive,
    and always within the column."""
    used = {item.casefold() for item in taken}
    name = name[:NICKNAME_MAX_LENGTH]
    if name.casefold() not in used:
        return name
    counter = 2
    while True:
        suffix = f" ({counter})"
        candidate = name[: NICKNAME_MAX_LENGTH - len(suffix)].rstrip() + suffix
        if candidate.casefold() not in used:
            return candidate
        counter += 1


def derive_nickname(*, aaguid: str, user_agent: str, transports: list[str], attachment: str | None, taken: Iterable[str]) -> DerivedName:
    name = authenticator_name(aaguid)
    source = SOURCE_AUTHENTICATOR
    if name is None and not _is_roaming(transports, attachment):
        name = describe_browser(user_agent)
        source = SOURCE_BROWSER
    if name is None:
        name = transport_name(transports, attachment)
        source = SOURCE_TRANSPORT
    return DerivedName(nickname=unique_among(name, taken), source=source)
