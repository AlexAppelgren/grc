"""Guard: seed integrity (playbook 5, 8.3).

Runs the E2E seed and demands that two tenants exist with exactly the properties journeys
depend on (`EXPECTED_TENANTS`: fixed ids, slugs, names, timezones), that the seed is
idempotent (a second run changes nothing and adds no audit row), that it writes its audit
rows through record(), and that it refuses to run on a deployed environment. Chunk 1
extends EXPECTED with every fixed login (its roles, its passkey, the one user still
awaiting enrolment) so a test cannot be hollowed out by a seed change.

Proven to fail 2026-09-19 by changing TENANT_B's slug in the seed but not in EXPECTED:
the test named the tenant and the property.
"""

from __future__ import annotations

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.shared.e2e_seed import EXPECTED_TENANTS, SeedRefused, seed_e2e
from apps.shared.models import AuditEvent, Tenant


class SeedIntegrityGuard(TestCase):
    def test_the_seed_creates_exactly_the_expected_tenants(self) -> None:
        counts = seed_e2e()
        self.assertEqual(counts["tenants"], 2)
        self.assertEqual(len(EXPECTED_TENANTS), 2, "journeys need two tenants (J-8)")
        for expected in EXPECTED_TENANTS:
            with self.subTest(tenant=expected.slug):
                row = Tenant.objects.get(slug=expected.slug)
                self.assertEqual(row.id, expected.id)
                self.assertEqual(row.name, expected.name)
                self.assertEqual(row.timezone, expected.timezone)
        self.assertEqual(Tenant.objects.count(), 2)
        slugs = {t.slug for t in EXPECTED_TENANTS}
        self.assertEqual(len(slugs), 2, "seed tenants must have distinct slugs")

    def test_the_seed_is_idempotent_and_audited(self) -> None:
        seed_e2e()
        audited = AuditEvent.objects.filter(action="tenant.seeded").count()
        self.assertEqual(audited, 2, "each seeded tenant leaves one audit row through record()")
        seed_e2e()
        self.assertEqual(Tenant.objects.count(), 2)
        self.assertEqual(AuditEvent.objects.filter(action="tenant.seeded").count(), 2)

    def test_the_command_prints_counts(self) -> None:
        from io import StringIO

        out = StringIO()
        call_command("seed_e2e", stdout=out)
        self.assertIn("tenants: 2", out.getvalue())

    @override_settings(IS_DEPLOYED_ENVIRONMENT=True, ENVIRONMENT="prod")
    def test_the_seed_refuses_a_deployed_environment(self) -> None:
        with self.assertRaises(SeedRefused):
            seed_e2e()
        self.assertEqual(Tenant.objects.count(), 0)
