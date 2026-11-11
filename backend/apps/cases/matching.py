"""Keeping `change_case.footprint_match` true after the scope moves (CAS-01, FP-01 to FP-04).

The verdict is cached because the feed, roadmap and briefing all read it. It is re-decided
when the bank's footprint changes (every open case of that bank) and when a change's scope
terms or authority change (every bank's case for it, FP-04), both from the audit row's
event on the ordered outbox cursor.

- One statement per bank, never per case (`tests_matching.py` pins the query count).
- The one scope rule: `taxonomy_in_footprint`, the database half of
  `apps/taxonomy/matching.py`.
- A flip changes the cached boolean only (D-30): no urgency, triage or notice.
- A case that falls outside is neither hidden nor deleted; the feed's filter leaves it out.

One audit row per bank with the count moved. This module writes, so the subquery over a
change's scope terms lives in `reading.py` (library fence).
"""

from __future__ import annotations

import uuid

from django.db import transaction
from django.db.models import Q

from apps.cases import reading
from apps.cases.models import ChangeCase
from apps.shared import outbox, tenancy
from apps.shared.audit import Actor, record
from apps.shared.models import OutboxEvent, Tenant, TenantStatus
from apps.taxonomy.matching import in_footprint_expression
from apps.taxonomy.models import CaseStatusCategory

# What the two writers already record. One handler per kind, and no second relay.
FOOTPRINT_APPROVED = "footprint.change_approved"
CHANGE_FACTS_UPDATED = "regulatory_change.facts_updated"

RECOMPUTED = "case.footprint_match_recomputed"
# Re-decided as the consequence of someone else's decision: a system actor.
ACTOR = Actor.system("footprint-recompute")

# A finished case is the record of what the bank did; it is never re-decided.
OPEN_CATEGORIES = ~Q(status__in=(CaseStatusCategory.CLOSED.value, CaseStatusCategory.DISMISSED.value))


def register() -> None:
    """Put both handlers on the one cursor. Called from the app's `ready()`, and safe to
    call again: `register_handler` treats the same function twice as one registration."""
    outbox.register_handler(FOOTPRINT_APPROVED, after_footprint_change)
    outbox.register_handler(CHANGE_FACTS_UPDATED, after_change_scope_change)


def after_footprint_change(event: OutboxEvent) -> None:
    """A bank's footprint moved: re-decide that bank's open cases. The event is the bank's,
    so the cursor already put the handler in its zone.
    """
    if event.tenant_id is None:  # pragma: no cover - a footprint change is always a bank's
        return
    _recompute(event.tenant_id, change_id=None)


def after_change_scope_change(event: OutboxEvent) -> None:
    """A change's facts moved: re-decide every bank's case for that change. Runs in the
    library's zone; the banks are read in full before the first bank's zone is entered.
    """
    change_id = event.audit_event.subject_id
    if change_id is None:  # pragma: no cover - the writer always names the change
        return
    for tenant_id in _active_tenant_ids():
        _recompute_in_tenant(tenant_id, change_id=change_id)


def _active_tenant_ids() -> list[uuid.UUID]:
    return list(
        Tenant.objects.filter(status=TenantStatus.ACTIVE.value).order_by("slug").values_list("id", flat=True)
    )


@tenancy.tenant_task
def _recompute_in_tenant(tenant_id: uuid.UUID, *, change_id: uuid.UUID) -> None:
    """One bank's cases for one change, inside that bank's zone."""
    _recompute(tenant_id, change_id=change_id)


def _recompute(tenant_id: uuid.UUID, *, change_id: uuid.UUID | None) -> None:
    """Re-decide this bank's cases in one statement, and record how many moved. Only rows
    whose verdict changed are written, so a redelivered event costs no rows.
    """
    verdict = in_footprint_expression(tenant_id, reading.scope_term_ids_of_each_case())
    cases = ChangeCase.objects.filter(OPEN_CATEGORIES, tenant_id=tenant_id)
    if change_id is not None:
        cases = cases.filter(change_id=change_id)
    with transaction.atomic():
        moved = cases.exclude(footprint_match=verdict).update(footprint_match=verdict)
        if moved:
            record(
                action=RECOMPUTED,
                actor=ACTOR,
                subject_type="footprint",
                subject_id=tenant_id,
                subject_title="Regulatory scope",
                summary="The regulatory scope moved, so open cases were re-checked against it.",
                tenant_id=tenant_id,
                after={"casesMoved": moved, "changeId": None if change_id is None else str(change_id)},
            )
