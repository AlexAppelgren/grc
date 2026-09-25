"""Agent runs (AGT-01, AGT-02, ID-10, AUD-01): open a run, close it, read the log of what
ran, and answer the one question every other writer of this chunk asks — is this run of
this key still open?

A run is the provenance anchor. `regulatory_change.agent_run_id`, `source_check.agent_run_id`
and `proposal.agent_run_id` all point here, so every claim an agent files can be traced to
the model, the pipeline and the night that produced it. Nothing here reaches the shared
library: a run is a record of work, and what the work found becomes a proposal a person or
a second, independent agent approves.

Three rules shape the module:

- **Platform-owned in R1** (Alex, 2026-09-19, item 14). bleqq's watch agents are part of
  the base package, so a run belongs to the platform and to no bank. A tenant-bound key is
  refused with `tenant_agents_not_available`, on a run and on every watch write
  (`refuse_tenant_key`), and a person's session never arrives at all:
  the route takes an API key alone. `c5-platform-agent-keys` strips the agent write scopes
  from a bank's keys at creation; this is the second guard, so neither alone is
  load-bearing. Chunk 11 adds a bank's own agents and their runs, and the model's tenant
  column and policies are already shaped for them, so nothing here needs a migration then.
- **A key acts only on its own run.** A run of another key answers 404 and never 403, so a
  run id is not something a key can probe for. What an agent files names the open run it
  was found in (`require_open_run`), so nothing an agent wrote lacks a night to trace to.
- **A retry replays.** The same `Idempotency-Key` answers the run it already opened. A
  close repeated with the same values answers the run it already closed, because what makes
  a close idempotent is the closing values themselves and not a stored key.

Every open and close writes its audit row and its outbox row in the same transaction as the
run, with the agent behind the key as the actor rather than the key's id (ID-10).
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

from apps.agents.models import AgentRun, RunStatus
from apps.agents.schemas import AgentRunFinish, AgentRunInput, AgentRunOut, AgentRunPage, AgentRunStats
from apps.identity.models import ApiKey
from apps.shared.audit import Actor, ActorType, record
from apps.shared.authentication import Principal
from apps.shared.errors import ProblemError

SUBJECT_TYPE = "agent_run"

# The four values `RunStatus` fixes, as the schema publishes them.
RunState = Literal["running", "succeeded", "failed", "interrupted"]


# ---------------------------------------------------------------------------------------
# Reading one run out
# ---------------------------------------------------------------------------------------
def row(run: AgentRun) -> AgentRunOut:
    """One run as every reader sees it. The stored counters are the camelCase shape
    `AgentRunStats` publishes, so what a run filed is what a reader is handed back."""
    return AgentRunOut(
        id=run.id,
        agent=run.agent.key,
        started_at=run.started_at,
        finished_at=run.finished_at,
        # A kind in code (`RunStatus`): the column holds one of its four values and the
        # schema publishes the same four, so the cast states what the choices already fix.
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
    """The counters as the JSON column stores them: camelCase, the shape the schema
    publishes. A close that files none leaves the run's own counters standing, which is the
    honest answer from a run that failed before it could count."""
    if values is None:
        return fallback
    return values.model_dump(mode="json", by_alias=True)


# ---------------------------------------------------------------------------------------
# POST /agent-runs
# ---------------------------------------------------------------------------------------
def _key_for(who: Principal, wanted: str) -> tuple[ApiKey, uuid.UUID]:
    """The calling key and the definition it is bound to.

    A key runs exactly one definition (ID-10), and the principal already carries which one,
    so the name the caller sent is compared against the key's own agent rather than looked
    up. Any mismatch is one refusal: a definition this build does not ship and one that
    belongs to another key are the same answer, so trying names tells a caller nothing about
    which definitions exist. It is also what keeps this module clear of the library fence —
    `agent` is a library record, and the module that writes never names one.
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
    """In R1 every run is a platform run (item 14), so a bank's key opens none and writes
    nothing to the watch: not a run, a source check, a change or anything on one. Every
    such write asks this first, so a bank's key that somehow holds a watch scope is refused
    with its reason named rather than writing the shared library, and the refusal comes
    before any write, so nothing is stored."""
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
    """Route decorator for every run and watch write, placed above its scope gate: a bank's
    key is refused with its reason named before its scopes are read. A bank's key has its
    watch scopes withheld when it is resolved (D-61, D-78), so the scope gate alone would
    answer a bare `permission_denied` and never say why (item 14)."""

    @functools.wraps(view)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
        who = getattr(request, "auth", None)
        if isinstance(who, Principal):
            refuse_tenant_key(who)
        return view(request, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


def open_run(*, who: Principal, body: AgentRunInput, idempotency_key: str | None) -> AgentRunOut:
    """`POST /agent-runs`: open a run for the key's agent and return it.

    A bank's key is refused here as well as at key creation (`refuse_tenant_key`).
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
    """The run this key already opened under this retry key, or None when it is new. The
    same key with a different body is a conflict: keeping either version would lose the
    other, and silently answering the first would hide a caller's bug."""
    # One filter keyword per line. Both keywords on one line read to gitleaks'
    # generic-api-key rule as a key followed by its value, and the secret scan failed on
    # an ORM query (2026-09-20). Allowlisting it would have taught the scanner to ignore
    # the shape a real leak takes, so the line is split instead.
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


# ---------------------------------------------------------------------------------------
# PATCH /agent-runs/{runId}
# ---------------------------------------------------------------------------------------
def _own_run(api_key_id: uuid.UUID | None, run_id: uuid.UUID) -> AgentRun:
    """The run this key opened. Another key's run, and one that never existed, answer the
    same 404: which run ids exist is not something a key may probe for. No key at all (a
    person naming a run) finds nothing, because every run was opened by a key."""
    run = AgentRun.objects.select_related("agent").filter(
        pk=run_id, api_key_id=api_key_id
    ).first()  # ordering: pk lookup inside one key, at most one row
    if run is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    return run


def finish_run(*, who: Principal, run_id: uuid.UUID, body: AgentRunFinish) -> AgentRunOut:
    """`PATCH /agent-runs/{runId}`: close the run into a terminal status and file what it
    counted.

    A run closes once. Repeating the same close answers the run it already closed, so a
    lost answer costs nothing; closing it into something else is refused, so a closed run
    is never quietly reopened or rewritten. A bank's key is refused first, as on opening one.
    """
    refuse_tenant_key(who)
    run = _own_run(who.subject_id, run_id)
    stats = _counted(run, _stats(body.stats, run.stats))
    output_ref = body.output_ref or ""
    error = body.error or ""
    if run.status != RunStatus.RUNNING.value:
        # Both sides as a reader reads them, so a close stored before a counter existed is
        # still the same close when it is sent again: the missing counter reads 0 on both.
        stored = _counted(run, _stats(AgentRunStats.model_validate(run.stats), run.stats))
        sent = _counted(run, _stats(body.stats, stored))
        if (run.status, stored, run.output_ref, run.error) != (body.status, sent, output_ref, error):
            raise ValidationError(
                "This run is already closed, so it cannot be closed again with different values.",
                code="invalid_transition",
            )
        _record_replay(run, who, "A retried close answered the run it already closed.")
        return row(run)
    with transaction.atomic():
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


# ---------------------------------------------------------------------------------------
# The provenance guard the other writers of this chunk ask
# ---------------------------------------------------------------------------------------
def require_open_run(who: Principal, run_id: uuid.UUID | None) -> AgentRun:
    """The open run this key named, for a write that files something against it: a source
    check or a registered change. A bank's key is refused first (`refuse_tenant_key`)."""
    refuse_tenant_key(who)
    return require_open_run_of_key(who.subject_id, run_id)


def require_open_run_of_key(api_key_id: uuid.UUID | None, run_id: uuid.UUID | None) -> AgentRun:
    """The open run of the key `api_key_id`, named as `run_id`; for a proposal, whose
    proposer carries the key rather than the principal.

    Naming no run answers 422 `run_not_open`, and so does a run of this key that is already
    closed, because the caller fixes both the same way, by opening a run and naming it —
    and because a closed run is a finished account of a night's work that nothing may be
    added to afterwards. A run of another key answers 404, exactly as closing one does.
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
    """Refuse one more write under `run` once `filed`, what the run has already filed of this
    kind, reaches `limit` (H41): 422 `run_budget_exhausted`. The budget is the definition's
    (`budget_defaults`), held by the server from a setting, so a runaway or injected run
    cannot flood the queue whatever it believes its budget is.

    Called inside the write's own transaction. It locks the run's row first, so two writes
    under one run count one after the other and never both squeeze past the last slot, and
    a close that landed meanwhile answers `run_not_open`. `what` names the kind, singular
    and plural, for the sentence."""
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
    """The counters as the server counts them from what the run filed, over what the run
    reported of itself (H41): the sources it swept, the records it re-checked, the changes
    it registered and the proposals it filed. What the server cannot see — its model calls,
    its fetches, the documents it set aside and which proposals were corrections — stays
    the run's own account."""
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


# ---------------------------------------------------------------------------------------
# GET /agent-runs
# ---------------------------------------------------------------------------------------
def list_runs(*, limit: int, offset: int) -> AgentRunPage:
    """The runs this caller may see, oldest first, one page at a time.

    Row-level security is what decides "may see": a bank's session reads the library's runs
    and its own, a console session reads the library's, and no session reads another bank's.
    The order is the model's own and is the order the sweeps happened in.
    """
    queryset = AgentRun.objects.select_related("agent").order_by("started_at", "id")
    total = queryset.count()
    return AgentRunPage(items=[row(run) for run in queryset[offset : offset + limit]], total=total)
