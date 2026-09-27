"""The recurrence rule of a recurring duty (REG-07, c8-recurring-duty-proposal).

`apps.library.recurrence` is the one wrapper around `python-dateutil`: it expands an RFC 5545
RRULE from a date and refuses what it cannot parse, what is finer than a day, what never
falls due, and what would fall due more than `RECURRENCE_MAX_OCCURRENCES` times in ten years,
all 422 `invalid_recurrence`. A rule arrives from a proposer, an agent as often as a person,
so each refusal is a trust-boundary check, not a courtesy.
"""

from __future__ import annotations

import time
from datetime import date

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, override_settings

from apps.library import recurrence

START = date(2026, 1, 15)
TEN_YEARS = date(2036, 1, 15)


class Expansion(SimpleTestCase):
    """A daily, a monthly, a quarterly and a yearly duty fall due on the dates the rule says."""

    def test_a_daily_rule_falls_due_every_day(self) -> None:
        self.assertEqual(
            recurrence.expand("FREQ=DAILY", START, date(2026, 1, 18)),
            [date(2026, 1, 15), date(2026, 1, 16), date(2026, 1, 17), date(2026, 1, 18)],
        )

    def test_a_monthly_rule_falls_due_on_its_day_of_the_month(self) -> None:
        self.assertEqual(
            recurrence.expand("FREQ=MONTHLY;BYMONTHDAY=10", START, date(2026, 4, 30)),
            [date(2026, 2, 10), date(2026, 3, 10), date(2026, 4, 10)],
        )

    def test_a_quarterly_rule_falls_due_after_each_quarter(self) -> None:
        # The quarterly report a month after each quarter closes.
        rule = "FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=-1"
        self.assertEqual(
            recurrence.expand(rule, START, date(2026, 12, 31)),
            [date(2026, 1, 31), date(2026, 4, 30), date(2026, 7, 31), date(2026, 10, 31)],
        )
        self.assertEqual(
            recurrence.expand("FREQ=MONTHLY;INTERVAL=3", START, date(2026, 12, 31)),
            [date(2026, 1, 15), date(2026, 4, 15), date(2026, 7, 15), date(2026, 10, 15)],
        )

    def test_a_yearly_rule_falls_due_once_a_year_and_honours_a_leap_day(self) -> None:
        self.assertEqual(
            recurrence.expand("FREQ=YEARLY;BYMONTH=3;BYMONTHDAY=31", START, date(2028, 12, 31)),
            [date(2026, 3, 31), date(2027, 3, 31), date(2028, 3, 31)],
        )
        self.assertEqual(
            recurrence.expand("FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=29", START, date(2033, 1, 1)),
            [date(2028, 2, 29), date(2032, 2, 29)],
        )

    def test_weekdays_land_on_the_real_calendar(self) -> None:
        # The last working day of each month: a weekday rule proves the expansion reads the
        # real calendar, whatever years it runs over.
        rule = "FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1"
        self.assertEqual(
            recurrence.expand(rule, START, date(2026, 5, 31)),
            [date(2026, 1, 30), date(2026, 2, 27), date(2026, 3, 31), date(2026, 4, 30), date(2026, 5, 29)],
        )

    def test_count_and_until_end_the_duty(self) -> None:
        self.assertEqual(
            recurrence.expand("FREQ=YEARLY;COUNT=2", START, TEN_YEARS), [date(2026, 1, 15), date(2027, 1, 15)]
        )
        self.assertEqual(
            recurrence.expand("FREQ=YEARLY;UNTIL=20280601", START, TEN_YEARS),
            [date(2026, 1, 15), date(2027, 1, 15), date(2028, 1, 15)],
        )
        self.assertEqual(
            recurrence.expand("RRULE:FREQ=YEARLY;UNTIL=20271231T235959Z", START, TEN_YEARS),
            [date(2026, 1, 15), date(2027, 1, 15)],
        )

    def test_the_rule_is_stored_in_one_spelling(self) -> None:
        self.assertEqual(recurrence.validated(" rrule:freq=yearly;bymonth=3 ", START), "FREQ=YEARLY;BYMONTH=3")


class Refusals(SimpleTestCase):
    """What the wrapper refuses, each 422 `invalid_recurrence` with words a proposer can act on."""

    def assert_refused(self, rule: str, words: str) -> None:
        with self.assertRaises(ValidationError) as caught:
            recurrence.validated(rule, START)
        self.assertEqual(caught.exception.code, "invalid_recurrence")
        self.assertIn(words, caught.exception.message)

    def test_a_rule_it_cannot_parse(self) -> None:
        for rule in ("", "every quarter", "FREQ=FORTNIGHTLY", "FREQ=MONTHLY;INTERVAL=0", "FREQ=YEARLY;BYSETPOS=0"):
            with self.subTest(rule=rule):
                self.assert_refused(rule, "is not a recurrence rule")

    def test_a_start_date_or_a_second_line_is_not_the_proposers(self) -> None:
        # The duty's dates start where the server says; DTSTART and a second line are refused.
        for rule in ("DTSTART:20200101\nRRULE:FREQ=YEARLY", "FREQ=YEARLY\nRDATE:20300101", "FREQ=YEARLY;DTSTART=20200101"):
            with self.subTest(rule=rule):
                self.assert_refused(rule, "is not a recurrence rule")

    def test_a_rule_finer_than_a_day(self) -> None:
        for rule in ("FREQ=HOURLY", "FREQ=SECONDLY;BYMONTH=2;BYMONTHDAY=30", "FREQ=DAILY;BYHOUR=9"):
            with self.subTest(rule=rule):
                self.assert_refused(rule, "is not a recurrence rule")

    def test_count_with_until(self) -> None:
        self.assert_refused("FREQ=YEARLY;COUNT=3;UNTIL=20300101", "is not a recurrence rule")

    def test_a_rule_that_never_falls_due(self) -> None:
        self.assert_refused("FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=30", "never falls due")
        self.assert_refused("FREQ=MONTHLY;BYMONTHDAY=40", "never falls due")
        self.assert_refused("FREQ=YEARLY;UNTIL=20200101", "never falls due")

    def test_a_rule_that_never_falls_due_is_refused_quickly(self) -> None:
        # dateutil walks an impossible rule to the year 9999; the wrapper runs it at the end
        # of the calendar's 400-year cycle so the walk is short.
        began = time.monotonic()
        self.assert_refused("FREQ=DAILY;BYMONTH=2;BYMONTHDAY=30", "never falls due")
        self.assertLess(time.monotonic() - began, 1.0)

    def test_a_rule_over_the_cap(self) -> None:
        # Monthly for ten years is 120 and passes; weekly is over.
        self.assertEqual(len(recurrence.expand("FREQ=MONTHLY", START, date(2036, 1, 14))), 120)
        self.assertEqual(recurrence.validated("FREQ=MONTHLY", START), "FREQ=MONTHLY")
        self.assert_refused("FREQ=WEEKLY", "more than 120 times in ten years")
        self.assert_refused("FREQ=DAILY", "more than 120 times in ten years")

    @override_settings(RECURRENCE_MAX_OCCURRENCES=4)
    def test_the_cap_is_a_setting(self) -> None:
        self.assertEqual(recurrence.validated("FREQ=YEARLY;INTERVAL=3", START), "FREQ=YEARLY;INTERVAL=3")
        self.assert_refused("FREQ=YEARLY", "more than 4 times in ten years")

    def test_a_rule_too_long_to_store(self) -> None:
        self.assert_refused("FREQ=YEARLY;BYMONTHDAY=" + ",".join(["1"] * 300), "is not a recurrence rule")
