"""Malware scanner seam (CAS-05, playbook 16).

For now this module holds only `ScanState`, the kind a piece of evidence carries from the
moment it is stored, so the evidence table can default to `pending` and a file stays
invisible until a scan says `clean`. `c9-scanner-adapter` adds the adapters beside it
(`MockScanner`, `ClamdScanner`, `get_scanner()`), which never answer `pending`.
"""

from __future__ import annotations

import enum


class ScanState(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): whether a stored file may be shown. The
    download branches on it, and an unknown answer is `error`, never `clean`."""

    PENDING = "pending"
    CLEAN = "clean"
    INFECTED = "infected"
    ERROR = "error"
