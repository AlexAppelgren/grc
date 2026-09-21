"""A bank's own decision about a suggested obligation link (WAT-04, ruling C).

Two facts sit on top of each other here and the whole point is that they never merge: the
library's link, which an agent suggested and a library editor may one day confirm, and this
bank's decision about it. What is proved is that deciding writes a tenant row and no library
row, that `removed` is stored rather than deleted, that a second decision rewrites one row
instead of stacking another, and that another bank still sees the suggestion untouched.

Proven to fail 2026-09-21 by having `_decide` confirm the `change_obligation` row as well:
the library-untouched test named the row it had moved, and the other bank's read changed.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction
from django.test import TestCase

from apps.cases import creation, testing as case_build
from apps.cases.models import CaseLinkDecision, CaseObligationLink, ChangeCase
from apps.library import testing as library_build
from apps.shared import factories, outbox, tenancy
from apps.shared.audit import Actor, record
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.watch import testing as watch_build
from apps.watch.models import ChangeObligation, RegulatoryChange

V1 = "/api/v1"
SECURITIES = "regime:securities"
AML = "regime:aml"


def drain() -> None:
    with transaction.atomic():
        tenancy.clear_tenant()
    while outbox.deliver_batch().delivered:
        pass


def registered(change: RegulatoryChange) -> None:
    with transaction.atomic():
        tenancy.clear_tenant()
        record(
            action=creation.CHANGE_REGISTERED,
            actor=Actor.system("watch"),
            subject_type="regulatory_change",
            subject_id=change.id,
            subject_title=change.title,
            summary=f"Registered {change.title}.",
            tenant_id=None,
        )
    drain()


class CaseObligationLinkTests(ScenarioTestCase):
    def setUp(self) -> None:
        watch_build.seed_watch_reference()
        creation.register()
        self.banks = case_build.two_tenants_with_different_footprints(inside=SECURITIES, outside=AML)
        drain()
        self.officer = factories.member(
            self.banks.inside, roles=("compliance_officer",), user_row=factories.user(name="Sara Lind")
        ).user
        self.reader = factories.member(self.banks.inside, roles=("reader",)).user
        self.instrument = library_build.instrument(key="lvm", short_name="LVM", regime=SECURITIES)
        self.obligation = library_build.obligation(
            self.instrument, key="obl-research", titles={"en": "Assess the quality of investment research paid for"}
        )
        self.change = watch_build.change_with_timeline(terms=(SECURITIES,))
        self.link = watch_build.obligation_link(self.change, self.obligation, confidence=0.9)
        registered(self.change)

    def _accept(self, obligation_id: uuid.UUID | None = None, who: Any = None) -> Any:
        return self.client.post(
            f"{V1}/changes/{self.change.id}/case/obligation-links",
            data={"obligationId": str(obligation_id or self.obligation.id)},
            content_type="application/json",
            **sign_in(who or self.officer, tenant=self.banks.inside),
        )

    def _remove(self, obligation_id: uuid.UUID | None = None, who: Any = None) -> Any:
        return self.client.delete(
            f"{V1}/changes/{self.change.id}/case/obligation-links/{obligation_id or self.obligation.id}",
            **sign_in(who or self.officer, tenant=self.banks.inside),
        )

    def _decisions(self, tenant: Any) -> list[CaseObligationLink]:
        with transaction.atomic():
            tenancy.activate(tenant.id)
            return list(CaseObligationLink.objects.all())

    def test_accepting_stores_this_banks_decision_and_names_the_person(self) -> None:
        response = self._accept()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["decision"], "accepted")
        self.assertEqual(body["obligationId"], str(self.obligation.id))
        self.assertEqual(body["decidedByName"], "Sara Lind")
        self.assertEqual(body["instrumentShortName"], self.obligation.instrument.short_name)
        rows = self._decisions(self.banks.inside)
        self.assertEqual([(row.obligation_id, row.decision) for row in rows], [(self.obligation.id, "accepted")])

    def test_removing_stores_a_decision_and_deletes_nothing(self) -> None:
        response = self._remove()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["decision"], "removed")
        rows = self._decisions(self.banks.inside)
        self.assertEqual([row.decision for row in rows], [CaseLinkDecision.REMOVED.value])

    def test_a_second_decision_rewrites_one_row(self) -> None:
        self._accept()
        self._remove()
        self._accept()
        rows = self._decisions(self.banks.inside)
        self.assertEqual(len(rows), 1, "one decision per obligation per case")
        self.assertEqual(rows[0].decision, CaseLinkDecision.ACCEPTED.value)

    def test_no_library_row_is_written(self) -> None:
        with transaction.atomic():
            tenancy.clear_tenant()
            before = list(ChangeObligation.objects.values())
        self._accept()
        self._remove()
        with transaction.atomic():
            tenancy.clear_tenant()
            self.assertEqual(list(ChangeObligation.objects.values()), before)

    def test_another_bank_sees_the_suggestion_untouched(self) -> None:
        self._remove()
        self.assertEqual(self._decisions(self.banks.outside), [])
        with transaction.atomic():
            tenancy.clear_tenant()
            self.link.refresh_from_db()
            self.assertTrue(watch_build.is_a_suggestion(self.link))

    def test_each_decision_writes_an_audit_row_in_this_bank(self) -> None:
        self._accept()
        self._remove()
        with transaction.atomic():
            tenancy.activate(self.banks.inside.id)
            rows = list(AuditEvent.objects.filter(action="case.obligation_link_decided").order_by("created"))
            self.assertEqual([row.after["decision"] for row in rows], ["accepted", "removed"])
            self.assertEqual(rows[-1].before, {"decision": "accepted"})

    def test_an_obligation_the_library_does_not_hold_answers_404(self) -> None:
        response = self._accept(obligation_id=uuid.uuid4())
        self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))
        self.assertEqual(self._decisions(self.banks.inside), [])

    def test_a_reader_without_cases_work_is_refused(self) -> None:
        response = self._accept(who=self.reader)
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.json()["requiredPermission"], "cases.work")

    def test_a_change_this_bank_has_no_case_for_answers_404(self) -> None:
        response = self.client.post(
            f"{V1}/changes/{uuid.uuid4()}/case/obligation-links",
            data={"obligationId": str(self.obligation.id)},
            content_type="application/json",
            **sign_in(self.officer, tenant=self.banks.inside),
        )
        self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))


class CaseObligationLinkIsolationTests(TestCase):
    """The decision is one bank's row and no other bank's read changes because of it."""

    def test_a_decision_is_invisible_to_another_bank(self) -> None:
        watch_build.seed_watch_reference()
        creation.register()
        banks = case_build.two_tenants_with_different_footprints(inside=SECURITIES, outside=AML)
        drain()
        obligation = library_build.obligation(
            library_build.instrument(key="lvm", short_name="LVM", regime=SECURITIES),
            key="obl-research",
            titles={"en": "Assess the quality of investment research paid for"},
        )
        change = watch_build.change_with_timeline(terms=(SECURITIES,))
        watch_build.obligation_link(change, obligation, confidence=0.4)
        registered(change)
        with transaction.atomic():
            tenancy.activate(banks.inside.id)
            case = ChangeCase.objects.get(change=change)
        case_build.link_decision(case, obligation, decision=CaseLinkDecision.REMOVED)
        with transaction.atomic():
            tenancy.activate(banks.outside.id)
            self.assertEqual(list(CaseObligationLink.objects.all()), [])
