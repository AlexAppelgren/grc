"""Scenario tests for the taxonomy app (playbook 4.1, Appendix B): one method per
`@integration` scenario in app.md, each carrying its ID. Chunk 2 un-skips VOC-S1 to S7,
VOC-S11, VOC-S14, FP-S1 to S4 and I18N-S1, S2 (backend halves; screens follow in chunk 3).
FP-S6 (one decision per request, one waiting request) came with the regulatory scope work,
FP-S17 (the opt-in rule in both twins) with the standards dimension.
VOC-S8, S9, S10, S12, S13 stay skipped (R2, R3). Never delete a scenario without updating
app.md.

Operations exercised (the audit-on-write guard reads these names): createVocabularyRow,
updateVocabularyRow, reorderVocabulary, retireVocabularyRow, restoreVocabularyRow, mergeVocabularyRow,
suggestVocabularyRow, declineVocabularySuggestion, createTerm, updateTerm,
createFootprintRequest, approveFootprintRequest, rejectFootprintRequest,
withdrawFootprintRequest.

Prefixes hosted: ACC, FP, I18N, VOC.
"""

from __future__ import annotations

import itertools
import json
import uuid
from pathlib import Path
from typing import Any
from unittest import mock, skip

from django.apps import apps as django_apps
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.db.models import ForeignKey

import datetime

from apps.cases import matching as case_matching, testing as cases_build
from apps.cases.models import ChangeCase
from apps.identity.models import TenantRole, User
from apps.library.models import Authority, Instrument, Jurisdiction, Language, Obligation, ObligationTerm
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import load_library, seed_authorities
from apps.proposals.models import Proposal, ProposalKind, ProposalStatus
from apps.shared import factories, outbox, permissions as perms, tenancy
from apps.shared.audit import Actor
from apps.shared.models import AuditEvent
from apps.shared.routes import iter_operations
from apps.shared.tenancy import library_write
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.shared.vocabulary import LibraryVocabulary, TenantVocabulary
from apps.watch import testing as watch_build
from apps.taxonomy import tenant_lists_logic
from apps.taxonomy.models import (
    ApprovalStatus,
    FootprintChangeRequest,
    FootprintHistory,
    FootprintTerm,
    Tagging,
    TaxonomyTerm,
    TenantTag,
    TermDimension,
    Urgency,
    WatchedMarket,
)
from apps.taxonomy.registry import REGISTRY
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies
from config.api import api

APPS_DIR = Path(__file__).resolve().parent.parent
V1 = "/api/v1"
INPUT_DELTAS = APPS_DIR.parent.parent / "docs" / "inputs" / "INPUT_DELTAS.md"

# FP-S4's two chunk 6 surfaces are dated, so they need a clock that does not move with the
# suite (playbook 8.3). At this instant the bank's own day is 1 October 2026, the ISO week
# it falls in began on Monday 28 September, and both changes were sighted inside it.
FP_S4_INSTANT = datetime.datetime(2026, 9, 30, 22, 30, tzinfo=datetime.UTC)
FP_S4_SIGHTED = datetime.datetime(2026, 9, 29, 9, 0, tzinfo=datetime.UTC)
FP_S4_KEY_DATE = datetime.date(2026, 10, 15)

# Queries per read, measured 2026-09-19 and pinned so an N+1 shows up as a number (playbook
# 10). Every scenario request starts with the same ten: the scenario client's audit count
# (1), the request's savepoint pair (2), the auth layer (identity flag on, the session row,
# flag off, activate, membership permissions, latest step-up: 6) and the caller's user for
# the label order (1). One fewer than measured at chunk 2's close: a bank session no longer
# reads the platform role assignments at all (hardening H13). Then the caller's tenant for
# the label order (1) and the read's own queries, which do not grow with the number of rows:
# - a vocabulary list: the rows with their usage count (1) and their labels (1);
URGENCY_READ_QUERIES = 10 + 1 + 2
# - the footprint: the selected terms (1) and their labels (1), the dimensions with their
#   term counts (1) and their labels (1), the pending request (1); the markets (FP-04),
#   four more however many countries there are: the footprint read again for the operating
#   check (1), the watch rows (1), the countries (1) and their labels (1).
FOOTPRINT_READ_QUERIES = 10 + 1 + 5 + 4


def _seed_library() -> None:
    seed_languages()
    seed_jurisdictions()
    seed_library_vocabularies()
    seed_term_dimensions()
    seed_taxonomy_terms()


class TaxonomyScenarioTests(ScenarioTestCase):
    """Scenario tests for apps.taxonomy, one method per @integration scenario."""

    def setUp(self) -> None:
        _seed_library()
        self.tenant = factories.tenant(slug="bank")
        self.activate(self.tenant)
        ensure_tenant_vocabularies(self.tenant, actor=Actor.system("test"))
        self.admin = factories.member(self.tenant, roles=("admin",), user_row=factories.user(name="Erik Holm")).user
        self.officer = factories.member(
            self.tenant, roles=("compliance_officer",), user_row=factories.user(name="Sara Lindqvist")
        ).user
        self.approver = factories.member(self.tenant, roles=("approver",), user_row=factories.user(name="Maria Ek")).user
        self.reader = factories.member(self.tenant, roles=("reader",), user_row=factories.user(name="Oskar Lund")).user
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        self.second_editor = factories.platform_user(roles=("library_editor",), email="editor2@bleqq.test")

    # --- helpers --------------------------------------------------------------------------
    def _post(self, path: str, body: dict[str, Any] | None, headers: dict[str, Any], **extra: Any) -> Any:  # compliance: allow-kwargs test helper forwarding request headers
        return self.client.post(f"{V1}{path}", data=body or {}, content_type="application/json", **headers, **extra)

    def _patch(self, path: str, body: dict[str, Any], headers: dict[str, Any], **extra: Any) -> Any:  # compliance: allow-kwargs test helper forwarding request headers
        return self.client.patch(f"{V1}{path}", data=body, content_type="application/json", **headers, **extra)

    def _get(self, path: str, headers: dict[str, Any]) -> Any:
        return self.client.get(f"{V1}{path}", **headers)

    def _preview(self, path: str, body: dict[str, Any], headers: dict[str, Any]) -> Any:
        """A dry run is a read that needs a body: it answers 200 and writes nothing, not even
        an audit row (AUD-01 audits changes, and nothing changed). The scenario client fails
        any 2xx POST without an audit row, so previews go through a plain client."""
        return Client().post(f"{V1}{path}", data=body, content_type="application/json", **headers)

    def _create_tag(self, label: str, headers: dict[str, Any], **fields: Any) -> Any:  # compliance: allow-kwargs test helper spreading optional body fields
        body = {"labels": {"en": label}, **fields}
        return self._post("/vocab/tenant_tag", body, headers)

    def _tag(self, label: str, key: str | None = None) -> Any:
        response = self._create_tag(label, sign_in(self.admin, tenant=self.tenant), **({"key": key} if key else {}))
        self.assertEqual(response.status_code, 201, response.content)
        self.activate(self.tenant)
        return TenantTag.objects.get(tenant=self.tenant, key=response.json()["key"])

    def _tag_subjects(self, tag: TenantTag, count: int) -> None:
        self.activate(self.tenant)
        for n in range(count):
            Tagging.objects.create(tenant=self.tenant, tag=tag, subject_type="obligation", subject_id=uuid.uuid5(uuid.NAMESPACE_URL, f"{tag.key}-{n}"))

    def _rows(self, list_name: str, headers: dict[str, Any], **query: Any) -> dict[str, Any]:  # compliance: allow-kwargs test helper forwarding query parameters
        suffix = "&".join(f"{k}={v}" for k, v in query.items())
        response = self._get(f"/vocab/{list_name}" + (f"?{suffix}" if suffix else ""), headers)
        self.assertEqual(response.status_code, 200, response.content)
        return {row["key"]: row for row in response.json()["items"]}

    # --- VOC ------------------------------------------------------------------------------
    def test_voc_s1(self) -> None:
        """VOC-S1

        Extendable lists are rows in three tiers and kinds stay in code (VOC-01).
        """
        # Every tier 2 list of INPUT_DELTAS §1 is a library vocabulary; every tier 3 list a
        # tenant vocabulary with a tenant foreign key (under forced RLS, proven by the RLS guard).
        tier_two = {"instrument_level", "provision_kind", "change_type", "duty_type", "relation_type", "source_kind", "term_dimension", "urgency", "library_tag", "flag"}
        tier_three = {"tenant_tag", "compliance_status", "risk_rating", "link_kind", "effort_size", "case_sub_status", "dismissal_reason", "close_reason"}
        for name in tier_two:
            with self.subTest(list=name):
                entry = REGISTRY[name]
                self.assertEqual(entry.tier, 2)
                self.assertTrue(issubclass(entry.model, LibraryVocabulary))
        for name in tier_three:
            with self.subTest(list=name):
                entry = REGISTRY[name]
                self.assertEqual(entry.tier, 3)
                self.assertTrue(issubclass(entry.model, TenantVocabulary))
                tenant_fk = [f for f in entry.model._meta.get_fields() if isinstance(f, ForeignKey) and f.related_model._meta.label == "shared.Tenant"]
                self.assertEqual(len(tenant_fk), 1)
        # The registry and the list of lists agree, and the API states tier and count.
        response = self._get("/vocab", sign_in(self.reader, tenant=self.tenant))
        self.assertEqual(response.status_code, 200, response.content)
        listed = {item["list"]: item for item in response.json()["items"]}
        self.assertEqual(set(listed), set(REGISTRY))
        self.assertEqual(listed["urgency"]["tier"], 2)
        self.assertEqual(listed["urgency"]["count"], 5)
        self.assertEqual(listed["tenant_tag"]["tier"], 3)
        self.assertEqual(listed["change_type"]["kinds"], ["pre_adoption", "adopted", "in_force", "supervisory", "recurring"])
        # An instrument level's kind is optional and has one value (D-37).
        self.assertEqual((listed["instrument_level"]["kind"], listed["instrument_level"]["kinds"]), ("instrument_level_kind", ["standard"]))
        # Kinds stay in code: the only enums are the tier-one allowlist (the kinds-only guard
        # enumerates them); no vocabulary row's kind is ever an OpenAPI enum.
        schema = api.get_openapi_schema()
        entry_schema = schema["components"]["schemas"]["VocabularyRow"]
        self.assertNotIn("enum", entry_schema["properties"]["kind"])
        self.assertNotIn("enum", json.dumps(entry_schema["properties"]["key"]))

    def test_voc_s2(self) -> None:
        """VOC-S2

        An admin adds a change type, a tag and a sub-status without a deploy (VOC-01, AC-VOC1).
        """
        before = json.dumps(api.get_openapi_schema(), sort_keys=True)
        admin = sign_in(self.admin, tenant=self.tenant)
        # The tenant admin adds a tag and a sub-status under the category assessing.
        tag = self._create_tag("Custody", admin)
        self.assertEqual(tag.status_code, 201, tag.content)
        self.assertEqual(tag.json()["key"], "custody")
        sub = self._post("/vocab/case_sub_status", {"labels": {"en": "Waiting for legal"}, "kind": "assessing"}, admin)
        self.assertEqual(sub.status_code, 201, sub.content)
        self.assertEqual(sub.json()["kind"], "assessing")
        wrong_kind = self._post("/vocab/case_sub_status", {"labels": {"en": "Limbo"}, "kind": "purgatory"}, admin)
        self.assertEqual(wrong_kind.status_code, 422)
        self.assertEqual(wrong_kind.json()["code"], "unknown_key")
        # The editor's change type goes through a proposal (VOC-07); a second editor approves.
        editor = sign_in(self.editor)
        proposed = self._post("/vocab/change_type", {"labels": {"en": "Supervisory statement", "sv": "Tillsynsuttalande"}, "kind": "supervisory", "usageNote": "A statement of supervisory expectations."}, editor)
        self.assertEqual(proposed.status_code, 202, proposed.content)
        proposal = proposed.json()["proposal"]
        self.assertEqual(proposal["kind"], "vocabulary_create")
        self.assertEqual(proposal["status"], "open")
        self.assertNotIn("supervisory_statement", self._rows("change_type", admin))
        approved = self._post(f"/proposals/{proposal['id']}/approve", {}, sign_in(self.second_editor, step_up=True))
        self.assertEqual(approved.status_code, 200, approved.content)
        # Each appears in the picker read (same endpoint serves pickers, filters, pills and agents).
        change_types = self._rows("change_type", admin)
        self.assertEqual(change_types["supervisory_statement"]["label"], "Supervisory statement")
        self.assertEqual(change_types["supervisory_statement"]["kind"], "supervisory")
        self.assertIn("custody", self._rows("tenant_tag", admin))
        self.assertIn("waiting_for_legal", self._rows("case_sub_status", admin))
        # The agent vocabulary read (AGT-02) sees the library list through its key.
        key = factories.api_key(self.tenant, scopes=("library:read",))
        agent = self._get("/vocab/change_type", {"HTTP_X_API_KEY": key.plain_key})
        self.assertEqual(agent.status_code, 200, agent.content)
        self.assertIn("supervisory_statement", {row["key"] for row in agent.json()["items"]})
        no_scope = factories.api_key(self.tenant, scopes=("changes:write",))
        self.assertEqual(self._get("/vocab/change_type", {"HTTP_X_API_KEY": no_scope.plain_key}).status_code, 403)
        # The contract did not move.
        self.assertEqual(before, json.dumps(api.get_openapi_schema(), sort_keys=True))

    def test_voc_s3(self) -> None:
        """VOC-S3

        The vocabulary screen renders the real pill with usage count, rename and reorder (VOC-02).
        """
        admin = sign_in(self.admin, tenant=self.tenant)
        custody = self._tag("Custody")
        advice = self._tag("Advice")
        self._tag_subjects(custody, 3)
        rows = self._rows("tenant_tag", admin)
        self.assertEqual(rows["custody"]["usageCount"], 3)
        self.assertEqual(rows["advice"]["usageCount"], 0)
        self.assertEqual(rows["custody"]["kind"], None)
        # Inline rename: the label changes, the key and every record that carries it do not.
        renamed = self._patch("/vocab/tenant_tag/custody", {"labels": {"en": "Custody services"}}, admin, HTTP_IF_MATCH=str(rows["custody"]["version"]))
        self.assertEqual(renamed.status_code, 200, renamed.content)
        self.assertEqual(renamed.json()["label"], "Custody services")
        self.assertEqual(renamed.json()["key"], "custody")
        self.assertEqual(Tagging.objects.filter(tag=custody).count(), 3)
        stale = self._patch("/vocab/tenant_tag/custody", {"labels": {"en": "Custody again"}}, admin, HTTP_IF_MATCH=str(rows["custody"]["version"]))
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["code"], "stale_write")
        # Drag to reorder: sort_order is stored and the picker follows it.
        reordered = self._post("/vocab/tenant_tag/reorder", {"keys": ["custody", "advice"]}, admin)
        self.assertEqual(reordered.status_code, 200, reordered.content)
        order = [row["key"] for row in self._get("/vocab/tenant_tag", admin).json()["items"]]
        self.assertLess(order.index("custody"), order.index("advice"))
        custody.refresh_from_db()
        advice.refresh_from_db()
        self.assertLess(custody.sort_order, advice.sort_order)
        # Only vocab.manage writes; any member reads.
        reader = sign_in(self.reader, tenant=self.tenant)
        self.assertEqual(self._get("/vocab/tenant_tag", reader).status_code, 200)
        denied = self._create_tag("Lending", reader)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["requiredPermission"], perms.VOCAB_MANAGE)

    def test_voc_s4(self) -> None:
        """VOC-S4

        Retiring a used value keeps history readable and leaves pickers (VOC-02, AC-VOC2).
        """
        admin = sign_in(self.admin, tenant=self.tenant)
        custody = self._tag("Custody")
        self._tag_subjects(custody, 4)
        # The usage count comes first: the unconfirmed retire answers 409 in_use with the count.
        refused = self._post("/vocab/tenant_tag/custody/retire", {}, admin)
        self.assertEqual(refused.status_code, 409, refused.content)
        self.assertEqual(refused.json()["code"], "in_use")
        self.assertEqual(refused.json()["usageCount"], 4)
        retired = self._post("/vocab/tenant_tag/custody/retire", {"confirm": True}, admin)
        self.assertEqual(retired.status_code, 200, retired.content)
        self.assertEqual(retired.json(), {"key": "custody", "usageCount": 4, "retired": True})
        # The four records still carry the key and render its label; the picker no longer offers it.
        self.assertEqual(Tagging.objects.filter(tag=custody).count(), 4)
        self.assertNotIn("custody", self._rows("tenant_tag", admin))
        history = self._rows("tenant_tag", admin, includeRetired="true")
        self.assertEqual(history["custody"]["label"], "Custody")
        self.assertFalse(history["custody"]["active"])
        custody.refresh_from_db()
        self.assertFalse(custody.active)
        self.assertEqual(AuditEvent.objects.filter(action="vocabulary.retired", subject_id=custody.id).count(), 1)
        # Retire, never delete: a retired value can be restored, audited the same way.
        self.assertEqual(self._post("/vocab/tenant_tag/custody/retire", {"confirm": True}, admin).json()["code"], "invalid_transition")
        self.assertEqual(self._post("/vocab/tenant_tag/custody/restore", {}, sign_in(self.reader, tenant=self.tenant)).status_code, 403)
        restored = self._post("/vocab/tenant_tag/custody/restore", {}, admin)
        self.assertEqual(restored.status_code, 200, restored.content)
        self.assertEqual(restored.json(), {"key": "custody", "usageCount": 4, "restored": True})
        self.assertIn("custody", self._rows("tenant_tag", admin))
        self.assertEqual(AuditEvent.objects.filter(action="vocabulary.restored", subject_id=custody.id).count(), 1)
        self.assertEqual(self._post("/vocab/tenant_tag/custody/restore", {}, admin).json()["code"], "invalid_transition")
        # A library value is restored through a proposal (VOC-07), like every library write.
        self.assertEqual(self._post("/vocab/flag/ai/restore", {}, sign_in(self.editor)).json()["code"], "invalid_transition")

    def test_voc_s5(self) -> None:
        """VOC-S5

        Merging re-points duplicates in one audited transaction (VOC-02).
        """
        admin = sign_in(self.admin, tenant=self.tenant)
        custody = self._tag("Custody")
        svcs = self._tag("Custody svcs", key="custody_svcs")
        self._tag_subjects(custody, 2)
        self._tag_subjects(svcs, 3)
        # One record carries both, so re-pointing it must not violate the unique tagging.
        first_tagging = Tagging.objects.filter(tag=custody).order_by("id").first()  # ordering: any one of the tagged subjects will do
        assert first_tagging is not None
        shared_subject = first_tagging.subject_id
        Tagging.objects.create(tenant=self.tenant, tag=svcs, subject_type="obligation", subject_id=shared_subject)
        before = AuditEvent.objects.count()
        preview = self._preview("/vocab/tenant_tag/custody_svcs/merge?dryRun=true", {"into": "custody"}, admin)
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertEqual(preview.json(), {"from": "custody_svcs", "into": "custody", "usageCount": 4, "repointed": 3, "dryRun": True})
        self.assertEqual(Tagging.objects.filter(tag=svcs).count(), 4)
        self.assertEqual(AuditEvent.objects.count(), before, "a preview writes nothing, not even an audit row")
        # A failure halfway answers a problem and leaves nothing changed.
        with mock.patch.object(tenant_lists_logic, "record", side_effect=RuntimeError("audit failed")):
            with self.assertLogs("config.api", "ERROR"):
                failed = self._post("/vocab/tenant_tag/custody_svcs/merge", {"into": "custody"}, admin)
        self.assertEqual((failed.status_code, failed.json()["code"]), (500, "internal_error"))
        self.activate(self.tenant)
        self.assertEqual(Tagging.objects.filter(tag=svcs).count(), 4)
        self.assertTrue(TenantTag.objects.get(pk=svcs.pk).active)
        merged = self._post("/vocab/tenant_tag/custody_svcs/merge", {"into": "custody"}, admin)
        self.assertEqual(merged.status_code, 200, merged.content)
        self.assertEqual(merged.json()["repointed"], 3)
        self.assertEqual(Tagging.objects.filter(tag=svcs).count(), 0)
        self.assertEqual(Tagging.objects.filter(tag=custody).count(), 5)
        self.assertFalse(TenantTag.objects.get(pk=svcs.pk).active)
        event = AuditEvent.objects.get(action="vocabulary.merged", subject_id=svcs.id)
        self.assertEqual(event.after["into"], "custody")
        self.assertEqual(event.after["repointed"], 3)
        self.assertEqual(event.before["from"], "custody_svcs")

    def test_voc_s6(self) -> None:
        """VOC-S6

        Create where you use it offers Create or Suggest by permission (VOC-03).
        """
        # The backend half: a holder of vocab.manage creates; anyone else suggests, and the
        # suggestion lands with the admin (a tenant list) or in the proposal queue (a library list).
        reader = sign_in(self.reader, tenant=self.tenant)
        admin = sign_in(self.admin, tenant=self.tenant)
        self.assertEqual(self._create_tag("Lending", reader).status_code, 403)
        suggested = self._post("/vocab/tenant_tag/suggest", {"labels": {"en": "Lending"}, "usageNote": "Loans and credit."}, reader)
        self.assertEqual(suggested.status_code, 201, suggested.content)
        self.assertEqual(suggested.json()["key"], "lending")
        self.assertEqual(suggested.json()["suggestedBy"]["name"], "Oskar Lund")
        self.assertNotIn("lending", self._rows("tenant_tag", admin))
        self.assertEqual(self._get("/vocab/tenant_tag/suggestions", reader).status_code, 403)
        inbox = self._get("/vocab/tenant_tag/suggestions", admin)
        self.assertEqual(inbox.status_code, 200, inbox.content)
        self.assertEqual([s["key"] for s in inbox.json()["items"]], ["lending"])
        # The admin creates it (which resolves the suggestion) and declines another.
        created = self._create_tag("Lending", admin)
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(self._get("/vocab/tenant_tag/suggestions", admin).json()["total"], 0)
        other = self._post("/vocab/tenant_tag/suggest", {"labels": {"en": "Leasing"}}, reader).json()
        declined = self._post(f"/vocab/tenant_tag/suggestions/{other['id']}/decline", {}, admin)
        self.assertEqual(declined.status_code, 200, declined.content)
        self.assertEqual(declined.json()["status"], "declined")
        # A library list suggestion is a proposal of kind vocabulary_create.
        library = self._post("/vocab/flag/suggest", {"labels": {"en": "Client money"}}, reader)
        self.assertEqual(library.status_code, 202, library.content)
        self.assertEqual(library.json()["proposal"]["kind"], "vocabulary_create")
        self.assertEqual(library.json()["proposal"]["payload"]["list"], "flag")

    def test_voc_s7(self) -> None:
        """VOC-S7

        A near-duplicate is refused with the near match offered (VOC-03, AC-VOC3).
        """
        admin = sign_in(self.admin, tenant=self.tenant)
        self._tag("Custody")
        # Case-insensitive uniqueness with the trailing space stripped: the same value.
        same = self._create_tag("custody ", admin)
        self.assertEqual(same.status_code, 409, same.content)
        self.assertEqual(same.json()["code"], "duplicate_key")
        self.assertEqual(same.json()["candidates"][0]["key"], "custody")
        # The trigram check offers the near match; the brief fixes the status at 422.
        near = self._create_tag("Custdy", admin)
        self.assertEqual(near.status_code, 422, near.content)
        self.assertEqual(near.json()["code"], "near_duplicate")
        self.assertEqual(near.json()["candidates"][0]["key"], "custody")
        self.assertEqual(near.json()["candidates"][0]["label"], "Custody")
        # vocab.manage may insist.
        forced = self._create_tag("Custdy", admin, force=True)
        self.assertEqual(forced.status_code, 201, forced.content)
        # The suggest path gets the same hint.
        hint = self._post("/vocab/tenant_tag/suggest", {"labels": {"en": "Custodi"}}, sign_in(self.reader, tenant=self.tenant))
        self.assertEqual(hint.status_code, 422)
        self.assertEqual(hint.json()["code"], "near_duplicate")

    @skip("pending: VOC-S8 (VOC-04, R2)")
    def test_voc_s8(self) -> None:
        """VOC-S8

        Statuses live inside fixed categories and a category never goes empty (VOC-04).
        """

    @skip("pending: VOC-S9 (VOC-05, R2)")
    def test_voc_s9(self) -> None:
        """VOC-S9

        Tenant scales map to fixed ordinals and the tone follows the ordinal (VOC-05).
        """

    @skip("pending: VOC-S10 (VOC-06, R2)")
    def test_voc_s10(self) -> None:
        """VOC-S10

        Reason lists drive dismissal, closure and risk acceptance (VOC-06).
        """

    def test_voc_s11(self) -> None:
        """VOC-S11

        A library vocabulary change goes through the proposal queue (VOC-07).
        """
        editor = sign_in(self.editor)
        body = {"dimension": "service_type", "labels": {"en": "Payments", "sv": "Betalningar"}, "usageNote": "Payment services under PSD2."}
        proposed = self._post("/taxonomy/terms", body, editor)
        self.assertEqual(proposed.status_code, 202, proposed.content)
        proposal = proposed.json()["proposal"]
        self.assertEqual(proposal["kind"], "term_create")
        self.assertEqual(proposal["payload"]["key"], "payments")
        keys = {t["key"] for t in self._get("/taxonomy/terms?dimension=service_type", editor).json()["items"]}
        self.assertNotIn("payments", keys)
        # The proposer cannot approve it; a second editor can, with a fresh step-up.
        own = self._post(f"/proposals/{proposal['id']}/approve", {}, sign_in(self.editor, step_up=True))
        self.assertEqual(own.status_code, 409)
        self.assertEqual(own.json()["code"], "four_eyes_violation")
        stale = self._post(f"/proposals/{proposal['id']}/approve", {}, sign_in(self.second_editor))
        self.assertEqual(stale.status_code, 403)
        self.assertEqual(stale.json()["code"], "step_up_required")
        approved = self._post(f"/proposals/{proposal['id']}/approve", {}, sign_in(self.second_editor, step_up=True))
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.json()["status"], "approved")
        terms = {t["key"]: t for t in self._get("/taxonomy/terms?dimension=service_type", editor).json()["items"]}
        self.assertEqual(terms["payments"]["label"], "Payments")
        self.assertEqual(terms["payments"]["dimension"]["key"], "service_type")
        # Relabelling a term is a proposal too; the term keeps its key and its label until approval.
        relabel_term = self._patch(f"/taxonomy/terms/{terms['payments']['id']}", {"labels": {"en": "Payment services"}}, editor, HTTP_IF_MATCH="1")
        self.assertEqual(relabel_term.status_code, 202, relabel_term.content)
        self.assertEqual(relabel_term.json()["proposal"]["kind"], "term_update")
        self.assertEqual(relabel_term.json()["proposal"]["payload"]["key"], "payments")
        approved_term = self._post(f"/proposals/{relabel_term.json()['proposal']['id']}/approve", {}, sign_in(self.second_editor, step_up=True))
        self.assertEqual(approved_term.status_code, 200, approved_term.content)
        terms = {t["key"]: t for t in self._get("/taxonomy/terms?dimension=service_type", editor).json()["items"]}
        self.assertEqual(terms["payments"]["label"], "Payment services")
        self.assertEqual(terms["payments"]["version"], 2)
        stale_term = self._patch(f"/taxonomy/terms/{terms['payments']['id']}", {"labels": {"en": "Payments"}}, editor, HTTP_IF_MATCH="1")
        self.assertEqual(stale_term.json()["code"], "stale_write")
        # A relabel and a retire of a library row are proposals too, and the direct write
        # route for library vocabularies does not exist: every write answers 202 or 403.
        relabel = self._patch("/vocab/urgency/act_now", {"labels": {"en": "Act immediately"}}, editor, HTTP_IF_MATCH="1")
        self.assertEqual(relabel.status_code, 202, relabel.content)
        self.assertEqual(relabel.json()["proposal"]["kind"], "vocabulary_relabel")
        self.assertEqual(self._rows("urgency", editor)["act_now"]["label"], "Act now")
        paths = {(op.method, op.path) for op in iter_operations(api)}
        self.assertNotIn(("PUT", "/vocab/{list}/{key}"), paths)
        self.assertNotIn(("DELETE", "/vocab/{list}/{key}"), paths)
        agent = factories.api_key(self.tenant, scopes=("library:read", "proposals:write", "changes:write", "sources:write"))
        self.assertEqual(self._post("/taxonomy/terms", body, {"HTTP_X_API_KEY": agent.plain_key}).status_code, 401)
        # The reader has no proposals.create and cannot propose from the tenant either.
        self.assertEqual(self._post("/taxonomy/terms", body, sign_in(self.reader, tenant=self.tenant)).status_code, 403)
        officer = self._post("/taxonomy/terms", {**body, "labels": {"en": "Lending"}}, sign_in(self.officer, tenant=self.tenant))
        self.assertEqual(officer.status_code, 202, officer.content)

    @skip("pending: VOC-S12 (VOC-08, R2)")
    def test_voc_s12(self) -> None:
        """VOC-S12

        Bulk tagging from a list previews and writes one audit entry (VOC-08).
        """

    @skip("pending: VOC-S13 (VOC-09, R3)")
    def test_voc_s13(self) -> None:
        """VOC-S13

        Tenant configuration is versioned, exportable and importable (VOC-09).
        """

    def test_voc_s14(self) -> None:
        """VOC-S14

        System rows can be relabelled but not removed, and the API returns key and kind (VOC-01).
        """
        admin = sign_in(self.admin, tenant=self.tenant)
        editor = sign_in(self.editor)
        # A system row of a library list: relabel through a proposal, never retire.
        relabel = self._patch("/vocab/urgency/act_now", {"labels": {"en": "Act immediately"}}, editor, HTTP_IF_MATCH="1")
        self.assertEqual(relabel.status_code, 202, relabel.content)
        approved = self._post(f"/proposals/{relabel.json()['proposal']['id']}/approve", {}, sign_in(self.second_editor, step_up=True))
        self.assertEqual(approved.status_code, 200, approved.content)
        rows = self._rows("urgency", admin)
        self.assertEqual(rows["act_now"]["label"], "Act immediately")
        self.assertEqual(rows["act_now"]["key"], "act_now")
        retire = self._post("/vocab/urgency/act_now/retire", {"confirm": True}, editor)
        self.assertEqual(retire.status_code, 409, retire.content)
        self.assertEqual(retire.json()["code"], "system_row")
        # A system row of a tenant list: the same rule, directly.
        tenant_retire = self._post("/vocab/compliance_status/gap/retire", {"confirm": True}, admin)
        self.assertEqual(tenant_retire.status_code, 409)
        self.assertEqual(tenant_retire.json()["code"], "system_row")
        renamed = self._patch("/vocab/compliance_status/gap", {"labels": {"sv": "Avvikelse"}}, admin, HTTP_IF_MATCH="1")
        self.assertEqual(renamed.status_code, 200, renamed.content)
        self.assertEqual(renamed.json()["labels"]["sv"], "Avvikelse")
        self.assertEqual(renamed.json()["kind"], "gap")
        # GET /vocab/urgency returns key, kind (the tone) and label per language, never an enum.
        response = self._get("/vocab/urgency", admin)
        self.assertEqual(response.status_code, 200)
        by_key = {row["key"]: row for row in response.json()["items"]}
        self.assertEqual([r["key"] for r in response.json()["items"]], ["act_now", "within_3_months", "six_months_plus", "monitor", "no_action"])
        self.assertEqual(by_key["act_now"]["kind"], "negative")
        self.assertEqual(by_key["within_3_months"]["kind"], "warning")
        self.assertEqual(by_key["six_months_plus"]["kind"], "notice")
        self.assertEqual(by_key["monitor"]["kind"], "information")
        self.assertEqual(by_key["no_action"]["kind"], "positive")
        self.assertEqual(by_key["act_now"]["labels"]["sv"], "Agera nu")
        self.assertEqual(by_key["act_now"]["extra"], {"ordinal": 1, "slaDays": 14})
        self.assertTrue(by_key["monitor"]["isDefault"])
        self.assertEqual(Urgency.objects.get(key="act_now").kind, "negative")
        with self.assertNumQueries(URGENCY_READ_QUERIES):
            self._get("/vocab/urgency", admin)
        # Language order: the user's locale first, then the tenant's default, then en.
        self.activate(self.tenant)
        User.objects.filter(pk=self.admin.pk).update(locale=Language.objects.get(key="sv"))
        self.assertEqual(self._rows("urgency", sign_in(self.admin, tenant=self.tenant))["monitor"]["label"], "Bevaka")

    # --- FP -------------------------------------------------------------------------------
    def _footprint(self, headers: dict[str, Any]) -> dict[str, Any]:
        response = self._get("/tenant/footprint", headers)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _set_footprint(self, terms: list[str]) -> None:
        self.activate(self.tenant)
        FootprintTerm.objects.filter(tenant=self.tenant).delete()
        for ref in terms:
            dimension, key = ref.split(":")
            term = tenant_lists_logic.term_by_ref(dimension, key)
            FootprintTerm.objects.create(tenant=self.tenant, term=term, added_by=self.admin)

    def test_fp_s1(self) -> None:
        """FP-S1

        A record matches when every dimension it carries has a term in the footprint (FP-01).
        """
        from apps.taxonomy import matching

        self._set_footprint(["service_type:custody", "service_type:portfolio_management", "regime:securities"])
        footprint = matching.footprint_of(self.tenant.id)
        restricting = matching.restricting_dimensions()
        self.assertEqual(footprint["service_type"], {"custody", "portfolio_management"})
        self.assertNotIn("client_category", footprint)
        # An empty client category dimension in the footprint does not restrict.
        self.assertTrue(matching.in_footprint({"service_type": {"custody"}, "client_category": {"retail"}}, footprint, restricting=restricting))
        self.assertFalse(matching.in_footprint({"service_type": {"advice"}}, footprint, restricting=restricting))
        # No scope terms at all: matches every tenant ("Not client-specific").
        self.assertTrue(matching.in_footprint({}, footprint, restricting=restricting))
        # A dimension that does not restrict the footprint is ignored (channel).
        self.assertNotIn("channel", restricting)
        self.assertTrue(matching.in_footprint({"service_type": {"custody"}, "channel": {"branch"}}, footprint, restricting=restricting))
        # A term of an opt-in dimension matches only a footprint that names it: the empty
        # standards group hides it, where an empty scope group would not.
        standard = {"standard": {"iso_iec_27001"}}
        self.assertFalse(matching.in_footprint(standard, footprint, restricting=restricting))
        self.assertTrue(matching.in_footprint(standard, {**footprint, **standard}, restricting=restricting))
        # The SQL function mirrors the Python rule against the real rows.
        custody = tenant_lists_logic.term_by_ref("service_type", "custody")
        advice = tenant_lists_logic.term_by_ref("service_type", "advice")
        retail = tenant_lists_logic.term_by_ref("client_category", "retail")
        branch = tenant_lists_logic.term_by_ref("channel", "branch")
        # Seeded inactive until its doors guard it (tests_matching.HeldStandard); the rule
        # ignores a term's state.
        iso = TaxonomyTerm.objects.get(dimension__key="standard", key="iso_iec_27001")
        self.assertTrue(matching.in_footprint_sql(self.tenant.id, [custody.id, retail.id]))
        self.assertFalse(matching.in_footprint_sql(self.tenant.id, [advice.id]))
        self.assertTrue(matching.in_footprint_sql(self.tenant.id, []))
        self.assertTrue(matching.in_footprint_sql(self.tenant.id, [custody.id, branch.id]))
        self.assertFalse(matching.in_footprint_sql(self.tenant.id, [advice.id, branch.id]))
        self.assertFalse(matching.in_footprint_sql(self.tenant.id, [custody.id, iso.id]))
        # The footprint read states the rule per dimension and shows the pending request slot.
        view = self._footprint(sign_in(self.reader, tenant=self.tenant))
        by_dimension = {d["dimension"]["key"]: d for d in view["dimensions"]}
        self.assertEqual({t["key"] for t in by_dimension["service_type"]["terms"]}, {"custody", "portfolio_management"})
        self.assertEqual(by_dimension["client_category"]["terms"], [])
        self.assertTrue(by_dimension["service_type"]["restrictsFootprint"])
        self.assertFalse(by_dimension["channel"]["restrictsFootprint"])
        self.assertFalse(by_dimension["service_type"]["allSelected"])
        # Each dimension says its kind, so a reader can tell "no restriction" from "none followed".
        self.assertEqual(
            {key: by_dimension[key]["dimension"]["kind"] for key in ("service_type", "theme", "standard")},
            {"service_type": "scope", "theme": "classification", "standard": "opt_in"},
        )
        self.assertEqual((by_dimension["standard"]["terms"], by_dimension["standard"]["restrictsFootprint"]), ([], True))
        self.assertIsNone(view["pendingRequest"])
        self.assertEqual(by_dimension["service_type"]["terms"][0]["kind"], None)
        reader = sign_in(self.reader, tenant=self.tenant)
        with self.assertNumQueries(FOOTPRINT_READ_QUERIES):
            self._get("/tenant/footprint", reader)

    def test_fp_s2(self) -> None:
        """FP-S2

        A footprint change previews, waits for a second person and audits per term (FP-02, AC-FP1).
        """
        seed_authorities()
        load_library()
        self._set_footprint(["service_type:advice", "service_type:custody", "regime:securities"])
        officer = sign_in(self.officer, tenant=self.tenant)
        body = {"adds": [{"dimension": "client_category", "key": "retail"}], "removes": [{"dimension": "service_type", "key": "advice"}]}
        # Dry run first (playbook 15: dry run, preview, commit): the same preview, nothing written.
        writes_before = (AuditEvent.objects.count(), FootprintChangeRequest.objects.count())
        dry = self._preview("/tenant/footprint/requests?dryRun=true", body, officer)
        self.assertEqual(dry.status_code, 200, dry.content)
        self.assertTrue(dry.json()["dryRun"])
        self.assertEqual([t["key"] for t in dry.json()["removes"]], ["advice"])
        # Five of the eight obligations in scope are advised business the change would hide
        # (the Norwegian suitability duty among them, since portfolio management is outside
        # this footprint); adding retail hides none, because the client category group was
        # empty before.
        self.assertEqual(dry.json()["preview"]["obligations"], {"hidden": 5, "revealed": 0, "available": True})
        # The other direction: widening the regimes reveals two insurance obligations it hid.
        widen = {"adds": [{"dimension": "regime", "key": "insurance"}], "removes": []}
        wider = self._preview("/tenant/footprint/requests?dryRun=true", widen, officer)
        self.assertEqual(wider.json()["preview"]["obligations"], {"hidden": 0, "revealed": 2, "available": True})
        self.assertEqual((AuditEvent.objects.count(), FootprintChangeRequest.objects.count()), writes_before)
        self.assertIsNone(self._footprint(officer)["pendingRequest"])
        self.assertEqual(self._preview("/tenant/footprint/requests?dryRun=true", body, sign_in(self.reader, tenant=self.tenant)).status_code, 403)
        created = self._post("/tenant/footprint/requests", body, officer)
        self.assertEqual(created.status_code, 201, created.content)
        request = created.json()
        self.assertEqual(request["status"], "pending")
        self.assertEqual(request["requestedBy"]["name"], "Sara Lindqvist")
        self.assertEqual([t["key"] for t in request["removes"]], ["advice"])
        self.assertEqual(request["removes"][0]["label"], "Advice")
        # The preview lists what would be hidden and revealed per record kind; the kinds that
        # have no table yet say so instead of pretending.
        self.assertEqual(request["preview"]["obligations"], {"hidden": 5, "revealed": 0, "available": True})
        self.assertEqual(request["preview"]["cases"], {"hidden": 0, "revealed": 0, "available": False})
        self.assertEqual(self._footprint(officer)["pendingRequest"]["id"], request["id"])
        # The library changes while the request waits: the suitability statement now covers
        # custody too, so removing Advice no longer hides it. A waiting request is counted
        # again on every read, so the approver decides against today's library.
        with library_write("test"):
            ObligationTerm.objects.create(
                obligation=Obligation.objects.get(stable_key="obl-suitability-statement"),
                term=tenant_lists_logic.term_by_ref("service_type", "custody"),
            )
        today = {"hidden": 4, "revealed": 0, "available": True}
        self.assertEqual(self._footprint(officer)["pendingRequest"]["preview"]["obligations"], today)
        # One pending request at a time; an unknown term is refused with the valid keys.
        again = self._post("/tenant/footprint/requests", body, officer)
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["code"], "request_pending")
        # The footprint itself has not moved.
        self.assertIn("advice", {t["key"] for d in self._footprint(officer)["dimensions"] for t in d["terms"]})
        # An approver needs footprint.approve and a fresh step-up.
        self.assertEqual(self._post(f"/tenant/footprint/requests/{request['id']}/approve", {}, sign_in(self.reader, tenant=self.tenant)).status_code, 403)
        no_step_up = self._post(f"/tenant/footprint/requests/{request['id']}/approve", {}, sign_in(self.approver, tenant=self.tenant))
        self.assertEqual(no_step_up.status_code, 403)
        self.assertEqual(no_step_up.json()["code"], "step_up_required")
        approver = sign_in(self.approver, tenant=self.tenant, step_up=True)
        stale = self._post(f"/tenant/footprint/requests/{request['id']}/approve", {}, approver, HTTP_IF_MATCH="99")
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["code"], "stale_write")
        approved = self._post(f"/tenant/footprint/requests/{request['id']}/approve", {"note": "Advice was wound down in June."}, approver, HTTP_IF_MATCH=str(request["version"]))
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.json()["status"], "approved")
        self.assertEqual(approved.json()["decidedBy"]["name"], "Maria Ek")
        terms = {t["key"] for d in self._footprint(officer)["dimensions"] for t in d["terms"]}
        self.assertNotIn("advice", terms)
        self.assertIn("retail", terms)
        # One audit event per term with the assertion reference, and one history row per term.
        self.activate(self.tenant)
        events = AuditEvent.objects.filter(action__in=("footprint.term_added", "footprint.term_removed"), tenant=self.tenant)
        self.assertEqual(events.count(), 2)
        assertion_ids = {e.step_up_assertion_id for e in events}
        self.assertEqual(len(assertion_ids), 1)
        self.assertIsNotNone(assertion_ids.pop())
        history = FootprintHistory.objects.filter(tenant=self.tenant, request_id=request["id"]).order_by("action")
        self.assertEqual([(h.action, h.term.key) for h in history], [("added", "retail"), ("removed", "advice")])
        # The decision keeps the counts it was taken against, not the ones from when the
        # request was sent: the request shows what its audit row says.
        decision = AuditEvent.objects.get(action="footprint.change_approved", tenant=self.tenant)
        self.assertEqual(decision.after["preview"]["obligations"], today)
        self.assertEqual(approved.json()["preview"], decision.after["preview"])
        self.assertEqual(FootprintChangeRequest.objects.get(pk=request["id"]).preview, decision.after["preview"])
        # Nothing else can happen to a decided request.
        twice = self._post(f"/tenant/footprint/requests/{request['id']}/approve", {}, approver, HTTP_IF_MATCH="2")
        self.assertEqual(twice.status_code, 409)
        self.assertEqual(twice.json()["code"], "invalid_transition")
        self.assertIsNone(self._footprint(officer)["pendingRequest"])
        # The list of requests carries the decision.
        listed = self._get("/tenant/footprint/requests", officer)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["total"], 1)
        self.assertEqual(listed.json()["items"][0]["decisionNote"], "Advice was wound down in June.")
        self.assertEqual(listed.json()["items"][0]["preview"], decision.after["preview"])
        # A request can be rejected with a note, or withdrawn by its requester. Adding
        # portfolio management would bring back four securities obligations; by the time it
        # is rejected the ESMA warnings cover it too, and the rejection keeps that count.
        widening = {"adds": [{"dimension": "service_type", "key": "portfolio_management"}], "removes": []}
        rejected_request = self._post("/tenant/footprint/requests", widening, officer).json()
        self.assertEqual(rejected_request["preview"]["obligations"], {"hidden": 0, "revealed": 4, "available": True})
        with library_write("test"):
            ObligationTerm.objects.create(
                obligation=Obligation.objects.get(stable_key="obl-esma-warnings"),
                term=tenant_lists_logic.term_by_ref("service_type", "portfolio_management"),
            )
        rejected = self._post(f"/tenant/footprint/requests/{rejected_request['id']}/reject", {"note": "Not yet."}, approver, HTTP_IF_MATCH="1")
        self.assertEqual(rejected.status_code, 200, rejected.content)
        self.assertEqual(rejected.json()["status"], "rejected")
        self.activate(self.tenant)
        rejection = AuditEvent.objects.get(action="footprint.change_rejected", tenant=self.tenant)
        self.assertEqual(rejection.after["preview"]["obligations"], {"hidden": 0, "revealed": 5, "available": True})
        self.assertEqual(rejected.json()["preview"], rejection.after["preview"])
        withdrawn_request = self._post("/tenant/footprint/requests", {"adds": [{"dimension": "channel", "key": "digital"}], "removes": []}, officer).json()
        self.assertEqual(self._post(f"/tenant/footprint/requests/{withdrawn_request['id']}/withdraw", {}, approver, HTTP_IF_MATCH="1").status_code, 403)
        withdrawn = self._post(f"/tenant/footprint/requests/{withdrawn_request['id']}/withdraw", {}, officer, HTTP_IF_MATCH="1")
        self.assertEqual(withdrawn.status_code, 200, withdrawn.content)
        self.assertEqual(withdrawn.json()["status"], "withdrawn")
        self.activate(self.tenant)
        withdrawal = AuditEvent.objects.get(action="footprint.change_withdrawn", tenant=self.tenant)
        self.assertEqual(withdrawn.json()["preview"], withdrawal.after["preview"])
        unknown = self._post("/tenant/footprint/requests", {"adds": [{"dimension": "service_type", "key": "lending"}], "removes": []}, officer)
        self.assertEqual(unknown.status_code, 422)
        self.assertEqual(unknown.json()["code"], "unknown_key")
        self.assertIn("custody", unknown.json()["detail"])

    def test_fp_s3(self) -> None:
        """FP-S3

        The requester cannot approve their own footprint change (FP-02).
        """
        self._set_footprint(["service_type:advice"])
        # The admin holds both footprint.request and footprint.approve, like Anna would.
        admin = sign_in(self.admin, tenant=self.tenant, step_up=True)
        request = self._post("/tenant/footprint/requests", {"adds": [{"dimension": "service_type", "key": "custody"}], "removes": []}, admin).json()
        own = self._post(f"/tenant/footprint/requests/{request['id']}/approve", {}, admin, HTTP_IF_MATCH="1")
        self.assertEqual(own.status_code, 409, own.content)
        self.assertEqual(own.json()["code"], "four_eyes_violation")
        self.assertEqual(FootprintChangeRequest.objects.get(pk=request["id"]).status, ApprovalStatus.PENDING.value)
        # The database check constraint refuses the row on its own.
        with self.assertRaises(Exception) as caught:  # compliance: allow-broad-except the driver raises IntegrityError for a CHECK violation
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("UPDATE footprint_change_request SET decided_by_id = requested_by_id WHERE id = %s", [request["id"]])
        self.assertIn("four_eyes", str(caught.exception))

    def _drop_advice_from_the_footprint(self) -> None:
        """A footprint change as FP-02 has it: one person asks, a second approves it with a
        passkey step-up, and the recomputation runs off the event the approval recorded
        (`apps/cases/matching.py`, on the one outbox cursor)."""
        case_matching.register()
        officer = sign_in(self.officer, tenant=self.tenant)
        approver = sign_in(self.approver, tenant=self.tenant, step_up=True)
        request = self._post(
            "/tenant/footprint/requests",
            {"adds": [], "removes": [{"dimension": "service_type", "key": "advice"}]},
            officer,
        ).json()
        approved = self._post(
            f"/tenant/footprint/requests/{request['id']}/approve", {}, approver, HTTP_IF_MATCH="1"
        )
        self.assertEqual(approved.status_code, 200, approved.content)
        with transaction.atomic():
            tenancy.clear_tenant()
        while outbox.deliver_batch().delivered:
            pass

    def test_fp_s4(self) -> None:
        """FP-S4

        Every surface respects the footprint and offers a way to look outside it (FP-03).

        Two halves. First the rule itself, which every surface calls rather than restating.
        Then the two surfaces chunk 6 added — the roadmap and the briefing — proved to leave
        an advice-only record out. The feed and the inventory are proved where they were
        built, and the "Show outside our scope" switch is the inventory's; the reports are
        the note under this scenario in app.md, because every one of them reads the
        obligation register and R1 has none.
        """
        # The backend rule the surfaces apply from chunk 3 on: one function, one SQL mirror,
        # and the dimension flag that says which dimensions restrict. The feed, inventory,
        # roadmap and briefing call these; the "show outside footprint" switch is the same
        # query without the predicate.
        from apps.taxonomy import matching

        self._set_footprint(["service_type:custody", "regime:securities"])
        advice = tenant_lists_logic.term_by_ref("service_type", "advice")
        custody = tenant_lists_logic.term_by_ref("service_type", "custody")
        records = {"advice-only": [advice.id], "custody": [custody.id], "unscoped": []}
        inside = {name for name, term_ids in records.items() if matching.in_footprint_sql(self.tenant.id, term_ids)}
        self.assertEqual(inside, {"custody", "unscoped"})
        outside = set(records) - inside
        self.assertEqual(outside, {"advice-only"})
        self.assertEqual(
            matching.restricting_dimensions(),
            {"regime", "account_type", "legal_entity", "service_type", "client_category", "jurisdiction", "licensed_activity", "product_type", "standard"},
        )

        # The roadmap and the briefing: one dated change inside the scope and one outside it,
        # both sighted this week and both still open, so the only thing separating them is
        # the footprint verdict the case carries.
        #
        # The advice-only case is put outside the scope the way a bank really puts it there:
        # the bank held Advice when both cases were opened, a second person approved dropping
        # it, and the recomputation re-decided every open case (apps/cases/matching.py).
        # Seeding the column false would have proved the roadmap's query and not the rule,
        # which is exactly why FP-S4's journey could not be driven end to end.
        watch_build.seed_watch_reference()
        self._set_footprint(["service_type:custody", "service_type:advice", "regime:securities"])
        ours = watch_build.change(
            title="FI adopts amended rules on paying for investment research",
            key_date=FP_S4_KEY_DATE,
            key_date_label="In force",
            first_seen_at=FP_S4_SIGHTED,
        )
        theirs = watch_build.change(
            title="Advice-only guidance on suitability",
            key_date=FP_S4_KEY_DATE,
            key_date_label="In force",
            first_seen_at=FP_S4_SIGHTED,
        )
        watch_build.term_link(ours, term_ref="service_type:custody")
        watch_build.term_link(theirs, term_ref="service_type:advice")
        cases_build.case(self.tenant, ours)
        cases_build.case(self.tenant, theirs)
        self._drop_advice_from_the_footprint()
        self.activate(self.tenant)
        self.assertEqual(
            {case.change_id: case.footprint_match for case in ChangeCase.objects.all()},
            {ours.id: True, theirs.id: False},
            "dropping Advice re-decided the advice-only case and left the other alone",
        )
        # The session is minted at the frozen instant too: one created at the real clock
        # would be days old to the request and answer 401 (playbook 8.3).
        with mock.patch("django.utils.timezone.now", return_value=FP_S4_INSTANT):
            headers = sign_in(self.reader, tenant=self.tenant)
            roadmap = self._get("/roadmap", headers)
            briefing = self._get("/briefings/current", headers)
        for name, response in (("roadmap", roadmap), ("briefing", briefing)):
            with self.subTest(surface=name):
                self.assertEqual(response.status_code, 200, response.content)
                titles = [item["title"] for item in response.json()["items"]]
                self.assertIn(ours.title, titles)
                self.assertNotIn(theirs.title, titles)

    def test_fp_s6(self) -> None:
        """FP-S6

        One decision per request, and one waiting request per organisation (FP-02). The races
        (approve against withdraw, approve against approve, two creates), each on two cw_app
        connections, are proved in tests_footprint.py.
        """
        self._set_footprint(["service_type:advice"])
        officer = sign_in(self.officer, tenant=self.tenant)
        approver = sign_in(self.approver, tenant=self.tenant, step_up=True)
        body = {"adds": [{"dimension": "client_category", "key": "retail"}], "removes": [{"dimension": "service_type", "key": "advice"}]}
        request = self._post("/tenant/footprint/requests", body, officer).json()
        again = self._post("/tenant/footprint/requests", body, officer)
        self.assertEqual(again.status_code, 409, again.content)
        self.assertEqual(again.json()["code"], "request_pending")
        # The database refuses a second waiting request on its own.
        self.activate(self.tenant)
        with self.assertRaises(IntegrityError) as caught, transaction.atomic():
            FootprintChangeRequest.objects.create(tenant=self.tenant, requested_by=self.officer)
        self.assertIn("footprint_change_request_one_pending", str(caught.exception))
        approved = self._post(f"/tenant/footprint/requests/{request['id']}/approve", {}, approver, HTTP_IF_MATCH="1")
        self.assertEqual(approved.status_code, 200, approved.content)
        # Each term's event names the request that caused it.
        self.activate(self.tenant)
        events = AuditEvent.objects.filter(tenant=self.tenant, action__in=("footprint.term_added", "footprint.term_removed"), actor_id=self.approver.id)
        self.assertEqual(sorted((e.action, (e.after or e.before)["request"]) for e in events), [("footprint.term_added", request["id"]), ("footprint.term_removed", request["id"])])
        # A decided request takes no second decision, whoever sends it.
        for path, headers in (("reject", approver), ("withdraw", officer), ("approve", approver)):
            late = self._post(f"/tenant/footprint/requests/{request['id']}/{path}", {"note": "Late."}, headers)
            self.assertEqual((late.status_code, late.json()["code"]), (409, "invalid_transition"), path)
        # Once decided, the organisation may wait on a new request again.
        self.assertEqual(self._post("/tenant/footprint/requests", {"adds": [{"dimension": "channel", "key": "digital"}], "removes": []}, officer).status_code, 201)

    # --- I18N -----------------------------------------------------------------------------
    def test_i18n_s1(self) -> None:
        """I18N-S1

        Languages and jurisdictions are rows, never columns or branches (I18N-01).
        """
        headers = sign_in(self.reader, tenant=self.tenant)
        languages = self._get("/reference/languages", headers)
        self.assertEqual(languages.status_code, 200, languages.content)
        # Reference reads are short fixed lists answered as arrays, never paginated (chunk 1's
        # `GET /reference/languages`, INPUT_DELTAS section 7); data lists answer `{items, total}`.
        self.assertEqual([lang["key"] for lang in languages.json()], ["da", "en", "fi", "nb", "sv"])
        jurisdictions = self._get("/reference/jurisdictions", headers)
        self.assertEqual(jurisdictions.status_code, 200, jurisdictions.content)
        by_key = {j["key"]: j for j in jurisdictions.json()}
        self.assertEqual(set(by_key), {"eu", "se", "dk", "no", "fi", "intl"})
        self.assertEqual(by_key["se"]["kind"], "country")
        self.assertEqual(by_key["eu"]["kind"], "supranational")
        # The row standards bodies issue under (D-38): reached by nothing, named by its kind.
        self.assertEqual(
            (by_key["intl"]["kind"], by_key["intl"]["parentKey"], by_key["intl"]["label"]), ("international", None, "International")
        )
        self.assertEqual(by_key["se"]["parentKey"], "eu")
        self.assertEqual(by_key["se"]["defaultLanguage"]["key"], "sv")
        self.assertEqual(by_key["se"]["label"], "Sweden")
        # No model column names a language or a country; the references are foreign keys.
        for model in django_apps.get_models():
            for field in model._meta.get_fields():
                name = field.name.lower()
                self.assertNotRegex(name, r"_(sv|en|da|nb|fi|no)$", f"{model._meta.label}.{field.name} names a language")
                self.assertNotRegex(name, r"(swedish|danish|norwegian|finnish|english)", f"{model._meta.label}.{field.name} names a language")
        self.assertIsInstance(User._meta.get_field("locale"), ForeignKey)
        self.assertIs(User._meta.get_field("locale").related_model, Language)
        self.assertIsInstance(Jurisdiction._meta.get_field("default_language"), ForeignKey)
        # An instrument's and an authority's jurisdiction reference the jurisdiction table.
        for model in (Instrument, Authority):
            self.assertIsInstance(model._meta.get_field("jurisdiction"), ForeignKey)
            self.assertIs(model._meta.get_field("jurisdiction").related_model, Jurisdiction)
        # No code branch names a country or a language in the taxonomy and library apps.
        for path in sorted((APPS_DIR / "taxonomy").glob("*.py")) + sorted((APPS_DIR / "library").glob("*.py")):
            if path.name.startswith("tests_"):
                continue
            source = path.read_text(encoding="utf-8")
            self.assertNotRegex(source, r"==\s*['\"](se|sv|dk|da|no|nb|fi|en|eu)['\"]", f"{path.name} branches on a language or country")

    def test_i18n_s2(self) -> None:
        """I18N-S2

        Translations are rows with the original marked and machine output labelled (I18N-01).
        """
        # The vocabulary label rows are the translation rows of chunk 2: one per language,
        # the original marked, machine output labelled, and the read falls back along the
        # caller's language order. Obligation summaries reuse the same shape in chunk 3.
        admin = sign_in(self.admin, tenant=self.tenant)
        created = self._post("/vocab/tenant_tag", {"labels": {"sv": "Rådgivning"}, "usageNote": "Skrivet på svenska."}, admin)
        self.assertEqual(created.status_code, 201, created.content)
        self.activate(self.tenant)
        tag = TenantTag.objects.get(tenant=self.tenant, key=created.json()["key"])
        original = tag.labels.get(language="sv")
        self.assertTrue(original.is_original)
        self.assertFalse(original.is_machine)
        tag.labels.create(tenant=self.tenant, language="en", text="Advice", is_machine=True)
        rows = self._rows("tenant_tag", admin)
        self.assertEqual(rows[tag.key]["label"], "Advice")
        self.assertEqual(rows[tag.key]["labels"], {"sv": "Rådgivning", "en": "Advice"})
        # A caller whose language order has neither language gets the original.
        User.objects.filter(pk=self.reader.pk).update(locale=Language.objects.get(key="fi"))
        TenantRole.objects.filter(tenant=self.tenant).exists()
        finnish = self._rows("tenant_tag", sign_in(self.reader, tenant=self.tenant))
        self.assertEqual(finnish[tag.key]["label"], "Advice")
        tag.labels.filter(language="en").delete()
        finnish = self._rows("tenant_tag", sign_in(self.reader, tenant=self.tenant))
        self.assertEqual(finnish[tag.key]["label"], "Rådgivning")
        # The API marks which label is the original and which is machine output.
        detail = self._get(f"/vocab/tenant_tag/{tag.key}", admin)
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(detail.json()["originalLanguage"], "sv")
        self.assertEqual(detail.json()["machineLanguages"], [])
        unknown = self._post("/vocab/tenant_tag", {"labels": {"xx": "Nope"}}, admin)
        self.assertEqual(unknown.status_code, 422)
        self.assertEqual(unknown.json()["code"], "unknown_key")
        # Every proposal and library row goes through the same rows: the contract drift rows exist.
        self.assertIn("`GET /taxonomy/terms`", INPUT_DELTAS.read_text(encoding="utf-8"))
        self.assertEqual(Proposal.objects.filter(status=ProposalStatus.OPEN.value, kind=ProposalKind.TERM_CREATE.value).count(), 0)

    def _obligation_per_jurisdiction(self, scenario: str, keys: tuple[str, ...]) -> dict[str, Obligation]:
        """One custody obligation under a securities instrument of each jurisdiction named,
        so the jurisdiction is the only thing that tells them apart."""
        from apps.library import testing as library_build

        return {
            key: library_build.obligation(
                library_build.instrument(key=f"{scenario}-{key}", regime="regime:securities", jurisdiction=key),
                key=f"{scenario}-{key}-custody",
                terms=("service_type:custody",),
            )
            for key in keys
        }

    def _inventory(self, headers: dict[str, Any]) -> set[str]:
        response = self._get("/obligations", headers)
        self.assertEqual(response.status_code, 200, response.content)
        return {row["stableKey"] for row in response.json()["items"]}

    def test_fp_s8(self) -> None:
        """FP-S8

        Turning on a country brings the EU rules that reach it (FP-04, AC-FP2).

        The officer's request holds the one jurisdiction they turned on; the Union rules that
        reach it come from each record's instrument at match time (D-28, D-29), so the
        preview never counts them as hidden and the inventory keeps them.
        """
        built = self._obligation_per_jurisdiction("fp-s8", ("eu", "se", "dk", "no"))
        self._set_footprint(["regime:securities"])
        reader = sign_in(self.reader, tenant=self.tenant)
        before = self._inventory(reader)
        self.assertEqual(before, {obligation.stable_key for obligation in built.values()}, "no jurisdiction in the scope restricts nothing")

        # When the officer turns on Denmark and chooses "Preview".
        officer = sign_in(self.officer, tenant=self.tenant)
        denmark = {"adds": [{"dimension": "jurisdiction", "key": "dk"}], "removes": []}
        preview = self._preview("/tenant/footprint/requests?dryRun=true", denmark, officer)
        self.assertEqual(preview.status_code, 200, preview.content)
        counted = preview.json()["preview"]["obligations"]

        # When they send it and a second person approves it with a fresh step-up.
        created = self._post("/tenant/footprint/requests", denmark, officer)
        self.assertEqual(created.status_code, 201, created.content)
        request = created.json()
        self.assertEqual(([term["key"] for term in request["adds"]], request["removes"]), (["dk"], []))
        self.activate(self.tenant)
        held = FootprintChangeRequest.objects.get(pk=request["id"])
        self.assertEqual(
            ([link.term.jurisdiction_id for link in held.add_links.select_related("term")], held.remove_links.count()),
            ([Jurisdiction.objects.get(key="dk").id], 0),
            "the request held Denmark only: no Union term and no derived one",
        )
        approver = sign_in(self.approver, tenant=self.tenant, step_up=True)
        approved = self._post(f"/tenant/footprint/requests/{request['id']}/approve", {}, approver, HTTP_IF_MATCH=str(request["version"]))
        self.assertEqual(approved.status_code, 200, approved.content)

        # Then the inventory lists the Union and Danish obligations and no Swedish or
        # Norwegian one, and the preview counted exactly those two as hidden.
        after = self._inventory(sign_in(self.reader, tenant=self.tenant))
        self.assertEqual(after, {built["eu"].stable_key, built["dk"].stable_key})
        self.assertEqual(before - after, {built["se"].stable_key, built["no"].stable_key})
        self.assertEqual(counted, {"hidden": len(before - after), "revealed": 0, "available": True})

        # One audit event and one history row for the term.
        self.activate(self.tenant)
        events = AuditEvent.objects.filter(tenant=self.tenant, action__in=("footprint.term_added", "footprint.term_removed"))
        self.assertEqual([(event.action, event.after["request"]) for event in events], [("footprint.term_added", request["id"])])
        history = FootprintHistory.objects.filter(tenant=self.tenant, request_id=request["id"]).select_related("term")
        self.assertEqual([(row.action, row.term.key) for row in history], [("added", "dk")])

    def test_fp_s9(self) -> None:
        """FP-S9

        A record's jurisdiction comes from its instrument, and EU rules reach the member countries and Norway (FP-04, AC-FP2).

        The derivation is `library.reading.instrument_scopes()` and its SQL twin (D-28,
        D-29): read from the mirror link and the jurisdiction's parent at match time, never
        stored, and appended to the array the database function has always been handed.
        """
        import ast
        import inspect
        import re
        import textwrap

        from apps.library import reading
        from apps.library.models import JurisdictionLabel
        from apps.taxonomy import matching

        # Given a footprint whose only jurisdiction is Norway, and one obligation each from
        # an EU, a Norwegian and a Swedish instrument.
        built = self._obligation_per_jurisdiction("fp-s9", ("eu", "no", "se"))
        self._set_footprint(["jurisdiction:no"])
        reader = sign_in(self.reader, tenant=self.tenant)

        # Then the EU and Norwegian obligations match and the Swedish one does not, and the
        # Swedish one says it is outside by its jurisdiction.
        self.assertEqual(self._inventory(reader), {built["eu"].stable_key, built["no"].stable_key})
        everything = self._get("/obligations?footprint=all", reader).json()["items"]
        swedish = next(row for row in everything if row["stableKey"] == built["se"].stable_key)
        self.assertEqual(
            [(reason["dimension"]["key"], [term["key"] for term in reason["terms"]]) for reason in swedish["outsideReason"]],
            [("jurisdiction", ["se"])],
        )

        # The rule and the SQL function, called unchanged, give the same answers from the
        # same derived terms: the Union's own and every country it reaches, Norway included.
        self.activate(self.tenant)
        scopes = reading.obligation_scopes([obligation.id for obligation in built.values()])
        handed = dict(
            Obligation.objects.filter(id__in=[obligation.id for obligation in built.values()])
            .annotate(term_ids=reading.scope_term_ids())
            .values_list("id", "term_ids")
        )
        footprint, restricting = matching.footprint_of(self.tenant.id), matching.restricting_dimensions()
        verdicts = {}
        for key, obligation in built.items():
            scope = scopes[obligation.id]
            with self.subTest(key):
                self.assertEqual(set(handed[obligation.id]), {term.id for terms in scope.values() for term in terms})
                pure = matching.in_footprint({d: {term.key for term in terms} for d, terms in scope.items()}, footprint, restricting=restricting)
                self.assertIs(matching.in_footprint_sql(self.tenant.id, handed[obligation.id]), pure)
                verdicts[key] = pure
        self.assertEqual(verdicts, {"eu": True, "no": True, "se": False})
        self.assertEqual(
            {key: [term.key for term in scopes[obligation.id]["jurisdiction"]] for key, obligation in built.items()},
            {"eu": ["eu", "se", "dk", "no", "fi"], "no": ["no"], "se": ["se"]},
        )

        # And no jurisdiction term is stored for any of them.
        self.assertFalse(ObligationTerm.objects.filter(obligation__in=list(built.values()), term__jurisdiction__isnull=False).exists())

        # When a proposal filed before the mirror rule would tag an obligation with a
        # jurisdiction term, applying it answers 422 and scopes nothing.
        filed = Proposal.objects.create(
            kind=ProposalKind.NEW_OBLIGATION_VERSION.value,
            title="Filed before the mirror rule",
            payload={
                "summaries": {"en": "The firm keeps client assets apart."},
                "originalLanguage": "en",
                "effectiveFromPrecision": "day",
                "terms": ["service_type:custody", "jurisdiction:no"],
            },
            origin="user",
            proposed_by_user=self.editor,
            target_type="obligation",
            target_id=built["se"].id,
        )
        refused = self._post(f"/proposals/{filed.id}/approve", {}, sign_in(self.second_editor, step_up=True))
        self.assertEqual((refused.status_code, refused.json()["code"]), (422, "jurisdiction_term_mirrored"), refused.content)
        self.assertEqual(Proposal.objects.get(pk=filed.pk).status, ProposalStatus.OPEN.value)
        self.assertFalse(ObligationTerm.objects.filter(obligation=built["se"], term__jurisdiction__isnull=False).exists())

        # And the code that decides this names no country and no dimension: no string in the
        # derivation or its SQL twin, docstrings aside, is a jurisdiction's key or label or a
        # dimension's key, and nothing in it selects a term through its dimension.
        names = {
            *Jurisdiction.objects.values_list("key", flat=True),
            *JurisdictionLabel.objects.values_list("text", flat=True),
            *TermDimension.objects.values_list("key", flat=True),
        }

        def named_in(source: str) -> set[str]:
            tree = ast.parse(textwrap.dedent(source))
            docstrings = {id(node.body[0].value) for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and isinstance(node.body[0], ast.Expr)}
            found: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                    found |= {name for name in names if re.search(rf"\b{re.escape(name)}\b", node.value, re.IGNORECASE)}
                if isinstance(node, ast.keyword) and node.arg and node.arg.startswith("dimension"):
                    found.add(node.arg)
            return found

        derivation = (reading.instrument_scopes, reading.obligation_scopes, reading._instrument_scope, reading.instrument_scope_term_ids, reading.scope_term_ids)
        self.assertEqual({function.__name__: named_in(inspect.getsource(function)) for function in derivation}, {function.__name__: set() for function in derivation})
        # The guard bites: a derivation that picked Norway's term by its dimension is named.
        self.assertEqual(named_in('def pick():\n    return TaxonomyTerm.objects.filter(dimension__key="jurisdiction", key="no")\n'), {"dimension__key", "jurisdiction", "no"})

    def test_fp_s10(self) -> None:
        """FP-S10

        Watching a market is one audited write that hides nothing (FP-04, AC-FP2).

        Exercises the two mutating operations `watchMarket` and `unwatchMarket`, which
        `apps/shared/tests_audit_on_write.py` reads this file for by name.
        """
        self._set_footprint(["regime:securities", "jurisdiction:se"])
        admin = sign_in(self.admin, tenant=self.tenant)
        before = self._footprint(admin)
        events_before = AuditEvent.objects.filter(action="markets.watch_added").count()

        watched = self._post("/tenant/footprint/watching", {"jurisdiction": "no"}, admin)
        self.assertEqual(watched.status_code, 200, watched.content)
        self.assertEqual(watched.json(), {"jurisdiction": {"key": "no", "kind": "country", "label": "Norway"}, "operating": False, "watching": True})
        self.activate(self.tenant)
        self.assertTrue(WatchedMarket.objects.filter(tenant=self.tenant, jurisdiction__key="no").exists())
        event = AuditEvent.objects.get(action="markets.watch_added")
        self.assertEqual(event.after, {"jurisdiction": "no"})
        self.assertIsNone(event.step_up_assertion_id)
        self.assertEqual(AuditEvent.objects.filter(action="markets.watch_added").count(), events_before + 1)
        # Watching hides nothing: the footprint and its default view are unchanged.
        after = self._footprint(admin)
        self.assertEqual(after["dimensions"], before["dimensions"])

        again = self._post("/tenant/footprint/watching", {"jurisdiction": "no"}, admin)
        self.assertEqual(again.status_code, 409, again.content)
        self.assertEqual(again.json()["code"], "already_watching")

        stopped = self._post("/tenant/footprint/watching/remove", {"jurisdiction": "no"}, admin)
        self.assertEqual(stopped.status_code, 200, stopped.content)
        self.assertEqual(stopped.json()["watching"], False)
        self.activate(self.tenant)
        self.assertFalse(WatchedMarket.objects.filter(tenant=self.tenant, jurisdiction__key="no").exists())
        self.assertTrue(AuditEvent.objects.filter(action="markets.watch_removed").exists())

        reader = sign_in(self.reader, tenant=self.tenant)
        seen = self._footprint(reader)
        self.assertIn("markets", seen)
        self.assertIn("se", [m["jurisdiction"]["key"] for m in seen["markets"] if m["operating"]])
        denied = self._post("/tenant/footprint/watching", {"jurisdiction": "no"}, reader)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["requiredPermission"], "footprint.request")

    def test_fp_s11(self) -> None:
        """FP-S11

        A market's level is computed, and operating comes first (FP-04).
        """
        from apps.taxonomy import markets_logic

        self._set_footprint(["regime:securities", "jurisdiction:se"])
        norway = Jurisdiction.objects.get(key="no")
        finland = Jurisdiction.objects.get(key="fi")

        def _start_operating(key: str) -> dict[str, Any]:
            officer = sign_in(self.officer, tenant=self.tenant)
            request = self._post(
                "/tenant/footprint/requests", {"adds": [{"dimension": "jurisdiction", "key": key}], "removes": []}, officer
            ).json()
            approver = sign_in(self.approver, tenant=self.tenant, step_up=True)
            self._post(f"/tenant/footprint/requests/{request['id']}/approve", {}, approver, HTTP_IF_MATCH=str(request["version"]))
            return request

        def _stop_operating(key: str) -> dict[str, Any]:
            officer = sign_in(self.officer, tenant=self.tenant)
            request = self._post(
                "/tenant/footprint/requests", {"adds": [], "removes": [{"dimension": "jurisdiction", "key": key}]}, officer
            ).json()
            approver = sign_in(self.approver, tenant=self.tenant, step_up=True)
            self._post(f"/tenant/footprint/requests/{request['id']}/approve", {}, approver, HTTP_IF_MATCH=str(request["version"]))
            return request

        # Given a tenant operating in Sweden and watching Norway.
        self.activate(self.tenant)
        markets_logic.watch(tenant=self.tenant, actor=Actor.system("test"), key="no")
        self.assertEqual(markets_logic.level_of(self.tenant.id, norway), markets_logic.WATCHING)
        events_before = AuditEvent.objects.filter(action__in=["markets.watch_added", "markets.watch_removed"]).count()

        # When a request to operate in Norway is approved, then Norway reads as operating,
        # its watch row is untouched, and no watch event is written.
        _start_operating("no")
        self.activate(self.tenant)
        self.assertEqual(markets_logic.level_of(self.tenant.id, norway), markets_logic.OPERATING)
        self.assertTrue(WatchedMarket.objects.filter(tenant=self.tenant, jurisdiction=norway).exists())
        self.assertEqual(
            AuditEvent.objects.filter(action__in=["markets.watch_added", "markets.watch_removed"]).count(), events_before
        )

        # When a request to stop operating in Norway is approved, then Norway reads as
        # watching again.
        _stop_operating("no")
        self.activate(self.tenant)
        self.assertEqual(markets_logic.level_of(self.tenant.id, norway), markets_logic.WATCHING)

        # Given Finland was never watched, when a request to operate is approved and later
        # reversed, then Finland reads as not followed.
        self.assertEqual(markets_logic.level_of(self.tenant.id, finland), markets_logic.NOT_FOLLOWED)
        _start_operating("fi")
        self.activate(self.tenant)
        self.assertEqual(markets_logic.level_of(self.tenant.id, finland), markets_logic.OPERATING)
        _stop_operating("fi")
        self.activate(self.tenant)
        self.assertEqual(markets_logic.level_of(self.tenant.id, finland), markets_logic.NOT_FOLLOWED)
        self.assertFalse(WatchedMarket.objects.filter(tenant=self.tenant, jurisdiction=finland).exists())

    def test_fp_s12(self) -> None:
        """FP-S12

        Jurisdiction terms mirror the jurisdiction rows and cannot be proposed (FP-04).

        Exercises `createTerm`, `updateTerm`, `createProposal` and `updateChange` answering
        422 `jurisdiction_term_mirrored`, a rule keyed on the link a mirrored term carries
        and never on a dimension key, so its sentence names no dimension and no country.
        """
        import re
        from io import StringIO

        from django.core.management import call_command

        from apps.library import testing as library_build
        from apps.taxonomy.models import TaxonomyTerm
        from apps.taxonomy.seeds import MIRRORED_JURISDICTION_KINDS

        # A jurisdiction no bank operates in, as standards bodies issue under: whichever
        # seed files it, it gets no term (D-38).
        Jurisdiction.objects.get_or_create(
            key="intl",
            defaults={"kind": "international", "default_language": Language.objects.get(key="en"), "sort_order": 99, "is_system": True},
        )
        # As a deploy runs it: no tenant activated, so it sees every tenant.
        tenancy.clear_tenant()
        call_command("seed_reference", stdout=StringIO())
        self.activate(self.tenant)

        def labels(row: Any) -> dict[str, str]:
            return {label.language: label.text for label in row.labels.all()}

        # Given the seeded jurisdictions, the mirror is exact both ways.
        rows = {
            row.key: row
            for row in Jurisdiction.objects.filter(active=True, kind__in=MIRRORED_JURISDICTION_KINDS).prefetch_related("labels")
        }
        mirrored = {
            term.key: term
            for term in TaxonomyTerm.objects.exclude(jurisdiction=None).select_related("dimension", "parent").prefetch_related("labels")
        }
        self.assertEqual(set(rows), {"eu", "se", "dk", "no", "fi"})
        self.assertEqual(set(mirrored), set(rows), "every mirrored jurisdiction has a term, and no term invents one")
        dimension = mirrored["eu"].dimension
        self.assertEqual({term.dimension_id for term in mirrored.values()}, {dimension.id}, "one dimension holds the mirror")
        self.assertEqual(set(TaxonomyTerm.objects.filter(dimension=dimension, active=True).values_list("key", flat=True)), set(rows))
        for key, term in mirrored.items():
            self.assertEqual((term.jurisdiction_id, labels(term)), (rows[key].id, labels(rows[key])), key)
        self.assertEqual(
            {key: term.parent.key if term.parent else None for key, term in mirrored.items()},
            {"eu": None, "se": "eu", "dk": "eu", "no": "eu", "fi": "eu"},
            "each country's term has the Union's as parent, Norway's included",
        )
        self.assertFalse(TaxonomyTerm.objects.filter(jurisdiction__key="intl").exists())
        self.assertFalse(TaxonomyTerm.objects.filter(dimension=dimension, key="intl").exists())

        # The regulatory scope lists the five terms, all of them when all are chosen.
        self._set_footprint(["regime:securities", *(f"{dimension.key}:{key}" for key in rows)])
        listed = next(
            entry for entry in self._footprint(sign_in(self.reader, tenant=self.tenant))["dimensions"] if entry["dimension"]["key"] == dimension.key
        )
        self.assertEqual(
            [(term["key"], term["label"]) for term in listed["terms"]],
            [("eu", "European Union"), ("se", "Sweden"), ("dk", "Denmark"), ("no", "Norway"), ("fi", "Finland")],
        )
        self.assertTrue(listed["allSelected"])

        # The term list marks exactly the mirrored terms, so an agent or a picker leaves them
        # out before sending anything, rather than learning the rule from a refusal.
        term_list = self._get("/taxonomy/terms", sign_in(self.reader, tenant=self.tenant))
        self.assertEqual(term_list.status_code, 200, term_list.content)
        self.assertEqual(
            {(row["dimension"]["key"], row["key"]) for row in term_list.json()["items"] if row["mirrored"]},
            {(dimension.key, key) for key in rows},
        )

        # When a proposal adds or renames a term of the mirrored dimension, or tags a record
        # with one, it answers 422 and nothing reaches the queue or the library.
        norway = mirrored["no"]
        instrument = library_build.instrument(key="fp-s12-instrument", regime="regime:securities")
        obligation = library_build.obligation(instrument, key="fp-s12-obligation", terms=("service_type:custody",))
        change = watch_build.change()
        editor = sign_in(self.editor)
        queued = Proposal.objects.count()
        refusals = {
            "a new term": self._post("/taxonomy/terms", {"dimension": dimension.key, "labels": {"en": "Iceland"}}, editor),
            "a key the mirror holds": self._post("/taxonomy/terms", {"dimension": dimension.key, "key": "se", "labels": {"en": "Sweden"}}, editor),
            "a rename": self._patch(f"/taxonomy/terms/{norway.id}", {"labels": {"en": "Kingdom of Norway"}}, editor),
            "a new term filed directly": self._post(
                "/proposals", {"kind": "term_create", "title": "Add Iceland", "payload": {"dimension": dimension.key, "key": "is", "labels": {"en": "Iceland"}}}, editor
            ),
            "a rename filed directly": self._post(
                "/proposals", {"kind": "term_update", "title": "Rename Norway", "payload": {"dimension": dimension.key, "key": "no", "labels": {"en": "Kingdom of Norway"}}}, editor
            ),
            "an obligation tagged with a market": self._post(
                "/proposals",
                {
                    "kind": "new_obligation_version",
                    "title": "Version 2, in Norway",
                    "targetType": "obligation",
                    "targetId": str(obligation.id),
                    "payload": {"summaries": {"en": "The firm keeps client assets apart."}, "originalLanguage": "en", "terms": ["service_type:custody", f"{dimension.key}:no"]},
                    "fieldSources": {"summaries.en": "https://www.fi.se/", "terms": "https://www.fi.se/"},
                },
                editor,
            ),
            "a change tagged with a market": self._patch(f"/changes/{change.id}", {"termIds": [str(norway.id)]}, editor),
        }
        named = {dimension.key, *rows, *(text for row in rows.values() for text in labels(row).values())}
        for what, response in refusals.items():
            with self.subTest(what):
                self.assertEqual((response.status_code, response.json()["code"]), (422, "jurisdiction_term_mirrored"), response.content)
                detail = response.json()["detail"]
                for word in named:
                    self.assertIsNone(re.search(rf"\b{re.escape(word)}\b", detail, re.IGNORECASE), f"the refusal names {word!r}")
        self.assertEqual(Proposal.objects.count(), queued, "nothing reached the queue")
        self.assertFalse(TaxonomyTerm.objects.filter(dimension=dimension, key="is").exists())
        self.assertEqual(TaxonomyTerm.objects.get(pk=norway.pk).version, norway.version)
        self.assertFalse(change.term_links.exists())

        # When seed_reference runs a second time, nothing changes and nothing is recorded.
        def mirror_state() -> list[tuple[Any, ...]]:
            terms = TaxonomyTerm.objects.filter(dimension=dimension).prefetch_related("labels")
            return sorted((t.id, t.key, t.jurisdiction_id, t.parent_id, t.active, t.sort_order, t.version, sorted(labels(t).items())) for t in terms)

        self.activate(self.tenant)  # the bank's own rows and the library's, read the same way before and after
        before, recorded = mirror_state(), set(AuditEvent.objects.values_list("id", flat=True))
        tenancy.clear_tenant()
        call_command("seed_reference", stdout=StringIO())
        self.activate(self.tenant)
        self.assertEqual(mirror_state(), before)
        self.assertEqual(list(AuditEvent.objects.exclude(id__in=recorded).values_list("action", "subject_title")), [])

    def test_fp_s13(self) -> None:
        """FP-S13

        The watched-market view of the inventory shows only what watching adds (FP-04).

        `footprint=watched` on `GET /obligations` and `GET /instruments` lists a record the
        scope hides, whose other dimensions the scope allows, and whose derived jurisdiction
        is one the bank watches: the same database function, called unchanged, answers each
        half. Each row names its jurisdiction, which the screen's "Market we watch" reads.
        """
        from apps.library import testing as library_build

        # Given a tenant operating in Sweden with the service "Custody" and watching Denmark,
        # and Danish obligations scoped to "Custody" and to "Advice".
        built = self._obligation_per_jurisdiction("fp-s13", ("eu", "se", "dk", "no"))
        danish_act = built["dk"].instrument
        advice = library_build.obligation(danish_act, key=f"{danish_act.stable_key}-advice", terms=("service_type:advice",))
        self._set_footprint(["regime:securities", "service_type:custody", "jurisdiction:se"])
        watched = self._post("/tenant/footprint/watching", {"jurisdiction": "dk"}, sign_in(self.admin, tenant=self.tenant))
        self.assertEqual(watched.status_code, 200, watched.content)
        reader = sign_in(self.reader, tenant=self.tenant)

        # When a user chooses "Markets we watch" in the inventory.
        response = self._get("/obligations?footprint=watched", reader)
        self.assertEqual(response.status_code, 200, response.content)
        rows = {row["stableKey"]: row for row in response.json()["items"]}

        # Then the Danish "Custody" obligation is listed, naming Denmark as its jurisdiction,
        # and it is outside the scope by its jurisdiction alone.
        danish = rows[built["dk"].stable_key]
        self.assertEqual(danish["jurisdiction"], {"key": "dk", "kind": "country", "label": "Denmark"})
        self.assertFalse(danish["inFootprint"])
        self.assertEqual([reason["dimension"]["key"] for reason in danish["outsideReason"]], ["jurisdiction"])
        # And the Danish "Advice" obligation is absent, because the other dimensions still
        # apply, and no EU, Swedish or unwatched Norwegian one is listed.
        self.assertNotIn(advice.stable_key, rows)
        for key in ("eu", "se", "no"):
            self.assertNotIn(built[key].stable_key, rows, key)
        self.assertEqual({row["jurisdiction"]["key"] for row in rows.values()}, {"dk"})

        # The default view is unchanged by watching, and "all" is the whole library, each row
        # naming its own jurisdiction.
        self.assertNotIn(built["dk"].stable_key, self._inventory(reader))
        self.assertIn(built["se"].stable_key, self._inventory(reader))
        everything = {row["stableKey"]: row["jurisdiction"]["key"] for row in self._get("/obligations?footprint=all", reader).json()["items"]}
        self.assertEqual(
            {key: everything[obligation.stable_key] for key, obligation in built.items()},
            {"eu": "eu", "se": "se", "dk": "dk", "no": "no"},
        )
        self.assertIn(advice.stable_key, everything)

        # The Instruments tab answers the same way: the Danish instrument alone, counting the
        # one obligation this view lists from it.
        instruments = self._get("/instruments?footprint=watched", reader)
        self.assertEqual(instruments.status_code, 200, instruments.content)
        listed = {row["stableKey"]: row for row in instruments.json()["items"]}
        self.assertEqual(listed[built["dk"].instrument.stable_key]["obligationCount"], 1)
        self.assertEqual({row["jurisdiction"]["key"] for row in listed.values()}, {"dk"})

        # And the list takes one footprint filter value, so no contradictory pair can be sent:
        # the retired boolean and an unknown value answer 422, and the published parameter is
        # one value of three, never a list.
        for path in ("/obligations", "/instruments"):
            for query in ("outsideFootprint=true", "outsideFootprint=false", "footprint=outside"):
                with self.subTest(path=path, query=query):
                    refused = self._get(f"{path}?{query}", reader)
                    self.assertEqual((refused.status_code, refused.json()["code"]), (422, "validation_error"), refused.content)
            parameters = {parameter["name"]: parameter for parameter in api.get_openapi_schema()["paths"][f"{V1}{path}"]["get"]["parameters"]}
            self.assertEqual(parameters["footprint"]["schema"]["enum"], ["in", "all", "watched"])
            self.assertTrue(parameters["outsideFootprint"]["deprecated"])

    def test_fp_s14(self) -> None:
        """FP-S14

        Markets stay inside the tenant and out of logs and error reports (FP-04, NFR-01).

        The watch list is a bank's own judgement, so it lives under row-level security and
        its keys travel in the body, never in a path or a query. The second half drives a
        watch and an unwatch through the WSGI entry point gunicorn calls, with the Sentry
        SDK started from the arguments settings.py passes it and the loggers at their
        deployed levels, and reads what each channel would have carried off the machine:
        the transactions and the error events, which pass through before_send.
        """
        import logging
        import os
        import re
        from pathlib import Path

        import sentry_sdk
        from django.conf import settings
        from django.core.handlers.wsgi import WSGIHandler
        from django.core.signals import request_finished, request_started
        from django.db import close_old_connections
        from django.test import RequestFactory, override_settings
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.transport import Transport

        from apps.shared.logging import JsonFormatter
        from apps.shared.middleware import RequestIdLogFilter
        from apps.shared.testing import sentry_init_kwargs

        # Given tenant A watches Norway, with a regulatory scope and a request waiting, and
        # tenant B watches nothing.
        self._set_footprint(["regime:securities", "jurisdiction:se"])
        a = sign_in(self.admin, tenant=self.tenant)
        self.assertEqual(self._post("/tenant/footprint/watching", {"jurisdiction": "no"}, a).status_code, 200)
        waiting = self._post(
            "/tenant/footprint/requests",
            {"adds": [{"dimension": "jurisdiction", "key": "no"}], "removes": []},
            sign_in(self.officer, tenant=self.tenant),
        )
        self.assertEqual(waiting.status_code, 201, waiting.content)
        self.activate(self.tenant)
        watched = WatchedMarket.objects.get(tenant=self.tenant, jurisdiction__key="no")
        a_rows = {
            str(self.tenant.id),
            str(watched.id),
            waiting.json()["id"],
            *(str(pk) for pk in FootprintTerm.objects.filter(tenant=self.tenant).values_list("id", flat=True)),
        }
        other = factories.tenant(slug="other-bank")
        b = sign_in(factories.member(other, roles=("admin",), user_row=factories.user(name="Lena Berg")).user, tenant=other)

        # When tenant B reads its footprint, Norway is not watched and nothing of A's is there.
        seen = self._get("/tenant/footprint", b)
        self.assertEqual(seen.status_code, 200, seen.content)
        norway = next(market for market in seen.json()["markets"] if market["jurisdiction"]["key"] == "no")
        self.assertEqual((norway["operating"], norway["watching"]), (False, False))
        self.assertIsNone(seen.json()["pendingRequest"])
        for row_id in a_rows:
            self.assertNotIn(row_id, seen.content.decode())

        # When tenant B asks to stop watching Norway, the answer is 404 and A's row stands.
        refused = self._post("/tenant/footprint/watching/remove", {"jurisdiction": "no"}, b)
        self.assertEqual((refused.status_code, refused.json()["code"]), (404, "not_found"))
        self.activate(self.tenant)
        self.assertEqual(
            WatchedMarket.objects.filter(tenant=self.tenant, jurisdiction__key="no").values_list("id", "added_by_id").get(),
            (watched.id, self.admin.id),
        )

        # When tenant A watches and stops watching a market, what leaves the machine holds
        # no jurisdiction key: the access line, the application log and the Sentry events.
        entrypoint = (Path(settings.BASE_DIR) / "docker-entrypoint.sh").read_text(encoding="utf-8")
        access_format = re.search(r"--access-logformat '([^']*)'", entrypoint)
        assert access_format is not None, "the entrypoint names gunicorn's access format"

        def access_line(environ: dict[str, Any], status: str, headers: list[tuple[str, str]], sent: int) -> str:
            """The line gunicorn 26.2.0 prints for this request: its `Logger.atoms()`
            restated, every atom it offers and not only the safe ones, because gunicorn
            itself cannot be imported on every machine the suite runs on (`import grp`)."""
            atoms = {
                "h": environ.get("REMOTE_ADDR", "-"), "l": "-", "u": "-", "t": "[23/Sep/2026:09:00:00 +0000]",
                "r": f"{environ['REQUEST_METHOD']} {environ['RAW_URI']} {environ['SERVER_PROTOCOL']}",
                "s": status.split(None, 1)[0], "m": environ["REQUEST_METHOD"], "U": environ["PATH_INFO"],
                "q": environ.get("QUERY_STRING"), "H": environ["SERVER_PROTOCOL"], "b": str(sent), "B": sent,
                "f": environ.get("HTTP_REFERER", "-"), "a": environ.get("HTTP_USER_AGENT", "-"),
                "T": 0, "D": 12000, "M": 12, "L": "0.012000", "p": f"<{os.getpid()}>",
                **{f"{{{name[5:].replace('_', '-').lower()}}}i": value for name, value in environ.items() if name.startswith("HTTP_")},
                **{f"{{{name.lower()}}}o": value for name, value in headers},
                **{f"{{{name.lower()}}}e": value for name, value in environ.items()},
            }
            return access_format.group(1) % {name: atoms.get(name, "-") for name in re.findall(r"%\((.*?)\)s", access_format.group(1))}

        def served(path: str, key: str) -> tuple[int, str]:
            """One request through the WSGI application, as gunicorn hands it over, and its
            access line. The test client's own handler would bypass the WSGI entry point
            Sentry wraps; database connections stay open as the test client keeps them."""
            request = RequestFactory().post(f"{V1}{path}", data={"jurisdiction": key}, content_type="application/json", **a)
            environ = {**request.environ, "RAW_URI": request.environ["PATH_INFO"]}
            started: list[Any] = []

            def start_response(status: str, headers: list[tuple[str, str]], exc_info: Any = None) -> Any:
                started.extend([status, headers])
                return lambda chunk: None

            request_started.disconnect(close_old_connections)
            request_finished.disconnect(close_old_connections)
            try:
                response = WSGIHandler()(environ, start_response)
                sent = len(b"".join(response))
                response.close()
            finally:
                request_started.connect(close_old_connections)
                request_finished.connect(close_old_connections)
            return int(started[0].split()[0]), access_line(environ, started[0], started[1], sent)

        class Captured(Transport):
            def __init__(self) -> None:
                super().__init__()
                self.events: list[dict[str, Any]] = []

            def capture_envelope(self, envelope: Any) -> None:
                self.events.extend(item.payload.json for item in envelope.items if item.payload.json)

        class Lines(logging.Handler):
            def __init__(self) -> None:
                super().__init__()
                self.lines: list[str] = []
                self.setFormatter(JsonFormatter())
                self.addFilter(RequestIdLogFilter())

            def emit(self, record: logging.LogRecord) -> None:
                self.lines.append(self.format(record))

        transport, app_log, access = Captured(), Lines(), []
        # The deployed levels (settings.LOGGING before test_settings quietens it), and an
        # over-budget line per request, so the log is known to hold something.
        deployed = {logging.getLogger(): "INFO", logging.getLogger("apps"): "INFO", logging.getLogger("django"): "INFO", logging.getLogger("django.request"): "WARNING"}
        quiet = {logger: logger.level for logger in deployed}
        for logger, level in deployed.items():
            logger.addHandler(app_log)
            logger.setLevel(level)
        # What settings.py itself passes, read by booting it with a DSN, so this proof follows
        # it. Four things are replaced: the transport, so nothing leaves; every trace is
        # kept; every warning becomes an error event, so the over-budget line of each request
        # passes through before_send as an error would; and the host's name and the build's
        # release, which differ from machine to machine and are nobody's content.
        deployed_sentry = sentry_init_kwargs()
        sentry_sdk.init(
            **{
                **deployed_sentry,
                "transport": transport,
                "traces_sample_rate": 1.0,
                "integrations": [*deployed_sentry["integrations"], LoggingIntegration(event_level=logging.WARNING)],
                "server_name": "api",
                "release": "fp-s14",
            }
        )
        try:
            with override_settings(API_BUDGET_MS=0):
                for path in ("/tenant/footprint/watching", "/tenant/footprint/watching/remove"):
                    status, line = served(path, "dk")
                    self.assertEqual(status, 200, line)
                    access.append(line)
            sentry_sdk.flush()
        finally:
            sentry_sdk.get_client().close()
            sentry_sdk.get_global_scope().set_client(None)
            for logger, previous in quiet.items():
                logger.removeHandler(app_log)
                logger.setLevel(previous)

        self.activate(self.tenant)
        self.assertEqual(AuditEvent.objects.filter(action__in=("markets.watch_added", "markets.watch_removed"), subject_title="dk").count(), 2)
        transactions = [event for event in transport.events if event.get("type") == "transaction"]
        self.assertEqual(len(transactions), 2, "one transaction per request reached the transport")
        errors = [event for event in transport.events if event.get("type") != "transaction" and "logentry" in event]
        self.assertEqual(
            [event["logentry"]["message"] for event in errors].count("request over budget"),
            2,
            "each request's over-budget warning reached the transport as an error event, through before_send",
        )
        self.assertTrue(app_log.lines, "each request logged over budget")
        denmark = Jurisdiction.objects.prefetch_related("labels").get(key="dk")
        keys = set(Jurisdiction.objects.values_list("key", flat=True))
        for channel, text in (("access log", "\n".join(access)), ("application log", "\n".join(app_log.lines)), ("Sentry", json.dumps(transport.events, default=str))):
            with self.subTest(channel):
                for key in keys:
                    self.assertIsNone(re.search(rf"(?<![A-Za-z0-9]){key}(?![A-Za-z0-9])", text), f"{channel} holds the key {key!r}")
                for word in (str(denmark.id), *(label.text for label in denmark.labels.all())):
                    self.assertNotIn(word, text, channel)

    @skip("pending: FP-S15 (FP-04, chunk 5)")
    def test_fp_s15(self) -> None:
        """FP-S15

        A change's jurisdiction comes from its authority, and the feed has the watched-market view (FP-04).
        """

    @skip("pending: FP-S16 (FP-01, INV-08, chunk 3)")
    def test_fp_s16(self) -> None:
        """FP-S16

        A standard shows only to tenants whose regulatory scope names it (FP-01, INV-08, AC-FP3).
        """

    def test_fp_s17(self) -> None:
        """FP-S17

        The pure rule and the SQL function agree on opt-in dimensions, whatever the flag says (FP-01).

        Over the seeded rows: the scope dimension "service_type" and the opt-in dimension
        "standard", with a second standard beside ISO/IEC 27001 so that naming another standard
        is never mistaken for naming this one. apps/taxonomy/tests_matching.py holds the pure
        cases, the larger mirror and the retired dimension.
        """
        from apps.taxonomy import matching

        standard = TermDimension.objects.get(key="standard")
        self.assertEqual((standard.kind, standard.restricts_footprint), ("opt_in", True))
        with library_write("test"):
            second = TaxonomyTerm.objects.create(dimension=standard, key="second_standard")
        terms = {
            "service_type:custody": tenant_lists_logic.term_by_ref("service_type", "custody"),
            # Seeded inactive (tests_matching.HeldStandard); the rule ignores a term's state.
            "standard:iso_iec_27001": TaxonomyTerm.objects.get(dimension=standard, key="iso_iec_27001"),
            "standard:second_standard": second,
        }
        subsets = [combo for n in range(len(terms) + 1) for combo in itertools.combinations(terms, n)]

        def as_dict(refs: tuple[str, ...]) -> dict[str, set[str]]:
            result: dict[str, set[str]] = {}
            for ref in refs:
                dimension, key = ref.split(":")
                result.setdefault(dimension, set()).add(key)
            return result

        def verdicts(footprint_refs: tuple[str, ...], record_refs: tuple[str, ...]) -> tuple[bool, bool]:
            self.activate(self.tenant)
            FootprintTerm.objects.filter(tenant=self.tenant).delete()
            for ref in footprint_refs:
                FootprintTerm.objects.create(tenant=self.tenant, term=terms[ref], added_by=self.admin)
            pure = matching.in_footprint(as_dict(record_refs), matching.footprint_of(self.tenant.id), restricting=matching.restricting_dimensions())
            return pure, matching.in_footprint_sql(self.tenant.id, [terms[ref].id for ref in record_refs])

        def every_combination_agrees() -> None:
            for footprint_refs in subsets:
                for record_refs in subsets:
                    pure, sql = verdicts(footprint_refs, record_refs)
                    self.assertIs(sql, pure, f"record {record_refs} footprint {footprint_refs}")

        every_combination_agrees()
        iso = ("standard:iso_iec_27001",)
        custody = ("service_type:custody",)
        # A record carrying an opt-in term matches only when the scope names that term, also
        # when the scope has no entry for the dimension at all.
        self.assertEqual(verdicts(custody, iso), (False, False))
        self.assertEqual(verdicts((), iso), (False, False))
        self.assertEqual(verdicts(("standard:second_standard",), iso), (False, False))
        self.assertEqual(verdicts(iso, iso), (True, True))
        # An empty scope dimension still does not restrict.
        self.assertEqual(verdicts(iso, custody + iso), (True, True))
        # A record carrying no opt-in term is unaffected by the opt-in dimension.
        self.assertEqual(verdicts(custody, custody), (True, True))
        self.assertEqual(verdicts(custody + iso, custody), (True, True))
        self.assertEqual(verdicts((), ()), (True, True))
        # With the flag cleared both still treat the dimension as restricting.
        with library_write("test"):
            TermDimension.objects.filter(pk=standard.pk).update(restricts_footprint=False)
        self.assertIn("standard", matching.restricting_dimensions())
        every_combination_agrees()
        self.assertEqual(verdicts(custody, iso), (False, False))
        self.assertEqual(verdicts(iso, iso), (True, True))
        # The regulatory scope read says so too, so a reader never offers "not restricted".
        view = self._footprint(sign_in(self.reader, tenant=self.tenant))
        read = next(d for d in view["dimensions"] if d["dimension"]["key"] == "standard")
        self.assertEqual((read["dimension"]["kind"], read["restrictsFootprint"]), ("opt_in", True))
        # Calling the pure rule without the opt-in dimensions is a TypeError: leaving the
        # argument out, or handing it a plain set that cannot say which dimensions are opt-in.
        with self.assertRaises(TypeError):
            matching.in_footprint(as_dict(iso), {})  # type: ignore[call-arg]
        with self.assertRaises(TypeError):
            matching.in_footprint(as_dict(iso), {}, restricting={"service_type", "standard"})

    @skip("pending: ACC-S2 (ACC-02, AC-ACC1, chunk 11)")
    def test_acc_s2(self) -> None:
        """ACC-S2

        An entry's scope narrows the footprint and can never widen it (ACC-02, AC-ACC1).
        """
