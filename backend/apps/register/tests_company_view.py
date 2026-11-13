"""What applies, company by company (REG-01, FP-05, D-75, REG-S18, REG-S19): the four reads
of `company_view.py`, proved through their routes as a real session.

Nothing here restates the rule: every expectation is read back from what the bank already
sees. An obligation is offered for a company when `GET /obligations` lists it and
`GET /obligations/{id}/register/entities` names the company; its target, answer, reason and
version are those of `GET /obligations/{id}/register`; a company's totals are the sum of its
rows; a regulation's roll-up is the inventory's own totals under each applicability filter.
A row is to decide exactly while its `decidedBy` is null, and a `toDecide` count is the
number of such rows, which is what a Decide all run sets (tests_decide_all.py).
The SQL span is pinned against `applicability._spans` over a matrix of duties and companies.

Proven to fail 2026-11-13, each by one change to `company_view.py` put back afterwards: with
every company read as spanned in `_offers`, the fund company was offered the duty on banks
alone and the payments duty (13 tests); with the target taken at one spanned entity instead
of two, the duty on banks alone named Example Bank AB and read under assessment (7); with
the entity's type left out of the span's checks, the twin test named the five duties that
carry a legal-entity term; with the reached jurisdictions never read, it named every Swedish
duty for the company that has Sweden outside its scope; with the working-inventory filter
lifted, the duty outside the footprint was listed and counted (8).
"""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.library import schemas as library_schemas
from apps.library import testing as library_build
from apps.library.models import Authority, Obligation
from apps.library.tests_reading import set_footprint
from apps.register import company_view
from apps.register import schemas as register_schemas
from apps.register.applicability import entities_spanned
from apps.register.models import TenantObligation, TenantObligationScope
from apps.register.tests_applicability import Bank, seed_library
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.adapters.registers import MockRegisters
from apps.shared.models import AuditEvent, Tenant
from apps.shared.testing import API_KEY_FOR_TESTS, SESSION_TOKEN_FOR_TESTS, agent_principal, sign_in, stub_api_key, stub_session, user_principal
from apps.taxonomy.models import ComplianceStatus, EntityScopeExclusion
from apps.tenants import registers_logic
from apps.tenants.models import OrgUnit, OrgUnitKind, RegisterEntry

V1 = "/api/v1"
FI = "fi"
ANSWERS = ("applies", "not_applicable", "under_assessment")
COUNT_OF = {"applies": "applies", "not_applicable": "notApplicable", "under_assessment": "underAssessment"}
ROW_FIELDS = {"obligationId", "refLabel", "title", "orgUnitId", "applicability", "reason", "decidedAt", "decidedBy", "version", "matchedTerms"}


def exclude(tenant: Tenant, entity: OrgUnit, *refs: str) -> None:
    """Take these terms out of one company's own scope, as an approved request leaves them."""
    request = factories.footprint_request(tenant)
    with transaction.atomic():
        tenancy.activate(tenant.id)
        for ref in refs:
            EntityScopeExclusion.objects.create(tenant=tenant, org_unit=entity, term=library_build.term(ref), request=request)


def register_facts(tenant: Tenant, entity: OrgUnit, number: str) -> None:
    """Finansinspektionen's facts on the mock register's company `number`, kept for `entity`."""
    read = MockRegisters().licence_facts(FI, number)
    assert read is not None
    facts = registers_logic.register_facts(FI, read)
    now = timezone.now()
    with transaction.atomic():
        tenancy.activate(tenant.id)
        RegisterEntry.objects.create(
            tenant=tenant,
            org_unit=entity,
            authority=Authority.objects.get(key=FI),
            facts=facts.model_dump(mode="json", by_alias=True),
            source_url="https://www.fi.se/",
            read_at=now,
            changed_at=now,
        )


def tally(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Rows of the answers list as the five counts a company or a regulation carries: by the
    answer each reads, and to decide where no person set it."""
    counted = Counter(row["applicability"] for row in rows)
    return {"offered": len(rows), **{COUNT_OF[answer]: counted[answer] for answer in ANSWERS}, "toDecide": sum(row["decidedBy"] is None for row in rows)}


def counts(row: dict[str, Any]) -> dict[str, int]:
    return {name: row[name] for name in ("offered", "applies", "notApplicable", "underAssessment", "toDecide")}


# ---------------------------------------------------------------------------------------
# The span as SQL
# ---------------------------------------------------------------------------------------
class TheSqlSpanMirrorsPython(TestCase):
    """`company_view.spans_expression()` against `applicability.entities_spanned()`, which
    runs `_spans`, for every duty and company of a matrix: no entity term, an entity term the
    duty carries and one it does not, exclusions that empty one dimension and not another,
    an opt-in dimension, and a dimension whose terms mirror the jurisdictions."""

    tenant: Tenant
    duties: dict[str, Obligation]

    @classmethod
    def setUpTestData(cls) -> None:
        seed_library()
        cls.tenant = factories.tenant(slug="cv-span")
        for name, entity_term, outside in (
            ("Example Holding AB", None, ()),
            ("Example Bank AB", "legal_entity:bank", ()),
            ("Example Fonder AB", "legal_entity:fund_company", ("regime:banking", "regime:insurance", "regime:payments")),
            ("Example Kort AB", "legal_entity:bank", ("service_type:custody", "service_type:advice", "regime:payments", "licensed_activity:card_issuing")),
            # None of these is a line the scope request accepts; the span reads whatever is stored.
            ("Example Certified AB", "legal_entity:insurer", ("standard:iso_iec_27001",)),
            ("Example Odd AB", "legal_entity:bank", ("legal_entity:insurer",)),
            ("Example Paradox AB", "legal_entity:bank", ("legal_entity:bank",)),
        ):
            entity = factories.legal_entity(cls.tenant, name=name, entity_term_id=library_build.term(entity_term).id if entity_term else None)
            exclude(cls.tenant, entity, *outside)
        factories.legal_entity(cls.tenant, name="Example Wound Down AB", active=False)
        securities = library_build.instrument(key="span-lvm", regime="regime:securities")
        payments = library_build.instrument(key="span-lob", regime="regime:payments")
        aml = library_build.instrument(key="span-amlr", regime="regime:aml", jurisdiction="eu")
        scoped: tuple[tuple[Any, str, tuple[str, ...]], ...] = (
            (securities, "no-own-term", ()),
            (securities, "banks", ("legal_entity:bank",)),
            (securities, "funds-and-insurers", ("legal_entity:fund_company", "legal_entity:insurer")),
            (securities, "insurers", ("legal_entity:insurer",)),
            (securities, "banks-and-insurers", ("legal_entity:bank", "legal_entity:insurer")),
            (securities, "custody-and-advice", ("service_type:custody", "service_type:advice")),
            (securities, "custody-and-execution-for-banks", ("service_type:custody", "service_type:execution_only", "legal_entity:bank")),
            (securities, "card-issuing", ("licensed_activity:card_issuing",)),
            (securities, "both-card-activities", ("licensed_activity:card_issuing", "licensed_activity:card_acquiring")),
            (payments, "payments-alone", ()),
            (payments, "payments-by-its-own-term", ("regime:payments",)),
            (payments, "payments-and-securities", ("regime:payments", "regime:securities")),
            (payments, "payments-custody", ("service_type:custody",)),
            (aml, "cross-cutting", ("regime:aml", "client_category:retail", "channel:digital")),
        )
        cls.duties = {key: library_build.obligation(law, key=f"span-{key}", terms=terms) for law, key, terms in scoped}
        cls.duties["standard"] = library_build.standard()

    def spans(self) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        """Duty key -> the names of the companies it spans, by the SQL and by `_spans`."""
        tenancy.activate(self.tenant.id)
        entities = list(
            OrgUnit.objects.filter(kind=OrgUnitKind.LEGAL_ENTITY.value, active=True).select_related("entity_term__dimension").order_by("name", "id")
        )
        rows = Obligation.objects.filter(pk__in=[duty.id for duty in self.duties.values()]).annotate(spans=company_view.spans_expression(entities))
        key_of = {duty.id: key for key, duty in self.duties.items()}
        by_sql = {key_of[row.id]: {entity.name for entity, spanned in zip(entities, row.spans, strict=True) if spanned} for row in rows}
        by_python = {key_of[duty_id]: {entity.name for entity in spanned} for duty_id, spanned in entities_spanned(list(key_of)).items()}
        return by_sql, by_python

    def test_every_duty_spans_the_same_companies_by_the_sql_and_by_the_python_rule(self) -> None:
        by_sql, by_python = self.spans()
        self.assertEqual(set(by_sql), set(self.duties))
        for key in self.duties:
            with self.subTest(duty=key):
                self.assertEqual(by_sql[key], by_python[key])

    def test_they_agree_where_a_guarded_dimension_mirrors_the_jurisdictions(self) -> None:
        """No guard reads the jurisdictions a rule reaches unless a company's own scope leaves
        one out, which no scope request can ask for; then the SQL reads them too, for every
        company at once."""
        nordic = factories.legal_entity(self.tenant, name="Example Nordic AB")
        exclude(self.tenant, nordic, "jurisdiction:se")
        by_sql, by_python = self.spans()
        for key in self.duties:
            with self.subTest(duty=key):
                self.assertEqual(by_sql[key], by_python[key])
        self.assertNotIn("Example Nordic AB", by_sql["no-own-term"], "a Swedish act reaches Sweden alone")
        self.assertIn("Example Nordic AB", by_sql["cross-cutting"], "a Union act reaches other countries too")

    def test_the_matrix_decides_both_ways_for_every_company_but_the_one_with_nothing_to_narrow_it(self) -> None:
        """A matrix every company spans whole would agree by accident."""
        by_sql, _ = self.spans()
        everyone = {
            "Example Holding AB",
            "Example Bank AB",
            "Example Fonder AB",
            "Example Kort AB",
            "Example Certified AB",
            "Example Odd AB",
            "Example Paradox AB",
        }
        spanned_by = {name: {key for key, names in by_sql.items() if name in names} for name in everyone}
        self.assertEqual(spanned_by["Example Holding AB"], set(self.duties), "no entity term and no exclusion: every duty")
        for name in everyone - {"Example Holding AB"}:
            with self.subTest(company=name):
                self.assertTrue(spanned_by[name])
                self.assertTrue(set(self.duties) - spanned_by[name])
        # The cases the brief names, read off the SQL alone.
        self.assertEqual(by_sql["banks"], {"Example Holding AB", "Example Bank AB", "Example Kort AB", "Example Odd AB"})
        self.assertNotIn("Example Fonder AB", by_sql["payments-alone"])
        self.assertIn("Example Fonder AB", by_sql["payments-and-securities"])
        self.assertNotIn("Example Kort AB", by_sql["custody-and-advice"], "every service it carries is outside the company's scope")
        self.assertIn("Example Kort AB", by_sql["custody-and-execution-for-banks"], "one service is left")
        self.assertNotIn("Example Kort AB", by_sql["card-issuing"])
        self.assertIn("Example Kort AB", by_sql["both-card-activities"])
        self.assertEqual(by_sql["standard"], everyone - {"Example Certified AB"}, "an opt-in term narrows only where it is excluded")
        self.assertEqual(by_sql["cross-cutting"], everyone)
        self.assertNotIn("Example Odd AB", by_sql["insurers"])
        # Its own type outside its own scope: the type must be carried, and another beside it.
        self.assertNotIn("Example Paradox AB", by_sql["banks"])
        self.assertIn("Example Paradox AB", by_sql["banks-and-insurers"])


# ---------------------------------------------------------------------------------------
# The four reads
# ---------------------------------------------------------------------------------------
class WhatAppliesCase(TestCase):
    """Tenant A, its three companies and two regulations. The securities act holds a duty on
    banks and fund companies that Example Bank AB answered (`shared`), a duty on banks alone
    answered for the obligation as a whole (`single`), a duty nobody answered (`nobody`), a
    custody duty answered for the obligation as a whole although it spans every company
    (`custody`), and an advice duty the bank's footprint leaves out (`outside`). The payments
    act holds one duty (`payments`), and payments is outside Example Fonder AB's own scope.
    Example Bank AB has register facts; tenant B has the same companies and nothing else."""

    a: Bank
    b: Bank
    shared: Obligation
    single: Obligation
    nobody: Obligation
    custody: Obligation
    outside: Obligation
    payments: Obligation

    @classmethod
    def setUpTestData(cls) -> None:
        seed_library()
        library_build.authority(key=FI, short_name="FI")
        cls.a = Bank("cv-a")
        cls.b = Bank("cv-b")
        set_footprint(cls.a.tenant, ("service_type:custody",))
        lvm = library_build.instrument(key="cv-lvm", short_name="LVM", official_ref="SFS 2007:528", regime="regime:securities")
        lob = library_build.instrument(key="cv-lob", short_name="LOB", official_ref="SFS 2010:751", regime="regime:payments")
        cls.shared = library_build.obligation(
            lvm, key="cv-lvm-1-shared", ref_label="1 §", titles={"en": "Keep client assets apart"}, terms=("legal_entity:bank", "legal_entity:fund_company")
        )
        cls.single = library_build.obligation(lvm, key="cv-lvm-2-single", ref_label="2 §", titles={"en": "Report large exposures"}, terms=("legal_entity:bank",))
        cls.nobody = library_build.obligation(lvm, key="cv-lvm-3-nobody", ref_label="3 §", titles={"en": "Record client orders"})
        cls.outside = library_build.obligation(lvm, key="cv-lvm-4-outside", ref_label="4 §", terms=("service_type:advice",))
        cls.custody = library_build.obligation(
            lvm, key="cv-lvm-5-custody", ref_label="5 §", titles={"en": "Reconcile custody accounts"}, terms=("service_type:custody", "client_category:retail")
        )
        cls.payments = library_build.obligation(lob, key="cv-lob-1-payments", ref_label="1 §", titles={"en": "Safeguard client funds"})
        exclude(cls.a.tenant, cls.a.fonder, "regime:payments")
        register_facts(cls.a.tenant, cls.a.bank_ab, "556000-0001")

    def setUp(self) -> None:
        # As the officer does on each obligation's page; the two that apply then get a status.
        officer = sign_in(self.a.officer, tenant=self.a.tenant)
        version: dict[uuid.UUID, int] = {}
        for duty, body in (
            (self.shared, {"orgUnitId": str(self.a.bank_ab.id), "applicability": "applies", "reason": "Holds client assets"}),
            (self.single, {"applicability": "not_applicable", "reason": "No large exposures"}),
            (self.custody, {"applicability": "applies", "reason": "Custody is offered group-wide"}),
        ):
            answered = self.client.put(f"{V1}/obligations/{duty.id}/applicability", data=body, content_type="application/json", **officer)
            self.assertEqual(answered.status_code, 200, answered.content)
            version[duty.id] = answered.json()["version"]
        for duty, path, status in (
            (self.shared, f"/register/entities/{self.a.bank_ab.id}", "partly_compliant"),
            (self.custody, "/register", "gap"),
        ):
            patched = self.client.patch(
                f"{V1}/obligations/{duty.id}{path}",
                data={"complianceStatus": status, "rationale": "Reviewed"},
                content_type="application/json",
                HTTP_IF_MATCH=f'"{version[duty.id]}"',
                **officer,
            )
            self.assertEqual(patched.status_code, 200, patched.content)

        self.sessions: dict[tuple[uuid.UUID, uuid.UUID], dict[str, Any]] = {}

    def get(self, path: str, params: dict[str, Any] | None = None, *, who: Any = None, tenant: Tenant | None = None) -> Any:
        """As the owner of tenant A, who holds `register.read` and nothing that decides, unless
        told otherwise; one session per person and test."""
        who, tenant = who or self.a.owner, tenant or self.a.tenant
        if (who.id, tenant.id) not in self.sessions:
            self.sessions[(who.id, tenant.id)] = sign_in(who, tenant=tenant)
        return self.client.get(f"{V1}{path}", params or {}, **self.sessions[(who.id, tenant.id)])

    def ok(self, path: str, params: dict[str, Any] | None = None, *, who: Any = None, tenant: Tenant | None = None) -> Any:
        response = self.get(path, params, who=who, tenant=tenant)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def companies(self) -> list[dict[str, Any]]:
        listed: list[dict[str, Any]] = self.ok("/applicability/companies")
        return listed

    def regulations(self, company: OrgUnit, **params: Any) -> dict[str, Any]:
        page: dict[str, Any] = self.ok("/applicability/regulations", {"orgUnitId": str(company.id), **params})
        return page

    def regulation_keys(self, company: OrgUnit, **params: Any) -> list[str]:
        return [row["instrument"]["key"] for row in self.regulations(company, **params)["items"]]

    def rows(self, company: OrgUnit, instrument: str, **params: Any) -> dict[str, Any]:
        page: dict[str, Any] = self.ok("/applicability/rows", {"orgUnitId": str(company.id), "instrument": instrument, **params})
        return page

    def row_ids(self, company: OrgUnit, instrument: str, **params: Any) -> list[str]:
        return [row["obligationId"] for row in self.rows(company, instrument, **params)["items"]]

    def roll_up(self, instrument: str) -> dict[str, Any]:
        """The roll-up of the regulation with this stable key, by the id the instruments list gives."""
        [listed] = [row for row in self.ok("/instruments", {"limit": 100})["items"] if row["stableKey"] == instrument]
        rolled: dict[str, Any] = self.ok(f"/instruments/{listed['id']}/applicability")
        return rolled

    def inventory_total(self, instrument: str, **filters: Any) -> int:
        """How many obligations of the regulation `GET /obligations` lists under these filters."""
        total: int = self.ok("/obligations", {"instrument": instrument, **filters})["total"]
        return total

    def page_says(self, company: OrgUnit, instrument: str) -> list[dict[str, Any]]:
        """What the obligation pages say about `company` under `instrument`, row by row: the
        duties the inventory lists, kept where the page's own span names the company, each
        with the answer the page shows for it."""
        expected = []
        for duty in self.ok("/obligations", {"instrument": instrument, "limit": 100})["items"]:
            spanned = [entity["orgUnitId"] for entity in self.ok(f"/obligations/{duty['id']}/register/entities")]
            if str(company.id) not in spanned:
                continue
            entry = self.ok(f"/obligations/{duty['id']}/register")
            self.assertEqual([entity["orgUnitId"] for entity in entry["panels"]["spannedEntities"]], spanned)
            if len(spanned) < 2:  # ObligationApplicabilityPanel answersOf: the obligation as a whole
                target, answer = None, entry
            else:
                target = str(company.id)
                answer = next(
                    (row for row in entry["entities"] if row["orgUnitId"] == target),
                    {"applicability": "under_assessment", "applicabilityReason": None, "applicabilityDecidedAt": None, "applicabilityDecidedBy": None, "version": 0},
                )
            expected.append(
                {
                    "obligationId": duty["id"],
                    "refLabel": duty["refLabel"],
                    "title": duty["title"]["text"],
                    "orgUnitId": target,
                    "applicability": answer["applicability"],
                    "reason": answer["applicabilityReason"],
                    "decidedAt": answer["applicabilityDecidedAt"],
                    "decidedBy": answer["applicabilityDecidedBy"],
                    "version": answer["version"],
                }
            )
        return expected


class AgreementWithTheObligationPage(WhatAppliesCase):
    def test_every_row_is_what_the_obligation_page_says_for_that_company(self) -> None:
        for company in (self.a.bank_ab, self.a.fonder, self.a.liv):
            for instrument in ("cv-lvm", "cv-lob"):
                with self.subTest(company=company.name, instrument=instrument):
                    page = self.rows(company, instrument, limit=100)
                    self.assertEqual([{name: row[name] for name in row if name != "matchedTerms"} for row in page["items"]], self.page_says(company, instrument))
                    self.assertEqual(page["total"], len(page["items"]))

    def test_the_five_duties_read_as_seeded(self) -> None:
        """The agreement above would hold over an empty list; these are the rows themselves."""
        bank, fonder, liv = (str(entity.id) for entity in (self.a.bank_ab, self.a.fonder, self.a.liv))
        officer = {"id": str(self.a.officer.id), "name": "Sara Lind"}
        read = {company.name: {row["obligationId"]: row for row in self.rows(company, "cv-lvm")["items"]} for company in (self.a.bank_ab, self.a.fonder, self.a.liv)}
        of_the_bank = read["Example Bank AB"]
        self.assertEqual(list(of_the_bank), [str(duty.id) for duty in (self.shared, self.single, self.nobody, self.custody)], "the inventory's order")
        # One spanning two entities, answered for one of them.
        self.assertEqual(
            {name: of_the_bank[str(self.shared.id)][name] for name in ("refLabel", "title", "orgUnitId", "applicability", "reason", "decidedBy", "version")},
            {"refLabel": "1 §", "title": "Keep client assets apart", "orgUnitId": bank, "applicability": "applies", "reason": "Holds client assets", "decidedBy": officer, "version": 2},
        )
        self.assertIsNotNone(of_the_bank[str(self.shared.id)]["decidedAt"])
        unanswered = {"applicability": "under_assessment", "reason": None, "decidedAt": None, "decidedBy": None, "version": 0}
        self.assertEqual({name: read["Example Fonder AB"][str(self.shared.id)][name] for name in ("orgUnitId", *unanswered)}, {"orgUnitId": fonder, **unanswered})
        self.assertNotIn(str(self.shared.id), read["Example Liv Försäkring AB"])
        # One spanning a single entity: the obligation as a whole, answered on the entry.
        self.assertEqual(
            {name: of_the_bank[str(self.single.id)][name] for name in ("orgUnitId", "applicability", "reason", "decidedBy")},
            {"orgUnitId": None, "applicability": "not_applicable", "reason": "No large exposures", "decidedBy": officer},
        )
        self.assertNotIn(str(self.single.id), read["Example Fonder AB"])
        # One nobody answered, offered for each company it spans.
        for name, target in (("Example Bank AB", bank), ("Example Fonder AB", fonder), ("Example Liv Försäkring AB", liv)):
            self.assertEqual({key: read[name][str(self.nobody.id)][key] for key in ("orgUnitId", *unanswered)}, {"orgUnitId": target, **unanswered})
        # The entry answered for the obligation as a whole while it spans several: each company still has its own answer to give.
        self.assertEqual({key: of_the_bank[str(self.custody.id)][key] for key in ("orgUnitId", *unanswered)}, {"orgUnitId": bank, **unanswered})
        # One a company's exclusion removes, and one the bank's footprint leaves out.
        self.assertEqual([row["obligationId"] for row in self.rows(self.a.bank_ab, "cv-lob")["items"]], [str(self.payments.id)])
        self.assertEqual(self.rows(self.a.fonder, "cv-lob"), {"items": [], "total": 0})
        for rows in read.values():
            self.assertNotIn(str(self.outside.id), rows)

    def test_a_companys_totals_are_the_sum_of_its_regulations_and_of_its_rows(self) -> None:
        listed = self.companies()
        self.assertEqual([row["orgUnit"] for row in listed], [{"id": str(entity.id), "name": entity.name} for entity in (self.a.bank_ab, self.a.fonder, self.a.liv)])
        for company, row in zip((self.a.bank_ab, self.a.fonder, self.a.liv), listed, strict=True):
            with self.subTest(company=company.name):
                regulations = self.regulations(company, limit=100)
                self.assertEqual(regulations["total"], len(regulations["items"]))
                every_row: list[dict[str, Any]] = []
                for regulation in regulations["items"]:
                    rows = self.rows(company, regulation["instrument"]["key"], limit=100)["items"]
                    self.assertEqual(counts(regulation), tally(rows), regulation["instrument"]["key"])
                    self.assertGreater(regulation["offered"], 0)
                    every_row += rows
                self.assertEqual(counts(row), tally(every_row))
                self.assertEqual(row["offered"], row["applies"] + row["notApplicable"] + row["underAssessment"])
                self.assertLessEqual(row["toDecide"], row["underAssessment"])
        self.assertEqual(
            [counts(row) for row in listed],
            [
                {"offered": 5, "applies": 1, "notApplicable": 1, "underAssessment": 3, "toDecide": 3},
                {"offered": 3, "applies": 0, "notApplicable": 0, "underAssessment": 3, "toDecide": 3},
                {"offered": 3, "applies": 0, "notApplicable": 0, "underAssessment": 3, "toDecide": 3},
            ],
        )

    def test_a_row_is_to_decide_exactly_while_no_person_has_answered_it_whatever_its_answer_reads(self) -> None:
        """A colleague's deliberate "under assessment" with a reason is an answer: the row
        still counts as under assessment, and no longer as to decide. A row that exists
        because somebody recorded a detail on it, with no answer, is still to decide."""
        officer = sign_in(self.a.officer, tenant=self.a.tenant)
        parked = self.client.put(
            f"{V1}/obligations/{self.nobody.id}/applicability",
            data={"orgUnitId": str(self.a.bank_ab.id), "applicability": "under_assessment", "reason": "Waiting for the legal opinion"},
            content_type="application/json",
            **officer,
        )
        self.assertEqual(parked.status_code, 200, parked.content)
        noted = self.client.patch(
            f"{V1}/obligations/{self.custody.id}/register/entities/{self.a.bank_ab.id}",
            data={"process": "Custody desk"},
            content_type="application/json",
            HTTP_IF_MATCH='"0"',
            **officer,
        )
        self.assertEqual(noted.status_code, 200, noted.content)
        everything = self.rows(self.a.bank_ab, "cv-lvm")["items"]
        to_decide = self.rows(self.a.bank_ab, "cv-lvm", state="to_decide")["items"]
        decided = self.rows(self.a.bank_ab, "cv-lvm", state="decided")["items"]
        # `decidedBy` is null exactly on the rows to decide.
        self.assertEqual(to_decide, [row for row in everything if row["decidedBy"] is None])
        self.assertEqual(decided, [row for row in everything if row["decidedBy"] is not None])
        self.assertEqual([(row["obligationId"], row["version"]) for row in to_decide], [(str(self.custody.id), noted.json()["version"])])
        [left_open] = [row for row in decided if row["obligationId"] == str(self.nobody.id)]
        self.assertEqual(
            (left_open["applicability"], left_open["reason"], left_open["decidedBy"]),
            ("under_assessment", "Waiting for the legal opinion", {"id": str(self.a.officer.id), "name": "Sara Lind"}),
        )
        of_the_bank = self.companies()[0]
        self.assertEqual(counts(of_the_bank), {"offered": 5, "applies": 1, "notApplicable": 1, "underAssessment": 3, "toDecide": 2})
        [securities] = [row for row in self.regulations(self.a.bank_ab)["items"] if row["instrument"]["key"] == "cv-lvm"]
        self.assertEqual(counts(securities), {"offered": 4, "applies": 1, "notApplicable": 1, "underAssessment": 2, "toDecide": 1})
        # The regulation's roll-up carries each company's own count: the bank's row is the bank's.
        self.assertEqual(
            {company["orgUnit"]["name"]: company["toDecide"] for company in self.roll_up("cv-lvm")["companies"]},
            {"Example Bank AB": 1, "Example Fonder AB": 3, "Example Liv Försäkring AB": 2},
        )

    def test_a_regulations_roll_up_is_the_inventorys_own_totals(self) -> None:
        for instrument in ("cv-lvm", "cv-lob"):
            with self.subTest(instrument=instrument):
                rolled = self.roll_up(instrument)
                self.assertEqual(rolled["inScope"], self.inventory_total(instrument))
                for answer in ANSWERS:
                    self.assertEqual(rolled[COUNT_OF[answer]], self.inventory_total(instrument, applicability=answer), answer)
                self.assertEqual(rolled["inScope"], rolled["applies"] + rolled["notApplicable"] + rolled["underAssessment"])
                self.assertEqual(sum(row["count"] for row in rolled["statuses"]), rolled["applies"])
                for row in rolled["statuses"]:
                    self.assertGreater(row["count"], 0)
                    self.assertEqual(row["count"], self.inventory_total(instrument, applicability="applies", complianceStatus=row["status"]["key"]))
                narrowed = {company["orgUnit"]["name"]: counts(company) for company in rolled["companies"]}
                for company in (self.a.bank_ab, self.a.fonder, self.a.liv):
                    rows = self.rows(company, instrument, limit=100)["items"]
                    self.assertEqual(narrowed.get(company.name), tally(rows) if rows else None)

    def test_the_roll_up_reads_as_seeded(self) -> None:
        rolled = self.roll_up("cv-lvm")
        self.assertEqual(
            {name: rolled[name] for name in ("inScope", "applies", "notApplicable", "underAssessment")},
            {"inScope": 4, "applies": 2, "notApplicable": 1, "underAssessment": 1},
        )
        tenancy.activate(self.a.tenant.id)
        scale = list(ComplianceStatus.objects.filter(key__in=("partly_compliant", "gap")).values_list("key", flat=True))
        self.assertEqual([row["status"]["key"] for row in rolled["statuses"]], scale, "the scale's order, zero counts left out")
        self.assertEqual(
            {row["status"]["key"]: (row["status"]["kind"], row["status"]["label"], row["count"]) for row in rolled["statuses"]},
            {"partly_compliant": ("partly", "Partly compliant", 1), "gap": ("gap", "Gap", 1)},
        )
        self.assertEqual([company["orgUnit"]["name"] for company in rolled["companies"]], ["Example Bank AB", "Example Fonder AB", "Example Liv Försäkring AB"])
        payments = self.roll_up("cv-lob")
        self.assertEqual(payments["statuses"], [])
        self.assertEqual(
            [company["orgUnit"]["name"] for company in payments["companies"]],
            ["Example Bank AB", "Example Liv Försäkring AB"],
            "a company it offers nothing for is left out",
        )


class RegulationsOfACompany(WhatAppliesCase):
    def test_the_regulations_come_in_key_order_with_the_instruments_own_reference(self) -> None:
        page = self.regulations(self.a.bank_ab)
        listed = {row["stableKey"]: row for row in self.ok("/instruments")["items"]}
        self.assertEqual([row["instrument"]["key"] for row in page["items"]], ["cv-lob", "cv-lvm"])
        for row in page["items"]:
            as_listed = listed[row["instrument"]["key"]]
            self.assertEqual(
                row["instrument"],
                {"id": as_listed["id"], "key": as_listed["stableKey"], "shortName": as_listed["shortName"], "jurisdiction": as_listed["jurisdiction"]},
            )
        self.assertEqual([row["instrument"]["key"] for row in self.regulations(self.a.fonder)["items"]], ["cv-lvm"])
        self.assertEqual([row["instrument"]["key"] for row in self.regulations(self.a.liv)["items"]], ["cv-lob", "cv-lvm"])

    def test_through_names_the_regime_and_the_companys_own_register_lines_behind_it(self) -> None:
        tenancy.activate(self.a.tenant.id)
        facts = registers_logic.register_facts(FI, MockRegisters().licence_facts(FI, "556000-0001"))  # type: ignore[arg-type]
        sources = registers_logic.term_sources(FI, facts)
        by_key = {row["instrument"]["key"]: row["through"] for row in self.regulations(self.a.bank_ab)["items"]}
        self.assertEqual(by_key["cv-lob"]["term"], {"key": "payments", "kind": None, "label": "Payments", "dimension": "regime"})
        self.assertEqual(by_key["cv-lob"]["lines"], sources[("regime", "payments")])
        self.assertEqual(by_key["cv-lvm"]["lines"], sources[("regime", "securities")])
        self.assertTrue(by_key["cv-lob"]["lines"] and by_key["cv-lvm"]["lines"])
        # A company with no register facts is offered the regulation all the same, through nothing it holds.
        for row in self.regulations(self.a.liv)["items"]:
            self.assertEqual(row["through"]["lines"], [])
            self.assertEqual(row["through"]["term"]["dimension"], "regime")

    def test_state_keeps_the_regulations_with_a_row_to_decide_or_with_one_a_person_answered(self) -> None:
        self.assertEqual(self.regulation_keys(self.a.bank_ab, state="to_decide"), ["cv-lob", "cv-lvm"])
        self.assertEqual(self.regulation_keys(self.a.bank_ab, state="decided"), ["cv-lvm"])
        self.assertEqual(self.regulations(self.a.fonder, state="decided"), {"items": [], "total": 0})
        # The counts stay the regulation's own, whatever the filter kept it for.
        [lvm] = self.regulations(self.a.bank_ab, state="decided")["items"]
        self.assertEqual(counts(lvm), {"offered": 4, "applies": 1, "notApplicable": 1, "underAssessment": 2, "toDecide": 2})
        # Kept exactly where the regulation's own count of that state is above zero.
        for company in (self.a.bank_ab, self.a.fonder, self.a.liv):
            everything = self.regulations(company)["items"]
            with self.subTest(company=company.name):
                self.assertEqual(self.regulation_keys(company, state="to_decide"), [row["instrument"]["key"] for row in everything if row["toDecide"]])
                self.assertEqual(
                    self.regulation_keys(company, state="decided"), [row["instrument"]["key"] for row in everything if row["offered"] > row["toDecide"]]
                )
        # A regulation leaves the to-decide list with its last unanswered row, and joins the other.
        answered = self.client.put(
            f"{V1}/obligations/{self.payments.id}/applicability",
            data={"orgUnitId": str(self.a.bank_ab.id), "applicability": "not_applicable", "reason": "No payment accounts"},
            content_type="application/json",
            **sign_in(self.a.officer, tenant=self.a.tenant),
        )
        self.assertEqual(answered.status_code, 200, answered.content)
        self.assertEqual(self.regulation_keys(self.a.bank_ab, state="to_decide"), ["cv-lvm"])
        self.assertEqual(self.regulation_keys(self.a.bank_ab, state="decided"), ["cv-lob", "cv-lvm"])

    def test_q_matches_as_the_instruments_list_does(self) -> None:
        for phrase, found in (("LOB", ["cv-lob"]), ("sfs 2007", ["cv-lvm"]), ("sfs", ["cv-lob", "cv-lvm"]), ("nothing-like-it", [])):
            with self.subTest(q=phrase):
                listed = {row["stableKey"] for row in self.ok("/instruments", {"q": phrase})["items"]}
                page = self.regulations(self.a.bank_ab, q=phrase)
                self.assertEqual([row["instrument"]["key"] for row in page["items"]], sorted(listed & {"cv-lob", "cv-lvm"}))
                self.assertEqual(([row["instrument"]["key"] for row in page["items"]], page["total"]), (found, len(found)))
        # The phrase and the state narrow together.
        self.assertEqual(self.regulation_keys(self.a.bank_ab, q="sfs", state="decided"), ["cv-lvm"])

    def test_the_page_is_cut_after_the_filters_and_the_total_is_not(self) -> None:
        first = self.regulations(self.a.bank_ab, limit=1)
        second = self.regulations(self.a.bank_ab, limit=1, offset=1)
        self.assertEqual(([row["instrument"]["key"] for row in first["items"]], first["total"]), (["cv-lob"], 2))
        self.assertEqual(([row["instrument"]["key"] for row in second["items"]], second["total"]), (["cv-lvm"], 2))
        self.assertEqual(self.regulations(self.a.bank_ab, offset=2), {"items": [], "total": 2})
        self.assertEqual(counts(second["items"][0]), counts(self.regulations(self.a.bank_ab)["items"][1]))


class RowsOfARegulation(WhatAppliesCase):
    def test_a_row_carries_exactly_the_published_fields_and_never_a_suggested_answer(self) -> None:
        for row in self.rows(self.a.bank_ab, "cv-lvm")["items"]:
            self.assertEqual(set(row), ROW_FIELDS)

    def test_matched_terms_are_the_duties_own_terms_the_company_carries(self) -> None:
        bank, fonder = ({row["obligationId"]: row["matchedTerms"] for row in self.rows(company, "cv-lvm")["items"]} for company in (self.a.bank_ab, self.a.fonder))
        entity_type = {"key": "bank", "kind": None, "label": "Bank", "dimension": "legal_entity"}
        self.assertEqual(bank[str(self.shared.id)], [entity_type], "its own entity-type term, and not the fund company's")
        self.assertEqual(bank[str(self.single.id)], [entity_type])
        self.assertEqual(bank[str(self.custody.id)], [{"key": "custody", "kind": None, "label": "Custody", "dimension": "service_type"}], "a term its register facts derive; never the client category beside it")
        self.assertEqual(bank[str(self.nobody.id)], [], "no own term: listed through its regulation's regime alone")
        # The fund company has no register facts: only its type can match.
        self.assertEqual(fonder[str(self.shared.id)], [{"key": "fund_company", "kind": None, "label": "Fund company", "dimension": "legal_entity"}])
        self.assertEqual(fonder[str(self.custody.id)], [])
        # The regime a duty inherits from its regulation is never a match, though the bank's facts derive it.
        self.assertEqual(self.rows(self.a.bank_ab, "cv-lob")["items"][0]["matchedTerms"], [])

    def test_state_filters_the_rows_and_the_total(self) -> None:
        self.assertEqual(self.row_ids(self.a.bank_ab, "cv-lvm", state="decided"), [str(self.shared.id), str(self.single.id)])
        self.assertEqual(self.row_ids(self.a.bank_ab, "cv-lvm", state="to_decide"), [str(self.nobody.id), str(self.custody.id)])
        self.assertEqual(self.rows(self.a.bank_ab, "cv-lvm", state="decided")["total"], 2)
        self.assertEqual(self.rows(self.a.bank_ab, "cv-lvm", state="to_decide", limit=1)["total"], 2)
        self.assertEqual(self.rows(self.a.liv, "cv-lvm", state="decided"), {"items": [], "total": 0})

    def test_the_page_is_cut_in_the_inventorys_order(self) -> None:
        everything = self.rows(self.a.bank_ab, "cv-lvm")
        self.assertEqual(everything["total"], 4)
        paged = [self.rows(self.a.bank_ab, "cv-lvm", limit=3, offset=offset) for offset in (0, 3, 6)]
        self.assertEqual([len(page["items"]) for page in paged], [3, 1, 0])
        self.assertEqual([row for page in paged for row in page["items"]], everything["items"])
        self.assertEqual({page["total"] for page in paged}, {4})

    def test_a_regulation_nobody_can_see_is_an_empty_page_as_in_the_inventory(self) -> None:
        private = library_build.instrument(key="cv-b-own", regime="regime:securities", owner_tenant=self.b.tenant)
        library_build.obligation(private, key="cv-b-own-duty", owner_tenant=self.b.tenant)
        for key in ("cv-b-own", "no-such-regulation"):
            with self.subTest(instrument=key):
                self.assertEqual(self.rows(self.a.bank_ab, key), {"items": [], "total": 0})
                self.assertEqual(self.ok("/obligations", {"instrument": key})["total"], 0)


class WhoMayRead(WhatAppliesCase):
    def routes(self, entity: Any = None, instrument: Any = None) -> list[str]:
        entity = entity or self.a.bank_ab.id
        return [
            f"{V1}/applicability/companies",
            f"{V1}/applicability/regulations?orgUnitId={entity}",
            f"{V1}/applicability/rows?orgUnitId={entity}&instrument=cv-lvm",
            f"{V1}/instruments/{instrument or self.shared.instrument_id}/applicability",
        ]

    def test_another_banks_legal_entity_and_what_is_no_active_legal_entity_are_404(self) -> None:
        department = factories.org_unit(self.a.tenant, name="Group Finance")
        closed = factories.legal_entity(self.a.tenant, name="Example Wound Down AB", active=False)
        cases = {"another bank's entity": self.b.bank_ab.id, "a department": department.id, "an inactive legal entity": closed.id, "an id nobody has": uuid.uuid4()}
        for case, entity_id in cases.items():
            for url in self.routes(entity=entity_id)[1:3]:
                with self.subTest(case=case, url=url):
                    response = self.client.get(url, **sign_in(self.a.owner, tenant=self.a.tenant))
                    self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"), response.content)
                    self.assertEqual(response.headers["Content-Type"], "application/problem+json")

    def test_a_regulation_private_to_another_bank_is_404_and_its_own_bank_reads_it(self) -> None:
        private = library_build.instrument(key="cv-b-private", regime="regime:securities", owner_tenant=self.b.tenant)
        library_build.obligation(private, key="cv-b-private-duty", owner_tenant=self.b.tenant)
        for instrument_id in (private.id, uuid.uuid4()):
            with self.subTest(instrument=instrument_id):
                response = self.get(f"/instruments/{instrument_id}/applicability")
                self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))
        own = self.ok(f"/instruments/{private.id}/applicability", who=self.b.owner, tenant=self.b.tenant)
        self.assertEqual((own["inScope"], own["underAssessment"]), (1, 1))

    def test_each_bank_reads_its_own_companies_and_answers_alone(self) -> None:
        listed = self.ok("/applicability/companies", who=self.b.owner, tenant=self.b.tenant)
        self.assertEqual([row["orgUnit"]["id"] for row in listed], [str(entity.id) for entity in (self.b.bank_ab, self.b.fonder, self.b.liv)])
        self.assertEqual({row["applies"] + row["notApplicable"] for row in listed}, {0}, "tenant A's answers are tenant A's")
        # No footprint and no exclusion in tenant B: the advice duty and the payments duty are offered there.
        self.assertEqual([(row["offered"], row["toDecide"]) for row in listed], [(6, 6), (5, 5), (4, 4)])
        rolled = self.ok(f"/instruments/{self.shared.instrument_id}/applicability", who=self.b.owner, tenant=self.b.tenant)
        self.assertEqual((rolled["inScope"], rolled["underAssessment"], rolled["statuses"]), (5, 5, []))

    def test_a_member_without_register_read_is_403_naming_it(self) -> None:
        who = user_principal(permissions=perms.TENANT_PERMISSIONS - {perms.REGISTER_READ}, tenant_id=self.a.tenant.id, subject_id=self.a.owner.id)
        with stub_session(who):
            for url in self.routes():
                with self.subTest(url=url):
                    response = self.client.get(url, HTTP_AUTHORIZATION=f"Bearer {SESSION_TOKEN_FOR_TESTS}")
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual((response.json()["code"], response.json()["requiredPermission"]), ("permission_denied", perms.REGISTER_READ))

    def test_a_key_is_refused_whatever_its_scopes_and_no_credential_is_401(self) -> None:
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES, tenant_id=self.a.tenant.id)):
            for url in self.routes():
                with self.subTest(url=url):
                    self.assertEqual(self.client.get(url, HTTP_X_API_KEY=API_KEY_FOR_TESTS).status_code, 401)
                    self.assertEqual(self.client.get(url).status_code, 401)

    def test_bad_input_is_422_in_the_usual_shape(self) -> None:
        entity = self.a.bank_ab.id
        cases = [
            "/applicability/regulations",
            "/applicability/regulations?orgUnitId=not-a-uuid",
            f"/applicability/regulations?orgUnitId={entity}&state=maybe",
            f"/applicability/regulations?orgUnitId={entity}&state=under_assessment",
            f"/applicability/regulations?orgUnitId={entity}&limit=101",
            f"/applicability/regulations?orgUnitId={entity}&q={'x' * 201}",
            f"/applicability/regulations?orgUnitId={entity}&q=sfs%00",  # PostgreSQL would refuse it with a 500
            f"/applicability/rows?orgUnitId={entity}",
            "/applicability/rows?instrument=cv-lvm",
            f"/applicability/rows?orgUnitId={entity}&instrument=cv-lvm&state=answered",
            f"/applicability/rows?orgUnitId={entity}&instrument=cv-lvm&state=applies",
            f"/applicability/rows?orgUnitId={entity}&instrument={'x' * 121}",
            f"/applicability/rows?orgUnitId={entity}&instrument=cv-lvm%00",
            f"/applicability/rows?orgUnitId={entity}&instrument=cv%20lvm",
            f"/applicability/rows?orgUnitId={entity}&instrument=cv-lvm&offset=-1",
            "/instruments/not-a-uuid/applicability",
        ]
        for path in cases:
            with self.subTest(path=path):
                response = self.client.get(f"{V1}{path}", **sign_in(self.a.owner, tenant=self.a.tenant))
                self.assertEqual((response.status_code, response.json()["code"]), (422, "validation_error"), response.content)

    def test_q_is_as_long_as_the_instruments_list_takes(self) -> None:
        self.assertEqual(register_schemas.QUERY_MAX, library_schemas.MAX_QUERY_LENGTH)

    def test_reading_writes_nothing(self) -> None:
        def stored() -> tuple[int, int, int]:
            tenancy.activate(self.a.tenant.id)
            return (TenantObligation.objects.count(), TenantObligationScope.objects.count(), AuditEvent.objects.filter(action__startswith="register.").count())

        before = stored()
        for url in self.routes():
            self.assertEqual(self.client.get(url, **sign_in(self.a.owner, tenant=self.a.tenant)).status_code, 200)
        self.assertEqual(stored(), before)


class ABankWithOneCompany(TestCase):
    def test_every_target_is_the_obligation_as_a_whole_and_the_answers_are_the_entrys(self) -> None:
        seed_library()
        tenant = factories.tenant(slug="cv-solo")
        officer = factories.member(tenant, roles=("compliance_officer",), user_row=factories.user(name="Sara Lind")).user
        only = factories.legal_entity(tenant, name="Example Bank AB", entity_term_id=library_build.term("legal_entity:bank").id)
        law = library_build.instrument(key="cv-solo-lvm", regime="regime:securities")
        answered = library_build.obligation(law, key="cv-solo-1", ref_label="1 §")
        waiting = library_build.obligation(law, key="cv-solo-2", ref_label="2 §", terms=("legal_entity:bank",))
        library_build.obligation(law, key="cv-solo-3", ref_label="3 §", terms=("legal_entity:insurer",))
        headers = sign_in(officer, tenant=tenant)
        stored = self.client.put(
            f"{V1}/obligations/{answered.id}/applicability", data={"applicability": "applies", "reason": "We are a bank"}, content_type="application/json", **headers
        )
        self.assertEqual(stored.status_code, 200, stored.content)
        page = self.client.get(f"{V1}/applicability/rows", {"orgUnitId": str(only.id), "instrument": "cv-solo-lvm"}, **headers).json()
        self.assertEqual(
            [(row["obligationId"], row["orgUnitId"], row["applicability"], row["reason"], row["version"]) for row in page["items"]],
            [(str(answered.id), None, "applies", "We are a bank", stored.json()["version"]), (str(waiting.id), None, "under_assessment", None, 0)],
        )
        [company] = self.client.get(f"{V1}/applicability/companies", **headers).json()
        self.assertEqual(counts(company), {"offered": 2, "applies": 1, "notApplicable": 0, "underAssessment": 1, "toDecide": 1})

    def test_a_bank_with_no_legal_entity_reads_an_empty_list(self) -> None:
        seed_library()
        tenant = factories.tenant(slug="cv-none")
        reader = factories.member_user(tenant)
        law = library_build.instrument(key="cv-none-lvm", regime="regime:securities")
        library_build.obligation(law, key="cv-none-1")
        factories.org_unit(tenant, name="Group Finance")
        response = self.client.get(f"{V1}/applicability/companies", **sign_in(reader, tenant=tenant))
        self.assertEqual((response.status_code, response.json()), (200, []))
        rolled = self.client.get(f"{V1}/instruments/{law.id}/applicability", **sign_in(reader, tenant=tenant)).json()
        self.assertEqual((rolled["inScope"], rolled["underAssessment"], rolled["companies"]), (1, 1, []))


# ---------------------------------------------------------------------------------------
# The same number of queries whatever the page, the library and the organisation hold
# ---------------------------------------------------------------------------------------
# What each read asks, pinned so a lookup that turns per row, per regulation or per company
# shows up here. Each is the logic alone, without the session's own queries.
#
# Every read: the legal entities (1), their exclusions (1) and the terms of the dimensions
# the span checks (1), then the obligations with every company's span (1): four.
#   companies    + the answered entries and the answered entity rows (2).
#   regulations  + the answered entries and the company's answered rows (2), the regulations
#                in key order and the page's rows (2), the labels of their jurisdictions and
#                of their regimes (2), and the company's register facts (1).
#   rows         + the regulation's entries and the company's rows on them (2), the page's
#                headings (2), its own scope terms (1), the labels of those the company
#                carries (1) and the company's register facts (1).
#   roll-up      + the regulation (1), the bank's answers and shown statuses on its duties (1),
#                the statuses and their labels (2), and the answered entries and entity rows (2).
COMPANIES_QUERIES = 6
REGULATIONS_QUERIES = 11
ROWS_QUERIES = 11
ROLL_UP_QUERIES = 10


class TheSameQueriesWhateverThePage(WhatAppliesCase):
    def reads(self, limit: int) -> None:
        tenant, order = self.a.tenant, ["en"]
        tenancy.activate(tenant.id)
        with self.assertNumQueries(COMPANIES_QUERIES):
            company_view.list_companies(tenant=tenant)
        with self.assertNumQueries(REGULATIONS_QUERIES):
            company_view.list_regulations(
                tenant=tenant, order=order, query=register_schemas.RegisterApplicabilityRegulationQuery(org_unit_id=self.a.bank_ab.id), limit=limit, offset=0
            )
        with self.assertNumQueries(ROWS_QUERIES):
            company_view.list_rows(
                tenant=tenant,
                order=order,
                query=register_schemas.RegisterApplicabilityAnswerQuery(org_unit_id=self.a.bank_ab.id, instrument="cv-lvm"),
                limit=limit,
                offset=0,
            )
        with self.assertNumQueries(ROLL_UP_QUERIES):
            company_view.instrument_applicability(tenant=tenant, order=order, instrument_id=self.shared.instrument_id)

    def test_a_page_of_one_and_a_page_of_a_hundred_cost_the_same_and_so_does_a_larger_library(self) -> None:
        self.reads(limit=1)
        self.reads(limit=100)
        # More duties, more regulations, more companies with exclusions and more answers.
        for number in range(6):
            law = library_build.instrument(key=f"cv-more-{number}", regime="regime:securities")
            for index in range(4):
                library_build.obligation(law, key=f"cv-more-{number}-{index}", terms=("legal_entity:bank",) if index % 2 else ())
            library_build.obligation(self.shared.instrument, key=f"cv-lvm-9{number}", ref_label=f"9{number} §")
        extra = factories.legal_entity(self.a.tenant, name="Example Kort AB", entity_term_id=library_build.term("legal_entity:bank").id)
        exclude(self.a.tenant, extra, "service_type:advice", "licensed_activity:card_issuing")
        answered = self.client.put(
            f"{V1}/obligations/{self.nobody.id}/applicability",
            data={"orgUnitId": str(extra.id), "applicability": "applies", "reason": "Card business"},
            content_type="application/json",
            **sign_in(self.a.officer, tenant=self.a.tenant),
        )
        self.assertEqual(answered.status_code, 200, answered.content)
        self.reads(limit=1)
        self.reads(limit=100)
