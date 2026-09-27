"""The index is filled from the library, and only from the library (SRC-01, SRC-02, D-10).

What these tests hold in place, in the order a reviewer would ask about it:

1. **The reads are reads.** `apps/search/sources.py` makes no write call of any kind, so
   the library fence keeps watching it without ever having to allow it.
2. **The rebuild is faithful and idempotent.** An obligation's chunks are its versions'
   summaries, one per language, carrying the validity dates the obligation card draws and
   the vocabulary keys a filter compares. Running it twice writes nothing the second time,
   so an embedding already paid for survives.
3. **Only shared records are indexed.** A record a bank owns, or one whose instrument a
   bank owns, leaves no chunk and asks for no embedding (D-10, owner item 10).
4. **The approval carries the index with it, and no model call.** Approving an
   obligation-version proposal rewrites that obligation's chunks in the approval's own
   transaction, and nothing embeds inside it, so the approval stays inside its budget.
5. **Embedding happens out of band, through the one relay.** The outbox cursor delivers
   the library event with no tenant active, and the handler fills one batch. A failing
   embedder costs its own row an attempt and nothing else.
6. **What one delivery leaves behind, the sweep takes.** A delivery holds the cursor's
   lock, so it embeds a batch and stops rather than making a full rebuild's model calls
   with every other consumer waiting. The beat sweep drains the rest, and it is also what
   picks up a rebuild whose row spent its attempts and a corpus that was never embedded
   because no model was contracted at the time.
"""

from __future__ import annotations

import ast
import datetime
import inspect
import sys
import time
import uuid
from io import StringIO
from pathlib import Path
from typing import Any
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone
from django.test import TestCase, override_settings

from apps.library.models import (
    Instrument,
    Jurisdiction,
    Obligation,
    ObligationSummary,
    ObligationTerm,
    ObligationTitle,
    ObligationVersion,
    Provision,
    ProvisionText,
    ProvisionVersion,
)
from apps.library.reading import version_rows
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.proposals.apply import apply as apply_proposal
from apps.proposals.models import Proposal, ProposalKind
from apps.search import indexing, sources, tasks
from apps.search.models import SearchChunk, SearchSource
from apps.shared import factories, outbox, tenancy
from apps.shared.adapters import embedder
from apps.shared.models import AuditEvent, OutboxEvent
from apps.shared.tenancy import library_write
from apps.shared.testing import sign_in
from apps.shared.tests_library_fence import WRITE_METHODS
from apps.taxonomy.models import DutyType, InstrumentLevel, ProvisionKind, TaxonomyTerm
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from config.celery import app as celery_app

# From the prototype's data (design/prototype), so the stems and the identifiers are real.
REF = "FFFS 2017:2"
TITLE_SV = "Lämna information om kostnader och avgifter"
TITLE_EN = "Disclose all costs and charges"
SUMMARY_SV = "Institutet ska i god tid lämna information om samtliga kostnader och avgifter."
SUMMARY_EN = "The institution discloses all costs and charges in good time."


def flush_outbox() -> None:
    """Mark everything the seeds and the fixture recorded as delivered, so a test that
    looks at its own event is not reading the hundredth row of a batch."""
    with transaction.atomic():
        OutboxEvent.objects.filter(published_at__isnull=True).update(published_at=timezone.now())


def library_fixture() -> None:
    seed_languages()
    seed_jurisdictions()
    seed_library_vocabularies()
    seed_term_dimensions()
    seed_taxonomy_terms()


class LibraryFixtureMixin:
    """One instrument, one obligation with two versions in two languages, one provision."""

    def build_library(self, *, owner: Any = None, instrument_owner: Any = None) -> None:
        library_fixture()
        with library_write("test fixture"):
            self.instrument = Instrument.objects.create(
                stable_key="fffs-2017-2",
                short_name="FFFS 2017:2",
                official_ref=REF,
                source_url="https://www.fi.se/",
                level=InstrumentLevel.objects.get(key="act"),
                binding=True,
                jurisdiction=Jurisdiction.objects.get(key="se"),
                regime=TaxonomyTerm.objects.get(dimension__key="regime", key="securities"),
                owner_tenant=instrument_owner,
                created_origin="user",
            )
            self.obligation = Obligation.objects.create(
                stable_key="obl-costs-and-charges",
                instrument=self.instrument,
                ref_label="9 kap. 6 §",
                duty_type=DutyType.objects.get(key="disclosure"),
                owner_tenant=owner,
                created_origin="user",
                source_url="https://www.fi.se/",
                source_label=f"{REF}, 9 kap. 6 §",
            )
            ObligationTitle.objects.create(obligation=self.obligation, language_id="sv", text=TITLE_SV, is_original=True)
            ObligationTitle.objects.create(obligation=self.obligation, language_id="en", text=TITLE_EN)
            self.version = ObligationVersion.objects.create(
                obligation=self.obligation, version_number=1, effective_from=datetime.date(2026, 1, 1)
            )
            ObligationSummary.objects.create(version=self.version, language_id="sv", text=SUMMARY_SV, is_original=True)
            ObligationSummary.objects.create(version=self.version, language_id="en", text=SUMMARY_EN)
            self.provision = Provision.objects.create(
                stable_key="fffs-2017-2-9-6",
                instrument=self.instrument,
                kind=ProvisionKind.objects.all()[0],
                ref_label="9 kap. 6 §",
                heading="Information om kostnader",
                path="FFFS 2017:2 > 9 kap. 6 §",
            )
            self.provision_version = ProvisionVersion.objects.create(
                provision=self.provision, version_number=1, effective_from=datetime.date(2026, 1, 1)
            )
            ProvisionText.objects.create(
                version=self.provision_version,
                language_id="sv",
                text="Institutet ska lämna information om kostnader.",
                is_original=True,
            )

    def add_version(self, *, effective_from: datetime.date | None, text: str = "Ny text om avgifter.") -> ObligationVersion:
        with library_write("test fixture"):
            version = ObligationVersion.objects.create(
                obligation=self.obligation, version_number=2, effective_from=effective_from
            )
            ObligationSummary.objects.create(version=version, language_id="sv", text=text, is_original=True)
        return version


class SourcesAreReads(TestCase):
    """`sources.py` is the index's read of the library and nothing else."""

    def test_sources_makes_no_write_call(self) -> None:
        tree = ast.parse(Path(sources.__file__).read_text(encoding="utf-8"))
        writes = [
            (node.lineno, node.func.attr)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in WRITE_METHODS
        ]
        self.assertEqual(writes, [], f"apps/search/sources.py writes: {writes}")


class ObligationReads(LibraryFixtureMixin, TestCase):
    def setUp(self) -> None:
        self.build_library()

    def test_one_chunk_per_version_per_language_with_the_facts_a_filter_compares(self) -> None:
        read = sources.obligation_chunks(self.obligation.id)

        self.assertEqual(read.source_type, SearchSource.OBLIGATION_VERSION.value)
        self.assertEqual(read.source_ids, [self.version.id])
        self.assertEqual({chunk.language for chunk in read.chunks}, {"sv", "en"})
        swedish = next(chunk for chunk in read.chunks if chunk.language == "sv")
        self.assertIn(REF, swedish.title, "an identifier is won by the keyword leg, so it has to be in the text")
        self.assertIn(TITLE_SV, swedish.title)
        self.assertEqual(swedish.body, SUMMARY_SV)
        self.assertEqual(swedish.hierarchy_path, f"{REF} > 9 kap. 6 §")
        self.assertEqual(swedish.valid_from, datetime.date(2026, 1, 1))
        self.assertIsNone(swedish.valid_to)
        self.assertEqual(swedish.metadata["obligation_id"], str(self.obligation.id))
        self.assertEqual(swedish.metadata["jurisdiction"], "se")
        self.assertEqual(swedish.metadata["duty_type"], "disclosure")
        self.assertTrue(swedish.metadata["binding"])

    def test_the_scope_terms_travel_on_the_chunk(self) -> None:
        term = TaxonomyTerm.objects.all()[0]
        with library_write("test fixture"):
            ObligationTerm.objects.create(obligation=self.obligation, term=term)

        chunk = sources.obligation_chunks(self.obligation.id).chunks[0]

        self.assertIn(str(term.id), chunk.metadata["term_ids"])

    def test_a_version_ends_the_day_before_the_next_one_takes_effect(self) -> None:
        second = self.add_version(effective_from=datetime.date(2026, 7, 1))

        by_source = {chunk.source_id: chunk for chunk in sources.obligation_chunks(self.obligation.id).chunks}

        self.assertEqual(by_source[self.version.id].valid_to, datetime.date(2026, 6, 30))
        self.assertIsNone(by_source[second.id].valid_to)

    def test_the_end_date_is_the_one_the_obligation_card_draws(self) -> None:
        """One rule, pinned to `reading.version_rows()`, so the card and the index agree."""
        self.add_version(effective_from=datetime.date(2026, 7, 1))
        versions = list(ObligationVersion.objects.filter(obligation=self.obligation))

        rows = version_rows(versions)
        chunks = {chunk.source_id: chunk for chunk in sources.obligation_chunks(self.obligation.id).chunks}

        for version in versions:
            card = rows[version.version_number].effective_to
            self.assertEqual(chunks[version.id].valid_to, card.date if card else None)

    def test_a_version_corrected_the_same_day_is_not_indexed(self) -> None:
        second = self.add_version(effective_from=datetime.date(2026, 1, 1))

        read = sources.obligation_chunks(self.obligation.id)

        self.assertEqual(read.source_ids, [self.version.id, second.id], "the scope still covers both")
        self.assertEqual({chunk.source_id for chunk in read.chunks}, {second.id}, "the correction wins")

    def test_a_later_version_with_no_date_runs_since_always_and_hides_the_earlier_one(self) -> None:
        """A null `effective_from` means since the obligation began (`logic.in_force`), so
        a version written that way after another leaves the earlier one never in force."""
        second = self.add_version(effective_from=None)

        read = sources.obligation_chunks(self.obligation.id)

        self.assertEqual({chunk.source_id for chunk in read.chunks}, {second.id})

    def test_a_record_a_bank_owns_is_not_indexed(self) -> None:
        tenant = factories.tenant(slug="owner-bank")
        with library_write("test fixture"):
            Obligation.objects.filter(id=self.obligation.id).update(owner_tenant=tenant)

        read = sources.obligation_chunks(self.obligation.id)

        self.assertEqual(read.chunks, [])
        self.assertEqual(read.source_ids, [self.version.id], "its chunks are still the rebuild's to remove")

    def test_a_record_of_an_instrument_a_bank_owns_is_not_indexed(self) -> None:
        tenant = factories.tenant(slug="owner-bank")
        with library_write("test fixture"):
            Instrument.objects.filter(id=self.instrument.id).update(owner_tenant=tenant)

        self.assertEqual(sources.obligation_chunks(self.obligation.id).chunks, [])
        self.assertEqual(sources.provision_chunks(self.provision.id).chunks, [])

    def test_an_unknown_obligation_reads_as_nothing(self) -> None:
        read = sources.obligation_chunks(uuid.uuid4())

        self.assertEqual((read.source_ids, read.chunks), ([], []))


class ProvisionReads(LibraryFixtureMixin, TestCase):
    def setUp(self) -> None:
        self.build_library()

    def test_a_provision_version_is_indexed_with_its_path_and_its_instrument(self) -> None:
        read = sources.provision_chunks(self.provision.id)

        self.assertEqual(read.source_type, SearchSource.PROVISION_VERSION.value)
        chunk = read.chunks[0]
        self.assertEqual(chunk.language, "sv")
        self.assertIn(REF, chunk.title)
        self.assertIn("Information om kostnader", chunk.title)
        self.assertEqual(chunk.hierarchy_path, "FFFS 2017:2 > 9 kap. 6 §")
        self.assertEqual(chunk.metadata["instrument_id"], str(self.instrument.id))
        self.assertIsNone(chunk.metadata["obligation_id"], "a provision carries no obligation of its own")
        self.assertIsNone(chunk.metadata["duty_type"])

    def test_a_stored_end_date_is_the_provisions_own(self) -> None:
        """A provision version may be written with the day its text stops applying; an
        obligation version never is, so the derivation above is the only rule it has."""
        with library_write("test fixture"):
            provision = Provision.objects.create(
                stable_key="fffs-2017-2-9-7",
                instrument=self.instrument,
                kind=ProvisionKind.objects.all()[0],
                ref_label="9 kap. 7 §",
                heading="Upphävd bestämmelse",
                path="FFFS 2017:2 > 9 kap. 7 §",
            )
            version = ProvisionVersion.objects.create(
                provision=provision,
                version_number=1,
                effective_from=datetime.date(2026, 1, 1),
                effective_to=datetime.date(2026, 9, 30),
            )
            ProvisionText.objects.create(version=version, language_id="sv", text="Gammal text.", is_original=True)

        chunk = sources.provision_chunks(provision.id).chunks[0]

        self.assertEqual(chunk.valid_to, datetime.date(2026, 9, 30))


    def test_an_unknown_provision_reads_as_nothing(self) -> None:
        read = sources.provision_chunks(uuid.uuid4())

        self.assertEqual((read.source_ids, read.chunks), ([], []))


class TheRebuild(LibraryFixtureMixin, TestCase):
    def setUp(self) -> None:
        self.build_library()

    def rebuild(self) -> indexing.IndexCounts:
        with transaction.atomic():
            return indexing.reindex(self.obligation.id)

    def test_a_rebuild_writes_the_chunks_and_nothing_else(self) -> None:
        counts = self.rebuild()

        self.assertEqual(counts.created, 2)
        self.assertEqual(SearchChunk.objects.count(), 2)
        self.assertTrue(all(chunk.owner_tenant_id is None for chunk in SearchChunk.objects.all()))

    def test_running_it_again_changes_nothing(self) -> None:
        self.rebuild()
        before = {chunk.id: chunk.title for chunk in SearchChunk.objects.all()}
        with indexing.index_write("test: pretend the worker embedded"):
            SearchChunk.objects.all().update(embedding=[0.5] * 1024, embedding_model="mock")

        counts = self.rebuild()

        self.assertEqual((counts.created, counts.updated, counts.deleted), (0, 0, 0))
        self.assertEqual(counts.unchanged, 2)
        self.assertEqual({chunk.id: chunk.title for chunk in SearchChunk.objects.all()}, before, "rows were replaced")
        self.assertTrue(all(chunk.embedding is not None for chunk in SearchChunk.objects.all()), "embeddings were lost")

    def test_changed_text_rewrites_the_chunk_and_drops_its_embedding(self) -> None:
        """A summary is append-only, so what changes under a chunk is the record around
        it: here the obligation's Swedish title, which is part of the citation line the
        keyword leg reads. The vector was made from text the chunk no longer holds."""
        self.rebuild()
        with indexing.index_write("test: pretend the worker embedded"):
            SearchChunk.objects.all().update(embedding=[0.5] * 1024, embedding_model="mock")
        with library_write("test fixture"):
            ObligationTitle.objects.filter(obligation=self.obligation, language_id="sv").update(text="Ny rubrik")

        counts = self.rebuild()

        self.assertEqual((counts.created, counts.updated, counts.unchanged), (0, 1, 1))
        swedish = SearchChunk.objects.get(language_id="sv")
        self.assertIn("Ny rubrik", swedish.title)
        self.assertIsNone(swedish.embedding, "a rewritten chunk keeps a vector of the text it no longer holds")
        self.assertIsNotNone(SearchChunk.objects.get(language_id="en").embedding)

    def test_a_version_corrected_the_same_day_loses_its_chunks(self) -> None:
        """`logic.in_force`: two versions effective the same day, the later number wins.
        The earlier one was never readable, so the rebuild takes its chunks away."""
        self.rebuild()
        self.add_version(effective_from=datetime.date(2026, 1, 1))

        counts = self.rebuild()

        self.assertEqual(counts.deleted, 2)
        self.assertEqual([chunk.language_id for chunk in SearchChunk.objects.all()], ["sv"])

    def test_the_indexer_writes_the_shared_zone_from_inside_a_banks_own(self) -> None:
        """Every chunk belongs to no tenant, so the rebuild steps out of whatever zone its
        caller is in and puts it straight back (H15). A bank's own words cannot ride out
        with it: an owned record never becomes a chunk in the first place."""
        tenant = factories.tenant(slug="a-bank")
        with transaction.atomic():
            tenancy.activate(tenant.id)

            indexing.reindex(self.obligation.id)

            self.assertEqual(tenancy.database_tenant_id(), tenant.id, "the session's zone was not put back")
        self.assertEqual(SearchChunk.objects.filter(owner_tenant__isnull=True).count(), 2)

    def test_a_rebuild_of_everything_writes_one_audit_row_with_counts(self) -> None:
        with transaction.atomic():
            counts = indexing.reindex_all()

        self.assertEqual(counts.created, 3, "two obligation summaries and one provision text")
        rows = AuditEvent.objects.filter(action=indexing.INDEX_REBUILT)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.get().after["created"], 3)
        self.assertEqual(OutboxEvent.objects.filter(topic=indexing.INDEX_REBUILT).count(), 1)

    def test_a_rebuild_of_everything_is_idempotent(self) -> None:
        with transaction.atomic():
            indexing.reindex_all()

        with transaction.atomic():
            counts = indexing.reindex_all()

        self.assertEqual((counts.created, counts.updated, counts.deleted), (0, 0, 0))
        self.assertEqual(counts.unchanged, 3)


class TheApprovalCarriesTheIndex(LibraryFixtureMixin, TestCase):
    """The hook chunk 4 left in `apps/search/logic.py` is now the rebuild (PRO-02, SRC-01).

    Applying an approved obligation-version proposal is the path that keeps the index in
    step with the library, and it is the path a reader's search depends on being fast: the
    chunks are written inside the approval's transaction and nothing is embedded there.
    """

    def setUp(self) -> None:
        self.build_library()
        self.reviewer = factories.platform_user(roles=("library_editor",), email="reviewer@bleqq.test")
        self.proposal = Proposal.objects.create(
            kind=ProposalKind.NEW_OBLIGATION_VERSION.value,
            target_type="obligation",
            target_id=self.obligation.id,
            title="Version 2 of the costs and charges duty",
            payload={
                "summaries": {"sv": "Ny lydelse om kostnader och avgifter."},
                "original_language": "sv",
                "effective_from": "2026-07-01",
                "is_machine": False,
            },
            origin="user",
        )
        flush_outbox()

    def approve(self) -> None:
        with transaction.atomic():
            apply_proposal(self.proposal, actor=factories.user_actor(), reviewer=self.reviewer, step_up=uuid.uuid4())

    def version_proposal(self, month: int) -> Proposal:
        """A new version of the same obligation, taking effect in `month`. The proposer is
        nobody in particular: four eyes is a database constraint on the two principals,
        and an agent's proposal is decided by any reviewer."""
        return Proposal.objects.create(
            kind=ProposalKind.NEW_OBLIGATION_VERSION.value,
            target_type="obligation",
            target_id=self.obligation.id,
            title=f"A further reading of the costs and charges duty from month {month}",
            payload={
                "summaries": {"sv": f"Lydelse {month} om kostnader och avgifter."},
                "original_language": "sv",
                "effective_from": f"2027-0{month}-01",
                "is_machine": False,
            },
            origin="agent",
        )

    def test_approving_a_version_rewrites_the_chunks_in_the_approval_transaction(self) -> None:
        with mock.patch.object(embedder, "get_embedder") as adapter:
            self.approve()

        adapter.assert_not_called()
        second = ObligationVersion.objects.get(obligation=self.obligation, version_number=2)
        chunks = {(chunk.source_id, chunk.language_id): chunk for chunk in SearchChunk.objects.all()}
        self.assertEqual(chunks[(second.id, "sv")].body, "Ny lydelse om kostnader och avgifter.")
        self.assertEqual(chunks[(self.version.id, "sv")].valid_to, datetime.date(2026, 6, 30))
        self.assertTrue(all(chunk.embedding is None for chunk in chunks.values()))

    def test_the_approval_writes_no_audit_row_of_its_own_for_the_index(self) -> None:
        """Every audit row an approval writes carries the reviewer's passkey assertion
        (`apps/proposals/tests_apply.py`), which a derived rebuild cannot name. The
        approval's own row is the event the embeddings then ride."""
        self.approve()

        self.assertFalse(AuditEvent.objects.filter(action=indexing.INDEX_REBUILT).exists())
        self.assertIn(
            OutboxEvent.objects.get(topic__in=tasks.INDEX_TOPICS).topic,
            tasks.INDEX_TOPICS,
            "the approval's own event is what asks for the embeddings",
        )

    def test_the_embeddings_follow_the_approval_through_the_outbox(self) -> None:
        self.approve()

        result = outbox.deliver_batch()

        self.assertEqual(result.failed, 0)
        self.assertEqual(SearchChunk.objects.filter(embedding__isnull=True).count(), 0)

    def test_the_approval_route_stays_inside_the_endpoint_budget(self) -> None:
        """Nothing pinned `POST /proposals/{id}/approve` until the rebuild moved inside
        it (NFR-02). A proposal is applied once and never again, so each timed call
        approves a fresh version of the same obligation, which is the shape that costs
        most: every earlier version's chunk is re-read and its end date rewritten.

        CPU time on the request thread, the best of five: what the work costs without the
        waits a loaded machine adds. The suite runs under coverage, whose tracer is paused
        for the timed calls only.
        """
        headers = sign_in(self.reviewer, step_up=True)
        proposals = [self.version_proposal(month) for month in range(2, 7)]
        spent = []
        tracer = sys.gettrace()
        sys.settrace(None)
        try:
            for proposal in proposals:
                started = time.thread_time()
                response = self.client.post(
                    f"/api/v1/proposals/{proposal.id}/approve", data={}, content_type="application/json", **headers
                )
                spent.append((time.thread_time() - started) * 1000)
        finally:
            sys.settrace(tracer)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertRegex(response["Server-Timing"], r"^app;dur=\d+\.\d$")
        self.assertEqual(SearchChunk.objects.filter(source_type=SearchSource.OBLIGATION_VERSION.value).count(), 7)
        self.assertLess(min(spent), settings.API_BUDGET_MS)


class TheEmbeddingRelay(LibraryFixtureMixin, TestCase):
    """Embedding happens out of band, through the one cursor, with no tenant active."""

    def setUp(self) -> None:
        self.build_library()
        flush_outbox()
        with transaction.atomic():
            indexing.reindex_all()

    def counted_embedder(self) -> list[int]:
        """The mock embedder with one entry per call, which is what a provider bills for.
        Returns the list, which fills as the calls are made."""
        calls: list[int] = []
        original = embedder.MockEmbedder.embed

        def counted(adapter: embedder.MockEmbedder, texts: list[str]) -> list[list[float]]:
            calls.append(len(texts))
            return original(adapter, texts)

        patched = mock.patch.object(embedder.MockEmbedder, "embed", counted)
        patched.start()
        self.addCleanup(patched.stop)
        return calls

    def test_the_handler_is_registered_for_the_events_a_rebuild_emits(self) -> None:
        # That `SearchConfig.ready()` is what registers, and that nothing registers at
        # import time, is pinned in `apps/shared/tests_outbox.py`. This is the search
        # app's own read of the result: both topics, this handler, once each and first. The
        # collab app also hears of an applied version (c10-producers, COL-02).
        for topic in tasks.INDEX_TOPICS:
            with self.subTest(topic=topic):
                self.assertEqual(outbox.handlers_for(topic)[0], tasks.embed_rebuilt_chunks)
                self.assertEqual(outbox.handlers_for(topic).count(tasks.embed_rebuilt_chunks), 1)

    def test_the_sweep_is_a_beat_entry_that_takes_no_tenant(self) -> None:
        # Importing this module registered the task, which is what the worker's own
        # autodiscovery does; `apps/shared/tests_celery_registration.py` walks every entry.
        entry = settings.CELERY_BEAT_SCHEDULE["search-embed-backlog"]
        self.assertEqual(entry["task"], "apps.search.tasks.embed_search_backlog")
        self.assertIn(entry["task"], celery_app.tasks)
        self.assertEqual(entry["schedule"], settings.SEARCH_EMBED_SWEEP_INTERVAL_S)
        # A chunk belongs to no tenant, so the sweep takes none: it reaches the shared zone
        # through `tenancy.platform_zone()` like every other write of the index.
        self.assertEqual(list(inspect.signature(tasks.embed_search_backlog.run).parameters), [])

    def test_a_sweep_with_nothing_to_do_says_nothing(self) -> None:
        indexing.embed_backlog()
        with self.assertNoLogs("apps.search.tasks", level="INFO"):
            tasks.embed_search_backlog()

    def test_the_worker_fills_the_embeddings_with_no_tenant_active(self) -> None:
        seen: dict[str, Any] = {}
        original = indexing.embed_pending

        def watched() -> int:
            # The database setting, because that is what the policies read and what the
            # rebuild refuses on. A library row's handlers are put in the shared zone by
            # the cursor itself, which sets the setting and not the Python mirror
            # (apps/shared/outbox.py: the mirror belongs to `@tenant_task`).
            seen["database"] = tenancy.database_tenant_id()
            return original()

        with mock.patch.object(indexing, "embed_pending", watched):
            result = outbox.deliver_batch()

        self.assertGreaterEqual(result.delivered, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(seen, {"database": None})
        self.assertEqual(SearchChunk.objects.filter(embedding__isnull=True).count(), 0)
        self.assertEqual({chunk.embedding_model for chunk in SearchChunk.objects.all()}, {"mock"})
        self.assertTrue(all(chunk.embedded_at is not None for chunk in SearchChunk.objects.all()))

    @override_settings(SEARCH_EMBED_BATCH_SIZE=1)
    def test_a_delivery_embeds_one_batch_and_the_sweep_drains_the_rest(self) -> None:
        """A delivery runs inside the cursor's transaction and holds the lock on the one
        cursor row, so it takes a batch and stops; everything behind it — every bank's
        case creation among them — would otherwise wait out a full rebuild's model calls
        one after another (playbook 6). The sweep takes the remainder on its own clock."""
        calls = self.counted_embedder()

        result = outbox.deliver_batch()

        self.assertEqual((result.delivered, result.failed), (1, 0))
        self.assertEqual(len(calls), 1, "one model call, not one per chunk in the backlog")
        self.assertEqual(SearchChunk.objects.filter(embedding__isnull=True).count(), 2)

        self.assertEqual(indexing.embed_backlog(), 2)

        self.assertEqual(len(calls), 3)
        self.assertEqual(SearchChunk.objects.filter(embedding__isnull=True).count(), 0)

    def test_the_sweep_picks_up_a_rebuild_whose_outbox_row_spent_its_attempts(self) -> None:
        """A row that has spent `OUTBOX_MAX_ATTEMPTS` is left failed and the cursor moves
        past it, so nothing would ever ask for those embeddings again. The sweep looks at
        the chunks and not at the events, so it simply finds them."""
        with override_settings(OUTBOX_MAX_ATTEMPTS=1):
            with mock.patch.object(indexing, "embed_pending", side_effect=RuntimeError("the model is down")):
                self.assertEqual(outbox.deliver_batch().failed, 1)
            spent = OutboxEvent.objects.get(topic=indexing.INDEX_REBUILT)
            self.assertEqual((spent.attempts, spent.published_at), (1, None))
            self.assertEqual(outbox.deliver_batch().delivered, 0, "the row is behind the cursor now")
        self.assertEqual(SearchChunk.objects.filter(embedding__isnull=True).count(), 3)

        self.assertEqual(indexing.embed_backlog(), 3)

        self.assertEqual(SearchChunk.objects.filter(embedding__isnull=True).count(), 0)

    def test_a_model_contracted_later_is_the_sweeps_work_and_needs_no_new_event(self) -> None:
        """D-09 leaves a deployment running with no embedder, and turning one on is a
        variable change with no library write behind it: there is no event for the corpus
        to ride, and the delivery it would have ridden is long published. The sweep is
        what notices, on its next tick, with nothing for anyone to remember to run."""
        with override_settings(EMBEDDER_PROVIDER="none"):
            result = outbox.deliver_batch()

        self.assertEqual((result.delivered, result.failed), (1, 0))
        self.assertEqual(SearchChunk.objects.filter(embedding__isnull=True).count(), 3)
        self.assertFalse(OutboxEvent.objects.filter(published_at__isnull=True).exists(), "nothing will ask again")

        self.assertEqual(indexing.embed_backlog(), 3)

        self.assertEqual(SearchChunk.objects.filter(embedding__isnull=True).count(), 0)
        self.assertEqual(indexing.embed_backlog(), 0, "the next tick finds nothing and asks the model nothing")

    @override_settings(EMBEDDER_PROVIDER="none")
    def test_the_sweep_asks_no_model_while_none_is_contracted(self) -> None:
        self.assertEqual(indexing.embed_backlog(), 0)
        self.assertEqual(SearchChunk.objects.filter(embedding__isnull=True).count(), 3)

    def test_embedding_twice_asks_the_model_nothing_the_second_time(self) -> None:
        with transaction.atomic():
            indexing.embed_pending()
        with mock.patch.object(embedder, "get_embedder") as adapter:
            with transaction.atomic():
                self.assertEqual(indexing.embed_pending(), 0)

        adapter.assert_not_called()

    @override_settings(EMBEDDER_PROVIDER="none")
    def test_no_contracted_model_leaves_the_keyword_leg_to_answer(self) -> None:
        """D-09: a deployed environment may run with no embedder. That is not a failure,
        and it must not spend an outbox row's attempts waiting for a key to arrive."""
        with transaction.atomic():
            self.assertEqual(indexing.embed_pending(), 0)

        result = outbox.deliver_batch()

        self.assertEqual((result.delivered, result.failed), (1, 0))
        self.assertEqual(SearchChunk.objects.filter(embedding__isnull=True).count(), 3)

    def test_a_failing_embedder_costs_its_own_row_an_attempt_and_nothing_else(self) -> None:
        other = OutboxEvent.objects.order_by("created").first()
        assert other is not None
        with mock.patch.object(indexing, "embed_pending", side_effect=RuntimeError("the model is down")):
            result = outbox.deliver_batch()

        self.assertEqual(result.failed, 1)
        failed = OutboxEvent.objects.get(topic=indexing.INDEX_REBUILT)
        self.assertEqual(failed.attempts, 1)
        self.assertIsNone(failed.published_at)
        self.assertEqual(failed.last_error, "RuntimeError")
        self.assertEqual(SearchChunk.objects.filter(embedding__isnull=True).count(), 3, "half an embedding was kept")


class TheRebuildCommand(LibraryFixtureMixin, TestCase):
    def setUp(self) -> None:
        self.build_library()

    def test_the_command_rebuilds_the_corpus_and_says_what_it_wrote(self) -> None:
        out = StringIO()

        call_command("reindex_library", stdout=out)

        self.assertEqual(SearchChunk.objects.count(), 3)
        self.assertIn("3", out.getvalue())

    def test_running_the_command_again_changes_nothing(self) -> None:
        call_command("reindex_library", stdout=StringIO())
        before = set(SearchChunk.objects.values_list("id", flat=True))

        call_command("reindex_library", stdout=StringIO())

        self.assertEqual(set(SearchChunk.objects.values_list("id", flat=True)), before)
        self.assertEqual(AuditEvent.objects.filter(action=indexing.INDEX_REBUILT).count(), 2, "each run is audited")

