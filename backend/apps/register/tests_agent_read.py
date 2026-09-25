"""The register read of an agent access credential (ACC-04, ACC-08, D-76, ADR 0057).

`GET /register-entries` and `GET /register-entries/{obligationId}` answer a service key of an
agent access entry, or a personal access token naming one, holding `tenant:read`, and only
while the bank's tenant reach and the entry's own toggle are both on. They carry D-76's
fields and nothing else: no gap, case, assessment, comment, evidence, audit row, risk or
evidence location, no superseded reading and no removed link. An obligation outside the
entry's scope, a bank's own private obligation and one under a standard (AC-REG2) are 404
alone and absent from the list. The page is paged 20 by default and 100 at most, in a
constant number of queries however many rows it holds."""

from __future__ import annotations

import datetime
import json
import uuid
from typing import Any

from django.db import connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.agents.models import AgentAccess, AgentAccessProduct
from apps.governance.models import TenantReach
from apps.library import testing as library_testing
from apps.library.models import Obligation
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.register.logic import ensure_register_entry
from apps.register.models import (
    Applicability,
    AssessmentMethod,
    ComplianceAssessment,
    Gap,
    InternalLink,
    Interpretation,
    TenantObligation,
    TenantObligationScope,
)
from apps.shared import factories, tenancy
from apps.shared.audit import Actor, ActorType
from apps.taxonomy.models import ComplianceStatus, FootprintTerm, GapSource, GapStatus, LinkKind, RiskRating, Team
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.tenants.models import InternalItem, OrgUnit, OrgUnitKind, TenantProduct, TenantProductTerm

V1 = "/api/v1"
STANDARD_KEY = "iso-iec-27001-2022-conformance"
ENTRIES = f"{V1}/register-entries"
READS = ("tenant:read", "library:read")

# What the bank wrote that an agent must never read. Each is unique text, so a response that
# carries any of them is caught by a plain search of its body.
NEVER = {
    "gap": "Reconciliation runs weekly, not daily",
    "remediation": "Move the reconciliation to the nightly batch",
    "assessment": "Second line found the reconciliation late twice",
    "superseded reading": "We first read this as covering pension accounts only",
    "removed link": "Retired custody manual",
    "evidence location": "sharepoint://compliance/custody-evidence",
    "private reason": "Our own rule applies to the Stockholm branch",
}


def seed() -> None:
    with transaction.atomic():
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()


class ReadWorld:
    """One bank with two legal entities and a custody product. Its footprint names custody
    and advice. `narrow` is an entry narrowed to the custody product; `general` names nothing
    and reads the whole footprint. Both hold a service key with `tenant:read`, and reach is
    on for the bank and both entries. Four in-scope obligations are decided on (custody-
    tagged or untagged), one tagged advice is outside `narrow`, one is the bank's own private
    obligation, and one is ISO/IEC 27001's conformance duty, which the bank follows."""

    def __init__(self, *, slug: str = "agent-read") -> None:
        seed()
        self.tenant = factories.tenant(slug=slug)
        self.officer = factories.member(self.tenant, roles=("compliance_officer",), user_row=factories.user(name="Sara Lindqvist")).user
        self.actor = Actor(kind=ActorType.USER, id=self.officer.id, label=self.officer.name)
        act = library_testing.instrument(key=f"{slug}-act", regime="regime:securities")
        self.in_scope = [
            library_testing.obligation(act, key=f"{slug}-custody-1", terms=("service_type:custody",)),
            library_testing.obligation(act, key=f"{slug}-custody-2", terms=("service_type:custody",)),
            library_testing.obligation(act, key=f"{slug}-untagged-1"),
            library_testing.obligation(act, key=f"{slug}-untagged-2"),
        ]
        self.outside = library_testing.obligation(act, key=f"{slug}-advice", terms=("service_type:advice",))
        own_act = library_testing.instrument(key=f"{slug}-own", regime="regime:securities", owner_tenant=self.tenant)
        self.private = library_testing.obligation(own_act, key=f"{slug}-own-duty", owner_tenant=self.tenant)
        self.standard = Obligation.objects.filter(stable_key=STANDARD_KEY).first() or library_testing.standard()
        tenancy.activate(self.tenant.id)
        for ref in ("service_type:custody", "service_type:advice", "standard:iso_iec_27001"):
            FootprintTerm.objects.create(tenant=self.tenant, term=library_testing.term(ref))
        self.parent = OrgUnit.objects.create(tenant=self.tenant, kind=OrgUnitKind.LEGAL_ENTITY.value, name="Example Bank AB")
        self.branch = OrgUnit.objects.create(tenant=self.tenant, kind=OrgUnitKind.LEGAL_ENTITY.value, name="Example Bank Oyj")
        product = TenantProduct.objects.create(tenant=self.tenant, name="Custody accounts")
        TenantProductTerm.objects.create(tenant=self.tenant, product=product, term=library_testing.term("service_type:custody"))
        self.narrow = factories.agent_access_entry(self.tenant, name="Custody platform agent")
        tenancy.activate(self.tenant.id)
        AgentAccessProduct.objects.create(tenant=self.tenant, agent_access_id=self.narrow.id, product=product)
        self.general = factories.agent_access_entry(self.tenant, name="Compliance assistant")
        self.narrow_key = factories.entry_key(self.tenant, self.narrow, scopes=READS).plain_key
        self.general_key = factories.entry_key(self.tenant, self.general, scopes=READS).plain_key
        self.reach(True)
        self.entry_reach(self.narrow, True)
        self.entry_reach(self.general, True)
        for obligation in (*self.in_scope, self.outside, self.standard):
            self.decide(obligation)
        self.decide(self.private, reason=NEVER["private reason"])

    # -- switches -----------------------------------------------------------------------
    def reach(self, on: bool) -> None:
        tenancy.activate(self.tenant.id)
        TenantReach.objects.update_or_create(tenant=self.tenant, defaults={"enabled": on})

    def entry_reach(self, entry: Any, on: bool) -> None:
        tenancy.activate(self.tenant.id)
        AgentAccess.objects.filter(pk=entry.id).update(tenant_reach=on)

    # -- the bank's register ------------------------------------------------------------
    def decide(self, obligation: Any, *, reason: str | None = None) -> TenantObligation:
        """Every D-76 field set, and beside them everything an agent must never read."""
        tenancy.activate(self.tenant.id)
        with transaction.atomic():
            entry = ensure_register_entry(tenant_id=self.tenant.id, obligation_id=obligation.id, actor=self.actor)
        compliant = ComplianceStatus.objects.get(key="compliant")
        gap_status = ComplianceStatus.objects.get(key="gap")
        TenantObligation.objects.filter(pk=entry.pk).update(
            applicability=Applicability.APPLIES.value,
            applicability_reason=reason or f"We hold client assets under {obligation.stable_key}",
            applicability_decided_at=timezone.now(),
            applicability_decided_by=self.officer,
            compliance_status=compliant,
            status_note=f"Reconciled daily for {obligation.stable_key}",
            risk_rating=RiskRating.objects.get(key="high"),
            first_line_owner=self.officer,
            owner_team=Team.objects.get(key="compliance"),
            process="Client asset reconciliation",
            system="Custody ledger",
            evidence_location=NEVER["evidence location"],
            next_review_date=datetime.date.today() + datetime.timedelta(days=90),
        )
        for entity, status in ((self.parent, compliant), (self.branch, gap_status)):
            TenantObligationScope.objects.create(
                tenant=self.tenant,
                tenant_obligation=entry,
                org_unit=entity,
                applicability=Applicability.APPLIES.value,
                applicability_reason=f"{entity.name} holds client assets",
                applicability_decided_at=timezone.now(),
                applicability_decided_by=self.officer,
                compliance_status=status,
                status_note=f"{entity.name} reconciles daily",
                owner=self.officer,
                process="Entity reconciliation",
                system="Entity ledger",
                evidence_location=NEVER["evidence location"],
            )
        Interpretation.objects.create(
            tenant=self.tenant,
            tenant_obligation=entry,
            version_number=1,
            body=NEVER["superseded reading"],
            author=self.officer,
            superseded_at=timezone.now(),
        )
        Interpretation.objects.create(
            tenant=self.tenant, tenant_obligation=entry, version_number=2, body="We read this as every client account.", author=self.officer
        )
        policy = LinkKind.objects.get(key="policy")
        for label, removed in (("Client asset policy", False), (NEVER["removed link"], True)):
            item = InternalItem.objects.create(
                tenant=self.tenant, kind=policy, name=f"{label} for {obligation.stable_key}", external_system="ServiceNow GRC"
            )
            InternalLink.objects.create(
                tenant=self.tenant,
                tenant_obligation=entry,
                internal_item=item,
                label=label,
                external_ref="POL-014",
                created_by=self.officer,
                removed_at=timezone.now() if removed else None,
                removed_by=self.officer if removed else None,
            )
        Gap.objects.create(
            tenant=self.tenant,
            tenant_obligation=entry,
            title=NEVER["gap"],
            remediation=NEVER["remediation"],
            severity=RiskRating.objects.get(key="high"),
            source=GapSource.objects.get(key="audit"),
            status=GapStatus.objects.get(key="open"),
            identified_by=self.officer,
        )
        ComplianceAssessment.objects.create(
            tenant=self.tenant,
            tenant_obligation=entry,
            method=AssessmentMethod.SECOND_LINE_REVIEW.value,
            status=compliant,
            rationale=NEVER["assessment"],
            assessed_by=self.officer,
        )
        return entry

    # -- calls --------------------------------------------------------------------------
    def get(self, client: Any, path: str, key: str, **params: Any) -> Any:
        tenancy.clear_tenant()
        return client.get(path, params, HTTP_X_API_KEY=key)


def leaks(body: bytes) -> list[str]:
    """Which of the texts an agent must never read appear in a response body."""
    text = body.decode()
    return [name for name, value in NEVER.items() if value in text]


class RegisterEntriesRead(TestCase):
    world: ReadWorld

    @classmethod
    def setUpTestData(cls) -> None:
        cls.world = ReadWorld()

    def test_the_list_carries_d76_fields_for_the_obligations_in_scope_and_nothing_else(self) -> None:
        response = self.world.get(self.client, ENTRIES, self.world.narrow_key)
        self.assertEqual(response.status_code, 200, response.content)
        page = response.json()
        self.assertEqual({row["obligationId"] for row in page["items"]}, {str(row.id) for row in self.world.in_scope})
        self.assertEqual(page["total"], len(self.world.in_scope))
        self.assertEqual(leaks(response.content), [])
        row = next(row for row in page["items"] if row["obligationId"] == str(self.world.in_scope[0].id))
        self.assertEqual(
            set(row),
            {
                "obligationId", "obligationKey", "applicability", "applicabilityReason", "complianceStatus", "statusNote",
                "interpretation", "owner", "ownerTeam", "process", "system", "nextReviewDate", "entities", "internalItems",
            },
        )
        self.assertEqual(row["obligationKey"], self.world.in_scope[0].stable_key)
        self.assertEqual((row["applicability"], row["interpretation"]), ("applies", "We read this as every client account."))
        # The worst entity it applies to, by category, as the register screen shows it.
        self.assertEqual(row["complianceStatus"]["kind"], "gap")
        self.assertEqual((row["owner"]["id"], row["ownerTeam"]["key"]), (str(self.world.officer.id), "compliance"))
        self.assertEqual({entity["orgUnitName"] for entity in row["entities"]}, {"Example Bank AB", "Example Bank Oyj"})
        self.assertEqual(
            set(row["entities"][0]),
            {
                "orgUnitId", "orgUnitName", "applicability", "applicabilityReason", "complianceStatus", "statusNote",
                "owner", "ownerTeam", "process", "system", "nextReviewDate",
            },
        )
        self.assertEqual([item["label"] for item in row["internalItems"]], ["Client asset policy"])
        self.assertEqual(set(row["internalItems"][0]), {"kind", "label", "url", "externalRef", "externalSystem"})

    def test_an_obligation_in_scope_reads_alone_and_every_other_answers_404(self) -> None:
        own = self.world.get(self.client, f"{ENTRIES}/{self.world.in_scope[2].id}", self.world.narrow_key)
        self.assertEqual(own.status_code, 200, own.content)
        self.assertEqual(own.json()["obligationId"], str(self.world.in_scope[2].id))
        self.assertEqual(leaks(own.content), [])
        for obligation in (self.world.outside, self.world.private, self.world.standard):
            refused = self.world.get(self.client, f"{ENTRIES}/{obligation.id}", self.world.narrow_key)
            self.assertEqual((refused.status_code, refused.json()["code"]), (404, "not_found"), obligation.stable_key)
        unknown = self.world.get(self.client, f"{ENTRIES}/{uuid.uuid4()}", self.world.narrow_key)
        self.assertEqual(unknown.status_code, 404)

    def test_an_entry_naming_nothing_reads_the_footprint_but_never_a_private_or_standard_obligation(self) -> None:
        response = self.world.get(self.client, ENTRIES, self.world.general_key)
        ids = {row["obligationId"] for row in response.json()["items"]}
        self.assertEqual(ids, {str(row.id) for row in (*self.world.in_scope, self.world.outside)})
        self.assertEqual(leaks(response.content), [])
        for obligation in (self.world.private, self.world.standard):
            refused = self.world.get(self.client, f"{ENTRIES}/{obligation.id}", self.world.general_key)
            self.assertEqual(refused.status_code, 404, obligation.stable_key)

    def test_an_obligation_in_scope_nobody_decided_reads_as_under_assessment(self) -> None:
        fresh = library_testing.obligation(self.world.in_scope[0].instrument, key="agent-read-fresh")
        response = self.world.get(self.client, f"{ENTRIES}/{fresh.id}", self.world.narrow_key)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual((body["applicability"], body["entities"], body["internalItems"]), ("under_assessment", [], []))
        self.assertNotIn(str(fresh.id), json.dumps(self.world.get(self.client, ENTRIES, self.world.narrow_key).json()))

    def test_pages_are_20_by_default_and_100_at_most(self) -> None:
        page = self.world.get(self.client, ENTRIES, self.world.general_key, limit=2, offset=1).json()
        self.assertEqual((len(page["items"]), page["total"]), (2, 5))
        everything = [row["obligationId"] for row in self.world.get(self.client, ENTRIES, self.world.general_key).json()["items"]]
        self.assertEqual([row["obligationId"] for row in page["items"]], everything[1:3])
        self.assertEqual(self.world.get(self.client, ENTRIES, self.world.general_key, limit=101).status_code, 422)

    def test_the_page_costs_the_same_queries_however_many_rows_it_holds(self) -> None:
        def count() -> int:
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(self.world.get(self.client, ENTRIES, self.world.general_key).status_code, 200)
            return len(queries)

        count()  # the key's first use stamps it and writes its security-log row once
        before = count()
        act = self.world.in_scope[0].instrument
        for n in range(4):
            self.world.decide(library_testing.obligation(act, key=f"agent-read-more-{n}"))
        self.assertEqual(count(), before)


class RegisterEntriesRefused(TestCase):
    world: ReadWorld

    @classmethod
    def setUpTestData(cls) -> None:
        cls.world = ReadWorld(slug="agent-refused")

    def assert_reach_off(self, key: str) -> None:
        for path in (ENTRIES, f"{ENTRIES}/{self.world.in_scope[0].id}"):
            response = self.world.get(self.client, path, key)
            self.assertEqual((response.status_code, response.json()["code"]), (403, "tenant_reach_off"), path)

    def test_the_tenant_switch_off_stops_every_entry_whatever_its_own_toggle_says(self) -> None:
        self.world.reach(False)
        self.assert_reach_off(self.world.narrow_key)
        self.assert_reach_off(self.world.general_key)

    def test_an_entry_whose_own_toggle_is_off_reads_nothing(self) -> None:
        self.world.entry_reach(self.world.narrow, False)
        self.assert_reach_off(self.world.narrow_key)
        self.assertEqual(self.world.get(self.client, ENTRIES, self.world.general_key).status_code, 200)

    def test_a_bank_with_no_reach_row_reads_as_off(self) -> None:
        tenancy.activate(self.world.tenant.id)
        TenantReach.objects.filter(tenant=self.world.tenant).delete()
        self.assert_reach_off(self.world.general_key)

    def test_a_personal_token_reads_only_when_it_names_an_entry_with_reach(self) -> None:
        named = factories.personal_token(self.world.tenant, self.world.officer, scopes=READS, entry=self.world.narrow).plain_key
        response = self.world.get(self.client, ENTRIES, named)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["total"], len(self.world.in_scope))
        unbound = factories.personal_token(self.world.tenant, self.world.officer, scopes=READS).plain_key
        refused = self.world.get(self.client, ENTRIES, unbound)
        self.assertEqual((refused.status_code, refused.json()["code"]), (403, "permission_denied"))

    def test_a_key_without_tenant_read_or_bound_to_no_entry_is_refused(self) -> None:
        library_only = factories.entry_key(self.world.tenant, self.world.narrow, scopes=("library:read",)).plain_key
        self.assertEqual(self.world.get(self.client, ENTRIES, library_only).status_code, 403)
        unbound = factories.api_key(self.world.tenant, scopes=READS).plain_key
        self.assertEqual(self.world.get(self.client, ENTRIES, unbound).status_code, 403)

    def test_a_person_and_a_missing_credential_cannot_use_the_agent_read(self) -> None:
        from apps.shared.testing import sign_in

        signed_in = self.client.get(ENTRIES, **sign_in(self.world.officer, tenant=self.world.tenant))
        self.assertEqual(signed_in.status_code, 401)
        self.assertEqual(self.client.get(ENTRIES).status_code, 401)

    def test_a_write_is_refused_as_read_only(self) -> None:
        tenancy.clear_tenant()
        response = self.client.post(ENTRIES, "{}", content_type="application/json", HTTP_X_API_KEY=self.world.narrow_key)
        self.assertIn(response.status_code, (403, 405))


class RegisterEntriesAcrossBanks(TestCase):
    a: ReadWorld
    b: ReadWorld

    @classmethod
    def setUpTestData(cls) -> None:
        cls.a = ReadWorld(slug="agent-bank-a")
        cls.b = ReadWorld(slug="agent-bank-b")

    def test_bank_b_reads_none_of_bank_a(self) -> None:
        listed = self.b.get(self.client, ENTRIES, self.b.general_key)
        a_ids = {str(row.id) for row in (*self.a.in_scope, self.a.outside)}
        self.assertFalse(a_ids & {row["obligationId"] for row in listed.json()["items"]})
        self.assertNotIn(b"Reconciled daily for agent-bank-a", listed.content)
        # A's obligation is a shared library fact B can see, so B answers with its own
        # (empty) decision on it, never A's.
        read = self.b.get(self.client, f"{ENTRIES}/{self.a.in_scope[2].id}", self.b.general_key)
        self.assertEqual(read.status_code, 200, read.content)
        self.assertEqual((read.json()["applicability"], read.json()["entities"]), ("under_assessment", []))
        self.assertNotIn(b"Reconciled daily", read.content)
        # A's private obligation is not B's to see at all.
        self.assertEqual(self.b.get(self.client, f"{ENTRIES}/{self.a.private.id}", self.b.general_key).status_code, 404)

