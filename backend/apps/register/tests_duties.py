"""Recurring duties in the bank's calendar (REG-07): the first occurrence is written by the one
writer when applicability becomes "applies", completing one writes only the next, computed
from the library's RRULE in the bank's time zone, and a read writes nothing. Every date here
is pinned; nothing reads today's date except the route test, which reads the decision time
the route stored.

Proven to fail 2026-09-25: with the tenant's zone dropped from `local_day()` the late-evening
decision landed a quarter early; with the done check removed the repeated completion was
audited a second time; with the writer's lookup removed a second first occurrence was
written; with the hook removed from applicability.py no first occurrence was written."""

from __future__ import annotations

import datetime
from typing import Any

from django.db import IntegrityError, transaction
from django.test import Client

from apps.library import testing as library_build
from apps.library.models import Obligation, RecurringDuty
from apps.register import duties
from apps.register.logic import ensure_register_entry
from apps.register.models import DutyOccurrence, TenantObligation, TenantObligationScope
from apps.register.tests_applicability import Bank, banks_duty, seed_library
from apps.shared import factories
from apps.shared.audit import Actor
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in

V1 = "/api/v1"
QUARTERLY = "FREQ=MONTHLY;BYMONTH=3,6,9,12;BYMONTHDAY=-1"
# 22:30 UTC on 30 September is already 1 October in Stockholm: the quarter that ends that day
# is behind the bank, so its first due date is the next quarter's end.
LATE_EVENING = datetime.datetime(2026, 9, 30, 22, 30, tzinfo=datetime.UTC)


def day(text: str) -> datetime.date:
    return datetime.date.fromisoformat(text)


class NextDue(ScenarioTestCase):
    """The one place a rule becomes a date."""

    def test_the_next_date_after_a_due_date_follows_the_rule(self) -> None:
        self.assertEqual(duties.next_due(QUARTERLY, day("2026-12-31"), inclusive=False), day("2027-03-31"))
        self.assertEqual(duties.next_due("FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=-1", day("2026-12-31"), inclusive=False), day("2027-03-31"))
        self.assertEqual(duties.next_due("FREQ=YEARLY;BYMONTH=11;BYMONTHDAY=30", day("2026-11-30"), inclusive=False), day("2027-11-30"))

    def test_a_first_date_may_be_the_day_itself(self) -> None:
        self.assertEqual(duties.next_due(QUARTERLY, day("2026-09-30"), inclusive=True), day("2026-09-30"))
        self.assertEqual(duties.next_due(QUARTERLY, day("2026-10-01"), inclusive=True), day("2026-12-31"))

    def test_a_rule_that_has_ended_or_does_not_parse_gives_no_date(self) -> None:
        self.assertIsNone(duties.next_due(f"{QUARTERLY};COUNT=1", day("2026-12-31"), inclusive=False))
        self.assertIsNone(duties.next_due("FREQ=YEARLY;UNTIL=20261231", day("2026-12-31"), inclusive=False))
        self.assertIsNone(duties.next_due("EVERY QUARTER", day("2026-12-31"), inclusive=False))

    def test_the_day_is_the_banks_own(self) -> None:
        stockholm = factories.tenant(slug="duty-sthlm", timezone="Europe/Stockholm")
        self.assertEqual(duties.local_day(stockholm, LATE_EVENING), day("2026-10-01"))
        london = factories.tenant(slug="duty-london", timezone="Europe/London")
        self.assertEqual(duties.local_day(london, LATE_EVENING), day("2026-09-30"))


class DutyTestCase(ScenarioTestCase):
    a: Bank
    b: Bank
    law: Obligation
    duty: RecurringDuty

    @classmethod
    def setUpTestData(cls) -> None:
        seed_library()
        cls.a = Bank("duty-a")
        cls.b = Bank("duty-b")
        cls.law = banks_duty()
        cls.duty = library_build.recurring_duty(cls.law, rule=QUARTERLY, note="Every quarter, on its last day")

    def actor(self, bank: Bank | None = None) -> Actor:
        who = (bank or self.a).officer
        return factories.user_actor(label=who.name, user_id=who.id)

    def entry(self, bank: Bank | None = None) -> TenantObligation:
        bank = bank or self.a
        self.activate(bank.tenant)
        return ensure_register_entry(tenant_id=bank.tenant.id, obligation_id=self.law.id, actor=self.actor(bank))

    def first(self, *, bank: Bank | None = None, scope: TenantObligationScope | None = None, at: datetime.datetime = LATE_EVENING) -> list[DutyOccurrence]:
        bank = bank or self.a
        entry = self.entry(bank)
        with transaction.atomic():
            return duties.schedule_first(tenant=bank.tenant, actor=self.actor(bank), targets=[(entry, scope)], at=at)

    def occurrences(self, bank: Bank | None = None) -> list[DutyOccurrence]:
        self.activate((bank or self.a).tenant)
        return list(DutyOccurrence.objects.all())

    def audit(self, action: str, bank: Bank | None = None) -> int:
        self.activate((bank or self.a).tenant)
        return AuditEvent.objects.filter(action=action).count()

    def complete(self, occurrence: Any, *, who: Any = None, note: str | None = None, bank: Bank | None = None, client: Any = None) -> Any:
        """Completing as `who`, the officer by default. A repeated completion writes nothing by
        design, so it passes a plain `Client()` instead of the one that demands an audit row."""
        bank = bank or self.a
        return (client or self.client).post(
            f"{V1}/duty-occurrences/{getattr(occurrence, 'id', occurrence)}/complete",
            data={} if note is None else {"note": note},
            content_type="application/json",
            **sign_in(who or bank.officer, tenant=bank.tenant),
        )

    def list(self, *, bank: Bank | None = None, obligation: Any = None) -> Any:
        bank = bank or self.a
        return self.client.get(
            f"{V1}/obligations/{getattr(obligation or self.law, 'id', obligation)}/duties", **sign_in(bank.officer, tenant=bank.tenant)
        )


class TheFirstOccurrence(DutyTestCase):
    def test_the_writer_dates_it_in_the_banks_zone_and_audits_it(self) -> None:
        [occurrence] = self.first()
        self.assertEqual(
            (occurrence.recurring_duty_id, occurrence.due_date, occurrence.status, occurrence.org_unit_id),
            (self.duty.id, day("2026-12-31"), "upcoming", None),
        )
        self.assertEqual(self.audit(duties.DUTY_SCHEDULED), 1)

    def test_a_second_call_for_the_same_target_writes_nothing(self) -> None:
        self.first()
        self.assertEqual(self.first(at=LATE_EVENING + datetime.timedelta(days=200)), [])
        self.assertEqual(len(self.occurrences()), 1)
        self.assertEqual(self.audit(duties.DUTY_SCHEDULED), 1)

    def test_an_entity_has_its_own_series_and_owner(self) -> None:
        self.first()
        entry = self.entry()
        scope = TenantObligationScope.objects.create(
            tenant=self.a.tenant, tenant_obligation=entry, org_unit=self.a.bank_ab, compliance_status=entry.compliance_status, owner=self.a.owner
        )
        [occurrence] = self.first(scope=scope)
        self.assertEqual((occurrence.org_unit_id, occurrence.owner_id), (self.a.bank_ab.id, self.a.owner.id))
        self.assertEqual(len(self.occurrences()), 2)

    def test_a_rule_that_ended_before_the_day_writes_nothing(self) -> None:
        other = library_build.obligation(self.law.instrument, key="lbf-no-duty", ref_label="7 kap. 2 §")
        library_build.recurring_duty(other, title="Once only", rule=f"{QUARTERLY};UNTIL=20260101")
        self.activate(self.a.tenant)
        entry = ensure_register_entry(tenant_id=self.a.tenant.id, obligation_id=other.id, actor=self.actor())
        with transaction.atomic():
            self.assertEqual(duties.schedule_first(tenant=self.a.tenant, actor=self.actor(), targets=[(entry, None)], at=LATE_EVENING), [])

    def test_setting_applies_through_the_route_writes_the_first_and_other_answers_write_none(self) -> None:
        def put(body: dict[str, Any]) -> Any:
            return self.client.put(
                f"{V1}/obligations/{self.law.id}/applicability", data=body, content_type="application/json", **sign_in(self.a.officer, tenant=self.a.tenant)
            )

        self.assertEqual(put({"applicability": "not_applicable", "reason": "No client money"}).status_code, 200)
        self.assertEqual(self.occurrences(), [])
        self.assertEqual(put({"applicability": "applies", "reason": "Client money"}).status_code, 200)
        self.assertEqual(put({"orgUnitId": str(self.a.bank_ab.id), "applicability": "applies", "reason": "Client money"}).status_code, 200)
        self.assertEqual(put({"applicability": "applies", "reason": "Still client money"}).status_code, 200)
        self.activate(self.a.tenant)
        entry = TenantObligation.objects.get(obligation=self.law)
        assert entry.applicability_decided_at is not None
        first = duties.next_due(QUARTERLY, duties.local_day(self.a.tenant, entry.applicability_decided_at), inclusive=True)
        self.assertEqual(
            sorted((row.org_unit_id is not None, row.due_date) for row in self.occurrences()), [(False, first), (True, first)]
        )
        self.assertEqual(self.occurrences(self.b), [])

    def test_the_database_refuses_another_banks_entry(self) -> None:
        entry_b = self.entry(self.b)
        self.activate(self.a.tenant)
        with self.assertRaises(IntegrityError), transaction.atomic():
            DutyOccurrence.objects.create(tenant=self.a.tenant, recurring_duty=self.duty, tenant_obligation_id=entry_b.id, due_date=day("2026-12-31"))


class Completing(DutyTestCase):
    def test_completing_writes_exactly_the_next_and_again_writes_nothing(self) -> None:
        [occurrence] = self.first()
        response = self.complete(occurrence, note="Filed on 20 December")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(
            (body["completed"]["status"], body["completed"]["note"], body["completed"]["completedBy"]["id"]),
            ("done", "Filed on 20 December", str(self.a.officer.id)),
        )
        self.assertEqual((body["next"]["dueDate"], body["next"]["status"]), ("2027-03-31", "upcoming"))
        self.assertEqual(len(self.occurrences()), 2)
        self.assertEqual(self.audit(duties.DUTY_COMPLETED), 1)

        again = self.complete(occurrence, note="Another note", client=Client())
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual((again.json()["next"]["id"], again.json()["completed"]["note"]), (body["next"]["id"], "Filed on 20 December"))
        self.assertEqual(len(self.occurrences()), 2)
        self.assertEqual(self.audit(duties.DUTY_COMPLETED), 1)
        self.activate(self.a.tenant)
        self.assertEqual(DutyOccurrence.objects.get(pk=occurrence.pk).version, 2)

    def test_a_next_occurrence_already_present_is_not_written_twice(self) -> None:
        [occurrence] = self.first()
        present = DutyOccurrence.objects.create(
            tenant=self.a.tenant, recurring_duty=self.duty, tenant_obligation=occurrence.tenant_obligation, due_date=day("2027-03-31")
        )
        response = self.complete(occurrence)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["next"]["id"], str(present.id))
        self.assertEqual(len(self.occurrences()), 2)

    def test_the_next_keeps_the_entity_and_the_owner(self) -> None:
        entry = self.entry()
        scope = TenantObligationScope.objects.create(
            tenant=self.a.tenant, tenant_obligation=entry, org_unit=self.a.bank_ab, compliance_status=entry.compliance_status, owner=self.a.owner
        )
        [occurrence] = self.first(scope=scope)
        self.assertEqual(self.complete(occurrence).status_code, 200)
        self.activate(self.a.tenant)
        following = DutyOccurrence.objects.get(due_date=day("2027-03-31"))
        self.assertEqual((following.org_unit_id, following.owner_id), (self.a.bank_ab.id, self.a.owner.id))

    def test_a_rule_that_has_ended_completes_with_no_next(self) -> None:
        other = library_build.obligation(self.law.instrument, key="lbf-last", ref_label="7 kap. 3 §")
        library_build.recurring_duty(other, title="Last report", rule=f"{QUARTERLY};UNTIL=20261231")
        self.activate(self.a.tenant)
        entry = ensure_register_entry(tenant_id=self.a.tenant.id, obligation_id=other.id, actor=self.actor())
        with transaction.atomic():
            [occurrence] = duties.schedule_first(tenant=self.a.tenant, actor=self.actor(), targets=[(entry, None)], at=LATE_EVENING)
        response = self.complete(occurrence)
        self.assertEqual((response.status_code, response.json()["next"]), (200, None))
        self.assertEqual(len(self.occurrences()), 1)

    def test_a_duty_the_library_retired_completes_with_no_next_and_is_not_listed(self) -> None:
        [occurrence] = self.first()
        retired = library_build.recurring_duty(self.law, title="Old report", status="retired")
        DutyOccurrence.objects.create(
            tenant=self.a.tenant, recurring_duty=retired, tenant_obligation=occurrence.tenant_obligation, due_date=day("2026-12-31")
        )
        old = DutyOccurrence.objects.get(recurring_duty=retired)
        response = self.complete(old)
        self.assertEqual((response.status_code, response.json()["next"]), (200, None))
        self.assertEqual([item["id"] for item in self.list().json()["items"]], [str(self.duty.id)])

    def test_another_bank_gets_404_and_a_reader_403_and_neither_writes(self) -> None:
        [occurrence] = self.first()
        response = self.complete(occurrence, bank=self.b)
        self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))
        reader = factories.member_user(self.a.tenant, roles=("reader",))
        response = self.complete(occurrence, who=reader)
        self.assertEqual((response.status_code, response.json()["requiredPermission"]), (403, "register.edit"))
        self.assertEqual([row.status for row in self.occurrences()], ["upcoming"])
        self.assertEqual(self.audit(duties.DUTY_COMPLETED), 0)


class Listing(DutyTestCase):
    def test_a_read_writes_nothing_and_shows_no_occurrence_before_one_exists(self) -> None:
        before = self.audit(duties.DUTY_SCHEDULED)
        response = self.list()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["total"], 1)
        [item] = response.json()["items"]
        self.assertEqual(
            (item["id"], item["title"], item["recurrenceNote"], item["nextOccurrence"]),
            (str(self.duty.id), "Quarterly report to the supervisor", "Every quarter, on its last day", None),
        )
        self.assertEqual(self.occurrences(), [])
        self.assertEqual(self.audit(duties.DUTY_SCHEDULED), before)

    def test_the_next_open_occurrence_is_the_banks_own(self) -> None:
        [occurrence] = self.first()
        self.complete(occurrence)
        [item] = self.list().json()["items"]
        self.assertEqual((item["nextOccurrence"]["dueDate"], item["nextOccurrence"]["status"]), ("2027-03-31", "upcoming"))
        [other_bank] = self.list(bank=self.b).json()["items"]
        self.assertIsNone(other_bank["nextOccurrence"])

    def test_an_obligation_the_bank_cannot_see_is_404_and_one_without_duties_an_empty_page(self) -> None:
        private = library_build.obligation(self.law.instrument, key="b-private", ref_label="1 §", owner_tenant=self.b.tenant)
        response = self.list(obligation=private)
        self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))
        plain = library_build.obligation(self.law.instrument, key="lbf-plain", ref_label="8 kap. 1 §")
        self.assertEqual(self.list(obligation=plain).json(), {"items": [], "total": 0})
