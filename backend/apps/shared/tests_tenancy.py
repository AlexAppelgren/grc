"""The library fence at runtime and the TenantModel base (playbook 14, PRO-01).

A throwaway concrete LibraryModel proves that save, update, delete and the bulk methods
are refused outside `library_write()` and accepted inside it, with a reason that is
readable while the fence is open. The AST half lives in tests_library_fence.py.
"""

from __future__ import annotations


from django.db import connection, models
from django.db import DEFAULT_DB_ALIAS, connections
from django.test import TestCase

from apps.shared import tenancy
from apps.shared.tenancy import (
    LibraryModel,
    LibraryQuerySet,
    LibraryWriteRefused,
    TenantModel,
    library_write,
    library_write_reason,
)


class ProbeLibraryRecord(LibraryModel):
    key = models.CharField(max_length=40)
    # The fenced manager LibraryModel declares, declared again so django-stubs binds it to this
    # model: a test module's models never reach the plugin's app registry, so the inherited
    # one is typed as LibraryModel's (whose only field is `id`). Same queryset, same fence.
    objects = LibraryQuerySet.as_manager()

    class Meta:
        app_label = "shared"
        db_table = "probe_library_record"
        managed = False
        ordering = ["key"]


class ProbeTenantRecord(TenantModel):
    note = models.CharField(max_length=40)

    class Meta:
        app_label = "shared"
        db_table = "probe_tenant_record"
        managed = False
        ordering = ["note"]


class LibraryFenceAtRuntime(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        with connection.schema_editor() as editor:
            editor.create_model(ProbeLibraryRecord)

    @classmethod
    def tearDownClass(cls) -> None:
        with connection.schema_editor() as editor:
            editor.delete_model(ProbeLibraryRecord)
        super().tearDownClass()

    def test_writes_are_refused_outside_the_fence(self) -> None:
        with self.assertRaises(LibraryWriteRefused):
            ProbeLibraryRecord(key="a").save()
        with self.assertRaises(LibraryWriteRefused):
            ProbeLibraryRecord.objects.create(key="a")
        with self.assertRaises(LibraryWriteRefused):
            ProbeLibraryRecord.objects.bulk_create([ProbeLibraryRecord(key="a")])
        with self.assertRaises(LibraryWriteRefused):
            ProbeLibraryRecord.objects.all().update(key="b")
        with self.assertRaises(LibraryWriteRefused):
            ProbeLibraryRecord.objects.all().delete()
        self.assertEqual(ProbeLibraryRecord.objects.count(), 0)
        self.assertIsNone(library_write_reason())

    def test_writes_are_accepted_inside_the_fence(self) -> None:
        with library_write("proposal 42 approved"):
            self.assertEqual(library_write_reason(), "proposal 42 approved")
            row = ProbeLibraryRecord.objects.create(key="a")
            ProbeLibraryRecord.objects.bulk_create([ProbeLibraryRecord(key="b")])
            ProbeLibraryRecord.objects.filter(pk=row.pk).update(key="c")
            ProbeLibraryRecord.objects.bulk_update([row], ["key"])
            row.delete()
            ProbeLibraryRecord.objects.all().delete()
        self.assertIsNone(library_write_reason())
        with self.assertRaises(ValueError):
            with library_write("   "):
                pass

    def test_tenant_model_carries_the_tenant_foreign_key(self) -> None:
        field = ProbeTenantRecord._meta.get_field("tenant")
        related = field.related_model
        assert isinstance(related, type)
        self.assertEqual(related._meta.label, "shared.Tenant")
        self.assertEqual(getattr(field.remote_field, "on_delete").__name__, "PROTECT")  # noqa: B009
        self.assertTrue(ProbeTenantRecord._meta.pk.name == "id")


class IdentityLookupMode(TestCase):
    """`tenancy.identity_lookup()` (chunk 1): the auth layer's window onto identity rows
    of every tenant before a tenant is known, switched off again on exit, and callable
    only from the auth layer (an AST guard below)."""

    def test_lookup_mode_sees_every_tenant_and_ends_with_the_block(self) -> None:
        from apps.shared import factories
        from apps.identity.models import Membership

        tenant_a = factories.tenant(slug="lookup-a")
        tenant_b = factories.tenant(slug="lookup-b")
        factories.member(tenant_a)
        factories.member(tenant_b)
        tenancy.activate(tenant_a.id)
        self.assertEqual(set(Membership.objects.values_list("tenant_id", flat=True)), {tenant_a.id})
        with tenancy.identity_lookup():
            self.assertTrue(tenancy.identity_lookup_active())
            self.assertEqual(set(Membership.objects.values_list("tenant_id", flat=True)), {tenant_a.id, tenant_b.id})
        self.assertFalse(tenancy.identity_lookup_active())
        self.assertEqual(set(Membership.objects.values_list("tenant_id", flat=True)), {tenant_a.id})

    def test_lookup_mode_refuses_to_run_outside_a_transaction(self) -> None:
        connection = connections[DEFAULT_DB_ALIAS]
        original = connection.in_atomic_block
        connection.in_atomic_block = False
        try:
            with self.assertRaises(tenancy.NotInTransaction):
                with tenancy.identity_lookup():
                    pass
        finally:
            connection.in_atomic_block = original

    def test_only_the_auth_layer_calls_identity_lookup(self) -> None:
        import ast
        from pathlib import Path

        allowed = {
            "shared/tenancy.py",
            "identity/session_logic.py",
            "identity/invitation_logic.py",
            "identity/api_keys_logic.py",
        }
        apps_dir = Path(__file__).resolve().parent.parent
        offenders: list[str] = []
        for path in sorted(apps_dir.rglob("*.py")):
            rel = path.relative_to(apps_dir).as_posix()
            if "/migrations/" in rel or rel.split("/")[-1].startswith("tests_") or rel.endswith("/testing.py"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    func = node.func
                    name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
                    if name == "identity_lookup" and rel not in allowed:
                        offenders.append(f"apps/{rel}:{node.lineno}")
        self.assertEqual(offenders, [], f"identity_lookup() is for the auth layer only; allowed: {sorted(allowed)}")
