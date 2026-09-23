"""Scenario stubs for the watch app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: WAT.
"""

import datetime
from typing import Any
from unittest import skip

from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.agents import testing as agent_build
from apps.cases import creation, testing as case_build
from apps.cases.models import CaseObligationLink
from apps.governance.models import AiGeneration
from apps.library import testing as library_build
from apps.shared import factories, outbox, permissions as perms, tenancy
from apps.shared.models import AuditEvent
from apps.shared.testing import (
    API_KEY_FOR_TESTS,
    SESSION_TOKEN_FOR_TESTS,
    agent_principal,
    sign_in,
    stub_api_key,
    stub_session,
    user_principal,
)
from apps.taxonomy.models import ChangeType
from apps.watch import testing as watch_build
from apps.watch.models import ChangeDocument, ChangeObligation, RegulatoryChange, SourceCheck

# The reform WAT-S3 names, held apart from the field that carries it. A stable key and the
# word "stableKey" on one line read to gitleaks' generic-api-key rule as a credential and
# its value, and the secret scan failed on a scenario fixture (2026-09-21). Allowlisting it
# would have taught the scanner to ignore the shape a real leak takes.
_DORA_RTS = "eu-dora-rts-2026-01"

# One reform as a sweep files it, for the scenarios that register one.
_CHANGE: dict[str, Any] = {
    "stableKey": "chg-fi-2026-research-payments",
    "title": "FI adopts amended rules on paying for investment research",
    "changeType": "adopted",
    "authorityLabel": "Finansinspektionen",
    "summary": "FI's board decided to amend three regulations in the securities area.",
    "sourceLabel": "Finansinspektionen",
    "sourceUrl": "https://www.fi.se/",
    "documents": [{"url": "https://www.fi.se/en/published/news/2026/research-payments/", "isPrimary": True}],
}


# WAT-S6 and WAT-S7 drive two banks over the real routes, so they need the case the
# registration opens and the words a bank writes over the draft.
_SECURITIES = "regime:securities"
_AML = "regime:aml"
_DRAFT = "Teams that pay for external research should confirm that documented criteria exist."

# The model call a confirming agent reports with its decision (D-80), from the prototype's
# own reform and its public source.
_DECISION: dict[str, Any] = {
    "model": "claude-opus-5",
    "modelVersion": "2026-05-01",
    "promptTemplate": "library-confirmer/curation/v1",
    "output": "Confirm. The memorandum adopts the rule, in the securities area, on the advice perimeter.",
    "citations": [{"label": "Finansinspektionen, decision memorandum", "url": "https://www.fi.se/en/published/news/2026/reporting/"}],
}
_OUR_WORDS = "Self-directed trading and Guided investing both pay for research; the desk documents the criteria."


def _drain() -> None:
    """Deliver the outbox until it is empty, so the cases the registration opened exist."""
    with transaction.atomic():
        tenancy.clear_tenant()
    while outbox.deliver_batch().delivered:
        pass


class WatchScenarioTests(TestCase):
    """Scenario tests for apps.watch, one method per @integration scenario."""

    def _run_with_a_key(self) -> tuple[Any, str]:
        """A platform key with a run open, and the value it sends as `X-API-Key`."""
        watch_build.seed_watch_reference()
        tenancy.clear_tenant()
        key = agent_build.agent_key()
        return agent_build.platform_run(key=key), key.plain_key

    def _two_banks(self) -> Any:
        """Two banks with different footprints, their cases opened by the real handler."""
        creation.register()
        banks = case_build.two_tenants_with_different_footprints(inside=_SECURITIES, outside=_AML)
        _drain()
        tenancy.clear_tenant()
        return banks

    def _register(self, plain: str, payload: dict[str, Any]) -> Any:
        return self.client.post(
            "/api/v1/changes", data=payload, content_type="application/json", HTTP_X_API_KEY=plain
        )

    def test_wat_s1(self) -> None:
        """WAT-S1

        The source registry and coverage log show what was checked and with what result (WAT-01).
        Operations: `createSource`, `updateSource`, `recordSourceCheck`.
        """
        watch_build.seed_watch_reference()
        tenancy.clear_tenant()
        key = agent_build.agent_key()
        person = factories.platform_user(email="library.editor@bleqq.example")
        editor = stub_session(user_principal(permissions={perms.SOURCES_MANAGE}, subject_id=person.id))
        session: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"}

        # Given a registered source "Finansinspektionen news" with a check cadence
        with editor:
            registered = self.client.post(
                "/api/v1/sources",
                data={
                    "name": "Finansinspektionen news",
                    "url": "https://www.fi.se/en/published/news/",
                    "kind": "authority_site",
                    "checkFrequency": "daily",
                },
                content_type="application/json",
                **session,
            )
        self.assertEqual(registered.status_code, 201, registered.content)
        self.assertEqual(registered.json()["checkFrequency"], "daily")

        # When an agent run logs a check with status ok and zero new items, and a later one fails
        run = agent_build.platform_run(key=key)
        now = timezone.now()
        first_check_at = now - datetime.timedelta(hours=2)
        for body, at in (
            ({"status": "ok", "itemsFound": 0}, first_check_at),
            ({"status": "failed", "error": "502 from the publisher after three retries"}, now),
        ):
            logged = self.client.post(
                f"/api/v1/agent-runs/{run.id}/source-checks",
                data={"sourceName": "Finansinspektionen news", "checkedAt": at.isoformat(), **body},
                content_type="application/json",
                HTTP_X_API_KEY=key.plain_key,
            )
            self.assertEqual(logged.status_code, 204, logged.content)

        # Then the coverage log lists both with time, result and the run
        logged_checks = list(SourceCheck.objects.order_by("checked_at"))
        self.assertEqual([check.status for check in logged_checks], ["ok", "failed"])
        self.assertEqual([check.items_found for check in logged_checks], [0, 0])
        self.assertEqual({check.agent_run_id for check in logged_checks}, {run.id})
        self.assertEqual([check.checked_at for check in logged_checks], [first_check_at, now])

        # And the console's "Source coverage" shows the source as stale after the failure,
        # with the failing check named
        with stub_session(user_principal(permissions={perms.SOURCES_MANAGE}, subject_id=person.id)):
            coverage = self.client.get("/api/v1/sources/coverage", **session)
        self.assertEqual(coverage.status_code, 200, coverage.content)
        row = coverage.json()[0]
        self.assertEqual(row["source"]["name"], "Finansinspektionen news")
        self.assertTrue(row["overdue"])
        self.assertEqual(row["lastStatus"], "failed")
        self.assertEqual(row["lastError"], "502 from the publisher after three retries")

    def test_wat_s2(self) -> None:
        """WAT-S2

        One record per reform carries a timeline with partial dates (WAT-02).
        Operations: `createChange`, `addChangeEvent`, `updateChangeEvent`.
        """
        run, plain = self._run_with_a_key()

        # Given a change registered with a consultation date of 2026-03, an adoption date
        # of 2026-06-15 and in force "Q1 2027"
        registered = self._register(
            plain,
            {
                **_CHANGE,
                "agentRunId": str(run.id),
                "events": [
                    {"label": "Consultation opened", "eventDate": "2026-03-01", "datePrecision": "month", "sortOrder": 1},
                    {"label": "Adopted", "eventDate": "2026-06-15", "datePrecision": "day", "occurred": True, "sortOrder": 2},
                    {"label": "In force", "eventDate": "2027-01-01", "datePrecision": "quarter", "sortOrder": 3},
                ],
            },
        )
        self.assertEqual(registered.status_code, 201, registered.content)

        # Then one regulatory change row exists with three timeline entries, each with its precision
        change = RegulatoryChange.objects.get()
        self.assertEqual(
            [(event.label, event.event_date, event.date_precision) for event in change.events.all()],
            [
                ("Consultation opened", datetime.date(2026, 3, 1), "month"),
                ("Adopted", datetime.date(2026, 6, 15), "day"),
                ("In force", datetime.date(2027, 1, 1), "quarter"),
            ],
        )
        # The screen renders them from these three facts; a date is a plain date with a
        # precision, never a timestamp, so no day is printed that the source did not state.
        self.assertEqual([type(event.event_date) for event in change.events.all()], [datetime.date] * 3)

    def test_wat_s3(self) -> None:
        """WAT-S3

        A known stableKey merges duplicates and returns the existing change (WAT-02, AC-WAT1).
        Operations: `createChange`, `addChangeDocument`.
        """
        run, plain = self._run_with_a_key()

        # Given a change registered with stableKey "eu-dora-rts-2026-01"
        first = self._register(plain, {**_CHANGE, "stableKey": _DORA_RTS, "agentRunId": str(run.id)})
        self.assertEqual(first.status_code, 201, first.content)

        # When an agent posts the same stableKey with a new source page
        again = self._register(
            plain,
            {
                **_CHANGE,
                "stableKey": _DORA_RTS,
                "agentRunId": str(run.id),
                "documents": [{"url": "https://eur-lex.europa.eu/eli/reg_del/2026/1/oj", "isPrimary": True}],
            },
        )

        # Then the response is 200 with the existing change id
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(again.json()["id"], first.json()["id"])

        # And the new page is linked as a duplicate document on that change
        pages = {document.url: document for document in ChangeDocument.objects.all()}
        self.assertTrue(pages["https://eur-lex.europa.eu/eli/reg_del/2026/1/oj"].is_duplicate)

        # And no second change row exists
        self.assertEqual(RegulatoryChange.objects.count(), 1)

    def _confirmer(self) -> tuple[Any, Any]:
        """The independent second agent (D-74): a definition of its own, a key holding the
        review scope and never `changes:write`, and a run of its own open."""
        tenancy.clear_tenant()
        key = agent_build.agent_key(
            agent_row=agent_build.agent(key="library-confirmer"),
            scopes=("agent-runs:write", "library:read", perms.SCOPE_PROPOSALS_REVIEW),
        )
        return key, agent_build.platform_run(key=key)

    def _confirm(self, change_id: str, body: dict[str, Any], headers: dict[str, Any]) -> Any:
        tenancy.clear_tenant()
        return self.client.post(
            f"/api/v1/changes/{change_id}/confirmation", data=body, content_type="application/json", **headers
        )

    def test_wat_s4(self) -> None:
        """WAT-S4

        Types, flags and scope come from vocabularies and stay suggestions until an agent of
        another definition confirms them, and then read machine-confirmed (WAT-03, D-74).
        Operations: `createChange`, `confirmChangeCuration`.
        """
        run, plain = self._run_with_a_key()
        sweeper = run.agent
        banks = self._two_banks()
        officer = factories.member(banks.inside, roles=("compliance_officer",)).user
        reader = sign_in(officer, tenant=banks.inside)

        # Given an agent classifies a change with a type, a flag and a scope term from the vocabularies
        tenancy.clear_tenant()
        registered = self._register(
            plain,
            {
                **_CHANGE,
                "agentRunId": str(run.id),
                "flags": ["advice_perimeter"],
                "termIds": [str(watch_build.term(_SECURITIES).id)],
            },
        )
        self.assertEqual(registered.status_code, 201, registered.content)
        change_id = registered.json()["id"]
        _drain()

        # Then each is stored as a key, marked suggested and naming the agent that suggested it,
        # and the change row a bank reads marks each as a suggestion
        def facts() -> list[dict[str, Any]]:
            feed = self.client.get("/api/v1/changes", {"footprint": "all"}, **reader)
            row = next(item for item in feed.json()["items"] if item["id"] == change_id)
            return [row["changeType"], *row["flags"], *row["terms"]]

        suggested = facts()
        self.assertEqual([fact["ref"]["key"] for fact in suggested], ["adopted", "advice_perimeter", "securities"])
        for fact in suggested:
            self.assertEqual(
                (fact["suggested"], fact["confirmedOrigin"], fact["suggestedByAgent"]["key"], fact["confirmedByAgent"]),
                (True, None, sweeper.key, None),
            )

        body = {
            "changeType": True,
            "flags": ["advice_perimeter"],
            "termIds": [str(watch_build.term(_SECURITIES).id)],
        }
        confirmer, review = self._confirmer()
        decided = {**body, "decision": _DECISION, "agentRunId": str(review.id)}

        # And the agent that suggested them cannot confirm them, through any key of its own
        sibling = agent_build.agent_key(agent_row=sweeper, scopes=("agent-runs:write", perms.SCOPE_PROPOSALS_REVIEW))
        own = self._confirm(
            change_id,
            {**decided, "agentRunId": str(agent_build.platform_run(key=sibling).id)},
            {"HTTP_X_API_KEY": sibling.plain_key},
        )
        self.assertEqual((own.status_code, own.json()["code"]), (409, "same_agent"))

        # And a bank's own compliance officer cannot confirm them: a change's type, flag and
        # scope are library facts
        banked = self._confirm(change_id, body, sign_in(officer, tenant=banks.inside))
        self.assertEqual((banked.status_code, banked.json()["requiredPermission"]), (403, perms.PROPOSALS_REVIEW))

        # When an agent of another definition confirms them, with the model call behind its
        # decision, inside its own open run
        confirmed = self._confirm(change_id, decided, {"HTTP_X_API_KEY": confirmer.plain_key})
        self.assertEqual(confirmed.status_code, 200, confirmed.content)

        # Then suggested becomes false, and each reads machine-confirmed naming the suggesting
        # and the confirming agent, never a person's verification, for every bank
        for fact in facts():
            self.assertEqual(
                (fact["suggested"], fact["confirmedOrigin"], fact["suggestedByAgent"]["key"], fact["confirmedByAgent"]["key"]),
                (False, "agent", sweeper.key, "library-confirmer"),
            )
        page = self.client.get(f"/api/v1/changes/{change_id}", **reader).json()
        self.assertEqual(page["changeTypeFact"]["confirmedOrigin"], "agent")
        self.assertEqual(page["changeTypeFact"]["confirmedByAgent"]["key"], "library-confirmer")

        # And the audit event records which agent confirmed, and its decision is in the AI
        # output log under agent_review, against its run
        tenancy.clear_tenant()
        audit = AuditEvent.objects.get(action="regulatory_change.curation_confirmed")
        self.assertEqual((audit.actor_type, audit.actor_label), ("agent", "library-confirmer"))
        self.assertEqual(audit.after["confirmedOrigin"], "agent")
        self.assertIsNone(audit.tenant_id)
        logged = AiGeneration.objects.get(purpose="agent_review", subject_id=change_id)
        self.assertEqual(logged.agent_run_id, review.id)
        self.assertTrue(logged.model_metadata_reported_by_agent)

    def test_wat_s5(self) -> None:
        """WAT-S5

        An unknown key answers unknown_key with the valid keys (WAT-03, AC-WAT2).
        Operations: `updateChange`.
        """
        watch_build.seed_watch_reference()
        change = watch_build.change_with_timeline()
        valid = sorted(ChangeType.objects.filter(active=True).values_list("key", flat=True))
        self.assertIn("adopted", valid, "the change type vocabulary is seeded before an agent reads it")
        typo = "ammendment"
        self.assertNotIn(typo, valid)

        with stub_api_key(agent_principal(scopes={perms.SCOPE_CHANGES_WRITE})):
            response = self.client.patch(
                f"/api/v1/changes/{change.id}",
                data={"changeType": typo, "summary": "A summary that must not be stored either."},
                content_type="application/json",
                HTTP_X_API_KEY=API_KEY_FOR_TESTS,
            )

        self.assertEqual(response.status_code, 422)
        problem = response.json()
        self.assertEqual(problem["code"], "unknown_key")
        self.assertIn(typo, problem["detail"])
        self.assertEqual(sorted(problem["validKeys"]), valid, "the refusal lists the keys the agent may send")

        change.refresh_from_db()
        self.assertEqual(change.change_type.key, "adopted", "nothing is stored on a refusal")
        self.assertNotIn("must not be stored", change.summary)

    def test_wat_s6(self) -> None:
        """WAT-S6

        Links to affected obligations carry a confidence, and the library and the bank
        decide separately (WAT-04, D-74).
        Operations: `replaceChangeObligations`, `confirmChangeCuration`,
        `acceptCaseObligationLink`, `removeCaseObligationLink`.

        The library's half is D-74's: an agent of another definition confirms a link for
        every bank, and it reads machine-confirmed. The bank's half is PRD WAT-04's person
        per bank, on that bank's own case, which the library's confirmation never replaces.
        """
        run, plain = self._run_with_a_key()
        banks = self._two_banks()
        officer = factories.member(
            banks.inside, roles=("compliance_officer",), user_row=factories.user(name="Sara Lind")
        ).user
        other = factories.member(banks.outside, roles=("compliance_officer",)).user
        instrument = library_build.instrument(key="fffs-2017-2", regime=_SECURITIES)
        research = library_build.obligation(
            instrument, key="fffs-2017-2-11-4", titles={"en": "Assess the quality of research paid for"}
        )
        reporting = library_build.obligation(
            instrument, key="fffs-2017-2-12-1", titles={"en": "Report transactions by the next working day"}
        )

        # Given an agent linked a change to two obligations with confidence 0.9 and 0.4.
        # The key is the platform's, so the connection must be out of a bank's zone: the
        # member factories above each left one activated (playbook 14).
        tenancy.clear_tenant()
        registered = self._register(
            plain,
            {
                **_CHANGE,
                "agentRunId": str(run.id),
                "termIds": [str(watch_build.term(_SECURITIES).id)],
                "obligationLinks": [
                    {"obligationId": str(research.id), "confidence": 0.9},
                    {"obligationId": str(reporting.id), "confidence": 0.4},
                ],
            },
        )
        self.assertEqual(registered.status_code, 201, registered.content)
        change_id = registered.json()["id"]
        _drain()

        # Then the change screen shows both with the confidence, as suggestions
        read = self.client.get(f"/api/v1/changes/{change_id}", **sign_in(officer, tenant=banks.inside))
        self.assertEqual(read.status_code, 200, read.content)
        suggested = {link["obligationId"]: link for link in read.json()["obligations"]}
        self.assertEqual(
            {key: (value["confidence"], value["confirmed"]) for key, value in suggested.items()},
            {str(research.id): (0.9, False), str(reporting.id): (0.4, False)},
        )

        # When an agent of another definition confirms the first for the shared library
        confirmer, review = self._confirmer()
        confirmed = self._confirm(
            change_id,
            {"obligationIds": [str(research.id)], "decision": _DECISION, "agentRunId": str(review.id)},
            {"HTTP_X_API_KEY": confirmer.plain_key},
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.content)

        # Then that link reads machine-confirmed for every bank, naming both agents, and the
        # audit event records which agent confirmed
        for person, bank in ((officer, banks.inside), (other, banks.outside)):
            links = {
                link["obligationId"]: link
                for link in self.client.get(f"/api/v1/changes/{change_id}", **sign_in(person, tenant=bank)).json()["obligations"]
            }
            first, second = links[str(research.id)], links[str(reporting.id)]
            self.assertEqual(
                (first["confirmed"], first["confirmedOrigin"], first["suggestedByAgent"]["key"], first["confirmedByAgent"]["key"]),
                (True, "agent", run.agent.key, "library-confirmer"),
            )
            self.assertEqual((second["confirmed"], second["confirmedOrigin"]), (False, None))
        tenancy.clear_tenant()
        audit = AuditEvent.objects.get(action="regulatory_change.curation_confirmed")
        self.assertEqual((audit.actor_type, audit.actor_label), ("agent", "library-confirmer"))
        self.assertEqual(audit.after["confirmed"], [f"obligation:{research.id}"])

        # When a compliance officer accepts the first and removes the second on its own case
        accepted = self.client.post(
            f"/api/v1/changes/{change_id}/case/obligation-links",
            data={"obligationId": str(research.id)},
            content_type="application/json",
            **sign_in(officer, tenant=banks.inside),
        )
        self.assertEqual(accepted.status_code, 201, accepted.content)
        removed = self.client.delete(
            f"/api/v1/changes/{change_id}/case/obligation-links/{reporting.id}",
            **sign_in(officer, tenant=banks.inside),
        )
        self.assertEqual(removed.status_code, 200, removed.content)

        # Then both decisions are stored on that bank's case and audited
        with transaction.atomic():
            tenancy.activate(banks.inside.id)
            decisions = {row.obligation_id: row.decision for row in CaseObligationLink.objects.all()}
            self.assertEqual(decisions, {research.id: "accepted", reporting.id: "removed"})
            self.assertEqual(AuditEvent.objects.filter(action="case.obligation_link_decided").count(), 2)

        # And the obligation shows "1 open change"
        counted = self.client.get(
            f"/api/v1/obligations/{research.id}/changes", **sign_in(officer, tenant=banks.inside)
        )
        self.assertEqual(counted.status_code, 200, counted.content)
        self.assertEqual(counted.json()["openCount"], 1)

        # And no library row changed: the second link is still there and still a suggestion,
        # and the first is as the library confirmed it, for everyone
        with transaction.atomic():
            tenancy.clear_tenant()
            links = {row.obligation_id: watch_build.is_a_suggestion(row) for row in ChangeObligation.objects.all()}
            self.assertEqual(links, {research.id: False, reporting.id: True})
        theirs = self.client.get(f"/api/v1/changes/{change_id}", **sign_in(other, tenant=banks.outside))
        self.assertEqual(
            {link["obligationId"]: link["confirmed"] for link in theirs.json()["obligations"]},
            {str(research.id): True, str(reporting.id): False},
            "another bank still sees both, as the library holds them, and has decided neither",
        )
        self.assertEqual(theirs.json()["case"]["obligationDecisions"], [])

    def test_wat_s7(self) -> None:
        """WAT-S7

        The "So what?" is AI-drafted until a person confirms or rewrites it per tenant (WAT-05).
        Operations: `saveSoWhat`, `confirmSoWhat`.

        The draft is the agent's, filed with the change it read and recorded in the AI
        output log from what that agent reported (D-66). Each bank confirms its own copy;
        the library's log row is a platform fact and no bank moves it (ruling I).
        """
        run, plain = self._run_with_a_key()
        banks = self._two_banks()
        officer = factories.member(
            banks.inside, roles=("compliance_officer",), user_row=factories.user(name="Sara Lind")
        ).user
        other = factories.member(banks.outside, roles=("compliance_officer",)).user

        # Given a change with a drafted "So what?" the run filed with it. The key is the
        # platform's, so the connection must be out of a bank's zone first.
        tenancy.clear_tenant()
        registered = self._register(
            plain,
            {
                **_CHANGE,
                "agentRunId": str(run.id),
                "termIds": [str(watch_build.term(_SECURITIES).id)],
                "soWhat": {
                    "text": _DRAFT,
                    "model": "claude-opus-5",
                    "modelVersion": "2026-05-01",
                    "citations": [{"label": "Finansinspektionen", "url": "https://www.fi.se/"}],
                },
            },
        )
        self.assertEqual(registered.status_code, 201, registered.content)
        change_id = registered.json()["id"]
        _drain()

        # Then an ai_generation row carries model, version and purpose
        with transaction.atomic():
            tenancy.clear_tenant()
            logged = AiGeneration.objects.get(subject_id=change_id)
            self.assertEqual(
                (logged.purpose, logged.model, logged.model_version, logged.status),
                ("so_what", "claude-opus-5", "2026-05-01", "draft"),
            )
            self.assertTrue(
                logged.model_metadata_reported_by_agent, "the agent reported it; bleqq did not measure it"
            )
            before = list(AiGeneration.objects.values())

        # And each bank's copy is labelled an AI draft
        for bank, person in ((banks.inside, officer), (banks.outside, other)):
            with self.subTest(bank=bank.slug):
                read = self.client.get(f"/api/v1/changes/{change_id}", **sign_in(person, tenant=bank))
                self.assertEqual(read.json()["case"]["soWhatText"], _DRAFT)
                self.assertFalse(read.json()["case"]["soWhatConfirmed"])

        # When the officer rewrites it
        saved = self.client.put(
            f"/api/v1/changes/{change_id}/so-what",
            data={"text": _OUR_WORDS},
            content_type="application/json",
            **sign_in(officer, tenant=banks.inside),
        )
        self.assertEqual(saved.status_code, 200, saved.content)

        # Then this bank's copy is confirmed with the person and the time
        body = saved.json()
        self.assertEqual((body["text"], body["confirmed"], body["isAiDraft"]), (_OUR_WORDS, True, False))
        self.assertEqual(body["confirmedByName"], "Sara Lind")
        self.assertIsNotNone(body["confirmedAt"])

        # And another tenant's copy is still the draft
        theirs = self.client.get(f"/api/v1/changes/{change_id}", **sign_in(other, tenant=banks.outside))
        self.assertEqual(theirs.json()["case"]["soWhatText"], _DRAFT)
        self.assertFalse(theirs.json()["case"]["soWhatConfirmed"])

        # Confirming as it stands works the same way, and neither act moves the library's row
        confirmed = self.client.post(
            f"/api/v1/changes/{change_id}/so-what/confirm",
            data={},
            content_type="application/json",
            **sign_in(other, tenant=banks.outside),
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        self.assertEqual(confirmed.json()["text"], _DRAFT, "confirming keeps the model's words")
        with transaction.atomic():
            tenancy.clear_tenant()
            self.assertEqual(list(AiGeneration.objects.values()), before, "the shared log row is nobody's to move")

    @skip("pending: WAT-S8 (WAT-06, chunk 13)")
    def test_wat_s8(self) -> None:
        """WAT-S8

        A tenant requests a source and private sources stay private (WAT-06).
        """

    @skip("pending: WAT-S10 (WAT-07, chunk 5)")
    def test_wat_s10(self) -> None:
        """WAT-S10

        A new edition of a standard is one change, and only tenants that follow it see it (WAT-02, WAT-07, CAS-01).
        """

    @skip("pending: WAT-S11 (WAT-07, chunk 5)")
    def test_wat_s11(self) -> None:
        """WAT-S11

        Every change carries a regime, a standard term needs a standards body, and a publisher's page keeps no snapshot (WAT-01, WAT-03, WAT-07).
        """

    @skip("pending: WAT-S12 (WAT-01, AUD-03, chunk 5)")
    def test_wat_s12(self) -> None:
        """WAT-S12

        A run re-checks the library records of the sources it checked and proposes the correction (WAT-01, AUD-03).
        """
