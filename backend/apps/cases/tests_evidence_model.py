"""The evidence table (CAS-05; schema v0.3 `evidence`; INPUT_DELTAS §18).

A piece of evidence is a file, a link or a reference to an internal document on one case.
These tests prove at the database, as cw_app, that only a stored and hashed file ever
carries a storage key (so nothing half-written can be downloaded), that a scan's answer
names when it came, that another bank's case or a non-member is refused by the composite
keys, and that another bank reads nothing. In Python they prove that a new row starts
`pending`, never `clean`, and that evidence is removed, never deleted, keeping its name
and hash for the case file and the audit trail.
"""

from __future__ import annotations

import datetime
from functools import partial

from django.db import transaction
from django.utils import timezone

from apps.cases.models import Evidence, EvidenceKind, RemovedNotDeleted
from apps.cases.tests_models import CaseDatabaseTestCase, CaseZoneTestCase
from apps.shared import factories, tenancy
from apps.shared.adapters.scanner import ScanState

HASH = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"


class EvidenceAsTheAppRole(CaseDatabaseTestCase):
    def evidence(self, **fields: object) -> Evidence:  # compliance: allow-kwargs test helper forwarding model fields
        base: dict[str, object] = {"tenant": self.tenant_a, "case": self.case_a, "uploaded_by": self.owner, "name": "Policy v2.pdf"}
        return Evidence.objects.using("app").create(**{**base, **fields})

    def file(self, **fields: object) -> Evidence:  # compliance: allow-kwargs test helper forwarding model fields
        stored: dict[str, object] = {
            "kind": EvidenceKind.FILE.value,
            "storage_key": "evidence/policy-v2.pdf",
            "content_hash": HASH,
            "size_bytes": 48213,
            "mime_type": "application/pdf",
        }
        return self.evidence(**{**stored, **fields})

    def test_a_file_is_stored_hashed_sized_and_typed(self) -> None:
        for missing in ("storage_key", "content_hash", "mime_type"):
            self.refused(partial(self.file, **{missing: ""}), f"a file with no {missing}")
        self.refused(lambda: self.file(size_bytes=None), "a file with no size")
        with self.as_app():
            self.file()

    def test_a_link_has_a_url_and_no_file(self) -> None:
        self.refused(lambda: self.evidence(kind=EvidenceKind.LINK.value), "a link with no url")
        self.refused(
            lambda: self.evidence(kind=EvidenceKind.LINK.value, url="https://intranet.example/policy", storage_key="evidence/x"),
            "a link carrying a storage key",
        )
        with self.as_app():
            self.evidence(kind=EvidenceKind.LINK.value, url="https://intranet.example/policy")

    def test_a_reference_carries_no_file(self) -> None:
        self.refused(
            lambda: self.evidence(kind=EvidenceKind.REFERENCE.value, storage_key="evidence/x"), "a reference carrying a storage key"
        )
        self.refused(lambda: self.evidence(kind=EvidenceKind.REFERENCE.value, name=""), "evidence with no name")
        with self.as_app():
            self.evidence(kind=EvidenceKind.REFERENCE.value, name="Board minutes 2026-09, item 4")

    def test_a_scan_answer_names_when_it_came(self) -> None:
        self.refused(lambda: self.file(scan_state=ScanState.CLEAN.value), "clean with no scan time")
        with self.as_app():
            self.file(scan_state=ScanState.CLEAN.value, scanned_at=timezone.now())

    def test_another_banks_case_or_person_is_refused(self) -> None:
        self.refused(lambda: self.file(case=self.case_b), "evidence.case")
        self.refused(lambda: self.file(uploaded_by=self.outsider), "evidence.uploaded_by")

    def test_another_bank_reads_none_of_it(self) -> None:
        with self.as_app():
            self.file()
        with self.as_app():
            self.assertEqual(Evidence.objects.using("app").count(), 1)
        with self.as_app(self.tenant_b):
            self.assertEqual(Evidence.objects.using("app").count(), 0)


class EvidenceModelTests(CaseZoneTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.person = factories.member_user(self.tenant_a, roles=("compliance_officer",))
        self.row = self.case(self.tenant_a)

    def link(self, name: str) -> Evidence:
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            return Evidence.objects.create(
                tenant=self.tenant_a,
                case=self.row,
                kind=EvidenceKind.LINK.value,
                name=name,
                url="https://intranet.example/policy",
                uploaded_by=self.person,
            )

    def test_a_new_row_starts_pending_never_clean(self) -> None:
        """CAS-05: a file is invisible until the scan passes, and the default says so."""
        self.assertEqual(Evidence._meta.get_field("scan_state").default, ScanState.PENDING.value)
        evidence = self.link("Research policy on the intranet")
        self.assertEqual(evidence.scan_state, ScanState.PENDING.value)
        self.assertEqual(str(evidence), f"{self.row.pk}:link:Research policy on the intranet")
        self.assertIsNone(evidence.scanned_at)

    def test_evidence_belongs_to_a_case(self) -> None:
        """The case is required; evidence on a register entry is not built (INPUT_DELTAS §18)."""
        self.assertFalse(Evidence._meta.get_field("case").null)
        self.assertNotIn("tenant_obligation_id", {f.column for f in Evidence._meta.concrete_fields})

    def test_evidence_is_removed_and_never_deleted(self) -> None:
        """Nothing is overwritten: a removed row keeps its name and hash (CAS-05)."""
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            evidence = Evidence.objects.create(
                tenant=self.tenant_a,
                case=self.row,
                kind=EvidenceKind.FILE.value,
                name="Policy v2.pdf",
                storage_key="evidence/policy-v2.pdf",
                content_hash=HASH,
                size_bytes=48213,
                mime_type="application/pdf",
                uploaded_by=self.person,
            )
            with self.assertRaises(RemovedNotDeleted):
                evidence.delete()
            with self.assertRaises(RemovedNotDeleted):
                Evidence.objects.filter(pk=evidence.pk).delete()
            evidence.removed_at = timezone.now()
            evidence.save()
            stored = Evidence.objects.get(pk=evidence.pk)
        self.assertEqual((stored.name, stored.content_hash), ("Policy v2.pdf", HASH))
        self.assertIsNotNone(stored.removed_at)

    def test_the_newest_comes_first(self) -> None:
        older = self.link("First link")
        newer = self.link("Second link")
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            Evidence.objects.filter(pk=older.pk).update(uploaded_at=newer.uploaded_at - datetime.timedelta(hours=1))
            first = Evidence.objects.filter(case=self.row).first()
        self.assertEqual(first.pk if first else None, newer.pk)
