"""A confirming agent's decision in the AI output log (AUD-02, PRO-02, D-80, governance 0002).

The row is the agent's own report, names the run it was made in and the record it decided,
and the database refuses it otherwise, so a later consumer cannot log a decision nobody
can trace. No bank reads it: the decision is about the proposal queue, where a bank sees
only what it filed itself, so the library read policy leaves it out while every bank still
reads the library's drafted "So what?". The platform reads it in its own zone.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import IntegrityError, transaction

from apps.agents import testing as agent_build
from apps.governance import ai_log
from apps.governance.models import AiGeneration, AiPurpose
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, tenancy
from apps.shared.schemas import AiCitation
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.seeds import seed_library_vocabularies

V1 = "/api/v1"
CITATION = AiCitation(
    label="Finansinspektionen, decision memorandum FI Dnr 25-12345",
    url="https://www.fi.se/en/published/news/2026/reporting/",
)


class AgentReviewRowTests(ScenarioTestCase):
    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        self.tenant = factories.tenant(slug="agent-review-a")
        self.officer = factories.member(self.tenant, roles=("compliance_officer",)).user
        # The confirming agent's key and run are the platform's (H15, AGT-01).
        tenancy.clear_tenant()
        self.agent_run = agent_build.platform_run(key=agent_build.reviewer_api_key())
        self.decision: dict[str, Any] = {
            "purpose": AiPurpose.AGENT_REVIEW,
            "model": "claude-opus-5",
            "model_version": "2026-05-01",
            "output": "Approve. The proposed wording matches the amended regulation as published.",
            "citations": [CITATION],
            "agent_run_id": self.agent_run.id,
            "subject_type": "proposal",
            "subject_id": uuid.uuid4(),
            "metadata_reported_by_agent": True,
        }

    def _log(self, fields: dict[str, Any]) -> AiGeneration:
        with transaction.atomic():
            tenancy.clear_tenant()
            return ai_log.log_generation(**fields)

    def test_a_decision_that_names_its_run_and_record_is_logged(self) -> None:
        row = self._log(self.decision)
        self.assertEqual((row.purpose, row.agent_run_id, row.tenant_id), ("agent_review", self.agent_run.id, None))
        self.assertTrue(row.model_metadata_reported_by_agent)

    def test_the_database_refuses_a_decision_nobody_can_trace(self) -> None:
        for change, why in (
            ({"agent_run_id": None}, "no run"),
            ({"subject_id": None}, "no record decided"),
            ({"subject_type": ""}, "a record of no kind"),
            ({"metadata_reported_by_agent": False}, "read as bleqq's own measurement"),
        ):
            with self.assertRaises(IntegrityError, msg=why):
                self._log({**self.decision, **change})
        self.assertFalse(AiGeneration.objects.filter(purpose=AiPurpose.AGENT_REVIEW.value).exists())
        drafted = self._log({**self.decision, "purpose": AiPurpose.SO_WHAT, "agent_run_id": None})
        self.assertEqual(drafted.purpose, "so_what", "the rule is the decision's alone")

    def test_a_bank_reads_the_librarys_draft_and_never_a_decision(self) -> None:
        decision = self._log(self.decision)
        drafted = self._log({**self.decision, "purpose": AiPurpose.SO_WHAT, "subject_type": "regulatory_change"})
        headers = sign_in(self.officer, tenant=self.tenant)
        listed = self.client.get(f"{V1}/ai-generations", **headers)
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual([row["id"] for row in listed.json()["items"]], [str(drafted.id)])
        self.assertEqual(listed.json()["total"], 1)
        filtered = self.client.get(f"{V1}/ai-generations?purpose=agent_review", **headers)
        self.assertEqual(filtered.json(), {"items": [], "total": 0})
        # The database's answer, not the route's: under the bank's tenant the row is not
        # there at all, and in the platform's own zone it is.
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            self.assertFalse(AiGeneration.objects.filter(pk=decision.pk).exists())
            self.assertTrue(AiGeneration.objects.filter(pk=drafted.pk).exists())
        with transaction.atomic():
            tenancy.clear_tenant()
            self.assertTrue(AiGeneration.objects.filter(pk=decision.pk).exists())
