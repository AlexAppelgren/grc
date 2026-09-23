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
from typing import Literal

from ninja import Field
from pydantic import ConfigDict, JsonValue

from apps.shared.schemas import CamelSchema, WriteBody

__all__ = [
    "AgentDefinitionOut",
    "AgentDefinitionPage",
    "AgentRunFinish",
    "AgentRunInput",
    "AgentRunOut",
    "AgentRunPage",
    "AgentRunStats",
    "CamelSchema",
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
    defaults of its definition (`backend/agents/<agent>/v<n>/definition.yaml`)."""

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
            "that something was found. Defaults to 0."
        ),
    )
    changes_registered: int = Field(
        default=0,
        description=(
            "How many regulatory changes the run put on the watch feed, counted against the "
            "change budget in the agent's definition. A change is a sighting the bank has yet "
            "to judge: it is not an obligation, it is not applicability and it is not a "
            "decision, and nothing in the inventory moves until a person acts on it. Defaults "
            "to 0."
        ),
    )
    proposals_submitted: int = Field(
        default=0,
        description=(
            "How many proposals the run put in the queue for the shared library, counted "
            "against the proposal budget in the agent's definition. A proposal is the only "
            "door an agent has into the library and it changes nothing until it is approved, "
            "so read this as a count of requests and never of library edits. Defaults to 0."
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


class AgentRunPage(CamelSchema):
    """`{items, total}` with `limit` and `offset`, not the designed cursor page (playbook 10)."""

    model_config = ConfigDict(json_schema_extra={"examples": [{"items": [_EXAMPLE_FINISHED_RUN], "total": 1}]})

    items: list[AgentRunOut] = Field(
        description=(
            "The runs on this page, oldest first, so a reader follows a sweep in the order it "
            "happened. A person signed in to a bank sees the platform's own library runs and "
            "that bank's own runs, never another bank's. An empty list is a 200 and means "
            "nothing has run yet; it is never an error."
        )
    )
    total: int = Field(
        description=(
            "How many runs this caller may see in total, not how many are on this page — use "
            "it to size a pager. It counts only what this caller is allowed to read, so two "
            "banks asking the same question will get different totals for the same platform."
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
