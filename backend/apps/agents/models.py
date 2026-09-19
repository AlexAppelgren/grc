"""Agent and run records (AGT-01, AGT-03, schema v0.3 `agent` and `agent_run`).

`Agent` is a library row: the platform's versioned definitions in
`backend/agents/<agent>/v<n>/` are loaded into it by the reference seed, and nothing else
writes it. `AgentRun` is the provenance anchor of everything an agent writes, and a mixed
table: a platform run for the shared library has `tenant_id` NULL and is visible to every
tenant, a tenant's own run only to that tenant, and each is written only from its own
zone (playbook 14, INPUT_DELTAS §5, agents migration 0001).

R1 columns only. The version rows, tenant controls, research requests and the cost and
token columns of schema v0.3 arrive with chunk 11 (AGT-03 to AGT-06).
"""

from __future__ import annotations

import enum
import uuid
from typing import Any

from django.db import models

from apps.shared.tenancy import LibraryModel
from apps.shared.vocabulary import KeyIsImmutable


class AgentKind(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): what an agent definition does.

    `watch` is ours: schema v0.3 stops at research, backfill and reverify, and the first
    shipped definition sweeps registered sources (INPUT_DELTAS §5).
    """

    RESEARCH = "research"
    BACKFILL = "backfill"
    REVERIFY = "reverify"
    WATCH = "watch"


AGENT_KIND_CHOICES = [(kind.value, kind.value) for kind in AgentKind]


class RunStatus(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): the run lifecycle the scheduler branches on."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


RUN_STATUS_CHOICES = [(status.value, status.value) for status in RunStatus]


class Agent(LibraryModel):
    """One research agent, owned by the platform (AGT-03). `key` is the definition's `id`
    and never changes; `current_version` is the version folder the seed loaded."""

    key = models.SlugField(max_length=80, unique=True)
    kind = models.CharField(max_length=16, choices=AGENT_KIND_CHOICES)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=False)
    current_version = models.PositiveIntegerField()

    class Meta:
        db_table = "agent"
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key

    def save(self, *args: Any, **kwargs: Any) -> None:  # compliance: allow-kwargs Django Model.save signature
        # Stable keys never change (playbook 4.3); a trigger refuses what skips this method.
        if not self._state.adding:
            stored = (
                type(self)._default_manager.filter(pk=self.pk).values_list("key", flat=True).first()
            )  # ordering: pk lookup, at most one row
            if stored is not None and stored != self.key:
                raise KeyIsImmutable("An agent key never changes; publish a new version instead.", code="key_immutable")
        super().save(*args, **kwargs)


class AgentRun(models.Model):
    """One execution (AGT-01): what an agent wrote points at the run that wrote it.

    `tenant` NULL is a platform run for the shared library. It is always the key's tenant:
    a platform key opens library runs, a tenant's key that tenant's runs, and the write
    policy refuses any other pairing. `idempotency_key` is the retry key of the call that
    opened the run, unique per API key, so a retried `POST /agent-runs` returns the run it
    already opened instead of a second one.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey(Agent, on_delete=models.PROTECT, related_name="runs")
    api_key = models.ForeignKey("identity.ApiKey", on_delete=models.PROTECT, related_name="agent_runs")
    tenant = models.ForeignKey("shared.Tenant", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=RUN_STATUS_CHOICES, default=RunStatus.RUNNING.value)
    model = models.CharField(max_length=120)
    pipeline_version = models.CharField(max_length=40)
    stats = models.JSONField(default=dict, blank=True)  # schema: AgentRunStats
    output_ref = models.CharField(max_length=500, blank=True)
    error = models.TextField(blank=True)
    idempotency_key = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = "agent_run"
        ordering = ["started_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["api_key", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="agent_run_idempotency_unique",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "-started_at"], name="agent_run_tenant_idx")]

    def __str__(self) -> str:
        return f"{self.agent_id}:{self.id}"

    def save(self, *args: Any, **kwargs: Any) -> None:  # compliance: allow-kwargs Django Model.save signature
        self.tenant_id = self.api_key.tenant_id
        super().save(*args, **kwargs)
