"""The bank's one monthly cap on its own agents (AGT-04, ruling 3). bleqq's agents run at
bleqq's cost and no figure here includes them (D-61): the spend is the sum of what the
bank's own agents' runs cost in the current calendar month of the bank's own time zone.

`spend`, `at_cap` and `cap_of` are what the scheduler, the controls and research requests
read before a run starts. The cap row is created on the first write. A cap at or below the
month's spend is accepted, because a bank must always be able to stop spending, and it
pauses the bank's running agents at once through `tenant_agents.pause`.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from django.db.models import Sum
from django.utils import timezone

from apps.agents.models import AgentRun, TenantAgent, TenantAgentBudget
from apps.agents.schemas import AgentBudgetInput
from apps.agents.tenant_agents import lock_tenant, pause
from apps.identity.models import User
from apps.shared.audit import Actor, ActorType, record
from apps.shared.authentication import Principal
from apps.shared.models import Tenant

SUBJECT_TYPE = "tenant_agent_budget"
CAP_REASON = "budget_cap"
ZERO = Decimal("0.00")


def _month(tenant: Tenant) -> tuple[datetime.datetime, datetime.datetime]:
    """The current calendar month of the bank's own time zone, as a half-open UTC range."""
    zone = ZoneInfo(tenant.timezone)
    first = timezone.now().astimezone(zone).date().replace(day=1)
    following = (first + datetime.timedelta(days=32)).replace(day=1)

    def start(day: datetime.date) -> datetime.datetime:
        return datetime.datetime.combine(day, datetime.time.min, tzinfo=zone).astimezone(datetime.UTC)

    return start(first), start(following)


def spend(tenant: Tenant) -> Decimal:
    """What the bank's own agents' runs cost this month. Only a run of one of the bank's own
    agents counts: a platform run has no `tenant_agent`, so it is never in it."""
    start, end = _month(tenant)
    total = AgentRun.objects.filter(
        tenant_id=tenant.id, tenant_agent__isnull=False, started_at__gte=start, started_at__lt=end
    ).aggregate(total=Sum("cost"))["total"]
    return ZERO if total is None else Decimal(total).quantize(ZERO)


def cap_of(tenant: Tenant) -> Decimal | None:
    """The bank's monthly cap, or None when it has set none."""
    return TenantAgentBudget.objects.filter(tenant=tenant).values_list("monthly_cap", flat=True).first()  # ordering: one row per tenant, by constraint


def at_cap(tenant: Tenant) -> bool:
    """Whether no run of the bank's own agents may start: no cap set yet, or the month's
    spend has reached it."""
    cap = cap_of(tenant)
    return cap is None or spend(tenant) >= cap


def _out(tenant: Tenant) -> dict[str, Any]:
    return {"monthly_cap": cap_of(tenant), "currency": "EUR", "spent_this_month": spend(tenant)}


def get_budget(*, tenant: Tenant) -> dict[str, Any]:
    """`GET /tenant/agent-budget`. Reads; writes nothing, not even the cap row."""
    return _out(tenant)


def put_budget(*, who: Principal, tenant: Tenant, body: AgentBudgetInput) -> dict[str, Any]:
    """`PUT /tenant/agent-budget`: set the cap, creating the row on the first write. At or
    below the month's spend it pauses every running agent of the bank's own at once."""
    lock_tenant(tenant, SUBJECT_TYPE)
    user = User.objects.get(pk=who.subject_id)
    row = TenantAgentBudget.objects.filter(tenant=tenant).first()  # ordering: one row per tenant, by constraint
    before = None if row is None else {"monthlyCap": str(row.monthly_cap), "currency": row.currency}
    if row is None:
        row = TenantAgentBudget(tenant=tenant)
    row.monthly_cap = body.monthly_cap
    row.updated_by = user
    row.save()
    record(
        action="agents.budget_set",
        actor=Actor(kind=ActorType.USER, id=user.id, label=user.name),
        subject_type=SUBJECT_TYPE,
        subject_id=row.id,
        subject_title="monthly cap",
        summary="Set the monthly cap on the bank's own agents.",
        tenant_id=tenant.id,
        before=before,
        after={"monthlyCap": str(row.monthly_cap), "currency": row.currency},
    )
    if at_cap(tenant):
        for agent in TenantAgent.objects.filter(tenant=tenant, enabled=True, paused_at__isnull=True).select_related("agent"):
            pause(agent, CAP_REASON)
    return _out(tenant)
