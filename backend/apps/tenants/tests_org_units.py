"""The bank's organisation outside the scenarios (TEN-02, ADM-01, D-21, D-43;
c8-ten-organisation): units with their tree, kinds, legal-entity term, registration number,
LEI, country and head, and the licences and certificates a legal entity holds. Writes need
`vocab.manage`, check `If-Match`, answer 422 `unknown_key` or `unknown_member`, and are
audited with the fields they changed before and after. A unit is deactivated and a licence
withdrawn; neither is ever deleted. TEN-S2 and TEN-S10 are in tests_scenarios.py.

Operations exercised: listOrgUnits, createOrgUnit, updateOrgUnit, listLicences,
createLicence, updateLicence.
"""

from __future__ import annotations

import sys
import time
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.library.reading import today_for
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories
from apps.shared import permissions as perms
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import TermDimensionKind
from apps.taxonomy.registry import REGISTRY
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.tenants.models import Licence, OrgUnit

V1 = "/api/v1"
UNITS = f"{V1}/tenant/org-units"
# However many units a page holds: the test's own audit count, the session and its
# savepoint, the tenant and the language order, then the page with its terms and heads, the
# term labels and the count.
LIST_QUERIES = 14


class OrganisationCase(ScenarioTestCase):
    tenant: Any
    other: Any
    admin: Any

    @classmethod
    def setUpTestData(cls) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        cls.tenant = factories.tenant(slug="org-a")
        cls.other = factories.tenant(slug="org-b")
        cls.admin = factories.member_user(cls.tenant, roles=("admin",))

    def setUp(self) -> None:
        self.headers = sign_in(self.admin, tenant=self.tenant)

    def post(self, url: str, body: dict[str, Any], headers: dict[str, Any] | None = None) -> Any:
        return self.client.post(url, data=body, content_type="application/json", **(headers or self.headers))

    def patch(self, url: str, body: dict[str, Any], version: int | None = None, headers: dict[str, Any] | None = None) -> Any:
        sent: dict[str, Any] = dict(headers or self.headers)
        if version is not None:
            sent["HTTP_IF_MATCH"] = f'"{version}"'
        return self.client.patch(url, data=body, content_type="application/json", **sent)

    def entity(self, name: str = "Example Bank AB", **fields: Any) -> dict[str, Any]:
        response = self.post(UNITS, {"kind": "legal_entity", "name": name, "entityTerm": "bank", **fields})
        self.assertEqual(response.status_code, 201, response.content)
        return dict(response.json())

    def events(self, action: str) -> list[AuditEvent]:
        self.activate(self.tenant)
        return list(AuditEvent.objects.filter(tenant=self.tenant, action=action).order_by("created", "id"))

    def reader(self) -> dict[str, Any]:
        return sign_in(factories.member_user(self.tenant, roles=("reader",)), tenant=self.tenant)

    def other_admin(self) -> dict[str, Any]:
        return sign_in(factories.member_user(self.other, roles=("admin",)), tenant=self.other)

    def problem(self, response: Any, status: int, code: str) -> None:
        self.assertEqual((response.status_code, response.json()["code"]), (status, code), response.content)


class UnitWrites(OrganisationCase):
    def test_a_legal_entity_carries_its_identity_and_a_term_of_the_legal_entity_dimension(self) -> None:
        head = factories.member_user(self.tenant)
        unit = self.entity(orgNumber="556000-0000", lei="5493000example000000", countryCode="se", headUserId=str(head.id))
        self.assertEqual(
            {key: unit[key] for key in ("kind", "name", "parentId", "orgNumber", "lei", "countryCode", "active", "version")},
            {"kind": "legal_entity", "name": "Example Bank AB", "parentId": None, "orgNumber": "556000-0000", "lei": "5493000EXAMPLE000000", "countryCode": "SE", "active": True, "version": 1},
        )
        self.assertEqual(unit["entityTerm"]["key"], "bank")
        self.assertEqual(unit["head"], {"id": str(head.id), "name": head.name})
        # The term is read from the dimension rows, the same registry obligations are scoped from.
        self.activate(self.tenant)
        term = OrgUnit.objects.select_related("entity_term__dimension").get(pk=unit["id"]).entity_term
        assert term is not None
        dimension = REGISTRY["term_dimension"].model.objects.get(pk=term.dimension_id)
        self.assertEqual((dimension.key, dimension.kind), ("legal_entity", TermDimensionKind.SCOPE.value))
        [event] = self.events("org_unit.created")
        self.assertEqual((event.subject_type, str(event.subject_id), event.actor_id), ("org_unit", unit["id"], self.admin.id))
        self.assertEqual(event.after["entityTerm"], "bank")
        self.assertEqual(event.after["headUserId"], str(head.id))

    def test_a_department_sits_under_its_entity_with_a_head(self) -> None:
        entity = self.entity()
        head = factories.member_user(self.tenant)
        response = self.post(UNITS, {"kind": "business_area", "name": "Retail Banking", "parentId": entity["id"], "headUserId": str(head.id)})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual((response.json()["parentId"], response.json()["head"]["id"], response.json()["entityTerm"]), (entity["id"], str(head.id), None))

    def test_only_a_legal_entity_carries_the_entity_fields(self) -> None:
        for field, value in (("entityTerm", "bank"), ("orgNumber", "556000-0000"), ("lei", "5493000EXAMPLE000000"), ("countryCode", "SE")):
            with self.subTest(field=field):
                self.problem(self.post(UNITS, {"kind": "function", "name": "Compliance", field: value}), 422, "validation_error")
        self.assertEqual(self.events("org_unit.created"), [])

    def test_a_term_outside_the_legal_entity_dimension_is_unknown_key(self) -> None:
        for key in ("custody", "no_such_term"):
            with self.subTest(key=key):
                self.problem(self.post(UNITS, {"kind": "legal_entity", "name": "Bank AB", "entityTerm": key}), 422, "unknown_key")

    def test_a_malformed_lei_or_country_is_refused(self) -> None:
        self.problem(self.post(UNITS, {"kind": "legal_entity", "name": "Bank AB", "lei": "TOO-SHORT"}), 422, "validation_error")
        self.problem(self.post(UNITS, {"kind": "legal_entity", "name": "Bank AB", "countryCode": "S1"}), 422, "validation_error")

    def test_a_head_who_is_not_an_active_member_of_the_bank_is_unknown_member(self) -> None:
        stranger = factories.member_user(self.other)
        gone = factories.member(self.tenant)
        self.activate(self.tenant)
        gone.deactivated_at = gone.created_at
        gone.save(update_fields=["deactivated_at"])
        for user_id in (stranger.id, gone.user_id, factories.user().id):
            with self.subTest(user=str(user_id)):
                self.problem(self.post(UNITS, {"kind": "function", "name": "Risk", "headUserId": str(user_id)}), 422, "unknown_member")

    def test_a_parent_of_another_bank_is_not_found(self) -> None:
        foreign = factories.org_unit(self.other)
        self.problem(self.post(UNITS, {"kind": "function", "name": "Risk", "parentId": str(foreign.id)}), 404, "not_found")

    def test_a_change_needs_the_current_version_and_records_only_what_moved(self) -> None:
        unit = self.entity()
        url = f"{UNITS}/{unit['id']}"
        changed = self.patch(url, {"name": "Example Bank Oyj", "countryCode": "FI"}, version=1)
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertEqual((changed.json()["name"], changed.json()["countryCode"], changed.json()["version"]), ("Example Bank Oyj", "FI", 2))
        self.problem(self.patch(url, {"name": "Stale"}, version=1), 409, "stale_write")
        self.activate(self.tenant)
        self.assertEqual(OrgUnit.objects.get(pk=unit["id"]).name, "Example Bank Oyj")
        [event] = self.events("org_unit.updated")
        self.assertEqual(event.before, {"name": "Example Bank AB", "countryCode": ""})
        self.assertEqual(event.after, {"name": "Example Bank Oyj", "countryCode": "FI"})

    def test_a_unit_never_moves_under_itself_or_below_itself(self) -> None:
        group = self.post(UNITS, {"kind": "group", "name": "Example Group"}).json()
        entity = self.entity(parentId=group["id"])
        self.problem(self.patch(f"{UNITS}/{group['id']}", {"parentId": entity["id"]}), 422, "validation_error")
        self.problem(self.patch(f"{UNITS}/{group['id']}", {"parentId": group["id"]}), 422, "validation_error")

    def test_a_unit_is_deactivated_listed_and_never_deleted(self) -> None:
        unit = self.entity()
        response = self.patch(f"{UNITS}/{unit['id']}", {"active": False})
        self.assertEqual((response.status_code, response.json()["active"]), (200, False))
        listed = self.client.get(UNITS, **self.headers).json()
        self.assertEqual([(row["id"], row["active"]) for row in listed["items"]], [(unit["id"], False)])
        self.activate(self.tenant)
        with self.assertRaises(ValidationError):
            OrgUnit.objects.get(pk=unit["id"]).delete()
        [event] = self.events("org_unit.updated")
        self.assertEqual((event.before, event.after), ({"active": True}, {"active": False}))

    def test_writes_need_vocab_manage_and_reads_need_only_membership(self) -> None:
        unit = self.entity()
        reader = self.reader()
        denied = self.post(UNITS, {"kind": "function", "name": "Risk"}, headers=reader)
        self.assertEqual((denied.status_code, denied.json()["requiredPermission"]), (403, perms.VOCAB_MANAGE))
        denied = self.patch(f"{UNITS}/{unit['id']}", {"name": "x"}, headers=reader)
        self.assertEqual((denied.status_code, denied.json()["requiredPermission"]), (403, perms.VOCAB_MANAGE))
        self.assertEqual([row["id"] for row in self.client.get(UNITS, **reader).json()["items"]], [unit["id"]])

    def test_another_bank_sees_none_of_the_units_and_cannot_change_one(self) -> None:
        unit = self.entity()
        other_admin = self.other_admin()
        self.assertEqual(self.client.get(UNITS, **other_admin).json(), {"items": [], "total": 0})
        self.problem(self.patch(f"{UNITS}/{unit['id']}", {"name": "Taken"}, headers=other_admin), 404, "not_found")
        self.problem(self.client.get(f"{UNITS}/{unit['id']}/licences", **other_admin), 404, "not_found")


class LicenceWrites(OrganisationCase):
    def licences(self, unit: dict[str, Any]) -> str:
        return f"{UNITS}/{unit['id']}/licences"

    def test_a_licence_carries_a_type_and_services_from_the_scope_dimensions(self) -> None:
        unit = self.entity()
        granted = today_for(self.tenant) - timedelta(days=3650)
        response = self.post(self.licences(unit), {"licenceType": "bank", "reference": "FI 12-3456", "grantedOn": granted.isoformat(), "serviceTerms": ["custody", "advice"], "scopeNote": "Deposits and lending."})
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body["licenceType"]["key"], body["orgUnitId"], body["version"]), ("bank", unit["id"], 1))
        self.assertEqual(sorted(term["key"] for term in body["serviceTerms"]), ["advice", "custody"])
        self.activate(self.tenant)
        licence = Licence.objects.get(pk=body["id"])
        kinds = {term.dimension.kind for term in [licence.licence_type, *(row.term for row in licence.service_terms.select_related("term__dimension"))]}
        self.assertLessEqual(kinds, {TermDimensionKind.SCOPE.value, TermDimensionKind.OPT_IN.value})
        [event] = self.events("licence.created")
        self.assertEqual(event.after["serviceTerms"], ["advice", "custody"])
        self.assertEqual(event.after["rewritten"], ["scopeNote"])
        self.assertNotIn("Deposits and lending.", str(event.after))

    def test_only_a_legal_entity_holds_a_licence(self) -> None:
        department = self.post(UNITS, {"kind": "business_area", "name": "Retail"}).json()
        self.problem(self.post(self.licences(department), {"licenceType": "bank"}), 422, "validation_error")

    def test_a_type_or_service_outside_the_scope_dimensions_is_unknown_key(self) -> None:
        unit = self.entity()
        self.problem(self.post(self.licences(unit), {"licenceType": "no_such_licence"}), 422, "unknown_key")
        self.problem(self.post(self.licences(unit), {"licenceType": "bank", "serviceTerms": ["custody", "nope"]}), 422, "unknown_key")
        self.assertEqual(self.events("licence.created"), [])

    def test_an_owner_who_is_not_an_active_member_is_unknown_member(self) -> None:
        unit = self.entity()
        stranger = factories.member_user(self.other)
        self.problem(self.post(self.licences(unit), {"licenceType": "bank", "ownerUserId": str(stranger.id)}), 422, "unknown_member")

    def test_an_end_before_its_start_is_refused(self) -> None:
        unit = self.entity()
        today = today_for(self.tenant)
        body = {"licenceType": "bank", "grantedOn": today.isoformat(), "withdrawnOn": (today - timedelta(days=1)).isoformat()}
        self.problem(self.post(self.licences(unit), body), 422, "validation_error")
        body = {"licenceType": "bank", "issuedOn": today.isoformat(), "validUntil": (today - timedelta(days=1)).isoformat()}
        self.problem(self.post(self.licences(unit), body), 422, "validation_error")

    def test_a_withdrawn_licence_stays_readable_and_a_stale_change_is_refused(self) -> None:
        unit = self.entity()
        created = self.post(self.licences(unit), {"licenceType": "bank", "serviceTerms": ["custody"]}).json()
        url = f"{V1}/tenant/licences/{created['id']}"
        withdrawn_on = today_for(self.tenant) + timedelta(days=30)
        response = self.patch(url, {"withdrawnOn": withdrawn_on.isoformat(), "serviceTerms": ["advice"]}, version=1)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()["withdrawnOn"], response.json()["version"]), (withdrawn_on.isoformat(), 2))
        self.assertEqual([term["key"] for term in response.json()["serviceTerms"]], ["advice"])
        self.problem(self.patch(url, {"reference": "late"}, version=1), 409, "stale_write")
        listed = self.client.get(self.licences(unit), **self.headers).json()
        self.assertEqual([(row["id"], row["withdrawnOn"]) for row in listed["items"]], [(created["id"], withdrawn_on.isoformat())])
        [event] = self.events("licence.updated")
        self.assertEqual(event.before, {"withdrawnOn": None, "serviceTerms": ["custody"]})
        self.assertEqual(event.after, {"withdrawnOn": withdrawn_on.isoformat(), "serviceTerms": ["advice"], "rewritten": []})
        self.activate(self.tenant)
        with self.assertRaises(ValidationError):
            Licence.objects.get(pk=created["id"]).delete()

    def test_another_bank_cannot_change_a_licence(self) -> None:
        unit = self.entity()
        created = self.post(self.licences(unit), {"licenceType": "bank"}).json()
        other_admin = self.other_admin()
        self.problem(self.patch(f"{V1}/tenant/licences/{created['id']}", {"reference": "x"}, headers=other_admin), 404, "not_found")
        self.problem(self.post(self.licences(unit), {"licenceType": "bank"}, headers=other_admin), 404, "not_found")


class SeededTreeBudget(OrganisationCase):
    """NFR-02, playbook 10: a full page of the organisation, every unit with its term and
    head, stays inside the API budget, and its query count does not grow with the page."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        head = factories.member_user(cls.tenant)
        group = factories.department(cls.tenant)
        entity = factories.seeded_legal_entity(cls.tenant, parent=group, head=head)
        for _ in range(settings.API_PAGE_SIZE_MAX):
            factories.department(cls.tenant, parent=entity, head=head)

    def test_a_full_page_stays_inside_the_budget(self) -> None:
        params = {"limit": settings.API_PAGE_SIZE_MAX}
        with self.assertNumQueries(LIST_QUERIES):
            response = self.client.get(UNITS, params, **self.headers)
        self.assertEqual(len(response.json()["items"]), settings.API_PAGE_SIZE_MAX)
        self.assertTrue(any(row["entityTerm"] for row in response.json()["items"]))
        # CPU time on the request thread, the best of fifteen, with the coverage tracer paused
        # for the timed calls only (the shape of apps/library/tests_reading.py).
        spent = []
        tracer = sys.gettrace()
        sys.settrace(None)
        try:
            for _ in range(15):
                started = time.thread_time()
                self.client.get(UNITS, params, **self.headers)
                spent.append((time.thread_time() - started) * 1000)
        finally:
            sys.settrace(tracer)
        self.assertLess(min(spent), settings.API_BUDGET_MS)
