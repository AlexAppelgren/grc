"""Malware scanner seam (CAS-05, playbook 16): the one place that decides whether a stored
file may be shown. `ScanState` is the kind a piece of evidence carries from the moment it
is stored; a scan answers `clean`, `infected` or `error`, never `pending`.

`mock` is deterministic and offline: the EICAR test string and a marker filename are
`infected`, another marker is `error`, everything else is `clean`. `clamd` streams the
bytes over INSTREAM (fetched from ClamAV's clamd(8) and clamd/scanner.c on 2026-09-25,
docs/plans/Verification_Log.md): the command `zINSTREAM\\0`, then chunks of a 4-byte
unsigned length in network byte order followed by that many bytes, then a zero-length
chunk; the reply, NUL-terminated for a `z` command, is `stream: OK`,
`stream: <signature> FOUND` (optionally `<signature>(<hash>:<size>) FOUND`), or an
`... ERROR` line, `INSTREAM size limit exceeded. ERROR` among them.

Bytes and replies are untrusted. A timeout, a refused or dropped connection, and any reply
that is not exactly one of the two good shapes is `error`: an unknown answer is never
`clean`. Nothing here logs, or puts into an exception, a filename, a path or a byte of the
file; a scan logs its provider, its state and the elapsed milliseconds.
"""

from __future__ import annotations

import enum
import logging
import re
import socket
import struct
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

# A file whose name holds one of these is answered as infected or as a failed scan by the
# mock, so seeds and tests can reach every branch without real malware.
MOCK_INFECTED_MARKER = "mock-infected"
MOCK_ERROR_MARKER = "mock-scan-error"
EICAR_MARKER = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"

# Bytes per INSTREAM chunk, and the most reply read back: both protocol framing, not policy.
CHUNK_BYTES = 64 * 1024
MAX_REPLY_BYTES = 1024
# ClamAV signature names: letters, digits and the punctuation its databases use.
_SIGNATURE = r"[A-Za-z0-9._:/+-]{1,200}"
_FOUND = re.compile(rf"stream: ({_SIGNATURE})(?:\([0-9a-f]{{1,128}}:[0-9]{{1,20}}\))? FOUND")


class ScanState(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): whether a stored file may be shown. The
    download branches on it, and an unknown answer is `error`, never `clean`."""

    PENDING = "pending"
    CLEAN = "clean"
    INFECTED = "infected"
    ERROR = "error"


@dataclass(frozen=True)
class ScanResult:
    """A scan's answer. `signature` names what was found and is set only when `infected`;
    `scanned_at` is UTC."""

    state: ScanState
    signature: str | None
    scanned_at: datetime


class ScannerAdapter(ABC):
    name: str

    def scan(self, content: bytes, *, filename: str) -> ScanResult:
        """Scan the bytes. `filename` is read by the mock's markers only and never logged."""
        started = time.monotonic()
        state, signature = self._verdict(content, filename)
        logger.info(
            "scan finished",
            extra={"provider": self.name, "state": str(state), "elapsed_ms": round((time.monotonic() - started) * 1000)},
        )
        return ScanResult(state=state, signature=signature, scanned_at=datetime.now(UTC))

    @abstractmethod
    def _verdict(self, content: bytes, filename: str) -> tuple[ScanState, str | None]: ...


class MockScanner(ScannerAdapter):
    name = "mock"
    EICAR_SIGNATURE = "Eicar-Test-Signature"
    MARKER_SIGNATURE = "Mock-Infected-Marker"

    def _verdict(self, content: bytes, filename: str) -> tuple[ScanState, str | None]:
        if EICAR_MARKER in content:
            return ScanState.INFECTED, self.EICAR_SIGNATURE
        if MOCK_INFECTED_MARKER in filename:
            return ScanState.INFECTED, self.MARKER_SIGNATURE
        if MOCK_ERROR_MARKER in filename:
            return ScanState.ERROR, None
        return ScanState.CLEAN, None


class ClamdScanner(ScannerAdapter):
    """INSTREAM over TCP to `SCANNER_HOST:SCANNER_PORT`; `SCANNER_TIMEOUT_SECONDS` bounds the
    connect and every send and read."""

    name = "clamd"

    def _verdict(self, content: bytes, filename: str) -> tuple[ScanState, str | None]:
        try:
            reply = self._exchange(content)
        except OSError:  # refused, reset, unreachable, or a timeout (socket.timeout is one)
            return ScanState.ERROR, None
        return parse_reply(reply)

    def _exchange(self, content: bytes) -> bytes:
        address = (settings.SCANNER_HOST, settings.SCANNER_PORT)
        with socket.create_connection(address, timeout=settings.SCANNER_TIMEOUT_SECONDS) as conn:
            conn.sendall(b"zINSTREAM\0")
            for start in range(0, len(content), CHUNK_BYTES):
                chunk = content[start : start + CHUNK_BYTES]
                conn.sendall(struct.pack("!I", len(chunk)) + chunk)
            conn.sendall(struct.pack("!I", 0))
            reply = b""
            while b"\0" not in reply and len(reply) <= MAX_REPLY_BYTES:
                part = conn.recv(MAX_REPLY_BYTES + 1 - len(reply))
                if not part:
                    break
                reply += part
            return reply


def parse_reply(reply: bytes) -> tuple[ScanState, str | None]:
    """The two good shapes, or `error`. A reply over the cap, not ASCII, or of any other
    shape is `error`."""
    if len(reply) > MAX_REPLY_BYTES:
        return ScanState.ERROR, None
    try:
        line = reply.split(b"\0", 1)[0].decode("ascii")
    except UnicodeDecodeError:
        return ScanState.ERROR, None
    if line == "stream: OK":
        return ScanState.CLEAN, None
    found = _FOUND.fullmatch(line)
    if found:
        return ScanState.INFECTED, found.group(1)
    return ScanState.ERROR, None


PROVIDERS: dict[str, type[ScannerAdapter]] = {"mock": MockScanner, "clamd": ClamdScanner}


def get_scanner() -> ScannerAdapter:
    """The configured scanner. The mock passes any real file, so it is refused on every
    deployed environment, the one named `test` included: a deployed environment without
    clamd stores no unscanned file. The boot refusal is `c14-eu-data-location`'s
    (docs/plans/briefs/HARDENING.md)."""
    provider = settings.SCANNER_PROVIDER
    if provider not in PROVIDERS:
        raise ValueError(f"SCANNER_PROVIDER={provider!r} is not one of {sorted(PROVIDERS)}")
    if provider == "mock" and settings.IS_DEPLOYED_ENVIRONMENT:
        raise ImproperlyConfigured(
            f"SCANNER_PROVIDER=mock on deployed environment {settings.ENVIRONMENT!r}: set it to clamd (CAS-05)."
        )
    return PROVIDERS[provider]()
