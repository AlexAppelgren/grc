"""Filing and reading a batch proposal (PRO-04, AGT-05; c11-proposal-batches-create).

A batch is one proposal of kind `obligation_scope`, a re-tag, with one row per obligation
carrying its preview: the scope the live `obligation_term` rows hold (`before`) and the
scope approving the row would leave (`after`). Filing it writes proposal rows only, never a
library row, and is refused unless every rule a proposal's scope answers to passes: live
shared obligations, live terms, no mirrored jurisdiction term and the standards rule. The
queue lists a batch once. It is the platform's: a library editor files one, and so does a
platform agent's key naming its own open run, while no bank's session or key reaches it.
Deciding it is apps/proposals/tests_batch_decide.py's.
"""

from __future__ import annotations

import sys
import time
import uuid
from typing import Any

from django.conf import settings
from django.test import TestCase, override_settings

from apps.agents import testing as agents_testing
from apps.library import testing as library_build
from apps.library.models import Obligation, ObligationTerm
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import seed_authorities
from apps.proposals import batch
from apps.proposals.logic import Proposer
from apps.proposals.models import OriginType, Proposal, ProposalBatchRow, ProposalKind
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.proposals.schemas import ObligationScopePayload
from apps.shared.errors import ProblemError
from apps.shared.models import AuditEvent
from apps.shared.tenancy import library_write
from apps.shared.testing import sign_in
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions

V1 = "/api/v1"
SOURCE = "https://www.fi.se/en/published/news/2026/client-money/"
CUSTODY = "service_type:custody"
RETAIL = "client_category:retail"


def change(obligation: Obligation, *, add: tuple[str, ...] = (CUSTODY,), remove: tuple[str, ...] = (), source: str = SOURCE) -> dict[str, Any]:
    return {"obligationId": str(obligation.id), "add": list(add), "remove": list(remove), "source": source}


def body(*changes: dict[str, Any], title: str = "Re-tag the client asset duties with custody") -> dict[str, Any]:
    return {"kind": "obligation_scope", "title": title, "payload": {"changes": list(changes)}, "sourceUrl": SOURCE}


class BatchTestCase(TestCase):
    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        seed_authorities()
        tenancy.clear_tenant()
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        self.law = library_build.instrument(key="fffs-2017-2", short_name="FFFS 2017:2", regime="regime:securities")
        self.obligations = [
            library_build.obligation(self.law, key=f"obl-client-assets-{n:02d}", terms=(RETAIL,)) for n in range(12)
        ]

    def _post(self, path: str, data: dict[str, Any], headers: dict[str, Any]) -> Any:
        response = self.client.post(f"{V1}{path}", data=data, content_type="application/json", **headers)
        tenancy.clear_tenant()
        return response

    def _file(self, data: dict[str, Any], headers: dict[str, Any] | None = None) -> Any:
        return self._post("/proposal-batches", data, headers if headers is not None else sign_in(self.editor))

    def _refused(self, response: Any, status: int, code: str) -> None:
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response.json()["code"], code)


class FilingABatch(BatchTestCase):
    def test_a_re_tag_over_twelve_obligations_is_one_proposal_with_twelve_rows(self) -> None:
        response = self._file(body(*(change(obligation) for obligation in self.obligations)))
        self.assertEqual(response.status_code, 201, response.content)
        answer = response.json()
        self.assertEqual((answer["kind"], answer["status"], answer["isBatch"], answer["rowCount"]), ("obligation_scope", "open", True, 12))
        self.assertEqual({row["subjectId"] for row in answer["rows"]}, {str(obligation.id) for obligation in self.obligations})
        for row in answer["rows"]:
            self.assertEqual((row["before"], row["after"]), ({"terms": [RETAIL]}, {"terms": sorted([RETAIL, CUSTODY])}))
            self.assertEqual((row["decision"], row["stale"], row["source"], row["subjectType"]), ("pending", False, SOURCE, "obligation"))
            self.assertEqual(row["target"]["instrumentShortName"], "FFFS 2017:2")
        proposal = Proposal.objects.get(pk=answer["id"])
        self.assertEqual((proposal.proposed_by_user_id, proposal.origin, proposal.target_id), (self.editor.id, OriginType.USER.value, None))
        self.assertEqual(ProposalBatchRow.objects.filter(proposal=proposal).count(), 12)
        # A preview writes nothing into the library.
        custody = library_build.term(CUSTODY)
        self.assertFalse(ObligationTerm.objects.filter(term=custody).exists())
        created = AuditEvent.objects.get(action="proposal.created", subject_id=proposal.id)
        self.assertEqual((created.after["isBatch"], created.after["rowCount"]), (True, 12))

    def test_the_queue_lists_a_batch_as_one_entry(self) -> None:
        filed = self._file(body(*(change(obligation) for obligation in self.obligations))).json()
        queue = self.client.get(f"{V1}/proposals?kind=obligation_scope", **sign_in(self.editor)).json()
        self.assertEqual([(item["id"], item["isBatch"], item["rowCount"]) for item in queue["items"]], [(filed["id"], True, 12)])
        detail = self.client.get(f"{V1}/proposals/{filed['id']}", **sign_in(self.editor))
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertTrue(detail.json()["isBatch"])

    def test_removing_and_adding_terms_previews_exactly_the_scope_left(self) -> None:
        answer = self._file(body(change(self.obligations[0], add=(CUSTODY,), remove=(RETAIL,)))).json()
        self.assertEqual((answer["rows"][0]["before"], answer["rows"][0]["after"]), ({"terms": [RETAIL]}, {"terms": [CUSTODY]}))

    def test_a_platform_agent_files_under_its_own_open_run(self) -> None:
        key = agents_testing.agent_key(scopes=(perms.SCOPE_PROPOSALS_WRITE,))
        headers = {"HTTP_X_API_KEY": key.plain_key}
        self._refused(self._file(body(change(self.obligations[0])), headers), 422, "run_not_open")
        run = agents_testing.platform_run(key=key)
        filed = self._file({**body(change(self.obligations[0])), "agentRunId": str(run.id), "model": "agent pipeline 0.4"}, headers)
        self.assertEqual(filed.status_code, 201, filed.content)
        proposal = Proposal.objects.get(pk=filed.json()["id"])
        self.assertEqual(
            (proposal.origin, proposal.proposed_by_api_key_id, proposal.proposed_by_agent_id, proposal.agent_run_id),
            (OriginType.AGENT.value, key.id, key.agent.id, run.id),
        )
        # Another key's run is not this key's to file under.
        other = agents_testing.platform_run()
        self._refused(self._file({**body(change(self.obligations[1])), "agentRunId": str(other.id)}, headers), 404, "not_found")

    def test_no_bank_and_no_other_platform_role_files_one(self) -> None:
        # Platform rows are written with no tenant activated (H15), so they come first.
        reader_key = agents_testing.agent_key(scopes=(perms.SCOPE_LIBRARY_READ,))
        admin = sign_in(factories.platform_user(roles=("platform_admin",)))
        tenant = factories.tenant(slug="bank")
        officer = factories.member_user(tenant, roles=("compliance_officer", "admin"))
        bank_key = factories.api_key(tenant, scopes=(perms.SCOPE_PROPOSALS_WRITE,))
        bank_session = sign_in(officer, tenant=tenant)
        tenancy.clear_tenant()
        for who, headers, wanted in (
            ("a bank's session", bank_session, perms.PROPOSALS_REVIEW),
            ("a platform admin", admin, perms.PROPOSALS_REVIEW),
            ("a bank's key with proposals:write", {"HTTP_X_API_KEY": bank_key.plain_key}, perms.SCOPE_PROPOSALS_WRITE),
            ("a platform key without proposals:write", {"HTTP_X_API_KEY": reader_key.plain_key}, perms.SCOPE_PROPOSALS_WRITE),
        ):
            with self.subTest(who=who):
                refused = self._file(body(change(self.obligations[0])), headers)
                self._refused(refused, 403, "permission_denied")
                self.assertEqual(refused.json()["requiredPermission"], wanted)
        self.assertFalse(Proposal.objects.exists())

    def test_the_writer_refuses_a_caller_inside_a_bank(self) -> None:
        tenant = factories.tenant(slug="bank")
        tenancy.activate(tenant.id)
        proposer = Proposer(actor=factories.user_actor(), user=self.editor)
        payload = ObligationScopePayload.model_validate(body(change(self.obligations[0]))["payload"])
        with self.assertRaises(ProblemError) as refused:
            batch.create_batch(kind="obligation_scope", title="Re-tag", payload=payload, proposer=proposer)
        self.assertEqual(refused.exception.status, 403)
        tenancy.clear_tenant()
        self.assertFalse(Proposal.objects.exists())

    @override_settings(PROPOSAL_BATCH_MAX_ROWS=3)
    def test_a_batch_above_the_cap_is_refused(self) -> None:
        self._refused(self._file(body(*(change(obligation) for obligation in self.obligations[:4]))), 422, "batch_too_large")
        self.assertEqual(self._file(body(*(change(obligation) for obligation in self.obligations[:3]))).status_code, 201)

    def test_a_retry_with_the_same_idempotency_key_files_one_batch(self) -> None:
        headers = {**sign_in(self.editor), "HTTP_IDEMPOTENCY_KEY": "retag-custody-1"}
        first = self._file(body(change(self.obligations[0])), headers)
        again = self._file(body(change(self.obligations[0])), headers)
        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(first.json()["id"], again.json()["id"])
        self.assertEqual(Proposal.objects.count(), 1)
        self.assertTrue(AuditEvent.objects.filter(action="proposal.replayed", subject_id=first.json()["id"]).exists())
        self._refused(self._file(body(change(self.obligations[1])), headers), 409, "idempotency_conflict")


    def test_a_batch_is_never_decided_as_one_proposal(self) -> None:
        filed = self._file(body(change(self.obligations[0]))).json()
        reviewer = sign_in(factories.platform_user(roles=("library_editor",), email="reviewer@bleqq.test"), step_up=True)
        for verb, data in (("approve", {"note": "Fine."}), ("reject", {"rejectionCode": "other", "note": "No."})):
            with self.subTest(verb=verb):
                self._refused(self._post(f"/proposals/{filed['id']}/{verb}", data, reviewer), 409, "invalid_transition")
        self.assertEqual(Proposal.objects.get(pk=filed["id"]).status, "open")


class TheBatchPayloadIsChecked(BatchTestCase):
    def test_every_rule_a_scope_answers_to(self) -> None:
        retired = self.obligations[1]
        with library_write("test"):
            Obligation.objects.filter(pk=retired.pk).update(status="retired")
        first = self.obligations[0]
        for case, data, status, code in (
            ("not a batch kind", {**body(change(first)), "kind": "new_obligation_version"}, 422, "unknown_key"),
            ("an obligation that is not here", body({**change(first), "obligationId": str(uuid.uuid4())}), 422, "unknown_key"),
            ("a retired obligation", body(change(retired)), 422, "unknown_key"),
            ("a term that is not a term", body(change(first, add=("service_type:dragon",))), 422, "unknown_key"),
            ("a mirrored jurisdiction term", body(change(first, add=("jurisdiction:se",))), 422, "jurisdiction_term_mirrored"),
            ("a standard's term on a law's duty", body(change(first, add=("standard:iso_iec_27001",))), 422, "standard_term_only_on_standards"),
            ("no source", body(change(first, source="  ")), 422, "source_missing"),
            ("a source nobody can follow", body(change(first, source="see above")), 422, "validation_error"),
            ("an entry that changes nothing", body(change(first, add=(RETAIL,))), 422, "validation_error"),
            ("an obligation named twice", body(change(first), change(first)), 422, "validation_error"),
            ("a term added and removed", body(change(first, add=(CUSTODY,), remove=(CUSTODY,))), 422, "validation_error"),
            ("no entry at all", body(), 422, "validation_error"),
            ("a field the payload does not name", body({**change(first), "tone": "negative"}), 422, "validation_error"),
            ("a source link that is not https", {**body(change(first)), "sourceUrl": "http://www.fi.se/"}, 422, "validation_error"),
            ("a blank title", body(change(first), title="  "), 422, "validation_error"),
        ):
            with self.subTest(case=case):
                self._refused(self._file(data), status, code)
        self.assertFalse(Proposal.objects.exists())

    def test_a_standards_duty_keeps_exactly_one_standard_term_and_link_sources(self) -> None:
        conformance = library_build.standard()
        for case, data, code in (
            ("losing its standard term", body(change(conformance, add=(), remove=("standard:iso_iec_27001",))), "standard_term_required"),
            ("a source that is not a link", body(change(conformance, source="fffs-2017-2-9-6")), "licensed_text"),
            ("a source label that is not its reference", {**body(change(conformance)), "sourceLabel": "Annex A 5.1"}, "licensed_text"),
        ):
            with self.subTest(case=case):
                self._refused(self._file(data), 422, code)
        filed = self._file({**body(change(conformance)), "sourceLabel": "ISO/IEC 27001:2022"})
        self.assertEqual(filed.status_code, 201, filed.content)


class ReadingABatch(BatchTestCase):
    def _filed(self, obligations: list[Obligation]) -> dict[str, Any]:
        response = self._file(body(*(change(obligation) for obligation in obligations)))
        self.assertEqual(response.status_code, 201, response.content)
        answer: dict[str, Any] = response.json()
        return answer

    def test_a_row_whose_record_moved_since_reads_as_stale(self) -> None:
        filed = self._filed(self.obligations[:2])
        with library_write("test"):
            ObligationTerm.objects.create(obligation=self.obligations[0], term=library_build.term("client_category:professional"))
        read = self.client.get(f"{V1}/proposal-batches/{filed['id']}", **sign_in(self.editor))
        self.assertEqual(read.status_code, 200, read.content)
        stale = {row["subjectId"]: row["stale"] for row in read.json()["rows"]}
        self.assertEqual(stale, {str(self.obligations[0].id): True, str(self.obligations[1].id): False})

    def test_only_a_reviewer_reads_a_batch_and_only_a_batch(self) -> None:
        filed = self._filed(self.obligations[:1])
        single = Proposal.objects.create(
            kind=ProposalKind.VOCABULARY_CREATE.value, title="A flag", origin=OriginType.USER.value, proposed_by_user=self.editor
        )
        editor = sign_in(self.editor)
        for missing in (str(single.id), str(uuid.uuid4()), "not-a-uuid"):
            with self.subTest(missing=missing):
                self._refused(self.client.get(f"{V1}/proposal-batches/{missing}", **editor), 404, "not_found")
        admin = sign_in(factories.platform_user(roles=("platform_admin",)))
        self._refused(self.client.get(f"{V1}/proposal-batches/{filed['id']}", **admin), 403, "permission_denied")

    def test_a_full_batch_is_read_inside_the_budget(self) -> None:
        """NFR-02: a batch of `PROPOSAL_BATCH_MAX_ROWS` rows is read in one answer that
        reports `Server-Timing: app` and stays under API_BUDGET_MS. CPU time on the request
        thread, the best of five, with coverage's tracer paused, as the other budget tests
        measure it."""
        extra = [
            library_build.obligation(self.law, key=f"obl-budget-{n:03d}", terms=(RETAIL,))
            for n in range(settings.PROPOSAL_BATCH_MAX_ROWS - len(self.obligations))
        ]
        filed = self._filed(self.obligations + extra)
        editor = sign_in(self.editor)
        response = self.client.get(f"{V1}/proposal-batches/{filed['id']}", **editor)
        self.assertEqual(len(response.json()["rows"]), settings.PROPOSAL_BATCH_MAX_ROWS)
        self.assertRegex(response["Server-Timing"], r"^app;dur=\d+\.\d$")
        spent = []
        tracer = sys.gettrace()
        sys.settrace(None)
        try:
            for _ in range(5):
                started = time.thread_time()
                self.client.get(f"{V1}/proposal-batches/{filed['id']}", **editor)
                spent.append((time.thread_time() - started) * 1000)
        finally:
            sys.settrace(tracer)
        self.assertLess(min(spent), settings.API_BUDGET_MS)

