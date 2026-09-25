"""Scenario stubs for the reports app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Prefixes hosted: REP.
"""

from unittest import mock, skip

from apps.reports import exporters
from apps.reports.models import ExportJob, ExportKind, JobStatus
from apps.shared import factories, tenancy
from apps.shared.testing import ScenarioTestCase, sign_in


class ReportsScenarioTests(ScenarioTestCase):
    """Scenario tests for apps.reports, one method per @integration scenario."""

    @skip("pending: REP-S1")
    def test_rep_s1(self) -> None:
        """REP-S1

        The dashboard shows the officer's figures from keys and categories (REP-01).
        """

    @skip("pending: REP-S2")
    def test_rep_s2(self) -> None:
        """REP-S2

        The committee pack and the exports are produced by jobs (REP-02).
        """

    def test_rep_s3(self) -> None:
        """REP-S3

        An export needs step-up and never runs inside the request (REP-02). `createExport`
        answers 403 without a fresh assertion and 202 with one; the worker builds the file
        after the request's transaction commits.
        """
        tenant = factories.tenant()
        person = factories.member(tenant, roles=("approver",)).user
        body = {"kind": "cases", "format": "json"}
        builder = mock.Mock(return_value=b"[]")
        with mock.patch.dict(exporters._REGISTRY, {ExportKind.CASES: exporters.Exporter(frozenset({"json"}), builder)}):
            refused = self.client.post(
                "/api/v1/exports", data=body, content_type="application/json", **sign_in(person, tenant=tenant)
            )
            self.assertEqual(refused.status_code, 403)
            self.assertEqual(refused.json()["code"], "step_up_required")

            headers = sign_in(person, tenant=tenant, step_up=True)
            with self.captureOnCommitCallbacks(execute=False) as queued:
                accepted = self.client.post("/api/v1/exports", data=body, content_type="application/json", **headers)
            self.assertEqual(accepted.status_code, 202)
            job_id = accepted.json()["id"]
            builder.assert_not_called()

            for hand_off in queued:
                hand_off()
            builder.assert_called_once()
        tenancy.activate(tenant.id)
        job = ExportJob.objects.get(pk=job_id)
        self.assertEqual(job.status, JobStatus.SUCCEEDED.value)
        self.assertIsNotNone(job.storage_key)

    @skip("pending: REP-S4")
    def test_rep_s4(self) -> None:
        """REP-S4

        A spreadsheet register imports with a dry run and a mapping asked once per value (REP-03).
        """

    @skip("pending: REP-S5")
    def test_rep_s5(self) -> None:
        """REP-S5

        A tenant can leave with everything and have deletion verified (REP-04).
        """

    @skip("pending: REP-S6 (REP-02, REG-08, chunk 12)")
    def test_rep_s6(self) -> None:
        """REP-S6

        The Statement of Applicability exports as a dated inventory export (REP-02, REG-08).
        """

    @skip("pending: REP-S7 (REP-04, chunk 12)")
    def test_rep_s7(self) -> None:
        """REP-S7

        Tenant exit needs two different people, each with a passkey (REP-04).
        """

    @skip("pending: REP-S8 (REP-04, chunk 12)")
    def test_rep_s8(self) -> None:
        """REP-S8

        Execution refuses until its conditions are met, and deletes nothing through the app role (REP-04).
        """
