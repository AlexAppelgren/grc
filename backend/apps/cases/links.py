"""This bank's own decision about a suggested obligation link (WAT-04, ruling C): on its own
case, a compliance officer says a suggested obligation really is affected here, or is not
related at all. A separate fact in the bank's zone that changes nothing another bank sees.

- No library row is written (`tests_links.py` reads `change_obligation` back unchanged);
  the obligation is read only to refuse an unknown one with the same 404.
- A removal is a stored `removed` row the same call reverses, so the case file shows it.
- One decision per obligation per case, rewritten in place.

Removing a link is not saying the obligation does not apply: that is the register's
(REG-01), untouched here.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.cases import reading
from apps.cases.models import CaseLinkDecision, CaseObligationLink, ChangeCase
from apps.cases.schemas import CasesObligationLink
from apps.shared.audit import Actor, record
from apps.shared.errors import not_found
from apps.shared.models import Tenant

SUBJECT_TYPE = "case_obligation_link"
DECIDED = "case.obligation_link_decided"


def accept_obligation_link(
    *, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID, obligation_id: uuid.UUID
) -> tuple[int, CasesObligationLink]:
    """`POST /changes/{changeId}/case/obligation-links`: this obligation really is affected
    for this bank."""
    return 201, _decide(
        tenant=tenant,
        actor=actor,
        user=user,
        order=order,
        change_id=change_id,
        obligation_id=obligation_id,
        decision=CaseLinkDecision.ACCEPTED,
    )


def remove_obligation_link(
    *, tenant: Tenant, actor: Actor, user: Any, order: list[str], change_id: uuid.UUID, obligation_id: uuid.UUID
) -> CasesObligationLink:
    """`DELETE /changes/{changeId}/case/obligation-links/{obligationId}`: not related to this
    bank. Despite the method nothing is deleted; the answer is the stored decision."""
    return _decide(
        tenant=tenant,
        actor=actor,
        user=user,
        order=order,
        change_id=change_id,
        obligation_id=obligation_id,
        decision=CaseLinkDecision.REMOVED,
    )


def _decide(
    *,
    tenant: Tenant,
    actor: Actor,
    user: Any,
    order: list[str],
    change_id: uuid.UUID,
    obligation_id: uuid.UUID,
    decision: CaseLinkDecision,
) -> CasesObligationLink:
    """One bank's row, its audit row and its outbox row in one transaction (AUD-01). The
    obligation is resolved first, so an unknown one stores nothing and answers 404.
    """
    case = _case_for(tenant, change_id)
    details = reading.obligation_details(obligation_id, order)
    if details is None:
        raise not_found()
    stored = (
        CaseObligationLink.objects.filter(tenant_id=case.tenant_id, case=case, obligation_id=obligation_id)
        .first()  # ordering: unique (tenant, case, obligation), at most one row
    )
    with transaction.atomic():
        row, _created = CaseObligationLink.objects.update_or_create(
            tenant_id=case.tenant_id,
            case=case,
            obligation_id=obligation_id,
            defaults={"decision": decision.value, "decided_by": user, "decided_at": timezone.now()},
        )
        record(
            action=DECIDED,
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=row.id,
            subject_title=details.title,
            summary=f"{actor.label} decided whether an obligation is affected for this company.",
            tenant_id=case.tenant_id,
            before={} if stored is None else {"decision": stored.decision},
            after={"decision": decision.value, "obligationId": str(obligation_id), "changeId": str(change_id)},
        )
    return CasesObligationLink(
        obligation_id=obligation_id,
        title=details.title,
        instrument_short_name=details.instrument_short_name,
        ref_label=details.ref_label,
        decision=decision.value,
        decided_at=row.decided_at,
        decided_by_name=None if user is None else user.name,
    )


def _case_for(tenant: Tenant, change_id: uuid.UUID) -> ChangeCase:
    """This bank's case for that change. Another bank's case, and a change nobody has a case
    for, answer the same 404, so no id can be probed (playbook 4.4)."""
    case = (
        ChangeCase.objects.filter(tenant=tenant, change_id=change_id)
        .first()  # ordering: unique (tenant, change), at most one row
    )
    if case is None:
        raise not_found()
    return case
