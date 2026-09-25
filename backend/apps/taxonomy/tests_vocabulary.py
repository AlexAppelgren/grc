"""Vocabulary and footprint rule branches (playbook 8.1: tests required with every change to
vocabulary retire and merge, footprint matching and four eyes).

The scenarios in tests_scenarios.py walk the happy paths and the refusals a person meets on
the screen. These pin the refusals a client meets at the edges: an unknown list or key, a
label in no language, a kind the list does not know, a stale or malformed `If-Match`, a
reorder that names a stranger, a merge into itself, a decided suggestion, an empty footprint
change, and who may read what.
"""

from __future__ import annotations

import json
from io import StringIO
from typing import Any
from unittest import mock

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext

from apps.cases import testing as cases_build
from apps.identity.models import User
from apps.library import testing as library_build
from apps.library.models import Jurisdiction, Language, Obligation
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories
from apps.shared.audit import Actor
from apps.shared.models import AuditEvent
from apps.shared.tenancy import library_write
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import (
    CaseStatusCategory,
    GapStatus,
    Team,
    CaseSubStatus,
    ChangeLifecycleKind,
    ChangeType,
    DutyType,
    EffortSize,
    FootprintChangeRequest,
    FootprintTerm,
    RejectionReason,
    RelationType,
    RiskRating,
    TaxonomyTerm,
    TaxonomyTermLabel,
    TenantTag,
)
from apps.taxonomy.seeds import (
    JURISDICTION_DIMENSION,
    LIBRARY_SYSTEM_ROWS,
    MIRRORED_JURISDICTION_KINDS,
    SystemRow as LibrarySystemRow,
    seed_library_vocabularies,
    seed_taxonomy_terms,
    seed_term_dimensions,
    taxonomy_term_specs,
)
from apps.taxonomy.registry import REGISTRY, VocabularyList
from apps.taxonomy.tenant_lists_logic import KEY_MAX_CHARS, LABEL_MAX_CHARS
from apps.taxonomy import repoint
from apps.taxonomy.tenant_hooks import TENANT_SYSTEM_ROWS, SystemRow, ensure_tenant_vocabularies
from apps.watch import testing as watch_build
from apps.watch import write as watch_door
from config.api import api

V1 = "/api/v1"
SEED = Actor.system("seed_reference")
# The kind the International row is seeded under (D-38): no bank operates there, so it must
# stay out of the mirror. Written as the literal the wire carries, so a renamed member fails here.
UNOPERATED_JURISDICTION_KIND = "international"
# schema v0.3's `proposal.rejection_code` CHECK, in its order, with the PRD's sector scope
# (PRO-S9) filed beside "not relevant".
REJECTION_REASONS = ["wrong_fact", "wrong_scope", "bad_source", "duplicate", "not_relevant", "outside_sector_scope", "poor_wording", "other"]


class VocabularyEdges(ScenarioTestCase):
    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        self.tenant = factories.tenant(slug="bank")
        self.activate(self.tenant)
        ensure_tenant_vocabularies(self.tenant, actor=SEED)
        self.admin_user = factories.member(self.tenant, roles=("admin",)).user
        self.admin = sign_in(self.admin_user, tenant=self.tenant)
        self.editor = sign_in(factories.platform_user(roles=("library_editor",), email="editor@bleqq.test"))

    def _post(self, path: str, body: dict[str, Any], headers: dict[str, Any], **extra: Any) -> Any:  # compliance: allow-kwargs test helper forwarding request headers
        return self.client.post(f"{V1}{path}", data=body, content_type="application/json", **headers, **extra)

    def _patch(self, path: str, body: dict[str, Any], headers: dict[str, Any], **extra: Any) -> Any:  # compliance: allow-kwargs test helper forwarding request headers
        return self.client.patch(f"{V1}{path}", data=body, content_type="application/json", **headers, **extra)

    def _get(self, path: str, headers: dict[str, Any]) -> Any:
        return self.client.get(f"{V1}{path}", **headers)

    def _code(self, response: Any) -> str:
        return str(response.json()["code"])

    def test_a_tenant_lists_extra_values_are_typed_before_they_are_written(self) -> None:
        refused = self._patch("/vocab/risk_rating/low", {"extra": {"ordinal": "abc"}}, self.admin)
        self.assertEqual(refused.status_code, 422, refused.content)
        self.assertEqual(self._code(refused), "validation_error")
        self.assertIn("ordinal", refused.json()["detail"])
        created = self._post("/vocab/risk_rating", {"labels": {"en": "Severe"}, "kind": "high", "extra": {"ordinal": "9"}}, self.admin)
        self.assertEqual(created.status_code, 201, created.content)
        self.activate(self.tenant)
        self.assertEqual(RiskRating.objects.get(tenant=self.tenant, key="severe").ordinal, 9)

    def test_lists_rows_and_keys_that_do_not_exist_are_not_found(self) -> None:
        self.assertEqual(self._get("/vocab/planets", self.admin).status_code, 404)
        self.assertIn("tenant_tag", self._get("/vocab/planets", self.admin).json()["detail"])
        self.assertEqual(self._get("/vocab/tenant_tag/nothing", self.admin).status_code, 404)
        self.assertEqual(self._patch("/vocab/tenant_tag/nothing", {"labels": {"en": "x"}}, self.admin).status_code, 404)
        self.assertEqual(self._get("/taxonomy/terms?dimension=planet", self.admin).status_code, 422)
        self.assertIn("service_type", self._get("/taxonomy/terms?dimension=planet", self.admin).json()["detail"])

    def test_a_platform_session_reads_library_lists_and_no_tenant_list(self) -> None:
        lists = {item["list"] for item in self._get("/vocab", self.editor).json()["items"]}
        self.assertIn("urgency", lists)
        self.assertNotIn("tenant_tag", lists)
        self.assertEqual(self._get("/vocab/tenant_tag", self.editor).status_code, 403)
        self.assertEqual(self._get("/tenant/footprint", self.editor).status_code, 404)
        dimensions = {row["key"]: row for row in self._get("/taxonomy/dimensions", self.editor).json()["items"]}
        self.assertFalse(dimensions["theme"]["extra"]["restrictsFootprint"])
        self.assertTrue(dimensions["service_type"]["extra"]["restrictsFootprint"])
        self.assertEqual(dimensions["theme"]["kind"], "classification")

    def test_a_create_needs_a_label_in_a_real_language_and_a_known_kind(self) -> None:
        self.assertEqual(self._code(self._post("/vocab/tenant_tag", {"labels": {"en": "  "}}, self.admin)), "validation_error")
        self.assertEqual(self._code(self._post("/vocab/tenant_tag", {"labels": {"en": "!!!"}}, self.admin)), "validation_error")
        self.assertEqual(self._code(self._post("/vocab/case_sub_status", {"labels": {"en": "Parked"}}, self.admin)), "unknown_key")
        # A list with no kind ignores one sent by mistake rather than storing it.
        plain = self._post("/vocab/tenant_tag", {"labels": {"en": "Leasing"}, "kind": "anything"}, self.admin)
        self.assertEqual(plain.status_code, 201, plain.content)
        self.assertIsNone(plain.json()["kind"])
        # The list's own columns are written from the camelCased names reads return.
        rated = self._post("/vocab/risk_rating", {"labels": {"en": "Severe"}, "kind": "high", "extra": {"ordinal": 9}}, self.admin)
        self.assertEqual(rated.status_code, 201, rated.content)
        self.assertEqual(rated.json()["extra"], {"ordinal": 9})
        self.activate(self.tenant)
        self.assertEqual(RiskRating.objects.get(tenant=self.tenant, key="severe").ordinal, 9)

    def test_a_patch_checks_if_match_and_writes_the_note_order_and_columns(self) -> None:
        malformed = self._patch("/vocab/risk_rating/low", {"usageNote": "x"}, self.admin, HTTP_IF_MATCH="yesterday")
        self.assertEqual(malformed.status_code, 422)
        patched = self._patch("/vocab/risk_rating/low", {"usageNote": "  Tolerable.  ", "sortOrder": 7, "extra": {"ordinal": 2}}, self.admin, HTTP_IF_MATCH='W/"1"')
        self.assertEqual(patched.status_code, 200, patched.content)
        body = patched.json()
        self.assertEqual((body["usageNote"], body["sortOrder"], body["extra"], body["version"]), ("Tolerable.", 7, {"ordinal": 2}, 2))
        self.assertEqual(self._code(self._patch("/vocab/risk_rating/low", {"usageNote": "y"}, self.admin, HTTP_IF_MATCH="1")), "stale_write")

    def test_reorder_merge_and_suggestions_refuse_what_they_cannot_do(self) -> None:
        self.assertEqual(self._code(self._post("/vocab/tenant_tag/reorder", {"keys": ["follow_up", "stranger"]}, self.admin)), "unknown_key")
        self.assertEqual(self._post("/vocab/urgency/reorder", {"keys": ["monitor"]}, self.admin).status_code, 403)
        self._post("/vocab/tenant_tag", {"labels": {"en": "Custody"}}, self.admin)
        self.assertEqual(self._code(self._post("/vocab/tenant_tag/custody/merge", {"into": "custody"}, self.admin)), "validation_error")
        self.assertEqual(self._code(self._post("/vocab/tenant_tag/follow_up/merge", {"into": "custody"}, self.admin)), "system_row")
        self.assertEqual(self._code(self._post("/vocab/tenant_tag/custody/merge", {"into": "nothing"}, self.admin)), "not_found")
        reader = sign_in(factories.member(self.tenant, roles=("reader",)).user, tenant=self.tenant)
        suggestion = self._post("/vocab/tenant_tag/suggest", {"labels": {"en": "Leasing"}}, reader).json()
        self.assertEqual(self._post("/vocab/tenant_tag/suggestions/00000000-0000-4000-8000-000000000000/decline", {}, self.admin).status_code, 404)
        self.assertEqual(self._post("/vocab/tenant_tag/suggestions/not-a-uuid/decline", {}, self.admin).status_code, 404)
        self.assertEqual(self._post(f"/vocab/tenant_tag/suggestions/{suggestion['id']}/decline", {}, self.admin).status_code, 200)
        self.assertEqual(self._code(self._post(f"/vocab/tenant_tag/suggestions/{suggestion['id']}/decline", {}, self.admin)), "invalid_transition")
        # A suggestion for a key that already exists is the duplicate it would become.
        self.assertEqual(self._code(self._post("/vocab/tenant_tag/suggest", {"labels": {"en": "Custody"}}, reader)), "duplicate_key")

    def test_a_tenants_reorder_retire_and_default_survive_the_next_deploy(self) -> None:
        """`seed_reference` runs the tenant hook for every tenant on every deploy. It writes a
        system row's order, active flag and default only when it creates the row, so a deploy
        never undoes the tenant's own choices, and each row it creates leaves one audit row."""
        self.activate(self.tenant)
        seeded = AuditEvent.objects.filter(tenant=self.tenant, action="vocabulary.created")
        self.assertEqual(seeded.count(), sum(len(rows) for _, rows in TENANT_SYSTEM_ROWS.values()))
        medium = seeded.get(subject_title="effort_size:m")
        # Whoever seeded the tenant is on the row; here the test factory that created it.
        self.assertEqual((medium.actor_type, medium.actor_label), ("system", "test_factory"))
        self.assertEqual(medium.subject_id, EffortSize.objects.get(tenant=self.tenant, key="m").id)
        self.assertEqual(medium.after, {"list": "effort_size", "key": "m", "labels": {"en": "M", "sv": "M"}, "kind": None})
        self.assertEqual(self._post("/vocab/effort_size/reorder", {"keys": ["l", "m", "s"]}, self.admin).status_code, 200)
        # No route retires a system row or moves a list's default yet, so those changes are
        # made on the rows themselves.
        self.activate(self.tenant)
        EffortSize.objects.filter(tenant=self.tenant, key="s").update(active=False)
        EffortSize.objects.filter(tenant=self.tenant, key="m").update(is_default=False)
        EffortSize.objects.filter(tenant=self.tenant, key="l").update(is_default=True)
        events = AuditEvent.objects.filter(tenant=self.tenant).count()
        call_command("seed_reference", stdout=StringIO())
        self.activate(self.tenant)
        rows = {row.key: (row.sort_order, row.active, row.is_default) for row in EffortSize.objects.filter(tenant=self.tenant)}
        self.assertEqual(rows, {"l": (0, True, True), "m": (1, True, False), "s": (2, False, False)})
        self.assertEqual(AuditEvent.objects.filter(tenant=self.tenant).count(), events, "a second deploy records nothing")

    def test_a_deploy_puts_a_system_rows_kind_back_and_records_it(self) -> None:
        """A system row's kind is the code's: no route changes it, so putting it back undoes
        no tenant choice, and every case status category keeps its system row."""
        self.activate(self.tenant)
        CaseSubStatus.objects.filter(tenant=self.tenant, key="assigned").update(kind=CaseStatusCategory.NEW.value)
        ensure_tenant_vocabularies(self.tenant, actor=SEED)
        row = CaseSubStatus.objects.get(tenant=self.tenant, key="assigned")
        self.assertEqual((row.kind, row.version), (CaseStatusCategory.ASSIGNED.value, 2))
        fixed = AuditEvent.objects.filter(tenant=self.tenant, action="vocabulary.updated")
        self.assertEqual(
            [(event.actor_label, event.subject_id, event.before, event.after) for event in fixed],
            [("seed_reference", row.id, {"kind": "new"}, {"kind": "assigned"})],
        )
        ensure_tenant_vocabularies(self.tenant, actor=SEED)
        self.assertEqual(fixed.count(), 1, "nothing to put back, nothing recorded")

    def test_a_system_key_the_tenant_already_uses_stops_the_seed(self) -> None:
        """A new system row whose key the tenant already chose for its own value is refused
        loudly: adopting the tenant's row would leave the list without its system value."""
        self.assertEqual(self._post("/vocab/tenant_tag", {"labels": {"en": "Leasing"}}, self.admin).status_code, 201)
        default_key, rows = TENANT_SYSTEM_ROWS["tenant_tag"]
        self.activate(self.tenant)
        with mock.patch.dict(TENANT_SYSTEM_ROWS, {"tenant_tag": (default_key, [*rows, SystemRow("leasing", {"en": "Leasing"})])}):
            with self.assertRaises(ValidationError) as refused:
                ensure_tenant_vocabularies(self.tenant, actor=SEED)
        self.assertEqual(refused.exception.code, "system_key_taken")
        self.assertIn("tenant_tag:leasing", refused.exception.message)
        self.assertFalse(TenantTag.objects.get(tenant=self.tenant, key="leasing").is_system)

    def test_an_agent_reads_with_library_read_and_never_writes(self) -> None:
        key = factories.api_key(self.tenant, scopes=("library:read",))
        agent = {"HTTP_X_API_KEY": key.plain_key}
        self.assertEqual(self._get("/vocab/urgency/act_now", agent).json()["key"], "act_now")
        self.assertEqual(self._get("/taxonomy/terms?dimension=regime", agent).status_code, 200)
        self.assertEqual(self._get("/vocab", agent).status_code, 401)
        self.assertEqual(self._post("/vocab/tenant_tag", {"labels": {"en": "x"}}, agent).status_code, 401)
        self.assertEqual(self._get("/tenant/footprint", agent).status_code, 401)
        writer = factories.api_key(self.tenant, scopes=("changes:write",))
        denied = self._post("/proposals", {"kind": "vocabulary_retire", "title": "x", "payload": {"list": "flag", "key": "ai"}}, {"HTTP_X_API_KEY": writer.plain_key})
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["requiredPermission"], "proposals:write")

    def test_labels_fall_back_along_the_callers_languages_then_the_original(self) -> None:
        self.activate(self.tenant)
        User.objects.filter(pk=self.admin_user.pk).update(locale=Language.objects.get(key="da"))
        admin = sign_in(self.admin_user, tenant=self.tenant)
        created = self._post("/vocab/tenant_tag", {"labels": {"fi": "Säilytys"}}, admin)
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["label"], "Säilytys", "no da, no tenant language, no en: the original")
        detail = self._get(f"/vocab/tenant_tag/{created.json()['key']}", admin).json()
        self.assertEqual(detail["originalLanguage"], "fi")

    def test_a_footprint_change_names_terms_that_exist_and_is_never_empty(self) -> None:
        officer_user = factories.member(self.tenant, roles=("compliance_officer",)).user
        officer = sign_in(officer_user, tenant=self.tenant)
        self.assertEqual(self._code(self._post("/tenant/footprint/requests", {"adds": [], "removes": []}, officer)), "validation_error")
        both = {"adds": [{"dimension": "regime", "key": "aml"}], "removes": [{"dimension": "regime", "key": "aml"}]}
        self.assertEqual(self._code(self._post("/tenant/footprint/requests", both, officer)), "validation_error")
        self.assertEqual(self._code(self._post("/tenant/footprint/requests", {"adds": [{"dimension": "planet", "key": "x"}]}, officer)), "unknown_key")
        missing = "/tenant/footprint/requests/00000000-0000-4000-8000-000000000000"
        approver = sign_in(self.admin_user, tenant=self.tenant, step_up=True)
        self.assertEqual(self._post(f"{missing}/approve", {}, approver).status_code, 404)
        self.assertEqual(self._post(f"{missing}/reject", {}, approver).status_code, 404)
        # The requester cannot reject their own request either: deciding is four eyes both ways.
        created = self._post("/tenant/footprint/requests", {"adds": [{"dimension": "regime", "key": "aml"}]}, officer).json()
        own = self._post(f"/tenant/footprint/requests/{created['id']}/reject", {}, officer)
        self.assertEqual(own.status_code, 409)
        self.assertEqual(self._code(own), "four_eyes_violation")
        # Approving a term the footprint already carries, or removing one it lacks, changes nothing twice.
        approved = self._post(f"/tenant/footprint/requests/{created['id']}/approve", {}, approver)
        self.assertEqual(approved.status_code, 200, approved.content)
        again = self._post("/tenant/footprint/requests", {"adds": [{"dimension": "regime", "key": "aml"}], "removes": [{"dimension": "regime", "key": "tax"}]}, officer).json()
        self.assertEqual(self._post(f"/tenant/footprint/requests/{again['id']}/approve", {}, approver).status_code, 200)
        regimes = {t["key"] for d in self._get("/tenant/footprint", officer).json()["dimensions"] if d["dimension"]["key"] == "regime" for t in d["terms"]}
        self.assertEqual(regimes, {"aml"})

    def test_a_footprint_change_naming_a_term_twice_is_refused_before_anything_is_written(self) -> None:
        officer = sign_in(factories.member(self.tenant, roles=("compliance_officer",)).user, tenant=self.tenant)
        aml = {"dimension": "regime", "key": "aml"}
        for body in ({"adds": [aml, aml]}, {"removes": [aml, aml]}):
            for path in ("/tenant/footprint/requests?dryRun=true", "/tenant/footprint/requests"):
                refused = self._post(path, body, officer)
                self.assertEqual(refused.status_code, 422, refused.content)
                self.assertEqual(self._code(refused), "validation_error")
        self.assertFalse(FootprintChangeRequest.objects.exists())

    def test_an_approval_never_switches_on_a_term_retired_while_the_request_waited(self) -> None:
        officer = sign_in(factories.member(self.tenant, roles=("compliance_officer",)).user, tenant=self.tenant)
        created = self._post("/tenant/footprint/requests", {"adds": [{"dimension": "regime", "key": "aml"}]}, officer)
        self.assertEqual(created.status_code, 201, created.content)
        with library_write("test"):
            TaxonomyTerm.objects.filter(dimension__key="regime", key="aml").update(active=False)
        approver = sign_in(self.admin_user, tenant=self.tenant, step_up=True)
        refused = self._post(f"/tenant/footprint/requests/{created.json()['id']}/approve", {}, approver)
        self.assertEqual(refused.status_code, 409, refused.content)
        self.assertEqual(self._code(refused), "stale_write")
        self.assertFalse(FootprintTerm.objects.filter(term__key="aml", term__dimension__key="regime").exists())
        self.assertEqual(FootprintChangeRequest.objects.get().status, "pending")


class RejectionReasons(ScenarioTestCase):
    """Rejection reasons are a library list (PRO-01, VOC-01, VOC-07, AC-VOC1): every deploy
    files schema v0.3's seven codes, a change is a proposal a second editor approves, a new
    reason leaves the contract as it was, and a deploy never undoes an approved relabel."""

    def setUp(self) -> None:
        call_command("seed_reference", stdout=StringIO())
        self.editor = sign_in(factories.platform_user(roles=("library_editor",), email="editor@bleqq.test"))
        self.second_editor = factories.platform_user(roles=("library_editor",), email="editor2@bleqq.test")

    def _get(self, path: str) -> Any:
        return self.client.get(f"{V1}{path}", **self.editor)

    def _write(self, method: str, path: str, body: dict[str, Any], **headers: Any) -> Any:  # compliance: allow-kwargs test helper forwarding request headers
        call = self.client.patch if method == "PATCH" else self.client.post
        return call(f"{V1}{path}", data=body, content_type="application/json", **self.editor, **headers)

    def _approve(self, proposed: Any) -> None:
        self.assertEqual(proposed.status_code, 202, proposed.content)
        approved = self.client.post(
            f"{V1}/proposals/{proposed.json()['proposal']['id']}/approve", data={}, content_type="application/json",
            **sign_in(self.second_editor, step_up=True),
        )
        self.assertEqual(approved.status_code, 200, approved.content)

    def _rows(self) -> dict[str, Any]:
        return {row["key"]: row for row in self._get("/vocab/rejection_reason").json()["items"]}

    def test_every_deploy_files_the_eight_reasons_in_en_and_sv(self) -> None:
        listed = {item["list"]: item for item in self._get("/vocab").json()["items"]}
        summary = listed["rejection_reason"]
        self.assertEqual(
            (summary["tier"], summary["kind"], summary["kinds"], summary["count"], summary["proposable"]),
            (2, None, [], len(REJECTION_REASONS), True),
        )
        rows = self._rows()
        self.assertEqual(list(rows), REJECTION_REASONS)
        for key, row in rows.items():
            with self.subTest(key=key):
                self.assertIsNone(row["kind"])
                self.assertTrue(row["isSystem"])
                self.assertEqual(set(row["labels"]), {"en", "sv"})
                self.assertTrue(all(text.strip() for text in row["labels"].values()))
        self.assertEqual([key for key, row in rows.items() if row["isDefault"]], ["other"])

    def test_a_write_is_a_proposal_and_a_new_reason_leaves_the_contract_as_it_was(self) -> None:
        before = json.dumps(api.get_openapi_schema(), sort_keys=True)
        proposed = self._write("POST", "/vocab/rejection_reason", {"labels": {"en": "Out of date", "sv": "Inaktuell"}})
        self.assertEqual(proposed.status_code, 202, proposed.content)
        proposal = proposed.json()["proposal"]
        self.assertEqual((proposal["kind"], proposal["status"], proposal["payload"]["list"]), ("vocabulary_create", "open", "rejection_reason"))
        self.assertNotIn("out_of_date", self._rows())
        self._approve(proposed)
        self.assertEqual(self._rows()["out_of_date"]["labels"], {"en": "Out of date", "sv": "Inaktuell"})
        self.assertEqual(before, json.dumps(api.get_openapi_schema(), sort_keys=True))
        # A system reason is relabelled through a proposal too, and never retired.
        relabel = self._write("PATCH", "/vocab/rejection_reason/other", {"labels": {"en": "Something else"}}, HTTP_IF_MATCH="1")
        self.assertEqual(relabel.status_code, 202, relabel.content)
        self.assertEqual(relabel.json()["proposal"]["kind"], "vocabulary_relabel")
        self.assertEqual(self._rows()["other"]["labels"]["en"], "Other")
        retire = self._write("POST", "/vocab/rejection_reason/other/retire", {"confirm": True})
        self.assertEqual((retire.status_code, retire.json()["code"]), (409, "system_row"))

    def test_the_next_deploy_keeps_an_approved_relabel_and_adds_no_row(self) -> None:
        self._approve(self._write("PATCH", "/vocab/rejection_reason/wrong_fact", {"labels": {"en": "Factual error"}}, HTTP_IF_MATCH="1"))
        call_command("seed_reference", stdout=StringIO())
        rows = self._rows()
        self.assertEqual(list(rows), REJECTION_REASONS)
        self.assertEqual(rows["wrong_fact"]["labels"], {"en": "Factual error", "sv": "Felaktig uppgift"})


class ReferenceSeedRuns(ScenarioTestCase):
    """What a deploy may touch (VOC-01, VOC-07, FP-01). `seed_reference` runs on every
    deploy. It creates a reference row once and never writes it again, so an approved
    reorder, retire or default change is still there after the next deploy; re-applying the
    code's sort order and active flag would undo it silently, with nothing in the log to
    say so. Every row it creates leaves one audit row, as the library seed does.

    Banking and payments join the regimes (PRD 0.2 names them first in the sector scope),
    the payment and credit sector's permit types join `legal_entity`, and card issuing and
    card acquiring join `licensed_activity`.
    """

    NEW_TERMS = (
        ("regime", "banking", "Banking", "Bankverksamhet"),
        ("regime", "payments", "Payments", "Betalningar"),
        ("legal_entity", "payment_institution", "Payment institution", "Betalningsinstitut"),
        ("legal_entity", "emoney_institution", "E-money institution", "Institut för elektroniska pengar"),
        ("legal_entity", "credit_market_company", "Credit market company", "Kreditmarknadsföretag"),
        ("legal_entity", "investment_firm", "Investment firm", "Värdepappersbolag"),
        ("licensed_activity", "card_issuing", "Card issuing", "Kortutgivning"),
        ("licensed_activity", "card_acquiring", "Card acquiring", "Kortinlösen"),
    )

    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_taxonomy_terms()
        self.editor = sign_in(factories.platform_user(roles=("library_editor",), email="editor@bleqq.test"))
        self.second_editor = factories.platform_user(roles=("library_editor",), email="editor2@bleqq.test")

    def _seed_again(self) -> None:
        call_command("seed_reference", stdout=StringIO())

    def _labels(self, dimension: str, key: str) -> dict[str, str]:
        term = TaxonomyTerm.objects.get(dimension__key=dimension, key=key)
        return {row.language: row.text for row in TaxonomyTermLabel.objects.filter(term=term)}

    def _approve(self, proposed: Any) -> None:
        self.assertEqual(proposed.status_code, 202, proposed.content)
        approved = self.client.post(
            f"{V1}/proposals/{proposed.json()['proposal']['id']}/approve", data={}, content_type="application/json",
            **sign_in(self.second_editor, step_up=True),
        )
        self.assertEqual(approved.status_code, 200, approved.content)

    def test_the_seed_files_the_new_terms_in_both_languages_and_keeps_every_earlier_key(self) -> None:
        for dimension, key, label_en, label_sv in self.NEW_TERMS:
            with self.subTest(term=f"{dimension}:{key}"):
                self.assertEqual(self._labels(dimension, key), {"en": label_en, "sv": label_sv})
        seeded = {(row.dimension.key, row.key) for row in TaxonomyTerm.objects.select_related("dimension")}
        wanted = {(spec["dimension"], spec["key"]) for spec in taxonomy_term_specs()}
        # The jurisdiction dimension is not in the fixture's term list: its terms mirror the
        # jurisdiction rows, one per mirrored row (FP-04).
        wanted |= {
            (JURISDICTION_DIMENSION, row.key) for row in Jurisdiction.objects.filter(kind__in=MIRRORED_JURISDICTION_KINDS)
        }
        self.assertEqual(seeded, wanted, "a seed run files every term of the fixture, every mirrored jurisdiction and no other")
        # The two new regimes sit at the end of the list, so no earlier term moved (spec §5).
        regimes = list(TaxonomyTerm.objects.filter(dimension__key="regime").order_by("sort_order").values_list("key", flat=True))
        self.assertEqual(regimes[-2:], ["banking", "payments"])
        self.assertEqual(regimes[:6], ["securities", "insurance", "tax", "data_protection", "aml", "ai_ict"])

    def test_the_seed_records_each_term_it_creates_and_a_second_run_records_nothing(self) -> None:
        created = AuditEvent.objects.filter(action="taxonomy.term_created", actor_label="seed_reference")
        self.assertEqual(created.count(), TaxonomyTerm.objects.count())
        banking = created.get(subject_title="regime:banking")
        self.assertEqual(banking.after, {"dimension": "regime", "key": "banking", "labels": {"en": "Banking", "sv": "Bankverksamhet"}})
        self.assertEqual(banking.actor_type, "system")
        seeded = AuditEvent.objects.filter(subject_type__in=("taxonomy_term", "vocabulary"))
        terms, events = TaxonomyTerm.objects.count(), seeded.count()
        self._seed_again()
        self.assertEqual(TaxonomyTerm.objects.count(), terms, "a second deploy creates no term")
        self.assertEqual(seeded.count(), events, "a second deploy records nothing")

    def test_the_seed_records_each_library_list_row_it_creates(self) -> None:
        filed = AuditEvent.objects.filter(action="library.seeded", subject_type="vocabulary")
        self.assertEqual(filed.count(), sum(len(rows) for _, rows in LIBRARY_SYSTEM_ROWS.values()))
        row = filed.get(subject_title="rejection_reason:other")
        self.assertEqual(row.after, {"list": "rejection_reason", "key": "other", "labels": {"en": "Other", "sv": "Annat"}})
        self.assertEqual((row.actor_type, row.actor_label, row.tenant_id), ("system", "seed_reference", None))

    def test_an_approved_term_reorder_survives_the_next_deploy(self) -> None:
        term = TaxonomyTerm.objects.get(dimension__key="regime", key="banking")
        self._approve(
            self.client.patch(
                f"{V1}/taxonomy/terms/{term.id}", data={"sortOrder": 1}, content_type="application/json", **self.editor
            )
        )
        self._seed_again()
        term.refresh_from_db()
        self.assertEqual(term.sort_order, 1, "the deploy must not put the term back where the code has it")

    def test_an_approved_library_list_reorder_retire_and_default_survive_the_next_deploy(self) -> None:
        # No proposal kind reorders a library list yet, so the change is made the way an
        # applied proposal makes it: inside the fence, on the row itself.
        with library_write("test"):
            RejectionReason.objects.filter(key="other").update(sort_order=0, is_default=False)
            RejectionReason.objects.filter(key="duplicate").update(active=False, is_default=True)
        self._seed_again()
        moved = RejectionReason.objects.get(key="other")
        retired = RejectionReason.objects.get(key="duplicate")
        self.assertEqual((moved.sort_order, moved.is_default), (0, False))
        self.assertEqual((retired.active, retired.is_default), (False, True))

    def test_a_deploy_puts_a_library_system_rows_kind_back_and_records_it(self) -> None:
        # No proposal changes a kind, so the code's kind is put back and the fix is logged.
        with library_write("test"):
            ChangeType.objects.filter(key="adopted").update(kind=ChangeLifecycleKind.IN_FORCE.value)
        self._seed_again()
        row = ChangeType.objects.get(key="adopted")
        self.assertEqual((row.kind, row.version), (ChangeLifecycleKind.ADOPTED.value, 2))
        fixed = AuditEvent.objects.filter(action="vocabulary.updated", subject_id=row.id)
        self.assertEqual(
            [(event.actor_label, event.tenant_id, event.before, event.after) for event in fixed],
            [("seed_reference", None, {"kind": "in_force"}, {"kind": "adopted"})],
        )
        self._seed_again()
        self.assertEqual(fixed.count(), 1, "nothing to put back, nothing recorded")

    def test_a_system_key_a_proposal_already_filed_stops_the_seed(self) -> None:
        with library_write("test"):
            RejectionReason.objects.create(key="off_topic", sort_order=9)
        default_key, rows = LIBRARY_SYSTEM_ROWS["rejection_reason"]
        grown = (default_key, [*rows, LibrarySystemRow("off_topic", {"en": "Off topic"}, "Not about this list.")])
        with mock.patch.dict(LIBRARY_SYSTEM_ROWS, {"rejection_reason": grown}), self.assertRaises(ValidationError) as refused:
            seed_library_vocabularies()
        self.assertEqual(refused.exception.code, "system_key_taken")
        self.assertFalse(RejectionReason.objects.get(key="off_topic").is_system)


class JurisdictionTermMirror(ScenarioTestCase):
    """The jurisdiction dimension's terms mirror the jurisdiction rows (FP-04, D-28,
    ADR 0026, the first half of FP-S12): the reference seed owns them, so nobody keeps two
    lists in step by hand, and a jurisdiction no bank operates in gets no term.

    What the seed owns and what it leaves alone is the point of most of these. The link, the
    parent and `active` are put back on every deploy, each with a version bump and an audit
    row, because no proposal may change a mirrored term. The labels and the sort order are
    written once, like every other seeded term, so a deploy cannot silently undo an approved
    translation or reorder; the exactness guard therefore claims the labels for a freshly
    seeded database only, and a label the jurisdiction dropped stays on the term until a
    proposal takes it off.
    """

    def setUp(self) -> None:
        call_command("seed_reference", stdout=StringIO())
        self.tenant = factories.tenant(slug="bank")
        self.activate(self.tenant)
        self.admin = sign_in(factories.member(self.tenant, roles=("admin",)).user, tenant=self.tenant)

    def _terms(self) -> dict[str, TaxonomyTerm]:
        rows = TaxonomyTerm.objects.filter(dimension__key=JURISDICTION_DIMENSION).select_related("parent").prefetch_related("labels")
        return {term.key: term for term in rows}

    def _mirrored_rows(self) -> dict[str, Jurisdiction]:
        rows = Jurisdiction.objects.filter(kind__in=MIRRORED_JURISDICTION_KINDS).select_related("parent").prefetch_related("labels")
        return {row.key: row for row in rows}

    def _state(self) -> list[tuple[Any, ...]]:
        return sorted(
            (
                term.id,
                term.key,
                term.jurisdiction_id,
                term.parent and term.parent.key,
                term.active,
                term.sort_order,
                term.version,
                tuple(sorted((label.language, label.text) for label in term.labels.all())),
            )
            for term in self._terms().values()
        )

    def _term_events(self) -> Any:
        return AuditEvent.objects.filter(subject_type="taxonomy_term", subject_title__startswith=f"{JURISDICTION_DIMENSION}:")

    def test_the_mirror_is_exact_in_both_directions(self) -> None:
        terms, mirrored = self._terms(), self._mirrored_rows()
        self.assertEqual(set(terms), set(mirrored), "every mirrored jurisdiction has a term, and no term invents one")
        for key, term in terms.items():
            with self.subTest(key=key):
                row = mirrored[key]
                self.assertEqual(term.jurisdiction_id, row.id, "the term names the row it mirrors")
                self.assertEqual(term.active, row.active)
                self.assertTrue(term.is_system)
                self.assertEqual(term.parent and term.parent.key, row.parent and row.parent.key)
                # A freshly seeded database only: after this the labels are the term's, and a
                # proposal is the only thing that may change or drop one.
                self.assertEqual(
                    {label.language: label.text for label in term.labels.all()},
                    {label.language: label.text for label in row.labels.all()},
                )
        self.assertEqual(terms["no"].parent and terms["no"].parent.key, "eu", "EU rules reach Norway (D-28)")
        linked = set(TaxonomyTerm.objects.exclude(jurisdiction=None).values_list("dimension__key", flat=True))
        self.assertEqual(linked, {JURISDICTION_DIMENSION}, "no other dimension holds a mirrored term")

    def test_the_regulatory_scope_page_lists_the_five_jurisdictions(self) -> None:
        listed = self.client.get(f"{V1}/taxonomy/terms?dimension={JURISDICTION_DIMENSION}", **self.admin)
        self.assertEqual(listed.status_code, 200, listed.content)
        rows = listed.json()["items"]
        self.assertEqual([row["key"] for row in rows], ["eu", "se", "dk", "no", "fi"])
        self.assertEqual([row["label"] for row in rows], ["European Union", "Sweden", "Denmark", "Norway", "Finland"])
        self.assertEqual([row["parentKey"] for row in rows], [None, "eu", "eu", "eu", "eu"])
        self.assertTrue(all(row["isSystem"] for row in rows))

    def test_a_jurisdiction_nobody_operates_in_is_not_mirrored(self) -> None:
        """The seeded International row standards bodies issue under gets no term: a tenant
        naming its markets would otherwise stop seeing standards (D-38, ADR 0032)."""
        international = Jurisdiction.objects.get(key="intl")
        self.assertEqual(international.kind, UNOPERATED_JURISDICTION_KIND)
        self.assertNotIn(international.kind, MIRRORED_JURISDICTION_KINDS)
        seed_taxonomy_terms()
        self.assertEqual(set(self._terms()), {"eu", "se", "dk", "no", "fi"})
        self.assertFalse(TaxonomyTerm.objects.filter(jurisdiction=international).exists())

    def test_the_seed_records_every_mirrored_term_it_files(self) -> None:
        filed = self._term_events().filter(action="taxonomy.term_created")
        self.assertEqual({event.subject_title for event in filed}, {f"{JURISDICTION_DIMENSION}:{key}" for key in self._terms()})
        union = filed.get(subject_title=f"{JURISDICTION_DIMENSION}:eu")
        self.assertEqual(
            union.after,
            {"dimension": JURISDICTION_DIMENSION, "key": "eu", "labels": {"en": "European Union", "sv": "Europeiska unionen"}},
        )
        self.assertEqual((union.actor_type, union.actor_label), ("system", "seed_reference"))
        self.assertEqual(union.subject_id, self._terms()["eu"].id)

    def test_a_second_seed_run_changes_nothing_and_records_nothing(self) -> None:
        before, events = self._state(), self._term_events().count()
        call_command("seed_reference", stdout=StringIO())
        self.assertEqual(self._state(), before)
        self.assertEqual(self._term_events().count(), events)

    def test_a_jurisdiction_that_moves_takes_its_term_with_it_and_says_so_in_the_log(self) -> None:
        """The three facts the seed owns. Norway leaving the internal market would put its
        term outside the Union's reach, and retiring the row would retire the term; neither
        may happen without a version bump and a line in the log."""
        norway = self._mirrored_rows()["no"]
        Jurisdiction.objects.filter(id=norway.id).update(parent=None, active=False)
        was = self._terms()["no"]
        seed_taxonomy_terms()
        term = self._terms()["no"]
        self.assertEqual((term.parent, term.active, term.version), (None, False, was.version + 1))
        event = self._term_events().get(action="taxonomy.term_updated")
        self.assertEqual(event.before, {"jurisdiction": str(norway.id), "parent": "eu", "active": True})
        self.assertEqual(event.after, {"jurisdiction": str(norway.id), "parent": None, "active": False})
        self.assertEqual((event.actor_type, event.actor_label), ("system", "seed_reference"))

    def test_an_approved_translation_and_reorder_of_a_mirrored_term_survive_the_next_deploy(self) -> None:
        """No proposal may change a mirrored term today (FP-S12 refuses one), but the seed
        must not be the reason: putting the labels and the sort order back on every deploy
        would undo an approved change with nothing in the log to say so."""
        term = self._terms()["se"]
        with library_write("test"):
            TaxonomyTerm.objects.filter(id=term.id).update(sort_order=99)
            TaxonomyTermLabel.objects.filter(term=term, language="sv").update(text="Konungariket Sverige")
        events = self._term_events().count()
        seed_taxonomy_terms()
        kept = self._terms()["se"]
        self.assertEqual(kept.sort_order, 99, "the deploy must not put the sort order back")
        self.assertEqual({label.language: label.text for label in kept.labels.all()}["sv"], "Konungariket Sverige")
        self.assertEqual(kept.version, term.version, "nothing the seed owns changed, so nothing was written")
        self.assertEqual(self._term_events().count(), events)

    def test_a_term_written_by_hand_under_a_mirrored_key_stops_the_seed(self) -> None:
        """The brief said such a term is adopted. It is refused instead, as every other
        reference seed refuses a taken key (INPUT_DELTAS §3): adopting it would keep its
        author's meaning while the dimension lost the row it is supposed to mirror."""
        stray = self._terms()["se"]
        with library_write("test"):
            TaxonomyTerm.objects.filter(id=stray.id).update(jurisdiction=None, parent=None, is_system=False)
        with self.assertRaises(ValidationError) as refused:
            seed_taxonomy_terms()
        self.assertEqual(refused.exception.code, "system_key_taken")
        self.assertIsNone(self._terms()["se"].jurisdiction_id, "the stray term is left as its author wrote it")
        self.assertEqual(TaxonomyTerm.objects.filter(dimension__key=JURISDICTION_DIMENSION, key="se").count(), 1)


class LibraryListUsage(ScenarioTestCase):
    """VOC-02, AC-VOC2: a library list counts the library and watch records that really
    carry each value, so the screen shows the count before a retire and a merge preview
    names what would move. Before this, eight library lists read 0 for every row, and
    "Amends" read 0 while FFFS 2026:11's relation to FFFS 2017:2 carried it."""

    # The value each list's records below carry, one per list that something references.
    USED = {
        "instrument_level": "act",
        "relation_type": "amends",
        "provision_kind": "chapter",
        "duty_type": "conduct",
        "library_tag": "costs",
        "change_type": "adopted",
        "urgency": "act_now",
        "source_kind": "authority_site",
        "flag": "ai",
    }

    def setUp(self) -> None:
        watch_build.seed_watch_reference()
        seed_term_dimensions()
        self.editor = sign_in(factories.platform_user(roles=("library_editor",), email="editor@bleqq.test"))
        amended = library_build.instrument(key="fffs-2017-2", regime="regime:securities")
        amending = library_build.instrument(key="fffs-2026-11", regime="regime:securities")
        library_build.relate_instruments(amending, amended, relation="amends")
        chapter = library_build.provision(amended, key="fffs-2017-2-9-kap", kind="chapter")
        first = library_build.obligation(amended, key="obl-costs", tags=("costs",), cites=(chapter,))
        second = library_build.obligation(amended, key="obl-disclose", duty_type="disclosure")
        library_build.relate(first, second, relation="related")
        self.change = watch_build.change(change_type="adopted", urgency="act_now")
        watch_build.term_link(self.change, flag_key="ai")
        watch_build.source(kind="authority_site")

    def _counts(self, list_name: str) -> dict[str, int]:
        response = self.client.get(f"{V1}/vocab/{list_name}", **self.editor)
        self.assertEqual(response.status_code, 200, response.content)
        return {row["key"]: row["usageCount"] for row in response.json()["items"]}

    def test_every_library_list_something_references_counts_its_real_uses(self) -> None:
        for list_name, key in self.USED.items():
            with self.subTest(list=list_name):
                self.assertGreater(self._counts(list_name)[key], 0)
        # Both instruments sit at the act level; each relation counts on its own list row.
        self.assertEqual(self._counts("instrument_level")["act"], 2)
        relations = self._counts("relation_type")
        self.assertEqual((relations["amends"], relations["related"], relations["implements"]), (1, 1, 0))
        self.assertEqual(self._counts("duty_type")["governance"], 0)

    def test_urgency_counts_the_librarys_suggestions_and_never_a_banks_case(self) -> None:
        tenant = factories.tenant(slug="bank")
        cases_build.case(tenant, self.change, urgency="monitor")
        counts = self._counts("urgency")
        self.assertEqual((counts["act_now"], counts["monitor"]), (1, 0))

    def test_a_list_read_counts_every_linked_table_in_one_query(self) -> None:
        entry = REGISTRY["relation_type"]
        with CaptureQueriesContext(connection) as queries:
            rows = {row.key: row.usage_count for row in entry.usage(RelationType.objects.all())}
        self.assertEqual(len(queries), 1)
        self.assertEqual(rows["amends"], 1)

    def test_the_watch_doors_re_point_writes_watch_tables_and_no_inventory_table(self) -> None:
        # A merge hands each table to the door that may write it; were an inventory table
        # ever handed to the watch door, the door refuses it inside the approval's fence.
        conduct = Obligation.objects.filter(duty_type__key="conduct")
        with self.assertRaises(watch_door.WatchWriteRefused), transaction.atomic(), library_write("test"):
            watch_door.repoint(conduct, conduct.none(), "duty_type", DutyType.objects.get(key="disclosure"))
        self.assertTrue(conduct.exists())

    def test_a_library_list_moves_nothing_outside_an_approved_merge(self) -> None:
        # The preview a library list offers counts what would move and refuses to move it:
        # its rows move only inside the approval (VOC-07). A list nothing references moves
        # nothing either way.
        conduct, disclosure = DutyType.objects.get(key="conduct"), DutyType.objects.get(key="disclosure")
        preview = REGISTRY["duty_type"].repoint
        self.assertEqual(repoint.count(preview(conduct, disclosure, dry_run=True)), Obligation.objects.filter(duty_type=conduct).count())
        with self.assertRaises(RuntimeError):
            preview(conduct, disclosure)
        self.assertEqual(REGISTRY["rejection_reason"].repoint(conduct, disclosure), {})


def _shape(entry: VocabularyList) -> tuple[Any, ...]:
    """What a registry entry promises its readers: tier, models, kind, extra columns,
    whether it is proposed, its references and, for a library list, its links."""
    return (
        entry.tier,
        entry.model.__name__,
        entry.label_model.__name__,
        entry.kind_name,
        entry.kinds,
        entry.kind_required,
        entry.extra_fields,
        entry.proposable,
        tuple(sorted(entry.references.items())),
        tuple((link.model.__name__, link.field) for link in entry.links),
    )


# The registry as chunk 8 found it on main, entry by entry. Chunk 8's register lists change
# exactly five things: the four lists below and the fixed level on risk_rating (VOC-05).
REGISTRY_BEFORE_CHUNK_8: dict[str, tuple[Any, ...]] = {
    "term_dimension": (2, "TermDimension", "TermDimensionLabel", "term_dimension_kind", ("scope", "classification", "opt_in"), True, ("restricts_footprint",), True, (), ()),
    "instrument_level": (2, "InstrumentLevel", "InstrumentLevelLabel", "instrument_level_kind", ("standard",), False, ("binding_default", "rank"), True, (), (("Instrument", "level"),)),
    "provision_kind": (2, "ProvisionKind", "ProvisionKindLabel", "provision_structural_kind", ("division", "unit", "annex"), True, ("jurisdiction",), True, (("jurisdiction", "jurisdiction"),), (("Provision", "kind"),)),
    "change_type": (2, "ChangeType", "ChangeTypeLabel", "change_lifecycle_kind", ("pre_adoption", "adopted", "in_force", "supervisory", "recurring"), True, (), True, (), (("RegulatoryChange", "change_type"),)),
    "duty_type": (2, "DutyType", "DutyTypeLabel", None, (), False, (), True, (), (("Obligation", "duty_type"),)),
    "relation_type": (2, "RelationType", "RelationTypeLabel", None, (), False, (), True, (), (("InstrumentRelation", "relation_type"), ("ObligationRelation", "relation_type"))),
    "source_kind": (2, "SourceKind", "SourceKindLabel", None, (), False, (), True, (), (("Source", "kind"),)),
    "urgency": (2, "Urgency", "UrgencyLabel", "pill_tone", ("information", "notice", "positive", "warning", "negative", "brand"), True, ("ordinal", "sla_days"), True, (), (("RegulatoryChange", "suggested_urgency"),)),
    "library_tag": (2, "LibraryTag", "LibraryTagLabel", None, (), False, (), True, (), (("ObligationTag", "tag"),)),
    "flag": (2, "Flag", "FlagLabel", None, (), False, (), True, (), (("ChangeTerm", "flag"),)),
    "rejection_reason": (2, "RejectionReason", "RejectionReasonLabel", None, (), False, (), True, (), ()),
    "jurisdiction": (2, "Jurisdiction", "JurisdictionLabel", "jurisdiction_kind", ("supranational", "country", "international"), True, (), False, (), ()),
    "tenant_tag": (3, "TenantTag", "TenantTagLabel", None, (), False, (), True, (), ()),
    "link_kind": (3, "LinkKind", "LinkKindLabel", None, (), False, (), True, (), ()),
    "effort_size": (3, "EffortSize", "EffortSizeLabel", None, (), False, (), True, (), ()),
    "compliance_status": (3, "ComplianceStatus", "ComplianceStatusLabel", "compliance_category", ("compliant", "partly", "gap", "not_assessed"), True, ("ordinal",), True, (), ()),
    "risk_rating": (3, "RiskRating", "RiskRatingLabel", None, (), False, ("ordinal",), True, (), ()),
    "case_sub_status": (3, "CaseSubStatus", "CaseSubStatusLabel", "case_status", ("new", "assigned", "assessing", "implementing", "signoff", "closed", "dismissed"), True, (), True, (), ()),
    "dismissal_reason": (3, "DismissalReason", "DismissalReasonLabel", None, (), False, (), True, (), ()),
    "close_reason": (3, "ClosureReason", "ClosureReasonLabel", "close_reason", ("signed_off", "not_applicable", "no_action"), True, (), True, (), ()),
}
CHUNK_8_CHANGES: dict[str, tuple[Any, ...]] = {
    "risk_rating": (3, "RiskRating", "RiskRatingLabel", "risk_level", ("low", "medium", "high"), True, ("ordinal",), True, (), ()),
    "gap_status": (3, "GapStatus", "GapStatusLabel", "gap_category", ("open", "remediating", "risk_accepted", "closed"), True, (), True, (), ()),
    "gap_source": (3, "GapSource", "GapSourceLabel", None, (), False, (), True, (), ()),
    "risk_acceptance_reason": (3, "RiskAcceptanceReason", "RiskAcceptanceReasonLabel", None, (), False, (), True, (), ()),
    "team": (3, "Team", "TeamLabel", None, (), False, ("email",), True, (), ()),
}

# One category of each categorised tenant list and the system row that holds it (VOC-04).
CATEGORY_ROWS = {
    "compliance_status": ("partly", "partly_compliant"),
    "case_sub_status": (CaseStatusCategory.ASSESSING.value, "assessing"),
    "close_reason": ("no_action", "no_action"),
    "gap_status": ("remediating", "remediating"),
}


class RegisterLists(ScenarioTestCase):
    """Chunk 8's register lists (VOC-04, VOC-05, VOC-06, REG-03, TEN-03) and the rules every
    categorised tenant list shares."""

    def setUp(self) -> None:
        seed_languages()
        self.tenant = factories.tenant(slug="bank")
        self.activate(self.tenant)
        ensure_tenant_vocabularies(self.tenant, actor=SEED)
        self.admin = sign_in(factories.member(self.tenant, roles=("admin",)).user, tenant=self.tenant)

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        return self.client.post(f"{V1}{path}", data=body, content_type="application/json", **self.admin)

    def _patch(self, path: str, body: dict[str, Any]) -> Any:
        return self.client.patch(f"{V1}{path}", data=body, content_type="application/json", **self.admin)

    def _items(self, list_name: str) -> dict[str, Any]:
        response = self.client.get(f"{V1}/vocab/{list_name}", **self.admin)
        self.assertEqual(response.status_code, 200, response.content)
        return {row["key"]: row for row in response.json()["items"]}

    def test_the_registry_gained_exactly_the_five_changes(self) -> None:
        self.assertEqual({name: _shape(entry) for name, entry in REGISTRY.items()}, REGISTRY_BEFORE_CHUNK_8 | CHUNK_8_CHANGES)
        self.assertEqual(set(REGISTRY) - set(REGISTRY_BEFORE_CHUNK_8), {"gap_status", "gap_source", "risk_acceptance_reason", "team"})

    def test_retiring_the_last_value_of_a_category_is_refused_on_every_categorised_list(self) -> None:
        for list_name, (kind, system_key) in CATEGORY_ROWS.items():
            with self.subTest(list=list_name):
                self.activate(self.tenant)
                events = AuditEvent.objects.filter(tenant=self.tenant).count()
                # The system row alone holds the category: the refusal names the category.
                refused = self._post(f"/vocab/{list_name}/{system_key}/retire", {"confirm": True})
                self.assertEqual(refused.status_code, 409, refused.content)
                self.assertEqual(refused.json()["code"], "category_empty")
                self.assertIn(kind, refused.json()["detail"])
                self.activate(self.tenant)
                self.assertEqual(AuditEvent.objects.filter(tenant=self.tenant).count(), events, "a refusal records nothing")
                # An organisation's own value is refused the same way once it is the last one.
                own = self._post(f"/vocab/{list_name}", {"labels": {"en": f"Our own {list_name}"}, "kind": kind, "force": True})
                self.assertEqual(own.status_code, 201, own.content)
                self.activate(self.tenant)
                REGISTRY[list_name].model.objects.filter(tenant=self.tenant, key=system_key).update(active=False)
                events = AuditEvent.objects.filter(tenant=self.tenant).count()
                last = self._post(f"/vocab/{list_name}/{own.json()['key']}/retire", {"confirm": True})
                self.assertEqual(last.json()["code"], "category_empty")
                self.activate(self.tenant)
                self.assertTrue(REGISTRY[list_name].model.objects.get(tenant=self.tenant, key=own.json()["key"]).active)
                self.assertEqual(AuditEvent.objects.filter(tenant=self.tenant).count(), events, "a refusal records nothing")

    def test_the_register_lists_file_system_rows_in_en_and_sv_and_a_deploy_keeps_a_relabel(self) -> None:
        expected: dict[str, dict[str, str | None]] = {
            "gap_status": {"open": "open", "remediating": "remediating", "risk_accepted": "risk_accepted", "closed": "closed"},
            "gap_source": dict.fromkeys(("assessment", "change_case", "audit", "incident", "regulator")),
            "risk_acceptance_reason": dict.fromkeys(("accepted_by_management", "cost_disproportionate", "compensating_control", "time_limited", "other")),
            "risk_rating": {"low": "low", "medium": "medium", "high": "high"},
        }
        for list_name, kinds in expected.items():
            with self.subTest(list=list_name):
                self.activate(self.tenant)
                entry = REGISTRY[list_name]
                rows = entry.model.objects.filter(tenant=self.tenant, is_system=True)
                self.assertEqual({row.key: row.kind for row in rows}, kinds)
                languages = {(label.vocabulary.key, label.language) for label in entry.label_model.objects.filter(tenant=self.tenant)}
                self.assertEqual(languages, {(key, language) for key in kinds for language in ("en", "sv")})
        relabelled = self._patch("/vocab/gap_status/open", {"labels": {"en": "Found", "sv": "Hittad"}})
        self.assertEqual(relabelled.status_code, 200, relabelled.content)
        call_command("seed_reference", stdout=StringIO())
        self.assertEqual((self._items("gap_status")["open"]["label"], self._items("gap_status")["open"]["kind"]), ("Found", "open"))
        self.activate(self.tenant)
        self.assertEqual(GapStatus.objects.get(tenant=self.tenant, key="open").labels.get(language="sv").text, "Hittad")

    def test_the_team_list_serves_active_teams_with_their_email(self) -> None:
        created = self._post("/vocab/team", {"labels": {"en": "Legal", "sv": "Juridik"}, "extra": {"email": "legal@bank.example"}})
        self.assertEqual(created.status_code, 201, created.content)
        bad = self._post("/vocab/team", {"labels": {"en": "Cards"}, "extra": {"email": "not an address"}})
        self.assertEqual(bad.status_code, 422, bad.content)
        self.assertIn("email", bad.json()["detail"])
        teams = self._items("team")
        self.assertEqual({key: (row["label"], row["extra"]) for key, row in teams.items()}, {"compliance": ("Compliance", {"email": ""}), "legal": ("Legal", {"email": "legal@bank.example"})})
        self.assertEqual(self._post("/vocab/team/legal/retire", {"confirm": True}).status_code, 200)
        self.assertEqual(set(self._items("team")), {"compliance"})
        # A team is addressable by (tenant, id), so a membership can carry a composite key to it.
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'team_tenant_id_unique'")
            self.assertEqual(cursor.fetchone(), ("UNIQUE (tenant_id, id)",))
        self.activate(self.tenant)
        self.assertEqual(Team.objects.filter(tenant=self.tenant).count(), 2)

    def test_a_label_longer_than_its_column_is_refused_naming_the_language(self) -> None:
        """H35: a label is capped at its column's width, on a tenant list and on a library
        proposal alike, so it is a 422 when it is written, never a 500 when it is saved."""
        self.assertEqual((LABEL_MAX_CHARS, KEY_MAX_CHARS), (200, 80))
        seed_library_vocabularies()
        too_long = "x" * (LABEL_MAX_CHARS + 1)
        created = self._post("/vocab/tenant_tag", {"labels": {"en": too_long}})
        self.assertEqual((created.status_code, created.json()["code"]), (422, "validation_error"))
        self.assertIn("labels.en", created.json()["detail"])
        relabel = self._patch("/vocab/tenant_tag/follow_up", {"labels": {"en": "Fine", "sv": too_long}})
        self.assertEqual(relabel.status_code, 422, relabel.content)
        self.assertIn("labels.sv", relabel.json()["detail"])
        editor = sign_in(factories.platform_user(roles=("library_editor",), email="editor@bleqq.test"))
        proposed = self.client.post(f"{V1}/vocab/flag", data={"labels": {"en": too_long}}, content_type="application/json", **editor)
        self.assertEqual(proposed.status_code, 422, proposed.content)
        self.assertIn("labels.en", proposed.json()["detail"])
        # A label that fits makes a key cut to the key column; a key given too long is refused.
        fits = self._post("/vocab/tenant_tag", {"labels": {"en": "y" * LABEL_MAX_CHARS}})
        self.assertEqual(fits.status_code, 201, fits.content)
        self.assertEqual(fits.json()["key"], "y" * KEY_MAX_CHARS)
        keyed = self._post("/vocab/tenant_tag", {"labels": {"en": "Leasing"}, "key": "k" * (KEY_MAX_CHARS + 1)})
        self.assertEqual(keyed.status_code, 422, keyed.content)
        self.assertIn("key", keyed.json()["detail"])
