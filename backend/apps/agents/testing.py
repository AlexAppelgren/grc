"""Agent builders for tests (playbook 8.1): a platform definition, a key bound to it, a
platform run, and a definition a bank may add.

`Agent` is a library row, written inside `library_write()`, which the library fence allows a
`testing.py` module. `platform_run()` refuses a tenant-bound key, since `AgentRun.save()`
copies the key's tenant and would quietly make a tenant run.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from collections.abc import Iterable
from typing import Any

from apps.agents.models import Agent, AgentKind, AgentRun, AgentScopeKind, AgentWritesTo, RunStatus
from apps.identity import tokens
from apps.identity.models import ApiKey
from apps.shared.models import Tenant
from apps.shared.adapters.agent_runner import RunHandle, RunnerEvent
from apps.shared.tenancy import library_write

REASON = "test builder"

# What the first shipped definition is (backend/agents/watch-sweeper/v1/), so a test reads
# the same names a run would.
SWEEPER_KEY = "watch-sweeper"
SWEEPER_MODEL = "agent pipeline 0.4"
SWEEPER_PIPELINE = "0.4"
# The scopes a platform watch key holds (ID-10); none reaches an inventory table.
WATCH_SCOPES: tuple[str, ...] = ("agent-runs:write", "sources:write", "changes:write", "library:read")


def agent(*, key: str | None = None, kind: AgentKind = AgentKind.WATCH, version: int = 1) -> Agent:
    """A platform agent definition. `key` is the definition's id and never changes."""
    with library_write(REASON):
        return Agent.objects.create(
            key=key or f"{SWEEPER_KEY}-{uuid.uuid4().hex[:6]}",
            kind=kind.value,
            description="Sweeps the registered sources for new regulation.",
            active=True,
            current_version=version,
        )


def tenant_definition(key: str = "bank-watch") -> Agent:
    """A definition a bank may add as its own agent: tenant-scoped, configurable, writing
    in the bank's zone. Shared by every bank that adds it, so it is fetched when it exists."""
    with library_write(REASON):
        row, _ = Agent.objects.get_or_create(
            key=key,
            defaults={
                "kind": AgentKind.RESEARCH.value,
                "current_version": 1,
                "scope": AgentScopeKind.TENANT.value,
                "tenant_configurable": True,
                "writes_to": AgentWritesTo.TENANT.value,
            },
        )
    return row

def agent_key(*, agent_row: Agent | None = None, scopes: Iterable[str] = WATCH_SCOPES) -> SimpleNamespace:
    """A live platform key bound to an agent: `.id`, `.row` (the ApiKey), `.agent` and
    `.plain_key` (the value a caller sends as `X-Api-Key`, shown once).

    No tenant: an agent-bound key is the platform's (ID-10), written with no tenant active
    (H15).
    """
    row_agent = agent_row if agent_row is not None else agent()
    plain, prefix, key_hash = tokens.new_api_key()
    row = ApiKey.objects.create(
        tenant=None, agent=row_agent, name=f"{row_agent.key} key", key_prefix=prefix, key_hash=key_hash, scopes=list(scopes)
    )
    return SimpleNamespace(id=row.id, row=row, agent=row_agent, plain_key=plain)


def reviewer_api_key(*, scopes: Iterable[str] = ("proposals:review",)) -> SimpleNamespace:
    """A platform key bound to its own agent definition, holding `scopes` (PRO-S13, ID-S31,
    D-62, ADR 0054): a second, independent agent that can work the review queue. A thin
    wrapper over `agent_key()` so every review-queue test asks for the same shape by name."""
    return agent_key(scopes=scopes)


def platform_run(
    *, key: SimpleNamespace | None = None, model: str = SWEEPER_MODEL, pipeline_version: str = SWEEPER_PIPELINE
) -> AgentRun:
    """One run of a platform agent, the provenance anchor of everything it writes. Opened
    with a platform key, because in R1 no tenant opens a run."""
    opened_with = key if key is not None else agent_key()
    if opened_with.row.tenant_id is not None:
        raise ValueError(
            "A platform run is opened with a platform key. In R1 bleqq's agents are "
            "platform-owned and no tenant opens a run (AGT-01, item 14)."
        )
    return AgentRun.objects.create(
        agent=opened_with.agent, api_key=opened_with.row, model=model, pipeline_version=pipeline_version
    )


# The model call behind a confirming agent's decision, as the agent reports it (D-80): the
# `AgentDecision` shape, camelCase as a request body carries it, with one public citation.
DECISION: dict[str, Any] = {
    "model": "claude-opus-5",
    "modelVersion": "2026-05-01",
    "promptTemplate": "library-confirmer/decide/v2",
    "promptHash": "9f2a1c7d4b8e05f3",
    "output": "Approve. The proposed wording matches the amended regulation as the decision memorandum publishes it.",
    "citations": [
        {
            "label": "Finansinspektionen, decision memorandum FI Dnr 25-12345",
            "url": "https://www.fi.se/en/published/news/2026/reporting/",
        }
    ],
}
# The same call when its verdict is a rejection, so a logged rejection never reads as an
# approval: every rejection a test expects to land carries this one.
REJECTION_DECISION: dict[str, Any] = {
    **DECISION,
    "output": "Reject. The version in force already says this, in the words the decision memorandum uses.",
}


def decision(key: SimpleNamespace) -> dict[str, Any]:
    """What a confirming agent's approve or reject body carries (D-80, AUD-02, AGT-01): the
    model call and a fresh run of its own key. A rejection overrides `decision` with
    `REJECTION_DECISION`."""
    return {"decision": DECISION, "agentRunId": str(platform_run(key=key).id)}


def tenant_key(tenant: Tenant, *, scopes: Iterable[str] = ("library:read",)) -> SimpleNamespace:
    """A bank's own key, for the tests that prove what such a key may *not* do: open a run,
    register a change or log a source check. It is never bound to an agent."""
    from apps.shared import factories

    return factories.api_key(tenant, name="Bank key", scopes=scopes)


def mock_run_events(handle: RunHandle) -> list[RunnerEvent]:
    """What a mock run reports: one progress event, then success with no findings, or that it
    was interrupted. Every number is drawn from a generator seeded with the run id, so the
    same run reports the same events and a test never depends on the clock."""
    seeded = random.Random(handle.run_id.int)  # noqa: S311 - a test double's numbers, not a secret
    tokens_in, tokens_out, cents = seeded.randint(1_000, 50_000), seeded.randint(100, 5_000), seeded.randint(1, 500)
    progress = RunnerEvent(
        run_id=handle.run_id, status=RunStatus.RUNNING, cost=Decimal(cents) / 200, tokens_in=tokens_in // 2, tokens_out=tokens_out // 2
    )
    if handle.status is RunStatus.INTERRUPTED:
        return [replace(progress, status=RunStatus.INTERRUPTED)]
    return [progress, replace(progress, status=RunStatus.SUCCEEDED, cost=Decimal(cents) / 100, tokens_in=tokens_in, tokens_out=tokens_out)]
