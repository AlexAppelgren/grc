"""The obligation page's one read (perf-obligation-page): `GET /obligations/{id}/register`
carries what every panel shows on load, so the page asks once instead of once per panel.

Each part must be exactly what the panel's own route answers the same caller, a part behind a
permission the caller lacks must be null while the rest still arrive, another bank must read
none of this bank's rows, the read must write nothing, and it must cost the same number of
queries however many rows each part holds.

Written before `panels.py`: every test failed on the missing `panels` key."""

from __future__ import annotations

from typing import Any

from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.library import testing as library_testing
from apps.register.models import InternalLink, TenantObligation
from apps.register.tests_gaps import gap_body
from apps.register.tests_links import POLICY
from apps.register.tests_units import UnitWorld
from apps.shared import factories
from apps.shared import permissions as perms
from apps.shared.models import AuditEvent
from apps.shared.testing import user_principal
from apps.watch import testing as watch_build

# The whole read on the standard with one row in every part, the same with three rows in
# each: the test client's audit count (1), the request's own savepoint, tenant and caller
# (6), the entry with its reading, scopes and labels (6), the entities spanned (6), the
# gaps (5), the assessments (3), the links (3), the units (4), the participants (5), the
# problem reports (4), the related changes (11) and the comments (5).
PANEL_QUERIES = 59
EVERY_PANEL = frozenset(
    {
        perms.REGISTER_READ,
        perms.REGISTER_EDIT,
        perms.GAPS_EDIT,
        perms.PROBLEMS_REPORT,
        perms.WATCH_READ,
        perms.LIBRARY_READ,
        perms.COMMENTS_WRITE,
    }
)


class PanelWorld(UnitWorld):
    """`UnitWorld`'s standard, which Bank AB follows, with a row in every panel."""

    def setUp(self) -> None:
        super().setUp()
        watch_build.seed_watch_reference()
        self.reader = user_principal(permissions=EVERY_PANEL, tenant_id=self.tenant.id, subject_id=self.officer.id)
        self.one_of_each(1)

    def one_of_each(self, n: int) -> None:
        """One more row in every part, written through each panel's own route."""
        path = f"/obligations/{self.standard.id}"
        writes = [
            ("POST", f"{path}/units", {"orgUnitId": str(self.bank_ab.id), "reference": f"X.{n}", "title": f"Our rule {n}"}),
            ("POST", f"{path}/gaps", gap_body(title=f"Gap {n}")),
            ("POST", f"{path}/internal-links", {**POLICY, "label": f"Policy {n}", "externalRef": f"POL-{n}"}),
            ("POST", f"{path}/problem-reports", {"description": f"The reference looks wrong ({n})."}),
            ("POST", "/comments", {"subjectType": "obligation", "subjectId": str(self.standard.id), "body": f"Comment {n}"}),
        ]
        for method, url, body in writes:
            response = self._call(method, url, body, who=self.reader)
            self.assertIn(response.status_code, (200, 201), (url, response.content))
        entity = next(row for row in self.read()["entities"] if row["orgUnitId"] == str(self.bank_ab.id))
        status = {"complianceStatus": ("compliant", "partly_compliant")[n % 2], "rationale": f"Assessment {n}"}
        response = self._call("PATCH", f"{path}/register/entities/{self.bank_ab.id}", status, version=entity["version"], who=self.reader)
        self.assertEqual(response.status_code, 200, response.content)
        person = factories.member_user(self.tenant, roles=("compliance_officer",))
        response = self._call("POST", f"{path}/participants", {"userId": str(person.id)}, who=self.reader)
        self.assertEqual(response.status_code, 201, response.content)
        watch_build.obligation_link(watch_build.change(stable_key=f"panel-change-{n}"), self.standard)

    def read(self, who: Any = None, obligation: Any = None) -> dict[str, Any]:
        response = self._call("GET", f"/obligations/{(obligation or self.standard).id}/register", who=who or self.reader)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def own_route(self, path: str, who: Any = None) -> Any:
        response = self._call("GET", path, who=who or self.reader)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()


class EachPartIsWhatItsOwnRouteAnswers(PanelWorld):
    def test_every_part_equals_the_first_page_of_its_own_route(self) -> None:
        panels = self.read()["panels"]
        path, subject = f"/obligations/{self.standard.id}", f"subjectType=obligation&subjectId={self.standard.id}"
        routes = {
            "spannedEntities": f"{path}/register/entities",
            "gaps": f"{path}/gaps?limit=100",
            "assessments": f"{path}/assessments?limit=20&offset=0",
            "internalLinks": f"{path}/internal-links?limit=20&offset=0",
            "participants": f"{path}/participants?limit=100",
            "problemReports": f"/problem-reports?{subject}&limit=20&offset=0",
            "changes": f"{path}/changes?limit=20&offset=0",
            "comments": f"/comments?{subject}&limit=20&offset=0",
        }
        self.assertEqual(set(panels), {*routes, "units"})
        for part, route in routes.items():
            with self.subTest(part):
                self.assertEqual(panels[part], self.own_route(route))
                if part != "spannedEntities":
                    self.assertGreater(panels[part]["total"], 0)
        self.assertEqual(panels["units"]["orgUnitId"], str(self.bank_ab.id))
        self.assertEqual(panels["units"]["units"], self.own_route(f"{path}/units?entity={self.bank_ab.id}&limit=100"))

    def test_the_entry_itself_is_unchanged(self) -> None:
        body = self.read()
        entry = self._call("PATCH", f"/obligations/{self.standard.id}/register", {"process": "Access reviews"}, version=body["version"])
        self.assertEqual(entry.status_code, 200, entry.content)
        again = self.read()
        self.assertEqual({key: again[key] for key in entry.json()}, entry.json())


class UnitsOnlyWhereThePanelShowsThem(PanelWorld):
    def test_a_duty_that_is_not_under_a_standard_carries_no_units(self) -> None:
        self.assertIsNone(self.read(obligation=self.not_a_standard)["panels"]["units"])

    def test_a_standard_no_legal_entity_follows_carries_no_units(self) -> None:
        self.activate(self.tenant)
        TenantObligation.objects.get(obligation=self.standard).scopes.update(applicability="does_not_apply")
        self.assertIsNone(self.read()["panels"]["units"])


class EachPartKeepsItsOwnGate(PanelWorld):
    def test_a_part_behind_a_permission_the_caller_lacks_is_null_and_the_rest_arrive(self) -> None:
        for missing, part in ((perms.PROBLEMS_REPORT, "problemReports"), (perms.WATCH_READ, "changes"), (perms.LIBRARY_READ, "comments")):
            with self.subTest(missing):
                who = user_principal(permissions=EVERY_PANEL - {missing}, tenant_id=self.tenant.id, subject_id=self.officer.id)
                panels = self.read(who)["panels"]
                self.assertIsNone(panels[part])
                self.assertEqual([name for name, value in panels.items() if value is None], [part])

    def test_without_register_read_the_whole_read_is_refused(self) -> None:
        who = user_principal(permissions=EVERY_PANEL - {perms.REGISTER_READ}, tenant_id=self.tenant.id, subject_id=self.officer.id)
        response = self._call("GET", f"/obligations/{self.standard.id}/register", who=who)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["requiredPermission"], perms.REGISTER_READ)

    def test_another_bank_reads_none_of_this_banks_rows(self) -> None:
        other = factories.tenant(slug="panels-other")
        stranger = factories.member_user(other, roles=("compliance_officer",))
        who = user_principal(permissions=EVERY_PANEL, tenant_id=other.id, subject_id=stranger.id)
        panels = self.read(who)["panels"]
        for part in ("gaps", "assessments", "internalLinks", "participants", "problemReports", "comments"):
            with self.subTest(part):
                self.assertEqual(panels[part], {"items": [], "total": 0})
        self.assertEqual(panels["spannedEntities"], [])
        self.assertIsNone(panels["units"])
        # The changes are linked to the shared duty for every bank; the case on each is the reader's own.
        self.assertGreater(panels["changes"]["total"], 0)
        self.assertEqual(panels["changes"]["openCount"], 0)

    def test_a_private_obligation_of_another_bank_is_404(self) -> None:
        other = factories.tenant(slug="panels-private")
        act = library_testing.instrument(key="panels-theirs", regime="regime:securities", owner_tenant=other)
        private = library_testing.obligation(act, key="panels-their-duty", owner_tenant=other)
        response = self._call("GET", f"/obligations/{private.id}/register", who=self.reader)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "not_found")


class TheReadIsCheap(PanelWorld):
    def test_it_writes_nothing(self) -> None:
        self.activate(self.tenant)
        before = (TenantObligation.objects.count(), InternalLink.objects.count(), AuditEvent.objects.count())
        self.read()
        self.activate(self.tenant)
        self.assertEqual((TenantObligation.objects.count(), InternalLink.objects.count(), AuditEvent.objects.count()), before)

    def test_the_query_count_is_fixed_however_many_rows_each_part_holds(self) -> None:
        def queries() -> int:
            with CaptureQueriesContext(connection) as read:
                self.read()
            return len(read.captured_queries)

        one = queries()
        self.one_of_each(2)
        self.one_of_each(3)
        self.assertEqual((one, queries()), (PANEL_QUERIES, PANEL_QUERIES))
