"""Approve all: one reviewer's decision to approve every proposal waiting in the console
queue under the filters they chose, carried out by the worker (PRO-02, D-128).

Approving the library baseline one call at a time from the browser took a round trip per
proposal, about an hour for 2,400. Here the reviewer steps up once and names the filters;
`start` reads the ids of what is waiting at that moment, writes one audit row for the
decision under that assertion, and queues `tasks.approve_listed`, which approves each id
through `logic.approve`, the one door into the library, in a transaction of its own. Every
approval writes its own audit rows with the same assertion id, four eyes is checked row by
row as always, and a refused row is counted with its reason while the rest go on.

Only what was waiting when the reviewer confirmed is approved: a proposal filed during the
run, such as the duties of a regulation the run just approved, waits for the next decision.
What the page selection would refuse is never read: the reviewer's own proposals, flagged
ones and batches, each for its own review.

The run's progress lives in the cache under the reviewer's id, the only reader being the
reviewer's own queue screen; the audit trail and the queue are the record of what happened.
One run per reviewer at a time: a second start while one is running answers 409
`approval_running`, unless the running one has said nothing for
`PROPOSALS_APPROVE_ALL_STALE_S`, which means its worker stopped.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.proposals import logic
from apps.proposals.logic import Reviewer
from apps.proposals.models import ProposalStatus
from apps.shared.audit import Actor, ActorType, record

IDLE = "idle"
RUNNING = "running"
FINISHED = "finished"
# How many refusals a run keeps with their reasons; the count covers them all.
REFUSALS_KEPT = 20
# How often the worker writes its progress, in approvals.
PROGRESS_EVERY = 10


def _key(user_id: uuid.UUID | str) -> str:
    return f"proposals:approve-all:{user_id}"


def idle() -> dict[str, Any]:
    return {"status": IDLE, "total": 0, "approved": 0, "refused": 0, "refusals": [], "startedAt": None, "updatedAt": None}


def state_of(user_id: uuid.UUID | str) -> dict[str, Any]:
    """The reviewer's latest run as the worker last wrote it, or an idle one."""
    state = cache.get(_key(user_id))
    return state if isinstance(state, dict) else idle()


def _save(user_id: uuid.UUID | str, state: dict[str, Any]) -> None:
    state["updatedAt"] = timezone.now().isoformat()
    cache.set(_key(user_id), state, timeout=settings.PROPOSALS_APPROVE_ALL_KEEP_S)


def _stale(state: dict[str, Any]) -> bool:
    updated = state.get("updatedAt")
    if not updated:
        return True
    return (timezone.now() - datetime.fromisoformat(updated)).total_seconds() > settings.PROPOSALS_APPROVE_ALL_STALE_S


def start(*, reviewer: Reviewer, kind: str | None, origin: str | None, step_up_assertion_id: uuid.UUID) -> dict[str, Any]:
    """Read what is waiting under the filters, record the decision and queue the run."""
    from apps.proposals import tasks

    user = reviewer.user
    current = state_of(user.id)
    if current["status"] == RUNNING and not _stale(current):
        raise ValidationError(
            "Your approval of every waiting proposal is still running. Wait for it to finish.",
            code="approval_running",
        )
    waiting = logic.queue(reviewer=reviewer, status=ProposalStatus.OPEN.value, kind=kind, origin=origin, not_mine=True)
    ids = [str(pk) for pk in waiting.filter(is_batch=False, risk_flags=[]).values_list("id", flat=True)]
    with transaction.atomic():
        record(
            action="proposal.approve_all_started",
            actor=reviewer.actor,
            subject_type=logic.SUBJECT_TYPE,
            subject_id=None,
            subject_title="",
            summary=f"Started approving all {len(ids)} waiting proposals",
            tenant_id=None,
            after={"count": len(ids), "kind": kind or "", "origin": origin or ""},
            step_up_assertion_id=step_up_assertion_id,
        )
        state = {**idle(), "status": RUNNING if ids else FINISHED, "total": len(ids), "startedAt": timezone.now().isoformat()}
        _save(user.id, state)
        if ids:
            transaction.on_commit(lambda: tasks.approve_listed.delay(str(user.id), ids, str(step_up_assertion_id)))
    return state


def approve_listed(*, user: Any, proposal_ids: list[str], step_up_assertion_id: uuid.UUID) -> dict[str, Any]:
    """Approve each listed proposal through `logic.approve`, one transaction each, as the
    reviewer who started the run and under the assertion they gave. A refusal is counted,
    the first `REFUSALS_KEPT` with their reasons, and the run goes on."""
    reviewer = Reviewer(actor=Actor(kind=ActorType.USER, id=user.id, label=user.name), user=user)
    state = {**state_of(user.id), "status": RUNNING, "total": len(proposal_ids)}
    try:
        for done, proposal_id in enumerate(proposal_ids, start=1):
            title = ""
            try:
                proposal = logic.by_id(uuid.UUID(proposal_id))
                title = proposal.title
                logic.approve(proposal=proposal, reviewer=reviewer, actor=reviewer.actor, note="", step_up_assertion_id=step_up_assertion_id)
            except ValidationError as refused:
                state["refused"] += 1
                if len(state["refusals"]) < REFUSALS_KEPT:
                    code = getattr(refused, "code", "") or "validation_error"
                    state["refusals"].append({"id": proposal_id, "title": title, "code": code, "detail": " ".join(refused.messages)})
            else:
                state["approved"] += 1
            if done % PROGRESS_EVERY == 0:
                _save(user.id, state)
    finally:
        state["status"] = FINISHED
        _save(user.id, state)
    return state
