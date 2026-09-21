"""Models of the governance app (AUD-02; schema v0.3 `ai_generation`; INPUT_DELTAS §6).

One table: the log of what a model produced. Every model call in the product leaves a row
here, written by `apps/governance/ai_log.py:log_generation()` and by nothing else, so the
question "what did a machine write, from which model, on which facts, and has anybody
stood behind it yet" has one place to be asked.

A mixed table (playbook 14): a row with no tenant is the library's — the "So what?" drafted
once per change and shared by every bank — and a row with a tenant is that bank's own, an
Ask answer among them. Reading is mixed so every bank sees the library's rows; writing is
the session's own zone alone, which is what keeps one bank from moving, rewriting or
deleting the platform's row (ruling I, HARDENING H15). The write rule is the database's,
not only the code's.

The review state is the designed `ai_status` kind, so a row ships as `draft` and a person
standing behind it is what moves it. Chunk 5 never moves it: a bank confirms its own copy
of a "So what?" on `change_case`, because the library's row has no tenant, two banks
confirming would overwrite one shared row, and the write policy refuses it anyway. Moving
the library row's state is a platform act and chunk 7 builds it.

Nothing here holds a prompt: `prompt_hash` and `prompt_template` are what is stored, so a
bank's own words can never be read back out of this log even by the platform (NFR-04,
D-07).
"""

from __future__ import annotations

import enum
import uuid

from django.db import models


def _choices(kind: type[enum.StrEnum]) -> list[tuple[str, str]]:
    return [(member.value, member.value) for member in kind]


class AiPurpose(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): what a model call was for (AUD-02). The
    console and the log's own filter branch on it, and an admin never adds one, because a
    new purpose is a new feature."""

    SO_WHAT = "so_what"
    CHANGE_SUMMARY = "change_summary"
    SCOPE_SUGGESTION = "scope_suggestion"
    LINK_SUGGESTION = "link_suggestion"
    TRANSLATION = "translation"
    ANSWER = "answer"


class AiStatus(enum.StrEnum):
    """Tier-one kind: how far a person has got with what the model wrote (AUD-02).

    `draft` is what every row ships as — the brief's "pending" is this value — and it is
    what keeps AI output labelled until somebody confirms it. `confirmed`, `edited` and
    `rejected` are the three things a person can do about it afterwards.
    """

    DRAFT = "draft"
    CONFIRMED = "confirmed"
    EDITED = "edited"
    REJECTED = "rejected"


class AiGeneration(models.Model):
    """One model call and what it produced (AUD-02, schema v0.3 `ai_generation`).

    Not a `TenantModel` and not a `LibraryModel`: the tenant column is nullable on purpose,
    because the same table holds the library's drafts and each bank's own answers, and the
    policies in this app's migration are what keep the two apart.

    What the row carries about the call itself is deliberately narrow. `model` and
    `model_version` say which machine wrote it; `prompt_template` and `prompt_hash` say
    which prompt did, without keeping the prompt; `subject_type` and `subject_id` name the
    record the call was about rather than repeating its text. `citations` is what the
    output rests on, so a reader can check it. `output` is kept because AUD-02 asks for it
    and because a confirmation has to be a confirmation of something.

    Where the metadata comes from is not the same everywhere, and the API says so: an Ask
    answer's model and version are observed by the wrapper that made the call, while a
    "So what?" filed by an agent with the change it read is **reported by that agent**
    (D-66). In R1 every agent is bleqq's own, so that is a reporting boundary; it becomes a
    trust boundary the day a bank runs its own agent against the route, which is R2's
    agent-access work.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("shared.Tenant", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    agent_run = models.ForeignKey(
        "agents.AgentRun", null=True, blank=True, on_delete=models.PROTECT, related_name="generations"
    )
    # Who asked, for `purpose = answer`. Null for everything a run produced by itself.
    asker = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    purpose = models.CharField(max_length=32, choices=_choices(AiPurpose))
    # The record the call was about, never its text: the input reference AUD-02 asks for.
    subject_type = models.CharField(max_length=32, blank=True)
    subject_id = models.UUIDField(null=True, blank=True)
    model = models.CharField(max_length=200)
    model_version = models.CharField(max_length=120, blank=True)
    # Who says so. False when bleqq's own wrapper made the call and read the two fields
    # above off the provider's response; true when an agent filed them with the record it
    # had read and this is its account of itself (D-66). Stored rather than derived from
    # the purpose, because it is the boundary itself and a later purpose must not inherit
    # somebody else's answer.
    model_metadata_reported_by_agent = models.BooleanField(default=False)
    prompt_template = models.CharField(max_length=200, blank=True)
    prompt_hash = models.CharField(max_length=128, blank=True)
    output = models.TextField(blank=True)
    citations = models.JSONField(default=list, blank=True)  # schema: AiCitation
    status = models.CharField(max_length=16, choices=_choices(AiStatus), default=AiStatus.DRAFT.value)
    reviewed_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    # Integer minor units, the one money shape the playbook allows (billing reads it).
    cost_minor = models.PositiveIntegerField(default=0)
    # Filled by chunk 7's Ask feedback; built now so chunk 7 adds no migration.
    feedback = models.CharField(max_length=16, blank=True)
    feedback_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_generation"
        # Newest first with the row id as a stable tiebreak, so `.first()` is the newest
        # generation and never a coin flip between two written in one transaction.
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
        ]

    def __str__(self) -> str:
        return f"{self.purpose}:{self.model}"
