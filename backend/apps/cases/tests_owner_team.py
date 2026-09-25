"""A team beside the person who owns a case (CAS-02, TEN-03; `c9-owner-team-and-reassign`).

Triage may name one of the bank's active teams beside the owner, by its key: the case then
answers `ownerTeam` as `{key, kind, label}`, on the move and on the change page, and the
triage's audit row carries the key. A key that is not an active team of this bank, another
bank's included, is 422 `unknown_key` listing the valid keys and moves nothing. The database
refuses another bank's team on its own, through the composite key (tenant_id, owner_team_id).

Proven to fail 2026-09-25 before cases 0005: the body had no `ownerTeam` and the case none.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.cases.models import ChangeCase
from apps.cases.tests_models import CaseDatabaseTestCase
from apps.cases.tests_triage import CaseRoutes, triage_bank
from apps.shared import factories, tenancy
from apps.shared.testing import sign_in
from apps.taxonomy.models import Team


class TriageNamesATeam(CaseRoutes):
    def setUp(self) -> None:
        self.bank = triage_bank()
        self.team = factories.team(self.bank.tenant, key="cards", label="Cards compliance")

    def triage(self, **extra: object) -> Any:
        return self.move(self.bank, "triage", {"urgency": "act_now", "ownerId": str(self.bank.owner.id), **extra})

    def test_a_team_beside_the_owner_is_stored_answered_and_audited_by_key(self) -> None:
        response = self.triage(ownerTeam="cards")
        self.assertEqual(response.status_code, 200, response.content)
        case = response.json()
        self.assertEqual(case["ownerTeam"], {"key": "cards", "kind": None, "label": "Cards compliance"})
        self.assertEqual(case["owner"]["id"], str(self.bank.owner.id), "the team sits beside the person, never instead")
        self.assertEqual(self.case(self.bank).owner_team_id, self.team.id)
        self.assertEqual(self.moves_audited(self.bank)[0].after["ownerTeam"], "cards")

    def test_the_change_page_lists_the_team(self) -> None:
        self.assertEqual(self.triage(ownerTeam="cards").status_code, 200)
        page = self.client.get(f"/api/v1/changes/{self.bank.change_id}", **sign_in(self.bank.officer, tenant=self.bank.tenant))
        self.assertEqual(page.status_code, 200, page.content)
        self.assertEqual(page.json()["case"]["ownerTeam"]["key"], "cards")

    def test_no_team_is_null_and_audits_none(self) -> None:
        response = self.triage()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(response.json()["ownerTeam"])
        self.assertIsNone(self.case(self.bank).owner_team_id)
        self.assertNotIn("ownerTeam", self.moves_audited(self.bank)[0].after)

    def test_a_retired_unknown_or_other_banks_team_is_422_unknown_key_and_moves_nothing(self) -> None:
        other = factories.tenant()
        factories.team(other, key="treasury", label="Treasury")
        retired = factories.team(self.bank.tenant, key="old_desk", label="Old desk")
        with transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            Team.objects.filter(pk=retired.pk).update(active=False)
        for key in ("old_desk", "nobody", "treasury"):
            with self.subTest(team=key):
                body = self.assertProblem(self.triage(ownerTeam=key), 422, "unknown_key")
                self.assertIn("cards", body["validKeys"])
                self.assertNotIn(key, body["validKeys"])
        self.assertEqual(self.case(self.bank).status, "new")
        self.assertEqual(self.ledger(self.bank), [])


class OwnerTeamCompositeKey(CaseDatabaseTestCase):
    """The database refuses another bank's team on a case, whatever Python does."""

    def test_another_banks_team_is_refused_and_the_banks_own_is_kept(self) -> None:
        own = factories.team(self.tenant_a, key="legal", label="Legal")
        foreign = factories.team(self.tenant_b, key="legal", label="Legal")
        self.refused(
            lambda: ChangeCase.objects.using("app").filter(pk=self.case_a.pk).update(owner_team_id=foreign.id),
            "another bank's team",
        )
        with self.as_app():
            ChangeCase.objects.using("app").filter(pk=self.case_a.pk).update(owner_team_id=own.id)
        with self.as_app():
            self.assertEqual(ChangeCase.objects.using("app").get(pk=self.case_a.pk).owner_team_id, own.id)
