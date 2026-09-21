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

from django.test import TestCase
from django.utils import timezone

from apps.agents import testing as agent_build
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.testing import (
    API_KEY_FOR_TESTS,
    SESSION_TOKEN_FOR_TESTS,
    agent_principal,
    stub_api_key,
    stub_session,
    user_principal,
)
from apps.taxonomy.models import ChangeType
from apps.watch import testing as watch_build
from apps.watch.models import ChangeDocument, RegulatoryChange, SourceCheck

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


class WatchScenarioTests(TestCase):
    """Scenario tests for apps.watch, one method per @integration scenario."""

    def _run_with_a_key(self) -> tuple[Any, str]:
        """A platform key with a run open, and the value it sends as `X-API-Key`."""
        watch_build.seed_watch_reference()
        tenancy.clear_tenant()
        key = agent_build.agent_key()
        return agent_build.platform_run(key=key), key.plain_key

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

    @skip("pending: WAT-S4")
    def test_wat_s4(self) -> None:
        """WAT-S4

        Types, flags and scope come from vocabularies and stay suggestions until confirmed (WAT-03).
        """

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

    @skip("pending: WAT-S6")
    def test_wat_s6(self) -> None:
        """WAT-S6

        Links to affected obligations carry a confidence, and the library and the bank
        decide separately (WAT-04).
        Operations: `replaceChangeObligations`, `acceptCaseObligationLink`,
        `removeCaseObligationLink`.
        """

    @skip("pending: WAT-S7")
    def test_wat_s7(self) -> None:
        """WAT-S7

        The "So what?" is AI-drafted until a person confirms or rewrites it per tenant (WAT-05).
        Operations: `saveSoWhat`, `confirmSoWhat`.
        """

    @skip("pending: WAT-S8")
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
