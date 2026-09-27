"""The bank's own records as the library reads show them (INV-07, OWN-04, TEN-06; D-57, ADR
0042, ADR 0059; d89-private-records).

A person of the bank reads its own instrument and obligation beside the shared library,
marked "Private to us". Another bank and the console never read them. A support session,
platform support reading the bank under a grant the bank approved, reads the shared library
and nothing the bank keeps as its own: each list leaves the record out and each address of it
answers the 404 of a record that does not exist (`reading.Reader.shared_only`).
"""

from __future__ import annotations

from typing import Any

from django.test import TestCase

from apps.identity.models import User
from apps.library import reading, testing as build
from apps.library.models import Instrument, Obligation
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, tenancy
from apps.shared.models import Tenant
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.testing import sign_in
from apps.shared.tests_support_session import grant
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms

V1 = "/api/v1"


class PrivateReads(TestCase):
    bank: Tenant
    other_bank: Tenant
    officer: User
    other_officer: User
    shared_act: Instrument
    shared: Obligation
    own_act: Instrument
    own: Obligation

    @classmethod
    def setUpTestData(cls) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_taxonomy_terms()
        cls.bank = factories.tenant(slug="reads-a")
        cls.other_bank = factories.tenant(slug="reads-b")
        cls.officer = factories.member_user(cls.bank, roles=("compliance_officer",))
        cls.other_officer = factories.member_user(cls.other_bank, roles=("compliance_officer",))
        cls.shared_act = build.instrument(key="reads-shared-act", regime="regime:securities")
        cls.shared = build.obligation(cls.shared_act, key="reads-shared-duty")
        cls.own_act = build.instrument(key="reads-own-act", regime="regime:securities", owner_tenant=cls.bank)
        cls.own = build.obligation(cls.own_act, key="reads-own-duty", owner_tenant=cls.bank)
        tenancy.clear_tenant()

    def support_session(self) -> dict[str, Any]:
        platform = factories.platform_user()
        row = grant(self.bank, platform, factories.member_user(self.bank, roles=("admin",)))
        entered = self.client.post(f"{V1}/console/support-access/{row.id}/enter", **sign_in(platform, tenant=None, step_up=True))
        self.assertEqual(entered.status_code, 200, entered.content)
        return {"HTTP_AUTHORIZATION": f"Bearer {entered.json()['accessToken']}"}

    def ids(self, path: str, headers: dict[str, Any]) -> set[str]:
        response = self.client.get(f"{V1}{path}?footprint=all&limit=100", **headers)
        self.assertEqual(response.status_code, 200, response.content)
        return {row["id"] for row in response.json()["items"]}

    def status(self, path: str, headers: dict[str, Any]) -> tuple[int, str | None]:
        response = self.client.get(f"{V1}{path}", **headers)
        return response.status_code, response.json().get("code")

    def test_the_bank_reads_its_own_beside_the_shared_library_marked_private(self) -> None:
        officer = sign_in(self.officer, tenant=self.bank)
        self.assertLessEqual({str(self.shared.id), str(self.own.id)}, self.ids("/obligations", officer))
        self.assertLessEqual({str(self.shared_act.id), str(self.own_act.id)}, self.ids("/instruments", officer))
        card = self.client.get(f"{V1}/obligations/{self.own.id}", **officer).json()
        self.assertTrue(card["privateToUs"])
        self.assertTrue(self.client.get(f"{V1}/instruments/{self.own_act.id}", **officer).json()["privateToUs"])
        self.assertFalse(self.client.get(f"{V1}/obligations/{self.shared.id}", **officer).json()["privateToUs"])

    def test_a_support_session_reads_the_shared_library_and_none_of_the_bank_s_own(self) -> None:
        support = self.support_session()
        obligations, instruments = self.ids("/obligations", support), self.ids("/instruments", support)
        self.assertIn(str(self.shared.id), obligations)
        self.assertIn(str(self.shared_act.id), instruments)
        self.assertNotIn(str(self.own.id), obligations)
        self.assertNotIn(str(self.own_act.id), instruments)
        for path in (
            f"/obligations/{self.own.id}",
            f"/obligations/{self.own.id}/diff",
            f"/obligations/{self.own.id}/sources",
            f"/instruments/{self.own_act.id}",
            f"/instruments/{self.own_act.id}/provisions",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.status(path, support), (404, "not_found"))
        self.assertEqual(self.status(f"/obligations/{self.shared.id}", support)[0], 200)

    def test_another_bank_reads_neither(self) -> None:
        other = sign_in(self.other_officer, tenant=self.other_bank)
        self.assertNotIn(str(self.own.id), self.ids("/obligations", other))
        self.assertEqual(self.status(f"/obligations/{self.own.id}", other), (404, "not_found"))
        self.assertEqual(self.status(f"/instruments/{self.own_act.id}", other), (404, "not_found"))


class WhoReadsSharedOnly(TestCase):
    def test_a_support_session_and_an_agent_access_credential_read_shared_records_only(self) -> None:
        bank = factories.tenant(slug="reads-who")
        support = Principal(kind=PrincipalKind.USER, subject_id=factories.platform_user().id, tenant_id=bank.id, support_access_id=bank.id)
        self.assertEqual(reading.reader_of(support), reading.SHARED_ONLY)
        person = Principal(kind=PrincipalKind.USER, subject_id=factories.member_user(bank, roles=("reader",)).id, tenant_id=bank.id)
        self.assertEqual(reading.reader_of(person), reading.OPEN)
        self.assertFalse(reading.OPEN.shared_only)
