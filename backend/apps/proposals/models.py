"""Models of the proposals app (PRO-01, PRO-02, AC-PRO2; schema v0.3 `proposal`).

`Proposal` is the door into the library, not the library: it lives in the library zone
(no tenant column, visible to every tenant's proposer and to the console) but is a plain
model rather than a `LibraryModel`, because people and agents create proposals from
apps/proposals/logic.py while the fence reserves library writes for
apps/proposals/apply.py, which applies an approved payload inside `library_write()`.

`ProposalTenant` is the tenant half: a proposal a bank's own person or agent made is
linked to that bank in its own tenant table under forced row-level security, never by a
column on `proposal`.

`kind` and `status` are tier-one kinds (apps/shared/kinds.py). The payload's shape is
named per kind in apps/proposals/schemas.py and validated when the proposal is created.
The check constraint `proposal_four_eyes` (RunSQL in migration 0001, widened in migration
0003) is the database's word on "never the proposer": refused for a repeated user, a
repeated key or a repeated agent definition, and for a reviewing key that names no agent
(PRO-S13, PRO-S14, D-62, ADR 0054). `proposed_by_agent`, `reviewed_by_api_key` and
`reviewed_by_agent` are copied from the acting API key at the one write path (a check
constraint cannot dereference a key), because a platform key holding `proposals:review`
is a second, independent agent that may work the same queue a person does.
"""

from __future__ import annotations

import enum
import uuid

from django.db import models

from apps.shared.tenancy import TenantModel


def _choices(kind: type[enum.StrEnum]) -> list[tuple[str, str]]:
    return [(member.value, member.value) for member in kind]


class ProposalKind(enum.StrEnum):
    """What a proposal changes; apply() branches on it. Chunk 2: the vocabulary and term
    kinds. Chunk 4 adds `new_obligation_version`, a new summary in force from a date, with
    the scope terms it changes. R1 wave 2 adds `new_instrument` and `new_obligation`, which
    create a record rather than change one and so name no target (PRO-01, INV-01, INV-03).
    `update_obligation` and `retire_record` wait for a scenario that needs them, and a
    watch link is never a proposal (D-64). Wave 3 adds `new_provision` and
    `new_provision_version`, a law's verbatim text, never a standard's (INV-02, INV-08)."""

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
    kind = models.CharField(max_length=40, choices=_choices(ProposalKind))
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.UUIDField(null=True, blank=True)
    change_id = models.UUIDField(null=True, blank=True)
    title = models.CharField(max_length=500)
    payload = models.JSONField(default=dict, blank=True)  # schema: ProposalPayload
    field_sources = models.JSONField(default=dict, blank=True)  # schema: ProposalFieldSources
    source_label = models.CharField(max_length=500, blank=True)
    source_url = models.URLField(max_length=2000, blank=True)
    effective_from = models.DateField(null=True, blank=True)
    origin = models.CharField(max_length=16, choices=_choices(OriginType))
    agent_run_id = models.UUIDField(null=True, blank=True)
    model = models.CharField(max_length=200, blank=True)
    proposed_by_user = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    proposed_by_api_key = models.ForeignKey("identity.ApiKey", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    proposed_by_agent = models.ForeignKey("agents.Agent", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    idempotency_key = models.CharField(max_length=200, null=True, blank=True)
    proposed_in_tenant = models.BooleanField(default=False)
    status = models.CharField(max_length=16, choices=_choices(ProposalStatus), default=ProposalStatus.OPEN.value)
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
        ]
        # The four-eyes check constraint `proposal_four_eyes` is created by RunSQL in
        # migration 0001 as `reviewed_by_id IS NULL OR proposed_by_user_id IS NULL OR
        # reviewed_by_id <> proposed_by_user_id`, and widened by RunSQL in migration 0003
        # with the same clause for the reviewing key and for the reviewing agent, plus a
        # clause refusing a reviewing key that names no agent (`reviewed_by_api_key_id IS
        # NULL OR reviewed_by_agent_id IS NOT NULL`): without it two unbound platform keys
        # would both carry a NULL agent, and NULL <> NULL is unknown in SQL, so the
        # agent comparison would pass on a missing value rather than on independence.
        # Django cannot spell `<>`, and the four-eyes guard reads the definition back from
        # pg_constraint.

    def __str__(self) -> str:
        return f"{self.kind} {self.id}"


class ProposalTenant(TenantModel):
    """Which tenant a proposal was made in (PRO-03). A tenant table of its own, under
    forced row-level security, so a tenant sees the library proposals its own people made
    without the library-zone `proposal` row ever carrying a tenant id: the console reads
    `proposed_in_tenant` and withholds the proposer's identity without learning which bank
    they work for."""

    proposal = models.ForeignKey(Proposal, on_delete=models.PROTECT, related_name="tenant_links")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "proposal_tenant"
        ordering = ["created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["proposal", "tenant"], name="proposal_tenant_unique")]

    def __str__(self) -> str:
        return f"{self.tenant_id}:{self.proposal_id}"
