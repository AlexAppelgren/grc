"""Statement of Applicability units (register 0003, `units.py`; REG-08, D-41, AC-REG2).

The table, proved as cw_app on committed rows: tenant B sees none of tenant A's units, the
database refuses every reference to another tenant's row (walking the migration's own
`COMPOSITE_KEYS`), one live unit per scope row and reference, and a unit is never deleted.
The rules, proved through the routes: a unit exists only under a standard (422
`units_only_under_standards`) for an entity whose conformance row applies (422
`scope_not_applicable`); it is added, listed per entity, renamed with `If-Match` and removed
by a stamp, each with one audit event, until it has a decision, a status or a gap (409
`unit_has_history`); and a paste's dry run reports every line and stores nothing.

Written before the logic: every route test failed with 501 `not_built` against the stubs,
and the table tests failed on the missing `soa_unit` table."""

from __future__ import annotations

import importlib
import json
import sys
import time
import uuid
from typing import Any
from unittest import mock

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DEFAULT_DB_ALIAS, IntegrityError, connection, transaction
from django.test import Client, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.library import testing as library_testing
from apps.library.models import Obligation
from apps.library.reading import obligation_scopes
from apps.register import applicability, logic, units
from apps.register.models import Applicability, Gap, SoaUnit, TenantObligationScope
from apps.register.tests_models import APP, Register, _seed_library
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.models import AuditEvent, Tenant
from apps.shared.testing import ScenarioTestCase, sign_in, stub_session, user_principal
from apps.taxonomy.models import ComplianceStatus, FootprintTerm, GapSource, GapStatus, RiskRating
from apps.tenants.models import OrgUnit, OrgUnitKind

COMPOSITE_KEYS = importlib.import_module("apps.register.migrations.0003_soa_unit").COMPOSITE_KEYS
V1 = "/api/v1"


# ---------------------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------------------
class UnitRegister(Register):
    """A bank's register with its entity's conformance row, a unit under it and a gap on
    the unit, every row written as cw_app in its own zone."""

    def __init__(self, tenant: Tenant, obligation: Obligation) -> None:
        super().__init__(tenant, obligation)
        with transaction.atomic(using=APP):
            tenancy.activate(tenant.id, using=APP)
            self.entity_scope = self.create(
                TenantObligationScope,
                tenant_obligation_id=self.entry.id,
                org_unit_id=self.organisation.entity.id,
                applicability=Applicability.APPLIES.value,
                compliance_status_id=self.status.id,
            )
            self.unit_fields = {
                "scope_id": self.entity_scope.id,
                "reference": "X.1",
                "title": "Our own words",
                "compliance_status_id": self.status.id,
            }
            self.unit = self.create(
                SoaUnit, **self.unit_fields, applicability_decided_by_id=self.user_id, removed_by_id=self.user_id
            )
            Gap.objects.using(APP).filter(pk=self.gap.pk).update(unit_id=self.unit.id)

    def target(self, table: str) -> uuid.UUID:
        return self.unit.id if table == "soa_unit" else super().target(table)

    def row(self, table: str) -> Any:
        return self.unit if table == "soa_unit" else super().row(table)


class UnitTableUnderRowLevelSecurity(TransactionTestCase):
    databases = {DEFAULT_DB_ALIAS, APP}

    def setUp(self) -> None:
        _seed_library()
        standard = library_testing.standard()
        self.a = UnitRegister(factories.tenant(slug="units-a"), standard)
        self.b = UnitRegister(factories.tenant(slug="units-b"), standard)

    def test_each_tenant_sees_only_its_own_units(self) -> None:
        for register in (self.a, self.b):
            with transaction.atomic(using=APP):
                tenancy.activate(register.tenant.id, using=APP)
                self.assertEqual(set(SoaUnit.objects.using(APP).values_list("id", flat=True)), {register.unit.id})

    def test_the_database_refuses_every_reference_to_another_tenants_row(self) -> None:
        a, b = self.a, self.b
        for table, column, target, _ in COMPOSITE_KEYS:
            constraint = f"{table}_{column}_same_tenant"
            with self.subTest(constraint), transaction.atomic(using=APP):
                tenancy.activate(a.tenant.id, using=APP)
                with self.assertRaisesMessage(IntegrityError, constraint), transaction.atomic(using=APP):
                    row = a.row(table)
                    type(row)._default_manager.using(APP).filter(pk=row.pk).update(**{column: b.target(target)})

    def test_one_live_unit_per_entity_and_reference_and_a_removal_frees_it(self) -> None:
        a = self.a
        with transaction.atomic(using=APP):
            tenancy.activate(a.tenant.id, using=APP)
            with self.assertRaisesMessage(IntegrityError, "soa_unit_live_reference_unique"), transaction.atomic(using=APP):
                a.create(SoaUnit, **a.unit_fields)
            SoaUnit.objects.using(APP).filter(pk=a.unit.pk).update(removed_at=timezone.now())
            again = a.create(SoaUnit, **a.unit_fields)
            self.assertEqual(SoaUnit.objects.using(APP).filter(reference="X.1").count(), 2)
            self.assertNotEqual(again.id, a.unit.id)

    def test_a_unit_is_never_deleted(self) -> None:
        with self.assertRaises(ValidationError) as refused:
            self.a.unit.delete(using=APP)
        self.assertEqual(refused.exception.code, "remove_not_delete")


# ---------------------------------------------------------------------------------------
# The rules, through the routes
# ---------------------------------------------------------------------------------------
class UnitWorld(ScenarioTestCase):
    """One bank with a standard its Bank AB follows, Liv does not and Finance never answered,
    and a duty that is not under a standard. Holds no test, so each class below runs only its own."""

    def setUp(self) -> None:
        _seed_library()
        self.tenant = factories.tenant(slug="units-bank")
        self.officer = factories.member_user(self.tenant, roles=("compliance_officer",))
        self.standard = library_testing.standard()
        act = library_testing.instrument(key="units-act", regime="regime:securities")
        self.not_a_standard = library_testing.obligation(act, key="units-act-duty")
        self.activate(self.tenant)
        self.status = ComplianceStatus.objects.get(is_default=True)
        self.bank_ab = self._entity("Bank AB")
        self.liv = self._entity("Liv AB")
        self.finance = self._entity("Finance AB")
        entry = logic.ensure_register_entry(
            tenant_id=self.tenant.id, obligation_id=self.standard.id, actor=factories.user_actor(user_id=self.officer.id)
        )
        other_entry = logic.ensure_register_entry(
            tenant_id=self.tenant.id, obligation_id=self.not_a_standard.id, actor=factories.user_actor(user_id=self.officer.id)
        )
        self.bank_ab_scope = self._scope(entry.id, self.bank_ab, Applicability.APPLIES)
        self._scope(entry.id, self.liv, Applicability.DOES_NOT_APPLY)
        self._scope(other_entry.id, self.bank_ab, Applicability.APPLIES)
        self.who = user_principal(
            permissions={perms.REGISTER_READ, perms.REGISTER_EDIT}, tenant_id=self.tenant.id, subject_id=self.officer.id
        )
        self.decider = user_principal(
            permissions={perms.REGISTER_READ, perms.REGISTER_EDIT, perms.APPLICABILITY_APPROVE},
            tenant_id=self.tenant.id,
            subject_id=self.officer.id,
        )

    # --- fixtures ----------------------------------------------------------------------
    def _entity(self, name: str) -> OrgUnit:
        return OrgUnit.objects.create(tenant=self.tenant, kind=OrgUnitKind.LEGAL_ENTITY.value, name=name)

    def _scope(self, entry_id: uuid.UUID, entity: OrgUnit, applicability: Applicability) -> TenantObligationScope:
        return TenantObligationScope.objects.create(
            tenant=self.tenant,
            tenant_obligation_id=entry_id,
            org_unit=entity,
            applicability=applicability.value,
            applicability_reason="Certified",
            applicability_decided_at=timezone.now(),
            applicability_decided_by=self.officer,
            compliance_status=self.status,
        )

    def _call(
        self, method: str, path: str, body: Any = None, *, version: int | None = None, who: Any = None, client: Any = None
    ) -> Any:
        """A request as `who`, the officer by default. A dry run writes nothing by design, so
        it passes a plain `Client()` instead of the one that demands an audit row."""
        client = client or self.client
        headers = self.as_user(self.who)
        if version is not None:
            headers["HTTP_IF_MATCH"] = f'"{version}"'
        with stub_session(who or self.who):
            if body is None:
                return client.generic(method, V1 + path, **headers)
            return client.generic(method, V1 + path, data=json.dumps(body), content_type="application/json", **headers)

    def _add(self, reference: str = "X.1", title: str = "Our access rules", *, entity: OrgUnit | None = None, obligation: Obligation | None = None) -> Any:
        body = {"orgUnitId": str((entity or self.bank_ab).id), "reference": reference, "title": title}
        return self._call("POST", f"/obligations/{(obligation or self.standard).id}/units", body)

    def _unit(self, reference: str = "X.1") -> SoaUnit:
        response = self._add(reference)
        self.assertEqual(response.status_code, 201, response.content)
        self.activate(self.tenant)
        return SoaUnit.objects.get(pk=response.json()["id"])

    def _events(self, action: str) -> list[AuditEvent]:
        self.activate(self.tenant)
        return list(AuditEvent.objects.filter(action=action).order_by("created", "id"))

    def _problem(self, response: Any, status: int, code: str) -> None:
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response.json()["code"], code)

    def _live(self) -> list[SoaUnit]:
        self.activate(self.tenant)
        return list(SoaUnit.objects.filter(removed_at__isnull=True).order_by("reference"))


class UnitRules(UnitWorld):
    # --- add and list ------------------------------------------------------------------
    def test_a_unit_is_added_undecided_with_one_audit_event_and_listed_per_entity(self) -> None:
        response = self._add("X.1", "  Our access rules  ")
        self.assertEqual(response.status_code, 201, response.content)
        unit = response.json()
        self.assertEqual(
            {k: unit[k] for k in ("obligationId", "orgUnitId", "reference", "title", "applicability", "hasHistory", "version")},
            {
                "obligationId": str(self.standard.id),
                "orgUnitId": str(self.bank_ab.id),
                "reference": "X.1",
                "title": "Our access rules",
                "applicability": "under_assessment",
                "hasHistory": False,
                "version": 1,
            },
        )
        self.assertIsNone(unit["applicabilityDecidedBy"])
        self.assertEqual(unit["complianceStatus"]["kind"], "not_assessed")
        (event,) = self._events(units.UNIT_CREATED)
        self.assertEqual((event.subject_type, str(event.subject_id), event.actor_id), ("soa_unit", unit["id"], self.officer.id))
        self.assertEqual(event.after["reference"], "X.1")
        self.assertEqual(event.after["orgUnitId"], str(self.bank_ab.id))

        listed = self._call("GET", f"/obligations/{self.standard.id}/units?entity={self.bank_ab.id}").json()
        self.assertEqual(([row["id"] for row in listed["items"]], listed["total"]), ([unit["id"]], 1))
        other = self._call("GET", f"/obligations/{self.standard.id}/units?entity={self.liv.id}").json()
        self.assertEqual(other, {"items": [], "total": 0})

    def test_the_list_is_by_reference_paged_and_costs_the_same_for_more_units(self) -> None:
        self._unit("X.2")
        path = f"/obligations/{self.standard.id}/units?entity={self.bank_ab.id}"
        with CaptureQueriesContext(connection) as one:
            self._call("GET", path)
        for reference in ("X.3", "X.1", "X.4"):
            self._unit(reference)
        with CaptureQueriesContext(connection) as four:
            page = self._call("GET", path + "&limit=3&offset=0").json()
        self.assertEqual(len(four.captured_queries), len(one.captured_queries))
        self.assertEqual(([row["reference"] for row in page["items"]], page["total"]), (["X.1", "X.2", "X.3"], 4))

    def test_a_unit_exists_only_under_a_standard_for_an_entity_that_follows_it(self) -> None:
        refusals = [
            (self._add(obligation=self.not_a_standard), 422, "units_only_under_standards"),
            (self._add(entity=self.liv), 422, "scope_not_applicable"),
            (self._add(entity=self.finance), 422, "scope_not_applicable"),
            (self._call("POST", f"/obligations/{uuid.uuid4()}/units", {"orgUnitId": str(self.bank_ab.id), "reference": "X.1", "title": "T"}), 404, "not_found"),
            (self._call("POST", f"/obligations/{self.standard.id}/units", {"orgUnitId": str(uuid.uuid4()), "reference": "X.1", "title": "T"}), 404, "not_found"),
            (self._add("   ", "Our words"), 422, "validation_error"),
        ]
        for response, status, code in refusals:
            with self.subTest(code=code):
                self._problem(response, status, code)
        self.activate(self.tenant)
        self.assertFalse(SoaUnit.objects.exists())
        self.assertEqual(self._events(units.UNIT_CREATED), [])

    def test_a_group_or_another_banks_entity_is_not_found(self) -> None:
        group = OrgUnit.objects.create(tenant=self.tenant, kind=OrgUnitKind.GROUP.value, name="Example Group")
        other = factories.tenant(slug="units-other")
        other_entity = OrgUnit.objects.create(tenant=other, kind=OrgUnitKind.LEGAL_ENTITY.value, name="Other Bank AB")
        for entity in (group, other_entity):
            with self.subTest(entity=entity.name):
                self._problem(self._add(entity=entity), 404, "not_found")

    def test_a_live_reference_is_listed_once_per_entity(self) -> None:
        self._unit("X.1")
        self._problem(self._add("X.1", "Again"), 409, "duplicate_key")

    # --- rename ------------------------------------------------------------------------
    def test_a_unit_without_history_is_renamed_with_if_match_and_audited(self) -> None:
        unit = self._unit("X.1")
        self._problem(self._call("PATCH", f"/units/{unit.id}", {"title": "New words"}), 409, "stale_write")
        self._problem(self._call("PATCH", f"/units/{unit.id}", {"title": "New words"}, version=7), 409, "stale_write")
        response = self._call("PATCH", f"/units/{unit.id}", {"reference": "X.9", "title": "New words"}, version=1)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual({k: response.json()[k] for k in ("reference", "title", "version")}, {"reference": "X.9", "title": "New words", "version": 2})
        (event,) = self._events(units.UNIT_RENAMED)
        self.assertEqual(event.before, {"reference": "X.1", "title": "Our access rules"})
        self.assertEqual(event.after, {"reference": "X.9", "title": "New words"})
        self.assertEqual(event.actor_id, self.officer.id)

    def test_a_rename_onto_a_live_reference_is_refused(self) -> None:
        self._unit("X.1")
        second = self._unit("X.2")
        self._problem(self._call("PATCH", f"/units/{second.id}", {"reference": "X.1"}, version=1), 409, "duplicate_key")

    def test_a_unit_with_history_keeps_its_reference_and_title(self) -> None:
        """A decision, a status or a gap each fix the unit: neither a rename nor a removal
        reaches it, and it is unchanged afterwards."""
        risk = RiskRating.objects.get(key="high")
        histories = {
            "decision": lambda unit: SoaUnit.objects.filter(pk=unit.pk).update(
                applicability=Applicability.DOES_NOT_APPLY.value,
                applicability_reason="Out of scope",
                applicability_decided_at=timezone.now(),
                applicability_decided_by=self.officer,
            ),
            "status": lambda unit: SoaUnit.objects.filter(pk=unit.pk).update(
                compliance_status=ComplianceStatus.objects.get(key="compliant")
            ),
            "gap": lambda unit: Gap.objects.create(
                tenant=self.tenant,
                tenant_obligation_id=self.bank_ab_scope.tenant_obligation_id,
                org_unit=self.bank_ab,
                unit=unit,
                title="Reviews are late",
                severity=risk,
                source=GapSource.objects.get(key="audit"),
                status=GapStatus.objects.get(key="open"),
                identified_by=self.officer,
            ),
        }
        for n, (history, make) in enumerate(histories.items()):
            with self.subTest(history):
                unit = self._unit(f"H.{n}")
                make(unit)
                listed = self._call("GET", f"/obligations/{self.standard.id}/units?entity={self.bank_ab.id}").json()
                self.assertTrue(next(row for row in listed["items"] if row["id"] == str(unit.id))["hasHistory"])
                self._problem(self._call("PATCH", f"/units/{unit.id}", {"title": "Moved"}, version=1), 409, "unit_has_history")
                self._problem(self._call("DELETE", f"/units/{unit.id}", version=1), 409, "unit_has_history")
                self.activate(self.tenant)
                after = SoaUnit.objects.get(pk=unit.pk)
                self.assertEqual((after.reference, after.title, after.version, after.removed_at), (f"H.{n}", "Our access rules", 1, None))
        self.assertEqual(self._events(units.UNIT_RENAMED) + self._events(units.UNIT_REMOVED), [])

    # --- remove ------------------------------------------------------------------------
    def test_a_unit_without_history_is_removed_by_a_stamp_and_audited(self) -> None:
        unit = self._unit("X.1")
        self._problem(self._call("DELETE", f"/units/{unit.id}"), 409, "stale_write")
        response = self._call("DELETE", f"/units/{unit.id}", version=1)
        self.assertEqual(response.status_code, 204, response.content)
        self.activate(self.tenant)
        removed = SoaUnit.objects.get(pk=unit.pk)
        self.assertIsNotNone(removed.removed_at)
        self.assertEqual(removed.removed_by_id, self.officer.id)
        (event,) = self._events(units.UNIT_REMOVED)
        self.assertEqual((event.subject_id, event.actor_id), (unit.id, self.officer.id))
        listed = self._call("GET", f"/obligations/{self.standard.id}/units").json()
        self.assertEqual(listed, {"items": [], "total": 0})
        self._problem(self._call("DELETE", f"/units/{unit.id}", version=2), 404, "not_found")
        self._problem(self._call("PATCH", f"/units/{unit.id}", {"title": "Back"}, version=2), 404, "not_found")
        self.assertEqual(self._add("X.1").status_code, 201)

    # --- paste -------------------------------------------------------------------------
    def test_a_paste_dry_run_reports_every_line_and_stores_nothing(self) -> None:
        self._unit("X.1")
        lines = [
            {"reference": " X.2 ", "title": "Our backups"},
            {"reference": "X.2", "title": "Our backups again"},
            {"reference": "X.1", "title": "Already listed"},
            {"reference": "R" * 65, "title": "Long reference"},
            {"reference": "X.3", "title": "T" * 301},
            {"reference": "", "title": "No reference"},
            {"reference": "X.4", "title": "Our logging"},
        ]
        created_before = self._events(units.UNIT_CREATED)
        response = self._call(
            "POST",
            f"/obligations/{self.standard.id}/units/paste",
            {"orgUnitId": str(self.bank_ab.id), "lines": lines},
            client=Client(),
        )
        self.assertEqual(response.status_code, 200, response.content)
        answer = response.json()
        self.assertEqual((answer["dryRun"], answer["created"]), (True, 0))
        self.assertEqual(
            [(row["line"], row["reference"][:4], row["outcome"], row["problem"], row["unitId"]) for row in answer["rows"]],
            [
                (1, "X.2", "will_create", None, None),
                (2, "X.2", "refused", "duplicate_reference", None),
                (3, "X.1", "refused", "reference_exists", None),
                (4, "RRRR", "refused", "reference_too_long", None),
                (5, "X.3", "refused", "title_too_long", None),
                (6, "", "refused", "empty_line", None),
                (7, "X.4", "will_create", None, None),
            ],
        )
        self.activate(self.tenant)
        self.assertEqual(list(SoaUnit.objects.values_list("reference", flat=True)), ["X.1"])
        self.assertEqual(self._events(units.UNIT_CREATED), created_before)

    def test_a_paste_refuses_unknown_values_and_the_same_places_a_unit_cannot_exist(self) -> None:
        paste = f"/obligations/{self.standard.id}/units/paste"
        line = {"reference": "X.1", "title": "Our words"}
        refusals = [
            (self._call("POST", paste, {"orgUnitId": str(self.bank_ab.id), "lines": [{**line, "applicability": "maybe"}]}), 422, "validation_error"),
            (self._call("POST", paste, {"orgUnitId": str(self.bank_ab.id), "lines": [line], "mode": "force"}), 422, "validation_error"),
            (self._call("POST", paste, {"orgUnitId": str(self.liv.id), "lines": [line]}), 422, "scope_not_applicable"),
            (
                self._call("POST", f"/obligations/{self.not_a_standard.id}/units/paste", {"orgUnitId": str(self.bank_ab.id), "lines": [line]}),
                422,
                "units_only_under_standards",
            ),
        ]
        for response, status, code in refusals:
            with self.subTest(code=code):
                self._problem(response, status, code)
        self.activate(self.tenant)
        self.assertFalse(SoaUnit.objects.exists())

    # --- another bank ------------------------------------------------------------------
    def test_another_bank_sees_no_unit_and_reaches_none(self) -> None:
        unit = self._unit("X.1")
        other = factories.tenant(slug="units-b")
        person = factories.member_user(other, roles=("compliance_officer",))
        who = user_principal(permissions={perms.REGISTER_READ, perms.REGISTER_EDIT}, tenant_id=other.id, subject_id=person.id)
        listed = self._call("GET", f"/obligations/{self.standard.id}/units", who=who)
        self.assertEqual(listed.json(), {"items": [], "total": 0})
        self._problem(self._call("PATCH", f"/units/{unit.id}", {"title": "Theirs"}, version=1, who=who), 404, "not_found")
        self._problem(self._call("DELETE", f"/units/{unit.id}", version=1, who=who), 404, "not_found")


# ---------------------------------------------------------------------------------------
# c8-units-paste-soa: the paste's commit, a unit's own decision, and a gap on a unit
# ---------------------------------------------------------------------------------------
class PasteCommit(UnitWorld):
    """The commit stores every unit, and every decision the lines carry through
    applicability's bulk path, in the request's one transaction: all of it or none. Written
    before the logic: every test here failed on the 501 `not_built` the commit answered."""

    def _paste(self, lines: list[dict[str, Any]], *, dry_run: bool = False, who: Any = None, client: Any = None) -> Any:
        body = {"orgUnitId": str(self.bank_ab.id), "lines": lines, "dryRun": dry_run}
        return self._call("POST", f"/obligations/{self.standard.id}/units/paste", body, who=who or self.decider, client=client)

    def test_a_commit_creates_every_unit_with_one_audit_event_each(self) -> None:
        lines = [{"reference": f"X.{n}", "title": f"Our control number {n}"} for n in range(1, 13)]
        response = self._paste(lines, who=self.who)
        self.assertEqual(response.status_code, 200, response.content)
        answer = response.json()
        self.assertEqual((answer["dryRun"], answer["created"]), (False, 12))
        live = {unit.reference: unit for unit in self._live()}
        self.assertEqual(
            [(row["outcome"], row["unitId"]) for row in answer["rows"]],
            [("created", str(live[line["reference"]].id)) for line in lines],
        )
        self.assertTrue(all(unit.applicability == Applicability.NOT_ASSESSED.value for unit in live.values()))
        events = self._events(units.UNIT_CREATED)
        self.assertEqual(sorted(event.subject_id for event in events), sorted(unit.id for unit in live.values()))
        self.assertEqual({event.actor_id for event in events}, {self.officer.id})

    def test_a_commit_sets_each_lines_decision_with_one_audit_event_per_unit(self) -> None:
        lines = [
            {"reference": "X.1", "title": "Our access rules", "applicability": "applies", "reason": "In the certificate"},
            {"reference": "X.2", "title": "Our backups", "applicability": "not_applicable", "reason": "No own data centre"},
            {"reference": "X.3", "title": "Our logging"},
        ]
        response = self._paste(lines)
        self.assertEqual(response.status_code, 200, response.content)
        x1, x2, x3 = self._live()
        self.assertEqual((x1.applicability, x1.applicability_reason, x1.applicability_decided_by_id), ("applies", "In the certificate", self.officer.id))
        self.assertEqual((x2.applicability, x2.applicability_reason), ("does_not_apply", "No own data centre"))
        self.assertIsNotNone(x1.applicability_decided_at)
        self.assertEqual((x3.applicability, x3.applicability_decided_at), ("not_assessed", None))
        events = self._events(applicability.APPLICABILITY_SET)
        self.assertEqual([(e.subject_type, e.subject_id, e.actor_id) for e in events], [("soa_unit", x1.id, self.officer.id), ("soa_unit", x2.id, self.officer.id)])
        self.assertEqual(events[0].before, {"applicability": "under_assessment", "reason": None})
        self.assertEqual(
            {k: events[1].after[k] for k in ("unitId", "orgUnitId", "applicability", "reason")},
            {"unitId": str(x2.id), "orgUnitId": str(self.bank_ab.id), "applicability": "not_applicable", "reason": "No own data centre"},
        )
        listed = self._call("GET", f"/obligations/{self.standard.id}/units?entity={self.bank_ab.id}").json()["items"]
        self.assertEqual([row["hasHistory"] for row in listed], [True, True, False])

    def test_decisions_need_applicability_approve_and_store_nothing_without_it(self) -> None:
        line = {"reference": "X.1", "title": "Our access rules", "applicability": "applies", "reason": "In the certificate"}
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run):
                response = self._paste([line], dry_run=dry_run, who=self.who, client=Client())
                self._problem(response, 403, "permission_denied")
                self.assertEqual(response.json()["requiredPermission"], perms.APPLICABILITY_APPROVE)
        self.assertEqual(self._live(), [])
        self.assertEqual(self._events(units.UNIT_CREATED), [])

    def test_a_line_with_half_a_decision_is_refused_on_its_row(self) -> None:
        lines = [
            {"reference": "X.1", "title": "Our access rules", "applicability": "applies", "reason": "  "},
            {"reference": "X.2", "title": "Our backups", "reason": "No own data centre"},
            {"reference": "X.3", "title": "Our logging", "applicability": "applies", "reason": "Certified"},
        ]
        answer = self._paste(lines, dry_run=True, client=Client()).json()
        self.assertEqual(
            [(row["outcome"], row["problem"]) for row in answer["rows"]],
            [("refused", "reason_missing"), ("refused", "reason_missing"), ("will_create", None)],
        )

    def test_a_commit_with_any_refused_line_stores_nothing(self) -> None:
        lines = [{"reference": "X.1", "title": "Our access rules"}, {"reference": "X.1", "title": "Twice"}]
        response = self._paste(lines, client=Client())
        self.assertEqual(response.status_code, 200, response.content)
        answer = response.json()
        self.assertEqual((answer["dryRun"], answer["created"]), (True, 0))
        self.assertEqual([row["outcome"] for row in answer["rows"]], ["will_create", "refused"])
        self.assertEqual(self._live(), [])

    def test_a_paste_over_the_cap_is_refused_whole_and_stores_nothing(self) -> None:
        lines = [{"reference": f"X.{n}", "title": "Ours", "applicability": "applies", "reason": "Certified"} for n in range(3)]
        with override_settings(REGISTER_BULK_MAX=2):
            for dry_run in (True, False):
                with self.subTest(dry_run=dry_run):
                    self._problem(self._paste(lines, dry_run=dry_run, client=Client()), 422, "validation_error")
        self.assertEqual(self._live(), [])
        self.assertEqual(self._events(units.UNIT_CREATED) + self._events(applicability.APPLICABILITY_SET), [])

    def test_a_decision_refused_by_the_bulk_path_takes_the_units_back_with_it(self) -> None:
        line = {"reference": "X.1", "title": "Our access rules", "applicability": "applies", "reason": "Certified"}
        refused = ValidationError("Refused for the test.", code="validation_error")
        with mock.patch.object(applicability, "_write", autospec=True, side_effect=refused):
            self._problem(self._paste([line], client=Client()), 422, "validation_error")
        self.assertEqual(self._live(), [])
        self.assertEqual(self._events(units.UNIT_CREATED), [])

    def test_93_decided_lines_stay_inside_the_budget_with_a_fixed_cost_per_line(self) -> None:
        """AC-REG1 at its size. Every lookup is once per call; only each unit's insert share,
        its events and its decision are per line, so the step between two sizes is fixed."""
        batch = iter(range(10_000))

        def lines(count: int) -> list[dict[str, Any]]:
            return [
                {"reference": f"A.{next(batch)}", "title": "Our own words", "applicability": "applies", "reason": "Certified"}
                for _ in range(count)
            ]

        def queries(count: int) -> int:
            with CaptureQueriesContext(connection) as captured:
                self.assertEqual(self._paste(lines(count)).status_code, 200)
            return len(captured)

        one, three = queries(1), queries(3)
        self.assertEqual(three - one, 2 * PASTE_LINE_QUERIES)
        spent = []
        tracer = sys.gettrace()
        sys.settrace(None)
        try:
            for _ in range(5):
                pasted = lines(93)
                started = time.thread_time()
                response = self._paste(pasted, client=Client())
                spent.append((time.thread_time() - started) * 1000)
                self.assertEqual(response.json()["created"], 93)
        finally:
            sys.settrace(tracer)
        self.assertLess(min(spent), settings.API_BUDGET_MS)
        self.assertEqual(len(self._events(applicability.APPLICABILITY_SET)), 4 + 5 * 93)


# Each pasted line: its unit's audit event (savepoint, audit row, outbox row, release) and
# its decision's audit event (four again). The units are one INSERT for the whole paste and
# their decisions one UPDATE, so neither grows with the paste.
PASTE_LINE_QUERIES = 8


class UnitDecisions(UnitWorld):
    """A unit's own answer through `PUT /obligations/{id}/applicability` and
    `POST /applicability`: stored on the unit, never on its entity's conformance row."""

    def _answer(self, unit: Any, value: str = "applies", *, version: int | None = 1, obligation: Any = None) -> Any:
        body = {"unitId": str(getattr(unit, "id", unit)), "applicability": value, "reason": "Certified"}
        return self._call("PUT", f"/obligations/{(obligation or self.standard).id}/applicability", body, version=version, who=self.decider)

    def test_a_unit_answer_is_stored_on_the_unit_with_if_match(self) -> None:
        unit = self._unit("X.1")
        self._problem(self._answer(unit, version=7), 409, "stale_write")
        response = self._answer(unit)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual({k: response.json()[k] for k in ("unitId", "orgUnitId", "applicability", "version")}, {"unitId": str(unit.id), "orgUnitId": None, "applicability": "applies", "version": 2})
        self.activate(self.tenant)
        unit.refresh_from_db()
        self.bank_ab_scope.refresh_from_db()
        self.assertEqual((unit.applicability, unit.version), ("applies", 2))
        self.assertEqual((self.bank_ab_scope.applicability_reason, self.bank_ab_scope.version), ("Certified", 1), "the conformance row keeps its own answer")

    def test_many_unit_answers_are_one_call(self) -> None:
        first, second = self._unit("X.1"), self._unit("X.2")
        rows = [
            {"obligationId": str(self.standard.id), "unitId": str(unit.id), "applicability": value, "reason": "Certified"}
            for unit, value in ((first, "applies"), (second, "not_applicable"))
        ]
        response = self._call("POST", "/applicability", {"rows": rows}, who=self.decider)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([row["unitId"] for row in response.json()["items"]], [str(first.id), str(second.id)])
        self.assertEqual([unit.applicability for unit in self._live()], ["applies", "does_not_apply"])

    def test_a_unit_the_answer_cannot_reach_is_refused_and_stores_nothing(self) -> None:
        unit = self._unit("X.1")
        removed = self._unit("X.2")
        self.assertEqual(self._call("DELETE", f"/units/{removed.id}", version=1).status_code, 204)
        self._problem(self._answer(uuid.uuid4(), version=None), 404, "not_found")
        self._problem(self._answer(removed, version=None), 404, "not_found")
        self._problem(self._answer(unit, obligation=self.not_a_standard, version=None), 404, "not_found")
        self.activate(self.tenant)
        TenantObligationScope.objects.filter(pk=self.bank_ab_scope.pk).update(applicability=Applicability.DOES_NOT_APPLY.value)
        self._problem(self._answer(unit), 422, "scope_not_applicable")
        self.assertEqual(self._events(applicability.APPLICABILITY_SET), [])


class GapsOnUnits(UnitWorld):
    """A gap may name a live unit under its own register entry (D-41): the gap is then in the
    unit's entity, and the unit's reference and title are fixed by it."""

    def setUp(self) -> None:
        super().setUp()
        self.recorder = user_principal(
            permissions={perms.REGISTER_READ, perms.REGISTER_EDIT, perms.GAPS_EDIT}, tenant_id=self.tenant.id, subject_id=self.officer.id
        )

    def _gap(self, unit_id: Any, *, obligation: Any = None, entity: Any = None) -> Any:
        body: dict[str, Any] = {"title": "Reviews are late", "severity": "high", "source": "audit", "unitId": str(unit_id)}
        if entity is not None:
            body["orgUnitId"] = str(entity.id)
        return self._call("POST", f"/obligations/{(obligation or self.standard).id}/gaps", body, who=self.recorder)

    def test_a_gap_on_a_live_unit_is_in_the_units_entity_and_fixes_the_unit(self) -> None:
        unit = self._unit("X.1")
        response = self._gap(unit.id)
        self.assertEqual(response.status_code, 201, response.content)
        gap = response.json()
        self.assertEqual((gap["unitId"], gap["orgUnitId"]), (str(unit.id), str(self.bank_ab.id)))
        (event,) = self._events("register.gap_recorded")
        self.assertEqual((event.after["unitId"], event.after["orgUnitId"]), (str(unit.id), str(self.bank_ab.id)))
        listed = self._call("GET", f"/obligations/{self.standard.id}/gaps").json()["items"]
        self.assertEqual([row["unitId"] for row in listed], [str(unit.id)])
        self._problem(self._call("PATCH", f"/units/{unit.id}", {"title": "Moved"}, version=1), 409, "unit_has_history")

    def test_a_unit_outside_the_gaps_entry_or_entity_is_422_and_stores_nothing(self) -> None:
        unit = self._unit("X.1")
        removed = self._unit("X.2")
        self.assertEqual(self._call("DELETE", f"/units/{removed.id}", version=1).status_code, 204)
        refusals = {
            "unknown": self._gap(uuid.uuid4()),
            "removed": self._gap(removed.id),
            "another entry": self._gap(unit.id, obligation=self.not_a_standard),
            "another entity": self._gap(unit.id, entity=self.liv),
        }
        for name, response in refusals.items():
            with self.subTest(name):
                self._problem(response, 422, "unknown_unit")
        self.activate(self.tenant)
        self.assertFalse(Gap.objects.exists())

    def test_a_unit_that_does_not_apply_has_no_gap(self) -> None:
        unit = self._unit("X.1")
        self.activate(self.tenant)
        SoaUnit.objects.filter(pk=unit.pk).update(applicability=Applicability.DOES_NOT_APPLY.value)
        self._problem(self._gap(unit.id), 409, "does_not_apply")
        self.activate(self.tenant)
        self.assertFalse(Gap.objects.exists())


class SoaWorld:
    """The scenarios' world (REG-S13 to REG-S15, SRC-S13): the prototype's Example Group with
    the standard in its regulatory scope, Example Bank AB following it and Liv not, each
    answered by the officer through the route, and every later call a real session."""

    def __init__(self, case: Any, slug: str) -> None:
        from apps.register.tests_applicability import Bank, seed_library

        self.case = case
        seed_library()
        self.bank = Bank(slug)
        self.tenant, self.officer = self.bank.tenant, self.bank.officer
        self.standard = library_testing.standard()
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            for terms in obligation_scopes([self.standard.id])[self.standard.id].values():
                FootprintTerm.objects.bulk_create([FootprintTerm(tenant=self.tenant, term=term) for term in terms])
        for entity, value in ((self.bank.bank_ab, "applies"), (self.bank.liv, "not_applicable")):
            answer = {"orgUnitId": str(entity.id), "applicability": value, "reason": "Certified" if value == "applies" else "Not in the certificate"}
            self.expect(self.call("PUT", f"/obligations/{self.standard.id}/applicability", answer, version=0), 200)

    def call(self, method: str, path: str, body: Any = None, *, version: int | None = None, who: Any = None) -> Any:
        headers = sign_in(who or self.officer, tenant=self.tenant)
        if version is not None:
            headers["HTTP_IF_MATCH"] = f'"{version}"'
        if body is None:
            return Client().generic(method, V1 + path, **headers)
        return Client().generic(method, V1 + path, data=json.dumps(body), content_type="application/json", **headers)

    def expect(self, response: Any, status: int, code: str | None = None) -> Any:
        self.case.assertEqual(response.status_code, status, response.content)
        if code is not None:
            self.case.assertEqual(response.json()["code"], code)
        return response.json() if response.content else None

    def paste(self, lines: list[dict[str, Any]], *, dry_run: bool, entity: Any = None) -> Any:
        body = {"orgUnitId": str((entity or self.bank.bank_ab).id), "lines": lines, "dryRun": dry_run}
        return self.call("POST", f"/obligations/{self.standard.id}/units/paste", body)

    def events(self, action: str) -> list[AuditEvent]:
        tenancy.activate(self.tenant.id)
        return list(AuditEvent.objects.filter(action=action, subject_type="soa_unit").order_by("created", "id"))

    def units(self) -> list[SoaUnit]:
        tenancy.activate(self.tenant.id)
        return list(SoaUnit.objects.filter(removed_at__isnull=True).order_by("reference"))
