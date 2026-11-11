"""This bank's own "So what?" on a case (WAT-05).

- The library's draft arrives unconfirmed: `creation.py` copies it into each case, and
  `apply_draft()` brings untouched copies up to a later draft. A confirmed or rewritten copy
  is never touched; an agent never overwrites a bank's words.
- A person confirms it: the words stay the model's, now stood behind by a named person, so
  the screen stops labelling them AI output (WAT-05, AUD-02).
- A person rewrites it: saving is the decision, so it confirms as well.

All three write one bank's row. The library's `ai_generation` row is never moved: it has no
tenant and the split write policy refuses a bank session anyway. The text never leaves the
tenant (NFR-01, NFR-04, D-07); the audit row says the wording was saved, never what it says.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.cases import reading
from apps.cases.models import ChangeCase
from apps.cases.schemas import CasesSoWhat
from apps.shared import outbox, tenancy
from apps.shared.audit import Actor, record
from apps.shared.errors import not_found
from apps.shared.models import OutboxEvent, Tenant, TenantStatus

SUBJECT_TYPE = "change_case"
SAVED = "case.so_what_saved"
CONFIRMED = "case.so_what_confirmed"

# The kind `apps/watch/so_what_draft.py` writes when a run files or improves a draft.
SO_WHAT_DRAFTED = "regulatory_change.so_what_drafted"

# A run improved the draft and the product brought the bank's untouched copy up to it.
DRAFT_ACTOR = Actor.system("so-what-drafted")
DRAFT_APPLIED = "case.so_what_draft_applied"


def register() -> None:
    """Put the backfill on the one cursor. Called from the app's `ready()`, and safe to call
    again: `register_handler` treats the same function twice as one registration."""
    outbox.register_handler(SO_WHAT_DRAFTED, apply_draft)


# --- PUT /changes/{changeId}/so-what and POST /changes/{changeId}/so-what/confirm ---
def save_so_what(*, tenant: Tenant, actor: Actor, user: Any, change_id: uuid.UUID, text: str) -> CasesSoWhat:
    """This bank's own wording, replacing the draft. Saving is the decision, so it confirms."""
    case = _case_for(tenant, change_id)
    return _write(case, actor=actor, user=user, text=text, action=SAVED)


def confirm_so_what(*, tenant: Tenant, actor: Actor, user: Any, change_id: uuid.UUID) -> CasesSoWhat:
    """The draft accepted as it stands: the words stay the model's, now stood behind. No
    draft is 404, never an empty confirmation.
    """
    case = _case_for(tenant, change_id)
    if not case.so_what_text:
        raise not_found()
    return _write(case, actor=actor, user=user, text=case.so_what_text, action=CONFIRMED)


def _case_for(tenant: Tenant, change_id: uuid.UUID) -> ChangeCase:
    """This bank's case for that change. Another bank's case, and a change nobody has a case
    for, answer the same 404, so no id can be probed (playbook 4.4)."""
    case = (
        ChangeCase.objects.select_related("change", "so_what_confirmed_by")
        .filter(tenant=tenant, change_id=change_id)
        .first()  # ordering: unique (tenant, change), at most one row
    )
    if case is None:
        raise not_found()
    return case


def _write(case: ChangeCase, *, actor: Actor, user: Any, text: str, action: str) -> CasesSoWhat:
    """One bank's row, its audit row and its outbox row in one transaction (AUD-01). No
    wording reaches the audit values: it is tenant content, and audit rows travel to webhooks
    and SIEMs (playbook 4.7).
    """
    was_confirmed = case.so_what_confirmed
    case.so_what_text = text
    case.so_what_confirmed = True
    case.so_what_confirmed_by = user
    case.so_what_confirmed_at = timezone.now()
    # No `If-Match` here, but the case has changed: a workflow write made from a copy read
    # before this one must be told it is stale (CAS-08).
    case.version = F("version") + 1
    with transaction.atomic():
        case.save(
            update_fields=["so_what_text", "so_what_confirmed", "so_what_confirmed_by", "so_what_confirmed_at", "version"]
        )
        record(
            action=action,
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=case.id,
            subject_title=case.change.title,
            summary=f"{actor.label} settled what a change means for this company.",
            tenant_id=case.tenant_id,
            before={"soWhatConfirmed": was_confirmed},
            after={"soWhatConfirmed": True, "characters": len(text)},
        )
    return so_what_of(case)


def so_what_of(case: ChangeCase) -> CasesSoWhat:
    """The "So what?" as this bank holds it. `isAiDraft` is computed and never stored: it is
    exactly "there are words and nobody here has stood behind them yet"."""
    return CasesSoWhat(
        case_id=case.id,
        change_id=case.change_id,
        text=case.so_what_text or None,
        confirmed=case.so_what_confirmed,
        confirmed_at=case.so_what_confirmed_at,
        confirmed_by_name=None if case.so_what_confirmed_by is None else case.so_what_confirmed_by.name,
        is_ai_draft=bool(case.so_what_text) and not case.so_what_confirmed,
    )


# --- The library's draft reaching the banks (WAT-05, D-66) ---
def apply_draft(event: OutboxEvent) -> None:
    """A run filed or improved a change's drafted wording: bring every untouched copy up to
    it, one statement per bank, from the library's zone. A confirmed or rewritten copy is left
    alone; a bank with no case yet gets the draft when its case opens.
    """
    change_id = event.audit_event.subject_id
    facts = None if change_id is None else reading.change_facts(change_id)
    if facts is None:  # pragma: no cover - the writer always names a change that exists
        return
    for tenant_id in _active_tenant_ids():
        _apply_draft_in_tenant(tenant_id, facts=facts)


def _active_tenant_ids() -> list[uuid.UUID]:
    """Every active bank, read in full before the first bank's zone is entered."""
    return list(
        Tenant.objects.filter(status=TenantStatus.ACTIVE.value).order_by("slug").values_list("id", flat=True)
    )


@tenancy.tenant_task
def _apply_draft_in_tenant(tenant_id: uuid.UUID, *, facts: reading.ChangeFacts) -> None:
    """This bank's copy, in this bank's zone, in one statement, with one audit row naming how
    many moved: a draft arriving, not a decision, so no urgency, triage or notice.
    """
    with transaction.atomic():
        moved = (
            ChangeCase.objects.filter(
                tenant_id=tenant_id,
                change_id=facts.id,
                so_what_confirmed=False,
            )
            .exclude(so_what_text=facts.so_what_draft)
            .update(so_what_text=facts.so_what_draft)
        )
        if moved:
            record(
                action=DRAFT_APPLIED,
                actor=DRAFT_ACTOR,
                subject_type="regulatory_change",
                subject_id=facts.id,
                subject_title=facts.title,
                summary="A drafted answer to “So what?” arrived for a change.",
                tenant_id=tenant_id,
                after={"casesUpdated": moved},
            )
