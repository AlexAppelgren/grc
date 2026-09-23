"""The console's tenants outside the scenarios (playbook 3 step 5): what creation writes,
what it refuses, and what the list shows. ADM-S6 proves the whole journey in
apps/governance/tests_scenarios.py; the branches live here. Creation asks only for a name
and the first administrator's address (D-68): the timezone, default language and content
languages are the bank's own to set afterwards, on its Organisation profile. The short name
is derived from the name, so no name the route accepts can fail on it: not a long one, not
a Danish or Norwegian one, and not one another platform admin is creating at the same moment.

Operations exercised: createConsoleTenant, listConsoleTenants.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from unittest import mock

from django.db import DEFAULT_DB_ALIAS, IntegrityError, connection, connections, transaction
from django.test import TransactionTestCase

from apps.identity.models import Invitation, PlatformRole, PlatformRoleAssignment, TenantRole
from apps.library.seeds import seed_languages
from apps.shared import factories, tenancy
from apps.shared.adapters.mailer import MockMailer
from apps.shared.audit import Actor
from apps.shared.models import AuditEvent, Tenant, TenantContentLanguage
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import ComplianceStatus
from apps.tenants import logic

V1 = "/api/v1"
WAIT_SECONDS = 10


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

    def test_the_longest_name_the_route_accepts_derives_a_short_name_that_fits(self) -> None:
        """A 200-character name slugifies to 200 characters and the column holds 80. The
        short name is cut to fit with its suffix, never ending on a hyphen, instead of the
        insert failing the whole creation."""
        name = " ".join(["Sparkasse"] * 20) + "n"
        self.assertEqual(len(name), 200)
        first = self._create(body(name=name))
        tenancy.clear_tenant()
        second = self._create(body(name=name, firstAdminEmail="second@example-bank.test"))
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(second.status_code, 201, second.content)
        # Cut at 80 lands on a hyphen, which is dropped; with "-2" the cut lands mid-word.
        self.assertEqual(first.json()["slug"], "-".join(["sparkasse"] * 8))
        self.assertEqual(second.json()["slug"], "-".join(["sparkasse"] * 7) + "-sparkass-2")
        self.assertEqual(first.json()["name"], name)
        for response in (first, second):
            self.assertLessEqual(len(response.json()["slug"]), 80)

    def test_danish_and_norwegian_letters_are_spelled_out_rather_than_dropped(self) -> None:
        """Unicode decomposition folds å and ä to a, but ø, æ and ß have no decomposition and
        would vanish: "Sør" would become "sr"."""
        created = self._create(body(name="Sør Sparebank"))
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["slug"], "sor-sparebank")
        tenancy.clear_tenant()
        created = self._create(body(name="Nørresundby Bank", firstAdminEmail="second@example-bank.test"))
        self.assertEqual(created.json()["slug"], "norresundby-bank")
        self.assertEqual(logic._derive_slug("ÆRØ Sparekasse på Ålands Straße"), "aero-sparekasse-pa-alands-strasse")
        self.assertEqual(logic._derive_slug("Ökad Säkerhet Oyj"), "okad-sakerhet-oyj")
        # Nothing left to spell: the short name falls back to a word, never to nothing.
        self.assertEqual(logic._derive_slug("!!!"), "tenant")

    def test_another_integrity_error_is_raised_rather_than_retried_as_a_taken_short_name(self) -> None:
        """Only tenant_slug_key means "that short name is taken, try the next"; any other
        refusal on the insert is a fault and surfaces as one, never a loop of retries."""
        existing = factories.tenant(slug="existing-bank")
        tenancy.clear_tenant()
        with self.assertRaises(IntegrityError) as clash, transaction.atomic():
            Tenant.objects.create(id=existing.id, name="Clash", slug="clash-bank")
        attempts = mock.Mock(side_effect=clash.exception)
        with mock.patch.object(Tenant.objects, "create", attempts), self.assertRaises(IntegrityError):
            logic.create_tenant(actor=Actor.system("test"), name="Third Bank AB", first_admin_email="third@example-bank.test", first_admin_title="")
        self.assertEqual(attempts.call_count, 1)

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


def _backend_pid() -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_backend_pid()")
        return int(cursor.fetchone()[0])


class SameNameRace(TransactionTestCase):
    """Two platform admins create banks of the same name at the same moment, and both are
    created (D-68). Each session runs `create_tenant` on a cw_app connection of its own, in
    its own thread and transaction, the way two requests reach production. The first inserts
    the short name and keeps its transaction open until PostgreSQL reports the second one
    waiting on the same unique key, then commits. The second read the short name as free
    before the first committed, so only the unique key can tell it otherwise.

    Proven to fail 2026-09-23 before the insert ran in a savepoint that retries the next
    suffix: the second creation raised IntegrityError on tenant_slug_key and wrote nothing."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        MockMailer.reset()
        with transaction.atomic():
            seed_languages()

    def _session(self, email: str, wait_for: threading.Event | None, created: threading.Event | None, pids: list[int]) -> str:
        """Create "Example Bank Oyj" in one transaction on a fresh cw_app connection of this
        thread's own, and answer the short name it got."""
        connections[DEFAULT_DB_ALIAS] = connections.create_connection("app")
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT current_user")
                    assert cursor.fetchone()[0] == connections.settings["app"]["USER"], "a racing session must be cw_app"
                pids.append(_backend_pid())
                if wait_for is not None and not wait_for.wait(WAIT_SECONDS):
                    raise AssertionError("the first session never created its tenant")
                tenant = logic.create_tenant(
                    actor=Actor.system("test"), name="Example Bank Oyj", first_admin_email=email, first_admin_title=""
                )
                if created is not None:
                    created.set()
                    self._hold_until_the_other_waits(pids)
            return tenant.slug
        finally:
            connections[DEFAULT_DB_ALIAS].close()

    def _hold_until_the_other_waits(self, pids: list[int]) -> None:
        mine = _backend_pid()
        deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < deadline:
            others = [pid for pid in pids if pid != mine]
            if others:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT %s = ANY(pg_blocking_pids(%s))", [mine, others[0]])
                    if cursor.fetchone()[0]:
                        return
            time.sleep(0.01)
        raise AssertionError("the second session never waited on the first")

    def test_two_banks_of_the_same_name_created_at_once_are_both_created(self) -> None:
        created = threading.Event()
        pids: list[int] = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            leading = pool.submit(self._session, "first@example-bank.test", None, created, pids)
            following = pool.submit(self._session, "second@example-bank.test", created, None, pids)
            slugs = (leading.result(), following.result())
        self.assertEqual(slugs, ("example-bank-oyj", "example-bank-oyj-2"))
        self.assertEqual(sorted(Tenant.objects.values_list("slug", flat=True)), ["example-bank-oyj", "example-bank-oyj-2"])
        for tenant in Tenant.objects.all():
            with transaction.atomic():
                tenancy.activate(tenant.id)
                self.assertEqual(Invitation.objects.filter(tenant=tenant).count(), 1)
                self.assertEqual(AuditEvent.objects.filter(tenant=tenant, action="tenant.created").count(), 1)
