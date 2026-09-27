"""Out of office with a delegate (TEN-04, COL-02): `GET` and `PUT /me/out-of-office`.

A member sets the last day they are away and a delegate, on their own membership, and ends
it early by sending nulls. What is pinned here beside TEN-S4 in `tests_scenarios.py`:

- **The delegate needs the approve permission themself.** Every approve permission the
  absent person holds, the delegate must hold too, or 422 `delegate_cannot_approve`.
  Delegation routes notices and grants nothing: a delegate whose roles lack
  `cases.signoff` still gets 403 on the approval route.
- **One open absence.** A second while one is open answers 409 `already_delegated`.
- **The bank's own day.** The window is read on the bank's local date, stored as a plain
  date; a last day before the bank's today is refused.
- **Four eyes is unchanged.** A delegate who asked for sign-off is still refused.
- **The audit names both.** The write's row names the absent person as actor and the
  delegate; a delegate's approval names the absent approver it acted for.

Operations exercised: getMyOutOfOffice, putMyOutOfOffice, approveSignoff.
"""

from __future__ import annotations

import datetime
from typing import Any
from unittest import mock
from zoneinfo import ZoneInfo

from apps.cases import tests_signoff as signoff_build
from apps.identity.models import Membership, User
from apps.library.reading import today_for
from apps.shared import factories, tenancy
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in

V1 = "/api/v1"
URL = f"{V1}/me/out-of-office"


class OutOfOfficeTestCase(ScenarioTestCase):
    def setUp(self) -> None:
        self.tenant = factories.tenant(slug="away-bank", timezone="Europe/Helsinki")
        self.approver = factories.member_user(self.tenant, roles=("approver",))
        self.second_approver = factories.member_user(self.tenant, roles=("approver",))
        self.officer = factories.member_user(self.tenant, roles=("compliance_officer",))
        self.reader = factories.member_user(self.tenant, roles=("reader",))

    @property
    def today(self) -> datetime.date:
        return today_for(self.tenant)

    def put(self, who: User, until: datetime.date | None, delegate: User | None | str) -> Any:
        body = {
            "untilDate": until.isoformat() if until else None,
            "delegateId": delegate if isinstance(delegate, str) or delegate is None else str(delegate.id),
        }
        return self.client.put(URL, data=body, content_type="application/json", **sign_in(who, tenant=self.tenant))

    def membership(self, who: User) -> Membership:
        self.activate(self.tenant)
        return Membership.objects.get(tenant=self.tenant, user=who)

    def events(self) -> list[AuditEvent]:
        self.activate(self.tenant)
        return list(AuditEvent.objects.filter(tenant=self.tenant, subject_type="membership").order_by("created", "id"))


class ReadAndSet(OutOfOfficeTestCase):
    def test_nobody_away_reads_nulls(self) -> None:
        response = self.client.get(URL, **sign_in(self.approver, tenant=self.tenant))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {"untilDate": None, "delegate": None, "away": False})

    def test_setting_a_window_stores_it_reads_it_back_and_audits_both_people(self) -> None:
        until = self.today + datetime.timedelta(days=7)
        response = self.put(self.approver, until, self.second_approver)
        self.assertEqual(response.status_code, 200, response.content)
        expected = {
            "untilDate": until.isoformat(),
            "delegate": {"id": str(self.second_approver.id), "name": self.second_approver.name},
            "away": True,
        }
        self.assertEqual(response.json(), expected)
        self.assertEqual(self.client.get(URL, **sign_in(self.approver, tenant=self.tenant)).json(), expected)
        membership = self.membership(self.approver)
        self.assertEqual((membership.out_of_office_until, membership.delegate_id), (until, self.second_approver.id))
        [event] = self.events()
        self.assertEqual(event.action, "out_of_office.set")
        self.assertEqual((event.actor_id, event.subject_id), (self.approver.id, membership.id))
        self.assertEqual(event.before, {"untilDate": None, "delegateId": None})
        self.assertEqual(event.after, {"untilDate": until.isoformat(), "delegateId": str(self.second_approver.id)})
        self.assertIn(self.approver.name, event.summary)
        self.assertIn(self.second_approver.name, event.summary)

    def test_ending_early_clears_the_window_and_a_new_one_may_follow(self) -> None:
        until = self.today + datetime.timedelta(days=3)
        self.put(self.approver, until, self.second_approver)
        response = self.put(self.approver, None, None)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {"untilDate": None, "delegate": None, "away": False})
        membership = self.membership(self.approver)
        self.assertEqual((membership.out_of_office_until, membership.delegate_id), (None, None))
        ended = self.events()[-1]
        self.assertEqual(ended.action, "out_of_office.ended")
        self.assertEqual(ended.before, {"untilDate": until.isoformat(), "delegateId": str(self.second_approver.id)})
        self.assertEqual(ended.after, {"untilDate": None, "delegateId": None})
        self.assertEqual(self.put(self.approver, self.today, self.second_approver).status_code, 200)

    def test_a_member_who_holds_no_approve_permission_may_name_any_member(self) -> None:
        response = self.put(self.reader, self.today, self.officer)
        self.assertEqual(response.status_code, 200, response.content)

    def test_a_window_that_closed_before_today_no_longer_counts_as_open(self) -> None:
        self.activate(self.tenant)
        Membership.objects.filter(user=self.approver).update(
            out_of_office_until=self.today - datetime.timedelta(days=1), delegate=self.second_approver
        )
        self.assertFalse(self.client.get(URL, **sign_in(self.approver, tenant=self.tenant)).json()["away"])
        self.assertEqual(self.put(self.approver, self.today, self.second_approver).status_code, 200)


class Refusals(OutOfOfficeTestCase):
    def assert_refused(self, response: Any, status: int, code: str) -> None:
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response.json()["code"], code)
        membership = self.membership(self.approver)
        self.assertEqual((membership.out_of_office_until, membership.delegate_id), (None, None))
        self.assertEqual(self.events(), [])

    def test_a_delegate_without_the_absent_persons_approve_permission_is_refused(self) -> None:
        # The compliance officer lacks `cases.signoff`, which the approver holds.
        self.assert_refused(self.put(self.approver, self.today, self.officer), 422, "delegate_cannot_approve")
        self.assert_refused(self.put(self.approver, self.today, self.reader), 422, "delegate_cannot_approve")

    def test_a_second_open_absence_is_refused(self) -> None:
        self.put(self.approver, self.today + datetime.timedelta(days=2), self.second_approver)
        before = self.events()
        response = self.put(self.approver, self.today + datetime.timedelta(days=9), self.second_approver)
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["code"], "already_delegated")
        self.assertEqual(self.membership(self.approver).out_of_office_until, self.today + datetime.timedelta(days=2))
        self.assertEqual(self.events(), before)

    def test_the_delegate_must_be_another_active_member_of_the_bank(self) -> None:
        other_bank = factories.tenant(slug="away-other")
        stranger = factories.member_user(other_bank, roles=("approver",))
        leaver = factories.member_user(self.tenant, roles=("approver",))
        self.activate(self.tenant)
        Membership.objects.filter(user=leaver).update(deactivated_at=datetime.datetime.now(datetime.UTC))
        for delegate in (self.approver, stranger, leaver, "00000000-0000-0000-0000-000000000000"):
            with self.subTest(delegate=delegate):
                response = self.put(self.approver, self.today, delegate)
                self.assert_refused(response, 422, "validation_error")
                self.assertEqual(response.json()["errors"][0]["field"], "delegateId")

    def test_a_date_and_a_delegate_come_together(self) -> None:
        self.assert_refused(self.put(self.approver, self.today, None), 422, "validation_error")
        self.assert_refused(self.put(self.approver, None, self.second_approver), 422, "validation_error")

    def test_the_last_day_is_read_on_the_banks_date_and_cannot_be_past(self) -> None:
        # 23:30 UTC on 10 March is already 11 March in Helsinki: the bank's today.
        moment = datetime.datetime(2027, 3, 10, 23, 30, tzinfo=datetime.UTC)
        self.assertEqual(moment.astimezone(ZoneInfo("Europe/Helsinki")).date(), datetime.date(2027, 3, 11))
        with mock.patch("django.utils.timezone.now", return_value=moment):
            self.assert_refused(self.put(self.approver, datetime.date(2027, 3, 10), self.second_approver), 422, "validation_error")
            response = self.put(self.approver, datetime.date(2027, 3, 11), self.second_approver)
            self.assertEqual(response.status_code, 200, response.content)
            self.assertTrue(response.json()["away"])

    def test_the_body_takes_the_two_fields_and_nothing_else(self) -> None:
        headers = sign_in(self.approver, tenant=self.tenant)
        for body in (
            {"untilDate": self.today.isoformat(), "delegateId": str(self.second_approver.id), "grant": "cases.signoff"},
            {"untilDate": "next friday", "delegateId": str(self.second_approver.id)},
            {"untilDate": self.today.isoformat()},
        ):
            with self.subTest(body=body):
                response = self.client.put(URL, data=body, content_type="application/json", **headers)
                self.assert_refused(response, 422, "validation_error")

    def test_without_a_session_both_routes_answer_401(self) -> None:
        self.assertEqual(self.client.get(URL).status_code, 401)
        self.assertEqual(self.client.put(URL, data={}, content_type="application/json").status_code, 401)


class SignoffWhileAway(ScenarioTestCase):
    """The sign-off route with a delegate: it grants nothing and four eyes stands."""

    def setUp(self) -> None:
        self.bank = signoff_build.Bank()
        self.today = today_for(self.bank.tenant)

    def away(self, absent: User, delegate: User, *, until: datetime.date | None = None) -> None:
        tenancy.activate(self.bank.tenant.id)
        Membership.objects.filter(user=absent).update(out_of_office_until=until or self.today, delegate=delegate)

    def approval(self) -> AuditEvent:
        tenancy.activate(self.bank.tenant.id)
        return AuditEvent.objects.filter(subject_id=self.bank.case.id, after__status="closed").get()

    def test_a_delegate_who_is_the_requester_is_still_refused(self) -> None:
        # The owner holds `cases.signoff` and asked for sign-off; the approver names them.
        self.away(self.bank.approver, self.bank.owner)
        self.bank.ready_for_signoff(self.client)
        response = self.bank.post(self.client, "approve", self.bank.owner, step_up=True)
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["code"], "four_eyes_violation")
        self.assertEqual(self.bank.fresh().status, "signoff")

    def test_a_delegate_whose_roles_lack_signoff_still_gets_403(self) -> None:
        # Set past the route's own check, as if the delegate's roles changed afterwards.
        self.away(self.bank.approver, self.bank.reader)
        self.bank.ready_for_signoff(self.client)
        response = self.bank.post(self.client, "approve", self.bank.reader, step_up=True)
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.json()["requiredPermission"], "cases.signoff")

    def test_a_delegates_approval_names_the_absent_approver(self) -> None:
        delegate = factories.member_user(self.bank.tenant, roles=("approver",))
        self.away(self.bank.approver, delegate)
        self.bank.ready_for_signoff(self.client)
        response = self.bank.post(self.client, "approve", delegate, step_up=True)
        self.assertEqual(response.status_code, 200, response.content)
        event = self.approval()
        self.assertEqual(event.actor_id, delegate.id)
        self.assertEqual(event.after["onBehalfOf"], [str(self.bank.approver.id)])

    def test_an_approval_outside_any_window_names_nobody_else(self) -> None:
        back = factories.member_user(self.bank.tenant, roles=("approver",))
        self.away(back, self.bank.approver, until=self.today - datetime.timedelta(days=1))
        self.bank.ready_for_signoff(self.client)
        self.assertEqual(self.bank.post(self.client, "approve", self.bank.approver, step_up=True).status_code, 200)
        self.assertNotIn("onBehalfOf", self.approval().after)
