"""The library fence at runtime and the TenantModel base (playbook 14, PRO-01).

A throwaway concrete LibraryModel proves that save, update, delete and the bulk methods
are refused outside `library_write()` and accepted inside it, with a reason that is
readable while the fence is open. The AST half lives in tests_library_fence.py.
"""

from __future__ import annotations

from typing import cast

from django.db import connection, models
from django.test import TestCase

from apps.shared.tenancy import (
    LibraryModel,
    LibraryWriteRefused,
    TenantModel,
    library_write,
    library_write_reason,
)


class ProbeLibraryRecord(LibraryModel):
    key = models.CharField(max_length=40)

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
        related = cast(type[models.Model], field.related_model)
        self.assertEqual(related._meta.label, "shared.Tenant")
        self.assertEqual(getattr(field.remote_field, "on_delete").__name__, "PROTECT")  # noqa: B009
        self.assertTrue(ProbeTenantRecord._meta.pk.name == "id")
