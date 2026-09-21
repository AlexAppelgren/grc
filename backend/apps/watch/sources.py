"""The source registry and the coverage log (WAT-01, AGT-01, ADM-02, AUD-01).

The registry is the list of places bleqq's agents check, and the coverage log is the answer
to "how do you know you missed nothing": every check ever made, with its time, its result,
the run behind it and, where it failed, why.

Two principals and two different judgements, which is why the gates here are not the ones
the change routes carry:

- **A library editor** (`sources.manage`, a platform permission no bank's role holds) adds
  a source, moves its address or cadence and switches automated checks off. No API key
  scope registers a source: an agent reports on the registry and never edits it.
- **An agent's key** (`sources:write`) logs one line of the coverage log against a run it
  has open. It names the source by the name it read at run start, and a name the registry
  does not hold is refused rather than invented.

Both are library rows and both go through `watch_write()` (apps/watch/write.py), which
reaches the seven watch tables and no inventory table, with `record()` in the same
transaction so no line of the log exists without its audit row (AUD-01).

**Staleness is computed, never stored.** A source is stale when the last
`SOURCE_STALE_AFTER_CHECKS` sweeps of it all failed, or when longer than its own cadence
plus `SOURCE_STALE_GRACE_HOURS` has passed since the last sweep that succeeded. Both are
settings with an env override; neither number appears in this module. Two things
deliberately do not make a source stale: a source whose automated checks are switched off,
because it is meant not to be checked, and a source nobody has ever checked, because the
log holds nothing to measure — that one reads `never`, which the console shows in its own
right.

**Only sweeps count.** A re-check looks again at one library record the source already
gave us (AGT-01, item 3); it says nothing about whether the source has been read since, so
a run full of re-checks must never make a source look fresh.

This module writes, so it names no library record: `apps/watch/keys.py` resolves what a
caller named and renders what a call answers, which is the split the library fence's AST
guard demands (apps/shared/tests_library_fence.py).
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any, cast

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.agents import runs
from apps.shared.audit import Actor, record
from apps.shared.authentication import Principal
from apps.watch import keys
from apps.watch.models import CheckFrequency, CheckStatus, SourceCheckKind
from apps.watch.schemas import (
    WatchSourceCheckInput,
    WatchSourceCoverage,
    WatchSourceInput,
    WatchSourceOut,
    WatchSourcePatch,
)
from apps.watch.write import watch_write

SUBJECT_TYPE = "source"
CHECK_SUBJECT_TYPE = "source_check"

REGISTERED = "source.registered"
UPDATED = "source.updated"
CHECK_LOGGED = "source_check.logged"

# What each cadence word means as a span. Not a threshold anyone tunes: it is what "weekly"
# means, keyed on the immutable kind the way a statutory mapping is (playbook 4.5). The
# grace on top of it is the setting.
CADENCE: dict[str, datetime.timedelta] = {
    CheckFrequency.DAILY.value: datetime.timedelta(days=1),
    CheckFrequency.WEEKLY.value: datetime.timedelta(days=7),
    CheckFrequency.MONTHLY.value: datetime.timedelta(days=30),
}

# What `lastStatus` says when the coverage log holds no sweep of a source at all. It is not
# a `check_status`: no check ended this way, because none was made.
NEVER = "never"


# ---------------------------------------------------------------------------------------
# GET /sources and GET /sources/coverage
# ---------------------------------------------------------------------------------------
def list_sources(order: list[str]) -> list[WatchSourceOut]:
    """The whole registry, by name. A read: it changes nothing and writes no audit row."""
    return keys.sources_out(order)


def source_coverage(order: list[str]) -> list[WatchSourceCoverage]:
    """Every source with the last line of its coverage log and whether it has gone stale.

    The log is read in one pass whatever the number of sources or checks (`keys.coverage_rows`),
    and the stale rule is applied here, in Python, against the two settings below.
    """
    now = timezone.now()
    grace = datetime.timedelta(hours=settings.SOURCE_STALE_GRACE_HOURS)
    rows = keys.coverage_rows(order, failures_to_stale=settings.SOURCE_STALE_AFTER_CHECKS)
    return [
        WatchSourceCoverage(
            source=row.source,
            last_checked_at=row.last_checked_at,
            # The column's choices plus NEVER are exactly what the schema publishes, so
            # the cast states what the database and this module already fix between them.
            last_status=cast(Any, row.last_status or NEVER),
            last_error=row.last_error or None,
            overdue=_is_overdue(row, now=now, grace=grace),
        )
        for row in rows
    ]


def _is_overdue(row: keys.Coverage, *, now: datetime.datetime, grace: datetime.timedelta) -> bool:
    """The stale rule, in one place.

    A source whose automated checks are off is never stale: it is deliberately not being
    checked, and saying otherwise would fill the console with rows nobody can act on.
    """
    if not row.source.active:
        return False
    if row.nth_sweep_at is not None and (row.last_ok_at is None or row.nth_sweep_at > row.last_ok_at):
        return True
    if row.last_ok_at is None:
        # Nothing has ever succeeded. With no sweep at all there is no clock to measure,
        # and with a failed run shorter than the setting allows the answer is still "not
        # yet": the failures themselves are what the rule above judges.
        return False
    return now - row.last_ok_at > CADENCE[row.source.check_frequency] + grace


# ---------------------------------------------------------------------------------------
# POST /sources and PATCH /sources/{sourceId}
# ---------------------------------------------------------------------------------------
def create_source(*, actor: Actor, order: list[str], body: WatchSourceInput) -> WatchSourceOut:
    """Register a place to watch.

    Every key is resolved and every refusal raised before the write opens, so a call naming
    a kind the library does not hold stores nothing at all.
    """
    kind = keys.resolve_keys(keys.SOURCE_KIND_LIST, [body.kind])[0]
    authority_id = keys.authority_with_id(body.authority_id)
    if keys.source_with_name(body.name) is not None:
        raise ValidationError(
            f"A source called {body.name!r} is already registered. The registry is shared, so "
            "one name names one place; change the one that exists instead.",
            code="duplicate_key",
        )
    source = keys.new_source(
        {
            "name": body.name,
            "url": _url(body.url),
            "kind": kind,
            "authority_id": authority_id,
            "check_frequency": body.check_frequency,
            "active": True,
        }
    )
    with watch_write("a source registered for the sweep"), transaction.atomic():
        source.save()
        record(
            action=REGISTERED,
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=source.id,
            subject_title=source.name,
            summary=f"{actor.label} registered a source for the agents to check.",
            tenant_id=None,
            after=_values_of(source),
        )
    return keys.source_out(source, order)


def update_source(
    *, actor: Actor, order: list[str], source_id: uuid.UUID, body: WatchSourcePatch
) -> WatchSourceOut:
    """Move a registered source's address or cadence, or switch its automated checks off.

    The name and the kind are not here and never move: a different place to watch is a
    different source, and the name is what an agent reports against. A field left out, and
    a field sent as null, both mean "leave it alone".
    """
    source = keys.source_for_write(source_id)
    sent = {name: value for name, value in body.model_dump(exclude_unset=True).items() if value is not None}
    before = _values_of(source)
    fields = []
    if "url" in sent:
        source.url = _url(sent["url"])
        fields.append("url")
    if "check_frequency" in sent:
        source.check_frequency = sent["check_frequency"]
        fields.append("check_frequency")
    if "active" in sent:
        source.active = sent["active"]
        fields.append("active")
    with watch_write("a source's registry row"), transaction.atomic():
        if fields:
            source.save(update_fields=fields)
        record(
            action=UPDATED,
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=source.id,
            subject_title=source.name,
            summary=f"{actor.label} changed a registered source.",
            tenant_id=None,
            before=before,
            after=_values_of(source),
        )
    return keys.source_out(source, order)


def _values_of(source: keys.SourceRow) -> dict[str, Any]:
    """A registry row as the audit records it. Library facts only; no bank's row is here."""
    return {
        "name": source.name,
        "url": source.url or None,
        "checkFrequency": source.check_frequency,
        "active": source.active,
    }


def _url(value: Any) -> str:
    """A URL as the column stores it, or the empty string the column uses for "none". It is
    what pydantic parsed and never the caller's raw string: an address is untrusted until
    the schema has read it (playbook 11.2)."""
    return "" if value is None else str(value)


# ---------------------------------------------------------------------------------------
# POST /agent-runs/{runId}/source-checks
# ---------------------------------------------------------------------------------------
def record_check(*, who: Principal, actor: Actor, run_id: uuid.UUID, body: WatchSourceCheckInput) -> None:
    """Log one line of the coverage log against an open run.

    Every refusal comes before the write, so a check that names a closed run or a source
    the registry does not hold logs nothing: a coverage log that recorded attempts nobody
    could place would be worse than one that recorded none.
    """
    run = runs.require_open_run(who, run_id)
    source = keys.source_with_name(body.source_name)
    if source is None:
        raise ValidationError(
            f"Not a registered source: {body.source_name}. GET /sources lists the ones a run may "
            "report on; an agent never registers one.",
            code="unknown_source",
        )
    failed = body.status == CheckStatus.FAILED.value
    subject_type, subject_id = _subject(body)
    if failed and not body.error:
        raise ValidationError("A failed check says what went wrong.", code="validation_error")
    if not failed and body.error:
        raise ValidationError("A check that succeeded carries no error.", code="validation_error")
    with watch_write("a line of the coverage log"), transaction.atomic():
        check = source.checks.create(
            agent_run=run,
            checked_at=body.checked_at or timezone.now(),
            status=body.status,
            # A failed check found nothing, whatever it reported: the count is what was
            # read, and a fetch that failed read nothing.
            items_found=0 if failed else (body.items_found or 0),
            error=body.error or "",
            kind=body.kind,
            subject_type=subject_type,
            subject_id=subject_id,
        )
        record(
            action=CHECK_LOGGED,
            actor=actor,
            subject_type=CHECK_SUBJECT_TYPE,
            subject_id=check.id,
            subject_title=source.name,
            summary=f"{actor.label} logged a {body.kind} of a source.",
            tenant_id=None,
            after={
                "source": source.name,
                "status": check.status,
                "kind": check.kind,
                "itemsFound": check.items_found,
                "agentRunId": str(run.id),
            },
        )


def _subject(body: WatchSourceCheckInput) -> tuple[str, uuid.UUID | None]:
    """The library record a re-check looked at, and the refusal when the pair does not hold.

    A re-check exists to say "this record still matches its source", so one that names no
    record says nothing; a sweep looks for new documents and names no record, so one that
    names a record is a caller sending the wrong kind. The database refuses both pairs as
    well (`source_check_recheck_names_a_subject`); refusing them here says which half is
    wrong in a sentence instead of letting a constraint error reach the caller.
    """
    if body.kind == SourceCheckKind.RECHECK.value:
        if body.subject_type is None or body.subject_id is None:
            raise ValidationError(
                "A re-check names the library record it re-checked, as `subjectType` and `subjectId`.",
                code="validation_error",
            )
        return body.subject_type, body.subject_id
    if body.subject_type is not None or body.subject_id is not None:
        raise ValidationError(
            "A sweep looks for new documents and names no library record. Send `kind` "
            f"{SourceCheckKind.RECHECK.value!r} to log a re-check of one.",
            code="validation_error",
        )
    return "", None
