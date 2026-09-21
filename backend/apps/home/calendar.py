"""Upcoming public facts and the revocable calendar feed (HOM-04).

Two different things live here because they answer the same question to two audiences.
`GET /upcoming` is the library's dated changes with nothing of any bank in them, which is
why an agent's key may read it. The calendar feed is one person's subscription in one bank,
whose address carries the only credential a calendar client can send.

**`GET /upcoming` is a library read and nothing else.** No case, no footprint verdict, no
owner and no "So what?" — not filtered out at the end, but never joined in the first place,
so there is no arrangement of filters, scopes or sessions under which a bank's judgement
could leave through it. That is what makes an agent's key safe on this one route and on no
other in this app. Two banks calling it receive byte-identical answers, which a test pins.

Its window opens at the server's own calendar day rather than any bank's. The tenant-local
day is the right floor for the roadmap, where the reader is one bank; here it would make
the "public" list answer two things at once, and a newsletter agent belongs to no bank at
all.

**The calendar feed is not built here.** The route was declared with a token in the path
(`c6-home-api-contract`), and D-52 and ADR 0045 answered q-feed-token the other way: the
address is `GET /api/v1/calendar/feed.ics?token=<prefix>.<secret>`, a prefix and a SHA-256
rather than one hash, with a per-person cap, a recent sign-in or step-up on creation, an
idle expiry and automatic revocation, and `calendar_feed` as the fifth table of the
identity-lookup clause. The decision says in as many words that the path form is not built,
and neither the declared route nor the `calendar_feed` model on main is in the decided
shape. Building the path form would put on `main` the thing the ADR refuses, so the four
feed functions below stay as they are and the contract goes back for the decided shape
(chunk 6 plan rule 3: a logic task that finds the contract wrong stops and reports).
"""

from __future__ import annotations

import datetime
from typing import NoReturn, cast

from django.utils import timezone

from apps.home.logic import not_built
from apps.home.schemas import HomeUpcomingItem, HomeUpcomingQuery
from apps.library.reading import vocabulary_refs
from apps.taxonomy.models import ChangeTypeLabel
from apps.watch import reading as watch_reads
from apps.watch.models import ChangeStatus, RegulatoryChange
from apps.watch.schemas import DatePrecision


def list_upcoming(order: list[str], page: HomeUpcomingQuery) -> list[HomeUpcomingItem]:
    """`GET /upcoming`: every change in the shared library still ahead of its date, earliest
    first (HOM-04, AGT-02).

    A withdrawn or superseded reform is not upcoming, whatever its date still says, and a
    change registered before anybody published a date is not upcoming either — so both are
    absent rather than listed with an empty date.

    Four queries however long the page is: the page itself with its change type, that type's
    labels, and the urgency rows with theirs.
    """
    rows = list(
        RegulatoryChange.objects.select_related("change_type")
        .filter(
            status=ChangeStatus.ACTIVE.value,
            key_date__gte=timezone.localdate(),
        )
        .order_by("key_date", "id")[page.offset : page.offset + page.limit]
    )
    types = vocabulary_refs(ChangeTypeLabel, (row.change_type for row in rows), order)
    # Through the watch app's own rule, never `vocabulary_refs()`: an urgency row's `kind`
    # column is its pill tone, and a tone is nobody's to send (NFR-03).
    urgencies = watch_reads.urgency_refs(
        {row.suggested_urgency_id for row in rows if row.suggested_urgency_id is not None}, order
    )
    return [
        HomeUpcomingItem(
            change_id=row.id,
            title=row.title,
            # The filter above is on a key date at or after today, so every row that reaches
            # here has one; the column is nullable because a change may be registered before
            # its date is known.
            key_date=cast(datetime.date, row.key_date),
            key_date_precision=cast(DatePrecision, row.key_date_precision) or None,
            key_date_label=row.key_date_label or None,
            change_type=types[row.change_type_id],
            authority_label=row.authority_label,
            suggested_urgency=None if row.suggested_urgency_id is None else urgencies[row.suggested_urgency_id],
            source_url=row.source_url,
        )
        for row in rows
    ]


def list_feeds() -> NoReturn:
    """`GET /calendar-feeds`. Waits for the contract to carry D-52's shape."""
    not_built("Calendar subscriptions are not built yet.")


def create_feed() -> NoReturn:
    """`POST /calendar-feeds`. Waits for the contract to carry D-52's shape."""
    not_built("Calendar subscriptions are not built yet.")


def revoke_feed() -> NoReturn:
    """`DELETE /calendar-feeds/{feedId}`. Waits for the contract to carry D-52's shape."""
    not_built("Calendar subscriptions are not built yet.")


def calendar_ics() -> NoReturn:
    """`GET /calendar/{feedToken}`. The route as declared takes the token in the path, which
    D-52 and ADR 0045 refuse; it reads no token and touches no row while it answers 501, so
    nothing about a token can be learned from it."""
    not_built("The calendar feed is not built yet.")
