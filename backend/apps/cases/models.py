"""Models of the cases app (CAS-01, WAT-04, WAT-05; schema v0.3 `change_case`;
INPUT_DELTAS §1, §8).

Two tenant tables, both `TenantModel` under enabled and forced row-level security: one
bank's case for one library change, and that bank's own decision about a suggested
obligation link. Everything here is judgement, which is why it is not in the watch zone —
the change, its timeline, its classification and its suggested links are library facts
every bank shares, and no bank's view of them may sit in a library row (playbook 14).

Neither table writes a library row and neither reads one to decide: accepting a link on a
case leaves `change_obligation` exactly as it was, which `tests_models.py` proves. A case
is not a register entry either: "applies" and "we comply" are separate facts kept in the
register (REG-01, REG-02), and closing a case never edits the inventory.

Chunk 9 (`c9-case-models`) adds the workflow: the case's triage, dismissal, sign-off and
close columns with the four-eyes CHECK, and four child tables, each a tenant table under
forced row-level security — the impact assessment, actions, the append-only transition
ledger and evidence. Every reference from a case table to a person, and from a child to
its case, is also a composite `(tenant_id, …)` foreign key added by the migration
(INPUT_DELTAS §1, D-18): PostgreSQL checks foreign keys with row-level security bypassed,
so only a composite key makes another bank's case or a non-member impossible to point at.
What the designed schema has differently is recorded in INPUT_DELTAS §8 and §18.
"""

from __future__ import annotations

import enum
from typing import Any

from django.db import models

from apps.shared.adapters.scanner import ScanState
from apps.shared.audit import AppendOnlyModel
from apps.shared.tenancy import TenantModel
from apps.taxonomy.models import CaseStatusCategory


def _choices(kind: type[enum.StrEnum]) -> list[tuple[str, str]]:
    return [(member.value, member.value) for member in kind]


class CaseLinkDecision(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): what a bank said about one suggested
    obligation link on its own case (WAT-04, ruling C). The change page branches on it —
    an accepted link is worked, a removed one is hidden — and no admin adds a third
    answer, because there is no third thing a bank can say about a link.
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


class ChangeCase(TenantModel):
    """One bank's case for one regulatory change (CAS-01).

    Created in the `new` category the moment the change is registered, with the change's
    suggested urgency and the footprint verdict computed then. `UNIQUE (tenant, change)` is
    what makes "exactly one case per bank per change" true, so a repeated registration
    finds the case instead of creating a second one.

    `so_what_text` starts as the library's AI draft and becomes this bank's own the moment
    someone saves over it; `so_what_confirmed` is what keeps AI output labelled until a
    person confirms it (WAT-05, AUD-02). The constraint below makes the confirmation name a
    person and a time, so "confirmed" can never be a flag nobody stands behind.

    The workflow columns are chunk 9's. `status` is the fixed category the guards read and
    `sub_status` a bank's own row inside it, which no guard reads (D-13). Three CHECKs hold
    what the state machine promises even against a bug in it: a dismissal names a reason,
    every category between triage and the close has an owner, and whoever signs off is
    not whoever asked (four eyes, CAS-06). `version` is what every case write's `If-Match`
    compares, so a concurrent edit is refused rather than merged (CAS-08). Whoever closed
    the case is on its last `CaseTransition` row, so there is no `closed_by`.
    """

    change = models.ForeignKey("watch.RegulatoryChange", on_delete=models.PROTECT, related_name="cases")
    status = models.CharField(
        max_length=16, choices=_choices(CaseStatusCategory), default=CaseStatusCategory.NEW.value
    )
    urgency = models.ForeignKey("taxonomy.Urgency", on_delete=models.PROTECT, related_name="+")
    # False until a person triages: the value above is the agent's suggestion, and the
    # screen says so (Alex's item 1; the designed schema has no such column, §8).
    urgency_confirmed = models.BooleanField(default=False)
    footprint_match = models.BooleanField()
    owner = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    so_what_text = models.TextField(blank=True)
    so_what_confirmed = models.BooleanField(default=False)
    so_what_confirmed_by = models.ForeignKey(
        "identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    so_what_confirmed_at = models.DateTimeField(null=True, blank=True)
    # The Monday of the ISO week the case first appeared in the briefing, in the bank's own
    # time zone. Null until a briefing has carried it (HOM-02, chunk 6).
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
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "change_case"
        # Newest first with the row id as a stable tiebreak, so `.first()` is the newest
        # case and never a coin flip between two created in the same transaction.
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
        # The four-eyes check constraint `change_case_four_eyes` (CAS-06, AC-CAS1) is created
        # by RunSQL in migration 0002 as `signed_off_by_id IS NULL OR (signoff_requested_by_id
        # IS NOT NULL AND signed_off_by_id <> signoff_requested_by_id)`: a sign-off answers a
        # request, and never the requester's own. Enumerated by apps/shared/tests_four_eyes.py.
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
    """What one bank decided about one suggested obligation link, on its own case
    (WAT-04, ruling C).

    A library editor confirms a link for the shared library; a compliance officer accepts
    or removes it here. The two are separate facts: this table holds no library row and
    writes none, so a bank saying "not related to us" changes nothing another bank sees.

    A removal is a `removed` row, not a deleted one, so the case file can say the bank
    looked at the link and said no (playbook 4.3). `UNIQUE (tenant, case, obligation)`
    means one decision per link, changed by rewriting that row rather than by stacking a
    second.
    """

    case = models.ForeignKey(ChangeCase, on_delete=models.CASCADE, related_name="obligation_links")
    obligation = models.ForeignKey("library.Obligation", on_delete=models.PROTECT, related_name="+")
    decision = models.CharField(max_length=16, choices=_choices(CaseLinkDecision))
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
    change, the bank's own deadline and the effort.

    One per case. There is no `contributors` column: the contributor teams are the case's
    team participants (D-20, INPUT_DELTAS §1), added and removed one at a time so two
    people editing them never replace each other's list. A saved assessment says why,
    which the CHECK holds at the database. `version` is the `If-Match` of its own writes,
    so the second of two people saving the same version gets `stale_write` (AC-CAS2).
    """

    case = models.OneToOneField(ChangeCase, on_delete=models.PROTECT, related_name="assessment")
    applies = models.CharField(
        max_length=16, choices=_choices(AssessmentApplies), default=AssessmentApplies.YES.value
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

    Removed, never deleted: `delete()` raises and removal sets `removed_at` and
    `removed_by`, so the case file still shows what was planned. `version` is the
    `If-Match` of its own writes. The ticket columns of the designed schema wait for
    `c13-tickets-export` (INPUT_DELTAS §1). The partial index serves every "what is open
    and when is it due" read without scanning done or removed actions.
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
    """One move of a case from one category to another (CAS-08), written in the same
    transaction as the move.

    Append-only in Python and by trigger, so the time a case spent in each stage cannot be
    rewritten afterwards. `by_user` names who moved it, which is why the case has no
    `closed_by`; it is empty only for a move no person made. `from_status` is empty on the
    first row of a case.
    """

    case = models.ForeignKey(ChangeCase, on_delete=models.PROTECT, related_name="+")
    from_status = models.CharField(max_length=16, choices=_choices(CaseStatusCategory), blank=True)
    to_status = models.CharField(max_length=16, choices=_choices(CaseStatusCategory))
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
    """One piece of evidence on a case: a file, a link or a reference to an internal
    document (CAS-05).

    Only a file has bytes, kept in the private bucket under `storage_key`, and a CHECK per
    kind makes a half-written row impossible: a file carries its key, hash, size and type;
    a link its url; neither a link nor a reference a storage key, so neither can ever be
    downloaded. A new row starts `pending` and a download serves only `clean`, so a file
    is invisible until the scan passes. Removed, never deleted: `delete()` raises and the
    row keeps its name and hash for the case file and the audit trail.
    """

    case = models.ForeignKey(ChangeCase, on_delete=models.PROTECT, related_name="evidence")
    kind = models.CharField(max_length=16, choices=_choices(EvidenceKind))
    name = models.TextField()
    storage_key = models.TextField(blank=True)
    url = models.TextField(blank=True)
    content_hash = models.CharField(max_length=128, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    mime_type = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    removed_at = models.DateTimeField(null=True, blank=True)
    scan_state = models.CharField(max_length=16, choices=_choices(ScanState), default=ScanState.PENDING.value)
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
