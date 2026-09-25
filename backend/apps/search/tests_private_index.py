"""A bank's own record never reaches the index, an embedding or a reranker (INV-07, OWN-04, D-57).

What these tests hold in place, in the order a reviewer would ask about it:

1. **The rebuild leaves a private record out, and every child of it.** A full rebuild
   over a bank's own instrument, its obligation, an obligation of its own under a shared
   instrument and their version and provision rows writes no chunk for any of them, while
   the shared record beside them is indexed as always.
2. **The worker embeds none of their text.** The outbox delivery and the beat sweep hand
   the embedder shared text only, whatever the backlog holds: a chunk a bank owns, however
   it got there, is not the embedder's to read, so it is never sent and never filled.
3. **The reranker judges shared text only.** A reader's search and an agent's
   find-similar pass the reranker no word of a bank's own chunk, and neither returns it.

Every private text carries one sentinel, so any place it turns up is a leak.
"""

from __future__ import annotations

import contextlib
import uuid
from typing import Any
from unittest import mock

from django.db import transaction
from django.test import TestCase

from apps.library import testing as build
from apps.search import hybrid, indexing
from apps.search.models import SearchChunk, SearchSource
from apps.search.schemas import SearchRequest, SimilarRequest
from apps.search.tests_indexing import flush_outbox, library_fixture
from apps.shared import factories, outbox, tenancy
from apps.shared.adapters import embedder, reranker

# Written into every private text and no shared one.
SENTINEL = "Vår egen tolkning av likviditetsbufferten"
SHARED_SUMMARY = "The institution keeps a liquidity buffer it can draw on within a day."


class PrivateRecordsMixin:
    """One shared obligation, and beside it tenant A's own instrument with an obligation
    and a provision, and an obligation of tenant A's own under the shared instrument."""

    def build_records(self) -> None:
        library_fixture()
        self.tenant = factories.tenant(slug="own-records-bank")
        shared_instrument = build.instrument(key="inv07-shared", regime="regime:securities")
        self.shared = build.obligation(
            shared_instrument, key="obl-inv07-shared", versions=((None, {"en": SHARED_SUMMARY}),)
        )
        own_instrument = build.instrument(
            key="inv07-own", short_name=f"{SENTINEL} (instrument)", regime="regime:securities", owner_tenant=self.tenant
        )
        own = build.obligation(
            own_instrument,
            key="obl-inv07-own",
            titles={"sv": f"{SENTINEL} (titel)"},
            versions=((None, {"sv": f"{SENTINEL}, första lydelsen."}), (None, {"sv": f"{SENTINEL}, andra lydelsen."})),
            owner_tenant=self.tenant,
        )
        own_under_shared = build.obligation(
            shared_instrument,
            key="obl-inv07-own-under-shared",
            titles={"en": f"{SENTINEL} (under a shared instrument)"},
            versions=((None, {"en": f"{SENTINEL}, as we read the shared act."}),),
            owner_tenant=self.tenant,
        )
        provision = build.provision(own_instrument, key="inv07-own-1", heading=f"{SENTINEL} (rubrik)")
        self.private_version_ids = {
            *own.versions.values_list("id", flat=True),
            *own_under_shared.versions.values_list("id", flat=True),
            build.provision_version(provision, texts={"sv": f"{SENTINEL}, bestämmelsen."}).id,
        }

    def own_chunk(self) -> SearchChunk:
        """A chunk a bank owns, written straight into the index: the shape a rebuild can
        never produce, so the embedder and the reranker are proven to refuse it on their own."""
        tenancy.activate(self.tenant.id)
        with indexing.index_write("test: a chunk this bank owns"):
            chunk = SearchChunk(
                source_type=SearchSource.OBLIGATION_VERSION.value,
                source_id=uuid.uuid4(),
                language_id="en",
                title=f"{SENTINEL} (a chunk of our own)",
                body=f"{SENTINEL}: {SHARED_SUMMARY}",
                owner_tenant=self.tenant,
            )
            chunk.save()
        tenancy.clear_tenant()
        return chunk


def spy_on_embedder(test: TestCase) -> list[str]:
    """Every text the mock embedder is handed, in order."""
    texts: list[str] = []
    original = embedder.MockEmbedder.embed

    def seen(adapter: embedder.MockEmbedder, batch: list[str]) -> list[list[float]]:
        texts.extend(batch)
        return original(adapter, batch)

    patched = mock.patch.object(embedder.MockEmbedder, "embed", seen)
    patched.start()
    test.addCleanup(patched.stop)
    return texts


def spy_on_reranker(test: TestCase) -> list[str]:
    """Every document the mock reranker is asked to judge, in order."""
    judged: list[str] = []
    original = reranker.MockReranker.rerank

    def seen(adapter: reranker.MockReranker, *, query: str, documents: list[str]) -> Any:
        judged.extend(documents)
        return original(adapter, query=query, documents=documents)

    patched = mock.patch.object(reranker.MockReranker, "rerank", seen)
    patched.start()
    test.addCleanup(patched.stop)
    return judged


class ThePrivateRecordIsNeverIndexed(PrivateRecordsMixin, TestCase):
    def setUp(self) -> None:
        self.build_records()
        flush_outbox()

    def test_a_rebuild_writes_no_chunk_for_a_private_record_or_any_child_of_it(self) -> None:
        with transaction.atomic():
            indexing.reindex_all()

        self.assertFalse(SearchChunk.objects.filter(source_id__in=self.private_version_ids).exists())
        self.assertFalse(SearchChunk.objects.filter(body__contains=SENTINEL).exists())
        self.assertFalse(SearchChunk.objects.filter(title__contains=SENTINEL).exists())
        self.assertTrue(SearchChunk.objects.filter(body=SHARED_SUMMARY).exists(), "the shared record is still indexed")

    def test_the_worker_hands_the_embedder_shared_text_only(self) -> None:
        texts = spy_on_embedder(self)
        with transaction.atomic():
            indexing.reindex_all()

        self.assertEqual(outbox.deliver_batch().failed, 0)
        indexing.embed_backlog()

        self.assertTrue(any(SHARED_SUMMARY in text for text in texts), "the shared record was embedded")
        self.assertFalse([text for text in texts if SENTINEL in text])

    def test_a_chunk_a_bank_owns_is_never_embedded(self) -> None:
        own = self.own_chunk()
        texts = spy_on_embedder(self)

        indexing.embed_backlog()
        with transaction.atomic():
            indexing.embed_pending()

        self.assertFalse([text for text in texts if SENTINEL in text])
        self.assertIsNone(self.embedding_of(own))

    def test_the_embedder_refuses_a_chunk_a_bank_owns_in_the_query_as_well_as_by_the_policy(self) -> None:
        """Narrower, never wider (`hybrid._filtered`): the policy hides the bank's chunk
        from the worker's shared zone, and the query leaves it out on its own, so a read
        run in the bank's zone by mistake still hands the embedder none of its text."""
        own = self.own_chunk()
        texts = spy_on_embedder(self)
        tenancy.activate(self.tenant.id)

        with mock.patch.object(tenancy, "platform_zone", contextlib.nullcontext):
            indexing.embed_backlog()

        self.assertFalse([text for text in texts if SENTINEL in text])
        self.assertIsNone(self.embedding_of(own))

    def embedding_of(self, chunk: SearchChunk) -> Any:
        tenancy.activate(self.tenant.id)
        try:
            return SearchChunk.objects.values_list("embedding", flat=True).get(pk=chunk.pk)
        finally:
            tenancy.clear_tenant()


class TheRerankerJudgesSharedTextOnly(PrivateRecordsMixin, TestCase):
    def setUp(self) -> None:
        self.build_records()
        with transaction.atomic():
            indexing.reindex_all()
        indexing.embed_backlog()
        self.own = self.own_chunk()
        self.documents = spy_on_reranker(self)

    def test_a_readers_search_passes_the_reranker_no_private_text(self) -> None:
        response = hybrid.run_search(
            SearchRequest(q=f"{SENTINEL} liquidity buffer"), tenant_id=self.tenant.id, user_id=uuid.uuid4()
        )

        self.assertFalse([document for document in self.documents if SENTINEL in document])
        self.assertFalse([hit for hit in response.items if SENTINEL in hit.title])

    def test_find_similar_passes_the_reranker_no_private_text_and_returns_shared_records_only(self) -> None:
        response = hybrid.find_similar(
            SimilarRequest(text=f"{SENTINEL}: {SHARED_SUMMARY}"), caller_id=uuid.uuid4(), tenant_id=self.tenant.id
        )

        self.assertTrue(self.documents, "the reranker was asked")
        self.assertFalse([document for document in self.documents if SENTINEL in document])
        self.assertTrue(response.items)
        self.assertFalse([hit for hit in response.items if SENTINEL in hit.title])
