"""Agent runs (AGT-01, AGT-02, ID-10, AUD-01): open, close, read the log, and answer "is this
run of this key still open?" for every other writer.

A run is the provenance anchor: changes, source checks and proposals point at it, so every
claim an agent files traces to its model, pipeline and night. A run never reaches the
shared library itself.

- Platform-owned: bleqq's watch agents belong to the platform. A tenant-bound key is refused
  with `tenant_agents_not_available` on a run and every watch write (`refuse_tenant_key`), on
  top of the agent scopes stripped from a bank's keys at creation, so neither guard alone is
  load-bearing. A session never arrives: the route takes an API key alone.
- A key acts only on its own run: another key's is 404, never 403, and every filing names
  the open run it came from (`require_open_run`).
- A retry replays: the same `Idempotency-Key` answers the same run, and a repeated close with
  the same values answers the closed run.

Every open and close audits in the run's transaction, the actor being the key's agent (ID-10).
"""

from __future__ import annotations

import functools
import uuid
from collections.abc import Callable
from typing import Any, Literal, TypeVar, cast

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone

from apps.agents import definitions
from apps.agents.models import AgentRun, RunStatus
from apps.agents.schemas import AgentRunFinish, AgentRunInput, AgentRunOut, AgentRunStats
from apps.identity.models import ApiKey
from apps.shared.audit import Actor, ActorType, record
from apps.shared.authentication import Principal
from apps.shared.errors import ProblemError, not_found

SUBJECT_TYPE = "agent_run"

# The four values `RunStatus` fixes, as the schema publishes them.
RunState = Literal["running", "succeeded", "failed", "interrupted"]


# --- Reading one run out ---
def row(run: AgentRun) -> AgentRunOut:
    """One run as every reader sees it. The stored counters are the camelCase shape
    `AgentRunStats` publishes, so what a run filed is what a reader is handed back."""
    return AgentRunOut(
        id=run.id,
        agent=run.agent.key,
        started_at=run.started_at,
        finished_at=run.finished_at,
        # A kind in code (`RunStatus`); the schema publishes the same values.
        status=cast(RunState, run.status),
        model=run.model,
        pipeline_version=run.pipeline_version,
        stats=AgentRunStats.model_validate(run.stats),
        output_ref=run.output_ref or None,
        error=run.error or None,
    )


def _actor(who: Principal) -> Actor:
    """The agent behind the key, never the key's id (ID-10). A key that reaches a write here
    is always bound to an agent, which is what `_key_for` refuses without."""
    return Actor(kind=ActorType.AGENT, id=who.agent_id, label=who.agent_label)


def _stats(values: AgentRunStats | None, fallback: dict[str, Any]) -> dict[str, Any]:
    """The counters as the JSON column stores them, camelCase. A close that files none leaves
    the run's own counters standing."""
    if values is None:
        return fallback
    return values.model_dump(mode="json", by_alias=True)


# --- POST /agent-runs ---
def _key_for(who: Principal, wanted: str) -> tuple[ApiKey, uuid.UUID]:
    """The calling key and the definition it is bound to (ID-10). The name sent is compared
    with the key's own agent, not looked up, so a missing and a foreign definition get the
    same refusal, and this writing module never names a library record.
    """
    if who.agent_id is None or who.agent_label != wanted:
        raise ProblemError(
            status=403,
            code="permission_denied",
            detail="This key is not entitled to run that agent.",
        )
    key = ApiKey.objects.filter(pk=who.subject_id).first()  # ordering: pk lookup, at most one row
    if key is None:  # pragma: no cover - the principal was resolved from this row a moment ago
        raise ProblemError(status=401, code="unauthenticated", detail="Sign in to continue.")
    return key, who.agent_id


def refuse_tenant_key(who: Principal) -> None:
    """A bank's key opens no run and writes nothing to the watch. Every such write asks this
    first, so a bank key holding a watch scope by mistake is refused by name before any
    write."""
    if who.tenant_id is not None:
        raise ProblemError(
            status=403,
            code="tenant_agents_not_available",
            detail=(
                "Agent runs and what they file belong to the platform. The agents that feed "
                "the shared library are part of the base package, and agents of your own "
                "arrive later."
            ),
        )


F = TypeVar("F", bound=Callable[..., Any])


def refuses_tenant_keys(view: F) -> F:
    """Route decorator for every run and watch write, above its scope gate: a bank's key has
    its watch scopes withheld (D-61, D-78), so the scope gate alone would answer a bare
    `permission_denied`; this names the reason first."""

    @functools.wraps(view)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
        who = getattr(request, "auth", None)
        if isinstance(who, Principal):
            refuse_tenant_key(who)
        return view(request, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


def open_run(*, who: Principal, body: AgentRunInput, idempotency_key: str | None) -> AgentRunOut:
    """`POST /agent-runs`: open a run for the key's agent and return it.

    A bank's key is refused here as well as at key creation (`refuse_tenant_key`). The run
    pins the version it opens with (AGT-06); a later publish never moves it.
    """
    refuse_tenant_key(who)
    key, agent_id = _key_for(who, body.agent)
    if idempotency_key:
        replayed = _replayed_open(key, body, idempotency_key, who)
        if replayed is not None:
            return replayed
    with transaction.atomic():
        run = AgentRun.objects.create(
            agent_id=agent_id,
            # Written once, here: the version this run runs, whatever is published later.
            agent_version_id=definitions.version_to_run(agent_id),
            api_key=key,
            model=body.model,
            pipeline_version=body.pipeline_version,
            idempotency_key=idempotency_key or "",
        )
        record(
            action="agent_run.opened",
            actor=_actor(who),
            subject_type=SUBJECT_TYPE,
            subject_id=run.id,
            subject_title=who.agent_label,
            summary=f"{who.agent_label} opened a run.",
            tenant_id=None,
            after={"agent": who.agent_label, "model": run.model, "pipelineVersion": run.pipeline_version},
        )
    return row(run)


def _replayed_open(
    key: ApiKey, body: AgentRunInput, idempotency_key: str, who: Principal
) -> AgentRunOut | None:
    """The run this key already opened under this retry key, or None. The same key with a
    different body is a conflict."""
    # One filter keyword per line: on one line gitleaks' generic-api-key rule reads them as a
    # key and its value, and allowlisting that shape would hide a real leak.
    existing = (
        AgentRun.objects.select_related("agent")
        .filter(
            api_key=key,
            idempotency_key=idempotency_key,
        )
        .first()  # ordering: (api_key, idempotency_key) is unique, at most one row
    )
    if existing is None:
        return None
    if (existing.model, existing.pipeline_version) != (body.model, body.pipeline_version):
        raise ValidationError(
            "This Idempotency-Key was already used to open a different run.",
            code="idempotency_conflict",
        )
    _record_replay(existing, who, "A retried open answered the run it already opened.")
    return row(existing)


def _record_replay(run: AgentRun, who: Principal, summary: str) -> None:
    with transaction.atomic():
        record(
            action="agent_run.replayed",
            actor=_actor(who),
            subject_type=SUBJECT_TYPE,
            subject_id=run.id,
            subject_title=run.agent.key,
            summary=summary,
            tenant_id=None,
            after={"status": run.status},
        )


# --- PATCH /agent-runs/{runId} ---
def _own_run(api_key_id: uuid.UUID | None, run_id: uuid.UUID) -> AgentRun:
    """The run this key opened, locked until the caller's transaction ends (H36). Another
    key's run and an unknown one are the same 404. A keyless (scheduler or request) run is
    never found by a person: `refuse_person_run` comes first. The lock keeps the status true
    for the whole write, so a close counts a filing in flight; only the run's row is locked."""
    run = (
        AgentRun.objects.select_related("agent")
        .select_for_update(of=("self",))
        .filter(pk=run_id, api_key_id=api_key_id)
        .first()  # ordering: pk lookup inside one key, at most one row
    )
    if run is None:
        raise not_found()
    return run


def finish_run(*, who: Principal, run_id: uuid.UUID, body: AgentRunFinish) -> AgentRunOut:
    """`PATCH /agent-runs/{runId}`: close the run into a terminal status and file its counts.
    Closes once: the same close again answers the closed run; a different one is refused. A
    bank's key is refused first.
    """
    refuse_tenant_key(who)
    with transaction.atomic():
        return _close(who, _own_run(who.subject_id, run_id), body)


def _close(who: Principal, run: AgentRun, body: AgentRunFinish) -> AgentRunOut:
    """`finish_run` once the run's row is locked (H36): a second close waits here and reads
    the first one's status, and the counts include every filing that committed first."""
    stats = _counted(run, _stats(body.stats, run.stats))
    output_ref = body.output_ref or ""
    error = body.error or ""
    if run.status != RunStatus.RUNNING.value:
        # Both sides as a reader reads them, so a counter added later reads 0 on both.
        stored = _counted(run, _stats(AgentRunStats.model_validate(run.stats), run.stats))
        sent = _counted(run, _stats(body.stats, stored))
        if (run.status, stored, run.output_ref, run.error) != (body.status, sent, output_ref, error):
            raise ValidationError(
                "This run is already closed, so it cannot be closed again with different values.",
                code="invalid_transition",
            )
        _record_replay(run, who, "A retried close answered the run it already closed.")
        return row(run)
    run.status = body.status
    run.stats = stats
    run.output_ref = output_ref
    run.error = error
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "stats", "output_ref", "error", "finished_at"])
    record(
        action="agent_run.closed",
        actor=_actor(who),
        subject_type=SUBJECT_TYPE,
        subject_id=run.id,
        subject_title=run.agent.key,
        summary=f"{run.agent.key} closed a run: {run.status}.",
        tenant_id=None,
        before={"status": RunStatus.RUNNING.value},
        after={"status": run.status, "stats": run.stats},
    )
    return row(run)


# --- The provenance guard the other writers ask ---
def require_open_run(who: Principal, run_id: uuid.UUID | None) -> AgentRun:
    """The open run this key named, for a write that files something against it: a source
    check or a registered change. A bank's key is refused first (`refuse_tenant_key`)."""
    refuse_tenant_key(who)
    return require_open_run_of_key(who.subject_id, run_id)


def refuse_person_run(person: Any, run_id: uuid.UUID | None) -> None:
    """A person files under no agent run: `_own_run` would find a keyless run for a proposer
    with no key, and their work would read as the agent's. Answers the same 404 as another
    key's run."""
    if person is not None and run_id is not None:
        raise not_found()


def require_open_run_of_key(api_key_id: uuid.UUID | None, run_id: uuid.UUID | None) -> AgentRun:
    """The open run of key `api_key_id` named as `run_id`, for a proposal, whose proposer
    carries the key. Locked until the write's transaction ends (H36), so the following close
    counts it. No run, or a closed one, is 422 `run_not_open`; another key's run is 404.
    """
    if run_id is None:
        raise ValidationError(
            "Name the open run this is filed under in agentRunId. Open one with POST /agent-runs first.",
            code="run_not_open",
        )
    run = _own_run(api_key_id, run_id)
    if run.status != RunStatus.RUNNING.value:
        raise ValidationError(
            "That run is closed. Open a run before filing anything against it.",
            code="run_not_open",
        )
    return run


def spend(run: AgentRun, filed: QuerySet[Any], *, limit: int, what: tuple[str, str]) -> None:
    """Refuse one more write under `run` once `filed` reaches `limit` (H41): 422
    `run_budget_exhausted`. The budget is a server setting, so a runaway or injected run
    cannot flood the queue. Locks the run's row first, so two writes cannot both take the last
    slot and a close meanwhile answers `run_not_open`. `what` names the kind for the sentence."""
    status = AgentRun.objects.select_for_update().filter(pk=run.pk).values_list("status", flat=True).first()  # ordering: pk lookup
    if status != RunStatus.RUNNING.value:
        raise ValidationError(
            "That run is closed. Open a run before filing anything against it.",
            code="run_not_open",
        )
    if filed.count() >= limit:
        raise ValidationError(
            f"This run has filed its {limit} {what[0] if limit == 1 else what[1]}, the most one run may file. "
            "Close it, and a new run files the rest.",
            code="run_budget_exhausted",
        )


def _counted(run: AgentRun, stats: dict[str, Any]) -> dict[str, Any]:
    """The counters the server can count from what the run filed (H41), over what it
    reported; the rest stays the run's own account."""
    from apps.proposals.models import Proposal
    from apps.watch.models import SourceCheckKind

    checks = run.source_checks.all()
    return {
        **stats,
        "sourcesChecked": checks.filter(kind=SourceCheckKind.SWEEP.value).values("source_id").distinct().count(),
        "recordsRechecked": checks.filter(kind=SourceCheckKind.RECHECK.value).values("subject_type", "subject_id").distinct().count(),
        "changesRegistered": run.changes.count(),
        "proposalsSubmitted": Proposal.objects.filter(agent_run_id=run.id).count(),
    }
