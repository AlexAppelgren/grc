"""Models of the governance app (AUD-02, ACC-08; INPUT_DELTAS §6).

`AiGeneration` logs every model call, written by `ai_log.log_generation()` alone. A mixed
table (playbook 14): a row with no tenant is the library's (the shared "So what?"), a row
with a tenant is that bank's. Every bank reads the library's rows except `agent_review`
(D-80); writing is the session's own zone only, so no bank can move the platform's row
(H15). Both rules are the database's. Rows ship as `draft`; a bank confirms its copy of a
"So what?" on `change_case`. No prompt is stored, only its hash and template (NFR-04, D-07).

Tenant reach (governance 0004, D-72, ADR 0057): `TenantReachRequest` (four eyes by check
constraint) and `TenantReach`, the bank's one state row, off until approved.

`AgentAccessCall` (governance 0005): one append-only row per agent access request, written
by `access_log.py` alone.
"""

from __future__ import annotations

import enum
import uuid

from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.shared.audit import AppendOnlyModel
from apps.shared.tenancy import TenantModel
from apps.taxonomy.models import ApprovalStatus
from apps.shared.kinds import choices


class AiPurpose(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): what a model call was for (AUD-02). A new
    purpose is a new feature, never an admin's row.

    `agent_review` is a confirming agent's decision on another agent's work, reported with the
    decision (`AgentDecision`, D-80). Its row is marked `model_metadata_reported_by_agent` and
    names the run and the record (check constraint), and only the platform reads it. A
    machine's approval is never logged as a drafting purpose, so the log can tell a draft
    from a decision.

    `what_applies` is the summary drafted above what applies to a bank's own agent (ACC-06),
    counted against that bank's monthly cap."""

    SO_WHAT = "so_what"
    CHANGE_SUMMARY = "change_summary"
    SCOPE_SUGGESTION = "scope_suggestion"
    LINK_SUGGESTION = "link_suggestion"
    TRANSLATION = "translation"
    ANSWER = "answer"
    AGENT_REVIEW = "agent_review"
    WHAT_APPLIES = "what_applies"


class AiStatus(enum.StrEnum):
    """Tier-one kind: how far a person has got with what the model wrote (AUD-02). Every row
    ships as `draft`, which keeps AI output labelled until someone confirms it.
    """

    DRAFT = "draft"
    CONFIRMED = "confirmed"
    EDITED = "edited"
    REJECTED = "rejected"


class AiGeneration(models.Model):
    """One model call and what it produced (AUD-02).

    The tenant column is nullable on purpose: the table holds the library's drafts and each
    bank's own answers, and this app's migration policies keep them apart. The row names the
    model, the prompt template and hash (never the prompt), the subject by id, and the
    `citations` the output rests on; `output` is kept so a confirmation confirms something.
    Model metadata is observed for a call bleqq made and reported by the agent for one an
    agent filed (D-66).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("shared.Tenant", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    agent_run = models.ForeignKey(
        "agents.AgentRun", null=True, blank=True, on_delete=models.PROTECT, related_name="generations"
    )
    # Who asked, for `purpose = answer`. Null for everything a run produced by itself.
    asker = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    purpose = models.CharField(max_length=32, choices=choices(AiPurpose))
    # The record the call was about, never its text: the input reference AUD-02 asks for.
    subject_type = models.CharField(max_length=32, blank=True)
    subject_id = models.UUIDField(null=True, blank=True)
    model = models.CharField(max_length=200)
    model_version = models.CharField(max_length=120, blank=True)
    # True when an agent filed the two fields above as its account of itself (D-66). Stored,
    # not derived from the purpose, because it is the trust boundary itself.
    model_metadata_reported_by_agent = models.BooleanField(default=False)
    prompt_template = models.CharField(max_length=200, blank=True)
    prompt_hash = models.CharField(max_length=128, blank=True)
    output = models.TextField(blank=True)
    citations = models.JSONField(default=list, blank=True)  # schema: AiCitation
    status = models.CharField(max_length=16, choices=choices(AiStatus), default=AiStatus.DRAFT.value)
    reviewed_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    # How a call bleqq made ended (AUD-02, D-82): the provider's stop reason, `aborted` or
    # `failed`. Nothing branches on it; empty on a row an agent filed (D-66).
    stop_reason = models.CharField(max_length=64, blank=True)
    # Integer minor units, the one money shape the playbook allows (billing reads it).
    cost_minor = models.PositiveIntegerField(default=0)
    # A reader's verdict on an Ask answer (`rateAnswer`) and its note.
    feedback = models.CharField(max_length=16, blank=True)
    feedback_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_generation"
        # Newest first with the row id as a stable tiebreak.
        ordering = ["-created_at", "id"]
        indexes = [
            models.Index(fields=["subject_type", "subject_id"], name="ai_generation_subject_idx"),
            models.Index(fields=["tenant", "-created_at"], name="ai_generation_tenant_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                # A review names a person and a time or neither, so "reviewed" can never be
                # a state nobody stands behind (the same rule `change_case` carries).
                condition=(
                    models.Q(reviewed_by__isnull=True, reviewed_at__isnull=True)
                    | models.Q(reviewed_by__isnull=False, reviewed_at__isnull=False)
                ),
                name="ai_generation_review_names_a_person",
            ),
            models.CheckConstraint(
                # A confirming agent's decision is its own report, made in a run and about a
                # record, so no consumer can log one that nobody can trace (D-80).
                condition=~models.Q(purpose=AiPurpose.AGENT_REVIEW.value)
                | (
                    models.Q(model_metadata_reported_by_agent=True, agent_run__isnull=False, subject_id__isnull=False)
                    & ~models.Q(subject_type="")
                ),
                name="ai_generation_agent_review_names_its_run",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.purpose}:{self.model}"


class TenantReachRequest(TenantModel):
    """A request to let the bank's register reach its own agents (ACC-08, D-72), decided by a
    second `security.manage` holder; never withdrawn; one pending per bank. The four-eyes
    constraint is created by RunSQL in governance 0004 in the words
    apps/shared/tests_four_eyes.py reads back."""

    requested_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    requested_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=16, choices=choices(ApprovalStatus), default=ApprovalStatus.PENDING.value)
    decided_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "tenant_reach_request"
        ordering = ["-requested_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"],
                condition=models.Q(status=ApprovalStatus.PENDING.value),
                name="tenant_reach_request_one_pending",
            ),
            models.CheckConstraint(
                condition=models.Q(decided_by__isnull=True, decided_at__isnull=True)
                | models.Q(decided_by__isnull=False, decided_at__isnull=False),
                name="tenant_reach_request_decision_names_a_person",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.status} {self.id}"


class TenantReach(TenantModel):
    """The bank's one row of tenant reach state (ACC-08): off until a request is approved,
    and no row reads as off. `request` is the approval that last switched it on; `changed_by`
    and `changed_at` name the last person to switch it either way."""

    enabled = models.BooleanField(default=False)
    request = models.ForeignKey(TenantReachRequest, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    changed_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    changed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "tenant_reach"
        ordering = ["tenant"]
        constraints = [models.UniqueConstraint(fields=["tenant"], name="tenant_reach_one_row")]

    def __str__(self) -> str:
        return f"{self.tenant_id}:{self.enabled}"


class AgentAccessCall(AppendOnlyModel, TenantModel):
    """One request an agent access credential made (ACC-08): credential, entry, acting person,
    tool, filter names with key values only, record count, scopes, duration and status.

    Never the content (playbook 4.7). Written once per request by `access_log.finish`;
    append-only in Python and by trigger. A tenant ledger row: only the D-53 purge removes
    it, whole. `agent_access` and `acting_user` are composite `(tenant_id, …)` keys."""

    api_key = models.ForeignKey("identity.ApiKey", on_delete=models.PROTECT, related_name="+")
    agent_access = models.ForeignKey("agents.AgentAccess", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    acting_user = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    tool = models.CharField(max_length=120)
    filters = models.JSONField(default=dict, blank=True)  # schema: AgentAccessCallFilters
    record_count = models.PositiveIntegerField(null=True, blank=True)
    scopes = ArrayField(models.CharField(max_length=32), default=list, blank=True)
    scope_narrowed = models.BooleanField(default=False)
    scope_terms = models.JSONField(default=dict, blank=True)  # schema: AgentAccessCallFilters
    duration_ms = models.PositiveIntegerField()
    status = models.PositiveSmallIntegerField()
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agent_access_call"
        ordering = ["-at", "-id"]
        indexes = [models.Index(fields=["tenant", "agent_access", "-at"], name="agent_access_call_entry_idx")]

    def __str__(self) -> str:
        return f"{self.tool}:{self.status}"
