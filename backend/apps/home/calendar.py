"""The public list of upcoming dates (HOM-04): `GET /upcoming`.

The library's dated changes with nothing of any bank joined in (no case, verdict, owner or
"So what?"), which is why an agent's key may read it; two banks get byte-identical answers.
A bank's own agent reads it narrowed to its footprint and entry scope (ACC-04, ACC-07, via
`watch.reading` and `library.reading.in_reach()`), which only leaves rows out.

The calendar subscription lives in `feed.py`: it writes a bank's rows and reads no library
record, and a module doing both is the shape `tests_library_fence.py` refuses (PRO-01).
The window opens at the server's calendar day, since a public list belongs to no bank.
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
    """`GET /upcoming`: every library change still ahead of its date, earliest first (HOM-04,
    AGT-02). Withdrawn, superseded and undated changes are absent. A confined reader (a
    bank's own agent) reads only its footprint and entry scope. Four queries per page.
    """
    changes = RegulatoryChange.objects.filter(status=ChangeStatus.ACTIVE.value, key_date__gte=timezone.localdate())
    changes = changes.filter(*in_reach(reader, change_scope_term_ids()))
    rows = list(changes.select_related("change_type").order_by("key_date", "id")[page.offset : page.offset + page.limit])
    types = vocabulary_refs(ChangeTypeLabel, (row.change_type for row in rows), order)
    # Through the watch app's own rule, never `vocabulary_refs()`: an urgency row's `kind` is
    # its pill tone, and a tone is nobody's to send (NFR-03).
    urgencies = watch_reads.urgency_refs(
        {row.suggested_urgency_id for row in rows if row.suggested_urgency_id is not None}, order
    )
    return [
        HomeUpcomingItem(
            change_id=row.id,
            title=row.title,
            # The filter guarantees a key date; the column is nullable for undated changes.
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
