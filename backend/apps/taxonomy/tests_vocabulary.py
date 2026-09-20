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

from apps.identity.models import User
from apps.library.models import Language
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories
from apps.shared.audit import Actor
from apps.shared.models import AuditEvent
from apps.shared.tenancy import library_write
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import (
    CaseStatusCategory,
    CaseSubStatus,
    ChangeLifecycleKind,
    ChangeType,
    EffortSize,
    RejectionReason,
    RiskRating,
    TaxonomyTerm,
    TaxonomyTermLabel,
    TenantTag,
)
from apps.taxonomy.seeds import (
    LIBRARY_SYSTEM_ROWS,
    SystemRow as LibrarySystemRow,
    seed_library_vocabularies,
    seed_taxonomy_terms,
    seed_term_dimensions,
    taxonomy_term_specs,
)
from apps.taxonomy.tenant_hooks import TENANT_SYSTEM_ROWS, SystemRow, ensure_tenant_vocabularies
from config.api import api

V1 = "/api/v1"
SEED = Actor.system("seed_reference")
# schema v0.3's `proposal.rejection_code` CHECK, in its order: the only list the inputs define.
REJECTION_REASONS = ["wrong_fact", "wrong_scope", "bad_source", "duplicate", "not_relevant", "poor_wording", "other"]


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
        created = self._post("/vocab/risk_rating", {"labels": {"en": "Severe"}, "extra": {"ordinal": "9"}}, self.admin)
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
        rated = self._post("/vocab/risk_rating", {"labels": {"en": "Severe"}, "extra": {"ordinal": 9}}, self.admin)
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

    def test_every_deploy_files_the_seven_reasons_in_en_and_sv(self) -> None:
        listed = {item["list"]: item for item in self._get("/vocab").json()["items"]}
        summary = listed["rejection_reason"]
        self.assertEqual(
            (summary["tier"], summary["kind"], summary["kinds"], summary["count"], summary["proposable"]),
            (2, None, [], 7, True),
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
        self.assertEqual(seeded, wanted, "a seed run files every term of the fixture and no other")
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
