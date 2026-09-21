"""Watch-zone rows for `seed_e2e` (c6-e2e-seed, WAT-06, H15): sources, their coverage
checks and regulatory changes, idempotent by natural key and built from the prototype's own
data, exactly as `apps/watch/testing.py` builds them for the backend suite.

Why this exists rather than `apps/shared/e2e_seed.py` writing these rows itself: `source`
and `regulatory_change` are library tables, and the library fence (`apps/shared/
tests_library_fence.py`) restricts a write of one to the watch pipeline's own steps —
registration, curation, the source registry, the So what draft — through `watch_write()`.
This module is the seed's own step, through `write.upsert()` (`apps/watch/write.py`'s
generic natural-key upsert, added for exactly this): `watch_write()` itself says in its own
docstring that the door exists for `c5-seed-watch` and `seed_e2e` to use it (neither had,
until this task).

Idempotent by the natural keys the rest of the seed already uses: a source by its `name`, a
change by its `stable_key`. `seed_e2e` may run twice against one database (a developer's
own, never a deployed one, `refuse_when_deployed()`), and a second run must find the same
rows rather than doubling them. A source's coverage check is the one exception with no
natural key of its own: this module keeps one check per source (`kind=SWEEP`), updated to
`timezone.now()` on every run, because "the last check happened just now" is the fact a
reseed should keep true and a fixed timestamp would go stale the day after it was written.
"""

from __future__ import annotations

import datetime

from django.utils import timezone

from apps.library.models import Authority, DatePrecision
from apps.proposals.models import OriginType
from apps.taxonomy.models import ChangeType, SourceKind, Urgency
from apps.watch import write
from apps.watch.models import CheckFrequency, CheckStatus, RegulatoryChange, Source, SourceCheck, SourceCheckKind


def seed_source(*, name: str, active: bool = True) -> Source:
    """A registered source, shared by every bank (WAT-06): written with no tenant
    activated, which is the only session the `source` write rule accepts one from."""
    return write.upsert(
        Source,
        "seed_e2e",
        lookup={"name": name},
        defaults={
            "url": "https://www.fi.se/",
            "kind": SourceKind.objects.get(key="authority_site"),
            "authority": Authority.objects.get(key="fi"),
            "check_frequency": CheckFrequency.WEEKLY.value,
            "active": active,
        },
    )


def seed_source_check(source: Source, *, status: CheckStatus, error: str = "") -> SourceCheck:
    """The one coverage-log line this seed keeps for a source, refreshed to "now" on every
    run so a healthy source never reads stale and a failed one always reads recent."""
    return write.upsert(
        SourceCheck,
        "seed_e2e",
        lookup={"source": source, "kind": SourceCheckKind.SWEEP.value},
        defaults={
            "checked_at": timezone.now(),
            "status": status.value,
            "items_found": 0 if status is CheckStatus.FAILED else 1,
            "error": error,
        },
    )


def seed_change(
    *,
    stable_key: str,
    title: str,
    key_date: datetime.date,
    key_date_label: str,
    urgency: str,
    first_seen_at: datetime.datetime,
    so_what_draft: str = "Confirm the affected process before the date falls due.",
    change_type: str = "adopted",
) -> RegulatoryChange:
    """One reform, merged on `stableKey` exactly as a sweep's retry would merge it
    (AC-WAT1): a second run updates the seed's own row rather than writing a duplicate."""
    return write.upsert(
        RegulatoryChange,
        "seed_e2e",
        lookup={"stable_key": stable_key},
        defaults={
            "title": title,
            "change_type": ChangeType.objects.get(key=change_type),
            "authority": Authority.objects.get(key="fi"),
            "authority_label": "Finansinspektionen",
            "published_on": key_date,
            "published_precision": DatePrecision.DAY.value,
            "summary": "FI's board decided to amend rules in the securities area.",
            "so_what_draft": so_what_draft,
            "suggested_urgency": Urgency.objects.get(key=urgency),
            "key_date": key_date,
            "key_date_precision": DatePrecision.DAY.value,
            "key_date_label": key_date_label,
            "source_label": "Finansinspektionen",
            "source_url": "https://www.fi.se/",
            "status": "active",
            "origin": OriginType.AGENT.value,
            "model": "agent pipeline 0.4",
            "first_seen_at": first_seen_at,
        },
    )
