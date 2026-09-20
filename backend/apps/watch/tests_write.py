"""The watch door (ruling H of the chunk 5 plan, plan rule 8).

`watch_write()` is the second named door into the library zone: it opens the library
fence for the seven watch tables and refuses, at runtime, every other library table, so
the door cannot reach `authority`, `instrument`, `provision`, `obligation` or a version
table even by mistake. The allowlist half — which modules may call it — is proven by the
AST guard in apps/shared/tests_library_fence.py.

Proven to fail 2026-09-20 by dropping the statement wrapper from `watch_write()` and
leaving the plain `library_write()`: the update, the delete and the insert below all went
through and the three tests named them. The raw-SQL test was proven to fail the same day
by anchoring the pattern at the start of the statement again: the common table expression,
the second statement after the semicolon, the COPY and the TRUNCATE all reached the
obligation table.
"""

from __future__ import annotations

import uuid

from django.db import connection
from django.test import TestCase

from apps.library.models import Authority, Obligation, Provision
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import seed_authorities
from apps.shared.tenancy import LibraryWriteRefused, library_write_reason
from apps.taxonomy.models import SourceKind, TaxonomyTerm
from apps.taxonomy.seeds import seed_library_vocabularies
from apps.watch.models import Source
from apps.watch.write import WATCH_TABLES, WatchWriteRefused, watch_write

REASON = "registering a change"


class WatchDoorTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_authorities()

    def _source(self) -> Source:
        return Source.objects.create(name="fi.se", kind=SourceKind.objects.get(key="authority_site"))

    def test_the_door_opens_the_library_fence_for_a_watch_table(self) -> None:
        with watch_write(REASON):
            row = self._source()
        self.assertEqual(row.name, "fi.se")

    def test_the_door_names_the_watch_step_as_the_reason(self) -> None:
        with watch_write(REASON):
            self.assertIn(REASON, library_write_reason() or "")

    def test_the_door_closes_again(self) -> None:
        with watch_write(REASON):
            self._source()
        self.assertIsNone(library_write_reason())
        with self.assertRaises(LibraryWriteRefused):
            Source.objects.create(name="another", kind=SourceKind.objects.get(key="authority_site"))

    def test_the_door_refuses_an_update_of_an_inventory_table(self) -> None:
        with self.assertRaises(WatchWriteRefused) as caught, watch_write(REASON):
            Authority.objects.filter(key="nobody").update(url="https://www.example.test/")
        self.assertIn("authority", str(caught.exception))

    def test_the_door_refuses_a_delete_from_an_inventory_table(self) -> None:
        with self.assertRaises(WatchWriteRefused), watch_write(REASON):
            Authority.objects.filter(key="fi").delete()
        # Nothing is read back: the refusal happens inside Django's delete transaction and
        # marks it for rollback, which is what a fence breach should do.

    def test_the_door_refuses_an_insert_into_a_library_table_it_does_not_own(self) -> None:
        with self.assertRaises(WatchWriteRefused), watch_write(REASON):
            TaxonomyTerm.objects.create(dimension_id=uuid.uuid4(), key="smuggled")

    def test_the_door_refuses_a_write_the_statement_does_not_start_with(self) -> None:
        """Raw SQL can put the write anywhere: inside a data-modifying common table
        expression, after a semicolon, or behind a verb Django never emits."""
        statements = (
            'WITH smuggled AS (INSERT INTO "obligation" (id) VALUES (%s) RETURNING id) SELECT id FROM smuggled',
            'SELECT 1; DELETE FROM "obligation"',
            'COPY "obligation" (id) FROM STDIN',
            'TRUNCATE TABLE "obligation"',
        )
        for statement in statements:
            with self.subTest(statement=statement[:30]):
                with self.assertRaises(WatchWriteRefused) as caught, watch_write(REASON):
                    with connection.cursor() as cursor:
                        cursor.execute(statement, [uuid.uuid4()] if "%s" in statement else None)
                self.assertIn("obligation", str(caught.exception))

    def test_the_door_leaves_reads_alone(self) -> None:
        with watch_write(REASON):
            self.assertEqual(Provision.objects.filter(stable_key="nobody").count(), 0)

    def test_the_door_leaves_a_locking_read_of_an_inventory_table_alone(self) -> None:
        """`SELECT ... FOR UPDATE OF "obligation"` reads; refusing it would break the
        proposal applier's own reads the moment a watch step called one."""
        with watch_write(REASON):
            rows = list(Obligation.objects.select_for_update(of=("self",)).filter(stable_key="nobody"))
        self.assertEqual(rows, [])

    def test_the_door_reaches_no_inventory_table(self) -> None:
        inventory = {
            model._meta.db_table
            for model in (Authority, Obligation, Provision)
        }
        self.assertEqual(WATCH_TABLES & inventory, set())
