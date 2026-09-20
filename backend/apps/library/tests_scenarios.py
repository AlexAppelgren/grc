"""Scenario tests for the library app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Chunk 3 un-skips INV-S7 and INV-S8, the two scenarios the write routes prove.
INV-S1 to INV-S6 and INV-S10 wait for the record reads; INV-S9 is R3.

Operations exercised (the audit-on-write guard reads these names):
reportObligationProblem, reportInstrumentProblem, reverifyObligation.

What a reader writes in a report is tenant content (playbook 4.7), so INV-S7 hunts a
sentinel sentence through every place it must not reach: the audit row, the outbox
payload the worker delivers, and the log. A report also stays inside the bank that
filed it (Alex, 2026-09-19, OWNER_RECOMMENDATIONS item 3): no other bank and no bleqq
reader sees it, which tests_report_isolation.py proves on the application role's own
connection, where row-level security is forced.

Prefixes hosted: INV.
"""

from __future__ import annotations

import ast
import contextlib
import datetime
import io
import logging
import uuid
from collections.abc import Iterator
from typing import Any
from unittest import skip

from apps.library import reading, testing
from apps.library.models import Obligation, ProblemReport, Verification
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, permissions as perms
from apps.shared.models import AuditEvent, OutboxEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.shared.tests_library_fence import LibraryWriteCalls, _is_allowed
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions

V1 = "/api/v1"
# One sentence a reader typed. It appears in the report row and nowhere else, so any other
# place it turns up is a leak of tenant content (playbook 4.7).
SENTINEL = "Yttrandet om kundkannedom saknar det femte aret, sallsynt nog."
VERIFIED_ON = datetime.datetime(2026, 3, 2, 9, 0, tzinfo=datetime.UTC)


@contextlib.contextmanager
def captured_logs() -> Iterator[io.StringIO]:
    """Everything every logger emits while the block runs, down to DEBUG. `assertLogs`
    cannot do this: it fails the test when nothing is logged, and a clean request logs
    nothing at all."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.DEBUG)
    root = logging.getLogger()
    was = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield stream
    finally:
        root.removeHandler(handler)
        root.setLevel(was)


class LibraryScenarioTests(ScenarioTestCase):
    """Scenario tests for apps.library, one method per @integration scenario."""

    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        self.tenant = factories.tenant(slug="bank")
        self.other = factories.tenant(slug="other-bank")
        self.activate(self.tenant)
        self.reader = factories.member(self.tenant, roles=("reader",), user_row=factories.user(name="Sara Lindqvist")).user
        self.admin = factories.member(self.tenant, roles=("admin",)).user
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        self.instrument = testing.instrument(key="fffs-2017-2", short_name="FFFS 2017:2", regime="regime:securities")
        self.obligation = testing.obligation(
            self.instrument, key="fffs-2017-2-9-6", ref_label="9 kap. 6 §", last_verified_at=VERIFIED_ON
        )
        # Another bank's private record: the caller must not learn that it exists (INV-07).
        # Written with that bank activated, because row-level security refuses a row for a
        # tenant other than the one the transaction is scoped to, the migrator included.
        self.activate(self.other)
        self.private = testing.obligation(
            testing.instrument(key="other-bank-source", owner_tenant=self.other),
            key="other-bank-duty",
            owner_tenant=self.other,
        )
        self.activate(self.tenant)

    def _post(self, path: str, body: dict[str, Any], headers: dict[str, Any]) -> Any:
        return self.client.post(f"{V1}{path}", data=body, content_type="application/json", **headers)

    def _report(self, **fields: object) -> dict[str, Any]:  # compliance: allow-kwargs test helper forwarding one body's fields
        body: dict[str, Any] = {"description": SENTINEL}
        body.update(fields)
        return body

    @skip("pending: INV-S1")
    def test_inv_s1(self) -> None:
        """INV-S1

        An instrument carries its identity, dates and lineage (INV-01).
        """

    @skip("pending: INV-S2")
    def test_inv_s2(self) -> None:
        """INV-S2

        The provision tree holds verbatim text versions (INV-02).
        """

    @skip("pending: INV-S3")
    def test_inv_s3(self) -> None:
        """INV-S3

        An obligation states the duty and its facets (INV-03).
        """

    @skip("pending: INV-S4")
    def test_inv_s4(self) -> None:
        """INV-S4

        "As of" returns the version in force on a date (INV-04, AC-INV1).
        """

    @skip("pending: INV-S5")
    def test_inv_s5(self) -> None:
        """INV-S5

        The diff between two versions is at sentence level (INV-04, AC-INV1).
        """

    @skip("pending: INV-S6")
    def test_inv_s6(self) -> None:
        """INV-S6

        Text exists in the original language with labelled translations (INV-05).
        """

    def test_inv_s7(self) -> None:
        """INV-S7

        Every record has a source link, a last-verified date and a way to report it (INV-06).
        """
        reader = sign_in(self.reader, tenant=self.tenant)

        # Given any instrument or obligation, it carries the source link and the date it was
        # last checked, which is what "Verified <date>" reads from. Asserted on the record the
        # subject lookup resolves; getObligation serialises the same two fields (chunk3-rest-T6).
        self.activate(self.tenant)
        subject = reading.visible_obligation(self.obligation.id, tenant=self.tenant)
        assert subject is not None
        self.assertTrue(subject.source_url)
        self.assertTrue(subject.source_label)
        self.assertEqual(subject.last_verified_at, VERIFIED_ON)
        source = reading.visible_instrument(self.instrument.id, tenant=self.tenant)
        assert source is not None
        self.assertTrue(source.source_url)

        # When a reader chooses "This looks wrong" and describes the problem, the report is
        # created and they see it acknowledged.
        with captured_logs() as logs:
            response = self._post(
                f"/obligations/{self.obligation.id}/problem-reports",
                self._report(versionNumber=1, language="en"),
                reader,
            )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "open")
        self.assertIn("createdAt", body)
        # The acknowledgement says the report exists; it does not echo the reader's words back.
        self.assertNotIn(SENTINEL, response.content.decode())

        self.activate(self.tenant)
        row = ProblemReport.objects.get(id=uuid.UUID(body["id"]))
        self.assertEqual(row.text, SENTINEL)
        self.assertEqual(row.subject_id, self.obligation.id)
        self.assertEqual((row.version_number, row.language_id), (1, "en"))
        # The tenant and the reporter come from the principal, never from the body.
        self.assertEqual(row.tenant_id, self.tenant.id)
        self.assertEqual(row.reporter_id, self.reader.id)

        # The words the reader typed reach the row and nothing else (playbook 4.7).
        event = AuditEvent.objects.get(action="library.problem_reported")
        outbox = OutboxEvent.objects.get(audit_event=event)
        for haystack in (event.summary, event.subject_title, str(event.before), str(event.after), str(outbox.payload)):
            self.assertNotIn(SENTINEL, haystack)
            self.assertNotIn("kundkannedom", haystack)
        self.assertNotIn(SENTINEL, logs.getvalue())
        self.assertEqual(event.after["reportId"], body["id"])

        # An instrument is reported the same way; its provisions are reported through it.
        instrument_response = self._post(
            f"/instruments/{self.instrument.id}/problem-reports", self._report(), reader
        )
        self.assertEqual(instrument_response.status_code, 201)
        self.activate(self.tenant)
        self.assertEqual(ProblemReport.objects.filter(subject_type="instrument").count(), 1)

        # A description of nothing is not a report.
        self.assertEqual(self._post(f"/obligations/{self.obligation.id}/problem-reports", {"description": "   "}, reader).status_code, 422)

        # A subject the caller cannot see is a 404, never a 403 that confirms it exists.
        for path in (
            f"/obligations/{self.private.id}/problem-reports",
            f"/obligations/{uuid.uuid4()}/problem-reports",
            f"/instruments/{uuid.uuid4()}/problem-reports",
            "/obligations/not-a-uuid/problem-reports",
        ):
            with self.subTest(path=path):
                self.assertEqual(self._post(path, self._report(), reader).status_code, 404)

        # Without problems.report there is no way in. The platform's own editor holds no
        # tenant permission, so bleqq never files a report inside a bank either.
        stranger = sign_in(self.editor)
        refused = self._post(f"/obligations/{self.obligation.id}/problem-reports", self._report(), stranger)
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.json()["requiredPermission"], perms.PROBLEMS_REPORT)

        self.activate(self.tenant)
        self.assertEqual(ProblemReport.objects.count(), 2)

    def test_inv_s8(self) -> None:
        """INV-S8

        The re-verification stamp is the only write outside a proposal (INV-06).
        """
        before = Obligation.objects.get(id=self.obligation.id)
        untouched = {
            field.attname: getattr(before, field.attname)
            for field in Obligation._meta.concrete_fields
            if field.name not in {"last_verified_at", "verified_by"}
        }

        # Given a library editor, when they re-verify a record against its source, only the
        # stamp moves. A fresh passkey assertion is the whole ceremony: no fact changes, so
        # there is nothing for a second pair of eyes to approve.
        editor = sign_in(self.editor, step_up=True)
        response = self._post(f"/obligations/{self.obligation.id}/verifications", {"outcome": "no_change"}, editor)
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["outcome"], "no_change")
        self.assertEqual(body["verifiedBy"]["name"], self.editor.name)

        after = Obligation.objects.get(id=self.obligation.id)
        assert after.last_verified_at is not None
        self.assertGreater(after.last_verified_at, VERIFIED_ON)
        self.assertEqual(after.verified_by_id, self.editor.id)
        for name, value in untouched.items():
            with self.subTest(field=name):
                self.assertEqual(getattr(after, name), value)

        # The stamp is audited with the assertion the reviewer's passkey produced.
        event = AuditEvent.objects.get(action="library.reverified")
        self.assertIsNotNone(event.step_up_assertion_id)

        # An outcome that found something leaves the stamp standing: the change arrives as a
        # proposal, which is the only door into the library.
        stamped = after.last_verified_at
        found = self._post(
            f"/obligations/{self.obligation.id}/verifications",
            {"outcome": "change_found", "note": "The fifth year is missing."},
            editor,
        )
        self.assertEqual(found.status_code, 201)
        self.assertEqual(Obligation.objects.get(id=self.obligation.id).last_verified_at, stamped)
        self.assertEqual(Verification.objects.count(), 2)

        # And the fence guard fails on any other module that writes a LibraryModel: the
        # scanner sees the model and the write call, and neither api.py nor reading.py is a
        # module allowed to open library_write().
        smuggled = ast.parse("from apps.library.models import Obligation\nObligation.objects.create(stable_key='x')\n")
        visitor = LibraryWriteCalls()
        visitor.visit(smuggled)
        self.assertIn("Obligation", visitor.names)
        self.assertEqual([method for _line, method in visitor.write_calls], ["create"])
        self.assertFalse(_is_allowed("library/api.py"))
        self.assertFalse(_is_allowed("library/reading.py"))
        self.assertTrue(_is_allowed("proposals/apply.py"))

        # What is refused, with nothing written.
        self.assertEqual(self._post(f"/obligations/{self.obligation.id}/verifications", {"outcome": "no_such_outcome"}, editor).status_code, 422)
        stale = sign_in(self.editor)
        refused = self._post(f"/obligations/{self.obligation.id}/verifications", {"outcome": "no_change"}, stale)
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.json()["code"], "step_up_required")

        # No tenant role reaches the library: between them the tenant's roles hold every
        # tenant permission, and proposals.review is not one of them (PRD section 6).
        everything = sign_in(self.admin, tenant=self.tenant, step_up=True)
        self.assertEqual(self._post(f"/obligations/{self.obligation.id}/verifications", {"outcome": "no_change"}, everything).status_code, 403)

        # No API key scope reaches it either: the route takes a person's session only, so a
        # key holding every scope is not even a principal here (AC-PRO1, ID-S21).
        key = factories.api_key(self.tenant, scopes=tuple(sorted(perms.ALL_SCOPES)))
        agent = self._post(
            f"/obligations/{self.obligation.id}/verifications", {"outcome": "no_change"}, {"HTTP_X_API_KEY": key.plain_key}
        )
        self.assertIn(agent.status_code, (401, 403))

        self.assertEqual(Verification.objects.count(), 2)

        # And the fence guard fails on any other module that writes a LibraryModel: the
        # scanner sees the model and the write call, and neither api.py nor reading.py is a
        # module allowed to open library_write().
        smuggled = ast.parse("from apps.library.models import Obligation\nObligation.objects.create(stable_key='x')\n")
        visitor = LibraryWriteCalls()
        visitor.visit(smuggled)
        self.assertIn("Obligation", visitor.names)
        self.assertEqual([method for _line, method in visitor.write_calls], ["create"])
        self.assertFalse(_is_allowed("library/api.py"))
        self.assertFalse(_is_allowed("library/reading.py"))
        self.assertTrue(_is_allowed("proposals/apply.py"))

    @skip("pending: INV-S9 (INV-07, R3)")
    def test_inv_s9(self) -> None:
        """INV-S9

        Tenant-private records are visible to their owner only (INV-07).
        """

    @skip("pending: INV-S10")
    def test_inv_s10(self) -> None:
        """INV-S10

        Legal dates are plain dates with a precision (INV-01, INV-02).
        """

    @skip("pending: INV-S11 (INV-08, chunk 3)")
    def test_inv_s11(self) -> None:
        """INV-S11

        An edition of a standard is an instrument with public facts and no text (INV-01, INV-02, INV-08).
        """

    @skip("pending: INV-S12 (INV-08, chunk 3)")
    def test_inv_s12(self) -> None:
        """INV-S12

        Every instrument carries a regime from the regime dimension (INV-01, INV-08).
        """
