"""The vocabulary registry (VOC-01, VOC-02): one entry per list the generic endpoints
serve, naming the model, its label model, the kinds its rows may carry, the extra
columns exposed as `extra{}`, how usage is counted and how a merge re-points. Adding a
list is adding an entry; the routes, the screen component and the agents' vocabulary
read need no change (AC-VOC1).

A library list names its `links`: every library and watch column that holds one of its
values. The usage count and the merge's re-point both read them, so a list counts
exactly the records a merge would move. This module reads only: the writes that re-point
rows live in apps/taxonomy/repoint.py (tenant rows), apps/proposals/apply.py (library
rows) and apps/watch/write.py (watch rows), so the library fence's AST heuristic sees no
write beside a library model's name.
"""

from __future__ import annotations

import functools
import operator
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from django.db.models import Count, IntegerField, OuterRef, QuerySet, Subquery, Value
from django.db.models.functions import Coalesce

from apps.library.models import (
    Instrument,
    InstrumentRelation,
    Jurisdiction,
    JurisdictionKind,
    JurisdictionLabel,
    Obligation,
    ObligationRelation,
    ObligationTag,
    Provision,
)
from apps.taxonomy import repoint
from apps.taxonomy.repoint import Link, Moves
from apps.watch.models import ChangeTerm, RegulatoryChange, Source
from apps.taxonomy.models import (
    CaseStatusCategory,
    CaseSubStatus,
    CaseSubStatusLabel,
    ChangeLifecycleKind,
    ChangeType,
    ChangeTypeLabel,
    CloseReason,
    ClosureReason,
    ClosureReasonLabel,
    ComplianceCategory,
    ComplianceStatus,
    ComplianceStatusLabel,
    DismissalReason,
    DismissalReasonLabel,
    DutyType,
    DutyTypeLabel,
    EffortSize,
    EffortSizeLabel,
    Flag,
    FlagLabel,
    GapCategory,
    GapSource,
    GapSourceLabel,
    GapStatus,
    GapStatusLabel,
    InstrumentLevel,
    InstrumentLevelKind,
    InstrumentLevelLabel,
    LibraryTag,
    LibraryTagLabel,
    LinkKind,
    LinkKindLabel,
    PillTone,
    ProvisionKind,
    ProvisionKindLabel,
    ProvisionStructuralKind,
    RejectionReason,
    RejectionReasonLabel,
    RelationType,
    RelationTypeLabel,
    RiskAcceptanceReason,
    RiskAcceptanceReasonLabel,
    RiskLevel,
    RiskRating,
    RiskRatingLabel,
    SourceKind,
    SourceKindLabel,
    TenantTag,
    TenantTagLabel,
    TermDimension,
    TermDimensionKind,
    TermDimensionLabel,
    Team,
    TeamLabel,
    Urgency,
    UrgencyLabel,
)

LIBRARY_TIER = 2
TENANT_TIER = 3


def _no_usage(queryset: QuerySet[Any]) -> QuerySet[Any]:
    """Nothing references this list yet; later chunks replace the annotation."""
    return queryset.annotate(usage_count=Value(0, output_field=IntegerField()))


def _count(relation: str) -> Callable[[QuerySet[Any]], QuerySet[Any]]:
    def annotate(queryset: QuerySet[Any]) -> QuerySet[Any]:
        return queryset.annotate(usage_count=Count(relation, distinct=True))

    return annotate


def _uses(*links: Link) -> Callable[[QuerySet[Any]], QuerySet[Any]]:
    """Count the rows of every linked table that hold each value, as one correlated
    subquery per table inside the list read itself: still one query per list read, and no
    GROUP BY over the list, so a join through one table cannot multiply another's count."""

    def per_table(link: Link) -> Coalesce:
        rows = link.model._default_manager.filter(**{link.field: OuterRef("pk")}).order_by().values(link.field)
        return Coalesce(Subquery(rows.annotate(uses=Count("pk")).values("uses")), 0)

    def annotate(queryset: QuerySet[Any]) -> QuerySet[Any]:
        total = functools.reduce(operator.add, (per_table(link) for link in links))
        return queryset.annotate(usage_count=total)

    return annotate


@dataclass(frozen=True)
class VocabularyList:
    name: str
    tier: int
    # A concrete Vocabulary subclass (tier 3 ones add `tenant`) and its concrete label model
    # (with a `vocabulary` foreign key). Typed Any because the columns the generic code reads
    # differ per tier and per list; the vocabulary-integrity guard proves the pairing.
    model: type[Any]
    label_model: type[Any]
    kind_name: str | None = None  # the tier-one kind's INPUT_DELTAS name, if rows carry one
    kinds: tuple[str, ...] = ()  # the values a row's kind may take ("" when none)
    kind_required: bool = False
    extra_fields: tuple[str, ...] = ()  # model columns exposed as extra{} (snake_case here)
    proposable: bool = True  # tier 2 only: False means the list is seeded and never proposed
    usage: Callable[[QuerySet[Any]], QuerySet[Any]] = _no_usage
    repoint: Callable[..., Moves] = repoint.nothing_to_repoint  # (source, target, *, dry_run) -> ids moved and dropped per table
    references: dict[str, str] = field(default_factory=dict)  # extra field -> related list
    links: tuple[Link, ...] = ()  # library lists: every library and watch column holding a value

    @property
    def is_library(self) -> bool:
        return self.tier == LIBRARY_TIER


def _values(kind: type[Any]) -> tuple[str, ...]:
    return tuple(member.value for member in kind)


def _library(entry: VocabularyList, *links: Link) -> VocabularyList:
    """A library list counted and merged through `links`."""
    return replace(entry, usage=_uses(*links), repoint=repoint.library_links(links), links=links)


REGISTRY: dict[str, VocabularyList] = {
    entry.name: entry
    for entry in (
        # --- tier 2: library lists, curated through proposals (VOC-07) ---
        VocabularyList("term_dimension", LIBRARY_TIER, TermDimension, TermDimensionLabel, "term_dimension_kind", _values(TermDimensionKind), True, ("restricts_footprint",), usage=_count("terms")),
        # The kind is optional (D-37): null on the five law and guidance levels, `standard` on one.
        _library(VocabularyList("instrument_level", LIBRARY_TIER, InstrumentLevel, InstrumentLevelLabel, "instrument_level_kind", _values(InstrumentLevelKind), False, ("binding_default", "rank")), Link(Instrument, "level")),
        _library(VocabularyList("provision_kind", LIBRARY_TIER, ProvisionKind, ProvisionKindLabel, "provision_structural_kind", _values(ProvisionStructuralKind), True, ("jurisdiction",), references={"jurisdiction": "jurisdiction"}), Link(Provision, "kind")),
        _library(VocabularyList("change_type", LIBRARY_TIER, ChangeType, ChangeTypeLabel, "change_lifecycle_kind", _values(ChangeLifecycleKind), True), Link(RegulatoryChange, "change_type")),
        _library(VocabularyList("duty_type", LIBRARY_TIER, DutyType, DutyTypeLabel), Link(Obligation, "duty_type")),
        _library(
            VocabularyList("relation_type", LIBRARY_TIER, RelationType, RelationTypeLabel),
            Link(InstrumentRelation, "relation_type", ("from_instrument", "to_instrument")),
            Link(ObligationRelation, "relation_type"),
        ),
        _library(VocabularyList("source_kind", LIBRARY_TIER, SourceKind, SourceKindLabel), Link(Source, "kind")),
        # A bank's case carries its own urgency, a tenant row a library merge never reaches, so
        # only the library's suggestion on a change counts and moves.
        _library(VocabularyList("urgency", LIBRARY_TIER, Urgency, UrgencyLabel, "pill_tone", _values(PillTone), True, ("ordinal", "sla_days")), Link(RegulatoryChange, "suggested_urgency")),
        _library(VocabularyList("library_tag", LIBRARY_TIER, LibraryTag, LibraryTagLabel), Link(ObligationTag, "tag", ("obligation",))),
        _library(VocabularyList("flag", LIBRARY_TIER, Flag, FlagLabel), Link(ChangeTerm, "flag", ("change",))),
        VocabularyList("rejection_reason", LIBRARY_TIER, RejectionReason, RejectionReasonLabel),
        VocabularyList("jurisdiction", LIBRARY_TIER, Jurisdiction, JurisdictionLabel, "jurisdiction_kind", _values(JurisdictionKind), True, proposable=False),
        # --- tier 3: tenant lists, managed with vocab.manage ---
        VocabularyList("tenant_tag", TENANT_TIER, TenantTag, TenantTagLabel, usage=_count("taggings"), repoint=repoint.tenant_tag),
        VocabularyList("link_kind", TENANT_TIER, LinkKind, LinkKindLabel),
        VocabularyList("effort_size", TENANT_TIER, EffortSize, EffortSizeLabel),
        VocabularyList("compliance_status", TENANT_TIER, ComplianceStatus, ComplianceStatusLabel, "compliance_category", _values(ComplianceCategory), True, ("ordinal",)),
        # The tone reads the fixed level, never the editable ordinal (VOC-05).
        VocabularyList("risk_rating", TENANT_TIER, RiskRating, RiskRatingLabel, "risk_level", _values(RiskLevel), True, ("ordinal",)),
        VocabularyList("case_sub_status", TENANT_TIER, CaseSubStatus, CaseSubStatusLabel, "case_status", _values(CaseStatusCategory), True),
        VocabularyList("dismissal_reason", TENANT_TIER, DismissalReason, DismissalReasonLabel),
        VocabularyList("close_reason", TENANT_TIER, ClosureReason, ClosureReasonLabel, "close_reason", _values(CloseReason), True),
        # Chunk 8's register lists (REG-03, VOC-04, VOC-06, TEN-03).
        VocabularyList("gap_status", TENANT_TIER, GapStatus, GapStatusLabel, "gap_category", _values(GapCategory), True),
        VocabularyList("gap_source", TENANT_TIER, GapSource, GapSourceLabel),
        VocabularyList("risk_acceptance_reason", TENANT_TIER, RiskAcceptanceReason, RiskAcceptanceReasonLabel),
        VocabularyList("team", TENANT_TIER, Team, TeamLabel, extra_fields=("email",)),
    )
}

LIBRARY_LISTS: tuple[str, ...] = tuple(name for name, entry in REGISTRY.items() if entry.is_library)
TENANT_LISTS: tuple[str, ...] = tuple(name for name, entry in REGISTRY.items() if not entry.is_library)
