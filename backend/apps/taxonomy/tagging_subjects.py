"""The records a tenant tag may sit on (VOC-08), read only: which kinds take a tag, and
which of the records a caller names they may read. Kept apart from the tagging writes in
tagging_logic.py so the module that writes rows never names a library model (the library
fence, apps/shared/tests_library_fence.py).

A record is readable when row-level security shows it to the caller's tenant (a shared
library record or the bank's own, a case or a register entry of its own) and the caller's
roles read its kind.
"""

from __future__ import annotations

import uuid
from typing import Any, Final

from django.core.exceptions import ValidationError
from django.db.models import Model

from apps.cases.models import ChangeCase
from apps.library.models import Obligation
from apps.register.models import TenantObligation
from apps.shared import permissions as perms
from apps.shared.authentication import Principal
from apps.watch.models import RegulatoryChange

# kind -> the model holding it and the permission that reads it.
SUBJECTS: Final[dict[str, tuple[type[Model], str]]] = {
    "obligation": (Obligation, perms.LIBRARY_READ),
    "change": (RegulatoryChange, perms.WATCH_READ),
    "change_case": (ChangeCase, perms.CASES_READ),
    "tenant_obligation": (TenantObligation, perms.REGISTER_READ),
}
NOT_FOUND = "There is nothing at this address in your organisation."


def kind_of(subject_type: str) -> tuple[type[Model], str]:
    found = SUBJECTS.get(subject_type)
    if found is None:
        raise ValidationError(
            f"{subject_type!r} records cannot be tagged; tag an obligation, a change, a case or a register entry.",
            code="unsupported_subject",
        )
    return found


def title_of(who: Principal, subject_type: str, subject_id: uuid.UUID) -> str:
    """The title the audit row names the record by, or the 404 an unknown id answers: a
    record the caller may not read is not there."""
    model, permission = kind_of(subject_type)
    row: Any = None
    if who.has_permission(permission):
        query = model._default_manager.filter(pk=subject_id)
        joins: dict[type[Model], str] = {ChangeCase: "change", TenantObligation: "obligation"}
        related = joins.get(model)
        row = (query.select_related(related) if related else query).first()  # ordering: pk lookup, at most one row
    if row is None:
        raise ValidationError(NOT_FOUND, code="not_found")
    if isinstance(row, Obligation):
        return row.stable_key
    if isinstance(row, TenantObligation):
        return row.obligation.stable_key
    if isinstance(row, ChangeCase):
        return row.change.title
    return str(row.title)


def readable(who: Principal, subject_type: str, subject_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """The ids among `subject_ids` the caller may read, in one query."""
    model, permission = kind_of(subject_type)
    if not who.has_permission(permission):
        return set()
    return set(model._default_manager.filter(pk__in=subject_ids).values_list("pk", flat=True))
