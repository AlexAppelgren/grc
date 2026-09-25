"""Scenario tests for the governance app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

AUD-S1 and AUD-S2 are proven by the structural guards in apps/shared; their scenarios
run those guard proofs, so one source proves each rule. AUD-S7 reads through
GET /audit-events (chunk 4).

Operations exercised (the audit-on-write guard reads these names): createProposal,
approveProposal, createConsoleTenant, updateTenant, createFootprintRequest, closeProblemReport,
createChange, confirmSoWhat, rateAnswer. ADM-S4 also drives the console routes other apps
register — the source registry, the search evaluation set, the platform agent keys and the
agent definitions they bind to — by their gate alone; what each one then does is its own
app's scenario.

Prefixes hosted: ACC, ADM, AUD.
"""

from __future__ import annotations

import unittest
import uuid
from typing import Any, ClassVar, cast
from unittest import skip

from django.db import DatabaseError, connection, transaction
from django.test import Client, override_settings
from django.utils.dateparse import parse_datetime

from apps.agents import testing as agent_build
from apps.cases import creation, testing as case_build
from apps.governance.models import AiGeneration
from apps.identity.models import Invitation, TenantRole
from apps.identity.session_logic import actor_of
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.search.tests_ask import answer_of, events_of
from apps.search.tests_hybrid import CorpusMixin
from apps.shared import factories, outbox, permissions as perms, tenancy
from apps.shared.audit import AppendOnlyRefused
# Modules, not classes: a TestCase imported by name would be collected and run here twice.
from apps.shared import tests_append_only as append_only_guards
from apps.shared import tests_audit_on_write as audit_guards
from apps.shared import tests_rls as rls_guards
from apps.shared.adapters.mailer import MockMailer
from apps.shared.models import AuditEvent, Tenant, TenantContentLanguage
from apps.shared.permissions import UNGATED_BY_DESIGN, gate_of
from apps.shared.routes import iter_operations
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import ComplianceStatus, Flag
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.taxonomy.tenant_hooks import TENANT_SYSTEM_ROWS
from apps.tenants import logic as tenants_logic
from apps.watch import testing as watch_build
from config.api import api

V1 = "/api/v1"
# The mixed tables (app.md, AC "Mixed tables"), each with its library read rule as
# PostgreSQL renders it back: every library row, except that a confirming agent's decisions
# in `ai_generation` are the platform's alone (D-80).
MIXED_TABLES = ("audit_event", "outbox_event", "problem_report", "api_key", "ai_generation")
LIBRARY_READ_RULES = dict.fromkeys(MIXED_TABLES, "(tenant_id IS NULL)") | {
    "ai_generation": "((tenant_id IS NULL) AND ((purpose)::text <> 'agent_review'::text))",
}

PLATFORM_ROLES = ("library_editor", "platform_admin")
_ANY_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")

# AUD-S4: the "So what?" a run files with a change, and the library an Ask answer rests on.
_SO_WHAT = "Teams that pay for external research should confirm that documented criteria exist."


class _AskCorpus(CorpusMixin):
    """The search tests' indexed library, so an Ask answer here cites a real obligation."""


# ADM-S4 drives every console endpoint that a platform permission gates. Ninja parses the
# body before the gate runs, so each entry carries a request the schema accepts; the id in
# a path never has to exist, because the gate answers first. The first assertion of the
# test fails when a console route is added and not listed here, so the table cannot rot.
PLATFORM_ROUTE_REQUESTS: dict[str, tuple[str, str, dict[str, Any] | None]] = {
    "listProposals": ("GET", "/proposals", None),
    "getProposal": ("GET", f"/proposals/{_ANY_ID}", None),
    "approveProposal": ("POST", f"/proposals/{_ANY_ID}/approve", {}),
    "rejectProposal": ("POST", f"/proposals/{_ANY_ID}/reject", {"rejectionCode": "other"}),
    # The console's own view of registered changes, gated by `proposals.review` like the
    # queue beside it: a library editor curates what an agent registered (WAT-01).
    "listConsoleChanges": ("GET", "/console/changes", None),
    "listConsoleTenants": ("GET", "/console/tenants", None),
    "createConsoleTenant": (
        "POST",
        "/console/tenants",
        {
            "name": "Console Bank AB",
            "slug": "console-bank",
            "timezone": "Europe/Stockholm",
            "defaultLanguage": "sv",
            "contentLanguages": ["sv", "en"],
            "firstAdminEmail": "first.admin@console-bank.test",
        },
    ),
    "consoleReissueEnrolment": (
        "POST",
        f"/console/tenants/{_ANY_ID}/members/{_ANY_ID}/reissue-enrolment",
        {"reason": "The administrator lost every device.", "outOfBandCheck": "Called the registered number."},
    ),
    # The source registry is the library editor's alone (WAT-01): a platform admin is refused.
    "createSource": (
        "POST",
        "/sources",
        {"name": "Finansinspektionen news", "kind": "authority_site", "checkFrequency": "daily"},
    ),
    "updateSource": ("PATCH", f"/sources/{_ANY_ID}", {"active": False}),
    # A key bound to an agent is the platform admin's alone (ID-10, AGT-01): a library
    # editor is refused. Creating one also needs a passkey, which the owner half proves.
    "listAgentKeys": ("GET", "/agent-keys", None),
    "createAgentKey": (
        "POST",
        "/agent-keys",
        {"name": "Watch sweeper", "agentId": str(_ANY_ID), "scopes": ["changes:write"]},
    ),
    "revokeAgentKey": ("POST", f"/agent-keys/{_ANY_ID}/revoke", {}),
    # The definitions a key is bound to, read under the same permission (ID-10, AGT-01).
    "listAgentDefinitions": ("GET", "/agent-definitions", None),
    # The re-verification stamp (chunk 3, INV-S8): a console action on a library record,
    # so a platform_admin is refused it and a library_editor reaches it (and is then asked
    # for a passkey, which is a different refusal).
    "reverifyObligation": ("POST", f"/obligations/{_ANY_ID}/verifications", {"outcome": "no_change"}),
    # The search evaluation set (SRC-05): the library editor's alone, a platform admin is refused.
    "listEvalQuestions": ("GET", "/eval/questions", None),
    "createEvalQuestion": (
        "POST",
        "/eval/questions",
        {"key": "r-en-90", "lang": "en", "question": "costs and charges", "expected": [], "matchKind": "concept"},
    ),
    "listEvalRuns": ("GET", "/eval/runs", None),
    "getEvalBaseline": ("GET", "/eval/baseline", None),
}

# Console routes whose caller a logic gate decides instead of a decorator (they carry a
# `logic-gate` reason in UNGATED_BY_DESIGN). Each still answers 403 with the permission it
# wanted, to the platform role that does not hold it. No problem-report route is here: a
# report is read and closed inside its bank under `problems.report` (D-50, AUD-S5).
LOGIC_GATED_PLATFORM_ROUTES: dict[str, tuple[str, str, dict[str, Any] | None, str]] = {
    "createProposal": (
        "POST",
        "/proposals",
        {"kind": "vocabulary_create", "title": "Add a flag", "payload": {"list": "flag", "key": "x", "labels": {"en": "X"}}},
        "platform_admin",
    ),
}


class GovernanceScenarioTests(ScenarioTestCase):
    """Scenario tests for apps.governance, one method per @integration scenario."""

    def _prove(self, *guards: type[unittest.TestCase]) -> None:
        """Run every proof of the guard classes that prove a scenario, one test at a time
        inside this test's transaction (a class-level run would close its connection), and
        fail with the guards' own messages."""
        result = unittest.TestResult()
        for guard in guards:
            for name in unittest.defaultTestLoader.getTestCaseNames(guard):
                guard(name)(result)  # __call__: Django wraps each proof in a savepoint
        self.assertGreater(result.testsRun, 0)
        self.assertEqual([f"{test}: {trace}" for test, trace in result.errors + result.failures], [])

    def _post(self, path: str, body: dict[str, Any], headers: dict[str, Any]) -> Any:
        return self.client.post(f"{V1}{path}", data=body, content_type="application/json", **headers)

    def _one(self, action: str, subject_id: Any) -> AuditEvent:
        return AuditEvent.objects.get(action=action, subject_id=subject_id)

    def _ai_log(self, headers: dict[str, Any], query: str) -> dict[str, Any]:
        response = self.client.get(f"{V1}/ai-generations?{query}", **headers)
        self.assertEqual(response.status_code, 200, response.content)
        return cast(dict[str, Any], response.json())

    def test_aud_s1(self) -> None:
        """AUD-S1

        Every write leaves an audit row and an outbox row in the same transaction (AUD-01, AC-AUD1).
        """
        # The client proof posts to the guard module's own probe views (its class decorator).
        with override_settings(ROOT_URLCONF=audit_guards.__name__):
            self._prove(
                audit_guards.MutatingRoutesHaveScenarios,
                audit_guards.AuditAssertingClientBites,
                audit_guards.RecordWritesBothRowsInOneTransaction,
            )

    def test_aud_s2(self) -> None:
        """AUD-S2

        The audit table rejects update and delete (AUD-01, AC-AUD1).

        The hatch clause is proven for the application role by
        apps/shared/tests_append_only.py, whose proofs need committed rows on the
        cw_app connection and so cannot run inside this transaction.
        """
        self._prove(audit_guards.AppendOnlyHolds, append_only_guards.EveryAppendOnlyTableRunsAGuard)

    def test_aud_s4(self) -> None:
        """AUD-S4

        Every model output is logged with its review state (AUD-02).
        Operations: `createChange`, `ask`, `confirmSoWhat`, `rateAnswer`, `listAiGenerations`.
        """
        # Given the library a question is answered from, two banks whose footprints differ,
        # and a watch run with a platform key open.
        _AskCorpus.build_corpus()
        watch_build.seed_watch_reference()
        creation.register()
        banks = case_build.two_tenants_with_different_footprints(inside="regime:securities", outside="regime:aml")
        officer_a = factories.member(
            banks.inside, roles=("compliance_officer",), user_row=factories.user(name="Sara Lind")
        ).user
        officer_b = factories.member(banks.outside, roles=("compliance_officer",)).user
        reader_a = factories.member(banks.inside, roles=("reader",)).user
        tenancy.clear_tenant()
        key = agent_build.agent_key()
        run = agent_build.platform_run(key=key)

        # And a So what draft and an agent classification: the run files a change with both.
        tenancy.clear_tenant()
        filed = self._post(
            "/changes",
            {
                "stableKey": "chg-fi-2026-research-payments",
                "title": "FI adopts amended rules on paying for investment research",
                "changeType": "adopted",
                "authorityLabel": "Finansinspektionen",
                "summary": "FI's board decided to amend three regulations in the securities area.",
                "sourceLabel": "Finansinspektionen",
                "sourceUrl": "https://www.fi.se/",
                "documents": [{"url": "https://www.fi.se/en/published/news/2026/research-payments/", "isPrimary": True}],
                "termIds": [str(watch_build.term("regime:securities").id)],
                "agentRunId": str(run.id),
                "soWhat": {
                    "text": _SO_WHAT,
                    "model": "claude-opus-5",
                    "modelVersion": "2026-05-01",
                    "citations": [{"label": "Finansinspektionen", "url": "https://www.fi.se/"}],
                },
            },
            {"HTTP_X_API_KEY": key.plain_key},
        )
        self.assertEqual(filed.status_code, 201, filed.content)
        change_id = filed.json()["id"]
        with transaction.atomic():
            tenancy.clear_tenant()
            while outbox.deliver_batch().delivered:  # the cases the registration opens
                pass

        # And an Ask answer in bank A. Ask changes no record and so writes no audit row by
        # design (SRC-05), which is why it goes through a plain client.
        asked = Client().post(
            f"{V1}/ask",
            data={"question": "What must we disclose about costs and charges?", "lang": "en"},
            content_type="application/json",
            **sign_in(reader_a, tenant=banks.inside),
        )
        self.assertEqual(asked.status_code, 200, getattr(asked, "content", b""))
        events = events_of(asked)
        answer_of(events)
        answer_id = events[0]["id"]

        # Then each has an ai_generation row with purpose, model, version, input reference,
        # output, citations and review state pending
        officer_a_headers = sign_in(officer_a, tenant=banks.inside)
        about_change = self._ai_log(officer_a_headers, f"subjectId={change_id}")
        by_purpose = {row["purpose"]: row for row in about_change["items"]}
        self.assertEqual(sorted(by_purpose), ["scope_suggestion", "so_what"], "narrowed to the one change")
        answers = [row for row in self._ai_log(officer_a_headers, "purpose=answer")["items"] if row["id"] == answer_id]
        self.assertEqual(len(answers), 1, "the answer's id is its row in the log")
        so_what, scope, answer = by_purpose["so_what"], by_purpose["scope_suggestion"], answers[0]
        for row in (so_what, scope, answer):
            with self.subTest(purpose=row["purpose"]):
                self.assertTrue(row["model"] and row["modelVersion"], row)
                self.assertTrue(row["output"], row)
                self.assertTrue(row["citations"], row)
                self.assertTrue(all(citation["label"] and citation["url"] for citation in row["citations"]), row)
                self.assertEqual((row["status"], row["reviewedBy"], row["reviewedAt"]), ("draft", None, None))
        # The input a draft and a classification were made from is the change they are about;
        # an answer's is the prompt it was given, kept as a template and a hash, never as text.
        for row in (so_what, scope):
            self.assertEqual((row["subjectType"], row["subjectId"]), ("regulatory_change", change_id))
            self.assertTrue(row["modelMetadataReportedByAgent"], "the run's own account of its model (D-66)")
        self.assertEqual((so_what["model"], so_what["modelVersion"], so_what["output"]), ("claude-opus-5", "2026-05-01", _SO_WHAT))
        self.assertIn("regime:securities", scope["output"])
        self.assertTrue(answer["promptTemplate"] and answer["promptHash"], answer)
        self.assertFalse(answer["modelMetadataReportedByAgent"], "bleqq made this call and measured it")
        self.assertTrue(answer["tenantScoped"])
        with transaction.atomic():
            tenancy.clear_tenant()
            shared_before = list(AiGeneration.objects.filter(subject_id=change_id).order_by("id").values())

        # When a person in bank A confirms the So what on their case
        confirmed = self._post(f"/changes/{change_id}/so-what/confirm", {}, officer_a_headers)
        self.assertEqual(confirmed.status_code, 200, confirmed.content)

        # Then bank A reads the row's review state as confirmed with the person and the time
        mine = {row["purpose"]: row for row in self._ai_log(officer_a_headers, f"subjectId={change_id}")["items"]}
        self.assertEqual(mine["so_what"]["status"], "confirmed")
        self.assertEqual(mine["so_what"]["reviewedBy"], {"id": str(officer_a.id), "name": "Sara Lind"})
        self.assertEqual(
            parse_datetime(mine["so_what"]["reviewedAt"]), parse_datetime(confirmed.json()["confirmedAt"])
        )
        # And bank B, which has not confirmed its own copy, reads the same row as a draft
        theirs = {
            row["purpose"]: row
            for row in self._ai_log(sign_in(officer_b, tenant=banks.outside), f"subjectId={change_id}")["items"]
        }
        self.assertEqual(theirs["so_what"]["id"], mine["so_what"]["id"])
        self.assertEqual((theirs["so_what"]["status"], theirs["so_what"]["reviewedBy"]), ("draft", None))
        # And nothing on the shared row is written
        with transaction.atomic():
            tenancy.clear_tenant()
            self.assertEqual(
                list(AiGeneration.objects.filter(subject_id=change_id).order_by("id").values()), shared_before
            )

        # When a person marks an answer as wrong
        note = "The itemised disclosure is due before the service, not only afterwards."
        rated = self._post(
            f"/answers/{answer_id}/feedback", {"feedback": "wrong", "note": note}, sign_in(reader_a, tenant=banks.inside)
        )
        self.assertEqual(rated.status_code, 204, rated.content)

        # Then feedback is stored on the row
        [answer] = [row for row in self._ai_log(officer_a_headers, "purpose=answer")["items"] if row["id"] == answer_id]
        self.assertEqual((answer["feedback"], answer["feedbackNote"]), ("wrong", note))

        # And a holder of ai_log.read lists the rows for their tenant only: bank B never sees
        # bank A's answer, and a reader without the permission is refused.
        theirs_all = self._ai_log(sign_in(officer_b, tenant=banks.outside), "purpose=answer")
        self.assertNotIn(answer_id, {row["id"] for row in theirs_all["items"]})
        refused = self.client.get(f"{V1}/ai-generations", **sign_in(reader_a, tenant=banks.inside))
        self.assertEqual((refused.status_code, refused.json()["requiredPermission"]), (403, "ai_log.read"))

    def test_aud_s5(self) -> None:
        """AUD-S5

        A problem report stays inside the bank that filed it (AUD-03).

        The integration half: the report is read by its own bank only, through
        listProblemReports and closeProblemReport, and refused to a library editor, another
        bank and a key; no problem-report route is gated by anything a platform role holds;
        the words reach no audit row and no outbox payload (what a webhook or SIEM stream
        carries); and the loop back to the library is an agent's proposal in an open run,
        approved by an editor, which the bank reads under Library updates. The dialog's copy
        is the journey's (`@e2e`). No model reads a report because nothing passes one to a
        model: `apps/shared/ai.py` is the only caller and takes no report.
        """
        from apps.agents import testing as agents_testing
        from apps.library import testing as build
        from apps.library.models import ProblemReport
        from apps.shared.models import OutboxEvent
        from apps.shared.permissions import Gate
        from apps.taxonomy import footprint_logic
        from apps.taxonomy.models import TaxonomyTerm
        from apps.shared.audit import Actor
        from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies

        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        obligation = build.obligation(
            build.instrument(key="aud-s5-instrument", regime="regime:securities"),
            key="obl-aud-s5",
            terms=("service_type:advice",),
        )
        tenant_a = factories.tenant(slug="aud-s5-a")
        tenant_b = factories.tenant(slug="aud-s5-b")
        self.activate(tenant_a)
        ensure_tenant_vocabularies(tenant_a, actor=Actor.system("test"))
        footprint_logic.seed_terms(
            tenant=tenant_a,
            actor=Actor.system("test"),
            terms=[TaxonomyTerm.objects.get(dimension__key="service_type", key="advice")],
        )
        reader_a = factories.member(tenant_a, roles=("reader",)).user
        officer_a = factories.member(tenant_a, roles=("compliance_officer",)).user
        officer_b = factories.member(tenant_b, roles=("compliance_officer",)).user
        editor = factories.platform_user(roles=("library_editor",))

        # Given a reader in tenant A reported "This looks wrong" on an obligation.
        words = "This looks wrong: the source says the review is annual, the summary says every two years."
        filed = self._post(f"/obligations/{obligation.id}/problem-reports", {"description": words}, sign_in(reader_a, tenant=tenant_a))
        self.assertEqual(filed.status_code, 201, filed.content)
        report_id = filed.json()["id"]

        # Then the report is readable by tenant A only.
        listed = self.client.get(f"{V1}/problem-reports", **sign_in(officer_a, tenant=tenant_a))
        self.assertEqual([row["id"] for row in listed.json()["items"]], [report_id])
        self.assertEqual(listed.json()["items"][0]["description"], words)
        closed = self.client.patch(
            f"{V1}/problem-reports/{report_id}",
            data={"status": "answered", "resolutionNote": "The watch will re-check it against the source."},
            content_type="application/json",
            **sign_in(officer_a, tenant=tenant_a),
        )
        self.assertEqual(closed.status_code, 200, closed.content)

        # When a library editor, another tenant, an API key or an agent asks for it, each
        # answers 403 or 404.
        other_bank = sign_in(officer_b, tenant=tenant_b)
        self.assertEqual(self.client.get(f"{V1}/problem-reports", **other_bank).json()["items"], [])
        reopen = {"status": "fixed", "resolutionNote": "Not ours to close."}
        self.assertEqual(
            self.client.patch(f"{V1}/problem-reports/{report_id}", data=reopen, content_type="application/json", **other_bank).status_code,
            404,
        )
        platform = sign_in(editor)
        self.assertEqual(self.client.get(f"{V1}/problem-reports", **platform).status_code, 403)
        self.assertEqual(
            self.client.patch(f"{V1}/problem-reports/{report_id}", data=reopen, content_type="application/json", **platform).status_code,
            403,
        )
        tenancy.clear_tenant()
        agent = agents_testing.agent_key(scopes=(perms.SCOPE_PROPOSALS_WRITE, perms.SCOPE_LIBRARY_READ))
        bank_key = factories.api_key(tenant_a, scopes=tuple(sorted(perms.ALL_SCOPES)))
        # A key is not a session, so both routes refuse it before any gate: 401, as every
        # session-only route answers a key (INPUT_DELTAS §14).
        for key in (agent.plain_key, bank_key.plain_key):
            self.assertEqual(self.client.get(f"{V1}/problem-reports", HTTP_X_API_KEY=key).status_code, 401)
            self.assertEqual(
                self.client.patch(f"{V1}/problem-reports/{report_id}", data=reopen, content_type="application/json", HTTP_X_API_KEY=key).status_code,
                401,
            )
        # And the console has no problem-report surface: every route that serves a report
        # is gated by `problems.report`, which no platform role holds.
        report_gates = {gate_of(op.view_func) for op in iter_operations(api) if "problem-report" in op.path}
        self.assertEqual(report_gates, {Gate("permission", perms.PROBLEMS_REPORT)})
        for role in PLATFORM_ROLES:
            self.assertNotIn(perms.PROBLEMS_REPORT, perms.SYSTEM_ROLES[role])

        # When the watch agents' re-check proposes the correction, in an open run of its own,
        # and an editor approves it.
        tenancy.clear_tenant()
        run = agents_testing.platform_run(key=agent)
        proposed = self._post(
            "/proposals",
            {
                "kind": "new_obligation_version",
                "title": "Re-check against the source: the review is annual",
                "targetType": "obligation",
                "targetId": str(obligation.id),
                "payload": {"summaries": {"en": "The institution reviews the duty every year."}, "originalLanguage": "en", "isMachine": True},
                "fieldSources": {"summaries.en": "https://www.fi.se/"},
                "sourceLabel": "Finansinspektionen",
                "sourceUrl": "https://www.fi.se/",
                "model": agents_testing.SWEEPER_MODEL,
                "agentRunId": str(run.id),
            },
            {"HTTP_X_API_KEY": agent.plain_key, "HTTP_IDEMPOTENCY_KEY": str(uuid.uuid4())},
        )
        self.assertEqual(proposed.status_code, 201, proposed.content)
        self.assertNotIn(words, proposed.content.decode(), "the correction carries no bank's words")
        approved = self._post(f"/proposals/{proposed.json()['id']}/approve", {}, sign_in(editor, step_up=True))
        self.assertEqual(approved.status_code, 200, approved.content)

        # Then tenant A sees the corrected record under "Library updates".
        updates = self.client.get(f"{V1}/library-updates", **sign_in(reader_a, tenant=tenant_a))
        self.assertEqual(updates.status_code, 200, updates.content)
        items = [item for day in updates.json()["days"] for item in day["items"]]
        self.assertIn(proposed.json()["id"], [item["id"] for item in items])
        self.assertIn(str(obligation.id), [item["target"]["id"] for item in items])

        # And the report's words reached no audit row and no outbox payload, in either zone.
        self.activate(tenant_a)
        carried = [
            " ".join([event.summary, event.subject_title, str(event.before), str(event.after)])
            for event in AuditEvent.objects.all()
        ] + [str(event.payload) for event in OutboxEvent.objects.all()]
        self.assertTrue(carried)
        self.assertEqual([text for text in carried if words in text], [])
        self.assertEqual(ProblemReport.objects.get(id=report_id).text, words)

    @skip("pending: AUD-S6 (AUD-04, chunk 12)")
    def test_aud_s6(self) -> None:
        """AUD-S6

        The purge deletes ten years after a record's last use and never updates a ledger row (AUD-04).
        """

    def test_aud_s7(self) -> None:
        """AUD-S7

        Mixed tables show library rows to everyone and tenant rows to their tenant (AUD-01).
        """
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        tenant_a = factories.tenant(slug="audit-a")
        tenant_b = factories.tenant(slug="audit-b")
        officer_a = factories.member(tenant_a, roles=("compliance_officer",)).user
        reader_b = factories.member(tenant_b, roles=("reader",)).user
        editor = factories.platform_user(roles=("library_editor",))
        second_editor = factories.platform_user(roles=("library_editor",))
        # Given a library change: a vocabulary row added by an approved proposal, recorded
        # with no tenant and a library editor as actor.
        body = {
            "kind": "vocabulary_create",
            "title": "Add the flag Client money",
            "payload": {"list": "flag", "key": "client_money", "labels": {"en": "Client money"}},
            "sourceLabel": "FFFS 2017:2",
            "sourceUrl": "https://www.fi.se/",
        }
        proposal = self._post("/proposals", body, sign_in(editor))
        self.assertEqual(proposal.status_code, 201, proposal.content)
        approved = self._post(f"/proposals/{proposal.json()['id']}/approve", {}, sign_in(second_editor, step_up=True))
        self.assertEqual(approved.status_code, 200, approved.content)
        library_event = self._one("vocabulary.created", Flag.objects.get(key="client_money").id)
        # And tenant A's own work (a footprint change request; cases arrive with chunk 9).
        requested = self._post(
            "/tenant/footprint/requests",
            {"adds": [{"dimension": "channel", "key": "digital"}], "removes": []},
            sign_in(officer_a, tenant=tenant_a),
        )
        self.assertEqual(requested.status_code, 201, requested.content)
        tenant_event = self._one("footprint.change_requested", requested.json()["id"])
        self.assertEqual(tenant_event.tenant_id, tenant_a.id)
        # When tenant B reads the audit log, it sees the library event and not tenant A's.
        read = self.client.get(f"{V1}/audit-events?limit=100", **sign_in(reader_b, tenant=tenant_b))
        self.assertEqual(read.status_code, 200, read.content)
        seen = {row["id"] for row in read.json()["items"]}
        self.assertIn(str(library_event.id), seen)
        self.assertNotIn(str(tenant_event.id), seen)
        # Tenant A sees both.
        read_a = self.client.get(f"{V1}/audit-events?limit=100", **sign_in(officer_a, tenant=tenant_a))
        self.assertTrue({str(library_event.id), str(tenant_event.id)} <= {row["id"] for row in read_a.json()["items"]})
        # When the row-level security guard enumerates the mixed tables, each is enabled and
        # forced, reads "shared or mine" and writes only the session's own zone (H15): the
        # tenant policy carries the own-zone rule and a read policy adds the platform's rows.
        self._prove(rls_guards.RowLevelSecurityGuard)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tablename, policyname, cmd, qual, with_check FROM pg_policies WHERE tablename = ANY(%s)",
                [list(MIXED_TABLES)],
            )
            policies = {(table, policy): (cmd, qual, check) for table, policy, cmd, qual, check in cursor.fetchall()}
        own_zone = rls_guards.own_zone_rule("tenant_id")
        for table in MIXED_TABLES:
            write_rule = policies[(table, "tenant_isolation")]
            self.assertEqual(write_rule[0], "ALL", f"{table}'s tenant policy is not the write rule")
            self.assertIn(own_zone, write_rule[2], f"{table} accepts a write outside the session's zone")
            read_rule = policies[(table, rls_guards.LIBRARY_READ_POLICY)]
            self.assertEqual(
                (read_rule[0], read_rule[1]), ("SELECT", LIBRARY_READ_RULES[table]), f"{table} is not shared-or-mine"
            )

    def _call(self, method: str, path: str, payload: dict[str, Any] | None, headers: dict[str, Any]) -> Any:
        if payload is None:
            return self.client.get(f"{V1}{path}", **headers)
        send = getattr(self.client, method.lower())  # POST and PATCH both carry a body
        return send(f"{V1}{path}", data=payload, content_type="application/json", **headers)

    # The queue read, the detail read, approve and reject are gated in the body
    # (apps/proposals/api.py: require_reviewer), never by a decorator, because a session and
    # a platform key need different checks and `has_permission`/`has_scope` are
    # kind-exclusive (PRO-S13, D-62, ADR 0054). For a session principal that gate is still
    # exactly `proposals.review`, which is what ADM-02 asks about here, so these four are
    # named the same way `tests_library_fence.py`'s `WATCH_ROUTE_GATES` names its own
    # body-gated routes.
    BODY_GATED_PLATFORM_OPERATIONS: ClassVar[dict[str, str]] = {
        "listProposals": perms.PROPOSALS_REVIEW,
        "getProposal": perms.PROPOSALS_REVIEW,
        "approveProposal": perms.PROPOSALS_REVIEW,
        "rejectProposal": perms.PROPOSALS_REVIEW,
    }

    def _platform_gated_operations(self) -> dict[str, str]:
        """Every registered operation a platform permission gates, with that permission."""
        gated: dict[str, str] = dict(self.BODY_GATED_PLATFORM_OPERATIONS)
        for operation in iter_operations(api):
            gate = gate_of(operation.view_func)
            if gate is not None and gate.kind == "permission" and gate.value in perms.PLATFORM_PERMISSIONS:
                gated[operation.operation_id] = gate.value
        return gated

    def test_adm_s4(self) -> None:
        """ADM-S4

        The platform console offers each surface to the platform role that owns it (ADM-02).
        """
        seed_languages()
        holders = {key: factories.platform_user(roles=(key,)) for key in PLATFORM_ROLES}
        gated = self._platform_gated_operations()
        self.assertEqual(
            sorted(gated),
            sorted(PLATFORM_ROUTE_REQUESTS),
            "a console endpoint was added or removed; list it in PLATFORM_ROUTE_REQUESTS so ADM-S4 drives it",
        )
        for operation_id, (method, path, payload) in PLATFORM_ROUTE_REQUESTS.items():
            permission = gated[operation_id]
            owner = next(key for key in PLATFORM_ROLES if permission in perms.SYSTEM_ROLES[key])
            other = next(key for key in PLATFORM_ROLES if key != owner)
            with self.subTest(operation=operation_id):
                refused = self._call(method, path, payload, sign_in(holders[other]))
                self.assertEqual(refused.status_code, 403, refused.content)
                self.assertEqual(refused.json()["requiredPermission"], permission)
                # The owning role reaches the operation: it may still be refused for
                # another reason (a missing record, a missing step-up), never for this one.
                answered = self._call(method, path, payload, sign_in(holders[owner]))
                code = answered.json().get("code", "") if answered.status_code >= 400 else ""
                self.assertNotEqual(code, "permission_denied", f"{operation_id} refused {owner}")
        # The console routes a logic gate decides answer the same way.
        for operation_id, (method, path, payload, refused_role) in LOGIC_GATED_PLATFORM_ROUTES.items():
            with self.subTest(operation=operation_id):
                self.assertIn((method, path), UNGATED_BY_DESIGN)
                refused = self._call(method, path, payload, sign_in(holders[refused_role]))
                self.assertEqual(refused.status_code, 403, refused.content)
                self.assertTrue(refused.json()["requiredPermission"])

    @skip("pending: ADM-S5 (ADM-02, chunk 14)")
    def test_adm_s5(self) -> None:
        """ADM-S5

        System health names what is wrong (ADM-02).
        """

    def test_adm_s6(self) -> None:
        """ADM-S6

        A tenant is created from the console with its first administrator invited (ADM-02, ID-01, TEN-01).
        """
        MockMailer.reset()
        seed_languages()
        platform_admin = factories.platform_user(roles=("platform_admin",))
        headers = sign_in(platform_admin)
        created = self._post(
            "/console/tenants",
            {"name": "Example Bank AB", "firstAdminEmail": "admin@example-bank.test", "firstAdminTitle": "Head of Compliance"},
            headers,
        )
        self.assertEqual(created.status_code, 201, created.content)
        tenant = Tenant.objects.get(pk=created.json()["id"])
        self.assertEqual(tenant.slug, "example-bank-ab")
        # The console lists it by id, never by a count.
        listed = self.client.get(f"{V1}/console/tenants", **headers)
        self.assertIn(str(tenant.id), [row["id"] for row in listed.json()["items"]])
        # The tenant has its system roles, but no default or content language yet: those
        # are the bank's own to set (D-68), and setting none here is how ADM-S17 finds its
        # onboarding "profile" step open.
        self.activate(tenant)
        self.assertTrue(TenantRole.objects.filter(tenant=tenant, key="admin", is_system=True).exists())
        self.assertTrue(ComplianceStatus.objects.filter(tenant=tenant, is_system=True).exists())
        self.assertIsNone(tenant.default_language_id)
        self.assertEqual(TenantContentLanguage.objects.filter(tenant=tenant).count(), 0)
        # And one pending administrator invitation, whose link was emailed.
        invitation = Invitation.objects.get(tenant=tenant)
        self.assertEqual([link.role.key for link in invitation.role_links.all()], ["admin"])
        self.assertIsNone(invitation.accepted_at)
        self.assertEqual([mail.to for mail in MockMailer.sent], ["admin@example-bank.test"])
        # The creation is audited in the new tenant's own log.
        creation = self._one("tenant.created", tenant.id)
        self.assertEqual(creation.tenant_id, tenant.id)
        # So are the lists it was given, under the same person: the console's rows are
        # nobody's deploy, and the log says who created the bank.
        listed_rows = AuditEvent.objects.filter(tenant=tenant, action="vocabulary.created")
        self.assertEqual(listed_rows.count(), sum(len(rows) for _, rows in TENANT_SYSTEM_ROWS.values()))
        self.assertEqual({(row.actor_type, row.actor_id) for row in listed_rows}, {(creation.actor_type, creation.actor_id)})
        self.assertEqual((creation.actor_type, creation.actor_id), ("user", platform_admin.id))

        # Creating a second tenant whose name derives the same short name gets a suffix
        # instead of a 409: nobody is ever asked to pick a different one. A fresh platform
        # request starts with no tenant active, unlike this test's own connection, which
        # the first create left scoped to the first tenant; clearing it first is what a
        # second, unrelated request would actually see.
        tenancy.clear_tenant()
        second = self._post(
            "/console/tenants",
            {"name": "Example Bank AB", "firstAdminEmail": "admin2@example-bank.test"},
            headers,
        )
        self.assertEqual(second.status_code, 201, second.content)
        self.assertEqual(Tenant.objects.get(pk=second.json()["id"]).slug, "example-bank-ab-2")

    def test_adm_s17(self) -> None:
        """ADM-S17

        A bank sets its own timezone and languages, not the platform on its behalf (ADM-02, TEN-01, D-68).
        """
        seed_languages()
        platform_admin = factories.platform_user(roles=("platform_admin",))
        # The real console path (create_tenant), not the factory: the factory builds a
        # ready-to-use tenant with English already set, which is exactly what this
        # scenario proves a console-created one does not have.
        tenant = tenants_logic.create_tenant(
            actor=actor_of(platform_admin), name="Example Bank AB", first_admin_email="admin@example-bank.test", first_admin_title=""
        )
        admin = factories.member(tenant, roles=("admin",)).user
        headers = sign_in(admin, tenant=tenant)

        before = self.client.get(f"{V1}/tenant", **headers).json()
        self.assertEqual(before["timezone"], "Europe/Stockholm")
        self.assertIsNone(before["defaultLanguage"])
        self.assertFalse(next(step for step in before["onboarding"]["steps"] if step["key"] == "profile")["done"])

        updated = self.client.patch(
            f"{V1}/tenant",
            data={"timezone": "Europe/Copenhagen", "defaultLanguage": "da", "contentLanguages": ["da", "en"]},
            content_type="application/json",
            **headers,
        )
        self.assertEqual(updated.status_code, 200, updated.content)

        after = self.client.get(f"{V1}/tenant", **headers).json()
        self.assertEqual(after["timezone"], "Europe/Copenhagen")
        self.assertEqual(after["defaultLanguage"]["key"], "da")
        self.assertTrue(next(step for step in after["onboarding"]["steps"] if step["key"] == "profile")["done"])

    @skip("pending: AUD-S8 (AUD-04, chunk 12)")
    def test_aud_s8(self) -> None:
        """AUD-S8

        The ledger purge refuses a cutoff inside the floor and a paused tenant (AUD-04).
        """

    @skip("pending: ADM-S7 (ADM-02, chunk 14)")
    def test_adm_s7(self) -> None:
        """ADM-S7

        The console reads each bank's figures through one audited window (ADM-02).
        """

    def test_aud_s9(self) -> None:
        """AUD-S9

        An agent's approval is in the audit trail with the agent named (AUD-01, AUD-02).
        """
        from apps.agents import testing as agents_testing
        from apps.governance.models import AiGeneration
        from apps.library import testing as build
        from apps.shared.audit import Actor
        from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies

        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        obligation = build.obligation(build.instrument(key="aud-s9-instrument", regime="regime:securities"), key="obl-aud-s9")
        tenant = factories.tenant(slug="aud-s9")
        self.activate(tenant)
        ensure_tenant_vocabularies(tenant, actor=Actor.system("test"))

        proposer_key = factories.api_key(tenant, scopes=("proposals:write",))
        tenancy.clear_tenant()  # a platform key is written with no tenant activated (H15)
        reviewer_key = agents_testing.reviewer_api_key()
        # An obligation version, whose record names the agent that confirmed it (D-79).
        approved = self._post(
            "/proposals",
            {
                "kind": "new_obligation_version",
                "title": "Refresh the wording against the source",
                "targetType": "obligation",
                "targetId": str(obligation.id),
                "payload": {"summaries": {"en": "The duty as the source now reads it."}, "originalLanguage": "en", "isMachine": True},
                "fieldSources": {"summaries.en": "https://www.fi.se/"},
            },
            {"HTTP_X_API_KEY": proposer_key.plain_key},
        )
        self.assertEqual(approved.status_code, 201, approved.content)
        # The create request authenticated with a tenant key, which re-activates the tenant
        # for the rest of this connection's transaction; a platform key is written and read
        # with no tenant activated (H15).
        tenancy.clear_tenant()
        # The agent corrects the wording on the way through and approves, sending the model
        # call behind its decision and the open run of its own key it was made in (D-80).
        corrected = "The duty as the source now reads it, from the day the decision names."
        sent = agents_testing.decision(reviewer_key)
        decision = self._post(
            f"/proposals/{approved.json()['id']}/approve",
            {"note": "Confirmed.", "payloadOverrides": {"summaries": {"en": corrected}}, "fieldSources": {"summaries.en": "https://www.fi.se/"}, **sent},
            {"HTTP_X_API_KEY": reviewer_key.plain_key},
        )
        self.assertEqual(decision.status_code, 200, decision.content)
        self.assertEqual(sorted(obligation.versions.values_list("version_number", flat=True)), [1, 2])
        self.assertEqual(decision.json()["correctedByAgent"]["key"], reviewer_key.agent.key, "the correction is the agent's")
        self.assertIsNone(decision.json()["correctedBy"], "no person corrected it")
        applied = obligation.versions.get(version_number=2).summaries.get(language_id="en")
        self.assertEqual(applied.text, corrected)

        event = self._one("proposal.approved", uuid.UUID(approved.json()["id"]))
        self.assertEqual(event.actor_type, "agent")
        self.assertEqual(event.actor_id, reviewer_key.agent.id)
        # Named by its definition, its version and the key it used, not the key's id alone.
        self.assertIn(reviewer_key.agent.key, event.actor_label)
        self.assertIn(f"v{reviewer_key.agent.current_version}", event.actor_label)
        self.assertEqual(event.after["reviewingApiKeyPrefix"], reviewer_key.row.key_prefix)
        self.assertNotIn(str(reviewer_key.id), event.actor_label)
        self.assertTrue(event.after["corrected"], "the correction is recorded with the decision")
        self.assertEqual(event.after["agentRunId"], sent["agentRunId"], "and so is the run it was made in")
        # No step-up assertion: a key cannot step up.
        self.assertIsNone(event.step_up_assertion_id)

        # The model call behind the decision is in the AI output log: the agent's own report,
        # with its citations, about this proposal, in that run, and still a draft, because
        # no person has confirmed what a machine decided.
        logged = AiGeneration.objects.get(subject_id=approved.json()["id"])
        self.assertEqual(
            (logged.purpose, logged.subject_type, str(logged.agent_run_id), logged.model_metadata_reported_by_agent),
            ("agent_review", "proposal", sent["agentRunId"], True),
        )
        self.assertEqual(logged.citations, agents_testing.DECISION["citations"])
        self.assertEqual((logged.status, logged.reviewed_by_id, logged.reviewed_at), ("draft", None, None))
        self.assertEqual((logged.model, logged.model_version), (agents_testing.DECISION["model"], agents_testing.DECISION["modelVersion"]))

        # A rejection by that agent is recorded the same way, with its reason. An agent may
        # reject a vocabulary proposal, though only a person may approve one (D-79).
        second = self._post(
            "/proposals",
            {"kind": "vocabulary_create", "title": "Add the flag Sanctioned", "payload": {"list": "flag", "key": "sanctioned", "labels": {"en": "Sanctioned"}}},
            {"HTTP_X_API_KEY": proposer_key.plain_key},
        )
        self.assertEqual(second.status_code, 201, second.content)
        tenancy.clear_tenant()  # the create request re-activated the tenant; see above (H15)
        rejected = self._post(
            f"/proposals/{second.json()['id']}/reject",
            {"rejectionCode": "duplicate", "note": "Already exists.", **sent, "decision": agents_testing.REJECTION_DECISION},
            {"HTTP_X_API_KEY": reviewer_key.plain_key},
        )
        self.assertEqual(rejected.status_code, 200, rejected.content)
        reject_event = self._one("proposal.rejected", uuid.UUID(second.json()["id"]))
        self.assertEqual(reject_event.actor_type, "agent")
        self.assertEqual(reject_event.after["rejectionCode"], "duplicate")
        self.assertEqual(reject_event.after["agentRunId"], sent["agentRunId"])
        self.assertIsNone(reject_event.step_up_assertion_id)
        self.assertIn(reviewer_key.agent.key, reject_event.actor_label)
        rejection_logged = AiGeneration.objects.get(subject_id=second.json()["id"])
        self.assertEqual(
            (rejection_logged.purpose, str(rejection_logged.agent_run_id), rejection_logged.output),
            ("agent_review", sent["agentRunId"], agents_testing.REJECTION_DECISION["output"]),
        )

        # Append-only: the decision cannot be edited afterwards, through the model or past it
        # in raw SQL, which the table's trigger refuses.
        written = event.summary
        with self.assertRaisesMessage(AppendOnlyRefused, "is append-only"):
            event.summary = "edited"
            event.save(update_fields=["summary"])
        with self.assertRaises(DatabaseError) as refused:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("UPDATE audit_event SET summary = 'edited' WHERE id = %s", [str(event.id)])
        self.assertIn("append-only", str(refused.exception))
        self.assertEqual(self._one("proposal.approved", uuid.UUID(approved.json()["id"])).summary, written)

    @skip("pending: ACC-S11 (ACC-08, AC-ACC2, chunk 11)")
    def test_acc_s11(self) -> None:
        """ACC-S11

        Tenant reach needs two people, and off means off (ACC-08, AC-ACC2).
        """

    @skip("pending: ACC-S12 (ACC-08, chunk 11)")
    def test_acc_s12(self) -> None:
        """ACC-S12

        The access log records the call and holds no content (ACC-08).
        """
