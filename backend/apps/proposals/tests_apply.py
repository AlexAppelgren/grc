"""Proposal apply (PRO-02, VOC-07; playbook 8.1: tests required with every change to proposal
apply, vocabulary retire and merge).

The scenarios in tests_scenarios.py prove the door: a proposal is the only way into the
library and a second person opens it. These prove what walks through it: every chunk 2 kind
applied against the library as it is at approval time, and refused when the library moved
underneath it (a key someone else created meanwhile, a system row, a row already retired),
with the proposal left open and nothing written.
"""

from __future__ import annotations

from typing import Any

from django.test import Client

from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.proposals.models import Proposal, ProposalStatus
from apps.shared import factories
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import Flag, ProvisionKind, TaxonomyTerm, Urgency
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies

V1 = "/api/v1"


class ProposalApply(ScenarioTestCase):
    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        self.tenant = factories.tenant(slug="bank")
        self.activate(self.tenant)
        ensure_tenant_vocabularies(self.tenant)
        self.officer = factories.member(self.tenant, roles=("compliance_officer",)).user
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        self.reviewer = factories.platform_user(roles=("library_editor",), email="reviewer@bleqq.test")

    # --- helpers ------------------------------------------------------------------------------
    def _post(self, path: str, body: dict[str, Any], headers: dict[str, Any], **extra: Any) -> Any:  # compliance: allow-kwargs test helper forwarding request headers
        return self.client.post(f"{V1}{path}", data=body, content_type="application/json", **headers, **extra)

    def _patch(self, path: str, body: dict[str, Any], headers: dict[str, Any], **extra: Any) -> Any:  # compliance: allow-kwargs test helper forwarding request headers
        return self.client.patch(f"{V1}{path}", data=body, content_type="application/json", **headers, **extra)

    def _approve(self, proposal: dict[str, Any]) -> Any:
        return self._post(f"/proposals/{proposal['id']}/approve", {}, sign_in(self.reviewer, step_up=True))

    def _proposed(self, response: Any) -> dict[str, Any]:
        self.assertEqual(response.status_code, 202, response.content)
        proposal: dict[str, Any] = response.json()["proposal"]
        return proposal

    def _new_flag(self, key: str = "client_money", label: str = "Client money") -> Flag:
        proposal = self._proposed(self._post("/vocab/flag", {"key": key, "labels": {"en": label}}, sign_in(self.editor)))
        self.assertEqual(self._approve(proposal).status_code, 200)
        return Flag.objects.get(key=key)

    # --- vocabulary kinds ---------------------------------------------------------------------
    def test_relabel_applies_labels_note_order_and_extra_columns(self) -> None:
        editor = sign_in(self.editor)
        proposal = self._proposed(
            self._patch(
                "/vocab/urgency/act_now",
                {"labels": {"sv": "Agera omedelbart"}, "usageNote": "Days, not weeks.", "sortOrder": 9, "extra": {"slaDays": 7, "ignored": 1}},
                editor,
                HTTP_IF_MATCH="1",
            )
        )
        self.assertEqual(proposal["kind"], "vocabulary_relabel")
        self.assertEqual(proposal["payload"]["extra"], {"slaDays": 7})
        self.assertEqual(self._approve(proposal).status_code, 200)
        row = Urgency.objects.get(key="act_now")
        self.assertEqual((row.usage_note, row.sort_order, row.sla_days, row.version), ("Days, not weeks.", 9, 7, 2))
        self.assertEqual(row.labels.get(language="sv").text, "Agera omedelbart")
        self.assertEqual(row.labels.get(language="en").text, "Act now")
        # The version moved, so a proposal made from the old read is refused before it queues.
        stale = self._patch("/vocab/urgency/act_now", {"labels": {"en": "x"}}, editor, HTTP_IF_MATCH="1")
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["code"], "stale_write")

    def test_retire_restore_and_merge_of_a_library_value_are_proposals(self) -> None:
        editor = sign_in(self.editor)
        money = self._new_flag()
        funds = self._new_flag("client_funds", "Client funds held")
        retire = self._proposed(self._post("/vocab/flag/client_money/retire", {}, editor))
        self.assertEqual(retire["kind"], "vocabulary_retire")
        self.assertTrue(Flag.objects.get(pk=money.pk).active, "nothing changes until approval")
        self.assertEqual(self._approve(retire).status_code, 200)
        self.assertFalse(Flag.objects.get(pk=money.pk).active)
        self.assertEqual(self._post("/vocab/flag/client_money/retire", {}, editor).json()["code"], "invalid_transition")
        restore = self._proposed(self._post("/vocab/flag/client_money/restore", {}, editor))
        self.assertEqual(restore["kind"], "vocabulary_restore")
        self.assertEqual(self._approve(restore).status_code, 200)
        self.assertTrue(Flag.objects.get(pk=money.pk).active)
        # Merge: the dry run answers what would move and writes nothing; the commit is a proposal.
        before = AuditEvent.objects.count()
        preview = Client().post(f"{V1}/vocab/flag/client_funds/merge?dryRun=true", data={"into": "client_money"}, content_type="application/json", **editor)
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertEqual(preview.json(), {"from": "client_funds", "into": "client_money", "usageCount": 0, "repointed": 0, "dryRun": True})
        self.assertEqual(AuditEvent.objects.count(), before)
        self.assertEqual(self._post("/vocab/flag/client_funds/merge", {"into": "client_funds"}, editor).json()["code"], "validation_error")
        self.assertEqual(self._post("/vocab/flag/ai/merge", {"into": "client_money"}, editor).json()["code"], "system_row")
        merge = self._proposed(self._post("/vocab/flag/client_funds/merge", {"into": "client_money"}, editor))
        self.assertEqual(merge["payload"], {"list": "flag", "key": "client_funds", "into": "client_money"})
        self.assertEqual(self._approve(merge).status_code, 200)
        self.assertFalse(Flag.objects.get(pk=funds.pk).active)
        self.assertEqual(AuditEvent.objects.get(action="vocabulary.merged", subject_id=funds.id).after["into"], "client_money")

    def test_approval_rechecks_the_library_as_it_is_now(self) -> None:
        editor = sign_in(self.editor)
        first = self._proposed(self._post("/vocab/flag", {"key": "custody_risk", "labels": {"en": "Custody risk"}}, editor))
        second = self._proposed(self._post("/vocab/flag", {"key": "custody_risk", "labels": {"en": "Custody risk"}}, sign_in(self.reviewer)))
        self.assertEqual(self._approve(first).status_code, 200)
        # The second proposal named a key that now exists: refused, left open, nothing written.
        clash = self._post(f"/proposals/{second['id']}/approve", {}, sign_in(self.editor, step_up=True))
        self.assertEqual(clash.status_code, 409, clash.content)
        self.assertEqual(clash.json()["code"], "duplicate_key")
        self.assertEqual(Proposal.objects.get(pk=second["id"]).status, ProposalStatus.OPEN.value)
        self.assertEqual(Flag.objects.filter(key="custody_risk").count(), 1)
        # A system row is never retired, even by a proposal that reached the queue directly.
        direct = self._post("/proposals", {"kind": "vocabulary_retire", "title": "Retire ai", "payload": {"list": "flag", "key": "ai"}}, editor)
        self.assertEqual(direct.status_code, 201, direct.content)
        refused = self._approve(direct.json())
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json()["code"], "system_row")
        self.assertTrue(Flag.objects.get(key="ai").active)
        # A row kind the list does not know is refused when the proposal is made, with the valid ones.
        bad_kind = self._post("/proposals", {"kind": "vocabulary_create", "title": "Odd", "payload": {"list": "change_type", "key": "odd", "labels": {"en": "Odd"}, "kind": "sideways"}}, editor)
        self.assertEqual(bad_kind.status_code, 422)
        self.assertEqual(bad_kind.json()["code"], "unknown_key")
        self.assertIn("in_force", bad_kind.json()["detail"])

    def test_proposals_only_name_library_lists_and_real_dimensions(self) -> None:
        editor = sign_in(self.editor)
        tenant_list = self._post("/proposals", {"kind": "vocabulary_create", "title": "Tag", "payload": {"list": "tenant_tag", "key": "x", "labels": {"en": "X"}}}, editor)
        self.assertEqual(tenant_list.status_code, 422)
        self.assertEqual(tenant_list.json()["code"], "unknown_key")
        self.assertIn("flag", tenant_list.json()["detail"])
        seeded = self._post("/proposals", {"kind": "vocabulary_create", "title": "Land", "payload": {"list": "jurisdiction", "key": "is", "labels": {"en": "Iceland"}}}, editor)
        self.assertEqual(seeded.json()["code"], "unknown_key")
        dimension = self._post("/proposals", {"kind": "term_create", "title": "T", "payload": {"dimension": "planet", "key": "x", "labels": {"en": "X"}}}, editor)
        self.assertEqual(dimension.json()["code"], "unknown_key")
        untitled = self._post("/proposals", {"kind": "vocabulary_retire", "title": "  ", "payload": {"list": "flag", "key": "ai"}}, editor)
        self.assertEqual(untitled.json()["code"], "validation_error")
        # Jurisdictions are seeded reference data: the vocabulary routes refuse to queue them.
        self.assertEqual(self._post("/vocab/jurisdiction", {"labels": {"en": "Iceland"}}, editor).json()["code"], "validation_error")

    # --- a proposal made directly is checked like one made through the vocabulary routes ---------
    def _direct(self, kind: str, payload: dict[str, Any], headers: dict[str, Any] | None = None) -> Any:
        body = {"kind": kind, "title": "Direct", "payload": payload}
        return self._post("/proposals", body, headers or sign_in(self.editor))

    def _refused(self, response: Any, code: str) -> None:
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()["code"], code, response.content)

    def test_extra_values_are_typed_and_references_resolved_when_the_proposal_is_made(self) -> None:
        before = Proposal.objects.count()
        urgency = {"list": "urgency", "key": "within_a_day", "labels": {"en": "Within a day"}, "kind": "negative"}
        self._refused(self._direct("vocabulary_create", {**urgency, "extra": {"ordinal": "abc"}}), "validation_error")
        self._refused(self._direct("vocabulary_relabel", {"list": "urgency", "key": "act_now", "extra": {"slaDays": "soon"}}), "validation_error")
        provision = {"list": "provision_kind", "key": "stycke", "labels": {"sv": "Stycke"}, "kind": "unit"}
        self._refused(self._direct("vocabulary_create", {**provision, "extra": {"jurisdiction": "atlantis"}}), "unknown_key")
        # The vocabulary routes build the same payload, so they refuse the same values.
        self._refused(self._patch("/vocab/urgency/act_now", {"extra": {"slaDays": "soon"}}, sign_in(self.editor), HTTP_IF_MATCH="1"), "validation_error")
        self.assertEqual(Proposal.objects.count(), before, "nothing reached the queue")
        # A clean value is stored as its column's type, and a reference becomes the row it names.
        typed = self._direct("vocabulary_create", {**urgency, "extra": {"ordinal": "4", "sla_days": "1"}})
        self.assertEqual(typed.status_code, 201, typed.content)
        self.assertEqual(typed.json()["payload"]["extra"], {"ordinal": 4, "slaDays": 1}, "the queue shows what approval writes")
        self.assertEqual(self._approve(typed.json()).status_code, 200)
        self.assertEqual((Urgency.objects.get(key="within_a_day").ordinal, Urgency.objects.get(key="within_a_day").sla_days), (4, 1))
        placed = self._direct("vocabulary_create", {**provision, "extra": {"jurisdiction": "se"}})
        self.assertEqual(placed.status_code, 201, placed.content)
        self.assertEqual(placed.json()["payload"]["extra"], {"jurisdiction": "se"})
        self.assertEqual(self._approve(placed.json()).status_code, 200)
        self.assertEqual(ProvisionKind.objects.filter(key="stycke").values_list("jurisdiction__key", flat=True).get(), "se")

    def test_extra_carries_only_the_lists_own_columns(self) -> None:
        urgency = {"list": "urgency", "key": "within_a_day", "labels": {"en": "Within a day"}, "kind": "negative"}
        for extra in ({"pillTone": "negative", "background": "#f00"}, {"ordinal": 5, "tone": "brand"}):
            self._refused(self._direct("vocabulary_create", {**urgency, "extra": extra}), "validation_error")
            self._refused(self._direct("vocabulary_relabel", {"list": "urgency", "key": "act_now", "extra": extra}), "validation_error")
        self._refused(self._direct("vocabulary_create", {"list": "flag", "key": "x", "labels": {"en": "X"}, "extra": {"rank": 1}}), "validation_error")
        self.assertFalse(Proposal.objects.exists())

    def test_keys_and_labels_are_checked_when_the_proposal_is_made(self) -> None:
        flag = {"list": "flag", "key": "client_money", "labels": {"en": "Client money"}}
        self._refused(self._direct("vocabulary_create", {**flag, "key": "Bad Key!"}), "validation_error")
        self._refused(self._direct("vocabulary_create", {**flag, "labels": {"zz": "Klientpengar"}}), "unknown_key")
        self._refused(self._direct("vocabulary_create", {**flag, "labels": {"en": "   "}}), "validation_error")
        self._refused(self._direct("vocabulary_relabel", {"list": "flag", "key": "ai", "labels": {"zz": "x"}}), "unknown_key")
        self._refused(self._direct("vocabulary_relabel", {"list": "flag", "key": "AI!", "labels": {"en": "x"}}), "validation_error")
        term = {"dimension": "service_type", "key": "sub_custody", "labels": {"en": "Sub-custody"}}
        self._refused(self._direct("term_create", {**term, "key": "Sub Custody"}), "validation_error")
        self._refused(self._direct("term_create", {**term, "labels": {"zz": "x"}}), "unknown_key")
        self._refused(self._direct("term_update", {"dimension": "service_type", "key": "custody", "labels": {"zz": "x"}}), "unknown_key")
        self._refused(self._direct("term_update", {"dimension": "service_type", "key": "Custody!"}), "validation_error")
        self.assertFalse(Proposal.objects.exists())
        # A good label is stored trimmed, as the vocabulary routes store it.
        made = self._direct("vocabulary_create", {**flag, "labels": {"en": "  Client money  ", "sv": ""}})
        self.assertEqual(made.status_code, 201, made.content)
        self.assertEqual(made.json()["payload"]["labels"], {"en": "Client money"})

    def test_a_stored_payload_that_no_longer_parses_is_refused_at_approval_and_stays_open(self) -> None:
        stored = Proposal.objects.create(
            kind="vocabulary_create", title="Written before the payload schema closed", payload={"list": "flag", "key": "x"}, origin="user"
        )
        refused = self._approve({"id": str(stored.id)})
        self.assertEqual(refused.status_code, 422, refused.content)
        self.assertEqual(refused.json()["code"], "validation_error")
        self.assertIn("labels", refused.json()["detail"])
        self.assertEqual(Proposal.objects.get(pk=stored.pk).status, ProposalStatus.OPEN.value)

    def test_field_sources_are_links_by_field_and_unknown_top_level_fields_are_refused(self) -> None:
        flag = {"list": "flag", "key": "client_money", "labels": {"en": "Client money"}}
        body = {"kind": "vocabulary_create", "title": "Add Client money", "payload": flag}
        editor = sign_in(self.editor)
        self._refused(self._post("/proposals", {**body, "fieldSources": {"labels": {"nested": True}}}, editor), "validation_error")
        self._refused(self._post("/proposals", {**body, "tone": "positive"}, editor), "validation_error")
        self.assertFalse(Proposal.objects.exists())
        made = self._post("/proposals", {**body, "fieldSources": {"labels": "https://www.fi.se/"}}, editor)
        self.assertEqual(made.status_code, 201, made.content)
        self.assertEqual(made.json()["fieldSources"], {"labels": "https://www.fi.se/"})

    # --- term kinds -----------------------------------------------------------------------------
    def test_terms_are_created_under_a_parent_and_updated_through_proposals(self) -> None:
        editor = sign_in(self.editor)
        parent = TaxonomyTerm.objects.get(dimension__key="service_type", key="custody")
        created = self._proposed(self._post("/taxonomy/terms", {"dimension": "service_type", "key": "sub_custody", "labels": {"sv": "Underförvaring"}, "parent": "custody"}, editor))
        self.assertEqual(self._approve(created).status_code, 200)
        term = TaxonomyTerm.objects.get(dimension__key="service_type", key="sub_custody")
        self.assertEqual(term.parent_id, parent.id)
        self.assertTrue(term.labels.get(language="sv").is_original)
        self.assertEqual(self._post("/taxonomy/terms", {"dimension": "service_type", "key": "SUB_CUSTODY", "labels": {"en": "Again"}}, editor).json()["code"], "duplicate_key")
        self.assertEqual(self._post("/taxonomy/terms", {"dimension": "service_type", "labels": {"en": "Orphan"}, "parent": "nowhere"}, editor).json()["code"], "unknown_key")
        update = self._proposed(self._patch(f"/taxonomy/terms/{term.id}", {"usageNote": "Held by a sub-custodian.", "sortOrder": 40}, editor))
        self.assertEqual(self._approve(update).status_code, 200)
        term.refresh_from_db()
        self.assertEqual((term.usage_note, term.sort_order, term.version), ("Held by a sub-custodian.", 40, 2))
        self.assertEqual(self._patch("/taxonomy/terms/00000000-0000-4000-8000-000000000000", {"sortOrder": 1}, editor).status_code, 404)
        self.assertEqual(self._patch("/taxonomy/terms/not-a-uuid", {"sortOrder": 1}, editor).status_code, 404)

    # --- deciding -------------------------------------------------------------------------------
    def test_an_agent_proposal_is_decided_by_any_reviewer_and_nobody_rejects_their_own(self) -> None:
        key = factories.api_key(self.tenant, scopes=("proposals:write",))
        agent = self._post("/proposals", {"kind": "vocabulary_create", "title": "Add Greenwashing", "payload": {"list": "flag", "key": "greenwashing", "labels": {"en": "Greenwashing"}}, "agentRunId": "00000000-0000-4000-8000-0000000000aa", "model": "mock-1"}, {"HTTP_X_API_KEY": key.plain_key})
        self.assertEqual(agent.status_code, 201, agent.content)
        self.assertEqual((agent.json()["agentRunId"], agent.json()["model"], agent.json()["origin"]), ("00000000-0000-4000-8000-0000000000aa", "mock-1", "agent"))
        self.assertEqual(self._post(f"/proposals/{agent.json()['id']}/approve", {}, sign_in(self.editor, step_up=True)).status_code, 200)
        own = self._proposed(self._post("/vocab/flag", {"labels": {"en": "Sanctions"}}, sign_in(self.editor)))
        refused = self._post(f"/proposals/{own['id']}/reject", {"rejectionCode": "duplicate", "note": "Mine."}, sign_in(self.editor))
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json()["code"], "four_eyes_violation")
        self.assertEqual(self.client.get(f"{V1}/proposals/00000000-0000-4000-8000-000000000000", **sign_in(self.editor)).status_code, 404)
