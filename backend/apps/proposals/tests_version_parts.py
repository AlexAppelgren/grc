"""An obligation version that corrects the title, the citation and the cited provisions
(D-144, Alex 2026-11-13: "Yes, go ahead and fix it, u dont need my approval to get things
right"; INV-02, INV-04, PRO-01, PRO-02).

`new_obligation_version` carries three optional parts beside `terms`: `titles`, `refLabel`
and `provisions`. Each given replaces that part of the obligation, each left out leaves it
alone, and the audit row of the approval holds what was there and what came. Proved here
through the routes: each part replaced and left alone, its source required, a provision of
another instrument or one the library does not hold refused by name, an empty list clearing
the citations, an independent agent confirming one, and the review screen's read showing the
reviewer the old and the new beside each other, before approval and after.

Operations exercised (the audit-on-write guard reads these names): createProposal,
approveProposal.
"""

from __future__ import annotations

from typing import Any

from apps.agents import testing as agents_testing
from apps.library import testing as library_build
from apps.library.models import Obligation, ObligationProvision, ObligationTitle, ObligationVersion
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.proposals.models import Proposal, ProposalStatus
from apps.shared import factories, tenancy
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions

V1 = "/api/v1"
SOURCE = "https://www.retsinformation.dk/eli/lta/2099/1"
OLD_TITLE = "Keep a register of financial contracts where the resolution plan requires it"
NEW_TITLE = "Keep a register of financial contracts"
SUMMARY = "The firm must keep a register of financial contracts."


class AVersionCorrectsTheObligation(ScenarioTestCase):
    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        self.reviewer = factories.platform_user(roles=("library_editor",), email="reviewer@bleqq.test")
        self.order = library_build.instrument(key="dk-bek-2099-1", jurisdiction="dk", regime="regime:banking")
        self.s12 = library_build.provision(self.order, key="dk-bek-2099-1/012", ref_label="§ 12", kind="section", sort_order=12)
        self.s13 = library_build.provision(self.order, key="dk-bek-2099-1/013", ref_label="§ 13", kind="section", sort_order=13)
        other = library_build.instrument(key="dk-lov-2099-2", jurisdiction="dk", regime="regime:banking")
        self.elsewhere = library_build.provision(other, key="dk-lov-2099-2/001", ref_label="§ 1", kind="section")
        self.duty = library_build.obligation(
            self.order, key="obl-dk-test-register", titles={"en": OLD_TITLE, "sv": "Föra ett register"}, ref_label="§ 12", cites=(self.s12,)
        )

    # --- helpers ------------------------------------------------------------------------------
    def file(self, payload: dict[str, Any], sources: dict[str, str] | None = None) -> Any:
        body = {"summaries": {"en": SUMMARY}, "originalLanguage": "en", **payload}
        fields = ["summaries.en", *[f"titles.{language}" for language in body.get("titles", {})]]
        fields += [name for name in ("refLabel", "provisions") if name in body]
        return self.client.post(
            f"{V1}/proposals",
            data={
                "kind": "new_obligation_version",
                "title": "Correct the register duty",
                "targetType": "obligation",
                "targetId": str(self.duty.id),
                "payload": body,
                "fieldSources": {name: SOURCE for name in fields} if sources is None else sources,
            },
            content_type="application/json",
            **sign_in(self.editor),
        )

    def filed(self, payload: dict[str, Any]) -> str:
        created = self.file(payload)
        self.assertEqual(created.status_code, 201, created.content)
        proposal_id: str = created.json()["id"]
        return proposal_id

    def approve(self, proposal_id: str) -> None:
        approved = self.client.post(f"{V1}/proposals/{proposal_id}/approve", data={}, content_type="application/json", **sign_in(self.reviewer, step_up=True))
        self.assertEqual(approved.status_code, 200, approved.content)
        tenancy.clear_tenant()

    def detail(self, proposal_id: str) -> dict[str, Any]:
        read = self.client.get(f"{V1}/proposals/{proposal_id}", **sign_in(self.reviewer))
        self.assertEqual(read.status_code, 200, read.content)
        tenancy.clear_tenant()
        found: dict[str, Any] = read.json()
        return found

    def titles(self) -> dict[str, tuple[str, bool, bool]]:
        return {row.language_id: (row.text, row.is_original, row.is_machine) for row in ObligationTitle.objects.filter(obligation=self.duty)}

    def cited(self) -> list[str]:
        return list(ObligationProvision.objects.filter(obligation=self.duty).values_list("provision__stable_key", flat=True))

    def audit(self, proposal_id: str) -> AuditEvent:
        return AuditEvent.objects.get(action="obligation.version_applied", after__proposal=proposal_id)

    # --- the parts, replaced and left alone -------------------------------------------------
    def test_title_citation_and_provisions_are_replaced_and_the_audit_row_keeps_both(self) -> None:
        proposal_id = self.filed({"titles": {"en": NEW_TITLE}, "refLabel": "§ 12-13", "provisions": ["dk-bek-2099-1/013", "dk-bek-2099-1/012", "dk-bek-2099-1/013"]})

        self.approve(proposal_id)

        self.assertEqual(self.titles(), {"en": (NEW_TITLE, True, False)}, "the title is exactly the given one: the old Swedish no longer translates it")
        self.assertEqual(Obligation.objects.get(pk=self.duty.pk).ref_label, "§ 12-13")
        self.assertEqual(sorted(self.cited()), ["dk-bek-2099-1/012", "dk-bek-2099-1/013"], "a key sent twice is cited once")
        self.assertEqual(ObligationVersion.objects.filter(obligation=self.duty).count(), 2, "the summary is a new version beside the first")
        event = self.audit(proposal_id)
        self.assertEqual(
            {name: event.before[name] for name in ("titles", "refLabel", "provisions")},
            {"titles": {"en": OLD_TITLE, "sv": "Föra ett register"}, "refLabel": "§ 12", "provisions": ["dk-bek-2099-1/012"]},
        )
        self.assertEqual(
            {name: event.after[name] for name in ("titles", "refLabel", "provisions")},
            {"titles": {"en": NEW_TITLE}, "refLabel": "§ 12-13", "provisions": ["dk-bek-2099-1/013", "dk-bek-2099-1/012"]},
        )

    def test_a_title_translation_given_beside_the_original_is_a_machine_translation(self) -> None:
        self.approve(self.filed({"titles": {"en": NEW_TITLE, "da": "Føre et register over finansielle kontrakter"}}))
        self.assertEqual(self.titles(), {"en": (NEW_TITLE, True, False), "da": ("Føre et register over finansielle kontrakter", False, True)})

    def test_a_version_without_the_three_parts_leaves_them_alone(self) -> None:
        proposal_id = self.filed({})
        self.approve(proposal_id)
        self.assertEqual(self.titles(), {"en": (OLD_TITLE, True, False), "sv": ("Föra ett register", False, True)})
        self.assertEqual((Obligation.objects.get(pk=self.duty.pk).ref_label, self.cited()), ("§ 12", ["dk-bek-2099-1/012"]))
        event = self.audit(proposal_id)
        self.assertEqual([event.before[name] for name in ("titles", "refLabel", "provisions")], [None, None, None])
        self.assertEqual([event.after[name] for name in ("titles", "refLabel", "provisions")], [None, None, None])

    def test_an_empty_provisions_list_removes_every_citation(self) -> None:
        self.approve(self.filed({"provisions": []}))
        self.assertEqual(self.cited(), [])
        self.assertTrue(type(self.s12).objects.filter(pk=self.s12.pk).exists(), "the provision stays in the library")

    # --- what the door refuses --------------------------------------------------------------
    def test_a_provision_of_another_instrument_or_one_not_held_is_refused_by_name(self) -> None:
        for key in ("dk-lov-2099-2/001", "dk-bek-2099-1/099"):
            with self.subTest(key=key):
                refused = self.file({"provisions": ["dk-bek-2099-1/013", key]})
                self.assertEqual((refused.status_code, refused.json()["code"]), (422, "unknown_key"), refused.content)
                self.assertIn(key, refused.json()["detail"])
                tenancy.clear_tenant()
        self.assertFalse(Proposal.objects.exists())

    def test_a_provision_moved_away_after_filing_is_refused_at_approval_and_nothing_is_written(self) -> None:
        stored = Proposal.objects.create(
            kind="new_obligation_version",
            title="Filed against a provision of another instrument",
            payload={"summaries": {"en": SUMMARY}, "originalLanguage": "en", "provisions": ["dk-lov-2099-2/001"]},
            field_sources={"summaries.en": SOURCE, "provisions": SOURCE},
            origin="user",
            proposed_by_user=self.editor,
            target_type="obligation",
            target_id=self.duty.id,
        )
        refused = self.client.post(f"{V1}/proposals/{stored.id}/approve", data={}, content_type="application/json", **sign_in(self.reviewer, step_up=True))
        self.assertEqual((refused.status_code, refused.json()["code"]), (422, "unknown_key"), refused.content)
        tenancy.clear_tenant()
        self.assertEqual(Proposal.objects.get(pk=stored.pk).status, ProposalStatus.OPEN.value)
        self.assertEqual((self.cited(), ObligationVersion.objects.filter(obligation=self.duty).count()), (["dk-bek-2099-1/012"], 1))

    def test_each_part_needs_its_source_and_a_title_its_original(self) -> None:
        missing = self.file({"titles": {"en": NEW_TITLE}, "refLabel": "§ 13"}, sources={"summaries.en": SOURCE, "titles.en": SOURCE})
        self.assertEqual((missing.status_code, missing.json()["code"]), (422, "source_missing"), missing.content)
        self.assertIn("refLabel", missing.json()["detail"])
        tenancy.clear_tenant()
        no_original = self.file({"titles": {"da": "Føre et register"}})
        self.assertEqual((no_original.status_code, no_original.json()["code"]), (422, "validation_error"), no_original.content)
        tenancy.clear_tenant()
        blank = self.file({"refLabel": "  "})
        self.assertEqual((blank.status_code, blank.json()["code"]), (422, "validation_error"), blank.content)

    # --- who may confirm, and what the reviewer reads ---------------------------------------
    def test_an_independent_agent_may_confirm_a_correction(self) -> None:
        proposal_id = self.filed({"titles": {"en": NEW_TITLE, "sv": "Föra ett register över finansiella avtal"}, "provisions": ["dk-bek-2099-1/012", "dk-bek-2099-1/013"]})
        confirmer = agents_testing.reviewer_api_key()
        tenancy.clear_tenant()
        approved = self.client.post(
            f"{V1}/proposals/{proposal_id}/approve", data=agents_testing.decision(confirmer), content_type="application/json", HTTP_X_API_KEY=confirmer.plain_key
        )
        self.assertEqual((approved.status_code, approved.json()["status"]), (200, "approved"), approved.content)
        tenancy.clear_tenant()
        self.assertEqual(self.titles(), {"en": (NEW_TITLE, True, False), "sv": ("Föra ett register över finansiella avtal", False, True)})
        self.assertEqual(sorted(self.cited()), ["dk-bek-2099-1/012", "dk-bek-2099-1/013"])
        version = ObligationVersion.objects.get(obligation=self.duty, version_number=2)
        self.assertEqual(version.verified_origin, "agent", "machine-confirmed, never read as a person's")

    def test_the_reviewer_reads_the_old_and_the_new_before_approval_and_after(self) -> None:
        proposal_id = self.filed({"titles": {"en": NEW_TITLE}, "refLabel": "§ 13", "provisions": ["dk-bek-2099-1/013"]})
        expected = {
            "titleBefore": OLD_TITLE,
            "titleAfter": NEW_TITLE,
            "refLabelBefore": "§ 12",
            "refLabelAfter": "§ 13",
            "provisionsAdded": [{"key": "dk-bek-2099-1/013", "referenceLabel": "§ 13"}],
            "provisionsRemoved": [{"key": "dk-bek-2099-1/012", "referenceLabel": "§ 12"}],
        }
        before = self.detail(proposal_id)
        self.assertEqual({name: before[name] for name in expected}, expected)
        self.approve(proposal_id)
        after = self.detail(proposal_id)
        self.assertEqual({name: after[name] for name in expected}, expected, "an approved proposal is read against what its approval found")

        untouched = self.detail(self.filed({}))
        self.assertEqual(
            {name: untouched[name] for name in expected},
            {"titleBefore": NEW_TITLE, "titleAfter": None, "refLabelBefore": "§ 13", "refLabelAfter": None, "provisionsAdded": [], "provisionsRemoved": []},
        )
