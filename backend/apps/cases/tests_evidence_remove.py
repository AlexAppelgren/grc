"""Removing evidence (CAS-05, playbook 4.3; c9-evidence).

Nothing is overwritten: a removal sets `removed_at` and nothing else. The row keeps its
name, its hash and its bytes' key for the case file and the audit trail, it leaves the
list and the download, and it no longer counts towards sign-off. A hard delete is refused
in Python and by the database.

Proven to fail 2026-09-25: with the removal writing `storage_key=""` beside `removed_at`
the "only removed_at changes" test failed naming the column.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.forms.models import model_to_dict

from apps.cases import evidence as evidence_logic
from apps.cases import logic
from apps.cases import testing as case_build
from apps.cases.models import Evidence, RemovedNotDeleted
from apps.cases.tests_evidence import AS_SESSION, V1, EvidenceTestCase, bank_with_case
from apps.shared import permissions as perms
from apps.shared import tenancy
from apps.shared.storage import get_storage
from apps.shared.testing import stub_session, user_principal
from apps.taxonomy.models import CaseStatusCategory


class RemoveEvidence(EvidenceTestCase):
    def remove(self, evidence_id: Any, *, principal: Any = None) -> Any:
        with stub_session(principal or self.bank.principal):
            return self.client.delete(f"{V1}/evidence/{evidence_id}", **AS_SESSION)

    def test_removal_sets_removed_at_only_and_writes_one_audit_row(self) -> None:
        body = self.attach_file().json()["evidence"]
        before = model_to_dict(self.row(body["id"]))
        response = self.remove(body["id"])
        self.assertEqual(response.status_code, 204)
        after = model_to_dict(self.row(body["id"]))
        self.assertIsNone(before.pop("removed_at"))
        self.assertIsNotNone(after.pop("removed_at"))
        self.assertEqual(after, before, "the row, its name and its hash stay as they were")
        self.assertTrue(get_storage().exists(self.row(body["id"]).storage_key), "the bytes stay for retention to purge (D-53)")
        self.assertEqual(len(self.audit_rows(evidence_logic.REMOVED)), 1)

    def test_a_removed_piece_leaves_the_list_the_download_and_the_sign_off_count(self) -> None:
        body = self.attach_file().json()["evidence"]
        with transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            self.assertEqual(logic.case_facts(self.bank.case, actor=None).clean_evidence_count, 1)
        self.remove(body["id"])
        with stub_session(self.bank.principal):
            listed = self.client.get(f"{V1}/changes/{self.bank.change_id}/evidence", **AS_SESSION).json()
        self.assertEqual(listed["total"], 0)
        self.assertEqual(self.download(body["id"]).status_code, 404)
        self.assertEqual(self.remove(body["id"]).status_code, 404, "a second removal finds nothing live")
        with transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            self.assertEqual(logic.case_facts(self.bank.case, actor=None).clean_evidence_count, 0)

    def test_a_hard_delete_is_impossible(self) -> None:
        body = self.attach_file().json()["evidence"]
        with transaction.atomic():
            tenancy.activate(self.bank.tenant.id)
            with self.assertRaises(RemovedNotDeleted):
                Evidence.objects.get(pk=body["id"]).delete()
            with self.assertRaises(RemovedNotDeleted):
                Evidence.objects.filter(pk=body["id"]).delete()

    def test_removal_needs_cases_work(self) -> None:
        body = self.attach_file().json()["evidence"]
        contributor = user_principal(
            subject_id=self.bank.person.id, tenant_id=self.bank.tenant.id, permissions={perms.CASES_READ, perms.CASES_CONTRIBUTE}
        )
        response = self.remove(body["id"], principal=contributor)
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(self.row(body["id"]).removed_at)

    def test_a_closed_cases_evidence_stays(self) -> None:
        body = self.attach({"kind": "reference", "name": "Policy 12"}).json()["evidence"]
        case_build.in_category(self.bank.case, CaseStatusCategory.CLOSED)
        response = self.remove(body["id"])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "case_closed")
        self.assertIsNone(self.row(body["id"]).removed_at)

    def test_another_banks_removal_is_404(self) -> None:
        body = self.attach({"kind": "reference", "name": "Policy 12"}).json()["evidence"]
        other = bank_with_case()
        self.assertEqual(self.remove(body["id"], principal=other.principal).status_code, 404)
        self.assertIsNone(self.row(body["id"]).removed_at)
