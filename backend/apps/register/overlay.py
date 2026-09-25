"""The register overlay on the inventory (REG-01, REG-02, INV-03): the caller's bank's own
applicability, compliance status and owner on each obligation `GET /obligations` and its
card return, and the filters over them.

The library read stays a library read: the overlay is one query over the bank's register
entries for a page, whatever its size, joined by obligation id, and nothing here writes. It
reads by the bank's id as well as under row-level security, so another bank's judgement on
the same shared record never reaches this one, and an obligation nobody in the bank has
worked on reads as not assessed with no status and no owner. The footprint decides which
rows a page holds (`library.reading.in_view()`, the one scope rule); the overlay never
hides a row, so a record shown outside the footprint keeps the bank's judgement on it.

"Applies" and "we comply" stay two facts (CLAUDE.md section 5). An obligation applies when
the entry or any of its legal entities' rows says so, so a gap can never hide behind the
entry's own answer; a status is shown only where it applies, and it is the worst of the
applying entities' statuses by `WORST_FIRST`, else the entry's own. Answering "does not
apply" hides the status and changes nothing: turning it back shows it again (REG-S4).

The overlay is the bank's judgement, so a bank's own agent reads it only through the gate the
register read has (ACC-04, ACC-08, D-76): `shown_to()` is true for a person and for a bank's
key bound to no entry, and for an agent access credential only while tenant reach is on for
the bank and for the entry it reads as. Without it the inventory answers such a credential
the library's facts alone (`library.reading.Reader`).
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from typing import Any, NamedTuple, TypeVar

from django.contrib.postgres.expressions import ArraySubquery
from django.db.models import CharField, Case, Exists, F, IntegerField, OuterRef, Q, QuerySet, Subquery, UUIDField, Value, When
from django.db.models.functions import Coalesce, JSONObject

from apps.agents.agent_access import reach_allowed
from apps.register.models import Applicability, TenantObligation, TenantObligationScope
from apps.register.schemas import Applicability as ApplicabilityAnswer
from apps.register.schemas import RegisterPersonRef, RegisterVocabRef
from apps.shared.authentication import Principal
from apps.shared.models import Tenant
from apps.taxonomy.models import ComplianceCategory, ComplianceStatus, ComplianceStatusLabel, TeamLabel
from apps.taxonomy.reading import label_of

# Worst first. The rank is the category's, fixed in code, because the bank may relabel and
# reorder its own rows: not assessed ranks below partly, since nobody has shown compliance.
# `status_logic.worst_of()` ranks by the same tuple, so the row and the card never disagree.
WORST_FIRST = (ComplianceCategory.GAP, ComplianceCategory.PARTLY, ComplianceCategory.NOT_ASSESSED, ComplianceCategory.COMPLIANT)
RANK = {category.value: index for index, category in enumerate(WORST_FIRST)}

# The published answer for a row with no entry, or an entry nobody has answered.
NOT_ASSESSED: ApplicabilityAnswer = "under_assessment"


class Overlay(NamedTuple):
    """The bank's judgement on one obligation, as a row and the card carry it."""

    applicability: ApplicabilityAnswer
    compliance_status: RegisterVocabRef | None
    first_line_owner: RegisterPersonRef | None
    owner_team: RegisterVocabRef | None


EMPTY = Overlay(NOT_ASSESSED, None, None, None)


def shown_to(principal: Principal) -> bool:
    """Whether the bank's overlay, and the bank's own tags beside it, may be answered to this
    caller: always to anyone but an agent access credential, and to one of those only while
    `reach_allowed` (the bank's tenant reach and the entry's own toggle, both on)."""
    return not principal.is_agent_access or reach_allowed(principal)


class OverlayFilters(NamedTuple):
    """The overlay's filters of `GET /obligations`, each None when not sent."""

    applicability: ApplicabilityAnswer | None
    compliance_status: str | None
    owner: uuid.UUID | None
    owner_team: str | None


def _entries(tenant: Tenant) -> QuerySet[Any]:
    """The bank's entries with the published answer and the shown status id, as SQL, so the
    read and every filter ask one definition."""
    applying = TenantObligationScope.objects.filter(
        tenant_obligation=OuterRef("pk"), product__isnull=True, applicability=Applicability.APPLIES.value
    )
    rank = Case(
        *(When(compliance_status__kind=category, then=Value(index)) for category, index in RANK.items()),
        default=Value(len(RANK)),
        output_field=IntegerField(),
    )
    worst = applying.annotate(rank=rank).order_by("rank", "org_unit__name", "id").values("compliance_status_id")[:1]
    return TenantObligation.objects.filter(tenant_id=tenant.id).annotate(
        answer=Case(
            When(Q(applicability=Applicability.APPLIES.value) | Exists(applying), then=Value("applies")),
            When(applicability=Applicability.DOES_NOT_APPLY.value, then=Value("not_applicable")),
            default=Value(NOT_ASSESSED),
            output_field=CharField(),
        ),
        shown_status_id=Coalesce(Subquery(worst), F("compliance_status_id"), output_field=UUIDField()),
    )


_Listed = TypeVar("_Listed", bound=QuerySet[Any])


def filtered(queryset: _Listed, tenant: Tenant, filters: OverlayFilters) -> _Listed:
    """The obligations whose overlay matches every filter sent. A key or an id the bank has
    no row for matches nothing, as a duty type does."""
    mine = _entries(tenant).filter(obligation_id=OuterRef("pk"))
    if filters.applicability == NOT_ASSESSED:
        # No entry at all is not assessed too.
        queryset = queryset.exclude(Exists(mine.exclude(answer=NOT_ASSESSED)))
    elif filters.applicability is not None:
        queryset = queryset.filter(Exists(mine.filter(answer=filters.applicability)))
    if filters.compliance_status is not None:
        statuses = ComplianceStatus.objects.filter(tenant_id=tenant.id, key=filters.compliance_status).values("id")
        queryset = queryset.filter(Exists(mine.filter(answer="applies", shown_status_id__in=statuses)))
    if filters.owner is not None:
        queryset = queryset.filter(Exists(mine.filter(first_line_owner_id=filters.owner)))
    if filters.owner_team is not None:
        queryset = queryset.filter(Exists(mine.filter(owner_team__key=filters.owner_team)))
    return queryset


def _labelled(label_model: type[Any], row_id: Any) -> ArraySubquery:
    return ArraySubquery(
        label_model.objects.filter(vocabulary_id=row_id)
        .order_by("language")
        .values(row=JSONObject(language="language", text="text", original="is_original"))
    )


def overlay(tenant: Tenant, obligation_ids: Collection[uuid.UUID], order: list[str]) -> dict[uuid.UUID, Overlay]:
    """The bank's overlay on each obligation that has an entry, from one query however many
    obligations: the entries with their owner, the shown status and the team, each with
    every label. An obligation without an entry is absent; read it as `EMPTY`."""
    status = ComplianceStatus.objects.filter(pk=OuterRef("shown_status_id")).values(
        row=JSONObject(key="key", kind="kind", labels=_labelled(ComplianceStatusLabel, OuterRef("pk")))
    )
    rows = (
        _entries(tenant)
        .filter(obligation_id__in=obligation_ids)
        .select_related("first_line_owner", "owner_team")
        .annotate(status=Subquery(status), team_labels=_labelled(TeamLabel, OuterRef("owner_team_id")))
    )
    found: dict[uuid.UUID, Overlay] = {}
    for entry in rows:
        owner, team = entry.first_line_owner, entry.owner_team
        found[entry.obligation_id] = Overlay(
            applicability=entry.answer,
            compliance_status=_ref(entry.status["key"], entry.status["kind"], entry.status["labels"], order)
            if entry.answer == "applies"
            else None,
            first_line_owner=None if owner is None else RegisterPersonRef(id=owner.id, name=owner.name),
            owner_team=None if team is None else _ref(team.key, team.kind, entry.team_labels, order),
        )
    return found


def _ref(key: str, kind: str | None, labels: list[dict[str, Any]], order: list[str]) -> RegisterVocabRef:
    texts = {label["language"]: label["text"] for label in labels}
    original = next((label["language"] for label in labels if label["original"]), None)
    return RegisterVocabRef(key=key, kind=kind, label=label_of(texts, order, original=original, key=key))
