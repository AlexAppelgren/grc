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

R1 columns only. Triage, dismissal, the assessment, actions, evidence, sign-off and the
close are chunk 9 (`c9-case-models`), and the four-eyes check constraint arrives with
them, because what it guards is the sign-off (CAS-06). What the designed schema has
differently is recorded in INPUT_DELTAS §8.
"""

from __future__ import annotations

import enum

from django.db import models

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

    No `version` column in R1, so no write takes `If-Match` and none can answer
    `stale_write`: the case's own concurrency is CAS-08 and lands with the workflow in
    chunk 9.
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
        ]
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
