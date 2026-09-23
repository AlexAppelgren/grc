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

    def _callers_of(self, name: str) -> list[tuple[str, str, int]]:
        """Every production call of `name`, as (`apps/<path>`, the top-level function or
        class it sits in, line). Module-level code is `<module>`. Migrations, tests and the
        testing helpers are not production code and are left out."""
        import ast
        from pathlib import Path

        apps_dir = Path(__file__).resolve().parent.parent
        found: list[tuple[str, str, int]] = []
        for path in sorted(apps_dir.rglob("*.py")):
            rel = path.relative_to(apps_dir).as_posix()
            if "/migrations/" in rel or rel.split("/")[-1].startswith("tests_") or rel.endswith("/testing.py"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for top in tree.body:
                scope = top.name if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else "<module>"
                for node in ast.walk(top):
                    if isinstance(node, ast.Call):
                        func = node.func
                        called = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
                        if called == name:
                            found.append((f"apps/{rel}", scope, node.lineno))
        return found

    @staticmethod
    def _outside(callers: list[tuple[str, str, int]], allowed: set[str]) -> list[str]:
        """The calls no entry of `allowed` covers. An entry is a whole module
        (`apps/<path>`) or one top-level function in it (`apps/<path>::<function>`)."""
        return [
            f"{module}::{scope}:{line}"
            for module, scope, line in callers
            if module not in allowed and f"{module}::{scope}" not in allowed
        ]

    def test_a_function_entry_covers_that_function_and_no_other(self) -> None:
        """What narrowing a module's entry to its functions buys (D-78): a new caller beside
        an allowed one is named, where a module-wide entry would have waved it through."""
        allowed = {"apps/a.py", "apps/b.py::door"}
        callers = [("apps/a.py", "anything", 1), ("apps/b.py", "door", 2), ("apps/b.py", "beside_the_door", 3)]
        self.assertEqual(self._outside(callers, allowed), ["apps/b.py::beside_the_door:3"])

    def test_only_the_auth_layer_calls_identity_lookup(self) -> None:
        allowed = {
            "apps/shared/tenancy.py",
            "apps/identity/session_logic.py",
            "apps/identity/invitation_logic.py",
            "apps/identity/api_keys_logic.py",
            # The fifth table of the clause and the fifth caller (HOM-04, D-52, ADR 0045):
            # a calendar client presents no session and no key, so the feed's token is
            # resolved to a row before any bank is known, exactly as an API key's is. It
            # reads `calendar_feed` by its unique prefix and nothing else, and activates
            # that row's tenant before it reads one row of the bank's own.
            "apps/home/feed.py",
        }
        offenders = self._outside(self._callers_of("identity_lookup"), allowed)
        self.assertEqual(offenders, [], f"identity_lookup() is for the auth layer only; allowed: {sorted(allowed)}")

    def test_only_record_leaves_the_tenant_zone(self) -> None:
        """Leaving the tenant zone is how a platform row gets written from a session that has
        a tenant (H15), so it belongs to the functions that are the only door into their
        ledger — `record()`, `log_event()` and, since chunk 7, `index_write()` — and to the
        tenancy module itself. A request that wants it for anything else is asking to write
        outside its own zone. Every entry below is named, with its reason, in D-78.

        `apps/search/indexing.py` is the third door and was reviewed as one (D-65, owner
        item 4): a search chunk is derived data, every chunk in R1 belongs to no tenant,
        and the words in one are copied from a shared library record that
        `apps/search/sources.py` refuses to read if a bank owns it. Nothing a bank wrote
        can ride out of its zone this way, and no other module may write a chunk at all
        (`apps/search/tests_index_fence.py`).

        `apps/identity/api_keys_logic.py` is allowed three functions and not the module
        (D-78): resolving a platform key, and the two writes of a platform key. Each asserts
        the zone the key's own row lives in — no tenant — rather than inheriting whatever
        the connection last had, and each is reached only by a platform key or by a platform
        session holding `agent_definitions.manage`, which no bank session can hold. A bank's
        own key is written and revoked inside its bank and needs no opening, so a new
        function in that module that calls `clear_tenant()` fails here until it is reviewed.
        """
        allowed = {
            "apps/shared/tenancy.py",
            "apps/shared/audit.py",
            "apps/identity/security_log.py",
            "apps/search/indexing.py",
            # The watch door's own generic upsert (c6-e2e-seed): `source` is the one watch
            # table with a zone column (WAT-06), and `write.upsert()` must not depend on
            # whichever tenant a shared connection happens to have active.
            "apps/watch/write.py",
            # The E2E seed writes both zones on purpose: it creates the banks, activates
            # each to write its own rows, and must stand outside all of them again to file
            # a library proposal as an agent would (PRO-03). It is not production code —
            # `manage.py seed_e2e` refuses to run on a deployed environment — and a seed
            # that could not leave a bank's zone could not seed the shared library at all.
            "apps/shared/e2e_seed.py",
            # Resolving a platform API key (D-62, ADR 0054): `api_key.tenant_id` is null for
            # a key bound to an agent, and the row it authenticates as belongs to no tenant.
            # The request that carries it may be the first on this connection since a
            # tenant-scoped one, so its own zone is asserted rather than inherited from
            # whatever the last request left active.
            "apps/identity/api_keys_logic.py::resolve_api_key",
            # Minting and revoking a platform agent key (ID-10, AGT-01, D-78): the row belongs
            # to no tenant, and both are reached only by a platform session holding
            # `agent_definitions.manage`, so the zone asserted is the one the caller is in.
            "apps/identity/api_keys_logic.py::create_agent_key",
            "apps/identity/api_keys_logic.py::revoke_agent_key",
        }
        offenders = [
            offender
            for name in ("platform_zone", "clear_tenant")
            for offender in self._outside(self._callers_of(name), allowed)
        ]
        self.assertEqual(
            offenders,
            [],
            "platform_zone() and clear_tenant() write rows that belong to no tenant; "
            f"allowed: {sorted(allowed)}. An audit row goes through record() and a security-log "
            "row through log_event(), which both do it there.",
        )
