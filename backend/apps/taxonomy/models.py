"""Models of the taxonomy app (VOC-01, VOC-02, VOC-07, FP-01, FP-02, FP-04, I18N-01; INPUT_DELTAS
§1; schema v0.3 `taxonomy_term`, `footprint_term`, `footprint_history`, `tenant_tag`,
`tagging`).

Three tiers (playbook 15):

- Tier 1, kinds in code: the enums at the top, each in apps/shared/kinds.py.
- Tier 2, library vocabularies: `LibraryVocabulary` subclasses with a label table each,
  written only by an approved proposal (apps/proposals/apply.py) or a reference seed.
  `TaxonomyTerm` is the one library list with a parent and a dimension.
- Tier 3, tenant vocabularies: `TenantListVocabulary` subclasses under forced RLS, with
  a label table that carries the tenant too. System rows are seeded per tenant by
  apps/taxonomy/tenant_hooks.py and can be relabelled but not removed.

A row's fixed `kind` is what the rules read: the lifecycle of a change type, the tone of
an urgency, the category of a compliance status or case sub-status, whether a dimension
restricts the footprint. Everything else on the row is an admin's.

The footprint (FP-01, FP-02): `FootprintTerm` rows are the company's terms; a change is
a `FootprintChangeRequest` with a preview, decided by a second person (check constraint
`footprint_change_request_four_eyes`), and every term switched leaves one
`FootprintHistory` row (append-only) and one audit event.

Markets (FP-04): the countries in the footprint are the ones the company operates in;
`WatchedMarket` rows are the ones it watches instead. A market's level is computed from
the two, never stored.
"""

from __future__ import annotations

import enum

from django.db import models

from apps.shared.audit import AppendOnlyModel
# Defined in kinds.py so the pure case state machine (apps/cases/state.py) reads them
# without importing a model; every caller that imports them from here keeps working.
from apps.shared.kinds import CaseStatusCategory as CaseStatusCategory
from apps.shared.kinds import CloseReason as CloseReason
from apps.shared.tenancy import LibraryModel, TenantModel
from apps.shared.vocabulary import (
    ORIGIN_CHOICES,
    LibraryVocabulary,
    LibraryVocabularyLabel,
    TenantListVocabulary,
    VocabularyLabel,
)


def _choices(kind: type[enum.StrEnum]) -> list[tuple[str, str]]:
    return [(member.value, member.value) for member in kind]


# ---------------------------------------------------------------------------------------
# Kinds (tier one, apps/shared/kinds.py)
# ---------------------------------------------------------------------------------------
class PillTone(enum.StrEnum):
    """The six pill tones (NFR-03, design/system/pills-and-labels.md), named as Green names
    them. A vocabulary row whose kind is a tone (urgency) renders with it; never a seventh."""

    INFORMATION = "information"
    NOTICE = "notice"
    POSITIVE = "positive"
    WARNING = "warning"
    NEGATIVE = "negative"
    BRAND = "brand"


class TermDimensionKind(enum.StrEnum):
    """What a dimension does to the footprint (FP-01, D-36). A scope dimension whose flag says
    it restricts narrows the footprint once the footprint names a term in it; a
    classification dimension never narrows it; an opt-in dimension (the standards a bank
    follows) shows a record carrying one of its terms only when the footprint names that
    term, even when it names none in the dimension, whatever the flag says."""

    SCOPE = "scope"
    CLASSIFICATION = "classification"
    OPT_IN = "opt_in"


class ChangeLifecycleKind(enum.StrEnum):
    PRE_ADOPTION = "pre_adoption"
    ADOPTED = "adopted"
    IN_FORCE = "in_force"
    SUPERVISORY = "supervisory"
    RECURRING = "recurring"


class ProvisionStructuralKind(enum.StrEnum):
    DIVISION = "division"
    UNIT = "unit"
    ANNEX = "annex"


class InstrumentLevelKind(enum.StrEnum):
    """Tier-one kind (INV-01, INV-08, D-37): the one optional sub-kind an instrument level
    may carry. The five seeded levels (`eu_regulation`, `eu_directive`, `eu_guidance`,
    `act`, `authority_regulation`) keep a null kind and are read by `binding`; `standard`
    is the only value, and it is what tells a pill to read "Standard" instead of "Binding"
    or "Guidance, comply or explain", and what the `provision` trigger (library 0008)
    refuses a provision under."""

    STANDARD = "standard"


class ComplianceCategory(enum.StrEnum):
    COMPLIANT = "compliant"
    PARTLY = "partly"
    GAP = "gap"
    NOT_ASSESSED = "not_assessed"


class ApprovalStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class FootprintAction(enum.StrEnum):
    ADDED = "added"
    REMOVED = "removed"


class SuggestionStatus(enum.StrEnum):
    """A member's suggestion for a tenant list (VOC-03): waiting in the admin's inbox,
    accepted when the row is created, or declined. Not `ApprovalStatus`, because nobody
    approves a suggestion: the admin creates the value or does not."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"


# ---------------------------------------------------------------------------------------
# Tier 2: library vocabularies
# ---------------------------------------------------------------------------------------
class TermDimension(LibraryVocabulary):
    """A taxonomy dimension (schema v0.3 `term_dimension`): `restricts_footprint` says
    whether a record's terms in it narrow the footprint (FP-01); `kind` says whether it
    describes scope, classifies or is opted into (an opt-in dimension restricts whatever the
    flag says, D-36)."""

    KIND_CHOICES = _choices(TermDimensionKind)

    restricts_footprint = models.BooleanField(default=True)

    class Meta:
        db_table = "term_dimension"
        ordering = ["sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["key"], name="term_dimension_key_unique")]


class TermDimensionLabel(LibraryVocabularyLabel):
    vocabulary = models.ForeignKey(TermDimension, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "term_dimension_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["vocabulary", "language"], name="term_dimension_label_unique")]


class InstrumentLevel(LibraryVocabulary):
    """Jurisdiction-neutral instrument levels with a binding default and a rank. The kind
    is optional: null on every level but `standard` (D-37)."""

    KIND_CHOICES = _choices(InstrumentLevelKind)

    binding_default = models.BooleanField(default=True)
    rank = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "instrument_level"
        ordering = ["sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["key"], name="instrument_level_key_unique")]


class InstrumentLevelLabel(LibraryVocabularyLabel):
    vocabulary = models.ForeignKey(InstrumentLevel, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "instrument_level_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["vocabulary", "language"], name="instrument_level_label_unique")]


class ProvisionKind(LibraryVocabulary):
    """Provision kinds, optionally per jurisdiction, with a fixed structural kind."""

    KIND_CHOICES = _choices(ProvisionStructuralKind)

    jurisdiction = models.ForeignKey("library.Jurisdiction", null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "provision_kind"
        ordering = ["sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["key"], name="provision_kind_key_unique")]


class ProvisionKindLabel(LibraryVocabularyLabel):
    vocabulary = models.ForeignKey(ProvisionKind, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "provision_kind_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["vocabulary", "language"], name="provision_kind_label_unique")]


class ChangeType(LibraryVocabulary):
    KIND_CHOICES = _choices(ChangeLifecycleKind)

    class Meta:
        db_table = "change_type"
        ordering = ["sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["key"], name="change_type_key_unique")]


class ChangeTypeLabel(LibraryVocabularyLabel):
    vocabulary = models.ForeignKey(ChangeType, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "change_type_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["vocabulary", "language"], name="change_type_label_unique")]


class DutyType(LibraryVocabulary):
    class Meta:
        db_table = "duty_type"
        ordering = ["sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["key"], name="duty_type_key_unique")]


class DutyTypeLabel(LibraryVocabularyLabel):
    vocabulary = models.ForeignKey(DutyType, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "duty_type_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["vocabulary", "language"], name="duty_type_label_unique")]


class RelationType(LibraryVocabulary):
    class Meta:
        db_table = "relation_type"
        ordering = ["sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["key"], name="relation_type_key_unique")]


class RelationTypeLabel(LibraryVocabularyLabel):
    vocabulary = models.ForeignKey(RelationType, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "relation_type_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["vocabulary", "language"], name="relation_type_label_unique")]


class SourceKind(LibraryVocabulary):
    class Meta:
        db_table = "source_kind"
        ordering = ["sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["key"], name="source_kind_key_unique")]


class SourceKindLabel(LibraryVocabularyLabel):
    vocabulary = models.ForeignKey(SourceKind, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "source_kind_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["vocabulary", "language"], name="source_kind_label_unique")]


class Urgency(LibraryVocabulary):
    """Urgency: `kind` is the pill tone (a tier-one kind), `ordinal` the fixed severity
    order, `sla_days` the editable expectation. KIND_CHOICES is not declared because a
    tone is not a category that must never go empty; the logic validates it."""

    KIND_VALUES = frozenset(tone.value for tone in PillTone)

    ordinal = models.PositiveIntegerField(default=0)
    sla_days = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = "urgency"
        ordering = ["ordinal", "sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["key"], name="urgency_key_unique")]


class UrgencyLabel(LibraryVocabularyLabel):
    vocabulary = models.ForeignKey(Urgency, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "urgency_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["vocabulary", "language"], name="urgency_label_unique")]


class LibraryTag(LibraryVocabulary):
    """Obligation tags (INPUT_DELTAS §1: `obligation.tags` become links to these rows)."""

    class Meta:
        db_table = "library_tag"
        ordering = ["sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["key"], name="library_tag_key_unique")]


class LibraryTagLabel(LibraryVocabularyLabel):
    vocabulary = models.ForeignKey(LibraryTag, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "library_tag_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["vocabulary", "language"], name="library_tag_label_unique")]


class Flag(LibraryVocabulary):
    """Change flags (`regulatory_change.flags` become links to these rows)."""

    class Meta:
        db_table = "flag"
        ordering = ["sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["key"], name="flag_key_unique")]


class FlagLabel(LibraryVocabularyLabel):
    vocabulary = models.ForeignKey(Flag, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "flag_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["vocabulary", "language"], name="flag_label_unique")]


class RejectionReason(LibraryVocabulary):
    """Why a reviewer rejected a proposal (PRO-01). Replaces schema v0.3's
    `proposal.rejection_code` CHECK; the proposal stores the key."""

    class Meta:
        db_table = "rejection_reason"
        ordering = ["sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["key"], name="rejection_reason_key_unique")]


class RejectionReasonLabel(LibraryVocabularyLabel):
    vocabulary = models.ForeignKey(RejectionReason, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "rejection_reason_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["vocabulary", "language"], name="rejection_reason_label_unique")]


# ---------------------------------------------------------------------------------------
# Taxonomy terms (library)
# ---------------------------------------------------------------------------------------
class TaxonomyTerm(LibraryModel):
    """One term of one dimension (schema v0.3 `taxonomy_term`): immutable key unique per
    dimension, labels per language, an optional parent, retired never deleted. A new term
    is a proposal (VOC-07). Not a `Vocabulary` subclass because a term list has no
    default row and its kind is its dimension.

    `jurisdiction` is set on the terms that mirror a jurisdiction row (FP-04, D-28,
    ADR 0026): the reference seed keeps them in step, and the rules that refuse a proposal
    or a tagging in a mirrored dimension read this column rather than a dimension key.

    `verified_origin`, `verified_by_agent` and `applied_by_proposal` are the term's
    machine-confirmed provenance, kept exactly as on every library list
    (`LibraryVocabulary`, INV-05, D-62, D-79); blank and null on a seeded term."""

    dimension = models.ForeignKey(TermDimension, on_delete=models.PROTECT, related_name="terms")
    key = models.SlugField(max_length=80)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    jurisdiction = models.OneToOneField("library.Jurisdiction", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    usage_note = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)
    verified_origin = models.CharField(max_length=16, choices=ORIGIN_CHOICES, blank=True, default="")
    verified_by_agent = models.ForeignKey("agents.Agent", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    applied_by_proposal = models.ForeignKey("proposals.Proposal", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "taxonomy_term"
        ordering = ["sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["dimension", "key"], name="taxonomy_term_dimension_key_unique")]

    def __str__(self) -> str:
        return f"{self.dimension_id}:{self.key}"


class TaxonomyTermLabel(LibraryVocabularyLabel):
    term = models.ForeignKey(TaxonomyTerm, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "taxonomy_term_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["term", "language"], name="taxonomy_term_label_unique")]


# ---------------------------------------------------------------------------------------
# Tier 3: tenant vocabularies (under forced RLS)
# ---------------------------------------------------------------------------------------
class TenantTag(TenantListVocabulary):
    class Meta:
        db_table = "tenant_tag"
        ordering = ["sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["tenant", "key"], name="tenant_tag_key_unique")]


class TenantTagLabel(VocabularyLabel):
    tenant = models.ForeignKey("shared.Tenant", on_delete=models.PROTECT, related_name="+")
    vocabulary = models.ForeignKey(TenantTag, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "tenant_tag_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["vocabulary", "language"], name="tenant_tag_label_unique")]


class Tagging(TenantModel):
    """A tenant tag on a record (schema v0.3 `tagging`): the subject is addressed by kind
    and id because tags apply to obligations, changes and cases alike. Usage counts and
    merges read and re-point these rows (VOC-02)."""

    tag = models.ForeignKey(TenantTag, on_delete=models.PROTECT, related_name="taggings")
    subject_type = models.CharField(max_length=64)
    subject_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tagging"
        ordering = ["created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["tag", "subject_type", "subject_id"], name="tagging_unique")]

    def __str__(self) -> str:
        return f"{self.tag_id}:{self.subject_type}:{self.subject_id}"


class LinkKind(TenantListVocabulary):
    class Meta:
        db_table = "link_kind"
        ordering = ["sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["tenant", "key"], name="link_kind_key_unique")]


class LinkKindLabel(VocabularyLabel):
    tenant = models.ForeignKey("shared.Tenant", on_delete=models.PROTECT, related_name="+")
    vocabulary = models.ForeignKey(LinkKind, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "link_kind_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["vocabulary", "language"], name="link_kind_label_unique")]


class EffortSize(TenantListVocabulary):
    class Meta:
        db_table = "effort_size"
        ordering = ["sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["tenant", "key"], name="effort_size_key_unique")]


class EffortSizeLabel(VocabularyLabel):
    tenant = models.ForeignKey("shared.Tenant", on_delete=models.PROTECT, related_name="+")
    vocabulary = models.ForeignKey(EffortSize, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "effort_size_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["vocabulary", "language"], name="effort_size_label_unique")]


class ComplianceStatus(TenantListVocabulary):
    """A tenant's compliance scale (VOC-05): `kind` is the fixed category, `ordinal` the
    fixed order reports sort by."""

    KIND_CHOICES = _choices(ComplianceCategory)

    ordinal = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "compliance_status"
        ordering = ["ordinal", "sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["tenant", "key"], name="compliance_status_key_unique")]


class ComplianceStatusLabel(VocabularyLabel):
    tenant = models.ForeignKey("shared.Tenant", on_delete=models.PROTECT, related_name="+")
    vocabulary = models.ForeignKey(ComplianceStatus, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "compliance_status_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["vocabulary", "language"], name="compliance_status_label_unique")]


class RiskRating(TenantListVocabulary):
    ordinal = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "risk_rating"
        ordering = ["ordinal", "sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["tenant", "key"], name="risk_rating_key_unique")]


class RiskRatingLabel(VocabularyLabel):
    tenant = models.ForeignKey("shared.Tenant", on_delete=models.PROTECT, related_name="+")
    vocabulary = models.ForeignKey(RiskRating, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "risk_rating_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["vocabulary", "language"], name="risk_rating_label_unique")]


class CaseSubStatus(TenantListVocabulary):
    """A tenant's case sub-statuses inside the seven fixed categories (VOC-04, D-13)."""

    KIND_CHOICES = _choices(CaseStatusCategory)

    class Meta:
        db_table = "case_sub_status"
        ordering = ["sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["tenant", "key"], name="case_sub_status_key_unique")]


class CaseSubStatusLabel(VocabularyLabel):
    tenant = models.ForeignKey("shared.Tenant", on_delete=models.PROTECT, related_name="+")
    vocabulary = models.ForeignKey(CaseSubStatus, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "case_sub_status_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["vocabulary", "language"], name="case_sub_status_label_unique")]


class DismissalReason(TenantListVocabulary):
    class Meta:
        db_table = "dismissal_reason"
        ordering = ["sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["tenant", "key"], name="dismissal_reason_key_unique")]


class DismissalReasonLabel(VocabularyLabel):
    tenant = models.ForeignKey("shared.Tenant", on_delete=models.PROTECT, related_name="+")
    vocabulary = models.ForeignKey(DismissalReason, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "dismissal_reason_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["vocabulary", "language"], name="dismissal_reason_label_unique")]


class ClosureReason(TenantListVocabulary):
    """A tenant's closure reasons (VOC-06), each inside a fixed `CloseReason` category.
    Named ClosureReason because `CloseReason` is the kind (apps/shared/kinds.py)."""

    KIND_CHOICES = _choices(CloseReason)

    class Meta:
        db_table = "close_reason"
        ordering = ["sort_order", "key"]
        constraints = [models.UniqueConstraint(fields=["tenant", "key"], name="close_reason_key_unique")]


class ClosureReasonLabel(VocabularyLabel):
    tenant = models.ForeignKey("shared.Tenant", on_delete=models.PROTECT, related_name="+")
    vocabulary = models.ForeignKey(ClosureReason, on_delete=models.CASCADE, related_name="labels")

    class Meta:
        db_table = "close_reason_label"
        ordering = ["language"]
        constraints = [models.UniqueConstraint(fields=["vocabulary", "language"], name="close_reason_label_unique")]


class VocabularySuggestion(TenantModel):
    """A member's "Suggest" for a tenant list (VOC-03): lands with the holders of
    vocab.manage, who create the row (which resolves the suggestion) or decline it. A
    suggestion for a library list is a proposal instead."""

    list_name = models.CharField(max_length=40)
    key = models.SlugField(max_length=80)
    labels = models.JSONField(default=dict, blank=True)  # schema: VocabularyLabels
    usage_note = models.TextField(blank=True)
    suggested_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=_choices(SuggestionStatus), default=SuggestionStatus.PENDING.value)

    class Meta:
        db_table = "vocabulary_suggestion"
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.list_name}:{self.key}"


# ---------------------------------------------------------------------------------------
# Footprint (tenant)
# ---------------------------------------------------------------------------------------
class FootprintTerm(TenantModel):
    """One term in the company's footprint (schema v0.3 `footprint_term`)."""

    term = models.ForeignKey(TaxonomyTerm, on_delete=models.PROTECT, related_name="footprint_terms")
    added_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "footprint_term"
        ordering = ["added_at", "id"]
        constraints = [models.UniqueConstraint(fields=["tenant", "term"], name="footprint_term_unique")]

    def __str__(self) -> str:
        return f"{self.tenant_id}:{self.term_id}"


class FootprintChangeRequest(TenantModel):
    """A footprint change waiting for a second person (FP-02, INPUT_DELTAS §5): what it
    adds and removes, the preview computed when it was made, and the decision. The
    check constraint makes the requester-is-not-decider rule the database's."""

    requested_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    requested_at = models.DateTimeField(auto_now_add=True)
    adds = models.ManyToManyField(TaxonomyTerm, through="taxonomy.FootprintChangeAdd", related_name="+")
    removes = models.ManyToManyField(TaxonomyTerm, through="taxonomy.FootprintChangeRemove", related_name="+")
    preview = models.JSONField(default=dict, blank=True)  # schema: FootprintPreview
    status = models.CharField(max_length=16, choices=_choices(ApprovalStatus), default=ApprovalStatus.PENDING.value)
    decided_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "footprint_change_request"
        ordering = ["requested_at", "id"]
        # One waiting request per tenant: two sent at the same moment cannot both wait
        # (FP-02, FP-S6). create_request answers 409 `request_pending` from this.
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"],
                condition=models.Q(status=ApprovalStatus.PENDING.value),
                name="footprint_change_request_one_pending",
            )
        ]
        # The four-eyes check constraint `footprint_change_request_four_eyes` is created by
        # RunSQL in migration 0001 as `decided_by_id IS NULL OR decided_by_id <> requested_by_id`.
        # Django can only spell "not equal" as NOT (a = b AND a IS NOT NULL), which is the
        # same rule but not the definition the four-eyes guard reads back from pg_constraint
        # (apps/shared/tests_four_eyes.py), so the database states it in its own words.

    def __str__(self) -> str:
        return f"{self.status} {self.id}"


class FootprintChangeAdd(TenantModel):
    request = models.ForeignKey(FootprintChangeRequest, on_delete=models.CASCADE, related_name="add_links")
    term = models.ForeignKey(TaxonomyTerm, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "footprint_change_add"
        ordering = ["created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["request", "term"], name="footprint_change_add_unique")]

    def __str__(self) -> str:
        return f"+{self.term_id}"


class FootprintChangeRemove(TenantModel):
    request = models.ForeignKey(FootprintChangeRequest, on_delete=models.CASCADE, related_name="remove_links")
    term = models.ForeignKey(TaxonomyTerm, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "footprint_change_remove"
        ordering = ["created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["request", "term"], name="footprint_change_remove_unique")]

    def __str__(self) -> str:
        return f"-{self.term_id}"


class FootprintHistory(AppendOnlyModel, TenantModel):
    """"What was our footprint on that date" without parsing the audit log (schema v0.3
    `footprint_history`): one row per term added or removed, with the request, the actor
    and the step-up assertion that unlocked it. Append-only in Python and by trigger."""

    # A ledger row: a monotonic big integer id breaks ties between rows written in the same
    # transaction, so "the footprint as of" replays them in the order they happened.
    id = models.BigAutoField(primary_key=True)  # type: ignore[assignment]  # TenantModel's uuid id, replaced on purpose
    term = models.ForeignKey(TaxonomyTerm, on_delete=models.PROTECT, related_name="+")
    action = models.CharField(max_length=16, choices=_choices(FootprintAction))
    request = models.ForeignKey(FootprintChangeRequest, null=True, blank=True, on_delete=models.PROTECT, related_name="history")
    changed_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    changed_at = models.DateTimeField(auto_now_add=True)
    step_up_assertion_id = models.UUIDField(null=True, blank=True)
    reason = models.TextField(blank=True)

    class Meta:
        db_table = "footprint_history"
        ordering = ["changed_at", "id"]
        indexes = [models.Index(fields=["tenant", "changed_at"], name="footprint_history_tenant_time")]

    def __str__(self) -> str:
        return f"{self.action} {self.term_id}"



# ---------------------------------------------------------------------------------------
# Markets (tenant)
# ---------------------------------------------------------------------------------------
class WatchedMarket(TenantModel):
    """A market the company watches (FP-04, D-30, INPUT_DELTAS §1): a jurisdiction it does
    not operate in but wants to see. Watching hides nothing, so it is a direct audited
    write rather than a footprint change request.

    The level is computed, never stored: a market is operating when its term is in the
    footprint, otherwise watching when a row here names it, otherwise not followed. So a
    market watched before it became operating reads as watched again once operating stops
    (D-31), and footprint approval never touches these rows."""

    jurisdiction = models.ForeignKey("library.Jurisdiction", on_delete=models.PROTECT, related_name="+")
    added_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "watched_market"
        ordering = ["added_at", "id"]
        constraints = [models.UniqueConstraint(fields=["tenant", "jurisdiction"], name="watched_market_unique")]

    def __str__(self) -> str:
        return f"{self.tenant_id}:{self.jurisdiction_id}"
