"""The public list of upcoming dates (HOM-04, AGT-02, NFR-01): what is on it, what can
never be on it, and that every caller gets the same answer.

`GET /upcoming` is the one route in this app an agent's key reaches, and the reason is that
it holds no bank in it at all. That claim is what this file exists to prove, from three
directions rather than one:

- **The shape.** The response keys are exactly `UpcomingItem`'s, asserted against the schema
  itself rather than against a list somebody typed, so a field added to the row in a later
  chunk fails this test instead of quietly reaching a newsletter.
- **The answer.** Two banks with different scopes, different cases and different judgements
  read byte-identical bodies. A footprint filter, a case join or an owner leaking in would
  break that equality whatever the shape said.
- **The gate.** A key without `upcoming:read` is refused; a key holding every scope there is
  reaches nothing else here (`tests_contract.py` owns that half).

Nothing here depends on the day the suite runs: the clock is frozen at a fixed instant and
every date is written out (playbook 8.3).
"""

from __future__ import annotations

import datetime
from typing import Any
from unittest import mock

from django.test import TestCase

from apps.cases import testing as cases_build
from apps.home import calendar as calendar_reads
from apps.home.schemas import HomeUpcomingItem, HomeUpcomingQuery
from apps.identity.models import User
from apps.shared import factories, permissions as perms
from apps.shared.models import Tenant
from apps.shared.testing import API_KEY_FOR_TESTS, agent_principal, sign_in, stub_api_key
from apps.watch import testing as watch_build
from apps.watch.models import ChangeStatus, RegulatoryChange
from apps.watch.write import watch_write

URL = "/api/v1/upcoming"
D = datetime.date

# A fixed instant, never "now". The server reads in UTC, where this instant is still
# 30 September, so a date of 30 September is today and one of 29 September has gone.
INSTANT = datetime.datetime(2026, 9, 30, 22, 30, tzinfo=datetime.UTC)
TODAY = D(2026, 9, 30)
GONE = D(2026, 9, 29)
SOON = D(2026, 10, 15)
LATER = D(2027, 1, 20)

# Four queries, measured 2026-09-21 and pinned: the page with its change type (1), that
# type's labels (1), and the urgency rows with their labels (2, through the watch app's own
# rule, which is what keeps the pill tone out of the answer). None grows with the page.
UPCOMING_QUERIES = 4


def a_change(*, title: str, key_date: datetime.date | None, urgency: str | None = "act_now") -> RegulatoryChange:
    return watch_build.change(title=title, key_date=key_date, key_date_label="In force", urgency=urgency)


class UpcomingContents(TestCase):
    """What reaches the public list and what does not (HOM-04)."""

    soon: RegulatoryChange
    later: RegulatoryChange
    today: RegulatoryChange

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.soon = a_change(title="Research payments", key_date=SOON)
        cls.later = a_change(title="Reporting", key_date=LATER, urgency="six_months_plus")
        cls.today = a_change(title="In force today", key_date=TODAY)
        # Four that must not be listed, each for a reason of its own.
        a_change(title="Yesterday", key_date=GONE)
        a_change(title="No date yet", key_date=None)
        withdrawn = a_change(title="Withdrawn", key_date=SOON)
        superseded = a_change(title="Superseded", key_date=SOON)
        with watch_write("test setup"):
            RegulatoryChange.objects.filter(pk=withdrawn.pk).update(status=ChangeStatus.WITHDRAWN.value)
            RegulatoryChange.objects.filter(pk=superseded.pk).update(status=ChangeStatus.SUPERSEDED.value)

    def read(self, **page: Any) -> list[HomeUpcomingItem]:
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            return calendar_reads.list_upcoming(["en"], HomeUpcomingQuery(**page))

    def test_the_dates_still_ahead_are_listed_earliest_first(self) -> None:
        self.assertEqual([item.title for item in self.read()], ["In force today", "Research payments", "Reporting"])

    def test_what_is_not_upcoming_is_absent_and_each_for_its_own_reason(self) -> None:
        """A date that has gone, a reform nobody has dated yet, and two the library no
        longer holds as active — a withdrawn reform is not upcoming however its date reads."""
        listed = [item.title for item in self.read()]
        for absent in ("Yesterday", "No date yet", "Withdrawn", "Superseded"):
            with self.subTest(absent=absent):
                self.assertNotIn(absent, listed)

    def test_today_itself_is_still_upcoming(self) -> None:
        """The floor is inclusive: a rule coming into force this morning is the one a reader
        most needs to see, and dropping it at midnight would be the wrong direction."""
        self.assertIn("In force today", [item.title for item in self.read()])

    def test_a_row_carries_the_librarys_facts_and_keys_rather_than_phrases(self) -> None:
        item = next(row for row in self.read() if row.title == "Research payments")
        self.assertEqual((item.change_id, item.key_date, item.key_date_label), (self.soon.id, SOON, "In force"))
        self.assertEqual((item.key_date_precision, item.authority_label), ("day", "Finansinspektionen"))
        self.assertEqual((item.change_type.key, item.change_type.kind), ("adopted", "adopted"))
        assert item.suggested_urgency is not None
        self.assertEqual((item.suggested_urgency.key, item.suggested_urgency.label), ("act_now", "Act now"))
        self.assertIsNone(item.suggested_urgency.kind, "the pill's tone is nobody's to send (NFR-03)")
        self.assertEqual(item.source_url, "https://www.fi.se/")

    def test_a_change_nobody_scored_carries_a_null_urgency_rather_than_a_guess(self) -> None:
        a_change(title="Unscored", key_date=SOON, urgency=None)
        unscored = next(row for row in self.read() if row.title == "Unscored")
        self.assertIsNone(unscored.suggested_urgency)

    def test_the_page_walks_the_list_and_never_reports_a_total(self) -> None:
        self.assertEqual([item.title for item in self.read(limit=2)], ["In force today", "Research payments"])
        self.assertEqual([item.title for item in self.read(limit=2, offset=2)], ["Reporting"])
        self.assertEqual(self.read(limit=2, offset=99), [], "past the end is an empty page, not an error")

    def test_the_query_count_does_not_grow_with_the_length_of_the_page(self) -> None:
        for number in range(20):
            a_change(title=f"Reform {number}", key_date=SOON + datetime.timedelta(days=number))
        for limit in (1, 100):
            with self.subTest(limit=limit), self.assertNumQueries(UPCOMING_QUERIES):
                self.assertEqual(len(self.read(limit=limit)), min(limit, 23))


class UpcomingHoldsNoBank(TestCase):
    """NFR-01: the list is library facts exactly, which is what makes an agent's key safe on
    it. Proved by the shape and by two banks reading the same bytes."""

    first: Tenant
    second: Tenant
    reader: User
    other_reader: User

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        change = a_change(title="Research payments", key_date=SOON)
        banks = cases_build.two_tenants_with_different_footprints()
        cls.first, cls.second = banks.inside, banks.outside
        cls.reader = factories.member_user(cls.first, roles=("reader",))
        cls.other_reader = factories.member_user(cls.second, roles=("reader",))
        # Two banks, two different judgements about one reform: one has it in scope and has
        # written a "So what?" on its case, the other has it out of scope.
        cases_build.case(cls.first, change, so_what_text="This changes how we pay for research.")
        cases_build.case(cls.second, change, footprint_match=False)

    def get(self, user: User, tenant: Tenant) -> Any:
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            return self.client.get(URL, **sign_in(user, tenant=tenant))

    def test_the_response_keys_are_exactly_the_public_row(self) -> None:
        """Asserted against the schema rather than a typed list, so a field added to the row
        later fails here instead of reaching a newsletter unnoticed."""
        expected = {field.alias or name for name, field in HomeUpcomingItem.model_fields.items()}
        body = self.get(self.reader, self.first).json()
        self.assertEqual(set(body[0]), expected)
        for forbidden in ("case", "inFootprint", "ownerId", "soWhat", "soWhatText", "tenantId", "urgency"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, body[0])

    def test_two_banks_read_byte_identical_answers(self) -> None:
        """A footprint filter, a case join or an owner leaking in would break this equality
        whatever the shape said: one bank holds the reform in scope with a judgement written
        on it, the other holds it out of scope."""
        self.assertEqual(
            self.get(self.reader, self.first).content, self.get(self.other_reader, self.second).content
        )

    def test_the_banks_own_so_what_is_nowhere_in_the_body(self) -> None:
        self.assertNotIn(b"This changes how we pay for research.", self.get(self.reader, self.first).content)

    def test_an_agent_key_reads_the_same_list_as_a_person(self) -> None:
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            with stub_api_key(agent_principal(scopes={perms.SCOPE_UPCOMING_READ})):
                by_key = self.client.get(URL, HTTP_X_API_KEY=API_KEY_FOR_TESTS)
        self.assertEqual(by_key.status_code, 200)
        self.assertEqual(by_key.content, self.get(self.reader, self.first).content)

    def test_a_key_without_the_scope_is_refused_and_reads_nothing(self) -> None:
        with stub_api_key(agent_principal(scopes={perms.SCOPE_LIBRARY_READ})):
            refused = self.client.get(URL, HTTP_X_API_KEY=API_KEY_FOR_TESTS)
        self.assertEqual((refused.status_code, refused.json()["code"]), (403, "permission_denied"))
        self.assertEqual(refused.json()["requiredPermission"], perms.SCOPE_UPCOMING_READ)


class UpcomingRoute(TestCase):
    """`GET /upcoming` end to end."""

    tenant: Tenant
    reader: User

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug="upcoming-route", timezone="Europe/Stockholm")
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        a_change(title="Research payments", key_date=SOON)

    def test_a_reader_gets_the_list_in_camel_case(self) -> None:
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            response = self.client.get(URL, **sign_in(self.reader, tenant=self.tenant))
        self.assertEqual(response.status_code, 200)
        row = response.json()[0]
        self.assertEqual(row["keyDate"], "2026-10-15")
        self.assertEqual(row["keyDateLabel"], "In force")
        self.assertEqual(row["authorityLabel"], "Finansinspektionen")
        self.assertEqual(row["suggestedUrgency"]["key"], "act_now")

    def test_an_empty_library_is_a_200_with_an_empty_array(self) -> None:
        with mock.patch("django.utils.timezone.now", return_value=INSTANT):
            far = self.client.get(f"{URL}?offset=50", **sign_in(self.reader, tenant=self.tenant))
        self.assertEqual((far.status_code, far.json()), (200, []))

    def test_without_a_credential_it_is_401(self) -> None:
        refused = self.client.get(URL)
        self.assertEqual((refused.status_code, refused.json()["code"]), (401, "unauthenticated"))
