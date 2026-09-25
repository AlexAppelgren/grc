""""This looks wrong": the report writer (chunk 3, INV-06, AUD-03).

A reader who spots a mistake in a public fact files a report instead of editing the
library. What the reader wrote is tenant content, so these tests pin where it may and may
not appear: in the row, and nowhere else. The tenant comes from the caller's principal,
never from the body, and the mixed policy on problem_report lets cw_app insert a row for
the tenant the transaction activated and refuses one for any other.

The routes over this writer are chunk3-rest-T11b (INV-S7).
"""

from __future__ import annotations

import uuid
from typing import get_type_hints

from django.core.exceptions import ValidationError
from django.db import DEFAULT_DB_ALIAS, ProgrammingError, transaction
from django.test import TransactionTestCase

from apps.library.models import ProblemReport, SubjectType
from apps.library.reports import create_report
from apps.library.seeds import seed_languages
from apps.shared import factories, tenancy
from apps.shared.audit import Actor, ActorType
from apps.shared.models import AuditEvent, OutboxEvent
from apps.shared.testing import ScenarioTestCase

TEXT = "The retention period says ten years, but the source says five."
SUBJECT = uuid.UUID("11111111-1111-4111-8111-111111111111")


class ReportWriter(ScenarioTestCase):
    def setUp(self) -> None:
        seed_languages()
        self.tenant = factories.tenant(slug="bank")
        self.activate(self.tenant)
        self.reader = factories.member(self.tenant, roles=("reader",)).user
        self.activate(self.tenant)
        self.actor = Actor(kind=ActorType.USER, id=self.reader.id, label=self.reader.name)

    def _create(self, **fields: object) -> ProblemReport:  # compliance: allow-kwargs test helper forwarding one call's fields
        defaults: dict[str, object] = {
            "subject_type": SubjectType.OBLIGATION,
            "subject_id": SUBJECT,
            "subject_title": "fffs-2017-2/9/6",
            "tenant_id": self.tenant.id,
            "reporter": self.reader,
            "actor": self.actor,
            "description": TEXT,
        }
        defaults.update(fields)
        with transaction.atomic():
            tenancy.activate(self.tenant.id)
            return create_report(**defaults)  # type: ignore[arg-type]

    # --- what is written ----------------------------------------------------------------
    def test_the_report_holds_the_text_the_subject_and_what_was_on_screen(self) -> None:
        report = self._create(version_number=2, language="sv")
        self.activate(self.tenant)
        row = ProblemReport.objects.get(id=report.id)
        self.assertEqual(row.text, TEXT)
        self.assertEqual(row.subject_type, SubjectType.OBLIGATION.value)
        self.assertEqual(row.subject_id, SUBJECT)
        self.assertEqual((row.version_number, row.language_id), (2, "sv"))
        self.assertEqual(row.status, "open")

    def test_the_tenant_and_the_reporter_come_from_the_caller(self) -> None:
        """A body cannot file a report for another bank: the writer takes no tenant input."""
        report = self._create()
        self.activate(self.tenant)
        row = ProblemReport.objects.get(id=report.id)
        self.assertEqual(row.tenant_id, self.tenant.id)
        self.assertEqual(row.reporter_id, self.reader.id)

    def test_every_report_carries_a_bank(self) -> None:
        """A report with no tenant would be a library row under the mixed policy, readable
        by every bank, which is the opposite of what Alex decided on 2026-09-19
        (OWNER_RECOMMENDATIONS item 3). The writer takes a tenant, never an absence, so
        there is no call that writes one; the route cannot either, because
        `caller_tenant()` answers 404 to a principal in no bank."""
        self.assertIs(get_type_hints(create_report)["tenant_id"], uuid.UUID)
        self._create()
        self.activate(self.tenant)
        self.assertFalse(ProblemReport.objects.filter(tenant__isnull=True).exists())

    # --- the text stays in the row ------------------------------------------------------
    def test_neither_the_audit_summary_nor_the_outbox_payload_holds_the_text(self) -> None:
        report = self._create(version_number=2, language="sv")
        self.activate(self.tenant)
        event = AuditEvent.objects.get(action="library.problem_reported")
        outbox = OutboxEvent.objects.get(audit_event=event)
        for haystack in (event.summary, event.subject_title, str(event.before), str(event.after), str(outbox.payload)):
            self.assertNotIn(TEXT, haystack)
            self.assertNotIn("retention period", haystack)
        self.assertEqual(event.tenant_id, self.tenant.id)
        self.assertEqual(event.subject_id, SUBJECT)
        self.assertEqual(event.after["reportId"], str(report.id))
        self.assertEqual((event.after["versionNumber"], event.after["language"]), (2, "sv"))

    def test_the_audit_and_outbox_rows_share_the_report_s_transaction(self) -> None:
        """Nothing is left behind when the write fails after the row: record() runs in the
        caller's transaction, so all three roll back together."""
        with self.assertRaises(RuntimeError), transaction.atomic():
            tenancy.activate(self.tenant.id)
            create_report(
                subject_type=SubjectType.OBLIGATION,
                subject_id=SUBJECT,
                subject_title="fffs-2017-2/9/6",
                tenant_id=self.tenant.id,
                reporter=self.reader,
                actor=self.actor,
                description=TEXT,
            )
            raise RuntimeError("the request failed after the report was written")
        self.activate(self.tenant)
        self.assertFalse(ProblemReport.objects.exists())
        self.assertFalse(AuditEvent.objects.filter(action="library.problem_reported").exists())
        self.assertFalse(OutboxEvent.objects.filter(topic="library.problem_reported").exists())

    # --- what is refused ----------------------------------------------------------------
    def test_a_description_of_nothing_is_refused(self) -> None:
        for description in ("", "   ", "\n\t"):
            with self.subTest(description=description), self.assertRaises(ValidationError) as caught:
                self._create(description=description)
            self.assertEqual(caught.exception.code, "description_required")
        self.activate(self.tenant)
        self.assertFalse(ProblemReport.objects.exists())

    def test_a_language_that_is_not_a_content_language_is_refused(self) -> None:
        with self.assertRaises(ValidationError) as caught:
            self._create(language="xx")
        self.assertEqual(caught.exception.code, "unknown_key")

    def test_a_version_number_below_one_is_refused(self) -> None:
        for version_number in (0, -3):
            with self.subTest(version_number=version_number), self.assertRaises(ValidationError) as caught:
                self._create(version_number=version_number)
            self.assertEqual(caught.exception.code, "invalid_value")

    def test_the_description_is_trimmed_but_kept_whole(self) -> None:
        report = self._create(description=f"  {TEXT}  ")
        self.activate(self.tenant)
        self.assertEqual(ProblemReport.objects.get(id=report.id).text, TEXT)


class ReportRowLevelSecurity(TransactionTestCase):
    """The mixed policy on problem_report, proven on the cw_app connection: the row the
    writer inserts is admitted for the activated tenant and refused for another. Committed
    rows, so the proof runs on the application role's own connection."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        with transaction.atomic():
            seed_languages()
        self.tenant = factories.tenant(slug="bank")
        self.other = factories.tenant(slug="other-bank")
        self.reader = factories.member(self.tenant, roles=("reader",)).user

    def test_cw_app_inserts_the_report_of_the_activated_tenant(self) -> None:
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant.id, using="app")
            ProblemReport.objects.using("app").create(
                tenant_id=self.tenant.id,
                reporter=self.reader,
                subject_type=SubjectType.OBLIGATION.value,
                subject_id=SUBJECT,
                text=TEXT,
                version_number=2,
                language_id="sv",
            )
            self.assertEqual(ProblemReport.objects.using("app").count(), 1)

    def test_cw_app_cannot_file_a_report_for_another_tenant(self) -> None:
        with self.assertRaises(ProgrammingError), transaction.atomic(using="app"):
            tenancy.activate(self.tenant.id, using="app")
            ProblemReport.objects.using("app").create(
                tenant_id=self.other.id,
                reporter=self.reader,
                subject_type=SubjectType.OBLIGATION.value,
                subject_id=SUBJECT,
                text=TEXT,
            )
