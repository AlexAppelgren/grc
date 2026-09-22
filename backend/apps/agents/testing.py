"""Agent builders for tests (playbook 8.1): a platform agent definition, a key bound to
it and a platform run to anchor everything that run writes.

`Agent` is a library row, so it is written inside `library_write()`. This module may do
that because the library fence exempts `testing.py` modules
(apps/shared/tests_library_fence.py), exactly as it exempts `apps/library/testing.py`;
`apps/shared/factories.py` is a production module to that guard and so never names a
library model beside a write.

R1 runs are platform runs and nothing else (AGT-01, Alex's item 14): bleqq's watch agents
are part of the base package, so the key that opens a run carries no tenant and the run it
opens carries none either. `AgentRun.save()` copies the key's tenant, so a tenant-bound
key here would quietly produce a tenant run; `platform_run()` refuses one rather than let
a test prove something about a shape R1 does not have.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from collections.abc import Iterable

from apps.agents.models import Agent, AgentKind, AgentRun
from apps.identity import tokens
from apps.identity.models import ApiKey
from apps.shared.models import Tenant
from apps.shared.tenancy import library_write

REASON = "test builder"

# What the first shipped definition is (backend/agents/watch-sweeper/v1/), so a test reads
# the same names a run would.
SWEEPER_KEY = "watch-sweeper"
SWEEPER_MODEL = "agent pipeline 0.4"
SWEEPER_PIPELINE = "0.4"
# The scopes a platform watch key holds in R1 (ID-10, PARALLEL_PLAN 7.2). No scope reaches
# an inventory table, and no tenant-created key carries any of them.
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


def agent_key(*, agent_row: Agent | None = None, scopes: Iterable[str] = WATCH_SCOPES) -> SimpleNamespace:
    """A live platform key bound to an agent: `.id`, `.row` (the ApiKey), `.agent` and
    `.plain_key` (the value a caller sends as `X-Api-Key`, shown once).

    No tenant: a key bound to an agent is the platform's, and no tenant route creates one
    (ID-10, rule 13). It is written with no tenant activated, which is the only session the
    mixed write rule accepts a platform row from (hardening H15).
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


def tenant_key(tenant: Tenant, *, scopes: Iterable[str] = ("library:read",)) -> SimpleNamespace:
    """A bank's own key, for the tests that prove what such a key may *not* do: open a run,
    register a change or log a source check. It is never bound to an agent."""
    from apps.shared import factories

    return factories.api_key(tenant, name="Bank key", scopes=scopes)
