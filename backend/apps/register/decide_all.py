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

- A person's answer is never overwritten. Before the door, each chunk creates the rows its
  targets name that do not exist yet (an insert that skips a row another write created), then
  locks them all and drops those a person has answered meanwhile, counted as skipped. A
  colleague's answer to the same row, written at the same moment, meets this chunk on the
  row's key or lock and is read under it: it is never taken for an unanswered row.
- Only what is still offered is set. The door checks an obligation's span and never the
  bank's working inventory, so each chunk reads afresh which of its targets the register
  still offers for the company and refuses the others.
- The person must still be allowed. Before each chunk the run reads afresh that they are an
  active member holding `applicability.approve` and that the company is still an active legal
  entity, and otherwise stops with an audit row.
- The reason never leaves the bank. It is kept beside the run's state in the cache, under
  the bank and the person, read there by the worker and dropped when the run ends: a task
  argument is printed by a broker and by an error tracker. Nothing here logs, and no
  exception carries it.

One run per person and bank: a second start answers 409 `decision_running` unless the running
one is silent past `REGISTER_DECIDE_ALL_STALE_S`. The start and every chunk hold one advisory
lock of the bank and the person for their whole transaction, and read and write the run's
state only under it, before the commit as `approve_all` writes its own: two starts at once are
one start and one 409, and a chunk delivered twice at once is decided once. A task acts only
on its own run and its own place in it: a chunk delivered again finds its place moved and
decides nothing, and a run replaced meanwhile decides nothing and records that it stopped. A
chunk whose body raises or whose commit fails ends its run as failed through the task's failure
hook (`fail`), with one `register.decide_all_stopped` row in a transaction of its own, so the
trail says the run ended even once the cache has let the state go. Every chunk keeps its state
marked uncommitted until its commit has happened, and only then keeps its counts as the run's
committed ones: a chunk whose commit fails, the last or only one and one that stopped for a
named reason among them, is still the hook's to record, and the row and the ended state count
what the run committed and never what was rolled back.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, NamedTuple

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from apps.identity import api_keys_logic
from apps.identity.models import User
from apps.library import reading
from apps.library.models import Obligation
from apps.register import applicability, company_view
from apps.register.schemas import REFUSALS_KEPT, RegisterDecideAllBody
from apps.shared import permissions as perms
from apps.register.logic import ensure_register_entries
from apps.shared import tenancy
from apps.shared.audit import Actor, ActorType, batched, record
from apps.shared.models import Tenant
from apps.taxonomy.reading import FALLBACK_LANGUAGE
from apps.tenants.models import OrgUnit, OrgUnitKind

logger = logging.getLogger(__name__)

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
COMPANY_GONE = "company_gone"
# Only in a stopped row's audit event: the run's own state was taken by a newer run's.
REPLACED = "replaced"
# Beside the state, never in it: the latest chunk kept its progress and has not committed yet.
UNCOMMITTED = "uncommitted"
# Beside the state: what the run's committed chunks counted, which a failed run's end reports.
COMMITTED = "committed"
COUNTS = ("set", "skipped", "refused")


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


def _lock_run(tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Hold the run's lock of the bank and the person until the open transaction ends."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [_key(tenant_id, user_id)])


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
    The state is read and kept under the run's lock; the worker is queued once the request
    has committed."""
    _lock_run(tenant.id, user.id)
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
        after: dict[str, Any] = {
            "count": len(targets),
            "orgUnitId": str(company.id),
            "instrument": body.instrument,
            "applicability": body.applicability,
            "selected": selected is not None,
        }
        if body.reason_draft_id is not None:
            # The reason began as the person's AI draft (D-143): its id and their review, never its words.
            after["reasonDraft"] = applicability.confirm_draft(
                tenant_id=tenant.id, actor=_actor(user), draft_id=body.reason_draft_id, reason=body.reason, org_unit_id=body.org_unit_id, applicability=body.applicability
            )
        record(
            action=STARTED,
            actor=_actor(user),
            subject_type=SUBJECT_TYPE,
            subject_id=company.id,
            subject_title=company.name,
            summary=f"Started deciding all {len(targets)} unanswered obligations",
            tenant_id=tenant.id,
            after=after,
        )
        _keep(tenant.id, user.id, held)
        if targets:
            _queue(tenant.id, user.id, company.id, targets, body.applicability, run_id)
    return state


# --- The worker: one chunk a task (tasks.decide_listed) ---
def decide_chunk(*, tenant_id: uuid.UUID, user_id: uuid.UUID, company_id: uuid.UUID, obligation_ids: list[str], word: str, run_id: str) -> None:
    """Decide the first `REGISTER_BULK_MAX` of `obligation_ids`, save the progress and queue the
    rest. Runs in the task's transaction with the bank activated. Whatever happens, a run this
    call ends reads as finished, and `stopped` says why when it did not try every target."""
    _lock_run(tenant_id, user_id)
    held = cache.get(_key(tenant_id, user_id))
    if held is None:
        # The run's state went before the worker came to it, and the reason with it.
        held = {"state": {**idle(), "total": len(obligation_ids), "orgUnitId": str(company_id), "applicability": word}, "reason": "", "runId": run_id}
    if held["runId"] != run_id:
        # A newer run took this one's place, so the rest of this one is never tried.
        _stop(tenant_id, _actor(User.objects.get(pk=user_id)), company_id, {}, REPLACED, len(obligation_ids))
        return
    state = held["state"]
    left = state["total"] - state["set"] - state["skipped"] - state["refused"]
    if state["status"] == FINISHED or left != len(obligation_ids):
        return  # this chunk was delivered before: nothing to do
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
            _stop(tenant_id, run.actor, company_id, {count: state[count] for count in COUNTS}, why, left)
        state["stopped"] = why
    finally:
        if not rest:
            state["status"], held["reason"] = FINISHED, ""
        # Until this chunk has committed, a failure of its body or of its commit is the failure
        # hook's to record: `_committed` drops the mark once it has.
        held[UNCOMMITTED] = True
        state["updatedAt"] = timezone.now().isoformat()
        # Kept under the run's lock, so a delivery of this chunk waiting on it finds its place
        # moved. The rest is queued only once this chunk has committed.
        _keep(tenant_id, user_id, held)
    transaction.on_commit(lambda: _committed(tenant_id, user_id, run_id))
    if rest:
        _queue(tenant_id, user_id, company_id, rest, word, run_id)


def _committed(tenant_id: uuid.UUID, user_id: uuid.UUID, run_id: str) -> None:
    """Once a chunk has committed: its counts are the run's committed ones and the mark that it
    had not committed goes, read and kept under the run's lock and only for this run."""
    with transaction.atomic():
        _lock_run(tenant_id, user_id)
        held = cache.get(_key(tenant_id, user_id))
        if isinstance(held, dict) and held["runId"] == run_id and held.pop(UNCOMMITTED, False):
            held[COMMITTED] = {count: held["state"][count] for count in COUNTS}
            _keep(tenant_id, user_id, held)


def _failing(held: Any, run_id: str) -> bool:
    """Whether the run `run_id` failed and the trail does not say so yet: it is still the
    person's latest run, and it is either still running (a chunk's task failed before it kept
    its progress, or kept it and never committed) or its last chunk kept its progress and never
    committed, whether its body raised, its commit failed or it had stopped for a reason it
    named. A run whose last chunk committed has its end in the trail already, and a replaced
    run is not this one."""
    if not isinstance(held, dict) or held["runId"] != run_id:
        return False
    return held["state"]["status"] != FINISHED or bool(held.get(UNCOMMITTED))


def _end_failed(tenant_id: uuid.UUID, user_id: uuid.UUID, held: dict[str, Any]) -> None:
    """Keep the run as finished and failed, counting what it committed, without its reason."""
    committed = held.get(COMMITTED) or dict.fromkeys(COUNTS, 0)
    held["state"] = {**held["state"], **committed, "status": FINISHED, "stopped": FAILED, "updatedAt": timezone.now().isoformat()}
    held["reason"] = ""
    held.pop(UNCOMMITTED, None)
    _keep(tenant_id, user_id, held)


def fail(*, tenant_id: uuid.UUID, user_id: uuid.UUID, company_id: uuid.UUID, run_id: str) -> None:
    """End the run as failed when its chunk's task failed, in its body or at its commit: the
    task's failure hook, which runs once the task's transaction has rolled back. One
    `register.decide_all_stopped` row says so (`_record_failure`), unless the run already
    ended with its own row or was replaced; a hook fired again finds it recorded. The state
    then reads finished and failed, claimed under the run's lock in that row's transaction and
    written all the same when the row could not be: the screen never shows a failed run as
    running for ever."""
    if not _failing(cache.get(_key(tenant_id, user_id)), run_id):
        return
    try:
        # A connection the failure left unusable is closed, so the row is written on a new one.
        if not connection.in_atomic_block:
            connection.close_if_unusable_or_obsolete()
        _record_failure(tenant_id, user_id, company_id, run_id)
    except DatabaseError:
        logger.exception("Could not record that the Decide all run %s failed", run_id)
    finally:
        held = cache.get(_key(tenant_id, user_id))
        if _failing(held, run_id):
            _end_failed(tenant_id, user_id, held)


@tenancy.tenant_task
def _record_failure(tenant_id: uuid.UUID, user_id: uuid.UUID, company_id: uuid.UUID, run_id: str) -> None:
    """The failed run's one end row, in a transaction of its own with the bank activated, read
    again under the run's lock: what its committed chunks counted, and how many were left. The
    run is claimed as ended under that same lock before the row is written, so a second hook
    waiting on the lock finds nothing left to record. The person who confirmed the run is its
    actor; the reason is never in it."""
    _lock_run(tenant_id, user_id)
    held = cache.get(_key(tenant_id, user_id))
    if not _failing(held, run_id):
        return
    _end_failed(tenant_id, user_id, held)
    counts = {count: held["state"][count] for count in COUNTS}
    _stop(tenant_id, _actor(User.objects.get(pk=user_id)), company_id, counts, FAILED, held["state"]["total"] - sum(counts.values()))


def _why_not(run: _Run) -> str | None:
    """Why the run may not go on, or None while it may: its reason is no longer kept, the
    person is no longer an active member of the bank, their roles no longer hold
    `applicability.approve`, or the company is no longer an active legal entity of the bank.
    Read afresh before every chunk, never from the run's start."""
    if not run.reason:
        return REASON_EXPIRED
    held = api_keys_logic.person_permissions(run.tenant.id, run.user_id)
    if held is None:
        return MEMBERSHIP_ENDED
    if perms.APPLICABILITY_APPROVE not in held:
        return PERMISSION_REVOKED
    company = OrgUnit.objects.filter(pk=run.company_id, kind=OrgUnitKind.LEGAL_ENTITY.value, active=True)
    return None if company.exists() else COMPANY_GONE


def _stop(tenant_id: uuid.UUID, actor: Actor, company_id: uuid.UUID, counts: dict[str, int], why: str, left: int) -> None:
    """One audit row for a run that ends before trying every target: why, what it counted
    (nothing for a replaced run, whose counts went with its state) and how many were left."""
    record(
        action=STOPPED,
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=company_id,
        subject_title=next(iter(OrgUnit.objects.filter(pk=company_id).values_list("name", flat=True)), ""),
        summary=f"Stopped deciding all unanswered obligations with {left} left",
        tenant_id=tenant_id,
        after={"stopped": why, **counts, "left": left},
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
    """Create the rows these targets name that do not exist yet, lock them all, leave those a
    person has answered and those no longer offered for the company, and store the rest
    through `applicability._store`. Every target has a row before its answer is read: a
    colleague's first answer written at the same moment either created the row first (the
    insert here skips it, and the lock waits for the colleague's commit and reads the answer),
    or waits on this chunk's row and lands after it, as a later single answer does."""
    company, targets = company_view.targets_for(tenant=run.tenant, org_unit_id=run.company_id, obligations=Obligation.objects.filter(pk__in=obligation_ids))
    headings = reading.obligation_headings(targets.keys(), run.order)
    status = applicability._default_status()
    with batched():  # the entries it creates are audited in one statement, as the door's are
        entries = ensure_register_entries(tenant_id=run.tenant.id, headings=headings, actor=run.actor, status=status)
    pairs = {(entries[obligation_id].id, company.id) for obligation_id, target in targets.items() if target is not None and obligation_id in entries}
    rows = applicability._new_scopes(run.tenant, pairs, status)
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
