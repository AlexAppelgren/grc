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

from apps.agents import budget, control, definitions, platform, platform_read, requests, runs, runs_read, tenant_agents
from apps.agents.schemas import (
    AgentBudget,
    AgentBudgetInput,
    AgentDefinitionDetail,
    AgentDefinitionPage,
    AgentRunFinish,
    AgentRunInput,
    AgentRunListItem,
    AgentRunListPage,
    AgentRunOut,
    AgentVersionInput,
    AgentVersionOut,
    PlatformAgentSettings,
    PlatformAgentSettingsInput,
    PlatformWatchPage,
    ResearchRequestInput,
    ResearchRequestOut,
    ResearchRequestPage,
    RetagRequestInput,
    TenantAgentInput,
    TenantAgentOut,
    TenantAgentPage,
    TenantAgentUpdate,
    TenantRunQuery,
)
from apps.shared import permissions as perms
from apps.shared.authentication import ApiKeyAuth, SessionAuth
from apps.shared.permissions import requires_permission, requires_scope, requires_step_up
from apps.shared.schemas import PageQuery
from apps.taxonomy.http import answers_problems, caller_tenant, principal, require_any

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
@runs.refuses_tenant_keys
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
    and the key must carry the `agent-runs:write` scope, which only a platform key bound to
    an agent definition can hold: in this release the agents that feed the shared library
    are part of the base package, so a bank opens no run of its own and its key is never
    given the scope. The run belongs to the platform. No key scope of any kind reaches the
    shared library: what an agent finds becomes a proposal or a private record, never a
    library edit, so opening a run grants nothing beyond the right to file work for review.

    Send `Idempotency-Key`. A retry with the same key returns the run that key already
    opened; without one a lost answer becomes a duplicate run and a duplicated night's
    findings. Opening a run is recorded in the audit log with the agent behind the key
    named, not the key's identifier.

    Answers 201 with the open run, its status `running` and its counters at zero. A replay
    answers 201 with the run that key already opened. Errors: `tenant_agents_not_available`
    when the key belongs to a bank, whatever scopes it was once given, since a bank opens no
    run in this release; `permission_denied` when the key lacks `agent-runs:write`, or when
    `agent` is not the definition this key is bound to — a key runs exactly one definition, so a
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
@runs.refuses_tenant_keys
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

    Among the counters is `outOfScope`: the documents the run read and set aside because
    they fall outside regulated financial services. Such a document is counted on its
    source's check and here, and nothing else — no change, no proposal — so this count is
    the only trace of it and the way a reader tells a quiet night from a night of documents
    that were not ours to watch.

    What the server can see for itself it counts as the run closes, and those numbers are
    the ones kept: `sourcesChecked`, `changesRegistered`, `proposalsSubmitted` and
    `recordsRechecked` are read from what the run filed, whatever the close sends. The
    other counters are the run's own account.

    Authenticated by the API key that opened the run, carrying the `agent-runs:write`
    scope; no session can close a run. A run closes once and into a terminal status. Sending
    the same close again answers the run it already closed, so a lost answer costs nothing;
    closing it into anything else is refused rather than quietly reopening or rewriting it.
    That is what makes the close idempotent, so `Idempotency-Key` is accepted on this call
    but nothing depends on it. What the agent filed while the run was open stands whichever
    status it ends in, and none of it has changed the shared library: a proposal waits for a
    person, or for a second and independent agent, to approve it. The close is recorded in
    the audit log against the agent behind the key.

    Answers 200 with the closed run. Errors: `tenant_agents_not_available` when the key
    belongs to a bank rather than to the platform, since a bank opens no run in this
    release; `not_found` when no such run exists or it belongs to another key, which are deliberately the same answer so that a run id cannot
    be probed for; `invalid_transition` when the run is already closed and the values sent
    differ from the ones it closed with; `permission_denied` when the key lacks
    `agent-runs:write`; `unauthenticated` when the key is missing, revoked or expired; and
    `validation_error` for a field the caller can fix, such as an error message over its
    length.
    """
    return runs.finish_run(who=principal(request), run_id=run_id, body=body)


@router.get(
    "/agent-runs",
    response=AgentRunListPage,
    auth=SESSION,
    operation_id="listAgentRuns",
    by_alias=True,
    summary="Read what the agents have been doing",
)
@answers_problems
def list_agent_runs(request: HttpRequest, query: Query[TenantRunQuery]) -> Any:
    """Returns the agent runs the caller may see, oldest first, one page at a time: when
    each ran, which agent, which version and which model, what started it and who asked,
    how it ended, what it counted and what it cost. Call it to show a bank what its own
    agents did, the history of one of them with `tenantAgentId`, the runs a person asked for
    with `mine`, and to investigate a run whose findings are being questioned.

    A person's session only; an API key cannot read this, so an agent cannot read its own
    history. Inside a bank it needs `agents.manage`, in the platform console
    `system.health`; a member with neither is refused. A bank sees its own runs only; the
    console sees the runs of bleqq's own agents. No bank sees another bank's runs or the
    runs of bleqq's agents, which are part of the base package and listed in the console;
    what bleqq watches is `GET /agents/platform`. The two filters only narrow that, and
    naming another bank's agent matches no run rather than answering an error.

    It changes nothing and writes nothing to the audit log. An empty list is a 200 with `total` 0 and means nothing has
    run yet, not that something is wrong.

    Errors: `validation_error` when `limit` is above 100, `offset` beyond the accepted
    depth or `tenantAgentId` is not a UUID; `permission_denied` with neither
    `agents.manage` nor `system.health`; `unauthenticated` without a session.
    """
    # Ungated by design: logic-gate (agents.manage in a tenant, or system.health in the console).
    who = require_any(request, perms.AGENTS_MANAGE, perms.SYSTEM_HEALTH)
    return runs_read.list_runs(who=who, query=query)


# ---------------------------------------------------------------------------------------
# The platform's agent definitions (ID-10, AGT-01, AGT-03): what a platform
# administrator binds an agent key to, and, from chunk 11, their versions and settings.
# ---------------------------------------------------------------------------------------
@router.get(
    "/agent-definitions",
    response=AgentDefinitionPage,
    auth=SESSION,
    operation_id="listAgentDefinitions",
    by_alias=True,
    summary="See which agents the platform ships, to bind a key to one",
)
@requires_permission(perms.AGENT_DEFINITIONS_MANAGE)
def list_agent_definitions(request: HttpRequest, page: Query[PageQuery]) -> AgentDefinitionPage:
    """Returns the platform's agent definitions, ordered by key, one page at a time: each
    one's identifier, stable key, what it does, the version this build loaded and whether
    it is released, whether it is one of bleqq's agents or one a bank may add as its own,
    and when its current version was published. Call it from the platform console before
    creating an agent key, to pick the agent the key will act as (`POST /agent-keys` takes
    the `id` as `agentId`), and to find the definition whose versions and settings to open.

    A person's session only, holding the platform permission `agent_definitions.manage`,
    which only a platform administrator holds; no session inside a bank and no API key can
    read it. The definitions are the platform's own versioned files, loaded on deploy, and
    this call only reads them: it changes nothing and writes nothing to the audit log. An
    empty list is a 200 with `total` 0.

    Errors: `validation_error` when `limit` is above 100 or `offset` beyond the accepted
    depth; `permission_denied` without `agent_definitions.manage`; `unauthenticated`
    without a session.
    """
    return definitions.list_definitions(limit=page.limit, offset=page.offset)


_AGENT_KEY = (
    "The stable key of one of the platform's agent definitions, such as `watch-sweeper`, as "
    "`GET /agent-definitions` lists it. A key never changes; a new version keeps it."
)


@router.get(
    "/agent-definitions/{agent_key}",
    response=AgentDefinitionDetail,
    auth=SESSION,
    operation_id="getAgentDefinition",
    by_alias=True,
    summary="Open one agent definition with every version it has published",
)
@requires_permission(perms.AGENT_DEFINITIONS_MANAGE)
@answers_problems
def get_agent_definition(request: HttpRequest, agent_key: str = Path(..., description=_AGENT_KEY)) -> Any:
    """Returns one definition as the list shows it, with every version it has published,
    newest first and retired ones included, so the console can show which version each past
    run used and publish or retire the next one.

    A person's session in the platform console holding `agent_definitions.manage`; no
    session inside a bank and no API key reaches a definition, in any release (AGT-03). It
    reads and writes nothing to the audit log.

    Errors: `unauthenticated` (401) without a session; `permission_denied` (403) without
    `agent_definitions.manage`; `not_found` (404) for a key no definition has.
    """
    return definitions.get_definition(agent_key=agent_key)


@router.post(
    "/agent-definitions/{agent_key}/versions",
    response={201: AgentVersionOut},
    auth=SESSION,
    operation_id="publishAgentVersion",
    by_alias=True,
    summary="Publish a new version of one of the platform's agents",
)
@requires_permission(perms.AGENT_DEFINITIONS_MANAGE)
@requires_step_up
@answers_problems
def publish_agent_version(
    request: HttpRequest, body: AgentVersionInput, agent_key: str = Path(..., description=_AGENT_KEY)
) -> Any:
    """Publishes the version folder this build ships for the definition, with a note of
    what changed. Runs opened from now on run it; a run already open keeps the version it
    opened with, and every earlier run still names the version it used. The prompt, tools
    and model come from the shipped folder and never from this request.

    A person's session in the platform console holding `agent_definitions.manage`, with a
    fresh passkey step-up, because a new version changes what runs for every bank at once.
    Records one audit event naming the person, the definition, the version and the
    assertion.

    Errors: `unauthenticated` (401); `permission_denied` (403) without
    `agent_definitions.manage`; `step_up_required` (403) without a fresh passkey assertion;
    `not_found` (404) for a key no definition has; `validation_error` (422) for a version
    number the build does not ship or a missing note. Published ahead of the logic that
    will fill it, and answering 501 `not_built` until that ships.
    """
    return definitions.publish_version(who=principal(request), agent_key=agent_key, body=body)


@router.post(
    "/agent-definitions/{agent_key}/versions/{version_no}/retire",
    response=AgentVersionOut,
    auth=SESSION,
    operation_id="retireAgentVersion",
    by_alias=True,
    summary="Retire a version so no new run starts on it",
)
@requires_permission(perms.AGENT_DEFINITIONS_MANAGE)
@requires_step_up
@answers_problems
def retire_agent_version(
    request: HttpRequest,
    agent_key: str = Path(..., description=_AGENT_KEY),
    version_no: int = Path(..., description="The number of the version to retire, counting from 1 within its definition."),
) -> Any:
    """Retires one published version: no new run starts on it, and every run that used it
    keeps pointing at it, because a published version is never rewritten or deleted.

    A person's session in the platform console holding `agent_definitions.manage`, with a
    fresh passkey step-up. Records one audit event naming the person, the version and the
    assertion.

    Errors: `unauthenticated` (401); `permission_denied` (403) without
    `agent_definitions.manage`; `step_up_required` (403) without a fresh passkey assertion;
    `not_found` (404) for a definition or version that does not exist. Published ahead of
    the logic that will fill it, and answering 501 `not_built` until that ships.
    """
    return definitions.retire_version(who=principal(request), agent_key=agent_key, version_no=version_no)


@router.get(
    "/agent-definitions/{agent_key}/settings",
    response=PlatformAgentSettings,
    auth=SESSION,
    operation_id="getPlatformAgentSettings",
    by_alias=True,
    summary="See how often one of bleqq's agents runs, where it looks and its budget",
)
@requires_permission(perms.AGENT_DEFINITIONS_MANAGE)
@answers_problems
def get_platform_agent_settings(request: HttpRequest, agent_key: str = Path(..., description=_AGENT_KEY)) -> Any:
    """Returns the settings one of bleqq's own agents runs with: its cadence, the
    jurisdictions it sweeps and its monthly budget. They are the same for every bank and
    carry no bank's figure.

    A person's session in the platform console holding `agent_definitions.manage`. It
    reads and writes nothing to the audit log.

    Errors: `unauthenticated` (401); `permission_denied` (403) without
    `agent_definitions.manage`; `not_found` (404) for a key no platform agent has,
    including a definition a bank adds for itself, which has no platform settings. An
    empty `jurisdictions` list means none has been set.
    """
    return platform.get_settings(agent_key=agent_key)


@router.put(
    "/agent-definitions/{agent_key}/settings",
    response=PlatformAgentSettings,
    auth=SESSION,
    operation_id="updatePlatformAgentSettings",
    by_alias=True,
    summary="Change how one of bleqq's agents runs, for every bank",
)
@requires_permission(perms.AGENT_DEFINITIONS_MANAGE)
@requires_step_up
@answers_problems
def update_platform_agent_settings(
    request: HttpRequest, body: PlatformAgentSettingsInput, agent_key: str = Path(..., description=_AGENT_KEY)
) -> Any:
    """Replaces the cadence, jurisdictions and monthly budget of one of bleqq's own agents.
    The change applies to every bank at once, which is why no bank can make it.

    A person's session in the platform console holding `agent_definitions.manage`, with a
    fresh passkey step-up. Records one audit event with the settings before and after, the
    person and the assertion, and no bank.

    Errors: `unauthenticated` (401); `permission_denied` (403) without
    `agent_definitions.manage`; `step_up_required` (403) without a fresh passkey assertion;
    `not_found` (404) for a key no platform agent has; `unknown_key` (422) for a
    jurisdiction the vocabulary does not hold, with the valid keys; `validation_error`
    (422). Published ahead of the logic that will fill it, and answering 501 `not_built`
    until that ships.
    """
    return platform.update_settings(who=principal(request), agent_key=agent_key, body=body)


@router.get(
    "/console/agent-runs",
    response=AgentRunListPage,
    auth=SESSION,
    operation_id="listPlatformRuns",
    by_alias=True,
    summary="Read what bleqq's own agents have been doing",
)
@requires_permission(perms.AGENT_DEFINITIONS_MANAGE)
@answers_problems
def list_platform_runs(request: HttpRequest, page: Query[PageQuery]) -> Any:
    """Returns the runs of bleqq's own agents, newest first, one page at a time, with the
    version each ran, what it cost, how it ended and what it filed: the sources it swept
    and the records it re-checked, counted from the coverage log, and the changes and
    proposals it filed, counted from those records rather than from the run's own report.
    A platform run reads no bank's row, so no bank's run, name or figure is in it, and
    `tenantAgentId` is always null here. Link a run's sources to the console's Sources
    page.

    A person's session in the platform console holding `agent_definitions.manage`. It reads
    and writes nothing to the audit log. An empty list is a 200 with `total` 0.

    Errors: `unauthenticated` (401); `permission_denied` (403) without
    `agent_definitions.manage`; `validation_error` (422) when `limit` is above 100 or
    `offset` beyond the accepted depth.
    """
    return platform.list_runs(limit=page.limit, offset=page.offset)


@router.post(
    "/console/research-requests",
    response={202: ResearchRequestOut},
    auth=SESSION,
    operation_id="createRetagRequest",
    by_alias=True,
    summary="Ask for library records to be re-tagged, as a batch to review",
)
@requires_permission(perms.PROPOSALS_REVIEW)
@answers_problems
def create_retag_request(request: HttpRequest, body: RetagRequestInput) -> Any:
    """Asks bleqq's agents to re-tag library records, such as "re-tag custody records with
    Client money". The answer is one batch proposal with a before-and-after preview,
    decided in the queue like any proposal; nothing in the library changes until an
    independent reviewer approves it. The request itself is a job: read its status later.

    A person's session in the platform console holding `proposals.review`; a bank asks its
    own agents with `POST /research-requests` and never re-tags the library. Records one
    audit event naming the person.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `proposals.review`;
    `validation_error` (422) for a topic that is empty or too long. Published ahead of the
    logic that will fill it, and answering 501 `not_built` until that ships.
    """
    return requests.create_retag(who=principal(request), body=body)


# ---------------------------------------------------------------------------------------
# A bank's own agents (AGT-04, AGT-05, ADR 0053): a person's session in the bank holding
# `agents.manage`, never a key. What bleqq watches is every member's read (`watch.read`).
# Every route that names a record loads it under row-level security first, so another
# bank's record is not found, and fences one of bleqq's agents with 403.
# ---------------------------------------------------------------------------------------
_TENANT_AGENT_ID = "One of the bank's own agents, as a UUID. Another bank's agent answers 404, never 403."


@router.get(
    "/agents/platform",
    response=PlatformWatchPage,
    auth=SESSION,
    operation_id="listPlatformWatch",
    by_alias=True,
    summary="See what bleqq's own agents watch for every bank",
)
@requires_permission(perms.WATCH_READ)
@answers_problems
def list_platform_watch(request: HttpRequest, page: Query[PageQuery]) -> Any:
    """Returns bleqq's own agents, read-only: each one's name, purpose, the jurisdictions it
    sweeps, its cadence, when it next runs and how its last run ended. They are the base
    package, the same for every bank, and keep running when a bank switches its own AI
    features off, because they read public sources only. Nothing else about them is here:
    no prompt, tool, model, version, budget, cost or finding.

    A person's session in a bank holding `watch.read`, which every member has; no API key.
    It reads and writes nothing to the audit log.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `watch.read`;
    `validation_error` (422) when `limit` is above 100. Published ahead of the logic that
    will fill it, and answering 501 `not_built` until that ships.
    """
    return platform_read.list_platform_watch(limit=page.limit, offset=page.offset)


@router.get(
    "/agents",
    response=TenantAgentPage,
    auth=SESSION,
    operation_id="listTenantAgents",
    by_alias=True,
    summary="See the agents your bank added for itself",
)
@requires_permission(perms.AGENTS_MANAGE)
@answers_problems
def list_tenant_agents(request: HttpRequest, page: Query[PageQuery]) -> Any:
    """Returns the agents the bank added for itself, with each one's switch, cadence, scope,
    next run and pause. bleqq's agents are not here: `GET /agents/platform` shows them.

    A person's session in a bank holding `agents.manage`; no API key. It reads and writes
    nothing to the audit log. An empty list is a 200 and means the bank has added none.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `agents.manage`;
    `validation_error` (422) when `limit` is above 100.
    """
    tenant = caller_tenant(request)
    return tenant_agents.list_tenant_agents(tenant=tenant, limit=page.limit, offset=page.offset)


@router.post(
    "/agents",
    response={201: TenantAgentOut},
    auth=SESSION,
    operation_id="createTenantAgent",
    by_alias=True,
    summary="Add an agent of your bank's own",
)
@requires_permission(perms.AGENTS_MANAGE)
@answers_problems
def create_tenant_agent(request: HttpRequest, body: TenantAgentInput) -> Any:
    """Adds an agent of the bank's own from a definition bleqq offers banks, with its
    cadence and scope; it starts switched off. What it finds stays in the bank's own zone:
    it never writes the shared library. The plan limits are the most frequent cadence and
    how many agents of its own a bank may add.

    A person's session in a bank holding `agents.manage`; no API key. Records one audit
    event naming the person and the definition.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `agents.manage`, or
    naming `agent_definitions.manage` when the definition is one of bleqq's own agents,
    which no bank adds or steers; `unknown_key` (422) for a definition key that does not
    exist, or a scope key the vocabulary does not hold, with the valid keys in `validKeys`;
    `above_plan_limit` (422) for a cadence more frequent than the plan allows, or one agent
    more than it allows; `duplicate_key` (409) when the bank has already added this
    definition; `validation_error` (422).
    """
    tenant = caller_tenant(request)
    return 201, tenant_agents.create_tenant_agent(who=principal(request), tenant=tenant, body=body)


@router.patch(
    "/agents/{tenant_agent_id}",
    response=TenantAgentOut,
    auth=SESSION,
    operation_id="updateTenantAgent",
    by_alias=True,
    summary="Switch your bank's agent on or off, or change its cadence or scope",
)
@requires_permission(perms.AGENTS_MANAGE)
@answers_problems
def update_tenant_agent(
    request: HttpRequest, body: TenantAgentUpdate, tenant_agent_id: uuid.UUID = Path(..., description=_TENANT_AGENT_ID)
) -> Any:
    """Changes what the body sends on one of the bank's own agents: its switch, cadence,
    run day and hour, or scope, and nothing else. Its instructions and tools are never the
    bank's to change. Switching an agent on needs the bank's monthly cap to be set first.

    A person's session in a bank holding `agents.manage`; no API key. Records one audit
    event with the fields before and after.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `agents.manage`;
    `not_found` (404) for an agent the bank does not have; `unknown_key` (422) for a scope
    key the vocabulary does not hold, with the valid keys in `validKeys`; `above_plan_limit`
    (422) for a cadence more frequent than the plan allows; `budget_cap_required` (422) when
    switching on before the bank has set its monthly cap; `validation_error` (422).
    """
    tenant = caller_tenant(request)
    return tenant_agents.update_tenant_agent(who=principal(request), tenant=tenant, tenant_agent_id=tenant_agent_id, body=body)


@router.post(
    "/agents/{tenant_agent_id}/runs",
    response={202: AgentRunListItem},
    auth=SESSION,
    operation_id="runTenantAgentNow",
    by_alias=True,
    summary="Run your bank's agent now",
)
@requires_permission(perms.AGENTS_MANAGE)
@answers_problems
def run_tenant_agent_now(request: HttpRequest, tenant_agent_id: uuid.UUID = Path(..., description=_TENANT_AGENT_ID)) -> Any:
    """Queues one run of the bank's own agent now, outside its cadence, and returns it; the
    run is a job, so follow it in `GET /agent-runs`. It counts against the bank's monthly
    cap like any other run.

    A person's session in a bank holding `agents.manage`; no API key. Records one audit
    event naming the person.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `agents.manage`;
    `not_found` (404) for an agent the bank does not have. Published ahead of the logic that
    will fill it, and answering 501 `not_built` until that ships.
    """
    tenant = caller_tenant(request)
    return control.run_now(who=principal(request), tenant=tenant, tenant_agent_id=tenant_agent_id)


@router.post(
    "/agents/{tenant_agent_id}/pause",
    response=TenantAgentOut,
    auth=SESSION,
    operation_id="pauseTenantAgent",
    by_alias=True,
    summary="Pause your bank's agent",
)
@requires_permission(perms.AGENTS_MANAGE)
@answers_problems
def pause_tenant_agent(request: HttpRequest, tenant_agent_id: uuid.UUID = Path(..., description=_TENANT_AGENT_ID)) -> Any:
    """Pauses one of the bank's own agents: it starts no run until someone resumes it, and
    it keeps its settings and its history. A run already open is not stopped; use
    `POST /agent-runs/{runId}/interrupt` for that.

    A person's session in a bank holding `agents.manage`; no API key. Records one audit
    event naming the person.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `agents.manage`;
    `not_found` (404) for an agent the bank does not have. Published ahead of the logic that
    will fill it, and answering 501 `not_built` until that ships.
    """
    tenant = caller_tenant(request)
    return control.pause(who=principal(request), tenant=tenant, tenant_agent_id=tenant_agent_id)


@router.delete(
    "/agents/{tenant_agent_id}/pause",
    response=TenantAgentOut,
    auth=SESSION,
    operation_id="resumeTenantAgent",
    by_alias=True,
    summary="Resume your bank's paused agent",
)
@requires_permission(perms.AGENTS_MANAGE)
@answers_problems
def resume_tenant_agent(request: HttpRequest, tenant_agent_id: uuid.UUID = Path(..., description=_TENANT_AGENT_ID)) -> Any:
    """Lifts the pause on one of the bank's own agents, so it runs on its cadence again.
    Nothing is deleted: the pause stays in the audit log.

    A person's session in a bank holding `agents.manage`; no API key. Records one audit
    event naming the person.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `agents.manage`;
    `not_found` (404) for an agent the bank does not have. Published ahead of the logic that
    will fill it, and answering 501 `not_built` until that ships.
    """
    tenant = caller_tenant(request)
    return control.resume(who=principal(request), tenant=tenant, tenant_agent_id=tenant_agent_id)


@router.post(
    "/agent-runs/{run_id}/interrupt",
    response=AgentRunListItem,
    auth=SESSION,
    operation_id="interruptAgentRun",
    by_alias=True,
    summary="Stop a run of your bank's agent",
)
@requires_permission(perms.AGENTS_MANAGE)
@answers_problems
def interrupt_agent_run(
    request: HttpRequest,
    run_id: uuid.UUID = Path(
        ..., description="The run to stop, as a UUID. Another bank's run answers 404; one of bleqq's runs answers 403."
    ),
) -> Any:
    """Stops an open run of one of the bank's own agents. What it filed before the stop
    stays, and the run reads as interrupted, with when and by whom. bleqq's library runs
    appear in the bank's run log but are never the bank's to stop.

    A person's session in a bank holding `agents.manage`; no API key. Records one audit
    event naming the person.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `agents.manage`, or
    naming `agent_definitions.manage` for a run of one of bleqq's agents; `not_found` (404)
    for a run the bank cannot see. Published ahead of the logic that will fill it, and
    answering 501 `not_built` until that ships.
    """
    tenant = caller_tenant(request)
    return control.interrupt(who=principal(request), tenant=tenant, run_id=run_id)


@router.get(
    "/tenant/agent-budget",
    response=AgentBudget,
    auth=SESSION,
    operation_id="getAgentBudget",
    by_alias=True,
    summary="See your bank's monthly cap on its own agents and this month's spend",
)
@requires_permission(perms.AGENTS_MANAGE)
@answers_problems
def get_agent_budget(request: HttpRequest) -> Any:
    """Returns the bank's one monthly cap on its own agents and what they have spent this
    calendar month in the bank's time zone. bleqq's own agents run at bleqq's cost and are
    never in the figure.

    A person's session in a bank holding `agents.manage`; no API key. It reads and writes
    nothing to the audit log.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `agents.manage`.
    """
    return budget.get_budget(tenant=caller_tenant(request))


@router.put(
    "/tenant/agent-budget",
    response=AgentBudget,
    auth=SESSION,
    operation_id="putAgentBudget",
    by_alias=True,
    summary="Set your bank's monthly cap on its own agents",
)
@requires_permission(perms.AGENTS_MANAGE)
@answers_problems
def put_agent_budget(request: HttpRequest, body: AgentBudgetInput) -> Any:
    """Sets the bank's monthly cap on its own agents; the first time, it creates it. A run
    that would pass the cap does not start, and a cap at or below this month's spend is
    accepted and pauses every running agent of the bank's own at once, since a bank must
    always be able to stop spending. A person resumes them.

    A person's session in a bank holding `agents.manage`; no API key. Records one audit
    event with the cap before and after, and one more for each agent the cap pauses.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `agents.manage`;
    `validation_error` (422) for a negative or malformed amount.
    """
    tenant = caller_tenant(request)
    return budget.put_budget(who=principal(request), tenant=tenant, body=body)


@router.get(
    "/research-requests",
    response=ResearchRequestPage,
    auth=SESSION,
    operation_id="listResearchRequests",
    by_alias=True,
    summary="See what your bank has asked its agents to do",
)
@requires_permission(perms.AGENTS_MANAGE)
@answers_problems
def list_research_requests(request: HttpRequest, page: Query[PageQuery]) -> Any:
    """Returns the bank's research requests, newest first, with each one's status. An empty
    list is a 200.

    A person's session in a bank holding `agents.manage`; no API key. It reads and writes
    nothing to the audit log.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `agents.manage`;
    `validation_error` (422) when `limit` is above 100. Published ahead of the logic that
    will fill it, and answering 501 `not_built` until that ships.
    """
    tenant = caller_tenant(request)
    return requests.list_requests(tenant=tenant, limit=page.limit, offset=page.offset)


@router.post(
    "/research-requests",
    response={202: ResearchRequestOut},
    auth=SESSION,
    operation_id="createResearchRequest",
    by_alias=True,
    summary="Ask your bank's agent to check a source or research a topic",
)
@requires_permission(perms.AGENTS_MANAGE)
@answers_problems
def create_research_request(request: HttpRequest, body: ResearchRequestInput) -> Any:
    """Asks one of the bank's own agents to run now, check a registered source or a web
    address now, or research a topic. The request is a job: it is queued and returned at
    once, and its run follows. It counts against the bank's monthly cap, and what the agent
    finds stays in the bank's own zone.

    A person's session in a bank holding `agents.manage`; no API key. Records one audit
    event naming the person and the kind, never the topic's text.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `agents.manage`;
    `not_found` (404) for an agent the bank does not have; `validation_error` (422) for a
    topic or address that is empty, too long or missing for its kind. Published ahead of
    the logic that will fill it, and answering 501 `not_built` until that ships.
    """
    tenant = caller_tenant(request)
    return requests.create_request(who=principal(request), tenant=tenant, body=body)


@router.get(
    "/research-requests/{request_id}",
    response=ResearchRequestOut,
    auth=SESSION,
    operation_id="getResearchRequest",
    by_alias=True,
    summary="See where one of your bank's research requests stands",
)
@requires_permission(perms.AGENTS_MANAGE)
@answers_problems
def get_research_request(
    request: HttpRequest,
    request_id: uuid.UUID = Path(..., description="The research request, as a UUID. Another bank's request answers 404."),
) -> Any:
    """Returns one of the bank's research requests with its status, for a screen following
    it until its run finishes.

    A person's session in a bank holding `agents.manage`; no API key. It reads and writes
    nothing to the audit log.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `agents.manage`;
    `not_found` (404) for a request the bank does not have. Published ahead of the logic
    that will fill it, and answering 501 `not_built` until that ships.
    """
    return requests.get_request(tenant=caller_tenant(request), request_id=request_id)
