"""A confirming agent's decision in the AI output log (AUD-02, PRO-02, AGT-01, D-80, governance 0002).

The row is the agent's own report, names the run it was made in and the record it decided,
and the database refuses it otherwise, so a later consumer cannot log a decision nobody
can trace. No bank reads it: the decision is about the proposal queue, where a bank sees
only what it filed itself, so the library read policy leaves it out while every bank still
reads the library's drafted "So what?". The platform reads it in its own zone.

The consumer is the queue: an agent's approval or rejection carries the model call behind
it (`decision`) and the open run of its own key it was made in (`agentRunId`), and the
decision writes exactly one `agent_review` row in its own transaction, beside the audit row
that names the same run. A person's decision carries neither, and logs no model call.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.agents import testing as agent_build
from apps.agents.models import AgentRun, RunStatus
from apps.governance import ai_log
from apps.governance.models import AiGeneration, AiPurpose
from apps.library import testing as library_build
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.proposals.models import Proposal, ProposalStatus
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.models import AuditEvent
from apps.shared.schemas import AiCitation
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions

V1 = "/api/v1"
CITATION = AiCitation(
    label="Finansinspektionen, decision memorandum FI Dnr 25-12345",
    url="https://www.fi.se/en/published/news/2026/reporting/",
)
DECISIONS = ("proposal.approved", "proposal.rejected")
REJECTION = {"rejectionCode": "duplicate", "note": "Version 2 already says this."}


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


class AgentDecisionsThroughTheQueue(ScenarioTestCase):
    """The approve and reject routes as a confirming agent calls them (PRO-02, AUD-02,
    AGT-01, D-80): the decision comes with the model call behind it and the run it was made
    in, or it is refused and nothing is written."""

    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        tenancy.clear_tenant()  # library records and platform keys belong to no tenant (H15)
        self.obligation = library_build.obligation(
            library_build.instrument(key="decision-log-instrument", regime="regime:securities"), key="obl-decision-log"
        )
        self.filer = agent_build.agent_key(scopes=(perms.SCOPE_PROPOSALS_WRITE,))
        self.confirmer = agent_build.reviewer_api_key()
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")

    # --- helpers --------------------------------------------------------------------------
    def _proposed(self) -> str:
        """An obligation version the filing agent proposes under an open run of its own."""
        tenancy.clear_tenant()
        created = self._post(
            "/proposals",
            {
                "kind": "new_obligation_version",
                "title": "Refresh the wording against the source",
                "targetType": "obligation",
                "targetId": str(self.obligation.id),
                "payload": {"summaries": {"en": "The duty as the source now reads it."}, "originalLanguage": "en", "isMachine": True},
                "fieldSources": {"summaries.en": "https://www.fi.se/"},
                "agentRunId": str(agent_build.platform_run(key=self.filer).id),
            },
            {"HTTP_X_API_KEY": self.filer.plain_key},
        )
        self.assertEqual(created.status_code, 201, created.content)
        proposal_id: str = created.json()["id"]
        return proposal_id

    def _post(self, path: str, body: dict[str, Any], headers: dict[str, Any]) -> Any:
        answer = self.client.post(f"{V1}{path}", data=body, content_type="application/json", **headers)
        tenancy.clear_tenant()  # the decision log and the queue are the platform's to read
        return answer

    def _as_confirmer(self, path: str, body: dict[str, Any]) -> Any:
        return self._post(path, body, {"HTTP_X_API_KEY": self.confirmer.plain_key})

    def _logged(self, proposal_id: str) -> list[AiGeneration]:
        return list(AiGeneration.objects.filter(purpose=AiPurpose.AGENT_REVIEW.value, subject_id=proposal_id))

    def _assert_logged_in(self, proposal_id: str, run_id: str, action: str) -> None:
        """One `agent_review` row, the agent's own report of the call behind the decision,
        in the run it named; and the decision's audit row names the same run."""
        rows = self._logged(proposal_id)
        self.assertEqual(len(rows), 1, "one decision is one model call")
        row = rows[0]
        self.assertEqual((row.subject_type, str(row.subject_id), str(row.agent_run_id)), ("proposal", proposal_id, run_id))
        self.assertTrue(row.model_metadata_reported_by_agent, "the agent's own account of itself, never bleqq's measurement")
        self.assertIsNone(row.tenant_id, "the queue is the platform's, so no bank reads it")
        decision = agent_build.DECISION
        self.assertEqual(
            (row.model, row.model_version, row.prompt_template, row.prompt_hash, row.output),
            (decision["model"], decision["modelVersion"], decision["promptTemplate"], decision["promptHash"], decision["output"]),
        )
        self.assertEqual(row.citations, decision["citations"])
        self.assertEqual(row.status, "draft", "AI output stays labelled: no person confirmed it")
        event = AuditEvent.objects.get(action=action, subject_id=proposal_id)
        self.assertEqual(event.after["agentRunId"], run_id)
        # Counted in its run, as a sweep's registrations are (D-80).
        self.assertEqual([generation.subject_id for generation in AgentRun.objects.get(pk=run_id).generations.all()], [row.subject_id])

    def _assert_untouched(self, proposal_id: str) -> None:
        self.assertEqual(Proposal.objects.get(pk=proposal_id).status, ProposalStatus.OPEN.value)
        self.assertEqual(sorted(self.obligation.versions.values_list("version_number", flat=True)), [1])
        self.assertFalse(AuditEvent.objects.filter(subject_id=proposal_id, action__in=DECISIONS).exists())
        self.assertEqual(self._logged(proposal_id), [], "a refused decision logs no model call")

    # --- an agent ---------------------------------------------------------------------------
    def test_an_agents_approval_logs_the_model_call_behind_it_in_its_run(self) -> None:
        proposal_id = self._proposed()
        sent = agent_build.decision(self.confirmer)
        approved = self._as_confirmer(f"/proposals/{proposal_id}/approve", {"note": "Confirmed against the source.", **sent})
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(sorted(self.obligation.versions.values_list("version_number", flat=True)), [1, 2])
        self._assert_logged_in(proposal_id, sent["agentRunId"], "proposal.approved")

    def test_an_agents_rejection_logs_the_model_call_behind_it_in_its_run(self) -> None:
        proposal_id = self._proposed()
        sent = agent_build.decision(self.confirmer)
        rejected = self._as_confirmer(f"/proposals/{proposal_id}/reject", {**REJECTION, **sent})
        self.assertEqual(rejected.status_code, 200, rejected.content)
        self.assertEqual(rejected.json()["status"], "rejected")
        self._assert_logged_in(proposal_id, sent["agentRunId"], "proposal.rejected")

    def test_an_agent_decides_only_with_its_decision_inside_an_open_run_of_its_own(self) -> None:
        proposal_id = self._proposed()
        own_run = str(agent_build.platform_run(key=self.confirmer).id)
        closed = agent_build.platform_run(key=self.confirmer)
        closed.status, closed.finished_at = RunStatus.SUCCEEDED.value, timezone.now()
        closed.save(update_fields=["status", "finished_at"])
        # A run of a different confirming agent's key: not this key's to count a decision in.
        another_agents_run = str(agent_build.platform_run(key=agent_build.reviewer_api_key()).id)
        decision = agent_build.DECISION
        for sent, status, code, why in (
            ({"agentRunId": own_run}, 422, "validation_error", "no decision: a model call nobody reported"),
            ({"decision": decision}, 422, "run_not_open", "no run to count it in"),
            ({"decision": decision, "agentRunId": str(closed.id)}, 422, "run_not_open", "a closed run takes nothing more"),
            ({"decision": decision, "agentRunId": another_agents_run}, 404, "not_found", "another agent's run, as one that never existed"),
            ({"decision": {**decision, "citations": []}, "agentRunId": own_run}, 422, "validation_error", "a decision nobody can check"),
        ):
            for verb, body in (("approve", {"note": "Confirmed."}), ("reject", REJECTION)):
                with self.subTest(verb=verb, why=why):
                    refused = self._as_confirmer(f"/proposals/{proposal_id}/{verb}", {**body, **sent})
                    self.assertEqual(refused.status_code, status, refused.content)
                    self.assertEqual(refused.json()["code"], code)
        self._assert_untouched(proposal_id)
        # The same key, with its decision in its own open run, then decides.
        approved = self._as_confirmer(f"/proposals/{proposal_id}/approve", {"decision": decision, "agentRunId": own_run})
        self.assertEqual(approved.status_code, 200, approved.content)

    # --- a person ---------------------------------------------------------------------------
    def test_a_person_sends_no_decision_and_logs_no_model_call(self) -> None:
        """A person's decision is not a model call: a body that says it was one, or names a
        run, is refused rather than logged as a machine's, and the person's own decision
        leaves the AI output log alone."""
        proposal_id = self._proposed()
        editor = sign_in(self.editor, step_up=True)
        run = str(agent_build.platform_run(key=self.confirmer).id)
        for sent in ({"decision": agent_build.DECISION}, {"agentRunId": run}):
            for verb, body in (("approve", {"note": "Confirmed."}), ("reject", REJECTION)):
                with self.subTest(verb=verb, sent=sorted(sent)):
                    refused = self._post(f"/proposals/{proposal_id}/{verb}", {**body, **sent}, editor)
                    self.assertEqual(refused.status_code, 422, refused.content)
                    self.assertEqual(refused.json()["code"], "validation_error")
        self._assert_untouched(proposal_id)
        approved = self._post(f"/proposals/{proposal_id}/approve", {"note": "Confirmed."}, editor)
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(self._logged(proposal_id), [])
        self.assertNotIn("agentRunId", AuditEvent.objects.get(action="proposal.approved", subject_id=proposal_id).after)
