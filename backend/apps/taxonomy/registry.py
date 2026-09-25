"""The vocabulary registry (VOC-01, VOC-02): one entry per list the generic endpoints
serve, naming the model, its label model, the kinds its rows may carry, the extra
columns exposed as `extra{}`, how usage is counted and how a merge re-points. Adding a
list is adding an entry; the routes, the screen component and the agents' vocabulary
read need no change (AC-VOC1).

Every list something references names its `links`: each library and watch column that
holds one of a library list's values, and each register, organisation and collaboration
column that holds one of a tenant list's. The usage count and the merge's re-point both
read them, so a list counts exactly the records a merge would move. An append-only
ledger (a compliance assessment) is history, so it neither counts nor moves: it keeps the
value it named, which stays resolvable because a merged-away value is retired, never
deleted. This module reads only: the writes that re-point
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

from django.db.models import Count, IntegerField, OuterRef, Q, QuerySet, Subquery, Value
from django.db.models.functions import Coalesce

from apps.library.models import (
    Authority,
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
from apps.collab.models import Participant
from apps.register.models import Gap, TenantObligation, TenantObligationScope
from apps.taxonomy import repoint
from apps.taxonomy.repoint import Link, Moves
from apps.tenants.models import InternalItem, Licence, TeamMember
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
    Tagging,
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
        rows = link.rows().filter(**{link.field: OuterRef("pk")}).order_by().values(link.field)
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
    # tier 2 only: True means the seed alone adds a value and no value is merged away, so a
    # proposal relabels, retires or restores and a system row may be retired (D-94)
    fixed_keys: bool = False
    usage: Callable[[QuerySet[Any]], QuerySet[Any]] = _no_usage
    repoint: Callable[..., Moves] = repoint.nothing_to_repoint  # (source, target, *, dry_run) -> ids moved and dropped per table
    references: dict[str, str] = field(default_factory=dict)  # extra field -> related list
    links: tuple[Link, ...] = ()  # every column holding a value, which the usage count and the merge read
    open_work: Callable[[Any], dict[str, int]] | None = None  # tenant lists: the open work a row owns, per table

    @property
    def is_library(self) -> bool:
        return self.tier == LIBRARY_TIER


def _values(kind: type[Any]) -> tuple[str, ...]:
    return tuple(member.value for member in kind)


def _library(entry: VocabularyList, *links: Link) -> VocabularyList:
    """A library list counted and merged through `links`."""
    return replace(entry, usage=_uses(*links), repoint=repoint.library_links(links), links=links)


def _tenant(entry: VocabularyList, *links: Link) -> VocabularyList:
    """A tenant list counted and merged through `links` (VOC-02, H32)."""
    return replace(entry, usage=_uses(*links), repoint=repoint.tenant_links(links), links=links)


# Every register, organisation and collaboration row a team is named on (TEN-03, COL-04):
# as the owner, as a member's team, or as a live participant. A person in both teams of a
# merge stays in the one kept, and a team taking part in a record beside the team it is
# merged into is stamped removed there, never deleted.
TEAM_LINKS = (
    Link(TenantObligation, "owner_team"),
    Link(TenantObligationScope, "owner_team"),
    Link(Gap, "owner_team"),
    Link(Licence, "owner_team"),
    Link(InternalItem, "owner_team"),
    Link(TeamMember, "team", ("user",)),
    Link(Participant, "team", ("tenant_obligation", "case", "user"), removable=True),
)
# What a team owns that is still open: a register entry and an entity row while they
# exist, a gap until it is closed, a licence until it is withdrawn, an internal item while
# it is active. A retired team would own it with nobody to pick it up.
TEAM_OPEN_WORK: tuple[tuple[type[Any], Q], ...] = (
    (TenantObligation, Q()),
    (TenantObligationScope, Q()),
    (Gap, ~Q(status__kind=GapCategory.CLOSED.value)),
    (Licence, Q(withdrawn_on__isnull=True)),
    (InternalItem, Q(active=True)),
)


def team_open_work(team: Any) -> dict[str, int]:
    """The open work `team` owns, counted per table; tables with none are left out."""
    counts = {model._meta.db_table: model._default_manager.filter(still_open, owner_team=team).count() for model, still_open in TEAM_OPEN_WORK}
    return {table: count for table, count in counts.items() if count}


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
        # The seed files every jurisdiction with its kind, parent and legal language, and its
        # key never changes (D-94): a proposal relabels, retires or restores one, and the
        # mirrored term follows in the same approval. Counted by the records filed under it,
        # so a retirement asks first; never merged, so nothing is re-pointed.
        VocabularyList(
            "jurisdiction", LIBRARY_TIER, Jurisdiction, JurisdictionLabel, "jurisdiction_kind", _values(JurisdictionKind), True,
            fixed_keys=True, usage=_uses(Link(Instrument, "jurisdiction"), Link(Authority, "jurisdiction")),
        ),
        # --- tier 3: tenant lists, managed with vocab.manage ---
        # A record that already carries the tag a merge moves to keeps one tagging (the
        # unique constraint), so the duplicate is dropped and not counted as moved.
        _tenant(VocabularyList("tenant_tag", TENANT_TIER, TenantTag, TenantTagLabel), Link(Tagging, "tag", ("subject_type", "subject_id"))),
        # An internal item's name is unique per kind and the item is never deleted, so a
        # merge that would give two items one name is refused until a person renames one.
        _tenant(VocabularyList("link_kind", TENANT_TIER, LinkKind, LinkKindLabel), Link(InternalItem, "kind", ("name",), drop_twins=False)),
        VocabularyList("effort_size", TENANT_TIER, EffortSize, EffortSizeLabel),
        # The register's current status rows count and move; the assessment ledger keeps
        # the status each assessment named (REG-04).
        _tenant(
            VocabularyList("compliance_status", TENANT_TIER, ComplianceStatus, ComplianceStatusLabel, "compliance_category", _values(ComplianceCategory), True, ("ordinal",)),
            Link(TenantObligation, "compliance_status"),
            Link(TenantObligationScope, "compliance_status"),
        ),
        # The tone reads the fixed level, never the editable ordinal (VOC-05). A gap's
        # severity is a risk rating too.
        _tenant(
            VocabularyList("risk_rating", TENANT_TIER, RiskRating, RiskRatingLabel, "risk_level", _values(RiskLevel), True, ("ordinal",)),
            Link(TenantObligation, "risk_rating"),
            Link(TenantObligationScope, "risk_rating"),
            Link(Gap, "severity"),
        ),
        VocabularyList("case_sub_status", TENANT_TIER, CaseSubStatus, CaseSubStatusLabel, "case_status", _values(CaseStatusCategory), True),
        VocabularyList("dismissal_reason", TENANT_TIER, DismissalReason, DismissalReasonLabel),
        VocabularyList("close_reason", TENANT_TIER, ClosureReason, ClosureReasonLabel, "close_reason", _values(CloseReason), True),
        # Chunk 8's register lists (REG-03, VOC-04, VOC-06, TEN-03).
        _tenant(VocabularyList("gap_status", TENANT_TIER, GapStatus, GapStatusLabel, "gap_category", _values(GapCategory), True), Link(Gap, "status")),
        _tenant(VocabularyList("gap_source", TENANT_TIER, GapSource, GapSourceLabel), Link(Gap, "source")),
        _tenant(VocabularyList("risk_acceptance_reason", TENANT_TIER, RiskAcceptanceReason, RiskAcceptanceReasonLabel), Link(Gap, "acceptance_reason")),
        # A team that owns open work is not retired: its work is moved first, by a merge or
        # by reassigning it (TEN-03).
        replace(_tenant(VocabularyList("team", TENANT_TIER, Team, TeamLabel, extra_fields=("email",)), *TEAM_LINKS), open_work=team_open_work),
    )
}

LIBRARY_LISTS: tuple[str, ...] = tuple(name for name, entry in REGISTRY.items() if entry.is_library)
TENANT_LISTS: tuple[str, ...] = tuple(name for name, entry in REGISTRY.items() if not entry.is_library)
