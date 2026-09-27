"""Recurring duties in the bank's calendar (REG-07): the library's recurring duty, the bank's
dated occurrences, and completing one generates only the next, in the bank's time zone.

The duty and its RFC 5545 rule are a library fact; an occurrence is the bank's work, on its
register entry and, where an entity's answer made the obligation apply, on that entity. The
first occurrence is written by `schedule_first()`, the one writer, called by applicability.py
in the transaction of an answer "applies"; completing one writes only the next. No horizon
of rows is written, and a read never writes one. A rule anchors its series at the date it is
read from: a rule with no phase of its own (`BYMONTH`, `BYMONTHDAY`) starts on the day it
began to apply, and after that each next date follows the last due date.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from collections.abc import Sequence
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.library.models import RecordStatus
from apps.library.reading import DutyRule, obligation_headings, recurring_duties
from apps.register.models import DutyOccurrence, DutyStatus, TenantObligation, TenantObligationScope
from apps.register.schemas import (
    RegisterDuty,
    RegisterDutyCompleteBody,
    RegisterDutyCompletion,
    RegisterDutyOccurrence,
    RegisterDutyPage,
    RegisterPersonRef,
)
from apps.shared.audit import Actor, record
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant

logger = logging.getLogger(__name__)

SUBJECT_TYPE = "duty_occurrence"
DUTY_SCHEDULED = "register.duty_scheduled"
DUTY_COMPLETED = "register.duty_completed"
OPEN = (DutyStatus.UPCOMING.value, DutyStatus.IN_PROGRESS.value, DutyStatus.MISSED.value)


def local_day(tenant: Tenant, at: datetime.datetime) -> datetime.date:
    """The calendar day `at` falls on in the bank's own time zone."""
    return timezone.localdate(at, ZoneInfo(tenant.timezone))


def next_due(rule: str, start: datetime.date, *, inclusive: bool) -> datetime.date | None:
    """The first date of `rule`, its series anchored at `start`: on or after `start` when
    `inclusive`, else strictly after it. None when the rule has ended or does not parse; the
    library's proposal validates a rule before it is stored, so the second is logged."""
    anchor = datetime.datetime.combine(start, datetime.time())
    try:
        series = rrulestr(rule, dtstart=anchor)
    except (ValueError, TypeError):
        logger.warning("recurring duty rule does not parse")
        return None
    found = series.after(anchor if inclusive else datetime.datetime.combine(start, datetime.time.max), inc=inclusive)
    return None if found is None else found.date()


# ---------------------------------------------------------------------------------------
# The one writer
# ---------------------------------------------------------------------------------------
def schedule_first(
    *,
    tenant: Tenant,
    actor: Actor,
    targets: Sequence[tuple[TenantObligation, TenantObligationScope | None]],
    at: datetime.datetime,
) -> list[DutyOccurrence]:
    """The first occurrence of each active recurring duty on each target that has none: an
    entry, or one entity's scope row of it, whose applicability has just become "applies".
    Dated from the bank's day of `at`, owned as the target is. Runs in the caller's
    transaction; one `register.duty_scheduled` event per occurrence written."""
    by_obligation: dict[uuid.UUID, list[DutyRule]] = {}
    for duty in recurring_duties({entry.obligation_id for entry, _ in targets}):
        by_obligation.setdefault(duty.obligation_id, []).append(duty)
    if not by_obligation:
        return []
    have = set(
        DutyOccurrence.objects.filter(tenant_obligation_id__in={entry.id for entry, _ in targets}).values_list(
            "recurring_duty_id", "tenant_obligation_id", "org_unit_id"
        )
    )
    today = local_day(tenant, at)
    written = []
    for entry, scope in targets:
        org_unit_id = None if scope is None else scope.org_unit_id
        owner_id, team_id = (entry.first_line_owner_id, entry.owner_team_id) if scope is None else (scope.owner_id, scope.owner_team_id)
        for duty in by_obligation.get(entry.obligation_id, []):
            if (duty.id, entry.id, org_unit_id) in have:
                continue
            due = next_due(duty.rule, today, inclusive=True)
            if due is None:
                continue
            occurrence, created = _occurrence(tenant, duty.id, entry.id, org_unit_id, due, owner_id, team_id)
            if created:
                _audit_scheduled(tenant, actor, duty, occurrence)
                written.append(occurrence)
    return written


def _occurrence(
    tenant: Tenant,
    duty_id: uuid.UUID,
    entry_id: uuid.UUID,
    org_unit_id: uuid.UUID | None,
    due: datetime.date,
    owner_id: uuid.UUID | None,
    team_id: uuid.UUID | None,
) -> tuple[DutyOccurrence, bool]:
    """The occurrence on `due`, written unless it is there already: two writers at once meet
    on the unique key, and the second reads the first's row."""
    try:
        with transaction.atomic():
            return (
                DutyOccurrence.objects.create(
                    tenant_id=tenant.id,
                    recurring_duty_id=duty_id,
                    tenant_obligation_id=entry_id,
                    org_unit_id=org_unit_id,
                    due_date=due,
                    owner_id=owner_id if team_id is None else None,
                    owner_team_id=team_id,
                ),
                True,
            )
    except IntegrityError:
        return DutyOccurrence.objects.get(recurring_duty_id=duty_id, org_unit_id=org_unit_id, due_date=due), False


def _audit_scheduled(tenant: Tenant, actor: Actor, duty: DutyRule, occurrence: DutyOccurrence) -> None:
    record(
        action=DUTY_SCHEDULED,
        actor=actor,
        subject_type=SUBJECT_TYPE,
        subject_id=occurrence.id,
        subject_title=f"{duty.title}, {occurrence.due_date.isoformat()}",
        summary="Duty occurrence scheduled.",
        tenant_id=tenant.id,
        after={
            "recurringDutyId": str(duty.id),
            "tenantObligationId": str(occurrence.tenant_obligation_id),
            "orgUnitId": None if occurrence.org_unit_id is None else str(occurrence.org_unit_id),
            "dueDate": occurrence.due_date.isoformat(),
        },
    )


# ---------------------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------------------
def list_duties(*, tenant: Tenant, order: list[str], obligation_id: uuid.UUID, limit: int, offset: int) -> RegisterDutyPage:
    """`GET /obligations/{obligationId}/duties`: the obligation's active recurring duties,
    by next due date, each with the bank's earliest open occurrence. Writes nothing; an
    obligation with no duty is an empty page."""
    if not obligation_headings([obligation_id], order):
        raise ValidationError("That obligation is not here.", code="not_found")
    rows = recurring_duties([obligation_id])
    upcoming: dict[uuid.UUID, DutyOccurrence] = {}
    for occurrence in (
        DutyOccurrence.objects.filter(recurring_duty_id__in=[duty.id for duty in rows], status__in=OPEN)
        .select_related("owner", "completed_by")
        .order_by("due_date", F("org_unit_id").asc(nulls_first=True), "id")
    ):
        upcoming.setdefault(occurrence.recurring_duty_id, occurrence)
    items = [
        RegisterDuty(
            id=duty.id,
            title=duty.title,
            recurrence_note=duty.note or None,
            next_occurrence=_out(upcoming[duty.id]) if duty.id in upcoming else None,
        )
        for duty in rows
    ]
    items.sort(key=lambda item: (item.next_occurrence is None, item.next_occurrence.due_date if item.next_occurrence else datetime.date.max))
    return RegisterDutyPage(items=items[offset : offset + limit], total=len(items))


def complete_occurrence(
    *, tenant: Tenant, actor: Actor, occurrence_id: uuid.UUID, body: RegisterDutyCompleteBody
) -> RegisterDutyCompletion:
    """`POST /duty-occurrences/{occurrenceId}/complete`: done, with the person, the time and
    the note, and the one next occurrence the rule gives after its due date, owned as this one
    was; none once the rule has ended or the library retired the duty. Completing a done
    occurrence again writes nothing and answers as the first time."""
    person = actor.id
    if person is None:
        raise ProblemError(status=403, code="permission_denied", detail="A person must do this.")
    with transaction.atomic():
        occurrence = (
            DutyOccurrence.objects.select_for_update(of=("self",))
            .select_related("recurring_duty")
            .filter(pk=occurrence_id)
            .first()  # ordering: the primary key, at most one row
        )
        if occurrence is None:
            raise ValidationError("That duty occurrence is not here.", code="not_found")
        duty = occurrence.recurring_duty
        active = duty.status == RecordStatus.ACTIVE.value
        due = next_due(duty.recurrence_rule, occurrence.due_date, inclusive=False) if active else None
        if occurrence.status == DutyStatus.DONE.value:
            following = None if due is None else _following(occurrence, due)
            return RegisterDutyCompletion(completed=_out(_reread(occurrence)), next=None if following is None else _out(following))
        before = occurrence.status
        occurrence.status = DutyStatus.DONE.value
        occurrence.completed_at = timezone.now()
        occurrence.completed_by_id = person
        occurrence.note = body.note or ""
        occurrence.version += 1
        occurrence.save(update_fields=["status", "completed_at", "completed_by", "note", "version"])
        following = None
        if due is not None:
            following, _ = _occurrence(
                tenant, duty.id, occurrence.tenant_obligation_id, occurrence.org_unit_id, due, occurrence.owner_id, occurrence.owner_team_id
            )
        record(
            action=DUTY_COMPLETED,
            actor=actor,
            subject_type=SUBJECT_TYPE,
            subject_id=occurrence.id,
            subject_title=f"{duty.title}, {occurrence.due_date.isoformat()}",
            summary="Duty occurrence completed.",
            tenant_id=tenant.id,
            before={"status": before},
            after={
                "status": DutyStatus.DONE.value,
                "nextOccurrenceId": None if following is None else str(following.id),
                "nextDueDate": None if following is None else following.due_date.isoformat(),
            },
        )
    return RegisterDutyCompletion(
        completed=_out(_reread(occurrence)), next=None if following is None else _out(_reread(following))
    )


def _following(occurrence: DutyOccurrence, due: datetime.date) -> DutyOccurrence | None:
    return DutyOccurrence.objects.filter(
        recurring_duty_id=occurrence.recurring_duty_id, org_unit_id=occurrence.org_unit_id, due_date=due
    ).first()  # ordering: unique per duty, bank, entity and date, at most one row


def _reread(occurrence: DutyOccurrence) -> DutyOccurrence:
    return DutyOccurrence.objects.select_related("owner", "completed_by").get(pk=occurrence.pk)


def _out(occurrence: DutyOccurrence) -> RegisterDutyOccurrence:
    owner, completed_by = occurrence.owner, occurrence.completed_by
    return RegisterDutyOccurrence(
        id=occurrence.id,
        due_date=occurrence.due_date,
        status=occurrence.status,  # type: ignore[arg-type]
        org_unit_id=occurrence.org_unit_id,
        owner=None if owner is None else RegisterPersonRef(id=owner.id, name=owner.name),
        completed_at=occurrence.completed_at,
        completed_by=None if completed_by is None else RegisterPersonRef(id=completed_by.id, name=completed_by.name),
        note=occurrence.note or None,
    )
