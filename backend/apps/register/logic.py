"""Business logic of the register app. Raises ValidationError with user-facing text; every
write goes through record(); every threshold comes from settings (playbook 3).

This module holds only `ensure_register_entry()` and `ensure_register_entries()`, which it
calls and which is the one creator of a register entry (proved by the AST guard in
tests_models.py), and the loaders the register's logic modules
share; each feature's rules live in a module of its own (CHUNK8_TASKS.md plan rule 3)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping

from django.core.exceptions import ValidationError

from apps.library.reading import RecordHeading, obligation_headings
from apps.register.models import TenantObligation
from apps.shared.audit import Actor, record
from apps.taxonomy.models import ComplianceStatus

ENTRY_CREATED = "register.entry_created"


def ensure_register_entry(*, tenant_id: uuid.UUID, obligation_id: uuid.UUID, actor: Actor) -> TenantObligation:
    """The bank's register entry on `obligation_id`, created on the first write that
    needs it, with its `register.entry_created` audit event in the same transaction. A read
    never calls this: an obligation nobody has worked on has no entry.

    The obligation is read under row-level security first, because the foreign key is checked
    without it: another bank's private obligation is `not_found`, exactly as an id that
    never existed. Then `ensure_register_entries()` creates it."""
    existing = TenantObligation.objects.filter(obligation_id=obligation_id).first()  # ordering: unique per bank, at most one row
    if existing is not None:
        return existing
    heading = obligation_headings([obligation_id], []).get(obligation_id)
    if heading is None:
        raise ValidationError("That obligation is not here.", code="not_found")
    status = ComplianceStatus.objects.get(is_default=True, active=True)
    return ensure_register_entries(tenant_id=tenant_id, headings={obligation_id: heading}, actor=actor, status=status)[obligation_id]


def ensure_register_entries(
    *,
    tenant_id: uuid.UUID,
    headings: Mapping[uuid.UUID, RecordHeading],
    actor: Actor,
    status: ComplianceStatus,
) -> dict[uuid.UUID, TenantObligation]:
    """The bank's register entries on the obligations of `headings`, locked, the missing ones
    created in one INSERT that skips an entry that already exists, then read back in one
    locking query. Each entry this call created gets its `register.entry_created` event; one
    another write created first gets none from here.

    `headings` is the caller's proof that the bank can see each obligation: it was read under
    row-level security (`obligation_headings()`), which the foreign key alone does not check.
    `tenant_id` is the activated bank's, which the tables' policies check on insert. A new
    entry is not assessed and carries the bank's default compliance `status`, which the caller
    reads once for everything its write creates."""
    new = {
        obligation_id: TenantObligation(tenant_id=tenant_id, obligation_id=obligation_id, compliance_status=status)
        for obligation_id in sorted(headings)
    }
    TenantObligation.objects.bulk_create(new.values(), ignore_conflicts=True)
    entries = {row.obligation_id: row for row in TenantObligation.objects.select_for_update().filter(obligation_id__in=new)}
    for obligation_id, entry in entries.items():
        if entry.id != new[obligation_id].id:
            continue
        heading = headings[obligation_id]
        record(
            action=ENTRY_CREATED,
            actor=actor,
            subject_type="tenant_obligation",
            subject_id=entry.id,
            subject_title=f"{heading.instrument_short_name}, {heading.reference_label}",
            summary="Register entry created.",
            tenant_id=tenant_id,
            after={"obligationId": str(obligation_id), "applicability": entry.applicability},
        )
    return entries
