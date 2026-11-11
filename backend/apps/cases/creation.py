"""One case per bank per change (CAS-01, WAT-05, FP-01, FP-03, AUD-01).

A case exists from the moment its change does, so nothing a sweep finds sits unowned. The
fan-out runs on the ordered outbox cursor, never in the registering request, which must stay
inside its budget. What crosses into a bank's zone:

- The footprint verdict, from the one scope rule (`apps/library/reading.py`); the change's
  scope includes the jurisdictions its authority reaches (FP-04), and a watched market never
  sets urgency or opens triage (D-30). Cached, and recomputed by `cases/matching.py`.
- The agent's suggestions, still labelled: the urgency with `urgency_confirmed` false and
  the drafted "So what?" with `so_what_confirmed` false.
- `triage_due_at`: opening time plus the bank's `triage_target_hours` (COL-02).
- Nothing else: `reading.py` hands over five facts, so this writing module names no library
  record (library fence).

`UNIQUE (tenant, change)` makes it exactly once: a replay or re-registration leaves the case
as it was.
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

# Nobody asked for this case: the product opened it. A system actor, never the agent behind
# the change, whose work stopped at the library.
ACTOR = Actor.system("change-registered")


def register() -> None:
    """Put the handler on the one cursor. Called from `ready()`; safe to call again, since
    `register_handler` counts the same function once."""
    outbox.register_handler(CHANGE_REGISTERED, create_cases)


def create_cases(event: OutboxEvent) -> None:
    """Every active bank's case for the change this event named. Runs in the library's
    zone; each case is written in its own bank's zone by `_create_case`.
    """
    change_id = event.audit_event.subject_id
    facts = None if change_id is None else reading.change_facts(change_id)
    if facts is None:
        # Nothing to fan out; the log names the row, not the change.
        logger.warning("change.registered named no change", extra={"outboxEventId": str(event.id)})
        return
    restricting = matching.restricting_dimensions()
    for tenant_id, triage_target_hours in _active_tenants():
        _create_case(tenant_id, facts=facts, restricting=restricting, triage_target_hours=triage_target_hours)


def _active_tenants() -> list[tuple[uuid.UUID, int]]:
    """Every active bank with its triage target in hours, read once and in full before the
    first case is written, since each write moves the session into another zone.
    `CASE_CREATION_BATCH` ids come back per round trip.
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
        # UNIQUE (tenant, change): a replay or re-registration. The savepoint takes the
        # attempt with it and the bank's case stands as it was.
        return
