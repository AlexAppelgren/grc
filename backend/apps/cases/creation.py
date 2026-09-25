"""One case per bank per change (CAS-01, WAT-05, FP-01, FP-03, AUD-01).

A registered change is a library fact every bank shares. A case is one bank's work on it,
and it exists from the moment the change does, so nothing a sweep finds can sit unowned.
The fan-out runs on the one ordered cursor over `outbox_event` (rulings 9 and 32), never in
the request that registered the change: a change reaching fifty banks writes fifty rows,
and the registering call must stay inside its budget.

What crosses from the library into a bank's zone, and what deliberately does not:

- **The footprint verdict, from the one scope rule.** `apps/library/reading.py` owns it and
  this module applies it per bank; there is no second rule here, which is why a change to
  the rule's own fixture moves what a case says. The change's scope carries the
  jurisdictions its authority reaches (`reading.change_facts()`, FP-04), so a Danish
  authority's change opens a case outside a Sweden-only footprint, and a watched market
  never sets its urgency or opens its triage (D-30). The verdict is cached because the change's
  scope and the bank's footprint both move afterwards, and `cases/matching.py` recomputes it
  when they do (`c5-cases-footprint-hooks`).
- **The agent's suggestions, still labelled as suggestions.** The urgency is the change's
  own, with `urgency_confirmed` false, and the drafted "So what?" is copied with
  `so_what_confirmed` false. A bank's own answer replaces either the moment a person gives
  one; until then the screen says whose words these are.
- **When triage is due, from the bank's own policy.** `triage_due_at` is the case's
  opening time plus the bank's `triage_target_hours` (COL-02), read with the list of banks
  so the fan-out costs no extra query per bank.
- **Nothing else of the library.** `apps/cases/reading.py` hands this module the five facts
  a case carries and no library record at all, which is also what keeps the library fence
  satisfied: a module that writes never names a library record.

Exactly once, without a read-then-write race: `UNIQUE (tenant, change)` is the backstop, so
a replayed event or a re-registration of the same `stableKey` finds the conflict at the
insert and leaves the bank's case exactly as it was.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Collection
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.cases import reading
from apps.cases.models import ChangeCase
from apps.library.reading import outside_reasons
from apps.shared import outbox, tenancy
from apps.shared.audit import Actor, record
from apps.shared.models import OutboxEvent, Tenant, TenantStatus
from apps.taxonomy import matching
from apps.taxonomy.models import CaseStatusCategory

logger = logging.getLogger(__name__)

# The kind the registration writes and this handler consumes. One handler, one kind.
CHANGE_REGISTERED = "change.registered"
CASE_CREATED = "case.created"

# Nobody asked for this bank's case: a sweep found a change and the product opened the work.
# A system actor is what the audit log should say, and never the agent behind the change,
# whose work stopped at the library.
ACTOR = Actor.system("change-registered")


def register() -> None:
    """Put the handler on the one cursor. Called from the app's `ready()`, and safe to call
    again: `register_handler` treats the same function twice as one registration, which is
    what lets a test that rebuilt the registry put this back without doubling it."""
    outbox.register_handler(CHANGE_REGISTERED, create_cases)


def create_cases(event: OutboxEvent) -> None:
    """Every active bank's case for the change this event named.

    Runs in the library's zone, because the event belongs to no bank; each case is written
    inside its own bank's zone by `_create_case`.
    """
    change_id = event.audit_event.subject_id
    facts = None if change_id is None else reading.change_facts(change_id)
    if facts is None:
        # The change the event named is not there. Nothing to fan out, and nothing worth
        # holding the cursor for: the row is delivered and the log names the row, not it.
        logger.warning("change.registered named no change", extra={"outboxEventId": str(event.id)})
        return
    restricting = matching.restricting_dimensions()
    for tenant_id, triage_target_hours in _active_tenants():
        _create_case(tenant_id, facts=facts, restricting=restricting, triage_target_hours=triage_target_hours)


def _active_tenants() -> list[tuple[uuid.UUID, int]]:
    """Every active bank with its triage target in hours, read once and in full before the
    first case is written.

    Once, because the fan-out must not read the list again from inside a bank's own zone,
    and in full because the writes that follow each move the session into a different zone.
    `CASE_CREATION_BATCH` is how many ids come back per round trip, so a change reaching
    hundreds of banks costs a handful of fetches rather than one per bank.
    """
    queryset = (
        Tenant.objects.filter(status=TenantStatus.ACTIVE.value)
        .order_by("slug")
        .values_list("id", "triage_target_hours")
    )
    return list(queryset.iterator(chunk_size=settings.CASE_CREATION_BATCH))


@tenancy.tenant_task
def _create_case(
    tenant_id: uuid.UUID, *, facts: reading.ChangeFacts, restricting: Collection[str], triage_target_hours: int
) -> None:
    """This bank's own case, inside this bank's zone, with its audit row and its outbox row
    in the same transaction as the case (AUD-01)."""
    match = not outside_reasons(facts.scope, matching.footprint_of(tenant_id), restricting)
    try:
        with transaction.atomic():
            case = ChangeCase.objects.create(
                tenant_id=tenant_id,
                change_id=facts.id,
                status=CaseStatusCategory.NEW.value,
                urgency_id=facts.urgency_id,
                urgency_confirmed=False,
                footprint_match=match,
                so_what_text=facts.so_what_draft,
                so_what_confirmed=False,
                triage_due_at=timezone.now() + timedelta(hours=triage_target_hours),
            )
            record(
                action=CASE_CREATED,
                actor=ACTOR,
                subject_type="change_case",
                subject_id=case.id,
                subject_title=facts.title,
                summary="A registered change opened a case that needs triage.",
                tenant_id=tenant_id,
                after={"status": case.status, "footprintMatch": match, "urgencyConfirmed": False},
            )
    except IntegrityError:
        # UNIQUE (tenant, change): this bank already has its case, so the event is a replay
        # or the change was registered again. The savepoint takes the attempt with it and
        # the bank's own case stands exactly as it was.
        return
