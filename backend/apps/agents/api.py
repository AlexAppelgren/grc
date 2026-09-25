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

from apps.agents import agent_access, budget, control, definitions, platform, platform_read, requests, runs, runs_read, tenant_agents
from apps.agents.schemas import (
    AgentAccessInput,
    AgentAccessKeyCreated,
    AgentAccessKeyInput,
    AgentAccessKeyOut,
    AgentAccessOut,
    AgentAccessPage,
    AgentAccessReachInput,
    AgentAccessUpdate,
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
from apps.taxonomy.http import actor_for, answers_problems, caller_tenant, caller_user, if_match, principal, require_any
from apps.taxonomy.reading import language_order

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
    """Returns the agent runs the caller may see, newest first, one page at a time: when
    each ran, which agent, which version and which model, what started it and who asked,
    how it ended, what it counted and what it cost. Call it to show a bank what its own
    agents have done and what that cost, the history of one of them with `tenantAgentId`,
    the runs a person asked for with `mine`, and to investigate a run whose findings are
    being questioned.

    A person's session only; an API key cannot read this, so an agent cannot read its own
    history. Inside a bank it needs `agents.manage`, in the platform console
    `system.health`; a member with neither is refused. A bank sees its own runs and nothing
    else; the platform console sees the runs of bleqq's own agents. bleqq's runs reach a
    bank as watch items and proposals rather than as run rows, so no platform cost, token
    count or model is ever on a bank's page: `GET /agents/platform` shows what bleqq's
    agents watch, when each next runs and how its last run ended. No bank sees another
    bank's runs; the two filters only narrow that, and naming another bank's agent matches
    no run rather than answering an error. Runs that started in the same instant keep one
    stable order, so paging never skips or repeats one. It changes nothing and writes
    nothing to the audit log. An empty list is a 200 with `total` 0 and means nothing has
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
    Published ahead of the logic that will fill it, and answering 501 `not_built` until
    that ships.
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
    `agent_definitions.manage`; `not_found` (404) for a key no platform agent has.
    Published ahead of the logic that will fill it, and answering 501 `not_built` until
    that ships.
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
    """Returns the runs of bleqq's own agents, oldest first, one page at a time, with the
    version each ran, what it cost and how it ended, for the console's agent pages. A
    platform run reads no bank's row, so no bank's name or figure is in it.

    A person's session in the platform console holding `agent_definitions.manage`. It reads
    and writes nothing to the audit log. An empty list is a 200 with `total` 0.

    Errors: `unauthenticated` (401); `permission_denied` (403) without
    `agent_definitions.manage`; `validation_error` (422) when `limit` is above 100 or
    `offset` beyond the accepted depth. Published ahead of the logic that will fill it, and
    answering 501 `not_built` until that ships.
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

    Only active agents whose current version is not retired are listed, by key. `nextRunAt`
    is a cadence after the last run started, or now when the agent has never run or is
    overdue, and null for an agent that runs only when asked. An empty list is a 200.

    Errors: `unauthenticated` (401); `permission_denied` (403) without `watch.read`;
    `validation_error` (422) when `limit` is above 100.
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


# ---------------------------------------------------------------------------------------
# acc-entries-and-log (ACC-01, ACC-03, ACC-08): the agents a bank runs itself, registered
# as agent access entries, and their service keys. Every route is an admin's, under
# `agent_access.manage` on a person's session; every write also needs a passkey step-up and
# is recorded in the audit log. The path takes a UUID converter, so `what-applies` beside
# it is never read as an entry.
# ---------------------------------------------------------------------------------------
_ENTRY_ID = (
    "The entry's identifier, a UUID as `GET /agent-access` lists it. An entry of another bank, "
    "or none, answers `not_found` (404)."
)
_ACCESS_GATE = (
    "Needs `agent_access.manage` on a person's session in the bank and a passkey step-up on it "
    "younger than the step-up window; an API key or a personal access token is refused, since "
    "neither can step up."
)
_ACCESS_GATE_ERRORS = (
    "`step_up_required` (403) without a fresh step-up, which the screen answers by opening the "
    "passkey prompt and retrying; `permission_denied` (403) without `agent_access.manage`; "
    "`unauthenticated` (401) without a live session"
)
_ACCESS_WHAT = (
    "An agent access entry is an agent the bank runs on its own infrastructure, registered so "
    "it can read Compliance Watch through the REST API or the MCP server. It is not one of the "
    "agents we run: it holds a name, a purpose, a scope and credentials, and every credential "
    "under it reads and nothing else."
)


def _access_views(request: HttpRequest, tenant: Any, rows: list[Any]) -> list[AgentAccessOut]:
    return agent_access.views(rows, language_order(request, tenant=tenant))


def _access_view(request: HttpRequest, tenant: Any, entry_id: uuid.UUID) -> AgentAccessOut:
    return _access_views(request, tenant, [agent_access.entry(tenant.id, entry_id)])[0]


@router.get(
    "/agent-access",
    response=AgentAccessPage,
    auth=SESSION,
    operation_id="listAgentAccess",
    by_alias=True,
    summary="See the agents your bank runs itself and the keys each holds",
    description=(
        f"{_ACCESS_WHAT}\n\n"
        "Answers the bank's entries one page at a time, by name, revoked ones included, each "
        "with its team, departments, products, tenant reach toggle and every credential bound "
        "to it (never a secret). An empty page is a 200 with `total` 0.\n\n"
        "A read: it changes nothing and writes no audit row. Needs `agent_access.manage` on a "
        "person's session in the bank.\n\n"
        "Errors: `validation_error` (422) when `limit` is above 100; `permission_denied` (403) "
        "without `agent_access.manage`; `unauthenticated` (401) without a live session."
    ),
)
@requires_permission(perms.AGENT_ACCESS_MANAGE)
def list_agent_access(request: HttpRequest, page: PageQuery = Query(...)) -> AgentAccessPage:
    tenant = caller_tenant(request)
    rows, total = agent_access.list_entries(tenant.id, limit=page.limit, offset=page.offset)
    return AgentAccessPage(items=_access_views(request, tenant, rows), total=total)


@router.post(
    "/agent-access",
    response={201: AgentAccessOut},
    auth=SESSION,
    operation_id="registerAgentAccess",
    by_alias=True,
    summary="Register an agent your bank runs itself so it can read",
    description=(
        f"{_ACCESS_WHAT}\n\n"
        "Registers the agent with its name, purpose, the team that answers for it, and the "
        "departments and products it serves, which narrow what it reads to their terms within the "
        "bank's footprint; naming neither narrows nothing. Answers 201 with the entry, active, "
        "tenant reach off and no credential yet: issue one with `POST /agent-access/{entryId}/keys`.\n\n"
        f"{_ACCESS_GATE} Records `agent_access.registered` in the audit log with the team, "
        "department and product ids and the step-up assertion, never the purpose.\n\n"
        "Errors: `unknown_key` (422) for a team, department or product the bank has not got; "
        "`name_required` or `purpose_required` (422) for one of spaces alone; `validation_error` "
        f"(422) for a body the schema refuses; {_ACCESS_GATE_ERRORS}."
    ),
)
@requires_permission(perms.AGENT_ACCESS_MANAGE)
@requires_step_up
@answers_problems
def register_agent_access(request: HttpRequest, body: AgentAccessInput) -> Any:
    tenant = caller_tenant(request)
    user = caller_user(request)
    row = agent_access.register(
        tenant=tenant,
        user=user,
        actor=actor_for(request, user),
        name=body.name,
        purpose=body.purpose,
        owner_team=body.owner_team,
        department_ids=body.department_ids,
        product_ids=body.product_ids,
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
    )
    return 201, _access_view(request, tenant, row.id)


@router.get(
    "/agent-access/{uuid:entry_id}",
    response=AgentAccessOut,
    auth=SESSION,
    operation_id="getAgentAccess",
    by_alias=True,
    summary="See one agent your bank runs itself and its keys",
    description=(
        f"{_ACCESS_WHAT}\n\n"
        "Answers the entry with its team, departments, products, tenant reach toggle, version and "
        "every credential bound to it, newest first, revoked ones included; never a secret.\n\n"
        "A read: it changes nothing and writes no audit row. Needs `agent_access.manage` on a "
        "person's session in the bank.\n\n"
        "Errors: `not_found` (404) for an entry the bank has not got; `permission_denied` (403) "
        "without `agent_access.manage`; `unauthenticated` (401) without a live session."
    ),
)
@requires_permission(perms.AGENT_ACCESS_MANAGE)
@answers_problems
def get_agent_access(request: HttpRequest, entry_id: uuid.UUID = Path(..., description=_ENTRY_ID)) -> Any:
    return _access_view(request, caller_tenant(request), entry_id)


@router.patch(
    "/agent-access/{uuid:entry_id}",
    response=AgentAccessOut,
    auth=SESSION,
    operation_id="updateAgentAccess",
    by_alias=True,
    summary="Rename, re-purpose or re-scope an agent your bank runs itself",
    description=(
        f"{_ACCESS_WHAT}\n\n"
        "Changes what the body sends and nothing else; a list sent replaces the whole list, so "
        "sending an empty `departmentIds` stops narrowing by department. The new scope counts "
        "from the entry's next call. Send `If-Match` with the version last read to be told when "
        "someone changed it first. Answers the entry, its version raised by one.\n\n"
        f"{_ACCESS_GATE} Records `agent_access.updated` with the ids and keys before and after, "
        "and whether the purpose changed, never its text.\n\n"
        "Errors: `invalid_transition` (409) for a revoked entry; `stale_write` (409) when "
        "`If-Match` names an old version; `unknown_key` (422) for a team, department or product "
        "the bank has not got; `name_required` or `purpose_required` (422) for one of spaces "
        "alone; `validation_error` (422) for a body the schema refuses or an `If-Match` that is "
        f"not a version; `not_found` (404) for an entry the bank has not got; {_ACCESS_GATE_ERRORS}."
    ),
)
@requires_permission(perms.AGENT_ACCESS_MANAGE)
@requires_step_up
@answers_problems
def update_agent_access(request: HttpRequest, body: AgentAccessUpdate, entry_id: uuid.UUID = Path(..., description=_ENTRY_ID)) -> Any:
    tenant = caller_tenant(request)
    agent_access.update(
        tenant=tenant,
        entry_id=entry_id,
        actor=actor_for(request),
        name=body.name,
        purpose=body.purpose,
        owner_team=body.owner_team,
        department_ids=body.department_ids,
        product_ids=body.product_ids,
        expected_version=if_match(request),
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
    )
    return _access_view(request, tenant, entry_id)


@router.post(
    "/agent-access/{uuid:entry_id}/revoke",
    response=AgentAccessOut,
    auth=SESSION,
    operation_id="revokeAgentAccess",
    by_alias=True,
    summary="Stop an agent your bank runs itself, and every key it holds, for good",
    description=(
        f"{_ACCESS_WHAT}\n\n"
        "Revokes the entry and, in the same moment, every credential bound to it: its service "
        "keys and any personal access token naming it. From the next call each answers "
        "`unauthenticated` (401). An entry is never deleted and never switched back on; register "
        "a new one instead. Takes no body; send `If-Match` with the version last read. Answers "
        "the entry, inactive.\n\n"
        f"{_ACCESS_GATE} Records `agent_access.revoked` with the prefixes of the credentials it "
        "revoked, and one row per revoked credential in the security log.\n\n"
        "Errors: `invalid_transition` (409) for an entry already revoked; `stale_write` (409) "
        "when `If-Match` names an old version; `validation_error` (422) for an `If-Match` that is "
        f"not a version; `not_found` (404) for an entry the bank has not got; {_ACCESS_GATE_ERRORS}."
    ),
)
@requires_permission(perms.AGENT_ACCESS_MANAGE)
@requires_step_up
@answers_problems
def revoke_agent_access(request: HttpRequest, entry_id: uuid.UUID = Path(..., description=_ENTRY_ID)) -> Any:
    tenant = caller_tenant(request)
    user = caller_user(request)
    agent_access.revoke(
        tenant=tenant,
        entry_id=entry_id,
        user=user,
        actor=actor_for(request, user),
        expected_version=if_match(request),
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
    )
    return _access_view(request, tenant, entry_id)


@router.put(
    "/agent-access/{uuid:entry_id}/tenant-reach",
    response=AgentAccessOut,
    auth=SESSION,
    operation_id="setAgentAccessReach",
    by_alias=True,
    summary="Let an agent your bank runs itself read your register, or stop it",
    description=(
        f"{_ACCESS_WHAT}\n\n"
        "Sets the entry's own half of tenant reach. With it on, the entry's credentials holding "
        "`tenant:read` read the bank's register decisions, but only while the bank's own switch "
        "(`GET /tenant/reach`, turned on by two people) is on as well; with the bank's switch "
        "off, every entry reads the shared library only, whatever this says. Send `If-Match` with "
        "the version last read. Answers the entry, its version raised by one.\n\n"
        f"{_ACCESS_GATE} Records `agent_access.reach_set` with the toggle before and after.\n\n"
        "Errors: `invalid_transition` (409) for a revoked entry; `stale_write` (409) when "
        "`If-Match` names an old version; `validation_error` (422) for a body the schema refuses "
        "or an `If-Match` that is not a version; `not_found` (404) for an entry the bank has not "
        f"got; {_ACCESS_GATE_ERRORS}."
    ),
)
@requires_permission(perms.AGENT_ACCESS_MANAGE)
@requires_step_up
@answers_problems
def set_agent_access_reach(request: HttpRequest, body: AgentAccessReachInput, entry_id: uuid.UUID = Path(..., description=_ENTRY_ID)) -> Any:
    tenant = caller_tenant(request)
    agent_access.set_tenant_reach(
        tenant=tenant,
        entry_id=entry_id,
        actor=actor_for(request),
        enabled=body.enabled,
        expected_version=if_match(request),
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
    )
    return _access_view(request, tenant, entry_id)


@router.post(
    "/agent-access/{uuid:entry_id}/keys",
    response={201: AgentAccessKeyCreated},
    auth=SESSION,
    operation_id="createAgentAccessKey",
    by_alias=True,
    summary="Issue a key to an agent your bank runs itself",
    description=(
        f"{_ACCESS_WHAT}\n\n"
        "Issues a service key bound to the entry and answers it once, with 201. The key acts as "
        "the entry and reads within its scope; put `plainKey` straight into the agent's secret "
        "store, because the server keeps only a hash of the secret and never shows it again. It "
        "holds only the reading scopes, and it expires no later than `AGENT_ACCESS_KEY_MAX_DAYS` "
        "days from now, which is also its expiry when none is sent.\n\n"
        f"{_ACCESS_GATE} Records `api_key.created` with the prefix, scopes and expiry, never the "
        "secret, and a row for the new key in the security log.\n\n"
        "Errors: `invalid_transition` (409) for a revoked entry; `unknown_key` (422) for a scope "
        "an entry's key may not hold, the message naming the valid ones; `expiry_in_past` (422) "
        "for an expiry that is not in the future; `expiry_too_late` (422) for one beyond the "
        "longest a key may live; `name_required` (422) for a name of spaces alone; "
        "`validation_error` (422) for a body the schema refuses; `not_found` (404) for an entry "
        f"the bank has not got; {_ACCESS_GATE_ERRORS}."
    ),
)
@requires_permission(perms.AGENT_ACCESS_MANAGE)
@requires_step_up
@answers_problems
def create_agent_access_key(request: HttpRequest, body: AgentAccessKeyInput, entry_id: uuid.UUID = Path(..., description=_ENTRY_ID)) -> Any:
    tenant = caller_tenant(request)
    user = caller_user(request)
    key, plain = agent_access.create_key(
        tenant=tenant,
        entry_id=entry_id,
        user=user,
        actor=actor_for(request, user),
        name=body.name,
        scopes=body.scopes,
        expires_at=body.expires_at,
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
    )
    return 201, AgentAccessKeyCreated(**agent_access.key_out(key).model_dump(), plain_key=plain)


@router.post(
    "/agent-access/{uuid:entry_id}/keys/{uuid:key_id}/revoke",
    response=AgentAccessKeyOut,
    auth=SESSION,
    operation_id="revokeAgentAccessKey",
    by_alias=True,
    summary="Stop one key of an agent your bank runs itself, for good",
    description=(
        f"{_ACCESS_WHAT}\n\n"
        "Revokes one credential bound to the entry, a service key or a personal access token "
        "naming it: from its next call it answers `unauthenticated` (401), and it never works "
        "again. Revoking one already revoked changes nothing and answers the same, so a retry is "
        "safe. Takes no body. Answers the credential with its revocation time.\n\n"
        f"{_ACCESS_GATE} Records `api_key.revoked` in the audit log every time, and a row "
        "in the security log the first time.\n\n"
        "Errors: `not_found` (404) for an entry the bank has not got or a credential not bound to "
        f"it; {_ACCESS_GATE_ERRORS}."
    ),
)
@requires_permission(perms.AGENT_ACCESS_MANAGE)
@requires_step_up
@answers_problems
def revoke_agent_access_key(
    request: HttpRequest,
    entry_id: uuid.UUID = Path(..., description=_ENTRY_ID),
    key_id: uuid.UUID = Path(..., description="The credential's identifier, a UUID as the entry's `keys` list shows it; one not bound to this entry answers `not_found` (404)."),
) -> Any:
    tenant = caller_tenant(request)
    user = caller_user(request)
    key = agent_access.revoke_key(
        tenant=tenant,
        entry_id=entry_id,
        key_id=key_id,
        user=user,
        actor=actor_for(request, user),
        step_up_assertion_id=request.step_up_assertion_id,  # type: ignore[attr-defined]
    )
    return agent_access.key_out(key)
