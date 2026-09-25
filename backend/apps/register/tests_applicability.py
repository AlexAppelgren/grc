"""Setting applicability (REG-01, D-75, D-42, AC-REG1): one person holding
`applicability.approve` stores the answer at once, for the obligation, one legal entity it
spans, or many rows in one call. Proved through the routes, as a real session without a
step-up: the stored row, the one audit event per row with the value before and after and the
reason, the scope row created in the write's transaction, the refusals that store nothing,
the cap, the pinned query count of a batch, and that no status or gap moves.

Proven to fail 2026-09-25: with the span check removed the fund company was answered on a
bank-only duty; with the version check removed the stale write landed; with the per-row
`record()` removed the audit counts named each route."""

from __future__ import annotations

import uuid
from typing import Any

from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext, override_settings

from apps.library import testing as library_build
from apps.library.models import Obligation
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.register.applicability import APPLICABILITY_SET, entities_spanned
from apps.register.models import Gap, TenantObligation, TenantObligationScope
from apps.shared import factories, tenancy
from apps.shared.models import AuditEvent, Tenant
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import ComplianceStatus, GapSource, GapStatus, RiskRating
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms

V1 = "/api/v1"
# What a register write audits; a sign-in writes audit rows of its own, which are not counted.
REGISTER_SUBJECTS = ("tenant_obligation",)


class Bank:
    """One bank with three legal entities, as the prototype's Example Group has them, a
    compliance officer holding `applicability.approve` and an owner who does not."""

    def __init__(self, slug: str) -> None:
        self.tenant = factories.tenant(slug=slug)
        self.officer = factories.member(
            self.tenant, roles=("compliance_officer",), user_row=factories.user(name="Sara Lind")
        ).user
        self.owner = factories.member_user(self.tenant, roles=("owner",))
        self.bank_ab = factories.legal_entity(
            self.tenant, name="Example Bank AB", entity_term_id=library_build.term("legal_entity:bank").id
        )
        self.fonder = factories.legal_entity(
            self.tenant, name="Example Fonder AB", entity_term_id=library_build.term("legal_entity:fund_company").id
        )
        self.liv = factories.legal_entity(
            self.tenant, name="Example Liv Försäkring AB", entity_term_id=library_build.term("legal_entity:insurer").id
        )


def seed_library() -> None:
    """The reference rows a library builder names: languages, jurisdictions, lists and terms."""
    seed_languages()
    seed_jurisdictions()
    seed_library_vocabularies()
    seed_taxonomy_terms()


def banks_duty() -> Obligation:
    """A duty on banks alone: it spans Example Bank AB and neither the fund company nor the insurer."""
    law = library_build.instrument(key="lbf", short_name="LBF", regime="regime:securities")
    return library_build.obligation(law, key="lbf-client-assets", ref_label="7 kap. 1 §", terms=("legal_entity:bank",))


class ApplicabilityTestCase(ScenarioTestCase):
    a: Bank
    b: Bank
    duty: Obligation
    standard: Obligation

    @classmethod
    def setUpTestData(cls) -> None:
        seed_library()
        cls.a = Bank("appl-a")
        cls.b = Bank("appl-b")
        cls.duty = banks_duty()
        cls.standard = library_build.standard()

    def put(self, obligation: Any, body: dict[str, Any], *, who: Any = None, if_match: int | None = None) -> Any:
        headers = sign_in(who or self.a.officer, tenant=self.a.tenant)
        if if_match is not None:
            headers["HTTP_IF_MATCH"] = f'"{if_match}"'
        return self.client.put(
            f"{V1}/obligations/{getattr(obligation, 'id', obligation)}/applicability",
            data=body,
            content_type="application/json",
            **headers,
        )

    def post_many(self, rows: list[dict[str, Any]], *, who: Any = None) -> Any:
        return self.client.post(
            f"{V1}/applicability",
            data={"rows": rows},
            content_type="application/json",
            **sign_in(who or self.a.officer, tenant=self.a.tenant),
        )

    def counts(self, tenant: Tenant | None = None) -> dict[str, int]:
        """Every row a write here could leave behind, in `tenant`'s zone."""
        with transaction.atomic():
            tenancy.activate((tenant or self.a.tenant).id)
            return {
                "entries": TenantObligation.objects.count(),
                "scopes": TenantObligationScope.objects.count(),
                "gaps": Gap.objects.count(),
                "audit": AuditEvent.objects.filter(subject_type__in=REGISTER_SUBJECTS).count(),
            }

    def scope_of(self, obligation: Obligation, entity: Any) -> TenantObligationScope:
        self.activate(self.a.tenant)
        return TenantObligationScope.objects.get(tenant_obligation__obligation=obligation, org_unit=entity, product__isnull=True)

    def answers(self) -> list[AuditEvent]:
        self.activate(self.a.tenant)
        return list(AuditEvent.objects.filter(action=APPLICABILITY_SET, tenant_id=self.a.tenant.id).order_by("created", "id"))


class SettingOneAnswer(ApplicabilityTestCase):
    def test_an_entity_answer_is_stored_at_once_with_its_scope_row_and_one_audit_event(self) -> None:
        response = self.put(self.duty, {"orgUnitId": str(self.a.bank_ab.id), "applicability": "applies", "reason": "Holds client assets"})
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(
            {key: body[key] for key in ("obligationId", "orgUnitId", "unitId", "applicability", "reason", "version")},
            {
                "obligationId": str(self.duty.id),
                "orgUnitId": str(self.a.bank_ab.id),
                "unitId": None,
                "applicability": "applies",
                "reason": "Holds client assets",
                "version": 1,
            },
        )
        self.assertEqual(body["decidedBy"], {"id": str(self.a.officer.id), "name": "Sara Lind"})
        scope = self.scope_of(self.duty, self.a.bank_ab)
        self.assertEqual(
            (scope.applicability, scope.applicability_reason, scope.applicability_decided_by_id),
            ("applies", "Holds client assets", self.a.officer.id),
        )
        self.assertIsNotNone(scope.applicability_decided_at)
        [event] = self.answers()
        self.assertEqual((event.actor_id, event.subject_type, event.subject_id), (self.a.officer.id, "tenant_obligation", scope.tenant_obligation_id))
        self.assertEqual(event.subject_title, "LBF, 7 kap. 1 §, Example Bank AB")
        self.assertEqual(event.before, {"applicability": "under_assessment", "reason": None})
        self.assertEqual(
            event.after,
            {"obligationId": str(self.duty.id), "orgUnitId": str(self.a.bank_ab.id), "applicability": "applies", "reason": "Holds client assets"},
        )

    def test_the_obligation_as_a_whole_is_answered_on_the_entry_with_if_match(self) -> None:
        first = self.put(self.duty, {"applicability": "not_applicable", "reason": "No client money held"}, if_match=0)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json()["orgUnitId"], None)
        again = self.put(self.duty, {"applicability": "applies", "reason": "Client money from 2027"}, if_match=first.json()["version"])
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(again.json()["version"], first.json()["version"] + 1)
        self.activate(self.a.tenant)
        entry = TenantObligation.objects.get(obligation=self.duty)
        self.assertEqual((entry.applicability, entry.applicability_reason), ("applies", "Client money from 2027"))
        last = self.answers()[-1]
        self.assertEqual(last.before, {"applicability": "not_applicable", "reason": "No client money held"})
        self.assertEqual(last.subject_type, "tenant_obligation")

    def test_a_stale_if_match_is_409_and_changes_nothing(self) -> None:
        body = {"orgUnitId": str(self.a.bank_ab.id), "applicability": "applies", "reason": "Certified"}
        self.assertEqual(self.put(self.duty, body, if_match=0).status_code, 200)
        before = self.counts()
        response = self.put(self.duty, {**body, "applicability": "not_applicable"}, if_match=0)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "stale_write")
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.scope_of(self.duty, self.a.bank_ab).applicability, "applies")

    def test_what_the_bank_cannot_see_or_the_obligation_does_not_span_is_404_and_stores_nothing(self) -> None:
        private = library_build.obligation(
            library_build.instrument(key="b-own", regime="regime:securities", owner_tenant=self.b.tenant),
            key="b-own-duty",
            owner_tenant=self.b.tenant,
        )
        department = factories.legal_entity(self.a.tenant, name="Group Finance")
        with transaction.atomic():
            tenancy.activate(self.a.tenant.id)
            department.kind = "function"
            department.save(update_fields=["kind"])
        closed = factories.legal_entity(self.a.tenant, name="Example Wound Down AB", active=False)
        cases = {
            "another bank's private obligation": (private.id, None),
            "an obligation that does not exist": (uuid.uuid4(), None),
            "another bank's entity": (self.duty.id, self.b.bank_ab.id),
            "an org unit that is not a legal entity": (self.duty.id, department.id),
            "an inactive legal entity": (self.duty.id, closed.id),
            "an entity the duty does not span": (self.duty.id, self.a.fonder.id),
        }
        before = self.counts()
        for case, (obligation_id, entity_id) in cases.items():
            body: dict[str, Any] = {"applicability": "applies", "reason": "Certified"}
            if entity_id is not None:
                body["orgUnitId"] = str(entity_id)
            with self.subTest(case):
                response = self.put(obligation_id, body)
                self.assertEqual(response.status_code, 404, response.content)
                self.assertEqual(response.json()["code"], "not_found")
        self.assertEqual(self.counts(), before)

    def test_applies_and_we_comply_stay_separate_facts(self) -> None:
        """Turning an obligation to "does not apply" leaves its status and its gaps as they were."""
        self.assertEqual(self.put(self.duty, {"applicability": "applies", "reason": "Client money"}).status_code, 200)
        self.activate(self.a.tenant)
        entry = TenantObligation.objects.get(obligation=self.duty)
        gap_status = ComplianceStatus.objects.get(key="gap")
        TenantObligation.objects.filter(pk=entry.pk).update(compliance_status=gap_status, status_note="Weekly, not daily")
        Gap.objects.create(
            tenant=self.a.tenant,
            tenant_obligation=entry,
            title="Reconciliation is weekly",
            severity=RiskRating.objects.get(key="high"),
            source=GapSource.objects.get(key="audit"),
            status=GapStatus.objects.get(key="open"),
            identified_by=self.a.officer,
        )
        response = self.put(self.duty, {"applicability": "not_applicable", "reason": "Client money moved to the group"})
        self.assertEqual(response.status_code, 200, response.content)
        self.activate(self.a.tenant)
        entry.refresh_from_db()
        self.assertEqual((entry.applicability, entry.compliance_status_id, entry.status_note), ("does_not_apply", gap_status.id, "Weekly, not daily"))
        self.assertEqual(list(Gap.objects.filter(tenant_obligation=entry).values_list("title", "status__key")), [("Reconciliation is weekly", "open")])

    def test_a_unit_the_bank_does_not_have_is_404_and_stores_nothing(self) -> None:
        """c8-units-paste-soa: a unit's own answers are proved in tests_units.py."""
        before = self.counts()
        response = self.put(self.standard, {"unitId": str(uuid.uuid4()), "applicability": "applies", "reason": "In scope"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "not_found")
        self.assertEqual(self.counts(), before)


class TheSpan(ApplicabilityTestCase):
    def test_a_duty_spans_its_entity_terms_and_a_conformance_obligation_every_entity_and_reading_writes_nothing(self) -> None:
        unset = factories.legal_entity(self.a.tenant, name="Example Holding AB")
        before = self.counts()
        self.activate(self.a.tenant)
        spanned = entities_spanned({self.duty.id, self.standard.id})
        self.assertEqual({row.id for row in spanned[self.duty.id]}, {self.a.bank_ab.id, unset.id})
        self.assertEqual(
            {row.id for row in spanned[self.standard.id]}, {self.a.bank_ab.id, self.a.fonder.id, self.a.liv.id, unset.id}
        )
        self.assertEqual(self.counts(), before)


class SettingManyAnswers(ApplicabilityTestCase):
    def rows(self) -> list[dict[str, Any]]:
        return [
            {"obligationId": str(self.standard.id), "orgUnitId": str(self.a.bank_ab.id), "applicability": "applies", "reason": "Certified"},
            {"obligationId": str(self.standard.id), "orgUnitId": str(self.a.liv.id), "applicability": "not_applicable", "reason": "Not certified"},
            {"obligationId": str(self.duty.id), "applicability": "applies", "reason": "Client money"},
        ]

    def test_every_row_is_stored_with_one_audit_event_each_in_the_order_sent(self) -> None:
        response = self.post_many(self.rows())
        self.assertEqual(response.status_code, 200, response.content)
        items = response.json()["items"]
        self.assertEqual(
            [(item["obligationId"], item["orgUnitId"], item["applicability"]) for item in items],
            [(row["obligationId"], row.get("orgUnitId"), row["applicability"]) for row in self.rows()],
        )
        events = self.answers()
        self.assertEqual(len(events), len(self.rows()))
        self.assertEqual({event.actor_id for event in events}, {self.a.officer.id})
        self.assertEqual([event.after["reason"] for event in events], [row["reason"] for row in self.rows()])
        self.assertEqual(self.scope_of(self.standard, self.a.liv).applicability, "does_not_apply")

    def test_one_refused_row_stores_nothing_at_all(self) -> None:
        before = self.counts()
        rows = [*self.rows(), {"obligationId": str(self.duty.id), "orgUnitId": str(self.b.bank_ab.id), "applicability": "applies", "reason": "x"}]
        response = self.post_many(rows)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.counts(), before)

    def test_a_row_twice_is_422_and_stores_nothing(self) -> None:
        before = self.counts()
        rows = [*self.rows(), {**self.rows()[0], "applicability": "not_applicable"}]
        response = self.post_many(rows)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")
        self.assertEqual(self.counts(), before)

    def test_a_call_over_the_cap_is_422_and_stores_nothing(self) -> None:
        before = self.counts()
        with override_settings(REGISTER_BULK_MAX=2):
            response = self.post_many(self.rows())
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")
        self.assertEqual(self.counts(), before)
        with override_settings(REGISTER_BULK_MAX=3):
            self.assertEqual(self.post_many(self.rows()).status_code, 200)

    def test_only_a_holder_of_applicability_approve_sets_many(self) -> None:
        before = self.counts()
        response = self.post_many(self.rows(), who=self.a.owner)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["requiredPermission"], "applicability.approve")
        self.assertEqual(self.counts(), before)

    def test_the_query_count_is_pinned_and_grows_by_a_fixed_step_per_row(self) -> None:
        """Every lookup is one query for the whole call; only each row's write and its audit
        event are per row. Measured on answers to rows that exist, so no creation is counted,
        and net of what the session and the route cost before the logic runs, which a call
        refused over the cap measures."""
        entities = [factories.legal_entity(self.a.tenant, name=f"Example Entity {n} AB") for n in range(4)]

        def call(count: int, applicability: str, *, expect: int = 200) -> int:
            rows = [
                {"obligationId": str(self.standard.id), "orgUnitId": str(entity.id), "applicability": applicability, "reason": "Certified"}
                for entity in entities[:count]
            ]
            headers = sign_in(self.a.officer, tenant=self.a.tenant)
            with CaptureQueriesContext(connection) as queries:
                response = self.client.post(f"{V1}/applicability", data={"rows": rows}, content_type="application/json", **headers)
            self.assertEqual(response.status_code, expect, response.content)
            return len(queries)

        call(4, "applies")  # creates the entry and the four scope rows
        with override_settings(REGISTER_BULK_MAX=1):
            gate = call(2, "applies", expect=422)
        two, four = call(2, "not_applicable"), call(4, "not_applicable")
        self.assertEqual(four - two, 2 * ROW_QUERIES)
        self.assertEqual(two - gate, BATCH_QUERIES + 2 * ROW_QUERIES)


# Each row: its UPDATE, then record()'s savepoint, audit row, outbox row and release.
ROW_QUERIES = 5
# Once per call, whatever its length: the obligations and their titles (2), the legal
# entities (1) and the scope rule (5), and the locking reads of the entries and the scope
# rows (2). Pinned so a lookup that turns per-row shows up here.
BATCH_QUERIES = 10


# c8-ui-applicability-status: the legal entities an answer can be given for, read before any
# row exists, so the obligation page offers each one (REG-01, REG-S12, D-42).
class SpannedEntities(ApplicabilityTestCase):
    def get_span(self, obligation: Any, *, who: Any = None, tenant: Tenant | None = None) -> Any:
        return self.client.get(
            f"{V1}/obligations/{getattr(obligation, 'id', obligation)}/register/entities",
            **sign_in(who or self.a.officer, tenant=tenant or self.a.tenant),
        )

    def test_a_standard_spans_every_entity_by_name_and_reading_it_writes_nothing(self) -> None:
        before = self.counts()
        response = self.get_span(self.standard)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json(),
            [{"orgUnitId": str(entity.id), "orgUnitName": entity.name} for entity in (self.a.bank_ab, self.a.fonder, self.a.liv)],
        )
        self.assertEqual(self.counts(), before)

    def test_a_bank_duty_spans_the_bank_alone_and_the_span_is_the_one_the_write_checks(self) -> None:
        names = [row["orgUnitName"] for row in self.get_span(self.duty).json()]
        self.assertEqual(names, ["Example Bank AB"])
        self.assertEqual(names, [entity.name for entity in entities_spanned([self.duty.id])[self.duty.id]])

    def test_any_member_who_reads_the_register_sees_it_and_only_their_own_bank(self) -> None:
        self.assertEqual(self.get_span(self.duty, who=self.a.owner).status_code, 200)
        ids = {row["orgUnitId"] for row in self.get_span(self.standard, who=self.b.officer, tenant=self.b.tenant).json()}
        self.assertEqual(ids, {str(entity.id) for entity in (self.b.bank_ab, self.b.fonder, self.b.liv)})

    def test_an_obligation_the_bank_cannot_see_is_404(self) -> None:
        private = library_build.obligation(
            library_build.instrument(key="b-span", regime="regime:securities", owner_tenant=self.b.tenant),
            key="b-span-duty",
            owner_tenant=self.b.tenant,
        )
        for obligation_id in (private.id, uuid.uuid4()):
            with self.subTest(obligation=obligation_id):
                response = self.get_span(obligation_id)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json()["code"], "not_found")

    def test_the_read_is_a_fixed_handful_of_queries(self) -> None:
        with CaptureQueriesContext(connection) as one:
            self.get_span(self.duty)
        factories.legal_entity(self.a.tenant, name="Example Kort AB", entity_term_id=library_build.term("legal_entity:bank").id)
        with CaptureQueriesContext(connection) as two:
            self.assertEqual(len(self.get_span(self.duty).json()), 2)
        self.assertEqual(len(one), len(two))
