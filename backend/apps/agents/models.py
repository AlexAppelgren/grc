"""Agent and run records (AGT-01, AGT-03, schema v0.3 `agent` and `agent_run`).

`Agent` is a library row: the platform's versioned definitions in
`backend/agents/<agent>/v<n>/` are loaded into it by the reference seed, and nothing else
writes it. `AgentRun` is the provenance anchor of everything an agent writes, and a mixed
table: a platform run for the shared library has `tenant_id` NULL and is visible to every
tenant, a tenant's own run only to that tenant, and each is written only from its own
zone (playbook 14, INPUT_DELTAS §5, agents migration 0001).

Chunk 11 (AGT-03 to AGT-06, agents 0004 and 0005) adds schema v0.3's platform and tenant
agent data. Every definition is bleqq's; `scope` says whether it is one of bleqq's own agents
or one a bank may add for itself, and the database refuses a bank's `tenant_agent` on any
other (ruling 1, ADR 0053). A published `agent_version` is never rewritten: a run points at
the version it opened with. A bank's agents, its research requests and its one monthly cap
are tenant rows; a request with no tenant is the console's `retag`.

Agent access (ACC-01, ACC-02, agents 0006) is not an agent we run: `AgentAccess` registers
an agent a bank runs on its own infrastructure, which reads through a credential and
nothing else, narrowed by the departments and products its join rows name.
"""

from __future__ import annotations

import enum
import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models

from apps.shared.tenancy import LibraryModel, TenantModel
from apps.shared.vocabulary import KeyIsImmutable


class AgentKind(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): what an agent definition does.

    `watch` is ours: schema v0.3 stops at research, backfill and reverify, and the first
    shipped definition sweeps registered sources (INPUT_DELTAS §5).

    `review` is ours too: a definition that proposes nothing and decides what another
    definition proposed, as the independent second principal on the library's queue
    (D-62, D-80). The first is `backend/agents/library-confirmer/v1/`.
    """

    RESEARCH = "research"
    BACKFILL = "backfill"
    REVERIFY = "reverify"
    WATCH = "watch"
    REVIEW = "review"


AGENT_KIND_CHOICES = [(kind.value, kind.value) for kind in AgentKind]


class RunStatus(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): the run lifecycle the scheduler branches on."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


RUN_STATUS_CHOICES = [(status.value, status.value) for status in RunStatus]


class AgentScopeKind(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): one of bleqq's agents or one a bank adds."""

    PLATFORM = "platform"
    TENANT = "tenant"


class AgentCadence(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): how often the scheduler starts an agent."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    MANUAL = "manual"


class AgentRuntime(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): which runner executes a definition (D-54)."""

    AGENT_SDK = "agent_sdk"
    MANAGED_AGENTS = "managed_agents"
    ROUTINE = "routine"


class AgentWritesTo(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): the zone an agent's output lands in."""

    LIBRARY = "library"
    TENANT = "tenant"


class RunTrigger(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): what started a run."""

    SCHEDULE = "schedule"
    MANUAL = "manual"
    REQUEST = "request"
    API = "api"


class ResearchRequestKind(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): what a research request asks for (AGT-05)."""

    RUN_NOW = "run_now"
    CHECK_SOURCE = "check_source"
    CHECK_URL = "check_url"
    RESEARCH_TOPIC = "research_topic"
    RETAG = "retag"


class ResearchRequestStatus(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): a research request's lifecycle."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


def _choices(kind: type[enum.StrEnum]) -> list[tuple[str, str]]:
    return [(member.value, member.value) for member in kind]


class Agent(LibraryModel):
    """One research agent, owned by the platform (AGT-03). `key` is the definition's `id`
    and never changes; `current_version` is the version folder the seed loaded."""

    key = models.SlugField(max_length=80, unique=True)
    kind = models.CharField(max_length=16, choices=AGENT_KIND_CHOICES)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=False)
    current_version = models.PositiveIntegerField()
    scope = models.CharField(max_length=16, choices=_choices(AgentScopeKind), default=AgentScopeKind.PLATFORM.value)
    tenant_configurable = models.BooleanField(default=False)
    runtime = models.CharField(max_length=16, choices=_choices(AgentRuntime), default=AgentRuntime.AGENT_SDK.value)
    default_cadence = models.CharField(max_length=16, choices=_choices(AgentCadence), default=AgentCadence.WEEKLY.value)
    writes_to = models.CharField(max_length=16, choices=_choices(AgentWritesTo), default=AgentWritesTo.LIBRARY.value)
    # What a platform agent carries in place of a bank's controls; a tenant row carries neither.
    platform_scope = models.JSONField(null=True, blank=True)  # schema: PlatformAgentScope
    platform_monthly_budget = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        db_table = "agent"
        ordering = ["key"]
        constraints = [
            # The platform fence starts here: one of bleqq's agents is never a bank's to steer.
            models.CheckConstraint(
                condition=~models.Q(scope=AgentScopeKind.PLATFORM.value, tenant_configurable=True),
                name="agent_platform_not_tenant_configurable",
            ),
            # A bank's kind of agent borrows no platform setting and never writes the library.
            models.CheckConstraint(
                condition=~models.Q(scope=AgentScopeKind.TENANT.value)
                | models.Q(
                    platform_scope__isnull=True,
                    platform_monthly_budget__isnull=True,
                    writes_to=AgentWritesTo.TENANT.value,
                ),
                name="agent_tenant_carries_no_platform_settings",
            ),
        ]

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


class AgentVersion(LibraryModel):
    """One published version of a definition (AGT-03). Append-only in the database: a run
    points at the version it opened with, so a version is never rewritten under it, and
    retiring it (`retired_at`) is the one change agents 0004 lets through. `prompt_path` is
    the prompt's file inside the version folder, never its body."""

    agent = models.ForeignKey(Agent, on_delete=models.PROTECT, related_name="versions")
    version_number = models.PositiveIntegerField()
    model = models.CharField(max_length=120)
    prompt_path = models.CharField(max_length=300)
    tools = models.JSONField(default=list, blank=True)  # schema: AgentToolList
    change_note = models.TextField(blank=True)
    published_by = models.ForeignKey(
        "identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    published_at = models.DateTimeField(auto_now_add=True)
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "agent_version"
        ordering = ["agent", "-version_number"]
        constraints = [models.UniqueConstraint(fields=["agent", "version_number"], name="agent_version_unique")]

    def __str__(self) -> str:
        return f"{self.agent_id}:v{self.version_number}"


class TenantAgent(TenantModel):
    """A bank's own agent (AGT-04): a tenant-scoped, tenant-configurable definition with the
    bank's own switch, cadence and scope. A trigger of agents 0005 refuses one on any other
    definition, and refuses a delete: an agent a bank stops is paused, never deleted. The
    one monthly cap is the bank's, on `TenantAgentBudget` (ruling 3)."""

    agent = models.ForeignKey(Agent, on_delete=models.PROTECT, related_name="tenant_agents")
    enabled = models.BooleanField(default=False)
    cadence = models.CharField(max_length=16, choices=_choices(AgentCadence), default=AgentCadence.WEEKLY.value)
    run_weekday = models.PositiveSmallIntegerField(null=True, blank=True)
    run_hour = models.PositiveSmallIntegerField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    scope = models.JSONField(default=dict, blank=True)  # schema: TenantAgentScope
    paused_at = models.DateTimeField(null=True, blank=True)
    paused_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    pause_reason = models.TextField(blank=True)
    updated_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenant_agent"
        ordering = ["tenant", "agent"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "agent"], name="tenant_agent_unique"),
            models.CheckConstraint(
                condition=models.Q(run_weekday__isnull=True) | models.Q(run_weekday__gte=1, run_weekday__lte=7),
                name="tenant_agent_run_weekday_range",
            ),
            models.CheckConstraint(
                condition=models.Q(run_hour__isnull=True) | models.Q(run_hour__lte=23),
                name="tenant_agent_run_hour_range",
            ),
        ]
        indexes = [
            models.Index(
                fields=["next_run_at"],
                condition=models.Q(enabled=True, paused_at__isnull=True),
                name="tenant_agent_due_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.tenant_id}:{self.agent_id}"


class ResearchRequest(models.Model):
    """A request for agent work (AGT-05). A mixed table with agent_run's split policy: a bank
    asks one of its own agents (`tenant` and `tenant_agent` set), and the platform console
    asks for a `retag` of library records (neither set), whose answer is a batch proposal,
    never a direct edit. `batch_proposal_id` names that batch; its foreign key arrives with
    the batch table (c11-proposal-batches-model)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("shared.Tenant", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    tenant_agent = models.ForeignKey(
        TenantAgent, null=True, blank=True, on_delete=models.PROTECT, related_name="research_requests"
    )
    requested_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=16, choices=_choices(ResearchRequestKind))
    topic = models.TextField(blank=True)
    source = models.ForeignKey("watch.Source", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    url = models.URLField(max_length=2000, blank=True)
    status = models.CharField(
        max_length=16, choices=_choices(ResearchRequestStatus), default=ResearchRequestStatus.QUEUED.value
    )
    result_summary = models.TextField(blank=True)
    batch_proposal_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "research_request"
        ordering = ["-created_at", "id"]
        constraints = [
            # A bank asks its own agent; only the console's retag has no tenant (ADR 0053).
            models.CheckConstraint(
                condition=models.Q(kind=ResearchRequestKind.RETAG.value, tenant__isnull=True, tenant_agent__isnull=True)
                | (
                    ~models.Q(kind=ResearchRequestKind.RETAG.value)
                    & models.Q(tenant__isnull=False, tenant_agent__isnull=False)
                ),
                name="research_request_zone",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "-created_at"], name="research_request_tenant_idx")]

    def __str__(self) -> str:
        return f"{self.kind}:{self.id}"


class TenantAgentBudget(TenantModel):
    """The bank's one monthly cap on its own agents (AGT-04, ruling 3): one row per tenant.
    Spend is summed from the month's `agent_run.cost`; there is no second ledger."""

    monthly_cap = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")
    updated_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenant_agent_budget"
        ordering = ["tenant"]
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="tenant_agent_budget_one_per_tenant"),
            models.CheckConstraint(condition=models.Q(monthly_cap__gte=0), name="tenant_agent_budget_not_negative"),
        ]

    def __str__(self) -> str:
        return f"{self.tenant_id}:{self.monthly_cap} {self.currency}"


class AgentRun(models.Model):
    """One execution (AGT-01): what an agent wrote points at the run that wrote it.

    `tenant` NULL is a platform run for the shared library. A run opened through the API
    lives in its key's zone: a platform key opens library runs, a tenant's key that
    tenant's runs, and the write policy refuses any other pairing. A run the worker opens
    has no key (a CHECK demands a key for `trigger = api` alone) and lives in its tenant
    agent's zone, or the library's when it has none. `idempotency_key` is the retry key of
    the call that opened the run, unique per API key, so a retried `POST /agent-runs`
    returns the run it already opened instead of a second one. `agent_version` is written
    once, when the run opens, and a trigger refuses changing it; counts stay in `stats`.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey(Agent, on_delete=models.PROTECT, related_name="runs")
    agent_version = models.ForeignKey(AgentVersion, null=True, blank=True, on_delete=models.PROTECT, related_name="runs")
    tenant_agent = models.ForeignKey(TenantAgent, null=True, blank=True, on_delete=models.PROTECT, related_name="runs")
    research_request = models.ForeignKey(
        ResearchRequest, null=True, blank=True, on_delete=models.PROTECT, related_name="runs"
    )
    api_key = models.ForeignKey(
        "identity.ApiKey", null=True, blank=True, on_delete=models.PROTECT, related_name="agent_runs"
    )
    trigger = models.CharField(max_length=16, choices=_choices(RunTrigger), default=RunTrigger.API.value)
    requested_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
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
    external_session_id = models.CharField(max_length=200, blank=True)
    budget_limit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # The scope the run was started with, copied at run start (D-32).
    scope = models.JSONField(default=dict, blank=True)  # schema: AgentRunScope
    interrupted_at = models.DateTimeField(null=True, blank=True)
    interrupted_by = models.ForeignKey(
        "identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    cost = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    tokens_in = models.BigIntegerField(null=True, blank=True)
    tokens_out = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "agent_run"
        ordering = ["started_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["api_key", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="agent_run_idempotency_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(api_key__isnull=False) | ~models.Q(trigger=RunTrigger.API.value),
                name="agent_run_api_run_has_a_key",
            ),
            models.CheckConstraint(
                condition=models.Q(tenant_agent__isnull=True) | models.Q(tenant__isnull=False),
                name="agent_run_tenant_agent_run_is_a_tenant_run",
            ),
        ]
        indexes = [models.Index(fields=["tenant", "-started_at"], name="agent_run_tenant_idx")]

    def __str__(self) -> str:
        return f"{self.agent_id}:{self.id}"

    def save(self, *args: Any, **kwargs: Any) -> None:  # compliance: allow-kwargs Django Model.save signature
        # The zone is derived, never the caller's: the key's, else the tenant agent's.
        if self.api_key is not None:
            self.tenant_id = self.api_key.tenant_id
        else:
            self.tenant_id = self.tenant_agent.tenant_id if self.tenant_agent is not None else None
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------------------
# Agent access (acc-foundation, agents 0006; ACC-01, ACC-02, D-70, ADR 0055)
# ---------------------------------------------------------------------------------------
class AgentAccess(TenantModel):
    """An agent a bank runs on its own infrastructure, registered so it can read (ACC-01).

    Not one of the agents we run: it holds no prompt, schedule or definition, and every
    credential under it reads and nothing else. Its scope is the terms of the departments
    and products it names intersected with the tenant footprint, computed per request and
    never stored (ACC-02, D-70); naming none narrows nothing. `tenant_reach` is the entry's
    half of D-72. Revoking sets `revoked_at` and clears `active`, which a CHECK keeps in
    step, and stops every credential under it; an entry is revoked, never deleted. Every
    reference is a composite `(tenant_id, …)` key (agents 0006), so an entry can name
    neither another bank's team, unit or product nor a person outside its own bank."""

    name = models.CharField(max_length=200)
    purpose = models.TextField()
    owner_team = models.ForeignKey("taxonomy.Team", on_delete=models.PROTECT, related_name="+")
    tenant_reach = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "agent_access"
        ordering = ["name", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(active=True, revoked_at__isnull=True, revoked_by__isnull=True)
                | models.Q(active=False, revoked_at__isnull=False),
                name="agent_access_revoked_is_inactive",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:  # compliance: allow-kwargs Django Model.delete signature
        raise ValidationError("An agent access entry is revoked, never deleted.", code="revoke_not_delete")


class AgentAccessDepartment(TenantModel):
    """A department an entry serves (ACC-02): an org unit of the same bank."""

    agent_access = models.ForeignKey(AgentAccess, on_delete=models.CASCADE, related_name="departments")
    department = models.ForeignKey("tenants.OrgUnit", on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "agent_access_department"
        ordering = ["agent_access", "department"]
        constraints = [
            models.UniqueConstraint(fields=["agent_access", "department"], name="agent_access_department_unique")
        ]


class AgentAccessProduct(TenantModel):
    """A product an entry serves (ACC-02): a product of the same bank."""

    agent_access = models.ForeignKey(AgentAccess, on_delete=models.CASCADE, related_name="products")
    product = models.ForeignKey("tenants.TenantProduct", on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "agent_access_product"
        ordering = ["agent_access", "product"]
        constraints = [models.UniqueConstraint(fields=["agent_access", "product"], name="agent_access_product_unique")]
