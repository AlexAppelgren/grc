"""Scenario stubs for the watch app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: WAT.
"""

from unittest import skip

from django.test import TestCase

from apps.shared import permissions as perms
from apps.shared.testing import API_KEY_FOR_TESTS, agent_principal, stub_api_key
from apps.taxonomy.models import ChangeType
from apps.watch import testing as watch_build


class WatchScenarioTests(TestCase):
    """Scenario tests for apps.watch, one method per @integration scenario."""

    @skip("pending: WAT-S1")
    def test_wat_s1(self) -> None:
        """WAT-S1

        The source registry and coverage log show what was checked and with what result (WAT-01).
        Operations: `createSource`, `updateSource`, `recordSourceCheck`.
        """

    @skip("pending: WAT-S2")
    def test_wat_s2(self) -> None:
        """WAT-S2

        One record per reform carries a timeline with partial dates (WAT-02).
        Operations: `createChange`, `addChangeEvent`, `updateChangeEvent`.
        """

    @skip("pending: WAT-S3")
    def test_wat_s3(self) -> None:
        """WAT-S3

        A known stableKey merges duplicates and returns the existing change (WAT-02, AC-WAT1).
        Operations: `createChange`, `addChangeDocument`.
        """

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
