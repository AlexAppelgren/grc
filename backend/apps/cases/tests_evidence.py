"""Evidence: attached, measured, scanned and streamed (CAS-05, D-11, D-101; c9-evidence).

A file is untrusted from the first byte. What is proved here is that the server, never the
client, says what a file is, how large it is and what it hashes to; that a file outside the
allow-list or over the cap is refused before a byte reaches storage; that nothing can be
downloaded until the scanner passed it, and an infected file's bytes are gone while its
row and hash stay; that every download is one audit row and a refusal none; and that no
filename reaches a log. Removal is `tests_evidence_remove.py`'s.

Proven to fail 2026-09-25: with the sniff dropped, the HTML file named `.pdf` was stored;
with the delete dropped from the scan task, the EICAR bytes stayed in storage; with a log
line naming the evidence planted in `add_evidence`, the log-capture test failed on it.
"""

from __future__ import annotations

import hashlib
import io
import tempfile
import uuid
import zipfile
from types import SimpleNamespace
from typing import Any
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.cases import evidence as evidence_logic
from apps.cases import tasks
from apps.cases import testing as case_build
from apps.cases.models import ChangeCase, Evidence
from apps.home.tests_feed import captured_logs
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.adapters.scanner import EICAR_MARKER, MOCK_ERROR_MARKER, ScanState
from apps.shared.models import AuditEvent
from apps.shared.storage import get_storage
from apps.shared.testing import SESSION_TOKEN_FOR_TESTS, stub_session, user_principal
from apps.taxonomy.models import CaseStatusCategory

V1 = "/api/v1"
AS_SESSION: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {SESSION_TOKEN_FOR_TESTS}"}
PDF = b"%PDF-1.7\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n"
SECRET_NAME = "Board minutes on the Kista branch closure.pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def ooxml(folder: str) -> bytes:
    """The smallest Office Open XML package: its content types and one part in `folder`."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("[Content_Types].xml", "<Types/>")
        package.writestr(f"{folder}document.xml", "<document/>")
    return buffer.getvalue()


def a_file(content: bytes = PDF, *, filename: str = "criteria.pdf", content_type: str = "application/pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(filename, content, content_type=content_type)


def bank_with_case(category: CaseStatusCategory = CaseStatusCategory.IMPLEMENTING) -> SimpleNamespace:
    """A bank with one case in `category` and one of its people holding every tenant
    permission, as a stubbed session."""
    tenant = factories.tenant()
    person = factories.member_user(tenant, roles=("admin",))
    row = case_build.case_on_a_new_change(tenant)
    case_build.in_category(row, category)
    return SimpleNamespace(
        tenant=tenant,
        person=person,
        case=row,
        change_id=row.change_id,
        principal=user_principal(subject_id=person.id, tenant_id=tenant.id, permissions=perms.TENANT_PERMISSIONS),
    )


class EvidenceTestCase(TestCase):
    """Every test writes into a storage root of its own, so what a test stored or deleted is
    exactly what it reads back."""

    def setUp(self) -> None:
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name, STORAGE_BACKEND="local", SCANNER_PROVIDER="mock")
        override.enable()
        self.addCleanup(override.disable)
        self.bank = bank_with_case()

    def attach(self, form: dict[str, Any], *, scan: bool = True, bank: SimpleNamespace | None = None) -> Any:
        """POST the form as a session of `bank`. With `scan`, the scan queued on commit runs
        (eagerly, as the test settings run Celery); without it, the file stays `pending`."""
        bank = bank or self.bank
        with stub_session(bank.principal), self.captureOnCommitCallbacks(execute=scan):
            return self.client.post(f"{V1}/changes/{bank.change_id}/evidence", data=form, **AS_SESSION)

    def attach_file(self, upload: SimpleUploadedFile | None = None, *, name: str = "Research criteria", scan: bool = True) -> Any:
        return self.attach({"kind": "file", "name": name, "file": upload or a_file()}, scan=scan)

    def download(self, evidence_id: Any, *, bank: SimpleNamespace | None = None) -> Any:
        with stub_session((bank or self.bank).principal):
            return self.client.get(f"{V1}/evidence/{evidence_id}/download", **AS_SESSION)

    def row(self, evidence_id: Any) -> Evidence:
        with transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            return Evidence.objects.get(pk=evidence_id)

    def audit_rows(self, action: str) -> list[AuditEvent]:
        with transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            return list(AuditEvent.objects.filter(action=action).order_by("created"))

    def stored_files(self) -> int:
        from pathlib import Path

        from django.conf import settings

        return sum(1 for path in Path(settings.MEDIA_ROOT).rglob("*") if path.is_file())


class AttachFile(EvidenceTestCase):
    def test_the_server_measures_hashes_and_types_the_bytes_it_received(self) -> None:
        response = self.attach_file(scan=False)
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()["evidence"]
        self.assertEqual(body["kind"], "file")
        self.assertEqual(body["scanState"], "pending", "a file is invisible until the scan passes")
        self.assertEqual(body["contentHash"], "sha256:" + hashlib.sha256(PDF).hexdigest())
        self.assertEqual(body["sizeBytes"], len(PDF))
        self.assertEqual(body["mimeType"], "application/pdf")
        self.assertEqual(body["uploadedBy"]["id"], str(self.bank.person.id))
        stored = self.row(body["id"])
        self.assertEqual(get_storage().read(stored.storage_key), PDF)

    def test_a_hash_and_a_size_the_client_claims_are_ignored_for_the_servers_own(self) -> None:
        response = self.attach(
            {"kind": "file", "name": "Research criteria", "file": a_file(), "contentHash": "sha256:" + "0" * 64, "sizeBytes": "1"}
        )
        self.assertEqual(response.status_code, 201, response.content)
        stored = self.row(response.json()["evidence"]["id"])
        self.assertEqual(stored.content_hash, "sha256:" + hashlib.sha256(PDF).hexdigest())
        self.assertEqual(stored.size_bytes, len(PDF))

    def test_the_storage_key_is_the_tenant_the_case_and_a_random_part_never_the_name(self) -> None:
        first = self.row(self.attach_file(a_file(filename="../../etc/passwd.pdf")).json()["evidence"]["id"])
        second = self.row(self.attach_file().json()["evidence"]["id"])
        prefix = f"{self.bank.tenant.id}/cases/{self.bank.case.id}/evidence/"
        for stored in (first, second):
            self.assertTrue(stored.storage_key.startswith(prefix), stored.storage_key)
            self.assertNotIn("passwd", stored.storage_key)
            self.assertNotIn("criteria", stored.storage_key)
        self.assertNotEqual(first.storage_key, second.storage_key)

    def test_every_allowed_type_is_recognised_in_its_bytes(self) -> None:
        cases = [
            ("a.pdf", "application/pdf", PDF),
            ("a.docx", DOCX, ooxml("word/")),
            ("a.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ooxml("xl/")),
            ("a.pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation", ooxml("ppt/")),
            ("a.png", "image/png", b"\x89PNG\r\n\x1a\n" + b"\0" * 16),
            ("a.jpeg", "image/jpeg", b"\xff\xd8\xff\xe0" + b"\0" * 16),
            ("a.jpg", "image/jpeg", b"\xff\xd8\xff\xe0" + b"\0" * 16),
            ("a.txt", "text/plain", "Kontrollerat av compliance, 2026.\n".encode()),
            ("a.csv", "text/csv", b"account,limit\n1,200\n"),
            ("a.pdf", "application/octet-stream", PDF),
        ]
        for filename, content_type, content in cases:
            with self.subTest(filename=filename, content_type=content_type):
                response = self.attach_file(a_file(content, filename=filename, content_type=content_type))
                self.assertEqual(response.status_code, 201, response.content)
                self.assertNotEqual(response.json()["evidence"]["mimeType"], "application/octet-stream")

    def test_a_file_outside_the_allow_list_is_refused_before_a_byte_is_stored(self) -> None:
        refused = [
            ("an HTML page", "page.html", "text/html", b"<html><script>alert(1)</script></html>"),
            ("HTML bytes named and declared as a PDF", "memo.pdf", "application/pdf", b"<html><body>not a pdf</body></html>"),
            ("a PDF declared as a PNG", "memo.png", "image/png", PDF),
            ("a PDF with a Word extension", "memo.docx", "application/pdf", PDF),
            ("a zip that is not a Word document", "memo.docx", DOCX, ooxml("xl/")),
            ("a broken zip", "memo.docx", DOCX, b"PK\x03\x04 not really"),
            ("markup as plain text", "note.txt", "text/plain", b"  <svg onload=alert(1)>"),
            ("binary as plain text", "note.txt", "text/plain", b"MZ\x90\x00\x03\x00"),
            ("an executable", "tool.exe", "application/x-msdownload", b"MZ\x90\x00"),
            ("an empty file", "empty.pdf", "application/pdf", b""),
        ]
        for label, filename, content_type, content in refused:
            with self.subTest(label):
                response = self.attach_file(a_file(content, filename=filename, content_type=content_type))
                self.assertEqual(response.status_code, 422, response.content)
                problem = response.json()
                self.assertEqual(problem["code"], "validation_error")
                self.assertIn("PDF", problem["detail"], "the refusal names the allow-list")
                self.assertIn("25 MB", problem["detail"], "and the cap")
        self.assertEqual(self.stored_files(), 0)
        with transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            self.assertFalse(Evidence.objects.exists())

    @override_settings(EVIDENCE_MAX_BYTES=len(PDF) - 1)
    def test_a_file_over_the_cap_is_refused_before_a_byte_is_stored(self) -> None:
        response = self.attach_file()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")
        self.assertEqual(self.stored_files(), 0)

    @override_settings(EVIDENCE_ALLOWED_TYPES=["image/png"])
    def test_the_allow_list_is_the_setting(self) -> None:
        self.assertEqual(self.attach_file().status_code, 422, "a PDF is refused once the setting leaves it out")

    def test_the_file_part_goes_with_the_file_kind_only(self) -> None:
        missing = self.attach({"kind": "file", "name": "Research criteria"})
        self.assertEqual(missing.status_code, 422)
        extra = self.attach({"kind": "reference", "name": "Policy 12", "file": a_file()})
        self.assertEqual(extra.status_code, 422)
        self.assertEqual(self.stored_files(), 0)

    @override_settings(ENVIRONMENT="production", IS_DEPLOYED_ENVIRONMENT=True, SCANNER_PROVIDER="mock")
    def test_a_deployed_mock_scanner_answers_503_and_stores_nothing(self) -> None:
        response = self.attach_file()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "scanner_unavailable")
        self.assertEqual(self.stored_files(), 0)
        with transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            self.assertFalse(Evidence.objects.exists())

    def test_attaching_writes_one_audit_row_with_the_hash_and_never_the_name(self) -> None:
        body = self.attach_file(name=SECRET_NAME).json()["evidence"]
        rows = self.audit_rows(evidence_logic.ATTACHED)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].after["contentHash"], body["contentHash"])
        self.assertNotIn(SECRET_NAME, str(rows[0].after) + rows[0].summary + rows[0].subject_title)

    @override_settings(CASE_EVIDENCE_MAX=1)
    def test_a_case_holds_at_most_the_cap_of_live_evidence(self) -> None:
        self.assertEqual(self.attach({"kind": "reference", "name": "Policy 12"}).status_code, 201)
        refused = self.attach({"kind": "reference", "name": "Policy 13"})
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json()["code"], "evidence_limit_reached")

    def test_a_closed_or_dismissed_case_takes_no_evidence(self) -> None:
        for category in (CaseStatusCategory.CLOSED, CaseStatusCategory.DISMISSED):
            with self.subTest(category=category.value):
                bank = bank_with_case(category)
                response = self.attach({"kind": "reference", "name": "Policy 12"}, bank=bank)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["code"], "case_closed")


class AttachLinkAndReference(EvidenceTestCase):
    def test_a_link_stores_an_https_address_and_fetches_nothing(self) -> None:
        with mock.patch("socket.create_connection", side_effect=AssertionError("a link is never fetched")):
            response = self.attach({"kind": "link", "name": "FI decision memo", "url": "https://intranet.example.com/memo/42"})
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()["evidence"]
        self.assertEqual(body["url"], "https://intranet.example.com/memo/42")
        self.assertEqual(body["scanState"], "clean", "a link has no bytes to scan")
        self.assertIsNone(body["contentHash"])

    def test_a_link_must_be_https(self) -> None:
        for url in ("", "http://intranet.example.com/memo", "javascript:alert(1)", "https://", "file:///etc/passwd", "https://exa mple.com/"):
            with self.subTest(url=url):
                self.assertEqual(self.attach({"kind": "link", "name": "Memo", "url": url}).status_code, 422)

    def test_a_reference_stores_a_name_only(self) -> None:
        response = self.attach({"kind": "reference", "name": "Credit policy, section 4"})
        self.assertEqual(response.status_code, 201)
        body = response.json()["evidence"]
        self.assertEqual((body["name"], body["url"], body["sizeBytes"]), ("Credit policy, section 4", None, None))
        self.assertEqual(self.attach({"kind": "reference", "name": "Policy", "url": "https://example.com/"}).status_code, 422)


class ScanEvidence(EvidenceTestCase):
    def test_a_clean_file_becomes_clean_through_one_audit_row(self) -> None:
        evidence_id = self.attach_file().json()["evidence"]["id"]
        stored = self.row(evidence_id)
        self.assertEqual(stored.scan_state, ScanState.CLEAN.value)
        self.assertIsNotNone(stored.scanned_at)
        self.assertEqual(len(self.audit_rows(tasks.SCANNED)), 1)

    def test_an_infected_file_loses_its_bytes_and_keeps_its_row_and_hash(self) -> None:
        eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + EICAR_MARKER + b"!$H+H*"
        body = self.attach_file(a_file(eicar, filename="notes.txt", content_type="text/plain")).json()["evidence"]
        stored = self.row(body["id"])
        self.assertEqual(stored.scan_state, ScanState.INFECTED.value)
        self.assertEqual(stored.content_hash, "sha256:" + hashlib.sha256(eicar).hexdigest(), "the hash stays")
        self.assertFalse(get_storage().exists(stored.storage_key), "the bytes are gone")
        self.assertEqual(self.stored_files(), 0)
        response = self.download(body["id"])
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "scan_failed")

    @override_settings(EVIDENCE_SCAN_RETRIES=2)
    def test_a_failed_scan_is_retried_then_stays_error_and_cannot_be_downloaded(self) -> None:
        with mock.patch("apps.shared.adapters.scanner.MockScanner.scan", autospec=True, side_effect=lambda self, content, filename: _error()) as scan:
            body = self.attach_file(name=f"{MOCK_ERROR_MARKER}.pdf").json()["evidence"]
        self.assertEqual(scan.call_count, 3, "the first try and two retries")
        stored = self.row(body["id"])
        self.assertEqual(stored.scan_state, ScanState.ERROR.value)
        self.assertTrue(get_storage().exists(stored.storage_key), "an error is not a verdict: the bytes stay")
        self.assertEqual(self.download(body["id"]).json()["code"], "scan_failed")

    def test_a_retry_that_passes_is_clean(self) -> None:
        answers = iter([_error(), _clean()])
        with mock.patch("apps.shared.adapters.scanner.MockScanner.scan", autospec=True, side_effect=lambda *a, **k: next(answers)):
            body = self.attach_file().json()["evidence"]
        self.assertEqual(self.row(body["id"]).scan_state, ScanState.CLEAN.value)

    def test_the_marker_name_reaches_the_scanner_so_the_seed_can_fail_a_scan(self) -> None:
        body = self.attach_file(name=f"Scan {MOCK_ERROR_MARKER}").json()["evidence"]
        self.assertEqual(self.row(body["id"]).scan_state, ScanState.ERROR.value)

    def test_a_scan_that_already_ran_is_not_run_again(self) -> None:
        body = self.attach_file().json()["evidence"]
        with mock.patch("apps.shared.adapters.scanner.MockScanner.scan") as scan:
            tasks.scan_evidence(str(self.bank.tenant.id), body["id"])
        scan.assert_not_called()
        self.assertEqual(len(self.audit_rows(tasks.SCANNED)), 1)


def _error() -> Any:
    from apps.shared.adapters.scanner import ScanResult

    return ScanResult(state=ScanState.ERROR, signature=None, scanned_at=timezone.now())


def _clean() -> Any:
    from apps.shared.adapters.scanner import ScanResult

    return ScanResult(state=ScanState.CLEAN, signature=None, scanned_at=timezone.now())


class DownloadEvidence(EvidenceTestCase):
    def test_a_pending_file_is_409_and_writes_no_audit_row(self) -> None:
        body = self.attach_file(scan=False).json()["evidence"]
        response = self.download(body["id"])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "scan_pending")
        self.assertEqual(self.audit_rows(evidence_logic.DOWNLOADED), [])

    def test_a_clean_file_streams_as_an_attachment_of_its_type_with_one_audit_row_per_download(self) -> None:
        body = self.attach_file(name=SECRET_NAME).json()["evidence"]
        for n in (1, 2):
            response = self.download(body["id"])
            self.assertEqual(response.status_code, 200)
            content = b"".join(response.streaming_content) if response.streaming else response.content
            self.assertEqual(content, PDF)
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertTrue(response["Content-Disposition"].startswith("attachment"))
            self.assertIn("no-store", response["Cache-Control"])
            self.assertEqual(response["X-Content-Type-Options"], "nosniff")
            rows = self.audit_rows(evidence_logic.DOWNLOADED)
            self.assertEqual(len(rows), n, "exactly one audit row per download")
        self.assertEqual(rows[-1].actor_id, self.bank.person.id)
        self.assertEqual(rows[-1].subject_id, uuid.UUID(body["id"]))
        self.assertNotIn(SECRET_NAME, str(rows[-1].after) + rows[-1].summary)

    def test_the_saved_name_ends_in_the_checked_type_and_hides_nothing(self) -> None:
        cases = [
            ("AMLR gap analysis.pdf", "application/pdf", "AMLR gap analysis.pdf"),
            ("Research criteria", "application/pdf", "Research criteria.pdf"),
            ("Q3 controls.ps1", "text/plain", "Q3 controls.ps1.txt"),
            ("report\u202etxt.exe", "text/plain", "reporttxt.exe.txt"),
            ("Photo.JPG", "image/jpeg", "Photo.JPG"),
            ("\u200b\r\n", "text/csv", "evidence.csv"),
            ("page.html", "text/html", "page.html.bin"),
        ]
        for name, mime, saved in cases:
            with self.subTest(name=name):
                self.assertEqual(evidence_logic.download_name(name, mime), saved)
        body = self.attach_file(name="Q3 controls.ps1").json()["evidence"]
        self.assertIn('filename="Q3 controls.ps1.pdf"', self.download(body["id"])["Content-Disposition"])

    def test_a_link_or_a_reference_has_nothing_to_download(self) -> None:
        body = self.attach({"kind": "reference", "name": "Policy 12"}).json()["evidence"]
        self.assertEqual(self.download(body["id"]).status_code, 404)
        self.assertEqual(self.audit_rows(evidence_logic.DOWNLOADED), [])

    def test_a_stored_type_outside_the_allow_list_is_never_served_as_itself(self) -> None:
        body = self.attach_file().json()["evidence"]
        with transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            Evidence.objects.filter(pk=body["id"]).update(mime_type="text/html")
        self.assertEqual(self.download(body["id"])["Content-Type"], "application/octet-stream")

    def test_a_reader_downloads_too(self) -> None:
        body = self.attach_file().json()["evidence"]
        reader = user_principal(subject_id=self.bank.person.id, tenant_id=self.bank.tenant.id, permissions={perms.CASES_READ})
        with stub_session(reader):
            response = self.client.get(f"{V1}/evidence/{body['id']}/download", **AS_SESSION)
        self.assertEqual(response.status_code, 200)


class ListEvidence(EvidenceTestCase):
    def test_every_live_piece_is_listed_with_its_scan_state_newest_first(self) -> None:
        pending = self.attach_file(scan=False).json()["evidence"]["id"]
        link = self.attach({"kind": "link", "name": "Memo", "url": "https://intranet.example.com/memo"}).json()["evidence"]["id"]
        with stub_session(self.bank.principal):
            response = self.client.get(f"{V1}/changes/{self.bank.change_id}/evidence", **AS_SESSION)
        self.assertEqual(response.status_code, 200)
        page = response.json()
        self.assertEqual(page["total"], 2)
        self.assertEqual([item["id"] for item in page["items"]], [link, pending])
        self.assertEqual(page["items"][1]["scanState"], "pending", "a bank sees a file that is not yet usable")
        with stub_session(self.bank.principal):
            second = self.client.get(f"{V1}/changes/{self.bank.change_id}/evidence?limit=1&offset=1", **AS_SESSION).json()
        self.assertEqual(([item["id"] for item in second["items"]], second["total"]), ([pending], 2))

    def test_a_case_with_no_evidence_is_an_empty_page(self) -> None:
        with stub_session(self.bank.principal):
            response = self.client.get(f"{V1}/changes/{self.bank.change_id}/evidence", **AS_SESSION)
        self.assertEqual(response.json(), {"items": [], "total": 0})


class AnotherBank(EvidenceTestCase):
    def test_another_banks_evidence_is_404_everywhere_and_leaves_no_audit_row(self) -> None:
        body = self.attach_file().json()["evidence"]
        other = bank_with_case()
        with stub_session(other.principal):
            listed = self.client.get(f"{V1}/changes/{self.bank.change_id}/evidence", **AS_SESSION)
            downloaded = self.client.get(f"{V1}/evidence/{body['id']}/download", **AS_SESSION)
            removed = self.client.delete(f"{V1}/evidence/{body['id']}", **AS_SESSION)
            attached = self.client.post(f"{V1}/changes/{self.bank.change_id}/evidence", data={"kind": "reference", "name": "x"}, **AS_SESSION)
        for response in (listed, downloaded, removed, attached):
            self.assertEqual(response.status_code, 404)
        self.assertEqual(self.audit_rows(evidence_logic.DOWNLOADED), [])
        self.assertIsNone(self.row(body["id"]).removed_at)
        with transaction.atomic():
            tenancy.activate(other.tenant.id)
            self.assertFalse(AuditEvent.objects.filter(action__startswith="case.evidence").exists())


class NoFilenameInLogs(EvidenceTestCase):
    def test_upload_scan_and_download_log_no_filename_path_or_byte(self) -> None:
        """Every logger, the ones that do not propagate included, at DEBUG, formatted as
        production writes them; the scanner's own line proves the capture is live."""
        secret_file = "kista-branch-closure-minutes.pdf"
        with captured_logs() as written:
            body = self.attach_file(a_file(filename=secret_file), name=SECRET_NAME).json()["evidence"]
            self.download(body["id"])
        stored = self.row(body["id"])
        self.assertTrue(any("scan finished" in line for line in written), written)
        for line in written:
            for value in (SECRET_NAME, secret_file, "kista", stored.storage_key, "%PDF"):
                self.assertNotIn(value, line, "a log line carried tenant content")


class CaseStatusIsUntouched(EvidenceTestCase):
    def test_attaching_evidence_moves_no_case(self) -> None:
        self.attach_file()
        with transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            case = ChangeCase.objects.get(pk=self.bank.case.pk)
        self.assertEqual(case.status, CaseStatusCategory.IMPLEMENTING.value)
