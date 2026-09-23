"""Keeping `change_case.footprint_match` true after the scope moves (CAS-01, FP-01 to FP-04).

The verdict is cached on the case because the feed, the roadmap and the briefing all read
it and none of them can afford to re-decide a bank's whole backlog per request. A cache is
only as good as what refreshes it, and two things move underneath it:

- **The bank's own footprint.** A second person approves a footprint change and the bank
  now watches custody, or has stopped advising. Every open case of that bank is re-decided.
- **A change's scope terms or its authority.** A run corrects the terms on a change, or a
  library editor does, or the change turns out to be another authority's, which moves the
  jurisdictions it reaches (FP-04). Every bank's case for that change is re-decided from
  the correction's event, and two banks with different footprints land on different
  answers from the same edit.

Both run on the one ordered cursor over `outbox_event`, from the audit row the write
already had to leave, so nothing has to be remembered to call them and nothing can happen
without its audit row (rulings 9 and 32).

Four rules the recomputation holds to:

- **One statement per bank, never one per case.** A footprint change in a bank with ten
  thousand cases is one UPDATE, and `apps/cases/tests_matching.py` pins the query count so
  a later convenience cannot turn it into a loop.
- **The one scope rule.** The verdict comes from `taxonomy_in_footprint`, the database's
  own half of the rule in `apps/taxonomy/matching.py` that every list query already uses.
  There is no second rule here, and a change to the rule moves what a case says.
- **A flip changes a cached boolean and nothing else** (D-30). No urgency is set, no triage
  is opened, nobody is notified, and the case's own decisions are untouched.
- **A case that falls outside is not hidden and not deleted.** It stays its owner's, and
  the feed's own footprint filter is what leaves it out; `footprint=all` still shows it.

One audit row per bank, naming how many cases moved. Never one per case: a recomputation is
the consequence of a decision somebody already made and already audited, not a new one.

This module writes, so it names no library record: the subquery over a change's scope terms
lives in `apps/cases/reading.py`, which is the split the library fence's AST guard demands
of `creation.py` for the same reason.
"""

from __future__ import annotations

import uuid

from django.db import transaction
from django.db.models import BooleanField, Func, Q, UUIDField, Value

from apps.cases import reading
from apps.cases.models import ChangeCase
from apps.shared import outbox, tenancy
from apps.shared.audit import Actor, record
from apps.shared.models import OutboxEvent, Tenant, TenantStatus
from apps.taxonomy.matching import SQL_FUNCTION
from apps.taxonomy.models import CaseStatusCategory

# What the two writers already record. One handler per kind, and no second relay.
FOOTPRINT_APPROVED = "footprint.change_approved"
CHANGE_FACTS_UPDATED = "regulatory_change.facts_updated"

RECOMPUTED = "case.footprint_match_recomputed"
# Nobody asked for this: a decision somebody else made moved the line, and the cases the
# line runs through were re-decided. A system actor is what the audit log should say.
ACTOR = Actor.system("footprint-recompute")

# A closed or dismissed case is finished work; re-deciding whether it is in scope would
# rewrite the record of what the bank did rather than what it should do next.
OPEN_CATEGORIES = ~Q(status__in=(CaseStatusCategory.CLOSED.value, CaseStatusCategory.DISMISSED.value))


def register() -> None:
    """Put both handlers on the one cursor. Called from the app's `ready()`, and safe to
    call again: `register_handler` treats the same function twice as one registration."""
    outbox.register_handler(FOOTPRINT_APPROVED, after_footprint_change)
    outbox.register_handler(CHANGE_FACTS_UPDATED, after_change_scope_change)


def after_footprint_change(event: OutboxEvent) -> None:
    """A bank's footprint moved: re-decide that bank's open cases.

    The event carries the bank's own tenant, so the cursor has already put the handler in
    that bank's zone and no other bank is in reach.
    """
    if event.tenant_id is None:  # pragma: no cover - a footprint change is always a bank's
        return
    _recompute(event.tenant_id, change_id=None)


def after_change_scope_change(event: OutboxEvent) -> None:
    """A change's facts moved: re-decide every bank's case for that change.

    The event belongs to no bank, so this runs in the library's zone and fans out. The
    banks are read once and in full before the first one's zone is entered, as case
    creation reads them, because each write moves the session into a different zone.
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
    """Re-decide this bank's cases in one statement, and record how many moved.

    `verdict` is the database's own scope rule over the change's scope terms, evaluated per
    row; the `exclude` is the same expression, so only the rows whose answer actually
    changed are written and a re-delivered event costs one statement and no rows.
    """
    verdict = Func(
        Value(tenant_id, output_field=UUIDField()),
        reading.scope_term_ids_of_each_case(),
        function=SQL_FUNCTION,
        output_field=BooleanField(),
    )
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
