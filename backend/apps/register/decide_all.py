"""Decide all: one person's confirmed decision that everything the register offers for one
company applies or does not, or a whole regulation of it, or the rows they ticked, carried
out by the worker with no limit on how many (REG-01, D-75, D-128, AC-REG1).

`start` reads, at that moment, the obligations offered for the company that nobody has
answered (`company_view.offered_for`: the page's own OFFERED, TARGET and TO DECIDE), writes
one audit row for the decision and queues `tasks.decide_listed` with ids alone. The task
decides one chunk of `REGISTER_BULK_MAX` in its own transaction and queues what is left, so a
chunk is committed before the next begins and a stopped worker loses at most one. Each
target goes through `applicability._store`, the door of a single answer: the same checks,
locks, audit event per row and recurring duties, as the person who started the run.

Four rules the door alone does not give:

- A person's answer is never overwritten. Before the door, each chunk locks the rows its
  targets name and drops those a person has answered meanwhile, counted as skipped.
- Only what is still offered is set. The door checks an obligation's span and never the
  bank's working inventory, so each chunk reads afresh which of its targets the register
  still offers for the company and refuses the others.
- The person must still be allowed. Before each chunk the run reads afresh that they are an
  active member holding `applicability.approve`, and otherwise stops with an audit row.
- The reason never leaves the bank. It is kept beside the run's state in the cache, under
  the bank and the person, read there by the worker and dropped when the run ends: a task
  argument is printed by a broker and by an error tracker. Nothing here logs, and no
  exception carries it.

One run per person and bank: a second start answers 409 `decision_running` unless the running
one is silent past `REGISTER_DECIDE_ALL_STALE_S`. A task acts only on its own run and its own
place in it, so a run replaced meanwhile and a chunk delivered twice decide nothing.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, NamedTuple

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.identity import api_keys_logic
from apps.identity.models import User
from apps.library import reading
from apps.library.models import Obligation
from apps.register import applicability, company_view
from apps.register.schemas import REFUSALS_KEPT, RegisterDecideAllBody
from apps.shared import permissions as perms
from apps.shared.audit import Actor, ActorType, record
from apps.shared.models import Tenant
from apps.taxonomy.reading import FALLBACK_LANGUAGE
from apps.tenants.models import OrgUnit

IDLE = "idle"
RUNNING = "running"
FINISHED = "finished"
STARTED = "register.decide_all_started"
STOPPED = "register.decide_all_stopped"
# The decision is about one company of the bank, so its audit rows are that company's.
SUBJECT_TYPE = "org_unit"
# Why a run ended before trying every target (schemas.DecideAllStopped).
PERMISSION_REVOKED = "permission_revoked"
MEMBERSHIP_ENDED = "membership_ended"
REASON_EXPIRED = "reason_expired"
FAILED = "failed"


class _Run(NamedTuple):
    """What every chunk of one run decides with: who, for which company, what and why."""

    tenant: Tenant
    user_id: uuid.UUID
    actor: Actor
    order: list[str]
    company_id: uuid.UUID
    word: str
    reason: str


class _Outcome(NamedTuple):
    """What became of the targets of one pass through the door, each counted once."""

    stored: int = 0
    skipped: int = 0
    refused: tuple[tuple[uuid.UUID, str, str], ...] = ()  # obligation, code, detail


# --- The run's state: what the screen reads, and beside it what only the worker reads ---
def _key(tenant_id: uuid.UUID, user_id: uuid.UUID) -> str:
    return f"register:decide-all:{tenant_id}:{user_id}"


def idle() -> dict[str, Any]:
    return {
        "status": IDLE,
        "total": 0,
        "set": 0,
        "skipped": 0,
        "refused": 0,
        "refusals": [],
        "stopped": None,
        "orgUnitId": None,
        "instrument": None,
        "applicability": None,
        "startedAt": None,
        "updatedAt": None,
    }


def state_of(tenant_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any]:
    """The person's latest run in this bank as the worker last wrote it, or an idle one. Never
    the reason, which is kept beside the state and not in it."""
    held = cache.get(_key(tenant_id, user_id))
    return held["state"] if isinstance(held, dict) else idle()


def _keep(tenant_id: uuid.UUID, user_id: uuid.UUID, held: dict[str, Any]) -> None:
    cache.set(_key(tenant_id, user_id), held, timeout=settings.REGISTER_DECIDE_ALL_KEEP_S)


def _stale(state: dict[str, Any]) -> bool:
    updated = state.get("updatedAt")
    return not updated or (timezone.now() - datetime.fromisoformat(updated)).total_seconds() > settings.REGISTER_DECIDE_ALL_STALE_S


def _queue(tenant_id: uuid.UUID, user_id: uuid.UUID, company_id: uuid.UUID, obligation_ids: list[str], word: str, run_id: str) -> None:
    """Hand these targets to the worker once the open transaction has committed: ids, the
    answer and the run, never the reason."""
    from apps.register import tasks

    transaction.on_commit(lambda: tasks.decide_listed.delay(str(tenant_id), str(user_id), str(company_id), obligation_ids, word, run_id))


def _actor(user: User) -> Actor:
    return Actor(kind=ActorType.USER, id=user.id, label=user.name)


# --- POST /applicability/decide-all ---
def start(*, tenant: Tenant, user: User, body: RegisterDecideAllBody) -> dict[str, Any]:
    """Read what is to decide under the body's filters, record the decision and queue the run.
    The state is kept, and the worker queued, only once the request has committed."""
    current = state_of(tenant.id, user.id)
    if current["status"] == RUNNING and not _stale(current):
        raise ValidationError("Your earlier Decide all is still running. Wait for it to finish.", code="decision_running")
    selected = body.obligation_ids
    cap = settings.REGISTER_DECIDE_ALL_SELECTED_MAX
    if selected is not None and len(selected) > cap:
        raise ValidationError(f"Select at most {cap} obligations in one call, or leave the selection out to decide them all.", code="validation_error")
    company, offered = company_view.offered_for(tenant=tenant, org_unit_id=body.org_unit_id, instrument=body.instrument)
    if selected is not None and set(selected) - offered.keys():
        raise ValidationError("That obligation is not offered for this legal entity.", code="not_found")
    chosen = offered.keys() if selected is None else set(selected)
    targets = [str(obligation_id) for obligation_id, to_decide in offered.items() if to_decide and obligation_id in chosen]
    now = timezone.now().isoformat()
    state = {
        **idle(),
        "status": RUNNING if targets else FINISHED,
        "total": len(targets),
        "orgUnitId": str(company.id),
        "instrument": body.instrument,
        "applicability": body.applicability,
        "startedAt": now,
        "updatedAt": now,
    }
    # The run's own name, and the reason for as long as there is something left to set.
    run_id = uuid.uuid4().hex
    held = {"state": state, "reason": body.reason if targets else "", "runId": run_id}
    with transaction.atomic():
        record(
            action=STARTED,
            actor=_actor(user),
            subject_type=SUBJECT_TYPE,
            subject_id=company.id,
            subject_title=company.name,
            summary=f"Started deciding all {len(targets)} unanswered obligations",
            tenant_id=tenant.id,
            after={
                "count": len(targets),
                "orgUnitId": str(company.id),
                "instrument": body.instrument,
                "applicability": body.applicability,
                "selected": selected is not None,
            },
        )
        transaction.on_commit(lambda: _keep(tenant.id, user.id, held))
        if targets:
            _queue(tenant.id, user.id, company.id, targets, body.applicability, run_id)
    return state


# --- The worker: one chunk a task (tasks.decide_listed) ---
def decide_chunk(*, tenant_id: uuid.UUID, user_id: uuid.UUID, company_id: uuid.UUID, obligation_ids: list[str], word: str, run_id: str) -> None:
    """Decide the first `REGISTER_BULK_MAX` of `obligation_ids`, save the progress and queue the
    rest. Runs in the task's transaction with the bank activated. Whatever happens, a run this
    call ends reads as finished, and `stopped` says why when it did not try every target."""
    held = cache.get(_key(tenant_id, user_id))
    if held is None:
        # The run's state went before the worker came to it, and the reason with it.
        held = {"state": {**idle(), "total": len(obligation_ids), "orgUnitId": str(company_id), "applicability": word}, "reason": "", "runId": run_id}
    state = held["state"]
    left = state["total"] - state["set"] - state["skipped"] - state["refused"]
    if held["runId"] != run_id or state["status"] == FINISHED or left != len(obligation_ids):
        return  # another run replaced this one, or this chunk was delivered before: nothing to do
    rest: list[str] = []
    state["stopped"] = FAILED  # unless this chunk gets through, or stops for a reason it names
    try:
        user = User.objects.select_related("locale").get(pk=user_id)
        tenant = Tenant.objects.select_related("default_language").get(pk=tenant_id)
        spoken = [language.key for language in (user.locale, tenant.default_language) if language is not None]
        run = _Run(tenant, user_id, _actor(user), [*spoken, FALLBACK_LANGUAGE], company_id, word, held["reason"])
        why = _why_not(run)
        if why is None:
            chunk = settings.REGISTER_BULK_MAX
            _tally(state, _decide(run, [uuid.UUID(obligation_id) for obligation_id in obligation_ids[:chunk]]), run.order)
            rest = obligation_ids[chunk:]
        else:
            _stop(run, state, why, left)
        state["stopped"] = why
    finally:
        if not rest:
            state["status"], held["reason"] = FINISHED, ""
        state["updatedAt"] = timezone.now().isoformat()
        if state["stopped"] == FAILED:
            _keep(tenant_id, user_id, held)  # this chunk's transaction is lost, so say so now
    # The progress is kept once the chunk has committed, and only then is the rest queued: a
    # chunk that never commits is delivered again and finds its place unchanged.
    transaction.on_commit(lambda: _keep(tenant_id, user_id, held))
    if rest:
        _queue(tenant_id, user_id, company_id, rest, word, run_id)


def _why_not(run: _Run) -> str | None:
    """Why the run may not go on, or None while it may: its reason is no longer kept, the
    person is no longer an active member of the bank, or their roles no longer hold
    `applicability.approve`. Read afresh before every chunk, never from the run's start."""
    if not run.reason:
        return REASON_EXPIRED
    held = api_keys_logic.person_permissions(run.tenant.id, run.user_id)
    if held is None:
        return MEMBERSHIP_ENDED
    return None if perms.APPLICABILITY_APPROVE in held else PERMISSION_REVOKED


def _stop(run: _Run, state: dict[str, Any], why: str, left: int) -> None:
    record(
        action=STOPPED,
        actor=run.actor,
        subject_type=SUBJECT_TYPE,
        subject_id=run.company_id,
        subject_title=OrgUnit.objects.values_list("name", flat=True).get(pk=run.company_id),
        summary=f"Stopped deciding all unanswered obligations with {left} left",
        tenant_id=run.tenant.id,
        after={"stopped": why, "set": state["set"], "skipped": state["skipped"], "refused": state["refused"], "left": left},
    )


def _decide(run: _Run, obligation_ids: list[uuid.UUID]) -> _Outcome:
    """These targets through the door together, in a savepoint. When the door refuses them
    (a `ValidationError`, which leaves nothing behind), each goes through on its own, so one
    refused row does not cost the others. Any other error ends the run as failed."""
    try:
        with transaction.atomic():
            return _through_the_door(run, obligation_ids)
    except ValidationError as refusal:
        if len(obligation_ids) == 1:
            code = getattr(refusal, "code", None) or "validation_error"
            return _Outcome(refused=((obligation_ids[0], code, " ".join(refusal.messages)),))
    outcomes = [_decide(run, [obligation_id]) for obligation_id in obligation_ids]
    return _Outcome(
        stored=sum(outcome.stored for outcome in outcomes),
        skipped=sum(outcome.skipped for outcome in outcomes),
        refused=tuple(refusal for outcome in outcomes for refusal in outcome.refused),
    )


def _through_the_door(run: _Run, obligation_ids: list[uuid.UUID]) -> _Outcome:
    """Lock the rows these targets name, leave those a person has answered and those no longer
    offered for the company, and store the rest through `applicability._store`. A row that does
    not exist yet has no lock to take: a first answer written in the same instant meets this
    one in the door as two single answers meet, the later one standing and both audited."""
    company, targets = company_view.targets_for(tenant=run.tenant, org_unit_id=run.company_id, obligations=Obligation.objects.filter(pk__in=obligation_ids))
    entries = applicability._locked_entries(obligation_ids)
    rows = applicability._locked_scopes([entry.id for entry in entries.values()], {company.id})
    answers: list[applicability._Answer] = []
    skipped = 0
    refused: list[tuple[uuid.UUID, str, str]] = []
    for obligation_id in obligation_ids:
        if obligation_id not in targets:
            refused.append((obligation_id, "not_found", "This obligation is no longer offered for this legal entity."))
            continue
        target = targets[obligation_id]
        entry = entries.get(obligation_id)
        row = entry if target is None or entry is None else rows.get((entry.id, target))
        if company_view.answered(row):
            skipped += 1
        else:
            answers.append(applicability._Answer(obligation_id, target, None, run.word, run.reason))
    if answers:
        applicability._store(tenant=run.tenant, actor=run.actor, order=run.order, answers=answers, expected_version=None)
    return _Outcome(stored=len(answers), skipped=skipped, refused=tuple(refused))


def _tally(state: dict[str, Any], outcome: _Outcome, order: list[str]) -> None:
    """Add one chunk's outcome to the run's progress, keeping the first refusals with their
    reasons and each obligation's own title."""
    state["set"] += outcome.stored
    state["skipped"] += outcome.skipped
    state["refused"] += len(outcome.refused)
    kept = outcome.refused[: max(REFUSALS_KEPT - len(state["refusals"]), 0)]
    if kept:
        headings = reading.obligation_headings([obligation_id for obligation_id, _, _ in kept], order)
        state["refusals"] += [
            {
                "obligationId": str(obligation_id),
                "title": headings[obligation_id].title if obligation_id in headings else "",
                "code": code,
                "detail": detail,
            }
            for obligation_id, code, detail in kept
        ]
