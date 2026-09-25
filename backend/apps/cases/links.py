"""This bank's own decision about a suggested obligation link (WAT-04, ruling C).

An agent links a change to the obligations it may touch, with a confidence; a library
editor confirms a link for the shared library. Neither of those is this. Here a compliance
officer says, on this bank's own case, that a suggested obligation really is affected here
or is not related to this bank at all — a separate fact, in the bank's own zone, that
changes nothing another bank sees.

Three rules hold it to that:

- **No library row is written.** `change_obligation` is not touched, which
  `apps/cases/tests_links.py` proves by reading it back unchanged after both decisions.
  The obligation itself is read for one reason only: to refuse a link to an obligation the
  library does not hold, which is the same 404 an unknown id gets.
- **A removal is a row, not a deletion.** `removed` is stored, so the case file can say the
  bank looked at the link and said no, and the same call reverses it. The link stays
  visible to every other bank.
- **One decision per obligation per case.** A second decision rewrites the bank's own row
  rather than stacking another, so a screen reading the case sees one answer.

An obligation removed here is not an obligation that does not apply: applicability is a
separate judgement in the register (REG-01), and nothing in this module touches it.
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
from apps.shared.errors import ProblemError
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
    """One bank's row, its audit row and its outbox row in one transaction (AUD-01).

    The obligation is resolved before the write opens, so a call naming one the library
    does not hold stores nothing and answers the same 404 an unknown id would get.
    """
    case = _case_for(tenant, change_id)
    details = reading.obligation_details(obligation_id, order)
    if details is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
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
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    return case
