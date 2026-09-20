"""The derived search index: its fence, its language configurations and its row-level
security (SRC-01, SRC-02, INV-08, H7).

Three proofs, in the order they would fail a reviewer:

1. **The fence bites at runtime.** A chunk cannot be saved, updated or deleted outside
   `index_write()`, in bulk or one at a time, and can inside it. The AST half is
   `tests_index_fence.py`.
2. **The text search configuration is the chunk's own language's.** Five seeded content
   languages, five PostgreSQL configurations, asserted on the generated column as the
   database itself stems it, and the mapping is checked against the seeded `language`
   rows so the two cannot drift apart (INPUT_DELTAS §3).
3. **Row-level security is real, as cw_app and not as the owner.** With tenant A active a
   shared chunk cannot be inserted, updated or deleted, and tenant B's chunk cannot be
   read; every tenant still reads the shared chunks, which in R1 is all of them.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import DEFAULT_DB_ALIAS, ProgrammingError, connections, transaction
from django.test import TestCase, TransactionTestCase

from apps.library.models import Language
from apps.library.seeds import seed_languages
from apps.search.indexing import IndexWriteRefused, index_write
from apps.search.models import TEXT_SEARCH_CONFIGS, SearchChunk, SearchSource
from apps.shared import factories, tenancy

REASON = "a test rebuild"
# From the prototype's data (FFFS 2017:2, costs and charges), so the stems are real words.
TITLE = "Disclose all costs and charges before and after the service"
BODY = "The institution discloses costs and charges, aggregated and itemised, before the service is provided."


def chunk(**overrides: object) -> SearchChunk:
    fields: dict[str, object] = {
        "source_type": SearchSource.OBLIGATION_VERSION.value,
        "source_id": uuid.uuid4(),
        "language_id": "en",
        "title": TITLE,
        "body": BODY,
    }
    fields.update(overrides)
    return SearchChunk(**fields)


class IndexFenceRuntimeTests(TestCase):
    """The fence refuses a write that did not come through the door."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_languages()

    def test_a_chunk_cannot_be_saved_outside_the_door(self) -> None:
        with self.assertRaises(IndexWriteRefused):
            chunk().save()

    def test_a_chunk_can_be_saved_inside_the_door(self) -> None:
        with index_write(REASON):
            row = chunk()
            row.save()
        self.assertEqual(SearchChunk.objects.count(), 1)
        self.assertEqual(SearchChunk.objects.first(), row)

    def test_the_door_needs_a_reason(self) -> None:
        with self.assertRaises(ValueError):
            with index_write("  "):
                pass

    def test_update_delete_and_the_bulk_writes_are_refused_outside_the_door(self) -> None:
        with index_write(REASON):
            row = chunk()
            row.save()
        for label, write in (
            ("save", lambda: row.save()),
            ("delete", lambda: row.delete()),
            ("queryset update", lambda: SearchChunk.objects.all().update(title="rewritten")),
            ("queryset delete", lambda: SearchChunk.objects.all().delete()),
            ("bulk_create", lambda: SearchChunk.objects.bulk_create([chunk()])),
            ("bulk_update", lambda: SearchChunk.objects.bulk_update([row], ["title"])),
        ):
            with self.subTest(write=label):
                with self.assertRaises(IndexWriteRefused):
                    write()
        self.assertEqual(SearchChunk.objects.get().title, TITLE)

    def test_the_door_closes_again_when_the_rebuild_ends(self) -> None:
        with index_write(REASON):
            chunk().save()
        with self.assertRaises(IndexWriteRefused):
            chunk().save()


class SearchChunkLanguageTests(TestCase):
    """A chunk is stemmed in its own language, not in Swedish or English alone."""

    @classmethod
    def setUpTestData(cls) -> None:
        seed_languages()

    def test_the_mapping_matches_the_seeded_language_rows(self) -> None:
        # The generated column cannot read the language table, so the configurations are
        # written into the migration. This is the only thing that keeps the two in step.
        seeded = dict(Language.objects.values_list("key", "text_search_config"))
        self.assertEqual(seeded, TEXT_SEARCH_CONFIGS)

    def test_each_language_is_indexed_with_its_own_configuration(self) -> None:
        for key, config in sorted(TEXT_SEARCH_CONFIGS.items()):
            with self.subTest(language=key):
                with index_write(REASON):
                    row = chunk(language_id=key, source_id=uuid.uuid4())
                    row.save()
                with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
                    cursor.execute(
                        "SELECT tsv = setweight(to_tsvector(%s::regconfig, title), 'A') "
                        "|| setweight(to_tsvector(%s::regconfig, body), 'B') "
                        "FROM search_chunk WHERE id = %s",
                        [config, config, row.id],
                    )
                    self.assertIs(cursor.fetchone()[0], True, f"{key} is not stemmed as {config}")

    def test_a_language_is_a_seeded_row_and_not_free_text(self) -> None:
        # `lang` holds the key of a `language` row behind a foreign key, so a sixth content
        # language arrives by seeding a row and a chunk in an unknown one cannot be written
        # at all. schema.sql's `CHECK (lang IN ('sv', 'en'))` is the departure INPUT_DELTAS
        # records: it would have refused Danish, Norwegian and Finnish.
        field = SearchChunk._meta.get_field("language")
        self.assertIs(field.related_model, Language)
        self.assertEqual(field.target_field.name, "key")
        self.assertEqual(field.db_column, "lang")
        self.assertFalse(field.null)

    def test_the_embedding_column_matches_the_embedder_the_product_runs(self) -> None:
        # A column of one width and an adapter of another is a failure nobody sees until a
        # vector is written, so the two are compared here (D-09).
        self.assertEqual(SearchChunk._meta.get_field("embedding").dimensions, settings.EMBEDDING_DIMENSIONS)

    def test_a_chunk_belongs_to_the_shared_zone(self) -> None:
        # R1 indexes shared records only (D-10, owner items 4 and 10).
        with index_write(REASON):
            row = chunk()
            row.save()
        self.assertIsNone(row.owner_tenant_id)


class SearchChunkIsolation(TransactionTestCase):
    """The policy as cw_app (the `app` alias), which is the role a request runs under.

    The indexer writes the shared zone with no tenant active; a bank's session must not be
    able to reach it at all, and must not see another bank's chunk if one ever existed.
    """

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        seed_languages()
        self.tenant_a = factories.tenant(slug="chunk-a")
        self.tenant_b = factories.tenant(slug="chunk-b")
        with index_write(REASON), transaction.atomic(using="app"):
            self.shared = chunk()
            self.shared.save(using="app")
        with index_write(REASON), transaction.atomic(using="app"):
            tenancy.activate(self.tenant_b.id, using="app")
            self.theirs = chunk(source_id=uuid.uuid4(), owner_tenant=self.tenant_b)
            self.theirs.save(using="app")

    def _as_tenant_a(self) -> None:
        tenancy.activate(self.tenant_a.id, using="app")

    def test_a_tenant_reads_the_shared_chunks_and_not_another_tenants(self) -> None:
        with transaction.atomic(using="app"):
            self._as_tenant_a()
            visible = set(SearchChunk.objects.using("app").values_list("id", flat=True))
        self.assertEqual(visible, {self.shared.id})

    def test_a_tenant_cannot_insert_a_shared_chunk(self) -> None:
        with self.assertRaises(ProgrammingError):
            with index_write(REASON), transaction.atomic(using="app"):
                self._as_tenant_a()
                chunk(source_id=uuid.uuid4()).save(using="app")

    def test_a_tenant_cannot_update_a_shared_chunk(self) -> None:
        with index_write(REASON), transaction.atomic(using="app"):
            self._as_tenant_a()
            changed = SearchChunk.objects.using("app").filter(id=self.shared.id).update(title="rewritten")
        self.assertEqual(changed, 0, "the shared chunk was reachable from a bank's session")
        self.assertEqual(SearchChunk.objects.get(id=self.shared.id).title, TITLE)

    def test_a_tenant_cannot_delete_a_shared_chunk(self) -> None:
        with index_write(REASON), transaction.atomic(using="app"):
            self._as_tenant_a()
            deleted, _ = SearchChunk.objects.using("app").filter(id=self.shared.id).delete()
        self.assertEqual(deleted, 0, "the shared chunk was deletable from a bank's session")
        self.assertTrue(SearchChunk.objects.filter(id=self.shared.id).exists())

    def test_a_tenant_cannot_pull_a_shared_chunk_into_its_own_zone(self) -> None:
        with index_write(REASON), transaction.atomic(using="app"):
            self._as_tenant_a()
            moved = SearchChunk.objects.using("app").filter(id=self.shared.id).update(owner_tenant=self.tenant_a)
        self.assertEqual(moved, 0)
        self.assertIsNone(SearchChunk.objects.get(id=self.shared.id).owner_tenant_id)
