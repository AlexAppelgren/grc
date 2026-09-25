"""Models of the register app (chunk 8; REG-01 to REG-05, TEN-03): the bank's judgement laid
over the shared library, every table a tenant table under forced row-level security.

A register entry (`TenantObligation`) is keyed on the obligation's id, so a bank-private
obligation joins unchanged later, and it is created by `logic.ensure_register_entry()` alone.
"Applies" and "we comply" are separate columns and neither derives from the other (CLAUDE.md
section 5). Statuses, scales, sources and reasons are the tenant's own list rows; the
applicability and the assessment method are kinds, because the rules branch on them.

PostgreSQL checks a foreign key without row-level security, so every reference to another
tenant row is also a composite `(tenant_id, …)` key, written as SQL in the migrations: to
`UNIQUE (tenant_id, id)` on the target, and to `membership_tenant_user_unique` for a person,
which makes every person named here a member of the same bank.

Nothing is overwritten: an assessment is an append-only ledger row with a trigger, and an
internal link is removed by stamping `removed_at` and `removed_by`, never deleted. Risk
acceptance is the one four-eyes step here (`gap_four_eyes`); applicability has none (D-75).
The Statement of Applicability's units are register 0003 (c8-reg-units)."""

from __future__ import annotations

import enum
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.shared.audit import AppendOnlyModel
from apps.shared.tenancy import TenantModel


class Applicability(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): does the obligation apply to us (REG-01). A new
    entry is `not_assessed` until one person holding `applicability.approve` answers (D-75)."""

    APPLIES = "applies"
    DOES_NOT_APPLY = "does_not_apply"
    NOT_ASSESSED = "not_assessed"


class AssessmentMethod(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): how a status was assessed (REG-04,
    `schema.sql` `assessment_method`). Audit results are the assessments of the two audit
    methods, which the standards reporting branches on."""

    SELF_ASSESSMENT = "self_assessment"
    SECOND_LINE_REVIEW = "second_line_review"
    INTERNAL_AUDIT = "internal_audit"
    EXTERNAL_AUDIT = "external_audit"
    REGULATOR = "regulator"


def _choices(kind: type[enum.StrEnum]) -> list[tuple[str, str]]:
    return [(value.value, value.value) for value in kind]


def _applicability() -> models.CharField:
    return models.CharField(max_length=16, choices=_choices(Applicability), default=Applicability.NOT_ASSESSED.value)


def _person(*, null: bool = True) -> models.ForeignKey:
    return models.ForeignKey("identity.User", null=null, blank=null, on_delete=models.PROTECT, related_name="+")


class TenantObligation(TenantModel):
    """One bank's register entry on one obligation (REG-01, REG-02). Applicability and its
    reason, who decided it and when, beside the compliance status: two facts, two columns.
    The status is the tenant's `compliance_status` row, risk its `risk_rating` row, and the
    owner a person or a team (TEN-03)."""

    obligation = models.ForeignKey("library.Obligation", on_delete=models.PROTECT, related_name="+")
    applicability = _applicability()
    applicability_reason = models.TextField(blank=True)
    applicability_decided_at = models.DateTimeField(null=True, blank=True)
    applicability_decided_by = _person()
    compliance_status = models.ForeignKey("taxonomy.ComplianceStatus", on_delete=models.PROTECT, related_name="+")
    risk_rating = models.ForeignKey("taxonomy.RiskRating", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    status_note = models.TextField(blank=True)
    first_line_owner = _person()
    compliance_contact = _person()
    owner_team = models.ForeignKey("taxonomy.Team", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    process = models.CharField(max_length=200, blank=True)
    system = models.CharField(max_length=200, blank=True)
    evidence_location = models.CharField(max_length=500, blank=True)
    next_review_date = models.DateField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenant_obligation"
        ordering = ["obligation_id", "id"]
        constraints = [models.UniqueConstraint(fields=["tenant", "obligation"], name="tenant_obligation_unique")]

    def __str__(self) -> str:
        return f"{self.obligation_id}@{self.tenant_id}"


class TenantObligationScope(TenantModel):
    """The entry's answer and status for one legal entity, and optionally one product of it,
    where the obligation spans several (REG-01, REG-02, D-42). Created, through `record()`, in
    the transaction of the write that needs it; a read never writes one. Owned by a person
    or a team, never both."""

    tenant_obligation = models.ForeignKey(TenantObligation, on_delete=models.PROTECT, related_name="scopes")
    org_unit = models.ForeignKey("tenants.OrgUnit", on_delete=models.PROTECT, related_name="+")
    product = models.ForeignKey("tenants.TenantProduct", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    applicability = _applicability()
    applicability_reason = models.TextField(blank=True)
    applicability_decided_at = models.DateTimeField(null=True, blank=True)
    applicability_decided_by = _person()
    compliance_status = models.ForeignKey("taxonomy.ComplianceStatus", on_delete=models.PROTECT, related_name="+")
    risk_rating = models.ForeignKey("taxonomy.RiskRating", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    status_note = models.TextField(blank=True)
    owner = _person()
    owner_team = models.ForeignKey("taxonomy.Team", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    process = models.CharField(max_length=200, blank=True)
    system = models.CharField(max_length=200, blank=True)
    evidence_location = models.CharField(max_length=500, blank=True)
    next_review_date = models.DateField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenant_obligation_scope"
        ordering = ["tenant_obligation_id", "org_unit_id", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_obligation", "org_unit", "product"],
                name="tenant_obligation_scope_unique",
                nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=models.Q(owner__isnull=True) | models.Q(owner_team__isnull=True),
                name="tenant_obligation_scope_one_owner_kind",
            ),
        ]


class ComplianceAssessment(AppendOnlyModel, TenantModel):
    """One status assessment, kept for ever (REG-04): the entry, or one of its scope rows,
    holds only the current status. Append-only in Python and by trigger."""

    tenant_obligation = models.ForeignKey(TenantObligation, on_delete=models.PROTECT, related_name="+")
    scope = models.ForeignKey(TenantObligationScope, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    method = models.CharField(
        max_length=24, choices=_choices(AssessmentMethod), default=AssessmentMethod.SELF_ASSESSMENT.value
    )
    status = models.ForeignKey("taxonomy.ComplianceStatus", on_delete=models.PROTECT, related_name="+")
    risk_rating = models.ForeignKey("taxonomy.RiskRating", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    rationale = models.TextField()
    next_review_date = models.DateField(null=True, blank=True)
    assessed_by = _person(null=False)
    assessed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "compliance_assessment"
        ordering = ["assessed_at", "id"]


class Gap(TenantModel):
    """A gap with an owner and a date, not a note on a status (REG-03). Its status, severity,
    source and acceptance reason are the tenant's list rows. Risk acceptance is behind four
    eyes: the person who accepts is never the person who asked (`gap_four_eyes`), and an
    acceptance names its reason and its requester (`gap_acceptance_complete`); a trigger
    keeps a gap out of a `risk_accepted` status until someone has accepted it."""

    tenant_obligation = models.ForeignKey(TenantObligation, on_delete=models.PROTECT, related_name="gaps")
    org_unit = models.ForeignKey("tenants.OrgUnit", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    severity = models.ForeignKey("taxonomy.RiskRating", on_delete=models.PROTECT, related_name="+")
    source = models.ForeignKey("taxonomy.GapSource", on_delete=models.PROTECT, related_name="+")
    status = models.ForeignKey("taxonomy.GapStatus", on_delete=models.PROTECT, related_name="+")
    identified_by = _person(null=False)
    identified_at = models.DateTimeField(default=timezone.now)
    owner = _person()
    owner_team = models.ForeignKey("taxonomy.Team", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    target_date = models.DateField(null=True, blank=True)
    remediation = models.TextField(blank=True)
    acceptance_reason = models.ForeignKey(
        "taxonomy.RiskAcceptanceReason", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    acceptance_note = models.TextField(blank=True)
    acceptance_requested_by = _person()
    acceptance_requested_at = models.DateTimeField(null=True, blank=True)
    accepted_by = _person()
    accepted_at = models.DateTimeField(null=True, blank=True)
    closed_by = _person()
    closed_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "gap"
        ordering = ["identified_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(accepted_by__isnull=True)
                | models.Q(
                    acceptance_reason__isnull=False,
                    acceptance_requested_by__isnull=False,
                    accepted_at__isnull=False,
                ),
                name="gap_acceptance_complete",
            ),
            models.CheckConstraint(
                condition=models.Q(owner__isnull=True) | models.Q(owner_team__isnull=True),
                name="gap_one_owner_kind",
            ),
        ]
        # The four-eyes check constraint `gap_four_eyes` is created by RunSQL in register 0002
        # as `accepted_by_id IS NULL OR accepted_by_id <> acceptance_requested_by_id`. Django
        # can only spell "not equal" as NOT (a = b), which is the same rule but not the
        # definition the four-eyes guard reads back from pg_constraint
        # (apps/shared/tests_four_eyes.py), so the database states it in its own words.

    def __str__(self) -> str:
        return self.title


class Interpretation(TenantModel):
    """How we read this rule (REG-04), in numbered versions per entry. A new version stamps
    `superseded_at` on the one before; the text of a version is never rewritten."""

    tenant_obligation = models.ForeignKey(TenantObligation, on_delete=models.PROTECT, related_name="interpretations")
    version_number = models.PositiveIntegerField()
    body = models.TextField()
    author = _person(null=False)
    created_at = models.DateTimeField(default=timezone.now)
    superseded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "interpretation"
        ordering = ["tenant_obligation_id", "version_number"]
        constraints = [
            models.UniqueConstraint(fields=["tenant_obligation", "version_number"], name="interpretation_version_unique")
        ]


class InternalLink(TenantModel):
    """A policy, procedure, control, process or system the entry links to (REG-05), with the
    reference an outside GRC system knows it by. The item is a composite key, so another
    bank's item cannot be linked; one live link per entry and item. Removed by stamping
    `removed_at` and `removed_by`, never deleted (R2_CROSS_CUTTING (l))."""

    tenant_obligation = models.ForeignKey(TenantObligation, on_delete=models.PROTECT, related_name="links")
    internal_item = models.ForeignKey("tenants.InternalItem", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    label = models.CharField(max_length=200)
    url = models.URLField(max_length=2000, blank=True)
    external_ref = models.CharField(max_length=200, blank=True)
    created_by = _person(null=False)
    created_at = models.DateTimeField(default=timezone.now)
    removed_at = models.DateTimeField(null=True, blank=True)
    removed_by = _person()

    class Meta:
        db_table = "internal_link"
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_obligation", "internal_item"],
                condition=models.Q(removed_at__isnull=True),
                name="internal_link_live_unique",
            )
        ]

    def __str__(self) -> str:
        return self.label

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:  # compliance: allow-kwargs Django Model.delete signature
        raise ValidationError("A link is removed by stamping removed_at, never deleted.", code="remove_not_delete")
