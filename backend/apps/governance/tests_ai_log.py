"""The AI output log (AUD-02, ruling 1): the one writer, the wrapper that uses it, the
read, and what never reaches a log line.

The zone rules are `apps/shared/tests_rls.py`'s — `ai_generation` is a mixed table under
the split policy — and the fence over who may call the model adapter is
`apps/shared/tests_ai_wrapper.py`'s. Here: the row a call leaves, the refusals, the read
and the three facts a reader must be able to trust about the row.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DEFAULT_DB_ALIAS, connections, transaction

from apps.governance import ai_log
from apps.governance.models import AiGeneration, AiPurpose, AiStatus
from apps.governance.schemas import AiCitation
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import ai, factories, tenancy
from apps.shared.adapters.llm import Completion, LlmAdapter, LlmError
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.seeds import seed_library_vocabularies

V1 = "/api/v1"

CITATION = AiCitation(
    label="Finansinspektionen, decision memorandum FI Dnr 25-12345",
    url="https://www.fi.se/en/published/news/2026/reporting/",
)


class _RecordingLlm(LlmAdapter):
    """A model that answers a fixed sentence and remembers what it was asked, so a test can
    assert over the prompt without any prompt reaching the log."""

    name = "recording"

    def __init__(self, text: str = "Confirm the documented criteria before 1 October.") -> None:
        self.text = text
        self.prompts: list[tuple[str, str]] = []

    def stream(self, *, system: str, prompt: str, max_tokens: int) -> Iterator[str | Completion]:
        self.prompts.append((system, prompt))
        yield self.text
        yield Completion(
            text=self.text,
            model="claude-opus-5",
            model_version="2026-05-01",
            input_tokens=12,
            output_tokens=7,
            stop_reason="end_turn",
        )


class _FailingLlm(LlmAdapter):
    name = "failing"

    def stream(self, *, system: str, prompt: str, max_tokens: int) -> Iterator[str | Completion]:
        raise LlmError("the model API could not be reached")
        yield  # pragma: no cover - unreachable, present so the signature stays a generator


class AiLogWriterTests(ScenarioTestCase):
    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        self.tenant = factories.tenant(slug="ai-log-writer")
        # The factory leaves its tenant activated; a library row is written with none.
        tenancy.clear_tenant()

    def test_a_row_carries_everything_aud_02_asks_for(self) -> None:
        with transaction.atomic():
            row = ai_log.log_generation(
                purpose=AiPurpose.SO_WHAT,
                model="claude-opus-5",
                model_version="2026-05-01",
                output="Confirm the documented criteria before 1 October.",
                citations=[CITATION],
                subject_type="regulatory_change",
                subject_id=uuid.UUID("c3a6e1f0-7b42-4d8e-95a1-2f0b6c8d4e19"),
                prompt_template="watch-sweeper/so-what/v1",
                prompt_hash="9f2a1c7d4b8e05f3",
                metadata_reported_by_agent=True,
            )
        self.assertEqual(
            (row.purpose, row.model, row.model_version, row.status),
            (AiPurpose.SO_WHAT.value, "claude-opus-5", "2026-05-01", AiStatus.DRAFT.value),
        )
        self.assertEqual(row.citations, [CITATION.model_dump(by_alias=True)])
        self.assertTrue(row.model_metadata_reported_by_agent)
        self.assertIsNone(row.tenant_id)
        self.assertIsNone(row.reviewed_by_id)
        self.assertIsNone(row.reviewed_at)

    def test_a_row_without_a_model_or_a_version_is_refused(self) -> None:
        """A log that cannot say which machine wrote something is not the log AUD-02 asks
        for, so the refusal is here and not left to the caller to remember."""
        for model, version in (("", "2026-05-01"), ("claude-opus-5", ""), ("  ", "  ")):
            with self.subTest(model=model, version=version):
                with self.assertRaises(ValidationError), transaction.atomic():
                    ai_log.log_generation(
                        purpose=AiPurpose.ANSWER,
                        model=model,
                        model_version=version,
                        output="x",
                        citations=[],
                    )

    def test_a_row_outside_a_transaction_is_refused(self) -> None:
        """A row that could commit while the write it records rolled back would claim a
        model was asked something that never happened.

        TestCase wraps each test in a transaction, so the guard's own condition is flipped
        for the length of the call, as `tests_audit_on_write.py` does for `record()`.
        """
        connection = connections[DEFAULT_DB_ALIAS]
        original = connection.in_atomic_block
        connection.in_atomic_block = False
        try:
            with self.assertRaises(ai_log.NotInTransaction):
                ai_log.log_generation(
                    purpose=AiPurpose.ANSWER, model="m", model_version="1", output="x", citations=[]
                )
        finally:
            connection.in_atomic_block = original

    def test_a_rollback_leaves_no_row(self) -> None:
        before = AiGeneration.objects.count()
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                ai_log.log_generation(
                    purpose=AiPurpose.ANSWER, model="m", model_version="1", output="x", citations=[]
                )
                raise RuntimeError("the write that caused the call failed")
        self.assertEqual(AiGeneration.objects.count(), before)

    def test_an_over_long_output_is_stored_up_to_the_cap(self) -> None:
        """Model output is text off a network, so the cap is at the boundary rather than
        left to the provider's token limit."""
        with transaction.atomic():
            row = ai_log.log_generation(
                purpose=AiPurpose.ANSWER,
                model="m",
                model_version="1",
                output="x" * (settings.AI_GENERATION_OUTPUT_MAX_CHARS + 500),
                citations=[],
            )
        self.assertEqual(len(row.output), settings.AI_GENERATION_OUTPUT_MAX_CHARS)


class AiWrapperTests(ScenarioTestCase):
    """`apps/shared/ai.py`: the one door to a model, and what it leaves behind."""

    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        self.tenant = factories.tenant(slug="ai-wrapper")
        tenancy.clear_tenant()

    def test_a_call_through_the_wrapper_writes_exactly_one_row(self) -> None:
        llm = _RecordingLlm()
        with transaction.atomic():
            result = ai.generate(
                purpose=AiPurpose.ANSWER,
                system="You answer from the context only.",
                prompt="[1] FI decided on 15 September 2026.",
                prompt_template="ask/answer/v1",
                citations=[CITATION],
                subject_type="regulatory_change",
                subject_id=uuid.uuid4(),
                llm=llm,
            )
        rows = list(AiGeneration.objects.all())
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(result.text, row.output)
        self.assertEqual((row.model, row.model_version), ("claude-opus-5", "2026-05-01"))
        self.assertEqual((row.input_tokens, row.output_tokens), (12, 7))
        self.assertEqual(row.status, AiStatus.DRAFT.value)

    def test_the_wrapper_never_stores_the_prompt(self) -> None:
        """The prompt is a hash and a template name. Nothing else of it survives the call,
        which is what keeps a bank's own words out of a shared log (NFR-04, D-07)."""
        llm = _RecordingLlm()
        system, prompt = "You answer from the context only.", "Secret Bank AB asked about custody."
        with transaction.atomic():
            tenancy.activate(self.tenant.id)  # a bank's own row is written in the bank's zone
            ai.generate(
                purpose=AiPurpose.ANSWER,
                system=system,
                prompt=prompt,
                prompt_template="ask/answer/v1",
                citations=[],
                tenant_id=self.tenant.id,
                llm=llm,
            )
        row = AiGeneration.objects.get()
        self.assertEqual(row.prompt_hash, ai.prompt_hash(system, prompt))
        self.assertNotIn("Secret Bank", row.prompt_hash)
        for value in (row.prompt_hash, row.prompt_template, row.subject_type):
            self.assertNotIn("custody", value)

    def test_the_wrapper_marks_its_rows_as_observed_not_reported(self) -> None:
        """D-66: the wrapper made the call itself, so the model and version on its row are
        bleqq's own measurement. An agent's filing says the opposite, and a reader has to
        be able to tell them apart."""
        with transaction.atomic():
            ai.generate(
                purpose=AiPurpose.ANSWER,
                system="s",
                prompt="p",
                prompt_template="ask/answer/v1",
                citations=[],
                llm=_RecordingLlm(),
            )
        self.assertFalse(AiGeneration.objects.get().model_metadata_reported_by_agent)

    def test_a_model_failure_writes_no_row(self) -> None:
        with self.assertRaises(LlmError), transaction.atomic():
            ai.generate(
                purpose=AiPurpose.ANSWER,
                system="s",
                prompt="p",
                prompt_template="ask/answer/v1",
                citations=[],
                llm=_FailingLlm(),
            )
        self.assertEqual(AiGeneration.objects.count(), 0)


class AiGenerationsReadTests(ScenarioTestCase):
    """`GET /ai-generations` (AUD-02): the reader's own rows plus the library's."""

    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        self.tenant_a = factories.tenant(slug="ai-read-a")
        self.tenant_b = factories.tenant(slug="ai-read-b")
        self.officer_a = factories.member(self.tenant_a, roles=("compliance_officer",)).user
        self.reader_a = factories.member(self.tenant_a, roles=("reader",)).user
        self.reader_b = factories.member(self.tenant_b, roles=("compliance_officer",)).user

    def _row(self, tenant: Any, purpose: AiPurpose = AiPurpose.ANSWER) -> AiGeneration:
        with transaction.atomic():
            if tenant is not None:
                tenancy.activate(tenant.id)
            else:
                tenancy.clear_tenant()
            return ai_log.log_generation(
                purpose=purpose,
                model="claude-opus-5",
                model_version="2026-05-01",
                output="Confirm the documented criteria before 1 October.",
                citations=[CITATION],
                tenant_id=None if tenant is None else tenant.id,
                metadata_reported_by_agent=purpose is AiPurpose.SO_WHAT,
            )

    def test_a_bank_reads_its_own_rows_and_the_librarys(self) -> None:
        library = self._row(None, AiPurpose.SO_WHAT)
        mine = self._row(self.tenant_a)
        theirs = self._row(self.tenant_b)
        response = self.client.get(f"{V1}/ai-generations", **sign_in(self.officer_a, tenant=self.tenant_a))
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        ids = {row["id"] for row in body["items"]}
        self.assertEqual(ids, {str(library.id), str(mine.id)})
        self.assertNotIn(str(theirs.id), ids)
        self.assertEqual(body["total"], 2)
        by_id = {row["id"]: row for row in body["items"]}
        self.assertFalse(by_id[str(library.id)]["tenantScoped"])
        self.assertTrue(by_id[str(mine.id)]["tenantScoped"])

    def test_the_library_row_says_who_reported_the_model(self) -> None:
        """The reporting boundary D-66 names, on the row a reader sees."""
        self._row(None, AiPurpose.SO_WHAT)
        self._row(self.tenant_a, AiPurpose.ANSWER)
        response = self.client.get(f"{V1}/ai-generations", **sign_in(self.officer_a, tenant=self.tenant_a))
        by_purpose = {row["purpose"]: row for row in response.json()["items"]}
        self.assertTrue(by_purpose["so_what"]["modelMetadataReportedByAgent"])
        self.assertFalse(by_purpose["answer"]["modelMetadataReportedByAgent"])

    def test_the_filters_narrow_and_an_unknown_value_is_an_empty_page(self) -> None:
        self._row(None, AiPurpose.SO_WHAT)
        self._row(self.tenant_a, AiPurpose.ANSWER)
        headers = sign_in(self.officer_a, tenant=self.tenant_a)
        narrowed = self.client.get(f"{V1}/ai-generations?purpose=so_what", **headers)
        self.assertEqual([row["purpose"] for row in narrowed.json()["items"]], ["so_what"])
        by_state = self.client.get(f"{V1}/ai-generations?status=draft", **headers)
        self.assertEqual(by_state.json()["total"], 2)
        unknown = self.client.get(f"{V1}/ai-generations?purpose=not_a_purpose", **headers)
        self.assertEqual((unknown.status_code, unknown.json()), (200, {"items": [], "total": 0}))

    def test_a_bank_with_no_rows_reads_an_empty_page(self) -> None:
        response = self.client.get(f"{V1}/ai-generations", **sign_in(self.reader_b, tenant=self.tenant_b))
        self.assertEqual((response.status_code, response.json()), (200, {"items": [], "total": 0}))

    def test_a_reader_without_the_permission_is_refused(self) -> None:
        response = self.client.get(f"{V1}/ai-generations", **sign_in(self.reader_a, tenant=self.tenant_a))
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.json()["requiredPermission"], "ai_log.read")

    def test_a_bank_cannot_write_move_or_delete_the_librarys_row(self) -> None:
        """Ruling I, through the ORM as well as in the policy: the library draft's review
        state is a platform fact, and a bank's own confirmation lives on its case."""
        library = self._row(None, AiPurpose.SO_WHAT)
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            self.assertEqual(
                AiGeneration.objects.filter(pk=library.pk).update(status=AiStatus.CONFIRMED.value), 0
            )
            self.assertEqual(AiGeneration.objects.filter(pk=library.pk).delete()[0], 0)
        with transaction.atomic():
            tenancy.clear_tenant()
            self.assertEqual(AiGeneration.objects.get(pk=library.pk).status, AiStatus.DRAFT.value)
