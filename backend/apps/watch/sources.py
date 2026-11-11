"""The source registry and the coverage log (WAT-01, AGT-01, ADM-02, AUD-01): where bleqq's
agents look, and every check ever made with its time, result, run and error.

- A library editor (`sources.manage`, no bank role holds it) registers and edits sources.
  No API key scope does: an agent reports on the registry and never edits it.
- An agent's key (`sources:write`) logs one line against a run it has open, naming the
  source by the name it read at run start; an unknown name is refused.

Both are library rows through `watch_write()` and `record()` (AUD-01).

Staleness is computed, never stored: the last `SOURCE_STALE_AFTER_CHECKS` sweeps all failed,
or more than the cadence plus `SOURCE_STALE_GRACE_HOURS` since the last good one. A source
with checks off is never stale; one never checked reads `never`. Only sweeps count: a
re-check of one record says nothing about the source being read since (AGT-01).

A standards publisher is not read automatically until a lawyer has read its terms (WAT-07,
D-45): a `standards_body` source, or one on a `STANDARDS_PUBLISHER_HOSTS` host, is
registered with checks off, and a run may log no check of an inactive source (422
`source_inactive`). `keys.py` resolves and renders the library rows (library fence).
"""

from __future__ import annotations

import datetime
import uuid
from urllib.parse import urlsplit
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

# What each cadence word means as a span: a meaning, not a tunable threshold (playbook 4.5).
# The grace on top is the setting.
CADENCE: dict[str, datetime.timedelta] = {
    CheckFrequency.DAILY.value: datetime.timedelta(days=1),
    CheckFrequency.WEEKLY.value: datetime.timedelta(days=7),
    CheckFrequency.MONTHLY.value: datetime.timedelta(days=30),
}

# The source kind of a standards publisher's own pages (D-45), by its stable key.
STANDARDS_BODY = "standards_body"

# `lastStatus` when the log holds no sweep: not a `check_status`, since no check was made.
NEVER = "never"


# --- GET /sources and GET /sources/coverage ---
def list_sources(order: list[str]) -> list[WatchSourceOut]:
    """The whole registry, by name. A read: it changes nothing and writes no audit row."""
    return keys.sources_out(order)


def source_coverage(order: list[str]) -> list[WatchSourceCoverage]:
    """Every source with the last line of its coverage log and whether it has gone stale: the
    log in one pass (`keys.coverage_rows`), the rule applied here.
    """
    now = timezone.now()
    grace = datetime.timedelta(hours=settings.SOURCE_STALE_GRACE_HOURS)
    rows = keys.coverage_rows(order, failures_to_stale=settings.SOURCE_STALE_AFTER_CHECKS)
    return [
        WatchSourceCoverage(
            source=row.source,
            last_checked_at=row.last_checked_at,
            # The column's choices plus NEVER are exactly what the schema publishes.
            last_status=cast(Any, row.last_status or NEVER),
            last_error=row.last_error or None,
            overdue=_is_overdue(row, now=now, grace=grace),
        )
        for row in rows
    ]


def _is_overdue(row: keys.Coverage, *, now: datetime.datetime, grace: datetime.timedelta) -> bool:
    """The stale rule, in one place. A source with checks off is never stale: nobody can act
    on it.
    """
    if not row.source.active:
        return False
    if row.nth_sweep_at is not None and (row.last_ok_at is None or row.nth_sweep_at > row.last_ok_at):
        return True
    if row.last_ok_at is None:
        # Nothing ever succeeded: no clock to measure. The failure rule above judges failures.
        return False
    return now - row.last_ok_at > CADENCE[row.source.check_frequency] + grace


# --- POST /sources and PATCH /sources/{sourceId} ---
def create_source(*, actor: Actor, order: list[str], body: WatchSourceInput) -> WatchSourceOut:
    """Register a place to watch. Every refusal comes before the write."""
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
            "active": not (kind.key == STANDARDS_BODY or _on_a_publisher_host(_url(body.url))),
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
    """Move a source's address or cadence, or switch its automated checks off. Name and kind
    never move (a different place is a different source). Unsent and null leave a field alone.
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
    if source.active and _on_a_publisher_host(source.url):
        raise ValidationError(
            "This address is a standards publisher's, which no run reads until a lawyer has "
            "cleared its terms. Its checks stay off; the host leaves STANDARDS_PUBLISHER_HOSTS "
            "when they are cleared.",
            code="validation_error",
        )
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


def _on_a_publisher_host(url: str) -> bool:
    """Whether an address is on a host of `STANDARDS_PUBLISHER_HOSTS` or a subdomain of one:
    a standards publisher no run reads until a lawyer has cleared its terms (D-45)."""
    # A fully qualified name's root dot (`iso.org.`) names the same host.
    host = (urlsplit(url).hostname or "").rstrip(".")
    return any(host == listed or host.endswith(f".{listed}") for listed in settings.STANDARDS_PUBLISHER_HOSTS)


def _values_of(source: keys.SourceRow) -> dict[str, Any]:
    """A registry row as the audit records it. Library facts only; no bank's row is here."""
    return {
        "name": source.name,
        "url": source.url or None,
        "checkFrequency": source.check_frequency,
        "active": source.active,
    }


def _url(value: Any) -> str:
    """A URL as the column stores it ("" for none), always pydantic's parse: an address is
    untrusted (playbook 11.2)."""
    return "" if value is None else str(value)


# --- POST /agent-runs/{runId}/source-checks ---
def record_check(*, who: Principal, actor: Actor, run_id: uuid.UUID, body: WatchSourceCheckInput) -> None:
    """Log one line of the coverage log against an open run. Every refusal comes before the
    write, so a closed run or unknown source logs nothing. A re-check past
    `WATCH_RUN_MAX_RECHECKS` is `run_budget_exhausted` (H41).
    """
    run = runs.require_open_run(who, run_id)
    source = keys.source_with_name(body.source_name)
    if source is None:
        raise ValidationError(
            f"Not a registered source: {body.source_name}. GET /sources lists the ones a run may "
            "report on; an agent never registers one.",
            code="unknown_source",
        )
    if not source.active:
        raise ValidationError(
            f"{source.name} is registered with its automated checks off, so no run reads it. "
            "A standards publisher stays that way until its terms allow an automated check.",
            code="source_inactive",
        )
    failed = body.status == CheckStatus.FAILED.value
    subject_type, subject_id = _subject(body)
    if failed and not body.error:
        raise ValidationError("A failed check says what went wrong.", code="validation_error")
    if not failed and body.error:
        raise ValidationError("A check that succeeded carries no error.", code="validation_error")
    with watch_write("a line of the coverage log"), transaction.atomic():
        if body.kind == SourceCheckKind.RECHECK.value:
            runs.spend(
                run,
                run.source_checks.filter(kind=SourceCheckKind.RECHECK.value),
                limit=settings.WATCH_RUN_MAX_RECHECKS,
                what=("re-check", "re-checks"),
            )
        check = source.checks.create(
            agent_run=run,
            checked_at=body.checked_at or timezone.now(),
            status=body.status,
            # A failed fetch read nothing, whatever it reported.
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
    """The library record a re-check looked at. A re-check must name a record and a sweep
    must not; the database refuses both too (`source_check_recheck_names_a_subject`), but here
    the refusal says which half is wrong.
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
