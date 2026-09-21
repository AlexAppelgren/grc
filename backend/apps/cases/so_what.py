"""This bank's own "So what?" on a case (WAT-05).

Three things happen to one field, and keeping them apart is the point of the module:

- **The library's draft arrives.** A run files what a change means and the words are copied
  into every bank's case unconfirmed, by `apps/cases/creation.py` when the case is opened
  and by `apply_draft()` below when a later run improves the draft. A copy a person has
  already confirmed or rewritten is never touched: a bank's words are its own, and an agent
  never overwrites them.
- **A person confirms them.** The words stay the model's; what changes is that a named
  person at a named time stood behind them, which is what stops the screen labelling them
  AI output (WAT-05, AUD-02).
- **A person rewrites them.** The bank's own wording replaces the draft, and saving is
  itself the decision, so it confirms as well.

All three write one bank's own row and nothing else. The library's `ai_generation` row is
not moved by any of them: it has no tenant, two banks confirming would fight over one
shared row, and the split write policy refuses a bank session that reaches for it anyway
(chunk 5 ruling I). Moving that row's review state is a platform act and chunk 7 builds it.

Tenant zone only. The text a bank saves never leaves its tenant: not to another bank, not
to a log, not to Sentry, not to an outbox payload and not to a model endpoint (NFR-01,
NFR-04, D-07). The audit row says that the wording was saved and never what it says.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.cases import reading
from apps.cases.models import ChangeCase
from apps.cases.schemas import CasesSoWhat
from apps.shared import outbox, tenancy
from apps.shared.audit import Actor, record
from apps.shared.errors import ProblemError
from apps.shared.models import OutboxEvent, Tenant, TenantStatus

SUBJECT_TYPE = "change_case"
SAVED = "case.so_what_saved"
CONFIRMED = "case.so_what_confirmed"

# The kind `apps/watch/so_what_draft.py` writes when a run files or improves a change's
# drafted wording. One handler, one kind.
SO_WHAT_DRAFTED = "regulatory_change.so_what_drafted"

# Nobody in the bank asked for this: a run wrote a better draft and the product brought the
# bank's untouched copy up to it. A system actor is what the audit log should say.
DRAFT_ACTOR = Actor.system("so-what-drafted")
DRAFT_APPLIED = "case.so_what_draft_applied"


def register() -> None:
    """Put the backfill on the one cursor. Called from the app's `ready()`, and safe to call
    again: `register_handler` treats the same function twice as one registration."""
    outbox.register_handler(SO_WHAT_DRAFTED, apply_draft)


# ---------------------------------------------------------------------------------------
# PUT /changes/{changeId}/so-what and POST /changes/{changeId}/so-what/confirm
# ---------------------------------------------------------------------------------------
def save_so_what(*, tenant: Tenant, actor: Actor, user: Any, change_id: uuid.UUID, text: str) -> CasesSoWhat:
    """This bank's own wording, replacing the draft. Saving is the decision, so it confirms."""
    case = _case_for(tenant, change_id)
    return _write(case, actor=actor, user=user, text=text, action=SAVED)


def confirm_so_what(*, tenant: Tenant, actor: Actor, user: Any, change_id: uuid.UUID) -> CasesSoWhat:
    """The draft accepted as it stands: the words stay the model's, now stood behind.

    A case with no draft to confirm answers 404 rather than storing an empty confirmation,
    because "this bank confirmed nothing" is not a position anybody should be able to quote.
    """
    case = _case_for(tenant, change_id)
    if not case.so_what_text:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
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
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    return case


def _write(case: ChangeCase, *, actor: Actor, user: Any, text: str, action: str) -> CasesSoWhat:
    """One bank's row, its audit row and its outbox row in one transaction (AUD-01).

    Neither the wording before nor the wording after reaches the audit values: the text is
    tenant content and an audit row is read by everyone in the bank who holds `audit.read`,
    carried to a webhook and streamed to a SIEM (playbook 4.7). What is recorded is that
    the bank's own wording now stands, and who stood behind it.
    """
    was_confirmed = case.so_what_confirmed
    case.so_what_text = text
    case.so_what_confirmed = True
    case.so_what_confirmed_by = user
    case.so_what_confirmed_at = timezone.now()
    with transaction.atomic():
        case.save(
            update_fields=["so_what_text", "so_what_confirmed", "so_what_confirmed_by", "so_what_confirmed_at"]
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


# ---------------------------------------------------------------------------------------
# The library's draft reaching the banks (WAT-05, D-66)
# ---------------------------------------------------------------------------------------
def apply_draft(event: OutboxEvent) -> None:
    """A run filed or improved a change's drafted wording: bring every untouched copy up to
    it, one statement per bank.

    Runs in the library's zone, because the event belongs to no bank. A bank that has
    confirmed or rewritten its own wording is left alone — that is the whole rule — and a
    bank with no case for the change yet gets the draft when its case is opened.
    """
    change_id = event.audit_event.subject_id
    facts = None if change_id is None else reading.change_facts(change_id)
    if facts is None:  # pragma: no cover - the writer always names a change that exists
        return
    for tenant_id in _active_tenant_ids():
        _apply_draft_in_tenant(tenant_id, facts=facts)


def _active_tenant_ids() -> list[uuid.UUID]:
    """Every active bank, read once and in full before the first bank's zone is entered, as
    `apps/cases/creation.py` reads it: the writes that follow each move the session into a
    different zone."""
    return list(
        Tenant.objects.filter(status=TenantStatus.ACTIVE.value).order_by("slug").values_list("id", flat=True)
    )


@tenancy.tenant_task
def _apply_draft_in_tenant(tenant_id: uuid.UUID, *, facts: reading.ChangeFacts) -> None:
    """This bank's copy, in this bank's zone, in one statement.

    One audit row per bank naming how many copies moved, never one per case: this is a
    library draft arriving, not a decision anybody made, and it sets no urgency, opens no
    triage and notifies nobody.
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
