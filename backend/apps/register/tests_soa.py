"""The Statement of Applicability (`soa.py`; REG-08, REG-S15, D-41, D-42, FP-03).

The register filtered by a standard and one legal entity, proved through the route: the
entity's conformance row with its own assessed status, and each live unit by reference with
the bank's title, its answer and reason, its status, who set it and when, and its history of
decisions. No status is computed from the units. A standard outside the bank's regulatory
scope is hidden and nothing is deleted; an entity that does not follow the standard has no
statement; another bank reaches none of it; the read costs the same for more units.

Written before the logic: every route test failed on the 501 `not_built` the stub answered."""

from __future__ import annotations

from typing import Any

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.library.reading import obligation_scopes
from apps.register.models import Applicability, SoaUnit, TenantObligationScope
from apps.register import tests_units
from apps.shared import factories
from apps.shared import permissions as perms
from apps.shared.testing import user_principal
from apps.taxonomy.models import ComplianceStatus, FootprintTerm


class StatementOfApplicability(tests_units.UnitWorld):
    def setUp(self) -> None:
        super().setUp()
        self.activate(self.tenant)
        self.in_scope = [
            FootprintTerm.objects.create(tenant=self.tenant, term=term)
            for terms in obligation_scopes([self.standard.id])[self.standard.id].values()
            for term in terms
        ]

    def _statement(self, entity: Any = None, *, query: str = "", who: Any = None) -> Any:
        entity_id = (entity or self.bank_ab).id
        return self._call("GET", f"/obligations/{self.standard.id}/statement-of-applicability?entity={entity_id}{query}", who=who)

    def _decide(self, unit: SoaUnit, value: str, reason: str, version: int) -> None:
        body = {"unitId": str(unit.id), "applicability": value, "reason": reason}
        response = self._call("PUT", f"/obligations/{self.standard.id}/applicability", body, version=version, who=self.decider)
        self.assertEqual(response.status_code, 200, response.content)

    def test_each_unit_shows_its_decision_status_who_when_and_history(self) -> None:
        second, first = self._unit("X.2"), self._unit("X.1")
        self._decide(first, "applies", "In the certificate", 1)
        self._decide(first, "not_applicable", "Outsourced to the group", 2)
        response = self._statement()
        self.assertEqual(response.status_code, 200, response.content)
        statement = response.json()
        self.assertEqual((statement["obligationId"], statement["total"]), (str(self.standard.id), 2))
        x1, x2 = statement["units"]
        self.assertEqual(
            {k: x1[k] for k in ("id", "reference", "title", "applicability", "applicabilityReason", "applicabilityDecidedBy")},
            {
                "id": str(first.id),
                "reference": "X.1",
                "title": "Our access rules",
                "applicability": "not_applicable",
                "applicabilityReason": "Outsourced to the group",
                "applicabilityDecidedBy": {"id": str(self.officer.id), "name": self.officer.name},
            },
        )
        self.assertIsNotNone(x1["applicabilityDecidedAt"])
        self.assertEqual(x1["complianceStatus"]["kind"], "not_assessed")
        self.assertEqual(
            [(row["applicability"], row["reason"], row["decidedBy"]["id"]) for row in x1["history"]],
            [("applies", "In the certificate", str(self.officer.id)), ("not_applicable", "Outsourced to the group", str(self.officer.id))],
        )
        self.assertLessEqual(x1["history"][0]["decidedAt"], x1["history"][1]["decidedAt"])
        self.assertEqual((x2["id"], x2["history"], x2["applicabilityDecidedAt"]), (str(second.id), [], None))

    def test_the_conformance_row_keeps_its_own_status_and_none_is_computed_from_the_units(self) -> None:
        unit = self._unit("X.1")
        self._decide(unit, "applies", "In the certificate", 1)
        self.activate(self.tenant)
        SoaUnit.objects.filter(pk=unit.pk).update(compliance_status=ComplianceStatus.objects.get(key="gap"))
        conformance = self._statement().json()["conformance"]
        self.assertEqual(
            {k: conformance[k] for k in ("orgUnitId", "applicability", "applicabilityReason")},
            {"orgUnitId": str(self.bank_ab.id), "applicability": "applies", "applicabilityReason": "Certified"},
        )
        self.assertEqual(conformance["complianceStatus"]["key"], self.status.key, "a unit's gap status never reaches the conformance row")
        self.activate(self.tenant)
        self.bank_ab_scope.refresh_from_db()
        self.assertEqual(self.bank_ab_scope.compliance_status_id, self.status.id)

    def test_a_standard_outside_the_regulatory_scope_is_hidden_and_nothing_is_deleted(self) -> None:
        unit = self._unit("X.1")
        self.activate(self.tenant)
        FootprintTerm.objects.filter(pk__in=[row.pk for row in self.in_scope if row.term.dimension.key == "standard"]).delete()
        self._problem(self._statement(), 404, "not_found")
        self.activate(self.tenant)
        self.assertTrue(SoaUnit.objects.filter(pk=unit.pk, removed_at__isnull=True).exists())
        FootprintTerm.objects.create(tenant=self.tenant, term=next(row.term for row in self.in_scope if row.term.dimension.key == "standard"))
        self.assertEqual([row["id"] for row in self._statement().json()["units"]], [str(unit.id)])

    def test_there_is_no_statement_where_a_unit_could_not_exist(self) -> None:
        refusals = [
            (self._statement(self.liv), 422, "scope_not_applicable"),
            (self._statement(self.finance), 422, "scope_not_applicable"),
            (self._call("GET", f"/obligations/{self.not_a_standard.id}/statement-of-applicability?entity={self.bank_ab.id}"), 422, "units_only_under_standards"),
            (self._call("GET", f"/obligations/{self.standard.id}/statement-of-applicability"), 422, "validation_error"),
        ]
        for response, status, code in refusals:
            with self.subTest(code=code):
                self._problem(response, status, code)

    def test_an_entity_that_stops_following_keeps_its_units_hidden_not_deleted(self) -> None:
        unit = self._unit("X.1")
        self.activate(self.tenant)
        TenantObligationScope.objects.filter(pk=self.bank_ab_scope.pk).update(applicability=Applicability.DOES_NOT_APPLY.value)
        self._problem(self._statement(), 422, "scope_not_applicable")
        TenantObligationScope.objects.filter(pk=self.bank_ab_scope.pk).update(applicability=Applicability.APPLIES.value, applicability_decided_at=timezone.now())
        self.assertEqual([row["id"] for row in self._statement().json()["units"]], [str(unit.id)])

    def test_another_bank_reaches_none_of_it(self) -> None:
        self._unit("X.1")
        other = factories.tenant(slug="soa-other")
        person = factories.member_user(other, roles=("compliance_officer",))
        who = user_principal(permissions={perms.REGISTER_READ}, tenant_id=other.id, subject_id=person.id)
        self._problem(self._statement(who=who), 404, "not_found")

    def test_the_read_needs_register_read(self) -> None:
        who = user_principal(permissions={perms.CASES_READ}, tenant_id=self.tenant.id, subject_id=self.officer.id)
        response = self._statement(who=who)
        self._problem(response, 403, "permission_denied")
        self.assertEqual(response.json()["requiredPermission"], perms.REGISTER_READ)

    def test_the_statement_is_paged_by_reference_and_costs_the_same_for_more_units(self) -> None:
        first = self._unit("X.2")
        self._decide(first, "applies", "Certified", 1)
        with CaptureQueriesContext(connection) as one:
            self.assertEqual(self._statement().status_code, 200)
        for reference in ("X.3", "X.1", "X.4"):
            self._decide(self._unit(reference), "applies", "Certified", 1)
        with CaptureQueriesContext(connection) as four:
            page = self._statement(query="&limit=3&offset=0").json()
        self.assertEqual(len(four.captured_queries), len(one.captured_queries))
        self.assertEqual(([row["reference"] for row in page["units"]], page["total"]), (["X.1", "X.2", "X.3"], 4))
