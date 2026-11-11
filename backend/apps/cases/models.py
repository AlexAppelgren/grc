"""Models of the cases app (CAS-01 to CAS-08, WAT-04, WAT-05; INPUT_DELTAS §1, §8, §18).

Tenant tables under forced row-level security: one bank's case for one library change, its
decisions about suggested obligation links, and the workflow (impact assessment, actions,
the append-only transition ledger and evidence). All judgement, so none of it sits in a
library row (playbook 14); accepting a link leaves `change_obligation` as it was
(`tests_models.py`), and a case never edits the register.

Every reference from a case table to a person, and from a child to its case, is also a
composite `(tenant_id, …)` foreign key in the migrations (D-18): PostgreSQL checks foreign
keys without row-level security, so only that key refuses another bank's case or a
non-member.
"""

from __future__ import annotations

import enum
from typing import Any

from django.db import models

from apps.shared.adapters.scanner import ScanState
from apps.shared.audit import AppendOnlyModel
from apps.shared.tenancy import TenantModel
from apps.taxonomy.models import CaseStatusCategory
from apps.shared.kinds import choices


class CaseLinkDecision(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): what a bank said about one suggested obligation
    link on its own case (WAT-04, ruling C). There is no third thing to say about a link.
    """

    ACCEPTED = "accepted"
    REMOVED = "removed"


class AssessmentApplies(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): the impact assessment's verdict (CAS-03)."""

    YES = "yes"
    PARTLY = "partly"
    NO = "no"


class EvidenceKind(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): what a piece of evidence is (CAS-05). Only a
    file has bytes in storage, so only a file is scanned and downloaded."""

    FILE = "file"
    LINK = "link"
    REFERENCE = "reference"


# The categories between triage and the close: a case in any of them has an owner.
OWNED_CATEGORIES = (
    CaseStatusCategory.ASSIGNED,
    CaseStatusCategory.ASSESSING,
    CaseStatusCategory.IMPLEMENTING,
    CaseStatusCategory.SIGNOFF,
)


class RemovedNotDeleted(RuntimeError):
    """An action or a piece of evidence was deleted from Python. Nothing is overwritten:
    removal sets `removed_at`, and the row keeps its name for the case file and the audit
    trail (playbook 4.3, CAS-05)."""


class _RemovedNotDeletedQuerySet(models.QuerySet):
    def delete(self) -> tuple[int, dict[str, int]]:
        raise RemovedNotDeleted(f"{self.model.__name__} rows are removed with removed_at, never deleted")


# What a workflow read and write joins beside the case. Field names, kept beside the model
# (a logic module may hold no string that reads as a role key, ID-S18).
CASE_JOINS = (
    "change",
    "urgency",
    "sub_status",
    "owner",
    "owner_team",
    "triaged_by",
    "dismissed_reason",
    "dismissed_by",
    "signoff_requested_by",
    "signed_off_by",
    "close_reason",
)


class ChangeCase(TenantModel):
    """One bank's case for one regulatory change (CAS-01).

    Created `new` when the change is registered, with the suggested urgency and the footprint
    verdict; `UNIQUE (tenant, change)` makes it one per bank per change. `so_what_text`
    starts as the library's draft; `so_what_confirmed` keeps it labelled until a person
    confirms, and a constraint makes a confirmation name a person and a time (WAT-05, AUD-02).

    `status` is the fixed category the guards read; `sub_status` a bank row inside it (D-13).
    CHECKs hold the state machine's promises: a dismissal names a reason, every category from
    triage to close has an owner, and the signer is not the requester (CAS-06). `version` is
    the `If-Match` of every case write (CAS-08). Who closed it is on the last transition row.
    """

    change = models.ForeignKey("watch.RegulatoryChange", on_delete=models.PROTECT, related_name="cases")
    status = models.CharField(
        max_length=16, choices=choices(CaseStatusCategory), default=CaseStatusCategory.NEW.value
    )
    urgency = models.ForeignKey("taxonomy.Urgency", on_delete=models.PROTECT, related_name="+")
    # False until a person triages: the urgency above is the agent's suggestion (INPUT_DELTAS §8).
    urgency_confirmed = models.BooleanField(default=False)
    footprint_match = models.BooleanField()
    owner = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    # A team of the bank beside the owner, never instead of one (CAS-02, TEN-03): it stays
    # when the owner changes or leaves. A composite key (cases 0005) keeps it this bank's.
    owner_team = models.ForeignKey("taxonomy.Team", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    so_what_text = models.TextField(blank=True)
    so_what_confirmed = models.BooleanField(default=False)
    so_what_confirmed_by = models.ForeignKey(
        "identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    so_what_confirmed_at = models.DateTimeField(null=True, blank=True)
    # The Monday (bank time) of the first briefing that carried the case; null until then (HOM-02).
    briefing_week = models.DateField(null=True, blank=True)
    sub_status = models.ForeignKey(
        "taxonomy.CaseSubStatus", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    triaged_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    triaged_at = models.DateTimeField(null=True, blank=True)
    dismissed_reason = models.ForeignKey(
        "taxonomy.DismissalReason", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    dismissed_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    dismissed_at = models.DateTimeField(null=True, blank=True)
    signoff_requested_by = models.ForeignKey(
        "identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    signoff_requested_at = models.DateTimeField(null=True, blank=True)
    signed_off_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    close_reason = models.ForeignKey(
        "taxonomy.ClosureReason", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    closed_note = models.TextField(blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    # Creation plus the bank's `triage_target_hours`, set once (COL-02); reminders read it only
    # while the case is `new`. Null on a case that left `new` before the column existed.
    triage_due_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "change_case"
        # Newest first with the row id as a stable tiebreak.
        ordering = ["-created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "change"], name="change_case_one_per_tenant"),
            models.CheckConstraint(
                condition=(
                    models.Q(so_what_confirmed=False, so_what_confirmed_by__isnull=True, so_what_confirmed_at__isnull=True)
                    | models.Q(
                        so_what_confirmed=True, so_what_confirmed_by__isnull=False, so_what_confirmed_at__isnull=False
                    )
                ),
                name="change_case_so_what_confirmation_names_a_person",
            ),
            # What the composite keys of the child tables point at (INPUT_DELTAS §1).
            models.UniqueConstraint(fields=["tenant", "id"], name="change_case_tenant_id_unique"),
            models.CheckConstraint(
                condition=~models.Q(status=CaseStatusCategory.DISMISSED.value)
                | models.Q(dismissed_reason__isnull=False),
                name="change_case_dismissal_needs_a_reason",
            ),
            models.CheckConstraint(
                condition=~models.Q(status__in=[category.value for category in OWNED_CATEGORIES])
                | models.Q(owner__isnull=False),
                name="change_case_worked_case_has_an_owner",
            ),
        ]
        # `change_case_four_eyes` (CAS-06, AC-CAS1) is created by RunSQL in 0002 as
        # `signed_off_by_id IS NULL OR (signoff_requested_by_id IS NOT NULL AND
        # signed_off_by_id <> signoff_requested_by_id)`; apps/shared/tests_four_eyes.py reads it.
        indexes = [
            models.Index(fields=["tenant", "status", "urgency"], name="change_case_queue_idx"),
            models.Index(
                fields=["tenant", "owner"],
                condition=~models.Q(
                    status__in=[CaseStatusCategory.CLOSED.value, CaseStatusCategory.DISMISSED.value]
                ),
                name="change_case_owner_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tenant_id}:{self.change_id}"


class CaseObligationLink(TenantModel):
    """What one bank decided about one suggested obligation link, on its own case (WAT-04,
    ruling C). Holds and writes no library row. A removal is a `removed` row (playbook 4.3);
    one decision per link, rewritten in place.
    """

    case = models.ForeignKey(ChangeCase, on_delete=models.CASCADE, related_name="obligation_links")
    obligation = models.ForeignKey("library.Obligation", on_delete=models.PROTECT, related_name="+")
    decision = models.CharField(max_length=16, choices=choices(CaseLinkDecision))
    decided_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "case_obligation_link"
        # Newest decision first, with a stable tiebreak.
        ordering = ["-decided_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "case", "obligation"], name="case_obligation_link_one_decision"
            )
        ]

    def __str__(self) -> str:
        return f"{self.case_id}:{self.obligation_id}:{self.decision}"


class ImpactAssessment(TenantModel):
    """One case's impact assessment (CAS-03): whether the change applies, why, what must
    change, the bank's deadline and the effort. One per case. No `contributors` column: the
    contributor teams are the case's team participants (D-20). A CHECK holds that a saved
    assessment says why; `version` is the `If-Match` of its writes (AC-CAS2).
    """

    case = models.OneToOneField(ChangeCase, on_delete=models.PROTECT, related_name="assessment")
    applies = models.CharField(
        max_length=16, choices=choices(AssessmentApplies), default=AssessmentApplies.YES.value
    )
    why = models.TextField(blank=True)
    what_must_change = models.TextField(blank=True)
    internal_deadline = models.DateField(null=True, blank=True)
    effort = models.ForeignKey("taxonomy.EffortSize", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    saved = models.BooleanField(default=False)
    saved_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    saved_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "impact_assessment"
        ordering = ["case", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(saved=False) | ~models.Q(why=""), name="impact_assessment_saved_says_why"
            ),
            models.CheckConstraint(
                condition=models.Q(saved=False, saved_by__isnull=True, saved_at__isnull=True)
                | models.Q(saved=True, saved_by__isnull=False, saved_at__isnull=False),
                name="impact_assessment_saved_names_a_person",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.case_id}:{self.applies}"


class Action(TenantModel):
    """One thing that must be done for a case, with an owner and a due date (CAS-04).
    Removed, never deleted (`delete()` raises). `version` is its `If-Match`. The designed
    ticket columns are deferred (INPUT_DELTAS §1). The partial index serves every open-and-due
    read.
    """

    case = models.ForeignKey(ChangeCase, on_delete=models.PROTECT, related_name="actions")
    title = models.TextField()
    owner = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    due_date = models.DateField()
    done_at = models.DateTimeField(null=True, blank=True)
    done_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    removed_at = models.DateTimeField(null=True, blank=True)
    removed_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    version = models.PositiveIntegerField(default=1)

    objects = _RemovedNotDeletedQuerySet.as_manager()

    class Meta:
        db_table = "action"
        ordering = ["due_date", "created_at", "id"]
        constraints = [
            models.CheckConstraint(condition=~models.Q(title=""), name="action_has_a_title"),
            models.CheckConstraint(
                condition=models.Q(done_at__isnull=True, done_by__isnull=True)
                | models.Q(done_at__isnull=False, done_by__isnull=False),
                name="action_done_names_a_person",
            ),
            models.CheckConstraint(
                condition=models.Q(removed_at__isnull=True, removed_by__isnull=True)
                | models.Q(removed_at__isnull=False, removed_by__isnull=False),
                name="action_removal_names_a_person",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "due_date"],
                condition=models.Q(done_at__isnull=True, removed_at__isnull=True),
                name="action_open_due_idx",
            )
        ]

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:  # compliance: allow-kwargs Django Model.delete signature
        raise RemovedNotDeleted("an action is removed with removed_at, never deleted")

    def __str__(self) -> str:
        return f"{self.case_id}:{self.title}"


class CaseTransition(AppendOnlyModel, TenantModel):
    """One move of a case between categories (CAS-08), written in the move's transaction.
    Append-only in Python and by trigger. `by_user` is empty only for a move no person made;
    `from_status` is empty on a case's first row.
    """

    case = models.ForeignKey(ChangeCase, on_delete=models.PROTECT, related_name="+")
    from_status = models.CharField(max_length=16, choices=choices(CaseStatusCategory), blank=True)
    to_status = models.CharField(max_length=16, choices=choices(CaseStatusCategory))
    at = models.DateTimeField(auto_now_add=True)
    by_user = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    note = models.TextField(blank=True)

    class Meta:
        db_table = "case_transition"
        # Oldest first, with the row id as a stable tiebreak for two moves in one instant.
        ordering = ["at", "id"]
        indexes = [models.Index(fields=["case", "at"], name="case_transition_idx")]

    def __str__(self) -> str:
        return f"{self.case_id}:{self.from_status}->{self.to_status}"


class Evidence(TenantModel):
    """One piece of evidence on a case: a file, a link or a reference (CAS-05).

    Only a file has bytes (private bucket, `storage_key`); a CHECK per kind makes a half-
    written row impossible, so neither a link nor a reference can be downloaded. A row starts
    `pending` and a download serves only `clean`. Removed, never deleted (`delete()` raises).
    """

    case = models.ForeignKey(ChangeCase, on_delete=models.PROTECT, related_name="evidence")
    kind = models.CharField(max_length=16, choices=choices(EvidenceKind))
    name = models.TextField()
    storage_key = models.TextField(blank=True)
    url = models.TextField(blank=True)
    content_hash = models.CharField(max_length=128, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    mime_type = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    removed_at = models.DateTimeField(null=True, blank=True)
    scan_state = models.CharField(max_length=16, choices=choices(ScanState), default=ScanState.PENDING.value)
    scanned_at = models.DateTimeField(null=True, blank=True)

    objects = _RemovedNotDeletedQuerySet.as_manager()

    class Meta:
        db_table = "evidence"
        # Newest first, with the row id as a stable tiebreak.
        ordering = ["-uploaded_at", "id"]
        constraints = [
            models.CheckConstraint(condition=~models.Q(name=""), name="evidence_has_a_name"),
            models.CheckConstraint(
                condition=~models.Q(kind=EvidenceKind.FILE.value)
                | (
                    ~models.Q(storage_key="")
                    & ~models.Q(content_hash="")
                    & models.Q(size_bytes__isnull=False)
                    & ~models.Q(mime_type="")
                ),
                name="evidence_file_is_stored_and_hashed",
            ),
            models.CheckConstraint(
                condition=~models.Q(kind=EvidenceKind.LINK.value) | (~models.Q(url="") & models.Q(storage_key="")),
                name="evidence_link_has_a_url",
            ),
            models.CheckConstraint(
                condition=~models.Q(kind=EvidenceKind.REFERENCE.value) | models.Q(storage_key=""),
                name="evidence_reference_has_no_file",
            ),
            models.CheckConstraint(
                condition=models.Q(scan_state=ScanState.PENDING.value) | models.Q(scanned_at__isnull=False),
                name="evidence_scan_names_a_time",
            ),
        ]

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:  # compliance: allow-kwargs Django Model.delete signature
        raise RemovedNotDeleted("evidence is removed with removed_at, never deleted")

    def __str__(self) -> str:
        return f"{self.case_id}:{self.kind}:{self.name}"
