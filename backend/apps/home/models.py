"""Models of the home app (HOM-02, HOM-04; INPUT_DELTAS §1, §9): three tenant tables under
forced row-level security, all one bank's own (playbook 14).

- A sent briefing is never rewritten: `briefing_item` is append-only by trigger.
  `briefing.email_sent_at` is the one thing stamped later.
- A calendar credential is stored hashed: only a lookup prefix and the secret's SHA-256,
  as for an API key (ID-10, D-52, ADR 0045).

The roadmap has no table; it is computed on every read.
"""

from __future__ import annotations

from django.db import models

from apps.shared.audit import AppendOnlyModel
from apps.shared.tenancy import TenantModel

# The lookup half of a calendar address, in hex; longer than an API key's because every
# member may hold several. The secret beside it is what the fetch verifies (D-52).
TOKEN_PREFIX_LENGTH = 16


class Briefing(TenantModel):
    """One week of regulation as it was sent to one bank (HOM-02).

    Written only by the weekly job; `UNIQUE (tenant, week_start)` makes a re-run a no-op.
    `week_start` is the Monday of the ISO week in the bank's time zone, a plain date.
    `email_sent_at` null means not sent yet, never "the briefing was empty".
    """

    week_start = models.DateField()
    generated_at = models.DateTimeField(auto_now_add=True)
    email_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "briefing"
        # Newest week first (playbook 4.5).
        ordering = ["-week_start"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "week_start"], name="briefing_one_per_week"),
        ]

    def __str__(self) -> str:
        return f"{self.tenant_id}:{self.week_start}"


class BriefingItem(AppendOnlyModel, TenantModel):
    """One case a briefing named, in its order (HOM-02). Append-only in Python and by
    trigger, so a sent briefing can be read forever and rewritten by nobody. `rank` 1 is the
    lead; a case appears once per week.
    """

    # No reverse accessor: items are read with `filter(briefing=...)`, and django-stubs cannot
    # resolve a reverse manager through two abstract bases.
    briefing = models.ForeignKey(Briefing, on_delete=models.CASCADE, related_name="+")
    case = models.ForeignKey("cases.ChangeCase", on_delete=models.PROTECT, related_name="+")
    rank = models.PositiveIntegerField()

    class Meta:
        db_table = "briefing_item"
        # The lead first, then briefing order, with the row id as a stable tiebreak.
        ordering = ["rank", "id"]
        constraints = [
            models.UniqueConstraint(fields=["briefing", "case"], name="briefing_item_one_per_case"),
        ]

    def __str__(self) -> str:
        return f"{self.briefing_id}:{self.rank}"


class CalendarFeed(TenantModel):
    """One person's calendar subscription to their bank's roadmap (HOM-04, D-52, ADR 0045).

    The address is `…/calendar/feed.ics?token=<prefix>.<secret>`; only the prefix and the
    secret's SHA-256 are kept, so the system can neither hand it back nor leak it. The lookup
    runs before any tenant is known, so this is a table of the identity-lookup clause
    (`apps/shared/tenancy.py`) and the prefix is unique across banks. Revocation stamps
    `revoked_at`, so a revoked and an unknown token can be answered alike. No filter column:
    a bank's own deadlines never reach a calendar (AC-TEN1).
    """

    user = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    # Unique across banks: the fetch looks it up before it knows the bank.
    token_prefix = models.CharField(max_length=TOKEN_PREFIX_LENGTH, unique=True)
    # SHA-256 of the secret half, compared in constant time. No plaintext column exists.
    token_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    # Last fetch, throttled as an API key's stamp; null until the first. The idle expiry reads it.
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "calendar_feed"
        # Newest first, so a new subscription lists at the top.
        ordering = ["-created_at", "id"]
        # Serves the person's list, the per-person cap count and a leaver's revocation.
        indexes = [models.Index(fields=["tenant", "user"], name="calendar_feed_owner_idx")]

    def __str__(self) -> str:
        # The row's own id and nothing else. A prefix is half an address and a hash is a
        # credential's shadow, and a model's repr reaches logs, shells and error pages
        # (playbook 4.7).
        return str(self.id)
