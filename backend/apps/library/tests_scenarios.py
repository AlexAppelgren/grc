"""Scenario tests for the library app.

One test per `@integration` scenario in app.md (playbook 4.1, Appendix B).
Each stub is skipped until the feature lands; un-skip it in the same commit
that builds the scenario, and never delete one without updating app.md.
The requirements coverage gate (scripts/requirements_coverage.py) fails
when a scenario here and a heading in app.md drift apart.

Chunk 3 un-skips INV-S3 to INV-S6, the record reads, INV-S7 and INV-S8, the two scenarios
the write routes prove, and, with the instrument read (chunk3-rest-T13), INV-S1 and
INV-S10; INV-S11 with the first standard, built by `testing.standard()`. INV-S2 waits for the provision tree read (chunk3-rest-T16); INV-S9 is R3.

Operations exercised (the audit-on-write guard reads these names):
reportObligationProblem, reportInstrumentProblem, reverifyObligation.

What a reader writes in a report is tenant content (playbook 4.7), so INV-S7 hunts a
sentinel sentence through every place it must not reach: the audit row, the outbox
payload the worker delivers, and the log. A report also stays inside the bank that
filed it (Alex, 2026-09-19, OWNER_RECOMMENDATIONS item 3): no other bank and no bleqq
reader sees it, which tests_report_isolation.py proves on the application role's own
connection, where row-level security is forced.

Prefixes hosted: INV.

The scenarios that read an obligation (INV-S3 to INV-S6) run against the sample library
the prototype's data seeds, so what a reader sees is what the product ships with. INV-S4
and INV-S5 add versions of their own, dated, and INV-S2 and INV-S6 read the seeded records
as of the data's own anchor date, so no test depends on the day it runs.
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

from django.conf import settings
from django.db import DatabaseError, connection, transaction

from apps.identity.models import User
from apps.library import reading, testing as build
from apps.library.models import Instrument, Obligation, ObligationVersion, ProblemReport, Verification
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import load_library, seed_authorities
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.models import AuditEvent, OutboxEvent, Tenant
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.shared.tests_library_fence import LibraryWriteCalls, _is_allowed
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms

V1 = "/api/v1"
URL = f"{V1}/obligations"
# One sentence a reader typed. It appears in the report row and nowhere else, so any other
# place it turns up is a leak of tenant content (playbook 4.7).
SENTINEL = "Yttrandet om kundkannedom saknar det femte aret, sallsynt nog."
D = datetime.date
# The two dates INV-S4 and INV-S5 compare, fixed: research payments version 2 takes effect
# on 2026-10-01, and nothing here reads the clock.
FIRST_VERSION = D(2025, 1, 1)
SECOND_VERSION = D(2026, 10, 1)
FIRST_SUMMARY = "Research is paid from own resources. The institution keeps the records."
SECOND_SUMMARY = "Research may be paid jointly with execution. The institution keeps the records."
# The prototype data's own anchor date (`_meta.anchor_date`): the seeded research payment
# obligation and 9 kap. 6 § are each on version 1, and each one's version 2 (2026-10-01)
# is still to come. A read of a seeded record names it, so what it reads never moves with
# the clock.
SEEDED_DAY = D(2026, 9, 16)


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

    tenant: Tenant
    other: Tenant
    reader: User
    admin: User
    editor: User
    instrument: Instrument
    obligation: Obligation
    private: Obligation
    versioned: Obligation

    @classmethod
    def setUpTestData(cls) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_taxonomy_terms()
        seed_authorities()
        load_library()
        cls.tenant = factories.tenant(slug="inventory-reader")
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        cls.admin = factories.member_user(cls.tenant, roles=("admin",))
        cls.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        # The record INV-S7 and INV-S8 act on is one the prototype's data seeds, so what
        # they prove about a source link and a verified date is true of the library the
        # product ships with rather than of a row a test built to pass.
        cls.instrument = Instrument.objects.get(stable_key="fffs-2017-2")
        cls.obligation = Obligation.objects.get(stable_key="obl-research-payments")
        cls.versioned = build.obligation(
            build.instrument(key="fffs-2017-2-versions", short_name="FFFS 2017:2", regime="regime:securities"),
            key="obl-research-payments-versions",
            titles={"en": "Pay for research only under the permitted models"},
            ref_label="Third-party payments",
            versions=((FIRST_VERSION, {"en": FIRST_SUMMARY}), (SECOND_VERSION, {"en": SECOND_SUMMARY})),
        )
        # Another bank's private record: the caller must not learn that it exists (INV-07).
        # Written with that bank activated, because row-level security refuses a row for a
        # tenant other than the one the transaction is scoped to, the migrator included.
        cls.other = factories.tenant(slug="other-bank")
        tenancy.activate(cls.other.id)
        cls.private = build.obligation(
            build.instrument(key="other-bank-source", regime="regime:securities", owner_tenant=cls.other),
            key="other-bank-duty",
            owner_tenant=cls.other,
        )
        tenancy.activate(cls.tenant.id)

    def read(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.client.get(path, params or {}, **sign_in(self.reader, tenant=self.tenant))
        self.assertEqual(response.status_code, 200, response.content)
        return dict(response.json())

    def card(self, stable_key: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.read(f"{URL}/{Obligation.objects.get(stable_key=stable_key).id}", params)

    def _post(self, path: str, body: dict[str, Any], headers: dict[str, Any]) -> Any:
        return self.client.post(f"{V1}{path}", data=body, content_type="application/json", **headers)

    def _report(self, **fields: object) -> dict[str, Any]:  # compliance: allow-kwargs test helper forwarding one body's fields
        body: dict[str, Any] = {"description": SENTINEL}
        body.update(fields)
        return body

    def test_inv_s1(self) -> None:
        """INV-S1

        An instrument carries its identity, dates and lineage (INV-01).
        """
        card = self.read(f"/api/v1/instruments/{self.instrument.id}")
        self.assertEqual((card["level"]["key"], card["binding"], card["officialRef"]), ("authority_regulation", True, "FFFS 2017:2"))
        self.assertEqual(card["eliUri"], "", "the ELI where available; FFFS 2017:2 has none")
        self.assertEqual((card["jurisdiction"]["key"], card["authority"]["key"]), ("se", "fi"))
        self.assertEqual(card["inForceFrom"], {"date": "2018-01-03", "precision": "day"})
        self.assertEqual(card["implementsNote"], "MiFID II delegated directive (EU) 2017/593")
        amendments = [link for link in card["lineage"] if link["relation"]["key"] == "amends"]
        self.assertEqual(
            [(link["direction"], link["instrument"]["key"]) for link in amendments],
            [("incoming", "fffs-2026-11")],
            "amended by FFFS 2026:11",
        )

        # No tenant_id column: it is readable by every tenant, unchanged.
        other_reader = sign_in(factories.member_user(self.other, roles=("reader",)), tenant=self.other)
        response = self.client.get(f"/api/v1/instruments/{self.instrument.id}", **other_reader)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stableKey"], "fffs-2017-2")

    def test_inv_s2(self) -> None:
        """INV-S2

        The provision tree holds verbatim text versions (INV-02).
        """
        self.activate(self.tenant)
        instrument = build.instrument(key="tree-instrument", regime="regime:securities", level="act")
        chapter = build.provision(instrument, key="tree-instrument/1", ref_label="1 kap.", kind="chapter")
        section = build.provision(instrument, key="tree-instrument/1-1", ref_label="1 §", kind="section", parent=chapter)
        build.provision(instrument, key="tree-instrument/1-1-1", ref_label="första stycket", kind="paragraph", parent=section)
        build.provision_version(section, version_no=1, effective_from=D(2018, 1, 1), texts={"en": "The original text."})
        build.provision_version(
            section,
            version_no=2,
            effective_from=D(2026, 11, 1),
            transitional_note="The amendment applies from 1 November 2026.",
            texts={"en": "The amended text."},
        )
        reader = sign_in(self.reader, tenant=self.tenant)

        def tree(instrument_id: uuid.UUID, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
            response = self.client.get(f"{V1}/instruments/{instrument_id}/provisions", params or {}, **reader)
            self.assertEqual(response.status_code, 200, response.content)
            return list(response.json())

        # Given a tree of chapter, section and paragraph, when a provision's text is
        # replaced by an amendment in force on 2026-11-01, a new text version row exists
        # with that effective date and a transitional note.
        before = tree(instrument.id, {"asOf": "2026-10-31"})
        found = next(node["children"][0] for node in before if node["stableKey"] == "tree-instrument/1")
        self.assertEqual(found["kind"]["key"], "section")
        self.assertEqual([v["versionNumber"] for v in found["versions"]], [1, 2])
        self.assertEqual(found["versions"][1]["effectiveFrom"], {"date": "2026-11-01", "precision": "day"})
        self.assertEqual(found["versions"][1]["transitionalNote"], "The amendment applies from 1 November 2026.")
        self.assertEqual(found["inForceVersion"], 1, "as of the day before the amendment, the earlier version still applies")
        unchanged_first_version = found["versions"][0]

        # As of on or after the amendment, the new version is in force, and the earlier
        # row has not been touched by the read.
        after = tree(instrument.id, {"asOf": "2026-11-01"})
        found_after = next(node["children"][0] for node in after if node["stableKey"] == "tree-instrument/1")
        self.assertEqual(found_after["inForceVersion"], 2)
        self.assertEqual(found_after["versions"][0], unchanged_first_version)

        # The tree screen's "Show what changed" opens the diff between the two versions.
        diff = self.client.get(f"{V1}/provisions/{section.id}/diff", **reader)
        self.assertEqual(diff.status_code, 200, diff.content)
        body = diff.json()
        self.assertEqual((body["fromVersion"], body["toVersion"]), (1, 2))
        self.assertEqual([segment["op"] for segment in body["segments"]], ["delete", "insert"])

        # And the seeded FFFS 2017:2 tree: a chapter, its sections and one paragraph
        # under a section (three levels), with 9 kap. 6 §'s own amendment still to come.
        fffs_tree = tree(self.instrument.id, {"asOf": SEEDED_DAY.isoformat()})
        fffs_chapter = next(node for node in fffs_tree if node["stableKey"] == "fffs-2017-2/9")
        fffs_section = next(child for child in fffs_chapter["children"] if child["stableKey"] == "fffs-2017-2/9-6")
        self.assertTrue(
            any(grandchild["kind"]["key"] == "paragraph" for grandchild in fffs_section["children"]), "9 kap. 6 § has a paragraph under it"
        )
        self.assertEqual([v["versionNumber"] for v in fffs_section["versions"]], [1, 2])
        self.assertTrue(fffs_section["versions"][1]["transitionalNote"])
        self.assertEqual(fffs_section["inForceVersion"], 1, "the version in force on the seeded day, whatever today is")

    def test_inv_s3(self) -> None:
        """INV-S3

        An obligation states the duty and its facets (INV-03).
        """
        card = self.card("obl-appropriateness")
        self.assertEqual(card["title"]["text"], "Assess appropriateness before non-advised trades in complex instruments")
        self.assertTrue(card["summary"]["text"].startswith("Before providing a non-advised service"), card["summary"])
        self.assertEqual(card["dutyType"]["key"], "conduct", "a key and a label, never a phrase to match on")
        self.assertEqual(
            (card["productScope"], card["triggerFrequency"], card["retention"], card["sanctionExposure"]),
            ("Complex instruments", "Per order in a complex instrument", "5 years", "FI remark, warning or sanction fee"),
        )
        scope = {entry["dimension"]["key"]: [term["key"] for term in entry["terms"]] for entry in card["scope"]}
        self.assertEqual(scope["service_type"], ["non_advised", "execution_only"])
        self.assertEqual(scope["client_category"], ["retail"])
        self.assertEqual(scope["regime"], ["securities"], "the instrument's regime is part of the obligation's scope")
        self.assertEqual(scope["lifecycle_stage"], ["pre_trade"])
        self.assertEqual(
            [(provision["refLabel"], provision["path"]) for provision in card["provisions"]],
            [("9 kap.", "LVM > 9 kap.")],
            "the provision it comes from, by reference and path; the verbatim text is the tree's",
        )
        self.assertEqual(
            [(related["instrument"]["key"], related["binding"], related["relation"]["key"]) for related in card["related"]],
            [("esma-35-43-3006", False, "related")],
        )
        self.assertEqual((card["instrument"]["key"], card["regime"]["key"], card["bindingLevel"]["key"]), ("sfs-2007-528", "securities", "act"))
        self.assertEqual(card["binding"], True)

    def test_inv_s4(self) -> None:
        """INV-S4

        "As of" returns the version in force on a date (INV-04, AC-INV1).
        """
        path = f"{URL}/{self.versioned.id}"
        early = self.read(path, {"asOf": "2026-06-30"})
        self.assertEqual(early["version"]["versionNumber"], 1)
        self.assertEqual(early["summary"]["text"], FIRST_SUMMARY)
        on_the_day = self.read(path, {"asOf": SECOND_VERSION.isoformat()})
        self.assertEqual(on_the_day["version"]["versionNumber"], 2)
        self.assertEqual(on_the_day["summary"]["text"], SECOND_SUMMARY)
        self.assertEqual(
            [(row["versionNumber"], row["effectiveFrom"]["date"], row["effectiveTo"]) for row in early["versions"]],
            [(1, "2025-01-01", {"date": "2026-09-30", "precision": "day"}), (2, "2026-10-01", None)],
        )
        # Nothing has rewritten the first version, and nothing can: the table is append-only
        # whatever the write path, so "as of" reads a history no correction can change.
        first = ObligationVersion.objects.get(obligation=self.versioned, version_number=1)
        with self.assertRaisesMessage(DatabaseError, "obligation_version is append-only"), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("UPDATE obligation_version SET effective_from = %s WHERE id = %s", ["2027-01-01", first.id])
        first.refresh_from_db()
        self.assertEqual(first.effective_from, FIRST_VERSION)

    def test_inv_s5(self) -> None:
        """INV-S5

        The diff between two versions is at sentence level (INV-04, AC-INV1).
        """
        diff = self.read(f"{URL}/{self.versioned.id}/diff")
        self.assertEqual((diff["fromVersion"], diff["toVersion"]), (1, 2), "the latest version against the one before it")
        self.assertEqual(
            [(segment["op"], segment["text"]) for segment in diff["segments"]],
            [
                ("delete", "Research is paid from own resources."),
                ("insert", "Research may be paid jointly with execution."),
                ("equal", "The institution keeps the records."),
            ],
            "the changed sentence is marked and the others are left alone",
        )
        self.assertEqual(
            (diff["fromEffective"]["date"], diff["toEffective"]["date"]),
            (FIRST_VERSION.isoformat(), SECOND_VERSION.isoformat()),
            "the screen names the two effective dates being compared",
        )

    def test_inv_s6(self) -> None:
        """INV-S6

        Text exists in the original language with labelled translations (INV-05).
        """
        # The reader's language order is en; the research payment summary was written in sv.
        card = self.card("obl-research-payments", {"asOf": SEEDED_DAY.isoformat()})
        self.assertEqual(card["version"]["versionNumber"], 1, "the version in force on the seeded day, whatever today is")
        self.assertEqual(card["summary"]["language"], "en")
        self.assertTrue(card["summary"]["isMachine"], "a machine translation stays labelled until a person confirms it")
        self.assertFalse(card["summary"]["isOriginal"])
        original = next(text for text in card["translations"] if text["isOriginal"])
        self.assertEqual(original["language"], "sv", "the original is there for 'Show original'")
        self.assertFalse(original["isMachine"])
        self.assertEqual({text["language"] for text in card["translations"]}, {"en", "sv"})
        swedish = self.read(f"{URL}/{self.versioned.id}/diff", {"lang": "sv"})
        self.assertEqual(swedish["language"], "en", "a language neither version has falls back to one both have")

    def test_inv_s7(self) -> None:
        """INV-S7

        Every record has a source link, a last-verified date and a way to report it (INV-06).
        """
        reader = sign_in(self.reader, tenant=self.tenant)

        # Given any instrument or obligation, it carries the source link and the date it was
        # last checked, which is what "Verified <date>" reads from. Asserted on the record the
        # subject lookup resolves; getObligation and getInstrument serialise the same fields
        # (chunk3-rest-T6, chunk3-rest-T13).
        self.activate(self.tenant)
        subject = reading.obligation_subject(self.obligation.id)
        self.assertTrue(subject.source_url)
        self.assertTrue(subject.source_label)
        self.assertIsNotNone(subject.last_verified_at)
        instrument_subject = reading.instrument_subject(self.instrument.id)
        self.assertTrue(instrument_subject.source_url)
        self.assertIsNotNone(instrument_subject.last_verified_at)

        # The instrument card itself carries the same two facts.
        instrument_card = self.read(f"/api/v1/instruments/{self.instrument.id}")
        self.assertEqual(instrument_card["sourceUrl"], instrument_subject.source_url)
        self.assertIsNotNone(instrument_card["lastVerifiedAt"])

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

        # A subject the caller cannot see is a 404, never a 403 that confirms it exists:
        # another bank's private record and an id that names nothing read the same.
        for path in (
            f"/obligations/{self.private.id}/problem-reports",
            f"/obligations/{uuid.uuid4()}/problem-reports",
            f"/instruments/{uuid.uuid4()}/problem-reports",
        ):
            with self.subTest(path=path):
                self.assertEqual(self._post(path, self._report(), reader).status_code, 404)
        # A path segment that is not an id at all is a malformed request, not a record being
        # hidden, and answers the 422 every other record route gives it (getObligation).
        self.assertEqual(self._post("/obligations/not-a-uuid/problem-reports", self._report(), reader).status_code, 422)

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
        verified_on = before.last_verified_at
        assert verified_on is not None, "a seeded record carries the date it was last checked (INV-S7)"
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
        self.assertGreater(after.last_verified_at, verified_on)
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
        # key holding every scope is not even a principal here (AC-PRO1, ID-S21). Only a
        # platform key bound to an agent can hold every scope; a bank's key holds at most the
        # bank's share, so both are tried.
        from apps.agents import testing as agents_testing

        tenancy.clear_tenant()  # a platform key is written with no tenant activated (H15)
        every_scope = agents_testing.agent_key(scopes=tuple(sorted(perms.ALL_SCOPES)))
        bank_key = factories.api_key(self.tenant, scopes=tuple(sorted(perms.TENANT_KEY_SCOPES)))
        for key in (every_scope, bank_key):
            agent = self._post(
                f"/obligations/{self.obligation.id}/verifications", {"outcome": "no_change"}, {"HTTP_X_API_KEY": key.plain_key}
            )
            self.assertIn(agent.status_code, (401, 403))

        self.assertEqual(Verification.objects.count(), 2)

    @skip("pending: INV-S9 (INV-07, chunk 11)")
    def test_inv_s9(self) -> None:
        """INV-S9

        Tenant-private records are visible to their owner only (INV-07).
        """

    def test_inv_s10(self) -> None:
        """INV-S10

        Legal dates are plain dates with a precision (INV-01, INV-02).
        """
        self.activate(self.tenant)
        quarter = build.instrument(
            key="quarter-precision", regime="regime:securities", in_force_from=D(2026, 10, 1), in_force_from_precision="quarter"
        )
        card = self.read(f"/api/v1/instruments/{quarter.id}")
        self.assertEqual(card["inForceFrom"], {"date": "2026-10-01", "precision": "quarter"})

    def test_inv_s11(self) -> None:
        """INV-S11

        An edition of a standard is an instrument with public facts and no text (INV-01, INV-02, INV-08).

        The screens' half ("Standard" in the binding slot, "licensed" in the tree) is the
        journey's. The standard's term stays as seeded, inactive: the reads show a record
        whatever its term's state, and nothing here asks a door to resolve it.
        """
        self.activate(self.tenant)
        duty = build.standard()
        edition = duty.instrument

        # Given the instrument at the level "Standard" under "International" and "ISO/IEC",
        # it holds its official reference, publication date with precision, catalogue link
        # and regime.
        card = self.read(f"{V1}/instruments/{edition.id}")
        self.assertEqual(
            (card["officialRef"], card["inForceFrom"], card["sourceUrl"], card["regime"]["key"]),
            ("ISO/IEC 27001:2022", {"date": "2022-10-25", "precision": "day"}, build.ISO_27001_CATALOGUE, "ai_ict"),
        )
        self.assertEqual((card["level"]["key"], card["level"]["kind"], card["binding"]), ("standard", "standard", False))
        self.assertEqual((card["jurisdiction"]["key"], card["authority"]["key"]), ("intl", "iso-iec"))

        # bindingLevel carries the kind "standard" on the standard's duty and a null kind on
        # every other level, in the list and on the card.
        rows = self.read(URL, {"footprint": "all", "limit": settings.API_PAGE_SIZE_MAX})
        self.assertEqual(rows["total"], len(rows["items"]))
        kinds = {row["stableKey"]: row["bindingLevel"]["kind"] for row in rows["items"]}
        self.assertEqual(kinds.pop(duty.stable_key), "standard")
        self.assertTrue(kinds)
        self.assertEqual(set(kinds.values()), {None})
        self.assertEqual(self.card(duty.stable_key)["bindingLevel"]["kind"], "standard")

        # The instrument has exactly one obligation and no provision.
        mine = self.read(URL, {"footprint": "all", "instrument": edition.stable_key})
        self.assertEqual([row["stableKey"] for row in mine["items"]], [duty.stable_key])
        response = self.client.get(f"{V1}/instruments/{edition.id}/provisions", **sign_in(self.reader, tenant=self.tenant))
        self.assertEqual((response.status_code, response.json()), (200, []))

    def test_inv_s12(self) -> None:
        """INV-S12

        Every instrument carries a regime from the regime dimension (INV-01, INV-08).
        """
        from django.db import IntegrityError

        from apps.proposals.models import Proposal, ProposalStatus
        from apps.proposals.tests_kinds import instrument_body
        from apps.taxonomy.models import InstrumentLevel

        # An instrument row written without a regime: the database refuses it.
        with self.assertRaises(IntegrityError), transaction.atomic(), tenancy.library_write("scenario"):
            Instrument.objects.create(
                stable_key="inv-s12-no-regime",
                short_name="No regime",
                official_ref="No regime",
                source_url="https://www.fi.se/",
                level=InstrumentLevel.objects.get(key="act"),
                binding=True,
                jurisdiction=self.instrument.jurisdiction,
                created_origin="user",
            )
        # Every seeded instrument's regime is a term of the regime dimension.
        seeded = Instrument.objects.select_related("regime__dimension")
        self.assertTrue(seeded.exists())
        self.assertEqual({instrument.regime.dimension.key for instrument in seeded}, {"regime"})
        # A proposal naming a term of the Service dimension as its regime, stored as it
        # arrived before the rule, is refused when a reviewer approves it: the apply
        # answers 422 not_a_regime and nothing is written.
        body = instrument_body(key="inv-s12-service-regime", regime="service_type:advice")
        tenancy.clear_tenant()  # the console's zone, as its own request has in production (proposals 0009)
        proposal = Proposal.objects.create(
            kind=body["kind"],
            title=body["title"],
            payload=body["payload"],
            field_sources=body["fieldSources"],
            source_url=body["sourceUrl"],
            origin="agent",
        )
        refused = self.client.post(f"{V1}/proposals/{proposal.id}/approve", data={}, content_type="application/json", **sign_in(self.editor, step_up=True))
        self.assertEqual(refused.status_code, 422, refused.content)
        self.assertEqual(refused.json()["code"], "not_a_regime")
        self.assertFalse(Instrument.objects.filter(stable_key="inv-s12-service-regime").exists())
        self.assertEqual(Proposal.objects.get(pk=proposal.pk).status, ProposalStatus.OPEN.value)
        self.assertFalse(AuditEvent.objects.filter(action="instrument.created").exists())

    @skip("pending: INV-S13 (INV-07, chunk 11)")
    def test_inv_s13(self) -> None:
        """INV-S13

        A private record's text never reaches a model, the index or another bank (INV-07).
        """

    def test_inv_s14(self) -> None:
        """INV-S14

        A record an agent confirmed reads as machine-confirmed (INV-05, INV-06, PRO-02).
        """
        from apps.agents import testing as agents_testing
        from apps.shared import tenancy

        tenancy.clear_tenant()  # a platform key is written with no tenant activated (H15)

        # A record of its own, with a single version dated "since always" (DEFAULT_VERSIONS),
        # so the version the proposal adds is unambiguously the one now in force: same date
        # (null), higher number.
        obligation = build.obligation(
            build.instrument(key="inv-s14-instrument", short_name="INV S14", regime="regime:securities"),
            key="obl-inv-s14-agent-confirmed",
            titles={"en": "A duty an agent confirms"},
        )
        proposer = agents_testing.agent_key(scopes=(perms.SCOPE_PROPOSALS_WRITE,))
        confirmer = agents_testing.agent_key(scopes=(perms.SCOPE_PROPOSALS_REVIEW,))
        body = {
            "kind": "new_obligation_version",
            "title": "Refresh the wording against the source",
            "targetType": "obligation",
            "targetId": str(obligation.id),
            "payload": {
                "summaries": {"en": "Agents keep the wording current with the source."},
                "originalLanguage": "en",
                "isMachine": True,
            },
            "fieldSources": {"summaries.en": "https://www.fi.se/"},
            # An agent files under an open run of its own (AGT-01).
            "agentRunId": str(agents_testing.platform_run(key=proposer).id),
        }
        created = self._post("/proposals", body, {"HTTP_X_API_KEY": proposer.plain_key})
        self.assertEqual(created.status_code, 201, created.content)
        # The confirming agent sends the model call behind its decision, in a run of its own (D-80).
        approved = self._post(
            f"/proposals/{created.json()['id']}/approve", agents_testing.decision(confirmer), {"HTTP_X_API_KEY": confirmer.plain_key}
        )
        self.assertEqual(approved.status_code, 200, approved.content)

        # The record's provenance names the proposing agent and the confirming agent:
        # verified_origin is "agent" and no person is named as its verifier. The version
        # itself carries the same three facts, so its row in the version list says so too.
        card = self.card(obligation.stable_key)
        provenance, version = card["provenance"], card["version"]
        for confirmation in (provenance, version):
            self.assertEqual(confirmation["verifiedOrigin"], "agent")
            self.assertEqual(confirmation["confirmedByAgent"]["key"], confirmer.agent.key)
            self.assertEqual(confirmation["proposedByAgent"]["key"], proposer.agent.key)
        self.assertIsNone(provenance["verifiedBy"])

        # When a person later re-verifies the record against its source, the stamp names
        # that person and is dated after the version's approval. That order is what the
        # backend answers; letting the machine-confirmed label give way to it in the
        # record's "Last verified" slot, and only there, is the screen's rule
        # (obligation-presentation.ts), which the @e2e half proves.
        editor = sign_in(self.editor, step_up=True)
        reverified = self._post(f"/obligations/{obligation.id}/verifications", {"outcome": "no_change"}, editor)
        self.assertEqual(reverified.status_code, 201, reverified.content)
        after = self.card(obligation.stable_key)
        self.assertEqual(after["provenance"]["verifiedBy"]["name"], self.editor.name)
        self.assertGreater(
            datetime.datetime.fromisoformat(after["provenance"]["lastVerifiedAt"]),
            datetime.datetime.fromisoformat(after["version"]["approvedAt"]),
        )
        # The version's own machine-confirmed facts are untouched: nothing overwritten.
        for confirmation in (after["provenance"], after["version"]):
            self.assertEqual(confirmation["verifiedOrigin"], "agent")
            self.assertEqual(confirmation["confirmedByAgent"]["key"], confirmer.agent.key)

    @skip("pending: INV-S15 (OWN-04, INV-07, AC-OWN1, chunk 11)")
    def test_inv_s15(self) -> None:
        """INV-S15

        The bank's own records read "Private to us", and nothing changes when the library catches up (OWN-04, INV-07, AC-OWN1).
        """
