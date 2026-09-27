"""Business logic of the register app. Raises ValidationError with user-facing text; every
write goes through record(); every threshold comes from settings (playbook 3).

This module holds only `ensure_register_entry()`, the one creator of a register entry
(proved by the AST guard in tests_models.py), and the loaders the register's logic modules
share; each feature's rules live in a module of its own (CHUNK8_TASKS.md plan rule 3)."""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.library.reading import obligation_headings
from apps.register.models import TenantObligation
from apps.shared.audit import Actor, record
from apps.taxonomy.models import ComplianceStatus

ENTRY_CREATED = "register.entry_created"


def ensure_register_entry(*, tenant_id: uuid.UUID, obligation_id: uuid.UUID, actor: Actor) -> TenantObligation:
    """The bank's register entry on `obligation_id`, created on the first write that
    needs it, with its `register.entry_created` audit event in the same transaction. A read
    never calls this: an obligation nobody has worked on has no entry.

    `tenant_id` is the activated bank's, which the tables' policies check on insert. The
    obligation is read under row-level security first, because the foreign key is checked
    without it: another bank's private obligation is `not_found`, exactly as an id that
    never existed. A new entry is not assessed and carries the bank's
    default compliance status. Two first writes at once meet on the unique key, and the
    second reads the entry the first created."""
    existing = TenantObligation.objects.filter(obligation_id=obligation_id).first()  # ordering: unique per bank, at most one row
    if existing is not None:
        return existing
    heading = obligation_headings([obligation_id], []).get(obligation_id)
    if heading is None:
        raise ValidationError("That obligation is not here.", code="not_found")
    try:
        with transaction.atomic():
            entry = TenantObligation.objects.create(
                tenant_id=tenant_id,
                obligation_id=obligation_id,
                compliance_status=ComplianceStatus.objects.get(is_default=True, active=True),
            )
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
    except IntegrityError:
        return TenantObligation.objects.get(obligation_id=obligation_id)
    return entry
