"""The drafted "So what?" a run files with the change it read (WAT-05, AUD-02, D-66).

Alex decided on 2026-09-21 that the words come from the agent that read the source, filed
with the change through the door it already writes through, and that the model, the version
and the citations it reports are what the AI output log records. That moves two things
worth proving over the real routes rather than over the function:

- **A draft is never filed unattributably.** Words with no model, no model version or no
  citation are refused, because a log row AUD-02 cannot attribute is not the log AUD-02
  asks for.
- **The row says who reported the model.** `modelMetadataReportedByAgent` is true on an
  agent's filing and false on a call bleqq's own wrapper made. It is the reporting boundary
  D-66 names, and the day a bank runs its own agent it becomes a trust boundary; a reader
  who cannot see which row is which has no way to know that.

And the two that did not change: no bank's term, name or text reaches the draft, and a
change filed with no draft is registered exactly as before.

Proven to fail 2026-09-21: with the metadata check removed, a `soWhat` carrying only words
was accepted and wrote a row naming no model; with `metadata_reported_by_agent` left at its
default, the log claimed bleqq had measured what an agent reported.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction

from apps.agents import testing as agent_build
from apps.cases import creation, testing as case_build
from apps.cases.models import ChangeCase
from apps.governance.models import AiGeneration, AiPurpose, AiStatus
from apps.shared import outbox, tenancy
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase
from apps.watch import so_what_draft, testing as watch_build
from apps.watch.models import RegulatoryChange

CHANGES = "/api/v1/changes"
JSON = "application/json"
SECURITIES = "regime:securities"
AML = "regime:aml"
STABLE_KEY = "chg-fi-2026-research-payments"

DRAFT = "Teams that pay for external research should confirm that documented criteria exist."
CITATION = {
    "label": "Finansinspektionen, decision memorandum FI Dnr 25-12345",
    "url": "https://www.fi.se/en/published/news/2026/reporting/",
}
SO_WHAT = {
    "text": DRAFT,
    "model": "claude-opus-5",
    "modelVersion": "2026-05-01",
    "promptTemplate": "watch-sweeper/so-what/v1",
    "promptHash": "9f2a1c7d4b8e05f3",
    "citations": [CITATION],
}


def body(**overrides: Any) -> dict[str, Any]:  # compliance: allow-kwargs test helper forwarding request fields
    payload: dict[str, Any] = {
        "stableKey": STABLE_KEY,
        "title": "FI adopts amended rules on paying for investment research",
        "changeType": "adopted",
        "authorityLabel": "Finansinspektionen",
        "authorityCode": "fi",
        "summary": "FI's board decided to amend three regulations in the securities area.",
        "suggestedUrgency": "act_now",
        "sourceLabel": "Finansinspektionen",
        "sourceUrl": "https://www.fi.se/",
        "documents": [{"url": "https://www.fi.se/en/published/news/2026/research-payments/", "isPrimary": True}],
        "model": "agent pipeline 0.4",
        # Every change carries a regime (D-39, AC-AGT1).
        "termIds": [str(watch_build.term(SECURITIES).id)],
    }
    payload.update(overrides)
    return payload


def drain() -> None:
    with transaction.atomic():
        tenancy.clear_tenant()
    while outbox.deliver_batch().delivered:
        pass


class SoWhatFilingCase(ScenarioTestCase):
    """A platform key with a run open, and two banks whose footprints do not overlap."""

    def setUp(self) -> None:
        watch_build.seed_watch_reference()
        tenancy.clear_tenant()
        self.key = agent_build.agent_key()
        self.platform_run = agent_build.platform_run(key=self.key)
        creation.register()
        self.banks = case_build.two_tenants_with_different_footprints(inside=SECURITIES, outside=AML)
        drain()
        tenancy.clear_tenant()

    def register(self, payload: dict[str, Any] | None = None) -> Any:
        return self.client.post(
            CHANGES,
            data=payload if payload is not None else body(agentRunId=str(self.platform_run.id), soWhat=SO_WHAT),
            content_type=JSON,
            HTTP_X_API_KEY=self.key.plain_key,
        )

    def patch(self, change_id: uuid.UUID, payload: dict[str, Any]) -> Any:
        return self.client.patch(
            f"{CHANGES}/{change_id}", data=payload, content_type=JSON, HTTP_X_API_KEY=self.key.plain_key
        )

    def stored(self) -> RegulatoryChange:
        with transaction.atomic():
            tenancy.clear_tenant()
            return RegulatoryChange.objects.get(stable_key=STABLE_KEY)

    def generations(self) -> list[AiGeneration]:
        """The So what rows only: the same filing also logs its suggested classification
        as a `scope_suggestion` row, which `tests_registration.py` proves."""
        with transaction.atomic():
            tenancy.clear_tenant()
            return list(AiGeneration.objects.filter(purpose=AiPurpose.SO_WHAT.value).order_by("created_at", "id"))


class ARunFilesWhatAChangeMeans(SoWhatFilingCase):
    def test_the_words_land_on_the_change_and_one_row_lands_in_the_log(self) -> None:
        response = self.register()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["soWhatDraft"], DRAFT)
        self.assertEqual(self.stored().so_what_draft, DRAFT)

        rows = self.generations()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.purpose, AiPurpose.SO_WHAT.value)
        self.assertEqual((row.model, row.model_version), ("claude-opus-5", "2026-05-01"))
        self.assertEqual(row.status, AiStatus.DRAFT.value, "AI output stays labelled until a person confirms it")
        self.assertEqual(row.output, DRAFT)
        self.assertEqual(row.citations, [CITATION])
        self.assertEqual((row.subject_type, row.subject_id), ("regulatory_change", self.stored().id))
        self.assertEqual(row.agent_run_id, self.platform_run.id)
        self.assertIsNone(row.tenant_id, "one draft per change, shared by every bank")

    def test_the_row_says_the_agent_reported_the_model(self) -> None:
        """D-66's reporting boundary, on the row itself."""
        self.register()
        self.assertTrue(self.generations()[0].model_metadata_reported_by_agent)

    def test_the_prompt_is_not_stored_only_its_name_and_its_hash(self) -> None:
        self.register()
        row = self.generations()[0]
        self.assertEqual((row.prompt_template, row.prompt_hash), ("watch-sweeper/so-what/v1", "9f2a1c7d4b8e05f3"))

    def test_the_filing_is_audited_with_the_model_named_and_the_words_left_out(self) -> None:
        self.register()
        with transaction.atomic():
            tenancy.clear_tenant()
            event = AuditEvent.objects.get(action=so_what_draft.SO_WHAT_DRAFTED)
        self.assertEqual(event.after["model"], "claude-opus-5")
        self.assertEqual(event.after["citations"], [CITATION["url"]])
        self.assertTrue(event.after["modelMetadataReportedByAgent"])
        self.assertNotIn(DRAFT, str(event.after), "the words are on the log row, not in the audit trail")

    def test_the_draft_reaches_every_banks_case_unconfirmed(self) -> None:
        self.register()
        drain()
        change = self.stored()
        for bank in (self.banks.inside, self.banks.outside):
            with self.subTest(bank=bank.slug):
                with transaction.atomic():
                    tenancy.activate(bank.id)
                    case = ChangeCase.objects.get(change=change)
                self.assertEqual(case.so_what_text, DRAFT)
                self.assertFalse(case.so_what_confirmed)

    def test_no_banks_words_reach_the_draft_or_its_log_row(self) -> None:
        """D-07, D-32: the draft is written from library facts, with two banks present."""
        self.register()
        drain()
        row = self.generations()[0]
        haystack = " ".join([row.output, row.prompt_template, row.prompt_hash, str(row.citations)])
        for bank in (self.banks.inside, self.banks.outside):
            with self.subTest(bank=bank.slug):
                self.assertNotIn(bank.name, haystack)
                self.assertNotIn(bank.slug, haystack)


class ADraftIsNeverFiledUnattributably(SoWhatFilingCase):
    def test_words_with_no_model_no_version_or_no_citation_are_refused(self) -> None:
        for missing in ("model", "modelVersion", "citations"):
            with self.subTest(missing=missing):
                report = {key: value for key, value in SO_WHAT.items() if key != missing}
                response = self.register(body(agentRunId=str(self.platform_run.id), soWhat=report))
                self.assertEqual(response.status_code, 422, response.content)
                self.assertEqual(response.json()["code"], "validation_error")
                self.assertEqual(self.generations(), [], "a refusal stores nothing at all")

    def test_an_empty_citation_list_is_refused(self) -> None:
        response = self.register(body(agentRunId=str(self.platform_run.id), soWhat={**SO_WHAT, "citations": []}))
        self.assertEqual((response.status_code, response.json()["code"]), (422, "validation_error"))

    def test_a_change_filed_with_no_draft_is_registered_and_logs_no_so_what(self) -> None:
        response = self.register(body(agentRunId=str(self.platform_run.id)))
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.stored().so_what_draft, "")
        self.assertEqual(self.generations(), [])


class ALaterRunImprovesTheDraft(SoWhatFilingCase):
    def test_a_patch_replaces_the_draft_and_writes_a_second_log_row(self) -> None:
        self.register()
        change = self.stored()
        better = {**SO_WHAT, "text": "Desks paying for research need documented annual criteria by 1 October."}
        response = self.patch(change.id, {"soWhat": better})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.stored().so_what_draft, better["text"])
        rows = self.generations()
        self.assertEqual([row.output for row in rows], [DRAFT, better["text"]])
        self.assertTrue(all(row.model_metadata_reported_by_agent for row in rows))

    def test_a_patch_with_words_and_no_model_is_refused_and_changes_nothing(self) -> None:
        self.register()
        change = self.stored()
        response = self.patch(change.id, {"soWhat": {"text": "Something better.", "citations": [CITATION]}})
        self.assertEqual((response.status_code, response.json()["code"]), (422, "validation_error"))
        self.assertEqual(self.stored().so_what_draft, DRAFT)
        self.assertEqual(len(self.generations()), 1)
