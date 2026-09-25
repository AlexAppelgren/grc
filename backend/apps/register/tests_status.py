"""Compliance status on the register entry and per legal entity (REG-02, TEN-03;
`c8-reg-status`): a read creates nothing, every write goes through `ensure_register_entry()`
and `record()` with `If-Match`, a status needs "applies" first, every status change leaves an
assessment row, and the obligation's pill is the worst of its entities by category.

Written before `status_logic.py` was filled: every route test failed with 501 `not_built` and
the worst-of tests with an import error."""

from __future__ import annotations

import json
import uuid
from typing import Any

from django.db import connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.identity.models import Membership
from apps.library import testing as library_testing
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.register import status_logic
from apps.register.models import Applicability, ComplianceAssessment, TenantObligation, TenantObligationScope
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.models import AuditEvent
from apps.shared.testing import SESSION_TOKEN_FOR_TESTS, stub_session, user_principal
from apps.taxonomy.models import ComplianceCategory, ComplianceStatus, RiskRating
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms
from apps.tenants.models import OrgUnit, OrgUnitKind

AS_SESSION: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"}
NOTE = "Reconciliation runs daily; the evidence log is still manual."


def seed_library() -> None:
    seed_languages()
    seed_jurisdictions()
    seed_library_vocabularies()
    seed_taxonomy_terms()


class RegisterStatusCase(TestCase):
    """One bank with three legal entities, an owner, a contact and a shared obligation."""

    tenant: Any
    owner: Any
    contact: Any
    obligation: Any
    entities: list[Any]

    @classmethod
    def setUpTestData(cls) -> None:
        seed_library()
        act = library_testing.instrument(key="status-act", regime="regime:securities")
        cls.obligation = library_testing.obligation(act, key="status-duty", titles={"en": "Keep client assets apart"})
        cls.tenant = factories.tenant(slug="status-a")
        cls.owner = factories.member_user(cls.tenant, roles=("compliance_officer",))
        cls.contact = factories.member_user(cls.tenant, roles=("compliance_officer",))
        with transaction.atomic():
            tenancy.activate(cls.tenant.id)
            cls.entities = [
                OrgUnit.objects.create(tenant=cls.tenant, kind=OrgUnitKind.LEGAL_ENTITY.value, name=name)
                for name in ("Example Bank AB", "Example Finance AB", "Example Liv AB")
            ]

    # --- helpers -------------------------------------------------------------------------
    def who(self, tenant: Any = None, person: Any = None) -> Any:
        tenant = tenant or self.tenant
        return user_principal(
            permissions={perms.REGISTER_READ, perms.REGISTER_EDIT}, tenant_id=tenant.id, subject_id=(person or self.owner).id
        )

    def url(self, entity: Any = None) -> str:
        base = f"/api/v1/obligations/{self.obligation.id}/register"
        return base if entity is None else f"{base}/entities/{entity.id}"

    def get(self, tenant: Any = None) -> Any:
        with stub_session(self.who(tenant)):
            return self.client.get(self.url(), **AS_SESSION)

    def patch(self, body: dict[str, Any], version: int | None, entity: Any = None, tenant: Any = None) -> Any:
        headers = dict(AS_SESSION)
        if version is not None:
            headers["HTTP_IF_MATCH"] = f'"{version}"'
        with stub_session(self.who(tenant)):
            return self.client.patch(self.url(entity), data=body, content_type="application/json", **headers)

    def entry(self, applicability: Applicability = Applicability.APPLIES) -> TenantObligation:
        """The entry as the applicability route leaves it (c8-reg-applicability's)."""
        tenancy.activate(self.tenant.id)
        with transaction.atomic():
            row = status_logic.ensure_register_entry(
                tenant_id=self.tenant.id, obligation_id=self.obligation.id, actor=factories.user_actor(user_id=self.owner.id)
            )
        TenantObligation.objects.filter(pk=row.pk).update(applicability=applicability.value)
        return TenantObligation.objects.get(pk=row.pk)

    def scope(self, entity: Any, applicability: Applicability = Applicability.APPLIES) -> TenantObligationScope:
        entry = self.entry() if not TenantObligation.objects.filter(obligation=self.obligation).exists() else TenantObligation.objects.get()
        return TenantObligationScope.objects.create(
            tenant=self.tenant,
            tenant_obligation=entry,
            org_unit=entity,
            applicability=applicability.value,
            compliance_status=ComplianceStatus.objects.get(is_default=True),
        )

    def counts(self) -> tuple[int, int, int, int]:
        tenancy.activate(self.tenant.id)
        return (
            TenantObligation.objects.count(),
            TenantObligationScope.objects.count(),
            ComplianceAssessment.objects.count(),
            AuditEvent.objects.count(),
        )


class ReadingCreatesNothing(RegisterStatusCase):
    def test_an_unanswered_obligation_reads_as_defaults_at_version_0_and_writes_nothing(self) -> None:
        before = self.counts()
        response = self.get()
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["version"], 0)
        self.assertIsNone(body["updatedAt"])
        self.assertEqual(body["applicability"], "under_assessment")
        self.assertEqual(body["complianceStatus"]["kind"], ComplianceCategory.NOT_ASSESSED.value)
        self.assertEqual(body["entities"], [])
        self.assertIsNone(body["ownerTeam"])
        self.assertEqual(self.counts(), before)

    def test_reading_an_obligation_with_three_entity_rows_writes_no_row(self) -> None:
        for entity in self.entities:
            self.scope(entity)
        before = self.counts()
        self.assertEqual(len(self.get().json()["entities"]), 3)
        self.assertEqual(self.counts(), before)

    def test_an_obligation_the_bank_cannot_see_is_404(self) -> None:
        other = factories.tenant(slug="status-private")
        act = library_testing.instrument(key="their-own", regime="regime:securities", owner_tenant=other)
        private = library_testing.obligation(act, key="their-duty", owner_tenant=other)
        for obligation_id in (private.id, uuid.uuid4()):
            with self.subTest(obligation=obligation_id), stub_session(self.who()):
                response = self.client.get(f"/api/v1/obligations/{obligation_id}/register", **AS_SESSION)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json()["code"], "not_found")

    def test_the_query_counts_do_not_grow_with_the_entities(self) -> None:
        self.entry()
        self.assertEqual(self.patch({"ownerTeam": "compliance", "riskRating": "high"}, 1).status_code, 200)
        self.scope(self.entities[0])

        def queries(version: int) -> tuple[int, int]:
            with CaptureQueriesContext(connection) as read:
                self.assertEqual(self.get().status_code, 200)
            with CaptureQueriesContext(connection) as write:
                self.assertEqual(self.patch({"process": f"Reconciliation {version}"}, version).status_code, 200)
            return len(read), len(write)

        one = queries(2)
        for entity in self.entities[1:]:
            self.scope(entity)
        self.assertEqual(queries(3), one)
        self.assertLessEqual(one[0], 12, "the register read is a fixed handful of queries")


class WritingTheEntry(RegisterStatusCase):
    def test_a_first_write_creates_the_entry_through_ensure_register_entry_and_audits_both(self) -> None:
        response = self.patch({"process": "Client asset reconciliation", "firstLineOwnerId": str(self.owner.id)}, 0)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["process"], "Client asset reconciliation")
        self.assertEqual(body["firstLineOwner"], {"id": str(self.owner.id), "name": self.owner.name})
        self.assertEqual(self.get().json()["version"], body["version"])
        actions = sorted(AuditEvent.objects.filter(action__startswith="register.").values_list("action", flat=True))
        self.assertEqual(actions, sorted(["register.entry_created", status_logic.ENTRY_UPDATED]))

    def test_every_field_is_stored_and_read_back(self) -> None:
        self.entry()
        body = {
            "complianceStatus": "partly_compliant",
            "statusNote": NOTE,
            "riskRating": "medium",
            "firstLineOwnerId": str(self.owner.id),
            "complianceContactId": str(self.contact.id),
            "ownerTeam": "compliance",
            "process": "Client asset reconciliation",
            "system": "Custody ledger",
            "evidenceLocation": "Compliance share / Client assets / 2026",
            "nextReviewDate": "2027-03-31",
            "rationale": "Second-line review found the manual log.",
        }
        response = self.patch(body, 1)
        self.assertEqual(response.status_code, 200, response.content)
        read = self.get().json()
        self.assertEqual(read["complianceStatus"]["key"], "partly_compliant")
        self.assertEqual(read["complianceStatus"]["kind"], "partly")
        self.assertEqual(read["complianceStatus"]["label"], "Partly compliant")
        self.assertEqual(read["riskRating"]["key"], "medium")
        self.assertEqual(read["ownerTeam"]["key"], "compliance")
        self.assertEqual(read["complianceContact"]["id"], str(self.contact.id))
        self.assertEqual(read["statusNote"], NOTE)
        self.assertEqual(read["system"], "Custody ledger")
        self.assertEqual(read["evidenceLocation"], "Compliance share / Client assets / 2026")
        self.assertEqual(read["nextReviewDate"], "2027-03-31")
        self.assertEqual(read["version"], 2)
        self.assertEqual(read, response.json())

    def test_only_the_fields_sent_change(self) -> None:
        self.entry()
        self.assertEqual(self.patch({"process": "Reconciliation", "system": "Ledger"}, 1).status_code, 200)
        response = self.patch({"system": "New ledger"}, 2)
        self.assertEqual(response.json()["process"], "Reconciliation")
        self.assertEqual(response.json()["system"], "New ledger")

    def test_the_audit_row_carries_keys_ids_and_dates_before_and_after_and_no_note_text(self) -> None:
        self.entry()
        self.assertEqual(self.patch({"complianceStatus": "compliant", "statusNote": NOTE, "nextReviewDate": "2027-03-31", "rationale": "Checked."}, 1).status_code, 200)
        event = AuditEvent.objects.filter(action=status_logic.ENTRY_UPDATED).get()
        self.assertEqual(event.actor_id, self.owner.id)
        self.assertEqual(event.before["complianceStatus"], "not_assessed")
        self.assertEqual(event.after["complianceStatus"], "compliant")
        self.assertIsNone(event.before["nextReviewDate"])
        self.assertEqual(event.after["nextReviewDate"], "2027-03-31")
        self.assertEqual(event.after["version"], 2)
        self.assertIn("statusNote", event.after["changed"])
        stored = json.dumps([event.before, event.after, event.summary])
        self.assertNotIn(NOTE, stored)
        self.assertNotIn("Checked.", stored)

    def test_if_match_is_required(self) -> None:
        self.entry()
        response = self.patch({"process": "Reconciliation"}, None)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_a_stale_version_is_409_and_merges_nothing(self) -> None:
        self.entry()
        before = self.counts()
        for version in (0, 2):
            with self.subTest(version=version):
                response = self.patch({"process": "Reconciliation"}, version)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["code"], "stale_write")
        self.assertEqual(self.counts(), before)
        self.assertEqual(TenantObligation.objects.get().process, "")


class StatusNeedsApplies(RegisterStatusCase):
    def test_a_status_other_than_not_assessed_is_409_while_not_assessed(self) -> None:
        self.entry(Applicability.NOT_ASSESSED)
        response = self.patch({"complianceStatus": "compliant"}, 1)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "invalid_transition")
        self.assertEqual(TenantObligation.objects.get().compliance_status.kind, ComplianceCategory.NOT_ASSESSED.value)

    def test_a_status_other_than_not_assessed_is_409_while_it_does_not_apply(self) -> None:
        self.entry(Applicability.DOES_NOT_APPLY)
        response = self.patch({"complianceStatus": "gap"}, 1)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "invalid_transition")

    def test_a_status_is_stored_once_it_applies(self) -> None:
        self.entry(Applicability.APPLIES)
        response = self.patch({"complianceStatus": "gap"}, 1)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["complianceStatus"]["kind"], "gap")

    def test_a_first_write_of_a_status_is_409_and_creates_no_entry(self) -> None:
        before = self.counts()
        response = self.patch({"complianceStatus": "compliant"}, 0)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.counts(), before)

    def test_not_assessed_and_the_other_fields_are_stored_while_it_does_not_apply(self) -> None:
        self.entry(Applicability.DOES_NOT_APPLY)
        response = self.patch({"complianceStatus": "not_assessed", "statusNote": NOTE}, 1)
        self.assertEqual(response.status_code, 200, response.content)


class RefusedValues(RegisterStatusCase):
    def test_an_unknown_or_retired_key_is_422_unknown_key_naming_the_valid_keys(self) -> None:
        self.entry()
        tenancy.activate(self.tenant.id)
        ComplianceStatus.objects.filter(key="partly_compliant").update(active=False)
        for body in ({"complianceStatus": "mostly"}, {"complianceStatus": "partly_compliant"}, {"riskRating": "extreme"}, {"ownerTeam": "nobody"}):
            with self.subTest(body=body):
                response = self.patch(body, 1)
                self.assertEqual(response.status_code, 422)
                problem = response.json()
                self.assertEqual(problem["code"], "unknown_key")
                self.assertTrue(problem["validKeys"])
                self.assertNotIn(next(iter(body.values())), problem["validKeys"])
        self.assertIn("compliant", self.patch({"complianceStatus": "mostly"}, 1).json()["validKeys"])
        self.assertEqual(TenantObligation.objects.get().version, 1)

    def test_a_person_who_is_not_an_active_member_is_422_unknown_member(self) -> None:
        self.entry()
        outsider = factories.member_user(factories.tenant(slug="status-outside"))
        tenancy.activate(self.tenant.id)
        Membership.objects.filter(user=self.contact).update(deactivated_at=timezone.now())
        for body in (
            {"firstLineOwnerId": str(outsider.id)},
            {"complianceContactId": str(self.contact.id)},
            {"firstLineOwnerId": str(uuid.uuid4())},
        ):
            with self.subTest(body=body):
                response = self.patch(body, 1)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["code"], "unknown_member")
        self.assertEqual(TenantObligation.objects.get().version, 1)


class AssessmentHistory(RegisterStatusCase):
    def test_each_status_change_writes_one_assessment_row_and_nothing_else_does(self) -> None:
        self.entry()
        self.assertEqual(self.patch({"complianceStatus": "partly_compliant", "riskRating": "high", "rationale": "Manual log."}, 1).status_code, 200)
        self.assertEqual(self.patch({"process": "Reconciliation"}, 2).status_code, 200)
        self.assertEqual(self.patch({"complianceStatus": "partly_compliant"}, 3).status_code, 200)
        self.assertEqual(self.patch({"complianceStatus": "compliant", "nextReviewDate": "2027-03-31"}, 4).status_code, 200)
        rows = list(ComplianceAssessment.objects.order_by("assessed_at", "id"))
        self.assertEqual([row.status.key for row in rows], ["partly_compliant", "compliant"])
        self.assertEqual(rows[0].rationale, "Manual log.")
        self.assertEqual(rows[0].risk_rating_id, RiskRating.objects.get(key="high").id)
        self.assertEqual(rows[0].assessed_by_id, self.owner.id)
        self.assertIsNone(rows[0].scope_id)
        self.assertEqual(str(rows[1].next_review_date), "2027-03-31")


class EntityRows(RegisterStatusCase):
    def test_a_first_entity_write_creates_its_row_at_version_1(self) -> None:
        before = self.counts()
        response = self.patch({"ownerId": str(self.owner.id), "nextReviewDate": "2027-03-31"}, 0, entity=self.entities[0])
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["version"], 1)
        self.assertEqual(body["orgUnitName"], "Example Bank AB")
        self.assertEqual(body["applicability"], "under_assessment")
        self.assertEqual(body["owner"]["id"], str(self.owner.id))
        entries, scopes, _, events = self.counts()
        self.assertEqual((entries, scopes), (before[0] + 1, before[1] + 1))
        self.assertEqual(events, before[3] + 2)
        self.assertEqual(AuditEvent.objects.filter(action=status_logic.ENTITY_UPDATED).get().subject_id, TenantObligationScope.objects.get().id)

    def test_an_entity_status_needs_the_entity_to_apply(self) -> None:
        self.scope(self.entities[0], Applicability.DOES_NOT_APPLY)
        self.scope(self.entities[1], Applicability.NOT_ASSESSED)
        for entity in self.entities[:2]:
            with self.subTest(entity=entity.name):
                response = self.patch({"complianceStatus": "compliant"}, 1, entity=entity)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["code"], "invalid_transition")
        response = self.patch({"complianceStatus": "compliant"}, 0, entity=self.entities[2])
        self.assertEqual(response.status_code, 409, "a row not written yet is not assessed")

    def test_a_person_or_a_team_owns_an_entity_row_never_both(self) -> None:
        self.scope(self.entities[0])
        team = self.patch({"ownerTeam": "compliance"}, 1, entity=self.entities[0]).json()
        self.assertEqual(team["ownerTeam"]["key"], "compliance")
        person = self.patch({"ownerId": str(self.owner.id)}, 2, entity=self.entities[0]).json()
        self.assertEqual(person["owner"]["id"], str(self.owner.id))
        self.assertIsNone(person["ownerTeam"])
        both = self.patch({"ownerId": str(self.owner.id), "ownerTeam": "compliance"}, 3, entity=self.entities[0])
        self.assertEqual(both.status_code, 422)

    def test_an_entity_status_change_writes_an_assessment_on_its_row(self) -> None:
        scope = self.scope(self.entities[0])
        self.assertEqual(self.patch({"complianceStatus": "gap", "rationale": "No reconciliation."}, 1, entity=self.entities[0]).status_code, 200)
        row = ComplianceAssessment.objects.get()
        self.assertEqual(row.scope_id, scope.id)
        self.assertEqual(row.status.key, "gap")

    def test_a_stale_entity_write_is_409(self) -> None:
        self.scope(self.entities[0])
        response = self.patch({"statusNote": NOTE}, 3, entity=self.entities[0])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "stale_write")
        self.assertEqual(TenantObligationScope.objects.get().status_note, "")

    def test_an_org_unit_that_is_not_one_of_the_banks_legal_entities_is_404(self) -> None:
        tenancy.activate(self.tenant.id)
        group = OrgUnit.objects.create(tenant=self.tenant, kind=OrgUnitKind.GROUP.value, name="Example Group")
        for entity in (group, OrgUnit(id=uuid.uuid4())):
            with self.subTest(entity=entity.id):
                response = self.patch({"statusNote": NOTE}, 0, entity=entity)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json()["code"], "not_found")


class TenantIsolation(RegisterStatusCase):
    def test_tenant_b_gets_404_on_tenant_a_entity_and_never_reads_a_register(self) -> None:
        self.scope(self.entities[0])
        self.assertEqual(self.patch({"statusNote": NOTE, "ownerTeam": "compliance"}, 1, entity=self.entities[0]).status_code, 200)
        tenant_b = factories.tenant(slug="status-b")
        person_b = factories.member_user(tenant_b, roles=("compliance_officer",))
        with stub_session(self.who(tenant_b, person_b)):
            response = self.client.patch(
                self.url(self.entities[0]), data={"statusNote": "theirs"}, content_type="application/json", HTTP_IF_MATCH='"2"', **AS_SESSION
            )
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["code"], "not_found")
            read = self.client.get(self.url(), **AS_SESSION).json()
        self.assertEqual(read["version"], 0)
        self.assertEqual(read["entities"], [])
        self.assertNotIn(NOTE, json.dumps(read))
        tenancy.activate(self.tenant.id)
        self.assertEqual(TenantObligationScope.objects.get().status_note, NOTE)


class WorstOf(TestCase):
    """The obligation's pill is the worst of its entities by the fixed category, never by the
    label or the bank's ordinal: gap, then partly, then not assessed, then compliant."""

    RANK = (ComplianceCategory.GAP, ComplianceCategory.PARTLY, ComplianceCategory.NOT_ASSESSED, ComplianceCategory.COMPLIANT)

    def test_each_pair_of_categories(self) -> None:
        for a in ComplianceCategory:
            for b in ComplianceCategory:
                expected = min((a, b), key=self.RANK.index)
                # Labels and ordinals that point the other way, so only the kind can decide.
                first = ComplianceStatus(key=f"a-{a}", kind=a.value, ordinal=9 if a is expected else 0)
                second = ComplianceStatus(key=f"b-{b}", kind=b.value, ordinal=0 if a is expected else 9)
                with self.subTest(pair=(a.value, b.value)):
                    worst = status_logic.worst_of([first, second])
                    assert worst is not None
                    self.assertEqual(worst.kind, expected.value)

    def test_nothing_to_rank_is_none(self) -> None:
        self.assertIsNone(status_logic.worst_of([]))

    def test_the_entry_reads_the_worst_of_the_entities_that_apply(self) -> None:
        with transaction.atomic():
            seed_library()
        act = library_testing.instrument(key="worst-act", regime="regime:securities")
        obligation = library_testing.obligation(act, key="worst-duty")
        tenant = factories.tenant(slug="worst")
        person = factories.member_user(tenant, roles=("compliance_officer",))
        tenancy.activate(tenant.id)
        entry = status_logic.ensure_register_entry(
            tenant_id=tenant.id, obligation_id=obligation.id, actor=factories.user_actor(user_id=person.id)
        )
        statuses = {row.key: row for row in ComplianceStatus.objects.all()}
        for name, applicability, key in (
            ("Bank AB", Applicability.APPLIES, "compliant"),
            ("Finance AB", Applicability.APPLIES, "partly_compliant"),
            ("Liv AB", Applicability.DOES_NOT_APPLY, "gap"),
        ):
            entity = OrgUnit.objects.create(tenant=tenant, kind=OrgUnitKind.LEGAL_ENTITY.value, name=name)
            TenantObligationScope.objects.create(
                tenant=tenant, tenant_obligation=entry, org_unit=entity, applicability=applicability.value, compliance_status=statuses[key]
            )
        read = status_logic.read_register(tenant=tenant, order=["en"], obligation_id=obligation.id)
        self.assertEqual(read.compliance_status.key, "partly_compliant", "an entity that does not apply is left out")
