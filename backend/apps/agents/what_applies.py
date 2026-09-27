"""What applies (ACC-06, ACC-07, D-71, AGENT_ACCESS.md section 6).

`POST /agent-access/what-applies` takes a description of what an agent of the bank is
building, buying or reviewing and answers, in one response:

- the full list, deterministic: every shared obligation in the bank's footprint and in the
  entry's scope, each with the bank's register decision on it when the credential holds
  `tenant:read` and tenant reach passes (apps/register/agent_read.py decides both, so this
  list reads no decision that read would refuse). It is ranked in memory by how many of the
  description's words each obligation's library text holds (its titles and its search
  chunks in force today, the library index), then by stable key, and paged like every list;
  nothing but paging ever shortens it. The bank's own private records are left out (D-57: a
  bank's own agent is a model) and counted, so their absence is said rather than silent;
- the scope it was answered in (`agent_access_guard.scope_statement`, the same statement
  every answer to such a credential carries in its header);
- what the description touches outside that scope, by label (out_of_scope.py);
- the summary slot, which says it holds no summary: the drafted summary is ACC-S5's.

The description is compared and dropped: it is never stored, never in an audit row, and
the access log keeps its name alone. It is capped at `AGENT_ACCESS_DESCRIPTION_MAX_CHARS`.
Nothing here writes.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Final, Literal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.agents.out_of_scope import outside_terms, words
from apps.agents.schemas import (
    WhatAppliesAnswer,
    WhatAppliesItem,
    WhatAppliesOutsideScope,
    WhatAppliesSummary,
)
from apps.library.logic import in_force
from apps.library.models import Obligation, ObligationTitle
from apps.library.reading import confirmation_of, localized, obligation_scopes, partial_date, scope_term_ids, today_for, versions_with_confirmation
from apps.library.schemas import ObligationInstrumentRef, ObligationVersionRef
from apps.register import agent_read
from apps.register.schemas import RegisterDecision
from apps.search.models import SearchChunk, SearchSource
from apps.shared import agent_access_guard
from apps.shared import permissions as perms
from apps.shared.authentication import Principal
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.taxonomy import entry_scope, matching

ASK_COMPLIANCE: Final = "ask_compliance"
RegisterRead = Literal["included", "tenant_reach_off", "not_granted"]


def _description(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        raise ValidationError("Describe what is being built, bought or reviewed.", code="description_required")
    limit = settings.AGENT_ACCESS_DESCRIPTION_MAX_CHARS
    if len(cleaned) > limit:
        raise ValidationError(f"A description is at most {limit} characters.", code="description_too_long")
    return cleaned


def _in_scope(tenant: Tenant, scope: entry_scope.EntryScope | None) -> list[uuid.UUID]:
    """The shared obligations in the footprint, then, for an entry, in its scope: the
    footprint's rule in the database, the entry's in memory with the pure rule the
    database's twin is pinned to (apps/taxonomy/tests_entry_scope.py)."""
    ids = list(
        Obligation.objects.filter(owner_tenant__isnull=True)
        .filter(matching.in_footprint_expression(tenant.id, scope_term_ids()))
        .order_by()
        .values_list("id", flat=True)
    )
    if scope is None:
        return ids
    footprint = matching.footprint_of(tenant.id)
    restricting = matching.restricting_dimensions()
    scopes = obligation_scopes(ids)
    return [
        obligation_id
        for obligation_id in ids
        if entry_scope.admits(
            {dimension: [term.key for term in terms] for dimension, terms in scopes.get(obligation_id, {}).items()},
            footprint,
            scope,
            restricting=restricting,
        )
    ]


def _ranked(ids: list[uuid.UUID], asked: set[str], on: datetime.date) -> list[uuid.UUID]:
    """`ids` by how many of the asked words their library text holds, then by stable key."""
    text: dict[uuid.UUID, set[str]] = {obligation_id: set() for obligation_id in ids}
    for obligation_id, title in ObligationTitle.objects.filter(obligation_id__in=ids).order_by().values_list("obligation_id", "text"):
        text[obligation_id] |= words(title)
    chunks = (
        SearchChunk.objects.filter(
            source_type=SearchSource.OBLIGATION_VERSION.value,
            owner_tenant__isnull=True,
            metadata__obligation_id__in=[str(obligation_id) for obligation_id in ids],
        )
        .filter(Q(valid_from__isnull=True) | Q(valid_from__lte=on), Q(valid_to__isnull=True) | Q(valid_to__gt=on))
        .order_by()
        .values_list("metadata__obligation_id", "title", "body")
    )
    for obligation_id, title, body in chunks:
        text[uuid.UUID(obligation_id)] |= words(f"{title} {body}")
    keys = dict(Obligation.objects.filter(id__in=ids).order_by().values_list("id", "stable_key"))
    return sorted(ids, key=lambda obligation_id: (-len(text[obligation_id] & asked), keys[obligation_id]))


def _decisions(tenant: Tenant, principal: Principal, order: list[str], count: int) -> tuple[RegisterRead, dict[uuid.UUID, RegisterDecision]]:
    """Whether the register is read, and its decisions by obligation when it is."""
    if perms.SCOPE_TENANT_READ not in principal.scopes or principal.agent_access_id is None:
        return "not_granted", {}
    try:
        page = agent_read.list_decisions(tenant=tenant, principal=principal, order=order, limit=max(count, 1), offset=0)
    except ProblemError as refused:
        if refused.code != "tenant_reach_off":
            raise
        return "tenant_reach_off", {}
    return "included", {decision.obligation_id: decision for decision in page.items}


def _items(ids: list[uuid.UUID], order: list[str], on: datetime.date, decisions: dict[uuid.UUID, RegisterDecision]) -> list[WhatAppliesItem]:
    """The page's rows in the ranked order, each as the library cites it on `on`."""
    rows = Obligation.objects.filter(id__in=ids).select_related("instrument").prefetch_related("titles", versions_with_confirmation())
    by_id = {row.id: row for row in rows}
    items = []
    for obligation_id in ids:
        row = by_id[obligation_id]
        version = in_force(list(row.versions.all()), on)
        confirmed = None if version is None else confirmation_of(version)
        items.append(
            WhatAppliesItem(
                obligation_id=row.id,
                stable_key=row.stable_key,
                ref_label=row.ref_label,
                title=localized(row.titles.all(), order),
                instrument=ObligationInstrumentRef(key=row.instrument.stable_key, short_name=row.instrument.short_name),
                version=None
                if version is None or confirmed is None
                else ObligationVersionRef(
                    version_number=version.version_number,
                    effective_from=partial_date(version.effective_from, version.effective_from_precision),
                    approved_at=version.approved_at,
                    verified_origin=confirmed.verified_origin,
                    confirmed_by_agent=confirmed.confirmed_by_agent,
                    proposed_by_agent=confirmed.proposed_by_agent,
                ),
                decision=decisions.get(row.id),
            )
        )
    return items


def answer(*, tenant: Tenant, principal: Principal, description: str, order: list[str], limit: int, offset: int) -> WhatAppliesAnswer:
    """The full list with its scope, what lies outside it, and the summary slot."""
    if not principal.is_agent_access:
        raise ProblemError(status=403, code="permission_denied", detail="Only a key or token of an agent your bank runs itself asks this.")
    asked = words(_description(description))
    on = today_for(tenant)
    scope = None if principal.agent_access_id is None else entry_scope.scope_of(tenant.id, principal.agent_access_id)
    ranked = _ranked(_in_scope(tenant, scope), asked, on)
    register, decisions = _decisions(tenant, principal, order, len(ranked))
    outside = [] if scope is None else outside_terms(tenant.id, scope, description, order)
    return WhatAppliesAnswer(
        scope=agent_access_guard.scope_statement(principal, tenant),
        summary=WhatAppliesSummary(status="not_drafted", text=None),
        items=_items(ranked[offset : offset + limit], order, on, decisions),
        total=len(ranked),
        register_read=register,
        own_records_left_out=Obligation.objects.filter(owner_tenant_id=tenant.id).count(),
        outside_scope=WhatAppliesOutsideScope(terms=outside, advice=ASK_COMPLIANCE if outside else None),
    )
