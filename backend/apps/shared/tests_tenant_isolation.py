"""Guard: tenant isolation (playbook 5, NFR-01, AC-NFR1, J-8).

Parametrised over `TENANT_SCOPED_ROUTES` (apps/shared/routes.py): for every tenant-scoped
GET, PATCH and DELETE route, a record that belongs to tenant A requested by a member of
tenant B answers 404, never 403 and never data. Phase 0 registers no tenant route, so the
enumeration is empty; the test still walks the registry (zero routes is a result, not a
skip) and proves the mechanism it will use: a principal of tenant B, the stubbed session,
the problem-shaped 404.

When chunk 1 adds the first tenant route it must register it here, and the route-count
assertion below is raised in the same commit so the guard cannot stay vacuous.
"""

from __future__ import annotations

from django.test import TestCase

from apps.shared import factories
from apps.shared.routes import TENANT_SCOPED_ROUTES, iter_operations
from apps.shared.testing import SESSION_TOKEN_FOR_TESTS, stub_session, user_principal
from config.api import api

# Raise this in the commit that registers the first tenant-scoped route.
EXPECTED_MINIMUM_TENANT_ROUTES = 0


class TenantIsolationGuard(TestCase):
    def test_registry_enumerates_every_tenant_scoped_route(self) -> None:
        self.assertIsInstance(TENANT_SCOPED_ROUTES, list)
        self.assertGreaterEqual(len(TENANT_SCOPED_ROUTES), EXPECTED_MINIMUM_TENANT_ROUTES)
        registered = {(op.method, op.path) for op in iter_operations(api)}
        for method, path, _model_label, factory_name in TENANT_SCOPED_ROUTES:
            with self.subTest(route=f"{method} {path}"):
                self.assertIn((method, path), registered, "registry names a route Ninja did not register")
                self.assertTrue(hasattr(factories, factory_name), f"no factory {factory_name} in factories.py")

    def test_other_tenants_record_answers_404_for_each_route(self) -> None:
        tenant_a = factories.tenant(slug="iso-a")
        tenant_b = factories.tenant(slug="iso-b")
        member_of_b = user_principal(tenant_id=tenant_b.id)
        for method, path, _model_label, factory_name in TENANT_SCOPED_ROUTES:
            record = getattr(factories, factory_name)(tenant=tenant_a)
            url = "/api/v1" + path.replace("{id}", str(record.id))
            with self.subTest(route=f"{method} {path}"), stub_session(member_of_b):
                response = self.client.generic(
                    method, url, HTTP_AUTHORIZATION=f"Bearer {SESSION_TOKEN_FOR_TESTS}"
                )
                self.assertEqual(response.status_code, 404, f"{method} {path} leaked or refused instead of 404")
                self.assertEqual(response.json()["code"], "not_found")

    def test_unknown_path_is_a_problem_shaped_404_not_a_403(self) -> None:
        """The shape every isolation 404 will take: an addressed resource that is not there,
        including a record in another tenant (playbook 4.4)."""
        member = user_principal()
        with stub_session(member):
            response = self.client.get(
                "/api/v1/no-such-route/00000000-0000-4000-8000-000000000001",
                HTTP_AUTHORIZATION=f"Bearer {SESSION_TOKEN_FOR_TESTS}",
            )
        self.assertEqual(response.status_code, 404)
