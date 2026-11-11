"""An approved scope item opens research by the bank's own agent (OWN-02, AGT-05; D-89, D-91,
D-98, ADR 0059, ADR 0061).

- Opening: `open_research` handles `scope_item.added` in the bank's zone and opens one
  `scope_item` request with its run for the bank's `scope-researcher`, through the one
  opener, no API key. With no such agent on (`no_tenant_agent`), AI off (`feature_off`) or
  the cap reached (`budget_cap_reached`) it opens nothing and audits
  `scope_item.research_waiting`. Once per item (a unique index too). The approver is the
  person it is asked for by.
- What reaches the model is `run_input` alone (D-98's second exception): the item's id, key,
  jurisdiction and regime term keys, and its name, reference and address, each capped at
  `SCOPE_RESEARCH_TEXT_MAX_CHARS` and screened (AGT-07), only for the bank's own running
  research run with AI on, through the logged wrapper. Never the description, another item
  or any bank record (D-57).
- Nothing typed is logged: audit rows carry ids, keys and flags.
- What comes back goes through `runner_events.apply_finding` to `proposals/tenant_agent.py`;
  nothing here writes the scope (`tests_scope_research.NoRunWritesTheScope`).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, cast

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.agents import budget, tasks
from apps.agents.models import AgentRun, ResearchRequest, ResearchRequestKind, ResearchRequestStatus, RunStatus, TenantAgent
from apps.agents.screen import screen_all
from apps.identity.models import User
from apps.shared import ai, outbox
from apps.shared.audit import Actor, batched, record
from apps.shared.errors import ProblemError
from apps.shared.models import OutboxEvent, Tenant
from apps.taxonomy import footprint_logic
from apps.taxonomy.models import ScopeItemStatus

logger = logging.getLogger(__name__)

SCOPE_ITEM_ADDED = "scope_item.added"
# The bleqq-authored, tenant-scoped definition that researches a scope item.
RESEARCHER = "scope-researcher"
ACTOR = Actor.system("scope research")
# The item's audit subject, spelled as taxonomy's `footprint_logic` spells it.
SCOPE_ITEM_SUBJECT = "scope_item"


def register() -> None:
    """Put the handler on the one cursor, from the app's `ready()`; safe to call again."""
    outbox.register_handler(SCOPE_ITEM_ADDED, open_research)


def _waiting_because(tenant: Tenant, tenant_agent: TenantAgent | None) -> str | None:
    """Why the research cannot open now, as a key, or None when it can."""
    if tenant_agent is None:
        return "no_tenant_agent"
    try:
        ai.ensure_enabled()
    except ProblemError as off:
        return off.code
    if budget.at_cap(tenant):
        return "budget_cap_reached"
    return None


@batched()
def open_research(event: OutboxEvent) -> None:
    """Open the research of the scope item `event` names, in the bank's zone, or record why
    it waits."""
    try:
        if event.tenant_id is None:
            raise ValueError("a scope item is always a bank's")
        item = footprint_logic.scope_item(event.tenant_id, uuid.UUID(str(event.payload.get("scopeItemId"))))
    except (ValueError, ValidationError):
        # Nothing to research and nothing worth holding the cursor for: the log names the row.
        logger.warning("scope_item.added named no scope item", extra={"outboxEventId": str(event.id)})
        return
    if item.status != ScopeItemStatus.IN_SCOPE.value or ResearchRequest.objects.filter(scope_item_id=item.id).exists():
        return
    tenant = Tenant.objects.get(pk=item.tenant_id)
    tenant_agent = (
        TenantAgent.objects.select_related("agent")
        .filter(tenant=tenant, agent__key=RESEARCHER, enabled=True, paused_at__isnull=True)
        .first()  # ordering: one agent per bank and definition, by constraint
    )
    reason = _waiting_because(tenant, tenant_agent)
    if reason is not None or tenant_agent is None:
        record(
            action="scope_item.research_waiting",
            actor=ACTOR,
            subject_type=SCOPE_ITEM_SUBJECT,
            subject_id=item.id,
            subject_title=item.key,
            summary=f"Research of scope item {item.key} waits for the organisation's own agent: {reason}.",
            tenant_id=tenant.id,
            after={"scopeItem": item.key, "reason": reason},
        )
        return
    # The approval is a person's session, so the event's actor is always the approver.
    approver = User.objects.get(pk=cast(uuid.UUID, event.audit_event.actor_id))
    request = ResearchRequest.objects.create(
        tenant=tenant,
        tenant_agent=tenant_agent,
        requested_by=approver,
        kind=ResearchRequestKind.SCOPE_ITEM.value,
        scope_item=item,
        risk_flags=screen_all([item.name, item.official_reference, item.source_url]),
    )
    run = tasks.open_request_run(request, requested_by=approver)
    request.status = (ResearchRequestStatus.RUNNING if run.status == RunStatus.RUNNING.value else ResearchRequestStatus.FAILED).value
    request.save(update_fields=["status"])
    record(
        action="research_request.created",
        actor=ACTOR,
        subject_type="research_request",
        subject_id=request.id,
        subject_title=tenant_agent.agent.key,
        summary=f"Scope item {item.key} opened research by {tenant_agent.agent.key}.",
        tenant_id=tenant.id,
        after={
            "kind": request.kind,
            "tenantAgent": str(tenant_agent.id),
            "scopeItem": item.key,
            "run": str(run.id),
            "riskFlags": request.risk_flags,
        },
    )


def _capped(text: str) -> str:
    return text[: settings.SCOPE_RESEARCH_TEXT_MAX_CHARS]


def run_input(run_id: uuid.UUID) -> dict[str, Any]:
    """What the run `run_id` gives its model: named fields, never a prompt the bank composes
    (ADR 0061). Only for a running scope-item research run of the bank's own agent, in the
    caller's zone, with the bank's AI on; anything else is refused and nothing is read."""
    run = (
        AgentRun.objects.select_related("research_request__scope_item__jurisdiction", "research_request__scope_item__regime_term")
        .filter(pk=run_id, tenant__isnull=False, status=RunStatus.RUNNING.value)
        .first()  # ordering: pk lookup, at most one row
    )
    request = None if run is None else run.research_request
    if request is None or request.kind != ResearchRequestKind.SCOPE_ITEM.value or request.scope_item is None:
        raise ValidationError("Only a running research of a scope item has an input.", code="not_found")
    ai.ensure_enabled()
    item = request.scope_item
    return {
        "keys": {
            "scopeItemId": str(item.id),
            "scopeItem": item.key,
            "jurisdiction": item.jurisdiction.key,
            "regime": item.regime_term.key,
        },
        "text": {
            "name": _capped(item.name),
            "officialReference": _capped(item.official_reference),
            "sourceAddresses": [_capped(item.source_url)],
        },
        "untrusted": True,
        "riskFlags": list(request.risk_flags),
    }
