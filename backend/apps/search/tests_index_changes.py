"""Registered changes are searchable (SRC-01, WAT-01, AGT-02; c7-index-changes).

What these tests hold in place, in the order a reviewer would ask about it:

1. **A change reads as one text under every content language.** Its title and summary, its
   authority, its authority's jurisdiction and its scope terms (never a flag), searchable
   from the day it was published, and owned by no bank. A withdrawn or superseded change
   has no chunk.
2. **The rebuild takes changes with it.** `reindex_change` and `reindex_all` write them,
   a second run writes nothing, a corrected summary drops the old vector, and a withdrawal
   removes the chunks.
3. **The watch events reach the index through the one cursor, with no tenant active.**
   One handler for a registration, a merge and a correction; a replay changes nothing; an
   event recorded in a bank's zone writes no chunk and asks no model anything. No watch
   writer is hooked.
4. **Both legs find it, inside the bank's scope.** The change is judged by the watch
   feed's own scope rule, so a change for a regime the bank does not do is held back like
   an obligation of that regime is.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any, ClassVar
from unittest import mock

from django.db import DEFAULT_DB_ALIAS, connections, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.cases import creation
from apps.search import hybrid, indexing, sources, tasks
from apps.search.models import TEXT_SEARCH_CONFIGS, SearchChunk, SearchSource
from apps.search.schemas import SearchFilters, SearchHitType, SearchMatchKind, SearchRequest, SimilarRequest
from apps.shared import factories, outbox, tenancy
from apps.shared.adapters import embedder
from apps.shared.audit import Actor, record
from apps.shared.models import OutboxEvent, Tenant
from apps.taxonomy.models import FootprintTerm
from apps.taxonomy.seeds import seed_term_dimensions
from apps.watch import curation, registration
from apps.watch import testing as watch
from apps.watch.models import ChangeStatus, RegulatoryChange
from apps.watch.write import watch_write

TITLE = "FI adopts amended rules on paying for investment research"
SUMMARY = "FI's board decided to amend three regulations in the securities area."
LANGUAGES = sorted(TEXT_SEARCH_CONFIGS)


def seed_reference() -> None:
    watch.seed_watch_reference()
    seed_term_dimensions()


def flush_outbox() -> None:
    """Mark what the fixtures recorded as delivered, so each test delivers its own rows."""
    with transaction.atomic():
        OutboxEvent.objects.filter(published_at__isnull=True).update(published_at=timezone.now())


def change_event(change: RegulatoryChange, topic: str, *, tenant: Tenant | None = None) -> OutboxEvent:
    """A watch event, written the only way one is written: through `record()`, in the zone
    it belongs to. The watch writers always pass no tenant; `tenant` is the row that
    should never exist."""
    with transaction.atomic():
        if tenant is None:
            tenancy.clear_tenant()
        else:
            tenancy.activate(tenant.id)
        audit = record(
            action=topic,
            actor=Actor.system("watch"),
            subject_type=registration.SUBJECT_TYPE,
            subject_id=change.id,
            subject_title=change.title,
            summary="A watch event.",
            tenant_id=None if tenant is None else tenant.id,
        )
        return OutboxEvent.objects.get(audit_event=audit)


def set_status(change: RegulatoryChange, status: ChangeStatus, *, superseded_by: RegulatoryChange | None = None) -> None:
    with watch_write("test: a library editor moved the change"):
        change.status = status.value
        change.superseded_by = superseded_by
        change.save()


def change_chunks() -> list[SearchChunk]:
    with transaction.atomic(), tenancy.platform_zone():
        return list(SearchChunk.objects.filter(source_type=SearchSource.CHANGE.value))


def search(query: str, *, tenant: Tenant, filters: SearchFilters | None = None) -> Any:
    body = SearchRequest(q=query, lang="en", types=[SearchHitType.CHANGE], filters=filters, limit=20)
    return hybrid.run_search(body, tenant_id=tenant.id, user_id=uuid.uuid4())


class ChangeReads(TestCase):
    change: ClassVar[RegulatoryChange]

    @classmethod
    def setUpTestData(cls) -> None:
        seed_reference()
        cls.change = watch.change_with_timeline(terms=("regime:securities",), flags=("advice_perimeter",))

    def test_one_chunk_per_content_language_with_the_facts_a_filter_compares(self) -> None:
        read = sources.change_chunks(self.change.id)

        self.assertEqual(read.source_type, SearchSource.CHANGE.value)
        self.assertEqual(read.source_ids, [self.change.id])
        self.assertEqual(sorted(chunk.language for chunk in read.chunks), LANGUAGES)
        securities = watch.term("regime:securities")
        for chunk in read.chunks:
            with self.subTest(language=chunk.language):
                self.assertEqual((chunk.source_id, chunk.title, chunk.body), (self.change.id, TITLE, SUMMARY))
                self.assertEqual(chunk.hierarchy_path, "Finansinspektionen")
                self.assertEqual((chunk.valid_from, chunk.valid_to), (watch.PUBLISHED_ON, None))
                self.assertEqual(chunk.metadata["authority"], "fi")
                self.assertEqual(chunk.metadata["jurisdiction"], "se")
                self.assertEqual(chunk.metadata["term_ids"], [str(securities.id)], "a flag never scopes a change")
                self.assertIsNone(chunk.metadata["instrument_id"])
                self.assertIsNone(chunk.metadata["obligation_id"])

    def test_a_change_with_no_authority_names_no_jurisdiction(self) -> None:
        row = watch.change(authority=None)

        metadata = sources.change_chunks(row.id).chunks[0].metadata

        self.assertEqual((metadata["authority"], metadata["jurisdiction"]), (None, None))

    def test_a_withdrawn_or_superseded_change_has_no_chunk_and_keeps_its_scope(self) -> None:
        successor = watch.change()
        for status in (ChangeStatus.WITHDRAWN, ChangeStatus.SUPERSEDED):
            with self.subTest(status=status):
                row = watch.change()
                set_status(row, status, superseded_by=successor if status is ChangeStatus.SUPERSEDED else None)

                read = sources.change_chunks(row.id)

                self.assertEqual((read.source_ids, read.chunks), ([row.id], []))

    def test_an_unknown_change_reads_as_nothing(self) -> None:
        read = sources.change_chunks(uuid.uuid4())

        self.assertEqual((read.source_ids, read.chunks), ([], []))

    def test_a_full_rebuild_reads_every_change(self) -> None:
        self.assertIn(self.change.id, sources.change_ids())


class TheChangeRebuild(TestCase):
    def setUp(self) -> None:
        seed_reference()
        self.change = watch.change_with_timeline()

    def rebuild(self) -> indexing.IndexCounts:
        with transaction.atomic():
            return indexing.reindex_change(self.change.id)

    def test_the_rebuild_writes_shared_chunks_and_a_second_run_writes_nothing(self) -> None:
        first = self.rebuild()
        second = self.rebuild()

        self.assertEqual(first.created, len(LANGUAGES))
        self.assertEqual((second.created, second.updated, second.deleted, second.unchanged), (0, 0, 0, len(LANGUAGES)))
        chunks = change_chunks()
        self.assertEqual(sorted(chunk.language_id for chunk in chunks), LANGUAGES)
        self.assertTrue(all(chunk.owner_tenant_id is None for chunk in chunks))

    def test_a_corrected_summary_rewrites_the_chunks_and_drops_their_vectors(self) -> None:
        self.rebuild()
        indexing.embed_backlog()
        with watch_write("test: a correction"):
            self.change.summary = "FI's board amended four regulations in the securities area."
            self.change.save()

        counts = self.rebuild()

        self.assertEqual(counts.updated, len(LANGUAGES))
        self.assertTrue(all(chunk.embedding is None for chunk in change_chunks()))

    def test_a_withdrawn_change_loses_its_chunks(self) -> None:
        self.rebuild()
        set_status(self.change, ChangeStatus.WITHDRAWN)

        counts = self.rebuild()

        self.assertEqual(counts.deleted, len(LANGUAGES))
        self.assertEqual(change_chunks(), [])

    def test_a_rebuild_of_everything_includes_the_changes(self) -> None:
        with transaction.atomic():
            counts = indexing.reindex_all()

        self.assertEqual(counts.created, len(LANGUAGES))
        self.assertEqual({chunk.source_id for chunk in change_chunks()}, {self.change.id})


class TheChangeHandler(TestCase):
    """The watch events reach the index through the one cursor (ruling 9), with no tenant
    active, and without a watch writer being touched."""

    def setUp(self) -> None:
        seed_reference()
        self.change = watch.change_with_timeline()
        flush_outbox()

    def test_one_handler_is_registered_for_each_watch_event_that_moves_a_change(self) -> None:
        self.assertEqual(
            tasks.CHANGE_TOPICS, (registration.REGISTERED, registration.UPDATED, curation.FACTS_UPDATED)
        )
        for topic in tasks.CHANGE_TOPICS:
            with self.subTest(topic=topic):
                self.assertEqual(outbox.handlers_for(topic).count(tasks.index_change), 1)
        # A registration also opens every bank's case; that handler is still there, and it
        # is the only other one.
        self.assertEqual(
            set(outbox.handlers_for(registration.REGISTERED)), {creation.create_cases, tasks.index_change}
        )

    def test_each_event_rebuilds_the_change_with_no_tenant_active_and_asks_no_model(self) -> None:
        seen: list[Any] = []
        original = indexing.reindex_change

        def watched(change_id: uuid.UUID) -> indexing.IndexCounts:
            # The database setting, which is what the policies read and what a write of
            # the shared zone needs; the Python mirror is `@tenant_task`'s, and unset too.
            seen.append((tenancy.database_tenant_id(), tenancy.active_tenant_id(), change_id))
            return original(change_id)

        for topic in tasks.CHANGE_TOPICS:
            with self.subTest(topic=topic):
                seen.clear()
                change_event(self.change, topic)
                with mock.patch.object(indexing, "reindex_change", watched), mock.patch.object(
                    embedder, "get_embedder"
                ) as adapter:
                    result = outbox.deliver_batch()

                self.assertEqual((result.delivered, result.failed), (1, 0))
                self.assertEqual(seen, [(None, None, self.change.id)])
                adapter.assert_not_called()
                self.assertEqual(len(change_chunks()), len(LANGUAGES), "one chunk per language, never a duplicate")

    def test_a_replayed_event_changes_nothing(self) -> None:
        event = change_event(self.change, registration.UPDATED)
        tasks.index_change(event)
        before = {(chunk.id, chunk.language_id) for chunk in change_chunks()}

        with mock.patch.object(indexing, "_write", wraps=indexing._write) as write:
            tasks.index_change(event)

        self.assertEqual(write.call_count, 1)
        self.assertEqual({(chunk.id, chunk.language_id) for chunk in change_chunks()}, before)

    def test_a_withdrawal_through_the_facts_event_removes_the_chunks(self) -> None:
        change_event(self.change, registration.REGISTERED)
        outbox.deliver_batch()
        set_status(self.change, ChangeStatus.WITHDRAWN)
        change_event(self.change, curation.FACTS_UPDATED)

        result = outbox.deliver_batch()

        self.assertEqual((result.delivered, result.failed), (1, 0))
        self.assertEqual(change_chunks(), [])

    def test_an_event_recorded_in_a_banks_zone_writes_no_chunk_and_asks_no_model(self) -> None:
        """Nothing a bank owns is indexed, embedded or sent to a model in R1 (D-10, owner
        items 4 and 10). The watch never records a change event in a bank's zone, so this
        row is the one that must not leak if it ever did."""
        bank = factories.tenant(slug="a-bank")
        flush_outbox()
        for topic in tasks.CHANGE_TOPICS:
            change_event(self.change, topic, tenant=bank)

        with mock.patch.object(indexing, "reindex_change") as rebuild, mock.patch.object(
            embedder, "get_embedder"
        ) as adapter, self.assertLogs("apps.search.tasks", level="WARNING") as logs:
            result = outbox.deliver_batch()
            indexing.embed_backlog()

        self.assertEqual(result.failed, 0)
        self.assertGreaterEqual(result.delivered, len(tasks.CHANGE_TOPICS))
        rebuild.assert_not_called()
        adapter.assert_not_called()
        self.assertEqual(change_chunks(), [])
        self.assertEqual(len(logs.records), len(tasks.CHANGE_TOPICS), "each skipped row is named, never its content")

    def test_an_event_naming_no_change_is_delivered_without_a_chunk(self) -> None:
        with transaction.atomic():
            tenancy.clear_tenant()
            record(
                action=registration.UPDATED,
                actor=Actor.system("watch"),
                subject_type=registration.SUBJECT_TYPE,
                subject_id=None,
                subject_title="",
                summary="A watch event.",
                tenant_id=None,
            )

        result = outbox.deliver_batch()

        self.assertEqual((result.delivered, result.failed), (1, 0))
        self.assertEqual(change_chunks(), [])


class ChangeSearch(TestCase):
    """Both legs find a registered change, and the bank's scope is the watch feed's."""

    tenant: ClassVar[Tenant]
    securities: ClassVar[RegulatoryChange]
    insurance: ClassVar[RegulatoryChange]

    @classmethod
    def setUpTestData(cls) -> None:
        seed_reference()
        cls.securities = watch.change_with_timeline(terms=("regime:securities",))
        cls.insurance = watch.change_with_timeline(
            title="Insurance distribution guidance on product oversight",
            terms=("regime:insurance",),
        )
        with transaction.atomic():
            indexing.reindex_all()
        indexing.embed_backlog()
        cls.tenant = factories.tenant(slug="change-search")

    def setUp(self) -> None:
        FootprintTerm.objects.create(tenant=self.tenant, term=watch.term("regime:securities"))

    def test_a_change_is_found_by_its_words_and_by_its_meaning(self) -> None:
        response = search("amended rules on paying for investment research", tenant=self.tenant)

        hit = next(hit for hit in response.items if hit.id == self.securities.id)
        self.assertEqual(hit.type, SearchHitType.CHANGE)
        self.assertEqual(hit.match_kind, SearchMatchKind.BOTH)
        self.assertEqual(hit.title, TITLE)
        self.assertEqual([item.id for item in response.items].count(self.securities.id), 1, "one hit per change")

    def test_a_change_is_held_back_by_the_banks_scope_like_the_feed_holds_it_back(self) -> None:
        inside = {hit.id for hit in search("insurance distribution guidance", tenant=self.tenant).items}
        outside = {
            hit.id
            for hit in search(
                "insurance distribution guidance", tenant=self.tenant, filters=SearchFilters(in_footprint=False)
            ).items
        }

        self.assertNotIn(self.insurance.id, inside, "the bank does not do insurance")
        self.assertIn(self.insurance.id, outside)

    def test_a_change_is_not_found_before_it_was_published(self) -> None:
        body = SearchRequest(
            q="investment research",
            lang="en",
            types=[SearchHitType.CHANGE],
            as_of=watch.PUBLISHED_ON - datetime.timedelta(days=1),
            limit=20,
        )

        response = hybrid.run_search(body, tenant_id=self.tenant.id, user_id=uuid.uuid4())

        self.assertEqual(response.items, [])

    def test_an_agent_finds_the_change_through_find_similar(self) -> None:
        response = hybrid.find_similar(
            SimilarRequest(text="amended rules on paying for investment research", types=[SearchHitType.CHANGE], limit=10),
            caller_id=uuid.uuid4(),
        )

        self.assertIn(self.securities.id, {hit.id for hit in response.items})


class TheAppRoleSeesASharedChunk(TransactionTestCase):
    """As `cw_app`, under forced row-level security, the chunk the handler wrote is the
    shared zone's: a bank reads it, and it names no owner."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        with transaction.atomic():
            seed_reference()
        self.bank = factories.tenant(slug="app-role-bank")
        self.change = watch.change_with_timeline()
        flush_outbox()
        change_event(self.change, registration.UPDATED)
        outbox.deliver_batch()

    def test_the_written_chunks_are_shared(self) -> None:
        with transaction.atomic(using="app"):
            tenancy.activate(self.bank.id, using="app")
            with connections["app"].cursor() as cursor:
                cursor.execute(
                    "SELECT lang, owner_tenant_id FROM search_chunk WHERE source_type = %s AND source_id = %s",
                    [SearchSource.CHANGE.value, self.change.id],
                )
                rows = cursor.fetchall()

        self.assertEqual(sorted(language for language, _ in rows), LANGUAGES)
        self.assertEqual({owner for _, owner in rows}, {None})
