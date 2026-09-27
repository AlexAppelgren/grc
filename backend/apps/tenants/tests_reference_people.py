"""The people picker, `GET /reference/people` (COL-04, TEN-03, HOM-05; `c8-ten-teams-people`).

Any member's session reads the bank's active members as ids and names and nothing else;
another bank's people and a deactivated member never appear; `permission=<key>` narrows the
list to the members whose session would hold that permission, exactly as `build_principal`
computes it. Written before the logic, when every call answered 501 `not_built`.
"""

from __future__ import annotations

from typing import Any

from django.test import TestCase
from django.utils import timezone

from apps.identity import session_logic
from apps.identity.models import Membership, SessionKind, TenantRole, User
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.models import Tenant
from apps.shared.testing import sign_in

URL = "/api/v1/reference/people"


class ReferencePeople(TestCase):
    tenant: Tenant
    other: Tenant
    reader: User
    approver: User
    admin: User
    gone: User
    stranger: User

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = factories.tenant(slug="people-a")
        cls.other = factories.tenant(slug="people-b")
        cls.reader = factories.member(cls.tenant, roles=("reader",), user_row=factories.user(name="Oskar Lund")).user
        cls.approver = factories.member(cls.tenant, roles=("reader", "approver"), user_row=factories.user(name="Anna Berg")).user
        cls.admin = factories.member(cls.tenant, roles=("admin",), user_row=factories.user(name="Karin Holm")).user
        cls.gone = factories.member(cls.tenant, roles=("approver",), user_row=factories.user(name="Erik Dahl")).user
        tenancy.activate(cls.tenant.id)
        Membership.objects.filter(user=cls.gone).update(deactivated_at=timezone.now())
        cls.stranger = factories.member(cls.other, roles=("approver",), user_row=factories.user(name="Björn Nyström")).user

    def people(self, query: str = "", user: User | None = None) -> Any:
        response = self.client.get(URL + query, **sign_in(user or self.reader, tenant=self.tenant))
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def holds(self, person: User, permission: str) -> bool:
        """What the person's own session would carry, from the function every request uses."""
        bundle = session_logic.create_session(user=person, kind=SessionKind.FULL, tenant_id=self.tenant.id, request=None)
        principal = session_logic.build_principal(bundle.session)
        return principal is not None and principal.has_permission(permission)

    def test_active_members_by_name_as_ids_and_names_only(self) -> None:
        people = self.people()
        self.assertEqual(
            people,
            [
                {"id": str(self.approver.id), "name": "Anna Berg"},
                {"id": str(self.admin.id), "name": "Karin Holm"},
                {"id": str(self.reader.id), "name": "Oskar Lund"},
            ],
        )
        ids = {row["id"] for row in people}
        self.assertNotIn(str(self.gone.id), ids, "a deactivated member is never offered")
        self.assertNotIn(str(self.stranger.id), ids, "another bank's people are never offered")

    def test_a_permission_narrows_the_list_to_its_holders_as_a_session_would_hold_it(self) -> None:
        for permission in (perms.CASES_SIGNOFF, perms.MEMBERS_MANAGE, perms.CASES_READ):
            with self.subTest(permission=permission):
                listed = {row["id"] for row in self.people(f"?permission={permission}")}
                expected = {str(p.id) for p in (self.reader, self.approver, self.admin) if self.holds(p, permission)}
                self.assertEqual(listed, expected)
                self.assertTrue(listed, "each of these permissions has a holder in this bank")

    def test_a_custom_role_counts_like_a_system_role(self) -> None:
        tenancy.activate(self.tenant.id)
        TenantRole.objects.create(tenant=self.tenant, key="dora_reviewer", permissions=[perms.REPORTS_READ, perms.CASES_SIGNOFF])
        reviewer = factories.member(self.tenant, roles=("dora_reviewer",), user_row=factories.user(name="Lena Ström")).user
        listed = {row["id"] for row in self.people(f"?permission={perms.CASES_SIGNOFF}")}
        self.assertIn(str(reviewer.id), listed)
        self.assertTrue(self.holds(reviewer, perms.CASES_SIGNOFF))

    def test_a_permission_nobody_here_holds_is_an_empty_200(self) -> None:
        lonely = factories.tenant(slug="people-c")
        only = factories.member_user(lonely, roles=("reader",))
        response = self.client.get(f"{URL}?permission={perms.MEMBERS_MANAGE}", **sign_in(only, tenant=lonely))
        self.assertEqual((response.status_code, response.json()), (200, []))

    def test_an_unknown_permission_is_422_unknown_key(self) -> None:
        response = self.client.get(f"{URL}?permission=cases.fly", **sign_in(self.reader, tenant=self.tenant))
        self.assertEqual((response.status_code, response.json()["code"]), (422, "unknown_key"))

    def test_an_enrolment_session_is_refused(self) -> None:
        response = self.client.get(URL, **sign_in(self.reader, tenant=self.tenant, kind="enrolment"))
        self.assertEqual((response.status_code, response.json()["code"]), (403, "enrolment_only"))
