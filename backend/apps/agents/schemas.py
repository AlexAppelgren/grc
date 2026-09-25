"""Request and response schemas of the agents app: camelCase through CamelSchema, app-prefixed
class names where a shape is specific to this app (playbook 4.1).

Plain Pydantic, never `ModelSchema`: the agent contract references no Django model, so it
lands beside the watch models rather than behind them. `Literal` rather than an enum class
for the fixed kinds a caller may send (`run_status`, `check_status`): a kind in code stays
in code, and the OpenAPI enum is the same either way.

What an agent may reach, and what it may not, is the thing to be precise about here. No
API key scope reaches the shared library: an agent proposes and a person or a second,
independent agent approves, and until then nothing in the library has moved. A run's
writes are idempotent, so a retry replays rather than duplicates. bleqq's own agents are
part of the base package and platform-run; a bank cannot switch one off or change its
cadence, and a bank's own agents write only in that bank's zone.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from ninja import Field
from pydantic import ConfigDict, JsonValue

from django.conf import settings

from apps.shared.schemas import CamelSchema, PageQuery, WriteBody
from apps.taxonomy.schemas import PersonRef

__all__ = [
    "AgentBudget",
    "AgentBudgetInput",
    "AgentDefinitionDetail",
    "AgentDefinitionOut",
    "AgentDefinitionPage",
    "AgentRunFinish",
    "AgentRunInput",
    "AgentRunOut",
    "AgentRunListItem",
    "AgentRunListPage",
    "AgentRunStats",
    "AgentVersionInput",
    "AgentVersionOut",
    "CamelSchema",
    "PlatformAgentSettings",
    "PlatformAgentSettingsInput",
    "PlatformWatchItem",
    "PlatformWatchLastRun",
    "PlatformWatchPage",
    "ResearchRequestInput",
    "ResearchRequestOut",
    "ResearchRequestPage",
    "RetagRequestInput",
    "TenantAgentInput",
    "TenantAgentOut",
    "TenantAgentPage",
    "TenantAgentScope",
    "TenantAgentUpdate",
    "TenantRunQuery",
]

# The examples are one night's sweep by the shipped `watch-sweeper` definition over Nordic
# and EU sources (FFFS and the EU instruments the prototype tracks). Never a real customer.
_EXAMPLE_RUN_ID = "5f1c2a80-3b6e-4a1e-9d21-0a2b8c7d4e10"
_EXAMPLE_MODEL = "regwatch-2026-08"
_EXAMPLE_PIPELINE = "watch-1.4.2"
_EXAMPLE_STATS: dict[str, JsonValue] = {
    "modelCalls": 42,
    "fetches": 118,
    "sourcesChecked": 31,
    "changesRegistered": 2,
    "proposalsSubmitted": 5,
    "outOfScope": 3,
    "recordsRechecked": 12,
    "correctionsProposed": 1,
}
_EXAMPLE_FINISHED_RUN: dict[str, JsonValue] = {
    "id": _EXAMPLE_RUN_ID,
    "agent": "watch-sweeper",
    "startedAt": "2026-09-20T02:00:03Z",
    "finishedAt": "2026-09-20T02:18:41Z",
    "status": "succeeded",
    "model": _EXAMPLE_MODEL,
    "pipelineVersion": _EXAMPLE_PIPELINE,
    "stats": _EXAMPLE_STATS,
    "outputRef": "runs/2026-09-20/watch-sweeper/5f1c2a80.jsonl",
    "error": None,
}


class AgentRunStats(CamelSchema):
    """The `stats` column of agent_run: what one run did, counted against the budget
    defaults of its definition (`backend/agents/<agent>/v<n>/definition.yaml`). What the
    server can see it counts itself as the run closes (H41): sources checked, changes
    registered, proposals submitted and records re-checked. The rest is the run's own
    account."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_STATS]})

    model_calls: int = Field(
        default=0,
        description=(
            "How many times the run called a language model, counted against the model-call "
            "budget in the agent's versioned definition. The agent reports it as it closes the "
            "run; it defaults to 0, so 0 on a finished run means the agent did no model work "
            "rather than that the number is missing."
        ),
    )
    fetches: int = Field(
        default=0,
        description=(
            "How many documents the run fetched from the outside world, counted against the "
            "fetch budget in the agent's definition. Fetched content is untrusted: it is "
            "screened for embedded instructions before it is read and never executed, so a "
            "high count measures work done and never facts established. Defaults to 0."
        ),
    )
    sources_checked: int = Field(
        default=0,
        description=(
            "How many registered sources the run visited, one per source per run, counting the "
            "sources where nothing had changed. A quiet source is still a check, and that is "
            "what lets a bank show that a source was watched on a given night rather than only "
            "that something was found. Counted by the server as the run closes, from the sweep "
            "lines the run logged in the coverage log; a number sent here is not kept. Defaults to 0."
        ),
    )
    changes_registered: int = Field(
        default=0,
        description=(
            "How many regulatory changes the run put on the watch feed, counted against the "
            "change budget in the agent's definition. A change is a sighting the bank has yet "
            "to judge: it is not an obligation, it is not applicability and it is not a "
            "decision, and nothing in the inventory moves until a person acts on it. Counted "
            "by the server as the run closes, from the new changes it registered (a second "
            "sighting is not a new change); a number sent here is not kept. Defaults to 0."
        ),
    )
    proposals_submitted: int = Field(
        default=0,
        description=(
            "How many proposals the run put in the queue for the shared library, counted "
            "against the proposal budget in the agent's definition. A proposal is the only "
            "door an agent has into the library and it changes nothing until it is approved, "
            "so read this as a count of requests and never of library edits. Counted by the "
            "server as the run closes, from the proposals filed under it; a number sent here "
            "is not kept. Defaults to 0."
        ),
    )
    out_of_scope: int = Field(
        default=0,
        ge=0,
        description=(
            "How many documents the run read and set aside because they fall outside the "
            "sector scope, a whole number with a minimum of 0 and no maximum. bleqq watches "
            "regulated financial services only, so a medical-device rule or an environmental "
            "permit that a source also publishes is counted on that source's check and here, "
            "and nothing is registered or proposed from it: it never reaches the watch feed or "
            "the proposal queue. Read it beside `sourcesChecked`, because a source that offered "
            "only such documents was still watched that night. Defaults to 0; a negative "
            "number is refused with `validation_error`."
        ),
    )
    records_rechecked: int = Field(
        default=0,
        ge=0,
        description=(
            "How many library records the run re-checked against the pages they cite, a whole "
            "number with a minimum of 0 and no maximum: one per record, each also logged as a "
            "`recheck` source check naming it, so the coverage log shows which records were "
            "compared beside the documents fetched. A record found unchanged still counts, "
            "because a quiet re-check is still a check. Counted by the server as the run "
            "closes, from the records its re-check lines name; a number sent here is not kept. "
            "Defaults to 0; a negative number is refused with `validation_error`."
        ),
    )
    corrections_proposed: int = Field(
        default=0,
        ge=0,
        description=(
            "How many of those re-checked records had drifted from their source and became a "
            "`new_obligation_version` proposal, a whole number with a minimum of 0 and no "
            "maximum. A correction is a request and never an edit: the record says what it "
            "said before until a second and independent principal approves it. These "
            "proposals are also counted in `proposalsSubmitted`. Defaults to 0; a negative "
            "number is refused with `validation_error`."
        ),
    )


class AgentRunInput(WriteBody):
    """`POST /agent-runs`, the first call of every execution (AGT-01). `agent` is the
    definition's stable key, never its label."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"agent": "watch-sweeper", "model": _EXAMPLE_MODEL, "pipelineVersion": _EXAMPLE_PIPELINE}]
        }
    )

    agent: str = Field(
        min_length=1,
        max_length=80,
        description=(
            "The stable key of the agent definition this run executes, such as "
            "`watch-sweeper` — the definition's key and never its label, between 1 and 80 "
            "characters. The key must name a definition this build ships and one the calling "
            "key is entitled to run, or the call is refused. A key is issued once and never "
            "changes: a new version of an agent keeps the key and raises its version, so a run "
            "log stays readable across versions."
        ),
    )
    model: str = Field(
        min_length=1,
        max_length=120,
        description=(
            "The identifier of the language model this run will use, as the runner names it, "
            "between 1 and 120 characters — `regwatch-2026-08`. It is recorded with the run so "
            "that any fact an agent produced can be traced to the model that produced it. "
            "Naming a model here does not make an endpoint approved: which endpoints tenant "
            "content may reach is a deployment decision and not a caller's."
        ),
    )
    pipeline_version: str = Field(
        min_length=1,
        max_length=40,
        description=(
            "The version of the agent pipeline that is running, between 1 and 40 characters — "
            "`watch-1.4.2`. It is the code-side companion to the definition's own version and "
            "is recorded with the run, so a later evaluation can tell a change of behaviour "
            "caused by new code from one caused by a new prompt or a new model."
        ),
    )


class AgentRunFinish(WriteBody):
    """`PATCH /agent-runs/{runId}`: a run closes once, into a terminal status."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "succeeded",
                    "stats": _EXAMPLE_STATS,
                    "outputRef": "runs/2026-09-20/watch-sweeper/5f1c2a80.jsonl",
                    "error": None,
                }
            ]
        }
    )

    status: Literal["succeeded", "failed"] = Field(
        description=(
            "How the run ended. `succeeded` means the agent finished its sweep and filed "
            "everything it found; `failed` means it stopped early — a blocked page, an "
            "exhausted budget, a crash — and whatever it had already filed still stands and is "
            "still attributed to this run. A run closes once and only into one of these two, "
            "so `running` cannot be sent here; opening the run is what sets that. Neither "
            "value says the findings are right: an agent's output stays labelled as machine "
            "output until a person at the bank confirms it."
        )
    )
    stats: AgentRunStats | None = Field(
        default=None,
        description=(
            "The counters for this run, filed as the agent closes it. Optional: omit it or "
            "send null and the counters already on the run stand unchanged, which is the "
            "honest answer from a run that failed before it could count."
        ),
    )
    output_ref: str | None = Field(
        default=None,
        max_length=500,
        description=(
            "Where the run's full working output was stored — an object-store path such as "
            "`runs/2026-09-20/watch-sweeper/5f1c2a80.jsonl` — at most 500 characters. It is a "
            "pointer for the engineers who operate the agents and never something a bank's "
            "screen shows, so it must not carry tenant content in its path. Null when the run "
            "kept no output."
        ),
    )
    error: str | None = Field(
        default=None,
        max_length=2000,
        description=(
            "What went wrong, in at most 2000 characters, on a run that failed. It is read by "
            "the people who operate the agents, so keep it to the technical cause: never a "
            "stack trace, never fetched page content, and never anything belonging to a bank, "
            "because this text travels to the operators' logs. Null on a run that succeeded."
        ),
    )


class AgentRunOut(CamelSchema):
    """One run as every reader sees it. A tenant reads the library's runs and its own; no
    reader sees another tenant's (AGT-01, item 14)."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_FINISHED_RUN]})

    id: uuid.UUID = Field(
        description=(
            "The run's permanent identifier, a UUID the server issues when the run opens. "
            "Every change, proposal and source check the agent files carries it, so it is the "
            "thread a reviewer pulls to see everything one execution did and where each claim "
            "came from."
        )
    )
    agent: str = Field(
        description=(
            "The stable key of the agent definition that executed, such as `watch-sweeper`. "
            "The key and never the label. It does not tell you which version ran: read "
            "`pipelineVersion` for that."
        )
    )
    started_at: datetime = Field(
        description=(
            "When the run was opened, as a UTC timestamp in ISO 8601. The server sets it, not "
            "the agent, so it cannot be backdated. Runs are listed oldest first by this value, "
            "which is the order a sweep actually happened in."
        )
    )
    finished_at: datetime | None = Field(
        description=(
            "When the run was closed, as a UTC timestamp in ISO 8601, set by the server. Null "
            "while the run is still open. A run that has been null for far longer than its "
            "cadence is a stuck run and not a successful one, so do not read null as 'still "
            "going well'."
        )
    )
    status: Literal["running", "succeeded", "failed"] = Field(
        description=(
            "Where the run stands. `running`: the agent is working and the server has heard "
            "nothing more. `succeeded`: the agent closed the run having filed what it found. "
            "`failed`: it closed early, and what it filed before that still counts. This is a "
            "statement about the execution and never about the findings — everything an agent "
            "filed stays labelled as machine output until a person at the bank confirms it."
        )
    )
    model: str = Field(
        description=(
            "The language model this run used, as the runner named it — `regwatch-2026-08`. "
            "Recorded so any fact an agent produced can be traced to the model behind it, and "
            "so a change in quality can be read against a change of model."
        )
    )
    pipeline_version: str = Field(
        description=(
            "The version of the agent pipeline that executed — `watch-1.4.2`. With `model` it "
            "is what an evaluation compares runs across. It is the running code's version and "
            "not the agent definition's own version number."
        )
    )
    stats: AgentRunStats = Field(
        description=(
            "What this run did, counted against the budgets in the agent's definition. All "
            "zeroes while the run is open, because an agent files its counters when it closes; "
            "zeroes on a closed run mean the run genuinely did nothing."
        )
    )
    output_ref: str | None = Field(
        description=(
            "Where the run's full working output was stored, a pointer for the engineers who "
            "operate the agents rather than anything a bank's screen shows. Null when the run "
            "kept no output or has not closed yet."
        )
    )
    error: str | None = Field(
        description=(
            "Why the run failed, as the agent reported it, in terms meant for the people who "
            "operate the agents. Null on a run that is still open or that succeeded. A run can "
            "fail with nothing here, so null is not proof that nothing went wrong — read "
            "`status` for that."
        )
    )


# ---------------------------------------------------------------------------------------
# The platform's agent definitions, read-only (ID-10, AGT-01): what a platform
# administrator binds an agent key to. Publishing a definition is AGT-03, R2.
# ---------------------------------------------------------------------------------------
_EXAMPLE_DEFINITION: dict[str, JsonValue] = {
    "id": "3c9e1f27-58b4-4d6a-a0e2-6f41b7c8d953",
    "key": "watch-sweeper",
    "description": (
        "Checks registered sources for new or changed regulatory documents, registers one "
        "change per reform with a stable key, and proposes obligation links."
    ),
    "currentVersion": 1,
    "active": False,
    "scope": "platform",
    "tenantConfigurable": False,
    "publishedAt": "2026-09-20T08:00:00Z",
}


class AgentDefinitionOut(CamelSchema):
    """One agent definition as the platform ships it, loaded from its versioned folder."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_DEFINITION]})

    id: uuid.UUID = Field(
        description=(
            "The definition's permanent identifier, a UUID. It is what `POST /agent-keys` takes "
            "as `agentId` to bind a key to this agent."
        )
    )
    key: str = Field(
        description=(
            "The definition's stable key, such as `watch-sweeper`: what a run names in "
            "`POST /agent-runs` and what the audit trail records as the actor. It is issued once "
            "and never changes; a new version keeps the key and raises `currentVersion`."
        )
    )
    description: str = Field(
        description=(
            "What the agent does, in the words of its definition file. It says what the agent is "
            "for and grants nothing: what a key bound to it may do is the key's scopes."
        )
    )
    current_version: int = Field(
        description=(
            "The version of the definition this build loaded — its prompt, tools and budgets — "
            "counting from 1. Runs started from now on run it."
        )
    )
    active: bool = Field(
        description=(
            "Whether the definition is released for scheduled runs. True for an active "
            "definition; false while it is a draft or after it is retired. A key can be bound to "
            "a draft so that its runner can be tried before release."
        )
    )
    scope: Literal["platform", "tenant"] = Field(
        description=(
            "Whose agent this definition makes. `platform`: one of bleqq's own agents, part of "
            "the base package, run by the platform for every bank at once; no bank switches it "
            "off, pauses it or changes its cadence, scope or budget. `tenant`: a definition a "
            "bank may add as its own agent, which then writes only in that bank's zone. Either "
            "way the definition itself, its prompt and its tools, is bleqq's."
        )
    )
    tenant_configurable: bool = Field(
        description=(
            "Whether a bank may add this definition as its own agent and set its switch, "
            "cadence and scope. Always false on a `platform` definition, which the database "
            "refuses otherwise; true on a `tenant` definition released for banks to add."
        )
    )
    published_at: datetime | None = Field(
        description=(
            "When the current version was published, as a UTC timestamp in ISO 8601. Null when "
            "no version row has been published for it yet, as for a definition the build loaded "
            "before versions were kept as rows."
        )
    )


class AgentDefinitionPage(CamelSchema):
    """`{items, total}` with `limit` and `offset` (playbook 10)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_EXAMPLE_DEFINITION], "total": 1}]})

    items: list[AgentDefinitionOut] = Field(
        description=(
            "The definitions on this page, ordered by key. They are the platform's own agents, "
            "the same for every bank; a bank's own agents are not listed here. An empty list is a "
            "200 and means no definition has been loaded yet."
        )
    )
    total: int = Field(
        description="How many definitions exist in total, not how many are on this page; use it to size a pager."
    )


# ---------------------------------------------------------------------------------------
# Chunk 11 (`c11-agents-contract`; AGT-03 to AGT-05, ADM-02). bleqq's agents are the base
# package and the console's alone; a bank adds agents of its own against a tenant-scoped
# definition and steers only those, inside its own zone (D-61, ADR 0053).
# ---------------------------------------------------------------------------------------
Cadence = Literal["daily", "weekly", "monthly", "manual"]
Trigger = Literal["schedule", "manual", "request", "api"]
RequestKind = Literal["run_now", "check_source", "check_url", "research_topic"]
RequestState = Literal["queued", "running", "done", "failed", "rejected", "cancelled"]

_CADENCE = (
    "`daily`, `weekly` and `monthly` start a run on that rhythm; `manual` starts none on a "
    "schedule, so the agent runs only when someone asks for a run."
)
_JURISDICTION_KEYS = (
    "Jurisdiction keys from the jurisdiction vocabulary (`GET /vocab/jurisdiction`), such as "
    "`se` or `eu`: keys and never labels, each one an active row; an unknown key is refused "
    "with `unknown_key` and the valid keys. The platform's editors add rows to that list "
    "through the proposal queue, so its members are not fixed here."
)
_MONEY = (
    "a decimal amount in euros with at most two decimals and eight digits before the point, "
    "never negative, sent and returned as a string such as `250.00` so no rounding creeps in"
)
_EXAMPLE_VERSION: dict[str, JsonValue] = {
    "versionNo": 2,
    "model": "regwatch-2026-08",
    "changeNote": "Reads the new FFFS index page.",
    "publishedAt": "2026-09-24T09:12:00Z",
    "publishedBy": {"id": "8a3c1e5f-2d4b-4f60-9e7a-1b2c3d4e5f60", "name": "Sara Lindqvist"},
    "retiredAt": None,
}
_EXAMPLE_TENANT_AGENT_ID = "0b7d2f64-1c3e-4a58-9d2b-6e4f8a1c3b57"
_EXAMPLE_SCOPE: dict[str, JsonValue] = {"jurisdictions": ["se", "fi"], "terms": ["payments"]}
_EXAMPLE_TENANT_AGENT: dict[str, JsonValue] = {
    "id": _EXAMPLE_TENANT_AGENT_ID,
    "agent": "bank-source-watch",
    "enabled": True,
    "cadence": "weekly",
    "runWeekday": 1,
    "runHour": 6,
    "nextRunAt": "2026-09-28T04:00:00Z",
    "scope": _EXAMPLE_SCOPE,
    "pausedAt": None,
    "pausedBy": None,
    "updatedAt": "2026-09-24T09:12:00Z",
}
_EXAMPLE_LIST_RUN: dict[str, JsonValue] = {
    **_EXAMPLE_FINISHED_RUN,
    "agent": "bank-source-watch",
    "tenantAgentId": _EXAMPLE_TENANT_AGENT_ID,
    "agentVersion": 1,
    "trigger": "manual",
    "requestedBy": {"id": "8a3c1e5f-2d4b-4f60-9e7a-1b2c3d4e5f60", "name": "Sara Lindqvist"},
    "cost": "1.84",
    "interruptedAt": None,
}
_EXAMPLE_REQUEST: dict[str, JsonValue] = {
    "id": "4e2a9c71-6b3d-4f18-8a5e-2c7d1b9f0e36",
    "kind": "research_topic",
    "tenantAgentId": _EXAMPLE_TENANT_AGENT_ID,
    "topic": "DORA subcontracting",
    "sourceId": None,
    "url": None,
    "status": "queued",
    "requestedBy": {"id": "8a3c1e5f-2d4b-4f60-9e7a-1b2c3d4e5f60", "name": "Sara Lindqvist"},
    "createdAt": "2026-09-24T09:12:00Z",
    "completedAt": None,
}
_EXAMPLE_WATCH: dict[str, JsonValue] = {
    "key": "watch-sweeper",
    "name": "Nordic and EU regulatory watch",
    "purpose": "Checks the registered sources for new or changed regulation every night.",
    "jurisdictions": ["se", "dk", "no", "fi", "eu"],
    "cadence": "daily",
    "nextRunAt": "2026-09-25T02:00:00Z",
    "lastRun": {"finishedAt": "2026-09-24T02:18:41Z", "status": "succeeded"},
}


class AgentVersionOut(CamelSchema):
    """One published version of a definition (AGT-03). Published once and never rewritten: a
    run points at the version it opened with, so retiring one only stops new runs."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_VERSION]})

    version_no: int = Field(
        description=(
            "The version's number, counting from 1 within its definition. It is the `v<n>` "
            "folder the build ships for the definition, and it never changes once published."
        )
    )
    model: str = Field(
        description=(
            "The language model this version runs, as its definition file names it, such as "
            "`regwatch-2026-08`. It names the model and does not approve an endpoint."
        )
    )
    change_note: str = Field(
        description=(
            "What changed in this version and why, in the words of the platform administrator "
            "who published it. Empty for a first version the build loaded."
        )
    )
    published_at: datetime = Field(
        description="When the version was published, as a UTC timestamp in ISO 8601, set by the server."
    )
    published_by: PersonRef | None = Field(
        description=(
            "The platform administrator who published the version, by id and name. Null for a "
            "first version the build loaded, which nobody published by hand."
        )
    )
    retired_at: datetime | None = Field(
        description=(
            "When the version was retired, as a UTC timestamp in ISO 8601, or null while it may "
            "still run. A retired version starts no new run; runs that used it keep pointing at it."
        )
    )


class AgentDefinitionDetail(AgentDefinitionOut):
    """One definition with every version it has published, newest first (AGT-03)."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{**_EXAMPLE_DEFINITION, "versions": [_EXAMPLE_VERSION]}]}
    )

    versions: list[AgentVersionOut] = Field(
        description=(
            "Every version of the definition, newest first, retired ones included, so the "
            "console shows which version each past run used. Empty when none has been published."
        )
    )


class AgentVersionInput(WriteBody):
    """`POST /agent-definitions/{agentKey}/versions`: publish a version folder the build ships."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"versionNo": 2, "changeNote": "Reads the new FFFS index page."}]})

    version_no: int = Field(
        ge=1,
        description=(
            "The number of the version to publish, a whole number with a minimum of 1: the "
            "`v<n>` folder this build ships for the definition. Its prompt, tools and model are "
            "read from that folder, never from this request, so no prompt text travels here."
        ),
    )
    change_note: str = Field(
        min_length=1,
        max_length=2000,
        description=(
            "What changed in this version and why, between 1 and 2000 characters, kept with "
            "the version for good. Name the change, not a bank: this note is platform text."
        ),
    )


class PlatformAgentSettings(CamelSchema):
    """What one of bleqq's agents runs with (AGT-03): the same for every bank, and carrying
    no tenant figure. A platform agent's settings live on its definition row."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"agentKey": "watch-sweeper", "cadence": "daily", "jurisdictions": ["se", "eu"], "monthlyBudget": "250.00"}]
        }
    )

    agent_key: str = Field(description="The stable key of the agent these settings belong to, such as `watch-sweeper`.")
    cadence: Cadence = Field(description=f"How often the platform starts the agent. {_CADENCE}")
    jurisdictions: list[str] = Field(description=f"The jurisdictions the agent sweeps. {_JURISDICTION_KEYS}")
    monthly_budget: Decimal | None = Field(
        description=f"What the agent may spend in a calendar month, {_MONEY}. Null when no budget is set."
    )


class PlatformAgentSettingsInput(WriteBody):
    """`PUT /agent-definitions/{agentKey}/settings`: the whole setting, for every bank at once."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"cadence": "daily", "jurisdictions": ["se", "eu"], "monthlyBudget": "250.00"}]}
    )

    cadence: Cadence = Field(description=f"How often the platform starts the agent. {_CADENCE}")
    jurisdictions: list[str] = Field(
        min_length=1,
        max_length=100,
        description=f"The jurisdictions the agent sweeps, between 1 and 100 of them. {_JURISDICTION_KEYS}",
    )
    monthly_budget: Decimal | None = Field(
        ge=0,
        max_digits=10,
        decimal_places=2,
        description=f"What the agent may spend in a calendar month, {_MONEY}, with a minimum of 0. Null removes the budget.",
    )


class RetagRequestInput(WriteBody):
    """`POST /console/research-requests`: ask for library records to be re-tagged (AGT-05).
    The answer is a batch proposal with a preview, never a direct edit."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"topic": "Re-tag custody records with Client money."}]})

    topic: str = Field(
        min_length=1,
        max_length=settings.AGENT_RESEARCH_TOPIC_MAX_CHARS,
        description=(
            "Which library records to re-tag and with what, between 1 and "
            f"{settings.AGENT_RESEARCH_TOPIC_MAX_CHARS} characters, such as \"Re-tag custody "
            "records with Client money\". Platform text about public records, never a bank's."
        ),
    )


class TenantAgentScope(CamelSchema):
    """A bank's own agent's scope: keys only, never free text (AGT-04). Empty lists mean the
    default: the bank's operating markets first, then the watched ones."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_SCOPE]})

    jurisdictions: list[str] = Field(
        default_factory=list,
        max_length=100,
        description=(
            f"The jurisdictions the agent looks at, at most 100, by default none. {_JURISDICTION_KEYS} "
            "None means the bank's operating markets first, then the ones it watches."
        ),
    )
    terms: list[str] = Field(
        default_factory=list,
        max_length=100,
        description=(
            "Taxonomy term keys the agent narrows to, at most 100, by default none, from "
            "`GET /taxonomy/terms`: keys and never labels, each an active row; an unknown key is "
            "refused with `unknown_key`. The platform's editors extend the taxonomy through the "
            "proposal queue. None means no narrowing by term."
        ),
    )


class TenantAgentOut(CamelSchema):
    """One of the bank's own agents (AGT-04): its switch, cadence, scope and pause."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_TENANT_AGENT]})

    id: uuid.UUID = Field(description="The bank's agent's identifier, a UUID. Another bank's agent answers 404.")
    agent: str = Field(
        description="The stable key of the tenant-scoped definition the bank added, such as `bank-source-watch`."
    )
    enabled: bool = Field(description="Whether the agent is switched on. Off, it starts no run on its cadence.")
    cadence: Cadence = Field(description=f"How often the agent runs. {_CADENCE}")
    run_weekday: int | None = Field(
        description=(
            "The day a weekly or monthly run starts, a whole number with a minimum of 1 "
            "(Monday) and a maximum of 7 (Sunday), in the bank's own time zone. Null for daily "
            "and manual."
        )
    )
    run_hour: int | None = Field(
        description=(
            "The hour a scheduled run starts, a whole number with a minimum of 0 and a maximum "
            "of 23, in the bank's own time zone. Null for manual."
        )
    )
    next_run_at: datetime | None = Field(
        description="When the next scheduled run starts, as a UTC timestamp in ISO 8601. Null when none is scheduled."
    )
    scope: TenantAgentScope = Field(description="What the agent looks at, by keys. Empty lists mean the default markets.")
    paused_at: datetime | None = Field(
        description=(
            "When the agent was paused, as a UTC timestamp in ISO 8601, or null when it is not. "
            "A paused agent starts no run until someone resumes it."
        )
    )
    paused_by: PersonRef | None = Field(
        description=(
            "The person who paused the agent. Null when it is not paused, or when the budget cap "
            "paused it rather than a person."
        )
    )
    updated_at: datetime = Field(description="When the agent's settings last changed, as a UTC timestamp in ISO 8601.")


class TenantAgentPage(CamelSchema):
    """`{items, total}` with `limit` and `offset` (playbook 10)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_EXAMPLE_TENANT_AGENT], "total": 1}]})

    items: list[TenantAgentOut] = Field(
        description="The bank's own agents on this page, by definition key. bleqq's agents are never listed here."
    )
    total: int = Field(description="How many agents the bank has added in total, not how many are on this page.")


class TenantAgentInput(WriteBody):
    """`POST /agents`: the bank adds an agent of its own from a tenant-scoped definition."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"agent": "bank-source-watch", "cadence": "weekly", "runWeekday": 1, "runHour": 6, "scope": _EXAMPLE_SCOPE}]}
    )

    agent: str = Field(
        min_length=1,
        max_length=80,
        description=(
            "The stable key of the definition to add, between 1 and 80 characters, from "
            "`GET /agent-definitions` rows whose `scope` is `tenant`. One of bleqq's own agents "
            "is refused with `permission_denied` naming `agent_definitions.manage`; a key no "
            "definition has is refused with `unknown_key`."
        ),
    )
    cadence: Cadence = Field(default="weekly", description=f"How often the agent runs, by default `weekly`. {_CADENCE}")
    run_weekday: int | None = Field(
        default=None,
        ge=1,
        le=7,
        description="The day a weekly or monthly run starts, a minimum of 1 (Monday) and a maximum of 7 (Sunday); by default null.",
    )
    run_hour: int | None = Field(
        default=None,
        ge=0,
        le=23,
        description="The hour, in the bank's own time zone, a scheduled run starts, a minimum of 0 and a maximum of 23; by default null.",
    )
    scope: TenantAgentScope = Field(
        default_factory=TenantAgentScope,
        description="What the agent looks at, by keys; by default empty, which means the bank's markets.",
    )


class TenantAgentUpdate(WriteBody):
    """`PATCH /agents/{tenantAgentId}`: change what the body sends and nothing else."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"enabled": True, "cadence": "daily"}]})

    enabled: bool | None = Field(default=None, description="Switch the agent on or off; by default null, which leaves it.")
    cadence: Cadence | None = Field(default=None, description=f"The new cadence; by default null, which leaves it. {_CADENCE}")
    run_weekday: int | None = Field(
        default=None, ge=1, le=7, description="The new run day, a minimum of 1 (Monday) and a maximum of 7 (Sunday); by default null, which leaves it."
    )
    run_hour: int | None = Field(
        default=None, ge=0, le=23, description="The new run hour, a minimum of 0 and a maximum of 23; by default null, which leaves it."
    )
    scope: TenantAgentScope | None = Field(default=None, description="The new scope, whole; by default null, which leaves it.")


class TenantRunQuery(PageQuery):
    """`GET /agent-runs`: the shared page, narrowed to one of the bank's agents or the
    caller's own requests (ruling 9)."""

    tenant_agent_id: uuid.UUID | None = Field(
        default=None,
        alias="tenantAgentId",
        description=(
            "Only the runs of this one of the bank's own agents, by its UUID identifier; by "
            "default null, which filters nothing. Another bank's agent matches no run."
        ),
    )
    mine: bool = Field(
        default=False,
        description="Only the runs the caller asked for with run now or a research request; by default false, which filters nothing.",
    )


class AgentRunListItem(AgentRunOut):
    """One run in the run log, with what chunk 11 adds: which of the bank's agents ran, which
    version, what started it, who asked, what it cost, and whether it was stopped."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_LIST_RUN]})

    tenant_agent_id: uuid.UUID | None = Field(
        description="The bank's own agent that ran, as a UUID, or null for one of bleqq's library runs."
    )
    agent_version: int | None = Field(
        description="The number of the definition version the run opened with, or null for a run opened before versions were kept."
    )
    trigger: Trigger = Field(
        description=(
            "What started the run. `schedule`: its cadence. `manual`: a person chose run now. "
            "`request`: a research request. `api`: a platform agent's key opened it."
        )
    )
    requested_by: PersonRef | None = Field(
        description="The person who asked for the run, by id and name, or null when nobody did (a schedule or a key)."
    )
    cost: Decimal | None = Field(
        description=f"What the run cost, {_MONEY}. Null while it runs or when nothing was reported."
    )
    interrupted_at: datetime | None = Field(
        description="When someone stopped the run, as a UTC timestamp in ISO 8601, or null when nobody did."
    )


class AgentRunListPage(CamelSchema):
    """`{items, total}` with `limit` and `offset` (playbook 10)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_EXAMPLE_LIST_RUN], "total": 1}]})

    items: list[AgentRunListItem] = Field(
        description=(
            "The runs on this page, oldest first. A bank's session sees bleqq's library runs and "
            "its own; the console sees the library's. An empty list is a 200, never an error."
        )
    )
    total: int = Field(description="How many runs this caller may see in total, not how many are on this page.")


class AgentBudget(CamelSchema):
    """The bank's one monthly cap on its own agents, and what they spent this month
    (AGT-04, ruling 3). bleqq's own agents run at bleqq's cost and are never in it."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"monthlyCap": "500.00", "currency": "EUR", "spentThisMonth": "212.40"}]})

    monthly_cap: Decimal | None = Field(description=f"The cap, {_MONEY}. Null when the bank has set none.")
    currency: Literal["EUR"] = Field(description="The currency of every amount here: `EUR`, the one currency agents are billed in.")
    spent_this_month: Decimal = Field(
        description=(
            f"What the bank's own agents cost in the current calendar month of the bank's time zone, {_MONEY}. "
            "No run of bleqq's own agents is in it."
        )
    )


class AgentBudgetInput(WriteBody):
    """`PUT /tenant/agent-budget`: set the bank's monthly cap."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"monthlyCap": "500.00"}]})

    monthly_cap: Decimal = Field(
        ge=0,
        max_digits=10,
        decimal_places=2,
        description=f"The new cap, {_MONEY}, with a minimum of 0. A run that would pass it does not start.",
    )


class ResearchRequestOut(CamelSchema):
    """A request for work by one of the bank's own agents (AGT-05)."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_REQUEST]})

    id: uuid.UUID = Field(description="The request's identifier, a UUID. Another bank's request answers 404.")
    kind: Literal["run_now", "check_source", "check_url", "research_topic", "retag"] = Field(
        description=(
            "What was asked. `run_now`: run the agent once now. `check_source`: check one "
            "registered source now. `check_url`: check one web address now. `research_topic`: "
            "research the topic named. `retag`: the console's request to re-tag library "
            "records, answered by a batch proposal and never a direct edit."
        )
    )
    tenant_agent_id: uuid.UUID | None = Field(
        description="The bank's own agent asked to do it, as a UUID, or null for the console's `retag`, which has none."
    )
    topic: str | None = Field(description="The topic to research, as the bank wrote it, or null for another kind.")
    source_id: uuid.UUID | None = Field(description="The registered source to check, as a UUID, or null for another kind.")
    url: str | None = Field(description="The web address to check, an https URL, or null for another kind.")
    status: RequestState = Field(
        description=(
            "Where the request stands. `queued`: waiting for its run. `running`: its run is "
            "open. `done`: the run finished. `failed`: the run failed. `rejected`: refused "
            "before it ran, such as at the budget cap. `cancelled`: withdrawn before it ran."
        )
    )
    requested_by: PersonRef = Field(description="The person who made the request, by id and name.")
    created_at: datetime = Field(description="When the request was made, as a UTC timestamp in ISO 8601.")
    completed_at: datetime | None = Field(
        description="When its run finished, as a UTC timestamp in ISO 8601, or null while it has not."
    )


class ResearchRequestPage(CamelSchema):
    """`{items, total}` with `limit` and `offset` (playbook 10)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_EXAMPLE_REQUEST], "total": 1}]})

    items: list[ResearchRequestOut] = Field(description="The bank's research requests on this page, newest first.")
    total: int = Field(description="How many requests the bank has made in total, not how many are on this page.")


class ResearchRequestInput(WriteBody):
    """`POST /research-requests`: ask one of the bank's own agents for work (AGT-05)."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"kind": "research_topic", "tenantAgentId": _EXAMPLE_TENANT_AGENT_ID, "topic": "DORA subcontracting"}]}
    )

    kind: RequestKind = Field(
        description=(
            "What to ask for. `run_now`: run the agent once now. `check_source`: check the "
            "registered source in `sourceId`. `check_url`: check the web address in `url`. "
            "`research_topic`: research the text in `topic`."
        )
    )
    tenant_agent_id: uuid.UUID = Field(
        description="The bank's own agent to ask, as a UUID. Another bank's agent answers 404."
    )
    topic: str | None = Field(
        default=None,
        min_length=1,
        max_length=settings.AGENT_RESEARCH_TOPIC_MAX_CHARS,
        description=(
            f"The topic for `research_topic`, between 1 and {settings.AGENT_RESEARCH_TOPIC_MAX_CHARS} "
            "characters; by default null. It is the bank's own text: it is never logged."
        ),
    )
    source_id: uuid.UUID | None = Field(
        default=None, description="The registered source for `check_source`, as a UUID; by default null."
    )
    url: str | None = Field(
        default=None,
        max_length=2000,
        description="The https web address for `check_url`, at most 2000 characters; by default null.",
    )


class PlatformWatchLastRun(CamelSchema):
    """How the last run of one of bleqq's agents ended, and nothing else about it."""

    finished_at: datetime | None = Field(
        description="When the last run finished, as a UTC timestamp in ISO 8601, or null while it is still running."
    )
    status: Literal["running", "succeeded", "failed"] = Field(
        description="How it ended. `running`: still going. `succeeded`: it finished. `failed`: it stopped early."
    )


class PlatformWatchItem(CamelSchema):
    """What one of bleqq's agents watches, as any member reads it (ruling 6): public facts
    about the platform's coverage and never a prompt, tool, model, version, budget, cost,
    finding, proposal count or setting."""

    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE_WATCH]})

    key: str = Field(description="The agent's stable key, such as `watch-sweeper`.")
    name: str = Field(description="The agent's name as a screen shows it, for display only.")
    purpose: str = Field(description="What the agent watches for, in one or two sentences, for display only.")
    jurisdictions: list[str] = Field(description=f"The jurisdictions it sweeps. {_JURISDICTION_KEYS}")
    cadence: Cadence = Field(description=f"How often it runs. {_CADENCE}")
    next_run_at: datetime | None = Field(
        description="When its next run starts, as a UTC timestamp in ISO 8601, or null when none is scheduled."
    )
    last_run: PlatformWatchLastRun | None = Field(
        description="How its last run ended, or null when it has never run."
    )


class PlatformWatchPage(CamelSchema):
    """`{items, total}` with `limit` and `offset` (playbook 10)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_EXAMPLE_WATCH], "total": 1}]})

    items: list[PlatformWatchItem] = Field(description="bleqq's agents on this page, by key. The same for every bank.")
    total: int = Field(description="How many of bleqq's agents there are in total, not how many are on this page.")
