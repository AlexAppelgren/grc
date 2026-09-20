"""Models of the home app (HOM-02, HOM-04; schema v0.3 `briefing`, `briefing_item`,
`calendar_feed`; INPUT_DELTAS §1, §9).

Three tenant tables, all three `TenantModel` under enabled and forced row-level security:
what one bank was told about a week, which cases that telling named, and the calendar
addresses that bank's people subscribed with. Everything here is one bank's own — a week
that holds nothing for one bank holds three reforms for another, because the footprint and
the cases behind it are its own — so none of it belongs in the library zone (playbook 14).

Two rules are structural here rather than remembered:

- **A sent briefing is never rewritten.** `briefing_item` is an `AppendOnlyModel` with the
  trigger of the same name, so a later change to the feed cannot alter what a person was
  told last Monday. The briefing row itself is not a ledger: `email_sent_at` is stamped
  when the mail goes out, which is the one thing about a snapshot that is not known when
  the snapshot is taken.
- **A credential is stored hashed.** `calendar_feed` has no column for the plaintext token
  and no `__str__` that could print one: the address is returned once by
  `POST /calendar-feeds` and only its SHA-256 hash is kept, exactly as an API key is
  (ID-10). The unique index on the hash is what makes a lookup a single indexed read
  rather than a scan.

Nothing here is a roadmap table. The roadmap is computed from the library's dated changes
and this bank's own cases every time it is asked for, so there is nothing to keep in step.
"""

from __future__ import annotations

import enum

from django.db import models

from apps.shared.audit import AppendOnlyModel
from apps.shared.tenancy import TenantModel


def _choices(kind: type[enum.StrEnum]) -> list[tuple[str, str]]:
    return [(member.value, member.value) for member in kind]


class FeedFilter(enum.StrEnum):
    """Tier-one kind (apps/shared/kinds.py): which kinds of dated item a surface includes.

    A calendar subscription's scope and the roadmap's `kind` filter are the same
    three-valued choice, and the code branches on it — the ICS builder skips what the
    filter excludes — so it is a kind and not a list an admin curates. `INTERNAL` produces
    an empty calendar in R1, because the branches that make the bank's own deadlines arrive
    with the register (chunk 8) and the case workflow (chunk 9).

    The API side of the same kind is the `FeedFilter` literal in `apps/home/schemas.py`;
    the two are kept apart because a model may not import a schema (playbook 4.1).
    """

    ALL = "all"
    REGULATORY = "regulatory"
    INTERNAL = "internal"


class Briefing(TenantModel):
    """One week of regulation as it was sent to one bank (HOM-02).

    A row exists only once the weekly job has run: `GET /briefings/current` computes the
    running week live and stores nothing, so a snapshot is always a week somebody was
    actually told about. `UNIQUE (tenant, week_start)` is what makes re-running the job for
    a week that already has one send nothing and write nothing.

    `week_start` is the Monday of the ISO week in the bank's own time zone, which is why it
    is a plain date and not a timestamp: the week a bank reads is the week its own calendar
    shows. `email_sent_at` stays null when the mail has not gone out, and a reader must not
    take null as "the briefing was empty".
    """

    week_start = models.DateField()
    generated_at = models.DateTimeField(auto_now_add=True)
    email_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "briefing"
        # Newest week first, so `.first()` is the most recent briefing and never a coin flip
        # between two weeks written in one transaction (playbook 4.5).
        ordering = ["-week_start"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "week_start"], name="briefing_one_per_week"),
        ]

    def __str__(self) -> str:
        return f"{self.tenant_id}:{self.week_start}"


class BriefingItem(AppendOnlyModel, TenantModel):
    """One case a briefing named, in the order the briefing named it (HOM-02).

    Append-only in Python and by trigger, which is what makes "a later change to the feed
    does not alter a sent briefing" true rather than remembered: the row that says this case
    led that week can be read forever and rewritten by nobody. The case it points at goes on
    moving; the fact that the week's mail led with it does not.

    `rank` 1 is the lead story. `UNIQUE (briefing, case)` means a case appears once in a
    week: the briefing already carries the tenant, so the pair is enough to say it.
    """

    # No reverse accessor: a week's items are read as `BriefingItem.objects.filter(
    # briefing=...)`, which is how the rest of this codebase reads a child list anyway.
    # django-stubs cannot resolve a reverse manager on a model that reaches its manager
    # through two abstract bases, and a type-ignore for a convenience nobody needs would
    # be the wrong trade.
    briefing = models.ForeignKey(Briefing, on_delete=models.CASCADE, related_name="+")
    case = models.ForeignKey("cases.ChangeCase", on_delete=models.PROTECT, related_name="+")
    rank = models.PositiveIntegerField()

    class Meta:
        db_table = "briefing_item"
        # The lead first, then the rest as the briefing ordered them, with the row id as a
        # stable tiebreak so two items written in one transaction never swap.
        ordering = ["rank", "id"]
        constraints = [
            models.UniqueConstraint(fields=["briefing", "case"], name="briefing_item_one_per_case"),
        ]

    def __str__(self) -> str:
        return f"{self.briefing_id}:{self.rank}"


class CalendarFeed(TenantModel):
    """One person's calendar subscription to their bank's roadmap (HOM-04).

    The address a calendar client polls carries 32 random bytes; only their SHA-256 hash is
    here, under a unique index, so the address is a credential the system cannot hand back
    and cannot leak. Losing it means revoking the subscription and creating another.

    Revocation stamps `revoked_at` rather than deleting the row, so a bank can still see
    that a subscription existed and when it stopped, and so a revoked token and one that
    never existed can be answered identically. Nothing else about the row ever changes.
    """

    user = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    # The SHA-256 of the token in the address, hex, 64 characters. No plaintext column
    # exists, here or anywhere: the address is returned once and never again.
    token_hash = models.CharField(max_length=64, unique=True)
    filter = models.CharField(max_length=16, choices=_choices(FeedFilter), default=FeedFilter.ALL.value)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "calendar_feed"
        # Newest first with the row id as a stable tiebreak, so the account screen lists the
        # subscription a person just made at the top.
        ordering = ["-created_at", "id"]
        indexes = [models.Index(fields=["tenant", "user"], name="calendar_feed_owner_idx")]

    def __str__(self) -> str:
        # The row's own id and nothing else. A hash is still a credential's shadow, and a
        # model's repr reaches logs, shells and error pages (playbook 4.7).
        return str(self.id)
