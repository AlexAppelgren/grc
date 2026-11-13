"""Business logic of the register app: `ensure_register_entry()` and
`ensure_register_entries()`, the one creator of a register entry (AST guard in
tests_models.py), the shared loaders, and `drafted_reason()`, the one shape of an AI-drafted
reason. Each feature's rules live in a module of its own."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping

from django.core.exceptions import ValidationError

from apps.library.reading import RecordHeading, obligation_headings
from apps.register.models import TenantObligation
from apps.shared.audit import Actor, record
from apps.taxonomy.models import ComplianceStatus

ENTRY_CREATED = "register.entry_created"
# A citation marker a model may still write ("[3]"), dropped from a drafted reason (D-143).
_MARKER = re.compile(r"\s*\[\d{1,4}\]")


def reason_draft_template(applicability: str) -> str:
    """The prompt template a reason draft for `applicability` is logged under (D-143): the answer
    it explains is part of it, so the draft is confirmed only beside that answer."""
    return f"register/reason-draft/v1:{applicability}"


def drafted_reason(output: str, limit: int) -> str:
    """A model's draft of a reason as the dialog is given it: citation marks dropped, white
    space folded, at most `limit` characters. `applicability.confirm_draft` compares the reason
    a person sets against this, so a draft kept as it stood reads confirmed."""
    return " ".join(_MARKER.sub("", output).split())[:limit].strip()


def ensure_register_entry(*, tenant_id: uuid.UUID, obligation_id: uuid.UUID, actor: Actor) -> TenantObligation:
    """The bank's register entry on `obligation_id`, created on the first write that needs
    it with its `register.entry_created` audit event. A read never calls this.

    The obligation is read under row-level security first, because the foreign key is
    checked without it: another bank's private obligation is `not_found`."""
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
    """The bank's register entries on the obligations of `headings`, locked: the missing ones
    created in one INSERT that skips existing rows, then read back in one locking query. Only
    entries this call created get a `register.entry_created` event.

    `headings` is the caller's proof, read under row-level security (`obligation_headings()`),
    that the bank can see each obligation; the foreign key alone does not check it. A new
    entry carries the bank's default compliance `status`."""
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
