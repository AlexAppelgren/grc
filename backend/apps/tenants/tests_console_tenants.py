"""The console's tenants outside the scenarios (playbook 3 step 5): what creation writes,
what it refuses, and what the list shows. ADM-S6 proves the whole journey in
apps/governance/tests_scenarios.py; the branches live here. Creation asks only for a name
and the first administrator's address (D-68): the timezone, default language and content
languages are the bank's own to set afterwards, on its Organisation profile.

Operations exercised: createConsoleTenant, listConsoleTenants.
"""

from __future__ import annotations

from typing import Any

from apps.identity.models import Invitation, PlatformRole, PlatformRoleAssignment, TenantRole
from apps.library.seeds import seed_languages
from apps.shared import factories, tenancy
from apps.shared.adapters.mailer import MockMailer
from apps.shared.models import AuditEvent, Tenant, TenantContentLanguage
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import ComplianceStatus

V1 = "/api/v1"


def body(**overrides: Any) -> dict[str, Any]:
    """A creation body the route accepts; each test overrides the one field it is about."""
    return {
        "name": "Example Bank Oyj",
        "firstAdminEmail": "Anna@example-bank.test",
        "firstAdminTitle": "Head of Compliance",
        **overrides,
    }


class ConsoleTenants(ScenarioTestCase):
    def setUp(self) -> None:
        MockMailer.reset()
        seed_languages()
        self.platform_admin = factories.platform_user(roles=("platform_admin",))
        self.headers = sign_in(self.platform_admin)

    def _create(self, payload: dict[str, Any] | None = None) -> Any:
        return self.client.post(
            f"{V1}/console/tenants", data=payload or body(), content_type="application/json", **self.headers
        )

    def _code(self, response: Any) -> str:
        return str(response.json()["code"])

    # -- creation --------------------------------------------------------------------
    def test_creation_writes_the_tenant_with_its_roles_and_a_derived_short_name(self) -> None:
        response = self._create()
        self.assertEqual(response.status_code, 201, response.content)
        row = response.json()
        self.assertEqual(row["slug"], "example-bank-oyj")
        self.assertEqual(row["status"], "active")
        self.assertIsNone(row["defaultLanguage"])
        tenant = Tenant.objects.get(slug="example-bank-oyj")
        self.assertEqual(tenant.timezone, "Europe/Stockholm")
        self.activate(tenant)
        # No default and no content language yet: those are the bank's own to set (D-68).
        self.assertIsNone(tenant.default_language_id)
        self.assertEqual(TenantContentLanguage.objects.filter(tenant=tenant).count(), 0)
        self.assertTrue(TenantRole.objects.filter(tenant=tenant, key="admin", is_system=True).exists())
        self.assertTrue(ComplianceStatus.objects.filter(tenant=tenant, is_system=True).exists())

    def test_creation_invites_the_first_admin_and_mails_the_link(self) -> None:
        self._create()
        tenant = Tenant.objects.get(slug="example-bank-oyj")
        self.activate(tenant)
        invitation = Invitation.objects.get(tenant=tenant, email="anna@example-bank.test")
        self.assertEqual(invitation.title, "Head of Compliance")
        self.assertEqual([link.role.key for link in invitation.role_links.all()], ["admin"])
        self.assertIsNone(invitation.accepted_at)
        self.assertIsNone(invitation.invited_by_id)
        sent = MockMailer.sent
        self.assertEqual([mail.to for mail in sent], ["anna@example-bank.test"])
        self.assertIn("Example Bank Oyj", sent[0].subject)

    def test_a_missing_title_is_allowed(self) -> None:
        response = self._create(body(firstAdminTitle=""))
        self.assertEqual(response.status_code, 201, response.content)

    def test_every_audit_row_the_call_writes_belongs_to_the_new_tenant(self) -> None:
        """Platform staff have no bypass: the call activates only what it has just written."""
        other = factories.tenant(slug="other-bank")
        before = set(AuditEvent.objects.values_list("id", flat=True))
        self._create()
        tenant = Tenant.objects.get(slug="example-bank-oyj")
        written = AuditEvent.objects.exclude(id__in=before)
        self.assertEqual({event.tenant_id for event in written}, {tenant.id})
        # The bank's own lists are created here too, and recorded like everything else.
        self.assertEqual({event.action for event in written}, {"tenant.created", "vocabulary.created", "invitation.created"})
        self.activate(other)
        self.assertFalse(Invitation.objects.filter(tenant=other).exists())

    def test_two_tenants_with_the_same_name_get_different_derived_short_names(self) -> None:
        """No person ever picks a short name, so two banks of the same name are never
        refused over one: the second gets a numeric suffix instead of a 409 (D-68)."""
        first = self._create()
        # A fresh request would start with no tenant active; this test's own connection is
        # left scoped to the first tenant by the create it just ran, unlike production,
        # where each request starts clean.
        tenancy.clear_tenant()
        second = self._create(body(firstAdminEmail="second@example-bank.test"))
        self.assertEqual(second.status_code, 201, second.content)
        self.assertEqual(first.json()["slug"], "example-bank-oyj")
        self.assertEqual(second.json()["slug"], "example-bank-oyj-2")

    # -- refusals --------------------------------------------------------------------
    def test_a_blank_name_is_refused(self) -> None:
        self.assertEqual(self._code(self._create(body(name="   "))), "name_required")

    def test_an_address_without_an_at_sign_is_refused(self) -> None:
        self.assertEqual(self._code(self._create(body(firstAdminEmail="anna"))), "invalid_email")

    def test_a_platform_account_cannot_be_a_banks_first_admin(self) -> None:
        """The other side of bootstrap_platform's rule: platform staff are separate accounts."""
        editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        refused = self._create(body(firstAdminEmail="Editor@bleqq.test"))
        self.assertEqual(refused.status_code, 422, refused.content)
        self.assertEqual(self._code(refused), "platform_account")
        self.assertFalse(Tenant.objects.filter(name="Example Bank Oyj").exists())
        self.assertEqual(
            list(PlatformRoleAssignment.objects.filter(user=editor).values_list("role__key", flat=True)),
            ["library_editor"],
        )
        self.assertTrue(PlatformRole.objects.filter(key="library_editor").exists())

    # -- the list --------------------------------------------------------------------
    def test_the_list_shows_the_tenant_row_and_nothing_under_it(self) -> None:
        factories.tenant(name="Alpha Bank", slug="alpha-bank")
        factories.tenant(name="Beta Bank", slug="beta-bank")
        response = self.client.get(f"{V1}/console/tenants", **self.headers)
        self.assertEqual(response.status_code, 200, response.content)
        page = response.json()
        self.assertEqual(page["total"], 2)
        self.assertEqual([row["slug"] for row in page["items"]], ["alpha-bank", "beta-bank"])
        self.assertEqual(
            sorted(page["items"][0]),
            ["createdAt", "defaultLanguage", "id", "name", "slug", "status"],
        )

    def test_the_list_paginates(self) -> None:
        for n in range(3):
            factories.tenant(slug=f"bank-{n}")
        page = self.client.get(f"{V1}/console/tenants?limit=2&offset=2", **self.headers).json()
        self.assertEqual(page["total"], 3)
        self.assertEqual([row["slug"] for row in page["items"]], ["bank-2"])

    def test_a_limit_above_the_maximum_is_refused(self) -> None:
        response = self.client.get(f"{V1}/console/tenants?limit=101", **self.headers)
        self.assertEqual(response.status_code, 422, response.content)
