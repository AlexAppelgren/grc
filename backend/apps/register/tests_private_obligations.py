"""The register decides the bank's own obligations as it decides shared ones (OWN-04, REG-01,
REG-02, INV-07; D-57, D-75, ADR 0059; d89-private-records).

An obligation the bank keeps as its own takes applicability per legal entity from one person
holding `applicability.approve`, with no second approver and no step-up, and its compliance
status per entity as a separate fact, both audited in the bank's zone. Another bank is
answered 404 for it, and an agent access credential never reads it, decided or not.
"""

from __future__ import annotations

from typing import Any

from apps.library import testing as library_testing
from apps.library.models import Obligation
from apps.register.models import Applicability, TenantObligation, TenantObligationScope
from apps.register.tests_agent_read import ENTRIES, ReadWorld
from apps.shared import factories, tenancy
from apps.shared.models import AuditEvent
from apps.shared.testing import sign_in
from django.test import TestCase

V1 = "/api/v1"


class TheBanksOwnObligationInTheRegister(TestCase):
    world: ReadWorld
    own: Obligation

    @classmethod
    def setUpTestData(cls) -> None:
        cls.world = ReadWorld(slug="own-register")
        act = library_testing.instrument(key="own-register-act-2", regime="regime:securities", owner_tenant=cls.world.tenant)
        cls.own = library_testing.obligation(act, key="own-register-duty-2", owner_tenant=cls.world.tenant)

    def officer(self) -> dict[str, Any]:
        return sign_in(self.world.officer, tenant=self.world.tenant)

    def answer(self, body: dict[str, Any], headers: dict[str, Any], if_match: int = 0) -> Any:
        return self.client.put(
            f"{V1}/obligations/{self.own.id}/applicability",
            data=body,
            content_type="application/json",
            HTTP_IF_MATCH=f'"{if_match}"',
            **headers,
        )

    def status(self, entity: Any, body: dict[str, Any], version: int, headers: dict[str, Any]) -> Any:
        return self.client.patch(
            f"{V1}/obligations/{self.own.id}/register/entities/{entity.id}",
            data=body,
            content_type="application/json",
            HTTP_IF_MATCH=f'"{version}"',
            **headers,
        )

    def test_applicability_and_status_are_set_per_legal_entity_as_two_facts(self) -> None:
        officer = self.officer()
        applied = self.answer({"orgUnitId": str(self.world.parent.id), "applicability": "applies", "reason": "Our own branch rule"}, officer)
        self.assertEqual(applied.status_code, 200, applied.content)
        tenancy.activate(self.world.tenant.id)
        scope = TenantObligationScope.objects.get(tenant_obligation__obligation=self.own, org_unit=self.world.parent)
        self.assertEqual((scope.applicability, scope.applicability_decided_by_id), (Applicability.APPLIES.value, self.world.officer.id))
        self.assertEqual(scope.compliance_status.key, "not_assessed", "applies is not we comply")
        event = AuditEvent.objects.get(action="register.applicability_set", subject_id=scope.tenant_obligation_id)
        self.assertEqual((event.tenant_id, event.step_up_assertion_id), (self.world.tenant.id, None))

        stated = self.status(self.world.parent, {"complianceStatus": "compliant"}, scope.version, officer)
        self.assertEqual(stated.status_code, 200, stated.content)
        tenancy.activate(self.world.tenant.id)
        scope.refresh_from_db()
        self.assertEqual((scope.applicability, scope.compliance_status.key), (Applicability.APPLIES.value, "compliant"))

    def test_another_bank_is_answered_404_and_stores_nothing(self) -> None:
        other = factories.tenant(slug="own-register-b")
        headers = sign_in(factories.member_user(other, roles=("compliance_officer",)), tenant=other)
        refused = self.answer({"applicability": "applies", "reason": "Not ours"}, headers)
        self.assertEqual((refused.status_code, refused.json()["code"]), (404, "not_found"))
        read = self.client.get(f"{V1}/obligations/{self.own.id}/register", **headers)
        self.assertEqual((read.status_code, read.json()["code"]), (404, "not_found"))
        tenancy.activate(other.id)
        self.assertFalse(TenantObligation.objects.exists())

    def test_an_agent_access_credential_never_reads_it_decided_or_not(self) -> None:
        """`world.private` is decided in full by the world; `own` is not decided at all."""
        key = {"HTTP_X_API_KEY": self.world.general_key}
        listed = self.client.get(f"{ENTRIES}?limit=100", **key)
        self.assertEqual(listed.status_code, 200, listed.content)
        for obligation in (self.world.private, self.own):
            self.assertNotIn(str(obligation.id), listed.content.decode())
            single = self.client.get(f"{ENTRIES}/{obligation.id}", **key)
            self.assertEqual((single.status_code, single.json()["code"]), (404, "not_found"))
