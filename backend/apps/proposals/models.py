"""Models of the proposals app (PRO-01, PRO-02, AC-PRO2).

`Proposal` is the door into the library, not the library: a plain model in the library zone,
created from apps/proposals/logic.py, while only apps/proposals/apply.py writes library rows.
A batch (PRO-04, AGT-05) is one proposal with `is_batch` and a `ProposalBatchRow` per record,
each written once and decided once. `ProposalTenant` links a proposal a bank made to that
bank under row-level security.

`owner_tenant` is a zone, not a link (INV-07, OWN-03, D-57, ADR 0050): a proposal of the
bank's own record is decided inside that bank and never reaches the console. `logic.create`
sets it, never a request body. `proposal` is a mixed table in the split shape (H15): a bank's
session may insert, beside its own rows, only a shared proposal it files; the console reads
no owned row, because the database hides it.

`proposal_four_eyes` (RunSQL) is the database's word on "never the proposer": a repeated
user, key or agent definition, and a reviewing key that names no agent, are refused
(PRO-S13, PRO-S14, D-62, ADR 0054). The agent columns are copied from the acting key at the
one write path, since a constraint cannot dereference a key.
"""

from __future__ import annotations

import enum
import uuid
from collections.abc import Collection
from typing import Any

from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.shared.tenancy import TenantModel
from apps.shared.kinds import choices


class ProposalKind(enum.StrEnum):
    """What a proposal changes; apply() branches on it. New-record kinds (`new_instrument`,
    `new_obligation`, `new_provision`, `new_recurring_duty`) name no target (PRO-01, INV-01,
    INV-02, INV-03, REG-07). `obligation_scope` is a batch's re-tag (PRO-04, AGT-05).
    `new_control` is a bank's own control, an internal item in the bank's zone, never a
    library row (OWN-05, D-99). `new_translations` only adds machine-made rows (INV-05,
    D-129). A watch link is never a proposal (D-64)."""

    VOCABULARY_CREATE = "vocabulary_create"
    VOCABULARY_RELABEL = "vocabulary_relabel"
    VOCABULARY_RETIRE = "vocabulary_retire"
    VOCABULARY_MERGE = "vocabulary_merge"
    VOCABULARY_RESTORE = "vocabulary_restore"
    TERM_CREATE = "term_create"
    TERM_UPDATE = "term_update"
    NEW_OBLIGATION_VERSION = "new_obligation_version"
    NEW_INSTRUMENT = "new_instrument"
    NEW_OBLIGATION = "new_obligation"
    NEW_PROVISION = "new_provision"
    NEW_PROVISION_VERSION = "new_provision_version"
    OBLIGATION_SCOPE = "obligation_scope"
    NEW_RECURRING_DUTY = "new_recurring_duty"
    NEW_CONTROL = "new_control"
    NEW_INSTRUMENT_SUMMARY = "new_instrument_summary"
    NEW_TRANSLATIONS = "new_translations"


class ProposalStatus(enum.StrEnum):
    OPEN = "open"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class OriginType(enum.StrEnum):
    """Where a record came from (schema v0.3 `origin_type`): an agent or a person."""

    AGENT = "agent"
    USER = "user"


class Proposal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=40, choices=choices(ProposalKind))
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.UUIDField(null=True, blank=True)
    change_id = models.UUIDField(null=True, blank=True)
    title = models.CharField(max_length=500)
    payload = models.JSONField(default=dict, blank=True)  # schema: ProposalPayload
    field_sources = models.JSONField(default=dict, blank=True)  # schema: ProposalFieldSources
    source_label = models.CharField(max_length=500, blank=True)
    source_url = models.URLField(max_length=2000, blank=True)
    # What the injection screen found in the texts the proposer sent (AGT-07, H40): the
    # queue shows it, and no agent approves while it stands.
    risk_flags = ArrayField(models.CharField(max_length=40), default=list, blank=True)
    effective_from = models.DateField(null=True, blank=True)
    origin = models.CharField(max_length=16, choices=choices(OriginType))
    agent_run_id = models.UUIDField(null=True, blank=True)
    model = models.CharField(max_length=200, blank=True)
    proposed_by_user = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    proposed_by_api_key = models.ForeignKey("identity.ApiKey", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    proposed_by_agent = models.ForeignKey("agents.Agent", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    idempotency_key = models.CharField(max_length=200, null=True, blank=True)
    proposed_in_tenant = models.BooleanField(default=False)
    status = models.CharField(max_length=16, choices=choices(ProposalStatus), default=ProposalStatus.OPEN.value)
    reviewed_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    reviewed_by_api_key = models.ForeignKey("identity.ApiKey", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    reviewed_by_agent = models.ForeignKey("agents.Agent", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_code = models.CharField(max_length=64, blank=True)
    review_note = models.TextField(blank=True)
    corrected_payload = models.JSONField(null=True, blank=True)  # schema: ProposalPayload
    corrected_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    corrected_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    # A batch (PRO-04) is this row plus `row_count` rows in `proposal_batch_row`, held
    # together by `proposal_batch_row_count`.
    is_batch = models.BooleanField(default=False)
    row_count = models.PositiveIntegerField(default=0)
    # The bank whose own record this proposes (INV-07, OWN-03), or null for the shared
    # library. Set by the server only (`logic.create`); row-level security reads it.
    owner_tenant = models.ForeignKey("shared.Tenant", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "proposal"
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["status", "created_at"], name="proposal_queue_idx")]
        # A retry key is the proposer's own (playbook 4.3): one person's or one key's, never
        # a value another bank or the platform's agent could claim first or replay into.
        constraints = [
            models.UniqueConstraint(
                fields=["proposed_by_user", "idempotency_key"],
                condition=models.Q(idempotency_key__isnull=False, proposed_by_user__isnull=False),
                name="proposal_idempotency_per_user",
            ),
            models.UniqueConstraint(
                fields=["proposed_by_api_key", "idempotency_key"],
                condition=models.Q(idempotency_key__isnull=False, proposed_by_api_key__isnull=False),
                name="proposal_idempotency_per_key",
            ),
            models.CheckConstraint(
                condition=models.Q(is_batch=True, row_count__gt=0) | models.Q(is_batch=False, row_count=0),
                name="proposal_batch_row_count",
            ),
        ]
        # `proposal_four_eyes` is RunSQL (migrations 0001, 0003): reviewer differs from the
        # proposer by user, key and agent, and a reviewing key must name an agent, since
        # NULL <> NULL would pass two unbound keys. The four-eyes guard reads it back from
        # pg_constraint.

    def __str__(self) -> str:
        return f"{self.kind} {self.id}"


class BatchRowDecision(enum.StrEnum):
    """A batch row's decision (PRO-04): every row starts pending and is decided once."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# The only columns of a batch row that change after it is written, and only once.
DECISION_FIELDS = ("decision", "rejection_reason", "decided_by", "decided_at")


class BatchRowRefused(RuntimeError):
    """A batch row was changed beyond its one decision, or deleted, from Python."""


class ProposalBatchRowQuerySet(models.QuerySet["ProposalBatchRow"]):
    def update(self, **kwargs: Any) -> int:  # compliance: allow-kwargs Django QuerySet signature
        raise BatchRowRefused("A batch row is written once; only its decision may change, through save()")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise BatchRowRefused("A batch row is never deleted")

    def decide(self, row_ids: Collection[uuid.UUID], *, decision: str, rejection_reason: Any, decided_by: Any, decided_at: Any) -> None:
        """The one bulk write a batch row takes: one decision for the rows `row_ids` in one
        UPDATE of the decision fields. A row already decided refuses the whole write, as
        `save()` does; the trigger `proposal_batch_row_decision_guard` stays the database's
        word."""
        ids = set(row_ids)
        pending = self.filter(pk__in=ids, decision=BatchRowDecision.PENDING.value)
        written = models.QuerySet.update(
            pending, decision=decision, rejection_reason=rejection_reason, decided_by=decided_by, decided_at=decided_at
        )
        if written != len(ids):
            raise BatchRowRefused("This batch row is already decided; a decision is made once")


class ProposalBatchRow(models.Model):
    """One library record a batch would change (PRO-04, AGT-05), with the preview computed
    when filed: `before` and `after` hold only the fields that would change. Library zone,
    no tenant column.

    Append-only but for one update: `decision` moves from `pending` once, with `decided_at`,
    `decided_by` (a person) and, for a rejection, a reason. The trigger
    `proposal_batch_row_decision_guard` refuses every other UPDATE, a second decision, a
    decision by the proposer and any DELETE; `save()` and the queryset refuse first."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proposal = models.ForeignKey(Proposal, on_delete=models.PROTECT, related_name="batch_rows")
    # What the row changes, as `target_type` names it on a single proposal.
    subject_type = models.CharField(max_length=64)
    subject_id = models.UUIDField()
    before = models.JSONField(default=dict, blank=True)  # schema: ProposalBatchRowPayload
    after = models.JSONField(default=dict, blank=True)  # schema: ProposalBatchRowPayload
    decision = models.CharField(max_length=16, choices=choices(BatchRowDecision), default=BatchRowDecision.PENDING.value)
    rejection_reason = models.ForeignKey("taxonomy.RejectionReason", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    decided_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ProposalBatchRowQuerySet.as_manager()

    class Meta:
        db_table = "proposal_batch_row"
        ordering = ["proposal", "subject_type", "subject_id"]
        constraints = [
            models.UniqueConstraint(fields=["proposal", "subject_type", "subject_id"], name="proposal_batch_row_unique"),
            # Decided means dated, and a rejection names its reason: the playbook's
            # "rejection needs a reason", held by the database.
            models.CheckConstraint(
                condition=(
                    models.Q(decision=BatchRowDecision.PENDING.value, decided_at__isnull=True, decided_by__isnull=True, rejection_reason__isnull=True)
                    | models.Q(decision=BatchRowDecision.APPROVED.value, decided_at__isnull=False, rejection_reason__isnull=True)
                    | models.Q(decision=BatchRowDecision.REJECTED.value, decided_at__isnull=False, rejection_reason__isnull=False)
                ),
                name="proposal_batch_row_decided",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.subject_type} {self.subject_id} ({self.decision})"

    def save(self, *args: Any, **kwargs: Any) -> None:  # compliance: allow-kwargs Django Model.save signature
        if not self._state.adding:
            fields = kwargs.get("update_fields")
            if fields is None or not set(fields) <= set(DECISION_FIELDS):
                raise BatchRowRefused("A batch row is written once; only its decision may change")
            if not type(self).objects.filter(pk=self.pk, decision=BatchRowDecision.PENDING.value).exists():
                raise BatchRowRefused("This batch row is already decided; a decision is made once")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:  # compliance: allow-kwargs Django Model.delete signature
        raise BatchRowRefused("A batch row is never deleted")


class ProposalTenant(TenantModel):
    """Which tenant a proposal was made in (PRO-03), under forced row-level security, so the
    library-zone `proposal` row never carries a tenant id and the console withholds the
    proposer without learning their bank."""

    proposal = models.ForeignKey(Proposal, on_delete=models.PROTECT, related_name="tenant_links")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "proposal_tenant"
        ordering = ["created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["proposal", "tenant"], name="proposal_tenant_unique")]

    def __str__(self) -> str:
        return f"{self.tenant_id}:{self.proposal_id}"
