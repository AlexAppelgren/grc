"""Routes of the agents app: auth class, permission or scope, step-up where playbook 4.2
lists the action, no business logic (playbook 4.1).

bleqq's agents are platform-owned and platform-run (Alex, 2026-09-19, item 14), and the
gates say so: the two run writes take `ApiKeyAuth` alone, so no session — tenant or
platform — opens or closes a run, and the run log takes `SessionAuth` alone, so no key
reads it. Which key may open a run is the logic's own refusal, in `runs.py:open_run`.

Every write carries `Idempotency-Key`: an agent retries, and a retry must return the run
it already opened rather than a second one (AGT-01).

Each route's docstring is its published `description` (django-ninja reads it), written for
an integrator at a bank who has never seen this codebase. The standard is
`docs/plans/briefs/API_DOCUMENTATION.md`.
"""

import uuid
from typing import Any

from django.http import HttpRequest
from ninja import Header, Path, Query, Router

from apps.agents import runs
from apps.agents.schemas import AgentRunFinish, AgentRunInput, AgentRunOut, AgentRunPage
from apps.shared import permissions as perms
from apps.shared.authentication import ApiKeyAuth, SessionAuth
from apps.shared.permissions import requires_scope
from apps.shared.schemas import PageQuery
from apps.taxonomy.http import answers_problems, principal, require_any

router = Router(tags=["Agents"])

KEY = ApiKeyAuth()
SESSION = SessionAuth()
IdempotencyKey = Header(
    None,
    alias="Idempotency-Key",
    description=(
        "The retry key for this write, chosen by the caller and unique to the API key making "
        "it; a UUID is the usual choice. Send the same key again when you cannot tell whether "
        "a call landed and the server replays what that key already did instead of doing the "
        "work twice — a retried open returns the run it already opened rather than a second "
        "one. Send a new key for genuinely new work. Reusing a key with a different body is a "
        "conflict and is refused with a 409 rather than silently accepted. It is optional in "
        "the schema so that a caller cannot be locked out by a lost key, but an agent always "
        "sends one: without it a retry cannot be recognised."
    ),
)


@router.post(
    "/agent-runs",
    response={201: AgentRunOut},
    auth=KEY,
    operation_id="startAgentRun",
    by_alias=True,
    summary="Open a run so everything the agent files can be traced to it",
)
@requires_scope(perms.SCOPE_AGENT_RUNS_WRITE)
@answers_problems
def start_agent_run(
    request: HttpRequest, body: AgentRunInput, idempotency_key: str | None = IdempotencyKey
) -> Any:
    """The first call of every execution. It opens a run and returns its identifier, which
    every later call in the same execution carries, so each change, proposal and source
    check the agent files can be traced back to the model, the pipeline and the night that
    produced it. Call it once, before any other work; close it with `PATCH /agent-runs/{runId}`
    even when the run failed.

    Authenticated by an API key alone — no session, tenant or platform, can open a run —
    and the key must carry the `agent-runs:write` scope. The run belongs to whatever the
    key belongs to and never to anything else: the platform's own key opens the library
    runs that feed the shared inventory, a bank's key opens runs in that bank's zone, and
    any other pairing is refused. No key scope of any kind reaches the shared library:
    what an agent finds becomes a proposal or a private record, never a library edit, so
    opening a run grants nothing beyond the right to file work for review.

    Send `Idempotency-Key`. A retry with the same key returns the run that key already
    opened; without one a lost answer becomes a duplicate run and a duplicated night's
    findings. Opening a run is recorded in the audit log with the agent behind the key
    named, not the key's identifier.

    Answers 201 with the open run, its status `running` and its counters at zero. A replay
    answers 201 with the run that key already opened. Errors: `tenant_agents_not_available`
    when the key belongs to a bank rather than to the platform, because in this release the
    agents that feed the shared library are part of the base package and a bank opens no run
    of its own; `permission_denied` when the key lacks `agent-runs:write`, or when `agent`
    is not the definition this key is bound to — a key runs exactly one definition, so a
    name this build does not ship and a name that belongs to another key are the same
    refusal, and trying names tells a caller nothing about which definitions exist;
    `unauthenticated` when the key is missing, revoked or expired; `idempotency_conflict`
    when the same `Idempotency-Key` is sent with a different body; and `validation_error`
    for a field the caller can fix.
    """
    return runs.open_run(who=principal(request), body=body, idempotency_key=idempotency_key)


@router.patch(
    "/agent-runs/{run_id}",
    response=AgentRunOut,
    auth=KEY,
    operation_id="finishAgentRun",
    by_alias=True,
    summary="Close a run and file what it did",
)
@requires_scope(perms.SCOPE_AGENT_RUNS_WRITE)
@answers_problems
def finish_agent_run(
    request: HttpRequest,
    body: AgentRunFinish,
    run_id: uuid.UUID = Path(
        ...,
        description=(
            "The identifier of the run to close: the UUID that opening the run returned. It "
            "must be a run this same API key opened — another key's run answers `not_found` "
            "rather than saying it exists."
        ),
    ),
    idempotency_key: str | None = IdempotencyKey,
) -> Any:
    """The last call of every execution, made whether the run worked or not. It closes the
    run into `succeeded` or `failed`, files the counters for the budgets in the agent's
    definition, and records where the working output was kept. A run that is never closed
    stays open for ever and reads as stuck, so close it from the failure path too.

    Authenticated by the API key that opened the run, carrying the `agent-runs:write`
    scope; no session can close a run. A run closes once and into a terminal status. Sending
    the same close again answers the run it already closed, so a lost answer costs nothing;
    closing it into anything else is refused rather than quietly reopening or rewriting it.
    That is what makes the close idempotent, so `Idempotency-Key` is accepted on this call
    but nothing depends on it. What the agent filed while the run was open stands whichever
    status it ends in, and none of it has changed the shared library: a proposal waits for a
    person, or for a second and independent agent, to approve it. The close is recorded in
    the audit log against the agent behind the key.

    Answers 200 with the closed run. Errors: `not_found` when no such run exists or it
    belongs to another key, which are deliberately the same answer so that a run id cannot
    be probed for; `invalid_transition` when the run is already closed and the values sent
    differ from the ones it closed with; `permission_denied` when the key lacks
    `agent-runs:write`; `unauthenticated` when the key is missing, revoked or expired; and
    `validation_error` for a field the caller can fix, such as an error message over its
    length.
    """
    return runs.finish_run(who=principal(request), run_id=run_id, body=body)


@router.get(
    "/agent-runs",
    response=AgentRunPage,
    auth=SESSION,
    operation_id="listAgentRuns",
    by_alias=True,
    summary="Read what the agents have been doing",
)
@answers_problems
def list_agent_runs(request: HttpRequest, page: Query[PageQuery]) -> Any:
    """Returns the agent runs the caller may see, oldest first, one page at a time: when
    each ran, which agent and which model, how it ended, and what it counted. Call it to
    show a bank that its watch is alive — that its sources were swept last night, and what
    came of it — and to investigate a run whose findings are being questioned.

    A person's session only; an API key cannot read this, so an agent cannot read its own
    history. Inside a bank it needs `agents.manage`, in the platform console
    `system.health`; a member with neither is refused. A bank sees the platform's own
    library runs, because those are what feed the shared inventory it relies on, and its
    own runs. It never sees another bank's runs, and no run of any bank is visible to
    another.

    bleqq's own agents are part of the base package: a bank reads their history here but
    cannot switch one off, pause it, or change its cadence, scope or budget. A bank's own
    agents, which it does control, appear in the same list. It changes nothing and writes
    nothing to the audit log. An empty list is a 200 with `total` 0 and means nothing has
    run yet, not that something is wrong.

    Errors: `validation_error` when `limit` is above 100 or `offset` beyond the accepted
    depth; `permission_denied` with neither `agents.manage` nor `system.health`;
    `unauthenticated` without a session.
    """
    # Ungated by design: logic-gate (agents.manage in a tenant, or system.health in the console).
    require_any(request, perms.AGENTS_MANAGE, perms.SYSTEM_HEALTH)
    return runs.list_runs(limit=page.limit, offset=page.offset)
