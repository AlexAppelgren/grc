"""The public list of upcoming dates (HOM-04).

`GET /upcoming` is the library's dated changes with nothing of any bank in them, which is
why an agent's key may read it. The calendar subscription answers the same question to the
other audience — one person, in one bank, through an address whose token is the only
credential a calendar client can send — and lives in `apps/home/feed.py`.

**Why two modules for one requirement.** This one reads library records and writes
nothing. That one writes a bank's own rows and reads no library record. Keeping them apart
is what `apps/shared/tests_library_fence.py` asks for: a module that names a library model
and also calls a write is exactly the shape a library write outside the fence takes, and
the guard cannot tell the two apart by reading one file (PRO-01). So the fence decides the
file boundary here, and the two halves meet only in `api.py`.

**`GET /upcoming` is a library read and nothing else.** No case, no footprint verdict, no
owner and no "So what?" — not filtered out at the end, but never joined in the first place,
so there is no arrangement of filters, scopes or sessions under which a bank's judgement
could leave through it. That is what makes an agent's key safe on this one route and on no
other in this app. Two banks calling it receive byte-identical answers, which a test pins.

**A bank's own agent reads it narrowed, and library-only still** (ACC-04, ACC-07). An
agent access credential gets the changes inside its bank's footprint and its entry's scope,
judged over the scope the watch feed judges a change by (`watch.reading`) with the same
database functions the inventory uses (`library.reading.in_reach()`). Nothing of the
bank is joined for it either: the narrowing only leaves rows out, so each row it gets is
the row everyone else gets.

Its window opens at the server's own calendar day rather than any bank's. The tenant-local
day is the right floor for the roadmap, where the reader is one bank; here it would make
the "public" list answer two things at once, and a newsletter agent belongs to no bank at
all.

"""

from __future__ import annotations

import datetime
from typing import cast

from django.utils import timezone

from apps.home.schemas import HomeUpcomingItem, HomeUpcomingQuery
from apps.library.reading import OPEN, Reader, in_reach, vocabulary_refs
from apps.taxonomy.models import ChangeTypeLabel
from apps.watch import reading as watch_reads
from apps.watch.reading import _scope_term_ids as change_scope_term_ids  # the feed's own rule, never a copy
from apps.watch.models import ChangeStatus, RegulatoryChange
from apps.watch.schemas import DatePrecision


def list_upcoming(order: list[str], page: HomeUpcomingQuery, reader: Reader = OPEN) -> list[HomeUpcomingItem]:
    """`GET /upcoming`: every change in the shared library still ahead of its date, earliest
    first (HOM-04, AGT-02).

    A withdrawn or superseded reform is not upcoming, whatever its date still says, and a
    change registered before anybody published a date is not upcoming either — so both are
    absent rather than listed with an empty date. A confined reader, a bank's own agent,
    reads only the changes inside its bank's footprint and its entry's scope.

    Four queries however long the page is: the page itself with its change type, that type's
    labels, and the urgency rows with theirs.
    """
    changes = RegulatoryChange.objects.filter(status=ChangeStatus.ACTIVE.value, key_date__gte=timezone.localdate())
    changes = changes.filter(*in_reach(reader, change_scope_term_ids()))
    rows = list(changes.select_related("change_type").order_by("key_date", "id")[page.offset : page.offset + page.limit])
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
