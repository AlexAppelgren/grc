"""Contract guard for the tenants routes chunk 8 declares (TEN-02, TEN-03, TEN-05, TEN-06,
COL-04, HOM-05, ADM-01; `c8-tenants-contract`).

Every route is published before its logic, behind the gate it will keep: 401 without a
session, 403 naming `requiredPermission` without its one permission, 403
`step_up_required` where a fresh passkey assertion is declared, and only then 501
`not_built` from the named function in the module of the package that will build it. A
`/tenant/` route that takes an id loads its record in the caller's bank first, so another
bank's id answers 404 before it ever sees a 501. A logic package that replaces its stub
changes the last rows of this file for its routes and nothing above them.

Written before the routes existed: every row failed with 404 until `tenants/api.py`
declared them.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from django.test import TestCase
from django.utils import timezone

from apps.shared import factories
from apps.shared import permissions as perms
from apps.shared.routes import TENANT_SCOPED_ROUTES, iter_operations
from apps.shared.testing import (
    API_KEY_FOR_TESTS,
    SESSION_TOKEN_FOR_TESTS,
    agent_principal,
    enrolment_principal,
    stub_api_key,
    stub_session,
    user_principal,
)
from config.api import api

AS_KEY: dict[str, Any] = {"HTTP_X_API_KEY": API_KEY_FOR_TESTS}
AS_SESSION: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"}

# The routes that were real before chunk 8 (TEN-01, ADM-02, ID-05, COL-02); their own tests
# prove them, and this file only keeps them out of the table below.
BUILT_BEFORE = {
    "getTenant",
    "updateTenant",
    "updateTenantWorkflow",
    "setTenantAi",
    "consoleReissueEnrolment",
    "listConsoleTenants",
    "createConsoleTenant",
}

# Routes of the table whose logic has landed: past every gate they answer with the real
# thing, which their own module proves, so the 501 rows below leave them out.
BUILT_SINCE = {
    # c8-ten-support-grants (TEN-06): tests_support_access.py.
    "requestConsoleSupportAccess",
    "listTenantSupportAccess",
    "approveSupportAccess",
    "declineSupportAccess",
    "revokeSupportAccess",
    # c8-support-session-guard (TEN-06): apps/shared/tests_support_session.py.
    "enterConsoleSupportAccess",
}

ORG_UNIT_BODY = {"kind": "business_area", "name": "Retail Banking"}
ORG_UNIT_PATCH = {"name": "Retail and Private Banking"}
LICENCE_BODY = {"licenceType": "credit_institution", "reference": "FI 12-3456"}
LICENCE_PATCH = {"withdrawnOn": "2026-12-31"}
PRODUCT_BODY = {"name": "Custody", "status": "live"}
PRODUCT_PATCH = {"status": "retired"}
REMOVE_BODY = {"owners": [{"kind": "register_entry", "teamKey": "compliance"}]}
SUPPORT_BODY = {"purpose": "The bank reports that its watch feed stopped updating on Monday.", "hours": 2}


class Records:
    """One bank's real rows for every id a route takes, so the 501 is reached past the load."""

    def __init__(self, tenant: Any) -> None:
        self.tenant = tenant
        self.member = factories.member_user(tenant, roles=("reader",))
        self.org_unit = factories.org_unit(tenant=tenant)
        self.product = factories.tenant_product(tenant=tenant)
        self.team = factories.team_key(tenant=tenant)
        self.grant = factories.support_access(tenant=tenant)
        self.licence = factories.licence(tenant=tenant)

    def routes(self) -> list[tuple[str, str, str, Any, str | None, bool]]:
        """(operationId, method, url, body, permission or None for any member, step-up)."""
        unit, licence, product = self.org_unit.id, self.licence.id, self.product.id
        member, team, grant = self.member.id, self.team.id, self.grant.id
        return [
            ("listOrgUnits", "get", "/api/v1/tenant/org-units", None, None, False),
            ("createOrgUnit", "post", "/api/v1/tenant/org-units", ORG_UNIT_BODY, perms.VOCAB_MANAGE, False),
            ("updateOrgUnit", "patch", f"/api/v1/tenant/org-units/{unit}", ORG_UNIT_PATCH, perms.VOCAB_MANAGE, False),
            ("listLicences", "get", f"/api/v1/tenant/org-units/{unit}/licences", None, None, False),
            ("createLicence", "post", f"/api/v1/tenant/org-units/{unit}/licences", LICENCE_BODY, perms.VOCAB_MANAGE, False),
            ("updateLicence", "patch", f"/api/v1/tenant/licences/{licence}", LICENCE_PATCH, perms.VOCAB_MANAGE, False),
            ("listProducts", "get", "/api/v1/tenant/products", None, None, False),
            ("createProduct", "post", "/api/v1/tenant/products", PRODUCT_BODY, perms.VOCAB_MANAGE, False),
            ("updateProduct", "patch", f"/api/v1/tenant/products/{product}", PRODUCT_PATCH, perms.VOCAB_MANAGE, False),
            ("listTeams", "get", "/api/v1/tenant/teams", None, None, False),
            ("listTeamMembers", "get", f"/api/v1/tenant/teams/{team}/members", None, None, False),
            ("listPeople", "get", "/api/v1/reference/people", None, None, False),
            ("getMemberOpenWork", "get", f"/api/v1/tenant/members/{member}/open-work", None, perms.MEMBERS_MANAGE, False),
            ("removeMember", "post", f"/api/v1/tenant/members/{member}/remove", REMOVE_BODY, perms.MEMBERS_MANAGE, True),
            ("listTenantSupportAccess", "get", "/api/v1/tenant/support-access", None, None, False),
            ("approveSupportAccess", "post", f"/api/v1/tenant/support-access/{grant}/approve", None, perms.SECURITY_MANAGE, True),
            ("declineSupportAccess", "post", f"/api/v1/tenant/support-access/{grant}/decline", None, perms.SECURITY_MANAGE, False),
            ("revokeSupportAccess", "post", f"/api/v1/tenant/support-access/{grant}/revoke", None, perms.SECURITY_MANAGE, False),
        ]

    def console_routes(self) -> list[tuple[str, str, str, Any, str | None, bool]]:
        grant = self.grant.id
        return [
            ("requestConsoleSupportAccess", "post", f"/api/v1/console/tenants/{self.tenant.id}/support-access", SUPPORT_BODY, perms.SUPPORT_ACCESS_GRANT, False),
            ("listConsoleSupportAccess", "get", "/api/v1/console/support-access", None, perms.SUPPORT_ACCESS_GRANT, False),
            ("enterConsoleSupportAccess", "post", f"/api/v1/console/support-access/{grant}/enter", None, perms.SUPPORT_ACCESS_GRANT, True),
        ]


def _call(client: Any, method: str, url: str, body: Any, headers: dict[str, Any]) -> Any:
    if body is None:
        return getattr(client, method)(url, **headers)
    return getattr(client, method)(url, data=body, content_type="application/json", **headers)


class TenantsContractCase(TestCase):
    records: Records
    other: Records
    admin: Any
    platform: Any

    @classmethod
    def setUpTestData(cls) -> None:
        cls.records = Records(factories.tenant(slug="contract-a"))
        cls.other = Records(factories.tenant(slug="contract-b"))
        cls.admin = factories.member_user(cls.records.tenant, roles=("admin",))
        cls.platform = factories.platform_user()

    def everything(
        self, *, tenant_id: uuid.UUID | None = None, permissions: frozenset[str] = perms.TENANT_PERMISSIONS
    ) -> Any:
        return user_principal(
            permissions=permissions,
            tenant_id=tenant_id or self.records.tenant.id,
            subject_id=self.admin.id,
            step_up_at=timezone.now(),
        )

    def console(self, *, permissions: frozenset[str] = perms.PLATFORM_PERMISSIONS, step_up: bool = True) -> Any:
        return user_principal(
            permissions=permissions, subject_id=self.platform.id, step_up_at=timezone.now() if step_up else None
        )

    def all_routes(self) -> list[tuple[str, str, str, Any, str | None, bool]]:
        return self.records.routes() + self.records.console_routes()


class TenantsRouteTable(TenantsContractCase):
    def test_the_table_names_every_new_tenants_operation_and_nothing_else(self) -> None:
        """A tenants route added without a row here would be published ungated by this file;
        a row naming no route would prove nothing."""
        registered = {op.operation_id for op in iter_operations(api) if op.view_func.__module__ == "apps.tenants.api"}
        self.assertEqual(registered - BUILT_BEFORE, {row[0] for row in self.all_routes()})

    def test_step_up_only_on_removal_approval_and_entering(self) -> None:
        """Playbook 4.2: removing a member, approving a support grant and entering one take a
        fresh passkey; a request, a decline and a revoke never do."""
        declared = {
            op.operation_id
            for op in iter_operations(api)
            if op.view_func.__module__ == "apps.tenants.api" and perms.step_up_of(op.view_func)
        }
        self.assertEqual(
            declared - BUILT_BEFORE, {"removeMember", "approveSupportAccess", "enterConsoleSupportAccess"}
        )

    def test_the_any_member_reads_are_ungated_by_design_as_a_capability(self) -> None:
        by_id = {op.operation_id: (op.method, op.path) for op in iter_operations(api)}
        for name, _method, _url, _body, permission, _step_up in self.records.routes():
            if permission is not None:
                continue
            with self.subTest(operation=name):
                entry = perms.UNGATED_BY_DESIGN[by_id[name]]
                self.assertIs(entry.reason, perms.UngatedReason.CAPABILITY)


class TenantsRouteGates(TenantsContractCase):
    def test_no_credential_is_401(self) -> None:
        for name, method, url, body, _permission, _step_up in self.all_routes():
            with self.subTest(operation=name):
                response = _call(self.client, method, url, body, {})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["code"], "unauthenticated")

    def test_an_agent_key_reaches_no_route(self) -> None:
        """The organisation, its people and support access are a person's business."""
        with stub_api_key(agent_principal(scopes=perms.ALL_SCOPES, tenant_id=self.records.tenant.id)):
            for name, method, url, body, _permission, _step_up in self.all_routes():
                with self.subTest(operation=name):
                    self.assertEqual(_call(self.client, method, url, body, AS_KEY).status_code, 401)

    def test_an_enrolment_session_reaches_no_route(self) -> None:
        """The people picker is refused to an enrolment session like every other route."""
        with stub_session(enrolment_principal(subject_id=self.admin.id)):
            for name, method, url, body, _permission, _step_up in self.all_routes():
                with self.subTest(operation=name):
                    self.assertEqual(_call(self.client, method, url, body, AS_SESSION).status_code, 401)

    def test_every_permission_but_its_own_is_403_naming_it(self) -> None:
        """Every other permission and a fresh step-up, so the only thing missing is the route's
        own permission and the 403 can only come from its gate."""
        everyone = perms.TENANT_PERMISSIONS | perms.PLATFORM_PERMISSIONS
        for name, method, url, body, permission, _step_up in self.all_routes():
            if permission is None:
                continue
            with self.subTest(operation=name), stub_session(self.everything(permissions=everyone - {permission})):
                response = _call(self.client, method, url, body, AS_SESSION)
                self.assertEqual(response.status_code, 403)
                problem = response.json()
                self.assertEqual(problem["code"], "permission_denied")
                self.assertEqual(problem["requiredPermission"], permission)

    def test_a_declared_step_up_without_a_fresh_assertion_is_403_step_up_required(self) -> None:
        stale = timezone.now() - timedelta(days=1)
        for name, method, url, body, _permission, step_up in self.all_routes():
            if not step_up:
                continue
            for step_up_at in (None, stale):
                who = user_principal(
                    permissions=perms.TENANT_PERMISSIONS | perms.PLATFORM_PERMISSIONS,
                    tenant_id=self.records.tenant.id if name != "enterConsoleSupportAccess" else None,
                    subject_id=self.admin.id,
                    step_up_at=step_up_at,
                )
                with self.subTest(operation=name, step_up_at=step_up_at), stub_session(who):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response.json()["code"], "step_up_required")

    def test_a_member_route_answers_404_to_a_console_session(self) -> None:
        """A platform session belongs to no bank, so a bank's own reads have nothing to show it."""
        with stub_session(self.console(permissions=perms.PLATFORM_PERMISSIONS | perms.TENANT_PERMISSIONS)):
            for name, method, url, body, _permission, _step_up in self.records.routes():
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(response.json()["code"], "not_found")

    def test_bad_input_is_422_before_the_stub(self) -> None:
        unit = self.records.org_unit.id
        member = self.records.member.id
        cases: list[tuple[str, str, str, Any]] = [
            ("createOrgUnit", "post", "/api/v1/tenant/org-units", {**ORG_UNIT_BODY, "kind": "department"}),
            ("createOrgUnit", "post", "/api/v1/tenant/org-units", {**ORG_UNIT_BODY, "name": "Retail\nBanking"}),
            ("createOrgUnit", "post", "/api/v1/tenant/org-units", {**ORG_UNIT_BODY, "name": "‮gniknaB"}),
            ("createOrgUnit", "post", "/api/v1/tenant/org-units", {**ORG_UNIT_BODY, "name": ""}),
            ("createOrgUnit", "post", "/api/v1/tenant/org-units", {**ORG_UNIT_BODY, "tone": "negative"}),
            ("updateOrgUnit", "patch", f"/api/v1/tenant/org-units/{unit}", {"name": "x" * 201}),
            ("createLicence", "post", f"/api/v1/tenant/org-units/{unit}/licences", {"reference": "FI 12-3456"}),
            ("createLicence", "post", f"/api/v1/tenant/org-units/{unit}/licences", {**LICENCE_BODY, "issuer": "Cert\tAB"}),
            ("createProduct", "post", "/api/v1/tenant/products", {**PRODUCT_BODY, "status": "paused"}),
            ("createProduct", "post", "/api/v1/tenant/products", {**PRODUCT_BODY, "name": "Custody\r\n"}),
            ("listProducts", "get", "/api/v1/tenant/products?limit=101", None),
            ("removeMember", "post", f"/api/v1/tenant/members/{member}/remove", {"owners": [{"kind": "gap"}]}),
            (
                "removeMember",
                "post",
                f"/api/v1/tenant/members/{member}/remove",
                {"owners": [{"kind": "gap", "teamKey": "compliance", "userId": str(self.admin.id)}]},
            ),
            ("removeMember", "post", f"/api/v1/tenant/members/{member}/remove", {"owners": [{"kind": "participation", "teamKey": "compliance"}]}),
        ]
        with stub_session(self.everything()):
            for name, method, url, body in cases:
                with self.subTest(operation=name, body=body):
                    response = _call(self.client, method, url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json()["code"], "validation_error")

    def test_the_support_request_refuses_a_blank_purpose_and_a_window_under_an_hour(self) -> None:
        url = f"/api/v1/console/tenants/{self.records.tenant.id}/support-access"
        with stub_session(self.console()):
            for body in ({**SUPPORT_BODY, "purpose": ""}, {**SUPPORT_BODY, "hours": 0}, {"hours": 2}):
                with self.subTest(body=body):
                    response = _call(self.client, "post", url, body, AS_SESSION)
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json()["code"], "validation_error")

    def test_an_unknown_permission_on_the_people_picker_is_422_unknown_key(self) -> None:
        with stub_session(self.everything()):
            for permission in ("cases.fly", "tenants.manage", ""):
                with self.subTest(permission=permission):
                    response = self.client.get(f"/api/v1/reference/people?permission={permission}", **AS_SESSION)
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json()["code"], "unknown_key")


class TenantsRoutesHideAnotherBanksRecords(TenantsContractCase):
    def test_every_id_route_answers_404_for_another_banks_record(self) -> None:
        """Tenant B's own admin holding every permission and a fresh step-up asks for tenant A's
        rows: 404 `not_found`, never 403 and never 501, which would say the id exists."""
        by_id = {op.operation_id: op.path for op in iter_operations(api)}
        with stub_session(self.everything(tenant_id=self.other.tenant.id)):
            for name, method, url, body, _permission, _step_up in self.records.routes():
                if "{" not in by_id[name]:
                    continue
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, {**AS_SESSION, "HTTP_IF_MATCH": '"1"'})
                    self.assertEqual(response.status_code, 404, response.content)
                    self.assertEqual(response.json()["code"], "not_found")

    def test_the_request_names_a_bank_that_exists(self) -> None:
        with stub_session(self.console()):
            response = _call(
                self.client, "post", f"/api/v1/console/tenants/{uuid.uuid4()}/support-access", SUPPORT_BODY, AS_SESSION
            )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "not_found")

    def test_every_tenant_id_route_but_the_licence_create_is_in_the_isolation_registry(self) -> None:
        """`tests_tenant_isolation` sends `{}`, which the licence create refuses before the
        load; this class proves that one instead."""
        registered = {(method, path) for method, path, _label, _factory in TENANT_SCOPED_ROUTES}
        by_id = {op.operation_id: (op.method, op.path) for op in iter_operations(api)}
        for name, _method, _url, _body, _permission, _step_up in self.records.routes():
            method, path = by_id[name]
            if "{" not in path or name == "createLicence":
                continue
            with self.subTest(operation=name):
                self.assertIn((method, path), registered)


class TenantsRouteStubs(TenantsContractCase):
    VERSIONED = {"updateOrgUnit", "updateLicence", "updateProduct"}

    def test_an_if_match_that_is_not_a_version_is_422_on_every_versioned_write(self) -> None:
        with stub_session(self.everything()):
            for name, method, url, body, _permission, _step_up in self.records.routes():
                if name not in self.VERSIONED:
                    continue
                with self.subTest(operation=name):
                    response = _call(self.client, method, url, body, {**AS_SESSION, "HTTP_IF_MATCH": "not-a-version"})
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json()["code"], "validation_error")

    def test_a_caller_holding_everything_reaches_the_named_stub(self) -> None:
        """Past every gate, in a real bank as a real member, or in the console: 501 `not_built`,
        in the one problem shape, with nothing of the server in it. Replaced row by row as
        each logic lands."""
        calls = [(route, self.everything()) for route in self.records.routes()]
        calls += [(route, self.console()) for route in self.records.console_routes()]
        for (name, method, url, body, _permission, _step_up), who in calls:
            if name in BUILT_SINCE:
                continue
            headers = {**AS_SESSION, "HTTP_IF_MATCH": '"1"'} if method == "patch" else AS_SESSION
            with self.subTest(operation=name), stub_session(who):
                response = _call(self.client, method, url, body, headers)
                self.assertEqual(response.status_code, 501, response.content)
                problem = response.json()
                self.assertEqual(problem["code"], "not_built")
                self.assertEqual(response.headers["Content-Type"], "application/problem+json")
                self.assertNotIn("traceback", response.content.decode().lower())

    def test_a_member_holding_nothing_reaches_the_any_member_reads(self) -> None:
        """Any member of the bank: no permission at all, and still past the gate."""
        with stub_session(self.everything(permissions=frozenset())):
            for name, method, url, body, permission, _step_up in self.records.routes():
                if permission is not None:
                    continue
                with self.subTest(operation=name):
                    expected = 200 if name in BUILT_SINCE else 501
                    self.assertEqual(_call(self.client, method, url, body, AS_SESSION).status_code, expected)

    def test_a_known_permission_on_the_people_picker_reaches_the_stub(self) -> None:
        with stub_session(self.everything(permissions=frozenset())):
            response = self.client.get(f"/api/v1/reference/people?permission={perms.CASES_SIGNOFF}", **AS_SESSION)
        self.assertEqual(response.status_code, 501)


class PermissionDescriptions(TestCase):
    def test_support_access_grant_and_security_manage_read_as_prd_0_4(self) -> None:
        """PRD 0.4, section 6: the request-then-enter grant, and the bank's side of it."""
        self.assertEqual(
            perms.PERMISSION_DESCRIPTIONS[perms.SUPPORT_ACCESS_GRANT],
            "Request support access to a bank and enter it read-only once a tenant admin approves.",
        )
        self.assertIn(
            "includes approving, declining and revoking support access",
            perms.PERMISSION_DESCRIPTIONS[perms.SECURITY_MANAGE],
        )


class TenantNameIsOneLine(TenantsContractCase):
    def test_the_tenant_name_refuses_a_line_break_on_both_writes(self) -> None:
        with stub_session(self.everything()):
            response = self.client.patch("/api/v1/tenant", data={"name": "Example\nBank"}, content_type="application/json", **AS_SESSION)
        self.assertEqual(response.status_code, 422)
        with stub_session(self.console()):
            response = self.client.post(
                "/api/v1/console/tenants",
                data={"name": "Second‮Bank", "firstAdminEmail": "admin@second-bank.test"},
                content_type="application/json",
                **AS_SESSION,
            )
        self.assertEqual(response.status_code, 422)
