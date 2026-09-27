"""The tenant-creation hook's branches (VOC-01, VOC-04, VOC-05, TEN-02): a second run over a
seeded tenant adds nothing, a system row whose kind drifted gets the code's kind back with an
audit row, a key the tenant already used for a value of its own stops the seed, and a system
role whose permissions drifted follows the code again. The first run over a new tenant is
proven by the console's creation tests (apps/tenants/tests_console_tenants.py)."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.identity import roles_logic
from apps.identity.models import TenantRole
from apps.shared import factories, permissions as perms
from apps.shared.audit import Actor
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase
from apps.taxonomy.models import Team
from apps.taxonomy.tenant_hooks import TENANT_SYSTEM_ROWS, ensure_tenant_vocabularies

SEED = Actor.system("test_seed")


class TenantHook(ScenarioTestCase):
    def setUp(self) -> None:
        self.tenant = factories.tenant()
        self.activate(self.tenant)

    def _events(self, action: str) -> int:
        return AuditEvent.objects.filter(tenant_id=self.tenant.id, action=action).count()

    def test_a_second_run_adds_no_row_and_no_audit_row(self) -> None:
        created, teams = self._events("vocabulary.created"), Team.objects.filter(tenant=self.tenant).count()
        with transaction.atomic():
            count = ensure_tenant_vocabularies(self.tenant, actor=SEED)
        self.assertEqual(count, sum(len(rows) for _, rows in TENANT_SYSTEM_ROWS.values()))
        self.assertEqual(self._events("vocabulary.created"), created)
        self.assertEqual(Team.objects.filter(tenant=self.tenant).count(), teams)

    def test_a_drifted_kind_is_put_back_and_recorded(self) -> None:
        Team.objects.filter(tenant=self.tenant, key="compliance").update(kind="stray")
        with transaction.atomic():
            ensure_tenant_vocabularies(self.tenant, actor=SEED)
        row = Team.objects.get(tenant=self.tenant, key="compliance")
        self.assertIsNone(row.kind)
        self.assertEqual(row.version, 2)
        event = AuditEvent.objects.get(tenant_id=self.tenant.id, action="vocabulary.updated", subject_id=row.id)
        self.assertEqual((event.before, event.after), ({"kind": "stray"}, {"kind": None}))

    def test_a_system_key_the_tenant_already_uses_stops_the_seed(self) -> None:
        Team.objects.filter(tenant=self.tenant, key="compliance").update(is_system=False)
        with self.assertRaises(ValidationError) as refused, transaction.atomic():
            ensure_tenant_vocabularies(self.tenant, actor=SEED)
        self.assertEqual(refused.exception.code, "system_key_taken")

    def test_a_system_role_whose_permissions_drifted_follows_the_code_again(self) -> None:
        TenantRole.objects.filter(tenant=self.tenant, key="admin").update(permissions=[], active=False)
        roles = TenantRole.objects.filter(tenant=self.tenant).count()
        with transaction.atomic():
            roles_logic.ensure_system_roles(self.tenant)
        admin = TenantRole.objects.get(tenant=self.tenant, key="admin")
        self.assertEqual(admin.permissions, sorted(perms.SYSTEM_ROLES["admin"]))
        self.assertTrue(admin.active)
        self.assertEqual(TenantRole.objects.filter(tenant=self.tenant).count(), roles)
