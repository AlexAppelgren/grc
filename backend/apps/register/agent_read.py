"""The register as the bank's own agents read it (ACC-04, ACC-08, D-76, ADR 0057).

A service key of an agent access entry, or a personal access token naming one, holding
`tenant:read`, reads the bank's settled decisions on the obligations in the entry's scope,
and only while the bank's tenant reach and the entry's own toggle are both on; otherwise
every read answers 403 `tenant_reach_off`. A credential bound to no entry reads nothing
here (its `tenant:read` is withheld when it is resolved, apps/identity/api_keys_logic.py).

What it reads is D-76's list and nothing else: applicability and its reason per legal
entity, compliance status and status note, the reading in force, owner, process, system,
next review and the live linked internal items. Never a gap, case, assessment, comment,
evidence or its location, risk rating or audit row. Never a private obligation (D-57: a
bank's own agent is a model) and never one under a standard, whose register rows are never
sent to a model (REG-08, AC-REG2). An obligation outside the entry's scope, private or
under a standard is 404 on its own and absent from the list: the answer another bank gets,
so scope cannot be probed by the shape of the error.

The scope is decided in the database inside the list's own query: the footprint's rule,
then the same rule against the entry's terms (taxonomy 0011), each handed its guard as an
uncorrelated subquery PostgreSQL runs once per query. A page costs the same fixed handful
of queries however many rows it holds.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from django.contrib.postgres.fields import ArrayField
from django.db.models import BooleanField, Exists, Func, OuterRef, Prefetch, QuerySet, Subquery, UUIDField, Value

from apps.agents.models import AgentAccess
from apps.governance.reach import tenant_reach_on
from apps.library.models import Obligation
from apps.library.reading import scope_term_ids
from apps.register.models import InternalLink, Interpretation, TenantObligation, TenantObligationScope
from apps.register.schemas import (
    RegisterDecision,
    RegisterDecisionEntity,
    RegisterDecisionItem,
    RegisterDecisionPage,
    RegisterPersonRef,
    RegisterVocabRef,
)
from apps.register.status_logic import _APPLICABILITY_OUT, _Refs, worst_of
from apps.shared.authentication import Principal
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.shared.vocabulary import label_for
from apps.taxonomy import matching
from apps.taxonomy.models import ComplianceStatus, InstrumentLevelKind
from apps.tenants.models import InternalItem

# The entry's guard for the second pass (taxonomy 0011's `taxonomy_entry_admits`, taken
# apart so each piece is an uncorrelated subquery rather than a per-row call).
_ENTRY_GUARD = (
    "(SELECT g.terms FROM taxonomy_entry_scope(%(expressions)s) AS s, taxonomy_term_map_guard(s.terms) AS g)",
    "(SELECT g.dimensions FROM taxonomy_entry_scope(%(expressions)s) AS s, taxonomy_term_map_guard(s.terms) AS g)",
    "(SELECT g.allowed FROM taxonomy_entry_scope(%(expressions)s) AS s, taxonomy_term_map_guard(s.terms) AS g)",
)
# An entry naming departments or products that derive no term reads nothing at all.
_ENTRY_NOT_EMPTY = "NOT (SELECT s.narrowed AND cardinality(s.terms) = 0 FROM taxonomy_entry_scope(%(expressions)s) AS s)"


def require_reach(tenant: Tenant, principal: Principal) -> uuid.UUID:
    """The entry the credential reads as, once the bank's tenant reach and the entry's own
    toggle are both on. A credential of no entry never gets this far with `tenant:read`."""
    entry_id = principal.agent_access_id
    if entry_id is None:
        raise ProblemError(status=403, code="permission_denied", detail="Only an agent access entry's key or token reads the register.")
    if not (tenant_reach_on(tenant.id) and AgentAccess.objects.filter(pk=entry_id, active=True, tenant_reach=True).exists()):
        raise ProblemError(
            status=403, code="tenant_reach_off", detail="Tenant reach is off for this agent, so it reads the library alone."
        )
    return entry_id


def _readable(tenant: Tenant, entry_id: uuid.UUID) -> QuerySet[Obligation]:
    """The shared obligations this entry may read decisions on: in the footprint and in the
    entry's scope, never a private one and never one under a standard."""
    arguments = (Value(tenant.id, output_field=UUIDField()), Value(entry_id, output_field=UUIDField()))
    guard = [Func(*arguments, template=template, output_field=ArrayField(UUIDField())) for template in _ENTRY_GUARD]
    return (
        Obligation.objects.filter(owner_tenant__isnull=True)
        .exclude(instrument__level__kind=InstrumentLevelKind.STANDARD.value)
        .filter(matching.in_footprint_expression(tenant.id, scope_term_ids()))
        .filter(Func(*arguments, template=_ENTRY_NOT_EMPTY, output_field=BooleanField()))
        .filter(Func(scope_term_ids(), *guard, function="taxonomy_scope_admits", output_field=BooleanField()))
    )


def _readable_ids(tenant: Tenant, entry_id: uuid.UUID) -> list[uuid.UUID]:
    """The obligations the bank has decided on that the entry may read, by stable key: one
    pass over the library, so the scope is judged once per obligation."""
    decided = TenantObligation.objects.filter(obligation_id=OuterRef("pk"))
    return list(_readable(tenant, entry_id).filter(Exists(decided)).order_by("stable_key", "id").values_list("id", flat=True))


def _with_children(rows: QuerySet[TenantObligation]) -> QuerySet[TenantObligation]:
    """The row and what it shows, in one query per child list however many rows. The risk
    rating is joined only because the shared labeller reads it; it is never answered."""
    entities = (
        TenantObligationScope.objects.filter(product__isnull=True)
        .select_related("compliance_status", "risk_rating", "owner_team", "owner", "org_unit")
        .order_by("org_unit__name", "id")
    )
    links = (
        InternalLink.objects.filter(removed_at__isnull=True, internal_item__isnull=False)
        .select_related("internal_item__kind")
        .prefetch_related("internal_item__kind__labels")
        .order_by("created_at", "id")
    )
    reading = Interpretation.objects.filter(tenant_obligation=OuterRef("pk"), superseded_at__isnull=True).values("body")[:1]
    return (
        rows.select_related("obligation", "compliance_status", "risk_rating", "owner_team", "first_line_owner")
        .annotate(reading=Subquery(reading))
        .prefetch_related(
            Prefetch("scopes", queryset=entities, to_attr="entity_rows"),
            Prefetch("links", queryset=links, to_attr="live_links"),
        )
    )


def list_decisions(*, tenant: Tenant, principal: Principal, order: list[str], limit: int, offset: int) -> RegisterDecisionPage:
    """`GET /register-entries`: the decisions the entry may read, by the obligation's
    stable key."""
    readable = _readable_ids(tenant, require_reach(tenant, principal))
    page = _with_children(TenantObligation.objects.filter(obligation_id__in=readable[offset : offset + limit]))
    rows = list(page.order_by("obligation__stable_key", "id"))
    refs = _Refs([*rows, *(entity for row in rows for entity in row.entity_rows)], order)  # type: ignore[attr-defined]
    return RegisterDecisionPage(items=[_decision(row, refs, order) for row in rows], total=len(readable))


def read_decision(*, tenant: Tenant, principal: Principal, order: list[str], obligation_id: uuid.UUID) -> RegisterDecision:
    """`GET /register-entries/{obligationId}`: one obligation's decisions, 404 unless the
    entry may read it; an obligation in scope nobody has decided on reads as undecided."""
    entry_id = require_reach(tenant, principal)
    obligation = _readable(tenant, entry_id).filter(pk=obligation_id).values_list("stable_key", flat=True).first()  # ordering: pk lookup, at most one row
    if obligation is None:
        raise ProblemError(status=404, code="not_found", detail="That obligation is not here.")
    row = _with_children(TenantObligation.objects.filter(obligation_id=obligation_id)).first()  # ordering: unique per bank, at most one row
    if row is None:
        status = ComplianceStatus.objects.get(is_default=True, active=True)
        return RegisterDecision(
            obligation_id=obligation_id,
            obligation_key=obligation,
            applicability="under_assessment",
            applicability_reason=None,
            compliance_status=_Refs([], order, [status]).of(status),
            status_note=None,
            interpretation=None,
            owner=None,
            owner_team=None,
            process=None,
            system=None,
            next_review_date=None,
            entities=[],
            internal_items=[],
        )
    return _decision(row, _Refs([row, *row.entity_rows], order), order)  # type: ignore[attr-defined]


def _decision(row: Any, refs: _Refs, order: list[str]) -> RegisterDecision:
    applying = [entity.compliance_status for entity in row.entity_rows if entity.applicability == "applies"]
    return RegisterDecision(
        obligation_id=row.obligation_id,
        obligation_key=row.obligation.stable_key,
        applicability=_APPLICABILITY_OUT[row.applicability],
        applicability_reason=row.applicability_reason or None,
        compliance_status=refs.of(worst_of(applying) or row.compliance_status),
        status_note=row.status_note or None,
        interpretation=row.reading,
        owner=_person(row.first_line_owner),
        owner_team=refs.maybe(row.owner_team),
        process=row.process or None,
        system=row.system or None,
        next_review_date=row.next_review_date,
        entities=[_entity(entity, refs) for entity in row.entity_rows],
        internal_items=[_item(link, order) for link in row.live_links],
    )


def _entity(scope: TenantObligationScope, refs: _Refs) -> RegisterDecisionEntity:
    return RegisterDecisionEntity(
        org_unit_id=scope.org_unit_id,
        org_unit_name=scope.org_unit.name,
        applicability=_APPLICABILITY_OUT[scope.applicability],
        applicability_reason=scope.applicability_reason or None,
        compliance_status=refs.of(scope.compliance_status),
        status_note=scope.status_note or None,
        owner=_person(scope.owner),
        owner_team=refs.maybe(scope.owner_team),
        process=scope.process or None,
        system=scope.system or None,
        next_review_date=scope.next_review_date,
    )


def _item(link: InternalLink, order: list[str]) -> RegisterDecisionItem:
    item = cast(InternalItem, link.internal_item)  # the prefetch keeps only links to an item
    return RegisterDecisionItem(
        kind=RegisterVocabRef(key=item.kind.key, kind=item.kind.kind, label=label_for(item.kind, order)),
        label=link.label,
        url=link.url or None,
        external_ref=link.external_ref or None,
        external_system=item.external_system or None,
    )


def _person(user: Any) -> RegisterPersonRef | None:
    return None if user is None else RegisterPersonRef(id=user.id, name=user.name)
