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

from django.core.management import call_command

from apps.identity.models import User
from apps.library.models import Language
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import RiskRating
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies
from config.api import api

V1 = "/api/v1"
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
        ensure_tenant_vocabularies(self.tenant)
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
