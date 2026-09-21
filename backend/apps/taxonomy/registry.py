"""The vocabulary registry (VOC-01, VOC-02): one entry per list the generic endpoints
serve, naming the model, its label model, the kinds its rows may carry, the extra
columns exposed as `extra{}`, how usage is counted and how a merge re-points. Adding a
list is adding an entry; the routes, the screen component and the agents' vocabulary
read need no change (AC-VOC1).

This module reads only: the writes that re-point rows live in apps/taxonomy/repoint.py
(tenant rows) and apps/proposals/apply.py (library rows), so the library fence's AST
heuristic sees no write beside a library model's name.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from django.db.models import Count, IntegerField, QuerySet, Value

from apps.library.models import Jurisdiction, JurisdictionKind, JurisdictionLabel
from apps.taxonomy import repoint
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
    RiskRating,
    RiskRatingLabel,
    SourceKind,
    SourceKindLabel,
    TenantTag,
    TenantTagLabel,
    TermDimension,
    TermDimensionKind,
    TermDimensionLabel,
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
    repoint: Callable[..., int] = repoint.nothing_to_repoint  # (source, target, *, dry_run) -> records moved
    references: dict[str, str] = field(default_factory=dict)  # extra field -> related list

    @property
    def is_library(self) -> bool:
        return self.tier == LIBRARY_TIER


def _values(kind: type[Any]) -> tuple[str, ...]:
    return tuple(member.value for member in kind)


REGISTRY: dict[str, VocabularyList] = {
    entry.name: entry
    for entry in (
        # --- tier 2: library lists, curated through proposals (VOC-07) ---
        VocabularyList("term_dimension", LIBRARY_TIER, TermDimension, TermDimensionLabel, "term_dimension_kind", _values(TermDimensionKind), True, ("restricts_footprint",), usage=_count("terms")),
        VocabularyList(
            "instrument_level",
            LIBRARY_TIER,
            InstrumentLevel,
            InstrumentLevelLabel,
            "instrument_level_kind",
            _values(InstrumentLevelKind),
            False,
            ("binding_default", "rank"),
        ),
        VocabularyList("provision_kind", LIBRARY_TIER, ProvisionKind, ProvisionKindLabel, "provision_structural_kind", _values(ProvisionStructuralKind), True, ("jurisdiction",), references={"jurisdiction": "jurisdiction"}),
        VocabularyList("change_type", LIBRARY_TIER, ChangeType, ChangeTypeLabel, "change_lifecycle_kind", _values(ChangeLifecycleKind), True),
        VocabularyList("duty_type", LIBRARY_TIER, DutyType, DutyTypeLabel),
        VocabularyList("relation_type", LIBRARY_TIER, RelationType, RelationTypeLabel),
        VocabularyList("source_kind", LIBRARY_TIER, SourceKind, SourceKindLabel),
        VocabularyList("urgency", LIBRARY_TIER, Urgency, UrgencyLabel, "pill_tone", _values(PillTone), True, ("ordinal", "sla_days")),
        VocabularyList("library_tag", LIBRARY_TIER, LibraryTag, LibraryTagLabel),
        VocabularyList("flag", LIBRARY_TIER, Flag, FlagLabel),
        VocabularyList("rejection_reason", LIBRARY_TIER, RejectionReason, RejectionReasonLabel),
        VocabularyList("jurisdiction", LIBRARY_TIER, Jurisdiction, JurisdictionLabel, "jurisdiction_kind", _values(JurisdictionKind), True, proposable=False),
        # --- tier 3: tenant lists, managed with vocab.manage ---
        VocabularyList("tenant_tag", TENANT_TIER, TenantTag, TenantTagLabel, usage=_count("taggings"), repoint=repoint.tenant_tag),
        VocabularyList("link_kind", TENANT_TIER, LinkKind, LinkKindLabel),
        VocabularyList("effort_size", TENANT_TIER, EffortSize, EffortSizeLabel),
        VocabularyList("compliance_status", TENANT_TIER, ComplianceStatus, ComplianceStatusLabel, "compliance_category", _values(ComplianceCategory), True, ("ordinal",)),
        VocabularyList("risk_rating", TENANT_TIER, RiskRating, RiskRatingLabel, extra_fields=("ordinal",)),
        VocabularyList("case_sub_status", TENANT_TIER, CaseSubStatus, CaseSubStatusLabel, "case_status", _values(CaseStatusCategory), True),
        VocabularyList("dismissal_reason", TENANT_TIER, DismissalReason, DismissalReasonLabel),
        VocabularyList("close_reason", TENANT_TIER, ClosureReason, ClosureReasonLabel, "close_reason", _values(CloseReason), True),
    )
}

LIBRARY_LISTS: tuple[str, ...] = tuple(name for name, entry in REGISTRY.items() if entry.is_library)
TENANT_LISTS: tuple[str, ...] = tuple(name for name, entry in REGISTRY.items() if not entry.is_library)
