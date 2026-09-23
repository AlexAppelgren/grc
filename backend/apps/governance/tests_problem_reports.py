"""A bank reads and closes its own problem reports (AUD-03, PRO-03, INV-06, chunk4-T18).

`GET /problem-reports` and `PATCH /problem-reports/{report_id}`, driven over real sessions.
What is held in place here:

- **The visibility rule.** A holder of `proposals.create` lists every report of their own
  bank; every other member lists the reports they filed. Another bank's report is never
  listed and answers 404 to a close, because row-level security has already hidden it.
- **The close.** `answered`, `fixed` or `rejected`, with a note; the reporter closes their
  own, a `proposals.create` holder any of the bank's, anyone else is refused naming that
  permission, and a second close answers 409 `already_closed`. Only the four closing
  columns are written.
- **The words stay in the row.** The report's text and the closing note reach no audit
  row, no outbox payload and no log line.
- **Nobody outside the bank.** Platform sessions hold no `problems.report` and are refused
  with it named; an agent's key is not a session.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from apps.library import testing as build
from apps.library.models import ProblemReport, ReportStatus
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, permissions as perms
from apps.shared.models import AuditEvent, OutboxEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions

V1 = "/api/v1"
REPORTS = f"{V1}/problem-reports"
WORDS = "The retention line says five years, but FFFS 2017:2 9 kap. 6 § says ten."
NOTE = "Checked against the source: the library is right, the screen shows the old version."


class ProblemReportsTestCase(ScenarioTestCase):
    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        self.instrument = build.instrument(key="fffs-2017-2", short_name="FFFS 2017:2", regime="regime:securities")
        self.obligation = build.obligation(
            self.instrument, key="fffs-2017-2-9-6", titles={"en": "Keep records for ten years"}, ref_label="9 kap. 6 §"
        )
        self.tenant = factories.tenant(slug="bank-a")
        self.other_bank = factories.tenant(slug="bank-b")
        self.officer = factories.member_user(self.tenant, roles=("compliance_officer",))
        self.reader = factories.member_user(self.tenant, roles=("reader",))
        self.colleague = factories.member_user(self.tenant, roles=("reader",))
        self.other_officer = factories.member_user(self.other_bank, roles=("compliance_officer",))

    def file(self, user: Any, *, on: str = "obligation", words: str = WORDS, tenant: Any = None) -> str:
        subject = self.obligation if on == "obligation" else self.instrument
        answer = self.client.post(
            f"{V1}/{on}s/{subject.id}/problem-reports",
            data={"description": words, "versionNumber": 1, "language": "en"},
            content_type="application/json",
            **sign_in(user, tenant=tenant or self.tenant),
        )
        self.assertEqual(answer.status_code, 201, answer.content)
        return str(answer.json()["id"])

    def listing(self, user: Any, query: str = "", *, tenant: Any = None) -> Any:
        return self.client.get(f"{REPORTS}{query}", **sign_in(user, tenant=tenant or self.tenant))

    def ids(self, user: Any, query: str = "", *, tenant: Any = None) -> list[str]:
        answer = self.listing(user, query, tenant=tenant)
        self.assertEqual(answer.status_code, 200, answer.content)
        return [row["id"] for row in answer.json()["items"]]

    def close(self, user: Any, report_id: str, body: dict[str, Any] | None = None, *, tenant: Any = None) -> Any:
        return self.client.patch(
            f"{REPORTS}/{report_id}",
            data=body if body is not None else {"status": "fixed", "resolutionNote": NOTE},
            content_type="application/json",
            **sign_in(user, tenant=tenant or self.tenant),
        )

    def row(self, report_id: str) -> ProblemReport:
        self.activate(self.tenant)
        return ProblemReport.objects.get(id=report_id)


class WhoReadsWhich(ProblemReportsTestCase):
    def test_an_officer_lists_every_report_of_the_bank_and_a_member_only_their_own(self) -> None:
        mine = self.file(self.reader)
        theirs = self.file(self.colleague, on="instrument")
        self.assertEqual(sorted(self.ids(self.officer)), sorted([mine, theirs]))
        self.assertEqual(self.ids(self.reader), [mine])
        self.assertEqual(self.ids(self.colleague), [theirs])

    def test_a_row_says_what_was_reported_on_what_by_whom(self) -> None:
        report_id = self.file(self.reader)
        body = self.listing(self.officer).json()
        self.assertEqual(body["total"], 1)
        row = body["items"][0]
        self.assertEqual(row["id"], report_id)
        self.assertEqual((row["subjectType"], row["subjectId"]), ("obligation", str(self.obligation.id)))
        self.assertEqual(row["subjectTitle"], "Keep records for ten years")
        self.assertEqual(row["subjectReference"], "FFFS 2017:2, 9 kap. 6 §")
        self.assertEqual(row["description"], WORDS)
        self.assertEqual((row["versionNumber"], row["language"]), (1, "en"))
        self.assertEqual(row["reporter"], {"id": str(self.reader.id), "name": self.reader.name})
        self.assertEqual(row["status"], "open")
        self.assertIsNone(row["closedBy"])
        self.assertIsNone(row["closedAt"])
        self.assertIsNone(row["resolutionNote"])
        self.assertIn("createdAt", row)

    def test_an_instrument_report_names_the_instrument(self) -> None:
        self.file(self.reader, on="instrument")
        row = self.listing(self.reader).json()["items"][0]
        self.assertEqual((row["subjectType"], row["subjectId"]), ("instrument", str(self.instrument.id)))
        self.assertEqual(row["subjectTitle"], "FFFS 2017:2")
        self.assertEqual(row["subjectReference"], self.instrument.official_ref)

    def test_another_bank_lists_nothing_and_cannot_close_it(self) -> None:
        report_id = self.file(self.reader)
        self.assertEqual(self.ids(self.other_officer, tenant=self.other_bank), [])
        refused = self.close(self.other_officer, report_id, tenant=self.other_bank)
        self.assertEqual(refused.status_code, 404, refused.content)
        self.assertEqual(refused.json()["code"], "not_found")
        self.assertEqual(self.row(report_id).status, ReportStatus.OPEN.value)

    def test_an_unknown_report_is_not_found(self) -> None:
        refused = self.close(self.officer, str(uuid.uuid4()))
        self.assertEqual(refused.status_code, 404, refused.content)

    def test_filters_by_status_and_subject(self) -> None:
        on_obligation = self.file(self.reader)
        on_instrument = self.file(self.reader, on="instrument")
        self.assertEqual(self.close(self.officer, on_instrument).status_code, 200)
        self.assertEqual(self.ids(self.officer, "?status=open"), [on_obligation])
        self.assertEqual(self.ids(self.officer, "?status=fixed"), [on_instrument])
        self.assertEqual(self.ids(self.officer, "?subjectType=instrument"), [on_instrument])
        self.assertEqual(self.ids(self.officer, f"?subjectId={self.obligation.id}"), [on_obligation])
        self.assertEqual(self.ids(self.officer, "?status=nonsense"), [])

    def test_newest_first_in_pages_of_at_most_a_hundred(self) -> None:
        first = self.file(self.reader)
        second = self.file(self.reader)
        page = self.listing(self.officer, "?limit=1").json()
        self.assertEqual((page["total"], [row["id"] for row in page["items"]]), (2, [second]))
        self.assertEqual(self.ids(self.officer, "?limit=1&offset=1"), [first])
        self.assertEqual(self.listing(self.officer, "?limit=101").status_code, 422)

    def test_platform_sessions_and_keys_are_refused(self) -> None:
        report_id = self.file(self.reader)
        for role in ("library_editor", "platform_admin"):
            platform = sign_in(factories.platform_user(roles=(role,)))
            for answer in (
                self.client.get(REPORTS, **platform),
                self.client.patch(
                    f"{REPORTS}/{report_id}",
                    data={"status": "fixed", "resolutionNote": NOTE},
                    content_type="application/json",
                    **platform,
                ),
            ):
                with self.subTest(role=role, method=answer.request["REQUEST_METHOD"]):
                    self.assertEqual(answer.status_code, 403, answer.content)
                    self.assertEqual(answer.json()["requiredPermission"], perms.PROBLEMS_REPORT)
        key = factories.api_key(self.tenant, scopes=tuple(sorted(perms.ALL_SCOPES)))
        self.assertEqual(self.client.get(REPORTS, HTTP_X_API_KEY=key.plain_key).status_code, 401)
        closing = self.client.patch(
            f"{REPORTS}/{report_id}",
            data={"status": "fixed", "resolutionNote": NOTE},
            content_type="application/json",
            HTTP_X_API_KEY=key.plain_key,
        )
        self.assertEqual(closing.status_code, 401)
        self.assertEqual(self.row(report_id).status, ReportStatus.OPEN.value)


class Closing(ProblemReportsTestCase):
    def test_the_reporter_closes_their_own_with_a_note(self) -> None:
        report_id = self.file(self.reader)
        before = self.row(report_id)
        answer = self.close(self.reader, report_id, {"status": "answered", "resolutionNote": f"  {NOTE}  "})
        self.assertEqual(answer.status_code, 200, answer.content)
        body = answer.json()
        self.assertEqual((body["id"], body["status"], body["resolutionNote"]), (report_id, "answered", NOTE))
        self.assertEqual(body["closedBy"], {"id": str(self.reader.id), "name": self.reader.name})
        self.assertIsNotNone(body["closedAt"])
        after = self.row(report_id)
        self.assertEqual((after.status, after.resolution_note, after.closed_by_id), ("answered", NOTE, self.reader.id))
        self.assertIsNotNone(after.closed_at)
        unchanged = ("text", "reporter_id", "tenant_id", "subject_type", "subject_id", "version_number", "language_id", "created_at")
        self.assertEqual([getattr(after, name) for name in unchanged], [getattr(before, name) for name in unchanged])

    def test_an_officer_closes_a_colleagues_report(self) -> None:
        report_id = self.file(self.reader)
        answer = self.close(self.officer, report_id, {"status": "rejected", "resolutionNote": NOTE})
        self.assertEqual(answer.status_code, 200, answer.content)
        self.assertEqual(self.row(report_id).closed_by_id, self.officer.id)
        # The reporter sees the close on their own list.
        closed = self.listing(self.reader).json()["items"][0]
        self.assertEqual((closed["status"], closed["resolutionNote"]), ("rejected", NOTE))
        self.assertEqual(closed["closedBy"]["id"], str(self.officer.id))

    def test_a_member_without_proposals_create_cannot_close_a_colleagues_report(self) -> None:
        report_id = self.file(self.reader)
        refused = self.close(self.colleague, report_id)
        self.assertEqual(refused.status_code, 403, refused.content)
        self.assertEqual(refused.json()["code"], "permission_denied")
        self.assertEqual(refused.json()["requiredPermission"], perms.PROPOSALS_CREATE)
        self.assertEqual(self.row(report_id).status, ReportStatus.OPEN.value)

    def test_a_closed_report_cannot_be_closed_again(self) -> None:
        report_id = self.file(self.reader)
        self.assertEqual(self.close(self.reader, report_id).status_code, 200)
        again = self.close(self.officer, report_id, {"status": "rejected", "resolutionNote": "Another view."})
        self.assertEqual(again.status_code, 409, again.content)
        self.assertEqual(again.json()["code"], "already_closed")
        after = self.row(report_id)
        self.assertEqual((after.status, after.resolution_note, after.closed_by_id), ("fixed", NOTE, self.reader.id))

    def test_a_close_needs_a_closing_status_and_a_note(self) -> None:
        report_id = self.file(self.reader)
        for body in (
            {"status": "open", "resolutionNote": NOTE},
            {"status": "accepted", "resolutionNote": NOTE},
            {"status": "fixed"},
            {"status": "fixed", "resolutionNote": "   "},
            {"resolutionNote": NOTE},
        ):
            with self.subTest(body=body):
                refused = self.close(self.reader, report_id, body)
                self.assertEqual(refused.status_code, 422, refused.content)
        self.assertEqual(self.row(report_id).status, ReportStatus.OPEN.value)

    def test_the_close_is_audited_without_the_words(self) -> None:
        report_id = self.file(self.reader)
        with self.assertLogs(level=logging.DEBUG) as logs:
            logging.getLogger().debug("every log line of the close is captured from here")
            self.assertEqual(self.close(self.officer, report_id).status_code, 200)
        self.activate(self.tenant)
        event = AuditEvent.objects.get(action="problem_report.closed", subject_id=report_id)
        self.assertEqual((event.tenant_id, event.actor_id, event.subject_type), (self.tenant.id, self.officer.id, "problem_report"))
        self.assertEqual(event.before, {"status": "open"})
        self.assertEqual(event.after, {"status": "fixed"})
        outbox = OutboxEvent.objects.get(audit_event=event)
        self.assertEqual((outbox.topic, outbox.tenant_id), ("problem_report.closed", self.tenant.id))
        carried = " ".join([event.summary, event.subject_title, str(event.before), str(event.after), str(outbox.payload), *logs.output])
        for words in (WORDS, NOTE):
            self.assertNotIn(words, carried)
