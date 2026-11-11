"""The recurrence rule of a recurring duty (REG-07): the one wrapper around `python-dateutil`.

The RRULE (`RecurringDuty.recurrence_rule`) arrives in a proposal, often from an agent, so it
is untrusted: `validated` refuses with 422 `invalid_recurrence` what dateutil cannot parse,
what the day-or-coarser grammar below does not allow, a rule that never falls due, and one
falling due more than `RECURRENCE_MAX_OCCURRENCES` times in ten years. The start date is the
server's, so DTSTART is refused; `INTERVAL` and `COUNT` are checked because dateutil loops
for ever on `INTERVAL=0`.

dateutil walks a rule that matches nothing to the year 9999, so the expansion runs the rule
in years near 9999 with the same calendar and moves each date back: same answer, a few years
of walking. Whole 400-year cycles always qualify.
"""

from __future__ import annotations

import calendar
import datetime
import re

from dateutil.relativedelta import relativedelta
from dateutil.rrule import rrule, rrulestr
from django.conf import settings
from django.core.exceptions import ValidationError

# The column's width (`RecurringDuty.recurrence_rule`).
RULE_MAX_CHARS = 500
HORIZON = relativedelta(years=10)
# The Gregorian calendar's cycle: 146 097 days, a whole number of weeks.
CYCLE_YEARS = 400
FREQUENCIES = frozenset({"DAILY", "WEEKLY", "MONTHLY", "YEARLY"})
PARTS = frozenset({"FREQ", "INTERVAL", "COUNT", "UNTIL", "WKST", "BYMONTH", "BYMONTHDAY", "BYYEARDAY", "BYWEEKNO", "BYDAY", "BYSETPOS"})
_CHARACTERS = re.compile(r"[A-Z0-9=;,+\-]+")
_POSITIVE = re.compile(r"[1-9][0-9]{0,3}")


def _refused(rule: str, why: str) -> ValidationError:
    return ValidationError(f"{rule!r} is not a recurrence rule: {why}", code="invalid_recurrence")


def normalised(rule: str) -> str:
    """`rule` in the one spelling the library stores (upper case, without an `RRULE:`
    prefix), or 422 `invalid_recurrence` for a rule outside the grammar."""
    text = rule.strip().upper().removeprefix("RRULE:")
    if not text or len(text) > RULE_MAX_CHARS or not _CHARACTERS.fullmatch(text):
        raise _refused(rule, f"write one RRULE line of at most {RULE_MAX_CHARS} characters, such as FREQ=YEARLY;BYMONTH=3;BYMONTHDAY=31.")
    parts: dict[str, str] = {}
    for part in text.split(";"):
        name, _, value = part.partition("=")
        if name not in PARTS or not value or name in parts:
            raise _refused(rule, f"use each of {', '.join(sorted(PARTS))} at most once, each with a value.")
        parts[name] = value
    if parts.get("FREQ") not in FREQUENCIES:
        raise _refused(rule, f"FREQ is one of {', '.join(sorted(FREQUENCIES))}; a duty falls due on a day.")
    if any(not _POSITIVE.fullmatch(parts[name]) for name in ("INTERVAL", "COUNT") if name in parts):
        raise _refused(rule, "INTERVAL and COUNT are whole numbers from 1 to 9999.")
    if "COUNT" in parts and "UNTIL" in parts:
        raise _refused(rule, "give COUNT or UNTIL, not both.")
    return text


def expand(rule: str, start: datetime.date, end: datetime.date) -> list[datetime.date]:
    """The days `rule` falls due from `start` to `end`, both included, or 422
    `invalid_recurrence` for a rule it refuses or one that falls due more than
    `RECURRENCE_MAX_OCCURRENCES` times in that span."""
    text = normalised(rule)
    shift = _shift(start.year, end.year)
    try:
        parsed = rrulestr(text, dtstart=datetime.datetime(start.year, start.month, start.day), ignoretz=True)
    except (ValueError, TypeError) as exc:
        raise _refused(rule, "check each part's value against RFC 5545.") from exc
    assert isinstance(parsed, rrule)
    last = datetime.datetime(end.year, end.month, end.day, 23, 59, 59)
    if parsed._until is not None:
        last = min(last, parsed._until)
    if last < parsed._dtstart:
        return []
    # `until` bounds the walk after the last day; a rule with COUNT takes none (RFC 5545
    # allows one or the other), and the loop below stops it at `last` instead.
    shifted_last = last.replace(year=last.year + shift)
    shifted = parsed.replace(
        dtstart=parsed._dtstart.replace(year=start.year + shift), until=None if parsed._count else shifted_last
    )
    cap = settings.RECURRENCE_MAX_OCCURRENCES
    days: list[datetime.date] = []
    for due in shifted:
        if due > shifted_last:
            break
        if len(days) == cap:
            raise ValidationError(
                f"{rule!r} falls due more than {cap} times in ten years: a duty recurs at most that often.",
                code="invalid_recurrence",
            )
        days.append(due.date().replace(year=due.year - shift))
    return days


def _same_calendar(first: int, last: int, shift: int) -> bool:
    return datetime.date(first, 1, 1).weekday() == datetime.date(first + shift, 1, 1).weekday() and all(
        calendar.isleap(year) == calendar.isleap(year + shift) for year in range(first, last + 1)
    )


def _shift(first: int, last: int) -> int:
    """The most years the span from `first` to `last` moves toward 9999 with its calendar
    unchanged, the year either side included (an ISO week can straddle a new year). A
    multiple of `CYCLE_YEARS` always qualifies, so the search ends within one cycle."""
    first, last = max(first - 1, datetime.MINYEAR), min(last + 1, datetime.MAXYEAR)
    return next(shift for shift in range(datetime.MAXYEAR - last, -1, -1) if _same_calendar(first, last, shift))


def validated(rule: str, start: datetime.date) -> str:
    """`rule` in its stored spelling, once it falls due at least once and at most
    `RECURRENCE_MAX_OCCURRENCES` times in the ten years from `start`; 422
    `invalid_recurrence` otherwise."""
    if not expand(rule, start, start + HORIZON - datetime.timedelta(days=1)):
        raise ValidationError(f"{rule!r} never falls due in the next ten years.", code="invalid_recurrence")
    return normalised(rule)
