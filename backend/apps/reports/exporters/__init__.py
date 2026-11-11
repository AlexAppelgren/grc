"""The exporter registry (REP-02, CAS-07): per export kind, the formats it offers and the
builder that turns a job into the file's bytes.

`POST /exports` refuses an unregistered kind with 501 `not_built` and a format the kind does
not offer with 422, before a row is written. Each builder lives in the app whose records it
exports and is registered at the bottom of this file. A builder runs in the worker under the
job's tenant and raises `ValidationError` with user-facing text when it cannot build. A kind
about one record also registers a `check`, run on create and on every download: 404 for
another bank's record, 403 for a person who may not read that kind, before anything is
written or streamed.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from apps.reports.models import EXPORT_FORMATS, ExportJob, ExportKind
from apps.shared.models import Tenant

Builder = Callable[[ExportJob], bytes]


class SubjectCheck(Protocol):
    def __call__(self, *, tenant: Tenant, permissions: frozenset[str], subject_id: uuid.UUID | None) -> None: ...


CONTENT_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "txt": "text/plain; charset=utf-8",
    "json": "application/json",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv; charset=utf-8",
}

# The task that registers each kind, named in the 501 a kind answers until it does.
PLANNED_BY: dict[ExportKind, str] = {
    ExportKind.CASE_FILE: "c9-case-file-export",
    ExportKind.CASES: "c12-export-changes-cases",
    ExportKind.COMMITTEE_PACK: "c12-committee-pack",
    ExportKind.INVENTORY: "c12-export-inventory",
    ExportKind.CHANGES: "c12-export-changes-cases",
    ExportKind.AUDIT_LOG: "c12-export-audit-log",
    ExportKind.CONFIGURATION: "c12-config-jobs",
    ExportKind.TENANT_EXPORT: "c12-exit-export",
}


@dataclass(frozen=True)
class Exporter:
    formats: frozenset[str]
    build: Builder
    check: SubjectCheck | None = None


_REGISTRY: dict[ExportKind, Exporter] = {}


def register(kind: ExportKind, *, formats: frozenset[str], build: Builder, check: SubjectCheck | None = None) -> None:
    """Register the builder of one kind, once. A second registration of the same kind, or
    a format outside the designed set, is a programming error and fails at import."""
    if kind in _REGISTRY:
        raise ValueError(f"export kind {kind} is already registered")
    unknown = formats - set(EXPORT_FORMATS)
    if not formats or unknown:
        raise ValueError(f"export kind {kind} offers formats outside {EXPORT_FORMATS}: {sorted(unknown)}")
    _REGISTRY[kind] = Exporter(formats=formats, build=build, check=check)


def lookup(kind: ExportKind) -> Exporter | None:
    return _REGISTRY.get(kind)


# --- Registrations (one line per builder) ---
from apps.reports.exporters import case_file as _case_file  # noqa: E402 - registered after the registry exists

register(ExportKind.CASE_FILE, formats=frozenset({"txt"}), build=_case_file.build, check=_case_file.check)
