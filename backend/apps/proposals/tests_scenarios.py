"""Scenario tests for the proposals app (playbook 4.1, Appendix B): one method per
`@integration` scenario in app.md, each carrying its ID. Chunk 2 un-skips the scenarios a
vocabulary proposal can prove: PRO-S2 (the library vocabulary half), PRO-S5, PRO-S6 and
PRO-S9. Chunk 4 adds PRO-S1, the obligation proposal kind with its source per changed
field; S3, S4 and S7 follow with approval, corrections and the tenant's view; PRO-S8 is
R2. Never delete a scenario without updating app.md.

Operations exercised (the audit-on-write guard reads these names): createProposal,
approveProposal, rejectProposal.

Prefixes hosted: PRO.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any
from unittest import mock, skip

from apps.library.models import (
    Instrument,
    ProblemReport,
    Jurisdiction,
    Obligation,
    ObligationSummary,
    ObligationTerm,
    ObligationVersion,
)
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.proposals import apply
from apps.proposals.models import Proposal, ProposalStatus, ProposalTenant
from apps.shared import factories, tenancy, permissions as perms
from apps.shared.audit import Actor
from apps.shared.models import AuditEvent, OutboxEvent
from apps.shared.routes import iter_operations
from apps.shared.tenancy import library_write
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import DutyType, Flag, InstrumentLevel, TaxonomyTerm
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies
from config.api import api

V1 = "/api/v1"
# Queries per queue read, measured 2026-09-21 and pinned so an N+1 shows up as a number
# (playbook 10): the scenario client's audit count (1), the request's savepoint pair (2), the
# auth layer for a platform session with no tenant (identity flag on, the session row, flag
# off, platform roles, latest step-up: 5), the reader's own locale for the language the rows
# are titled in (1) and the page with its proposer and reviewer (1). The library records the
# rows name cost two more, for the whole page at once rather than per row, and this queue
# holds a vocabulary proposal, which names none (apps/proposals/tests_reading.py pins that
# the cost does not grow with the row count).
PROPOSAL_QUEUE_QUERIES = 1 + 2 + 5 + 1 + 1
# The change an agent's watch run linked the proposal to (chunk 5 makes these rows; the
# column is a plain id until then), and the summary version 1 carries, so a scenario can
# prove that applying version 2 leaves version 1 exactly as it was written.
CHANGE_ID = uuid.UUID("b7e1c0a4-9f3d-4f6a-9c21-5d8e2f0a1b33")
VERSION_ONE_SV = "Institutet bedömer kunden innan rådgivning enligt tidigare lydelse."


class ProposalsScenarioTests(ScenarioTestCase):
    """Scenario tests for apps.proposals, one method per @integration scenario."""

    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        self.tenant = factories.tenant(slug="bank")
        self.activate(self.tenant)
        ensure_tenant_vocabularies(self.tenant, actor=Actor.system("test"))
        self.officer = factories.member(self.tenant, roles=("compliance_officer",), user_row=factories.user(name="Sara Lindqvist")).user
        self.admin = factories.member(self.tenant, roles=("admin",)).user
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        self.second_editor = factories.platform_user(roles=("library_editor",), email="editor2@bleqq.test")

    def _post(self, path: str, body: dict[str, Any] | None, headers: dict[str, Any], **extra: Any) -> Any:  # compliance: allow-kwargs test helper forwarding request headers
        return self.client.post(f"{V1}{path}", data=body or {}, content_type="application/json", **headers, **extra)

    def _obligation(self) -> Obligation:
        """An obligation to propose a new version of. Chunk 3 seeds the real library; a
        scenario needs one record, written as the seeds write theirs."""
        with library_write("scenario"):
            instrument = Instrument.objects.create(
                stable_key="fffs-2017-2",
                short_name="FFFS 2017:2",
                official_ref="FFFS 2017:2",
                source_url="https://www.fi.se/",
                level=InstrumentLevel.objects.get(key="act"),
                binding=True,
                jurisdiction=Jurisdiction.objects.get(key="se"),
                created_origin="user",
            )
            return Obligation.objects.create(
                stable_key="obl-advice-suitability",
                instrument=instrument,
                ref_label="9 kap. 6 §",
                duty_type=DutyType.objects.get(key="conduct"),
                created_origin="user",
                source_url="https://www.fi.se/",
                source_label="FFFS 2017:2, 9 kap. 6 §",
            )

    def _flag_proposal(self) -> dict[str, Any]:
        body = {
            "kind": "vocabulary_create",
            "title": "Add the flag Client money",
            "payload": {"list": "flag", "key": "client_money", "labels": {"en": "Client money", "sv": "Kundmedel"}, "usageNote": "Safeguarding of client funds."},
            "sourceLabel": "FFFS 2017:2",
            "sourceUrl": "https://www.fi.se/",
        }
        return body

    def _version_one(self, obligation: Obligation) -> ObligationVersion:
        """The version in force before the proposal: chunk 3 seeds these, a scenario needs one."""
        with library_write("scenario"):
            version = ObligationVersion.objects.create(obligation=obligation, version_number=1, effective_from=date(2024, 1, 1))
            ObligationSummary.objects.create(version=version, language_id="sv", text=VERSION_ONE_SV, is_original=True)
            ObligationTerm.objects.create(obligation=obligation, term=self._term("legal_entity", "bank"))
        return version

    def _term(self, dimension: str, key: str) -> Any:
        return TaxonomyTerm.objects.get(dimension__key=dimension, key=key)

    def _version_proposal(self, obligation: Obligation, *, scoped: bool = True) -> dict[str, Any]:
        """An agent's proposal of a new version, sourced field by field, waiting in the
        queue. `scoped=False` leaves the scope alone, and then names no source for it."""
        payload: dict[str, Any] = {
            "summaries": {"sv": "Institutet bedömer kunden innan rådgivning.", "en": "The institution assesses the client before advising."},
            "originalLanguage": "sv",
            "isMachine": True,
            "effectiveFrom": "2026-10-01",
            "effectiveFromPrecision": "day",
        }
        sources = {
            "summaries.sv": "https://www.fi.se/",
            "summaries.en": "https://www.fi.se/",
            "effectiveFrom": "https://www.fi.se/",
        }
        if scoped:
            payload["terms"] = ["legal_entity:bank", "client_category:retail"]
            sources["terms"] = "https://www.fi.se/"
        key = factories.api_key(self.tenant, scopes=("proposals:write",))
        created = self._post(
            "/proposals",
            {
                "kind": "new_obligation_version",
                "title": "Version 2 of the advice obligation, in force 1 October 2026",
                "targetType": "obligation",
                "targetId": str(obligation.id),
                "changeId": str(CHANGE_ID),
                "payload": payload,
                "fieldSources": sources,
                "sourceLabel": "Finansinspektionen, board decision 15 September 2026",
                "sourceUrl": "https://www.fi.se/",
            },
            {"HTTP_X_API_KEY": key.plain_key},
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.activate(self.tenant)
        row: dict[str, Any] = created.json()
        return row

    def test_pro_s1(self) -> None:
        """PRO-S1

        A proposal carries a source per changed field (PRO-01).
        """
        obligation = self._obligation()
        key = factories.api_key(self.tenant, scopes=("proposals:write",))
        agent = {"HTTP_X_API_KEY": key.plain_key}
        body: dict[str, Any] = {
            "kind": "new_obligation_version",
            "title": "Version 2 of the advice obligation, in force 1 October 2026",
            "targetType": "obligation",
            "targetId": str(obligation.id),
            "payload": {
                "summaries": {"sv": "Institutet bedömer kunden innan rådgivning.", "en": "The institution assesses the client before advising."},
                "originalLanguage": "sv",
                "isMachine": True,
                "effectiveFrom": "2026-10-01",
                "effectiveFromPrecision": "day",
                "terms": ["legal_entity:bank", "client_category:retail"],
            },
            "fieldSources": {
                "summaries.sv": "https://www.fi.se/",
                "summaries.en": "https://www.fi.se/",
                "effectiveFrom": "https://www.fi.se/",
                "terms": "https://www.fi.se/",
            },
            "sourceLabel": "Finansinspektionen, board decision 15 September 2026",
            "sourceUrl": "https://www.fi.se/",
        }
        # A proposal missing the source of any changed field is refused, and nothing is stored.
        for missing in ("summaries.sv", "terms"):
            without = self._post("/proposals", {**body, "fieldSources": {f: u for f, u in body["fieldSources"].items() if f != missing}}, agent)
            self.assertEqual(without.status_code, 422, without.content)
            self.assertEqual(without.json()["code"], "source_missing")
            self.assertIn(missing, without.json()["detail"])
        self.assertFalse(Proposal.objects.filter(kind="new_obligation_version").exists())
        # A source nobody could follow, and a source beside a field this proposal never
        # changes, are refused as firmly as a missing one.
        for case, sources in (
            ("not a source", {**body["fieldSources"], "terms": "n/a"}),
            ("no such field", {**body["fieldSources"], "dutyType": "https://www.fi.se/"}),
        ):
            with self.subTest(case=case):
                refused = self._post("/proposals", {**body, "fieldSources": sources}, agent)
                self.assertEqual(refused.status_code, 422, refused.content)
                self.assertEqual(refused.json()["code"], "validation_error")
        self.assertFalse(Proposal.objects.filter(kind="new_obligation_version").exists())
        # With every changed field sourced, the proposal is made and each source is kept.
        created = self._post("/proposals", body, agent)
        self.assertEqual(created.status_code, 201, created.content)
        proposal = created.json()
        self.assertEqual(proposal["fieldSources"], body["fieldSources"])
        self.assertEqual(proposal["payload"]["terms"], ["legal_entity:bank", "client_category:retail"])
        self.assertEqual(proposal["payload"]["originalLanguage"], "sv")
        # A proposal against an obligation nobody can find never enters the queue.
        unknown = self._post("/proposals", {**body, "targetId": str(uuid.uuid4())}, agent)
        self.assertEqual(unknown.status_code, 422, unknown.content)
        self.assertEqual(unknown.json()["code"], "unknown_key")
        # It waits for approval in the console's queue, and the editor sees its sources.
        editor = sign_in(self.editor)
        waiting = self.client.get(f"{V1}/proposals?status=open&kind=new_obligation_version", **editor)
        self.assertEqual(waiting.status_code, 200, waiting.content)
        self.assertEqual([row["id"] for row in waiting.json()["items"]], [proposal["id"]])
        self.assertEqual(waiting.json()["items"][0]["status"], "open")
        # The agent proposed inside its tenant: the link row is the tenant's, the proposal
        # row carries no tenant id, and the audit row is the tenant's (AUD-01).
        self.assertTrue(Proposal.objects.get(pk=proposal["id"]).proposed_in_tenant)
        # The link row is the bank's, so it is read from the bank's zone: the editor's session
        # above is the platform's, and a tenant table shows a platform session nothing (H-C).
        tenancy.activate(self.tenant.id)
        self.assertEqual([link.tenant_id for link in ProposalTenant.objects.all()], [self.tenant.id])
        self.assertEqual(AuditEvent.objects.get(action="proposal.created", subject_id=proposal["id"]).tenant_id, self.tenant.id)

    def test_pro_s2(self) -> None:
        """PRO-S2

        No scope and no tenant role can change a library record directly (PRO-01, AC-PRO1).
        """
        # The library vocabulary half (chunk 2): an API key with every scope and a tenant admin
        # holding every tenant permission. Instruments, provisions and obligations follow in
        # chunk 3 and reuse the same fence.
        key = factories.api_key(self.tenant, scopes=tuple(sorted(perms.ALL_SCOPES)))
        agent = {"HTTP_X_API_KEY": key.plain_key}
        self.assertEqual(self._post("/vocab/flag", {"labels": {"en": "Client money"}}, agent).status_code, 401)
        self.assertEqual(self.client.patch(f"{V1}/vocab/flag/ai", data={"labels": {"en": "x"}}, content_type="application/json", **agent).status_code, 401)
        self.assertEqual(self._post("/taxonomy/terms", {"dimension": "regime", "labels": {"en": "Crypto"}}, agent).status_code, 401)
        # A person with every tenant permission gets a proposal, never a row.
        everything = sign_in(self.admin, tenant=self.tenant, step_up=True)
        # Between them the tenant's system roles hold every tenant permission; none of them is
        # a library write. (cases.signoff is the approver's alone, PRD section 6.)
        tenant_roles = ("admin", "compliance_officer", "owner", "approver", "contributor", "reader", "auditor")
        held = frozenset().union(*(perms.SYSTEM_ROLES[role] for role in tenant_roles))
        self.assertEqual(held, perms.TENANT_PERMISSIONS)
        officer = sign_in(self.officer, tenant=self.tenant, step_up=True)
        proposed = self._post("/vocab/flag", {"labels": {"en": "Client money"}}, officer)
        self.assertEqual(proposed.status_code, 202, proposed.content)
        self.assertFalse(Flag.objects.filter(key="client_money").exists())
        # The admin without proposals.create cannot even propose; the review route is 403 for both.
        self.assertEqual(self._post("/vocab/flag", {"labels": {"en": "Client money"}}, everything).status_code, 403)
        proposal_id = proposed.json()["proposal"]["id"]
        self.assertEqual(self._post(f"/proposals/{proposal_id}/approve", {}, officer).status_code, 403)
        self.assertEqual(self._post(f"/proposals/{proposal_id}/approve", {}, everything).status_code, 403)
        self.assertEqual(self.client.get(f"{V1}/proposals", **officer).status_code, 403)
        # No route writes a library vocabulary or term directly.
        paths = {(op.method, op.path) for op in iter_operations(api)}
        for forbidden in (("PUT", "/vocab/{list}/{key}"), ("DELETE", "/vocab/{list}/{key}"), ("DELETE", "/taxonomy/terms/{term_id}"), ("PUT", "/taxonomy/terms/{term_id}")):
            self.assertNotIn(forbidden, paths)
        # The only path that leaves a library change is an approved proposal.
        approved = self._post(f"/proposals/{proposal_id}/approve", {}, sign_in(self.second_editor, step_up=True))
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertTrue(Flag.objects.filter(key="client_money").exists())

    def test_pro_s3(self) -> None:
        """PRO-S3

        Approval applies payload, version, audit row and re-index in one transaction (PRO-02).
        """
        obligation = self._obligation()
        first = self._version_one(obligation)
        proposal = self._version_proposal(obligation)

        # The re-index cannot be written: the whole request rolls back, so nothing is
        # applied, nothing is audited and the proposal is still waiting for a reviewer.
        with mock.patch.object(apply, "reindex", side_effect=RuntimeError("index unavailable")):
            failed = self._post(f"/proposals/{proposal['id']}/approve", {}, sign_in(self.second_editor, step_up=True))
        self.assertEqual(failed.status_code, 500, failed.content)
        self.assertEqual([version.version_number for version in obligation.versions.all()], [1])
        self.assertEqual(Proposal.objects.get(pk=proposal["id"]).status, ProposalStatus.OPEN.value)
        self.assertFalse(AuditEvent.objects.filter(action="obligation.version_applied").exists())
        self.assertFalse(AuditEvent.objects.filter(action="proposal.approved").exists())

        approved = self._post(f"/proposals/{proposal['id']}/approve", {"note": "Matches the decision."}, sign_in(self.second_editor, step_up=True))

        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.json()["status"], "approved")
        # A new version, with the stated effective date. Version 1 is untouched: the
        # history is read as it was written (INV-04).
        version = obligation.versions.order_by("-version_number").first()
        assert version is not None
        self.assertEqual(version.version_number, 2)
        self.assertEqual(version.effective_from, date(2026, 10, 1))
        self.assertEqual(version.effective_from_precision, "day")
        self.assertEqual(str(version.applied_by_proposal_id), proposal["id"])
        self.assertEqual(version.approved_by_id, self.second_editor.id)
        self.assertIsNotNone(version.approved_at)
        self.assertEqual(version.caused_by_change, CHANGE_ID)
        self.assertEqual(
            {row.language_id: (row.text, row.is_original, row.is_machine) for row in version.summaries.all()},
            {
                "sv": ("Institutet bedömer kunden innan rådgivning.", True, False),
                "en": ("The institution assesses the client before advising.", False, True),
            },
        )
        self.assertEqual(first.summaries.get(language_id="sv").text, VERSION_ONE_SV)
        # The scope the payload carried replaced the obligation's own.
        self.assertEqual(
            sorted(f"{link.term.dimension.key}:{link.term.key}" for link in ObligationTerm.objects.filter(obligation=obligation)),
            ["client_category:retail", "legal_entity:bank"],
        )
        # The audit row, its outbox row and the decision are one transaction, and the
        # library change carries the reviewer's assertion.
        applied = AuditEvent.objects.get(action="obligation.version_applied", subject_id=obligation.id)
        self.assertIsNone(applied.tenant_id)
        self.assertIsNotNone(applied.step_up_assertion_id)
        self.assertEqual(applied.after["versionNumber"], 2)
        self.assertEqual(applied.before["versionNumber"], 1)
        self.assertTrue(OutboxEvent.objects.filter(topic="obligation.version_applied").exists())
        self.assertTrue(OutboxEvent.objects.filter(topic="proposal.approved").exists())

    def test_pro_s4(self) -> None:
        """PRO-S4

        The reviewer corrects scope and wording before approving (PRO-02).
        """
        obligation = self._obligation()
        self._version_one(obligation)
        proposal = self._version_proposal(obligation)
        reviewer = sign_in(self.second_editor, step_up=True)
        corrected_sv = "Institutet bedömer kundens kunskap och erfarenhet innan rådgivning."

        # A correction that introduces a field nobody sourced is refused, and applies
        # nothing: this proposal left the scope alone, so it named no source for it.
        unscoped = self._version_proposal(obligation, scoped=False)
        no_source = self._post(
            f"/proposals/{unscoped['id']}/approve",
            {"payloadOverrides": {"terms": ["legal_entity:bank", "client_category:professional"]}},
            reviewer,
        )
        self.assertEqual(no_source.status_code, 422, no_source.content)
        self.assertEqual(no_source.json()["code"], "source_missing")
        self.assertIn("terms", no_source.json()["detail"])
        self.assertEqual([version.version_number for version in obligation.versions.all()], [1])
        self.assertIsNone(Proposal.objects.get(pk=unscoped["id"]).corrected_payload)
        self.assertEqual(Proposal.objects.get(pk=unscoped["id"]).status, ProposalStatus.OPEN.value)

        # The editor disagrees with the scope and the wording, and approves their own version.
        approved = self._post(
            f"/proposals/{proposal['id']}/approve",
            {
                "note": "Retail only, and the wording follows the decision.",
                "payloadOverrides": {"summaries": {"sv": corrected_sv, "en": "The institution assesses the client's knowledge and experience before advising."}, "terms": ["client_category:retail"]},
            },
            reviewer,
        )

        self.assertEqual(approved.status_code, 200, approved.content)
        # The applied version carries the corrected values.
        version = obligation.versions.order_by("-version_number").first()
        assert version is not None
        self.assertEqual(version.version_number, 2)
        self.assertEqual(version.summaries.get(language_id="sv").text, corrected_sv)
        self.assertEqual(
            [f"{link.term.dimension.key}:{link.term.key}" for link in ObligationTerm.objects.filter(obligation=obligation)],
            ["client_category:retail"],
        )
        # Both payloads are kept, and the correction is the reviewer's own.
        row = Proposal.objects.get(pk=proposal["id"])
        applied = dict(row.corrected_payload or {})
        self.assertEqual(row.payload["summaries"]["sv"], "Institutet bedömer kunden innan rådgivning.")
        self.assertEqual(row.payload["terms"], ["legal_entity:bank", "client_category:retail"])
        self.assertEqual(applied["summaries"]["sv"], corrected_sv)
        self.assertEqual(applied["terms"], ["client_category:retail"])
        # The date nobody corrected came through untouched.
        self.assertEqual(applied["effectiveFrom"], "2026-10-01")
        self.assertEqual(row.corrected_by_id, self.second_editor.id)
        self.assertIsNotNone(row.corrected_at)
        self.assertEqual(AuditEvent.objects.get(action="proposal.approved", subject_id=row.id).after["corrected"], True)

    def test_pro_s5(self) -> None:
        """PRO-S5

        Approving your own proposal answers four_eyes_violation (PRO-02, AC-PRO2).
        """
        editor = sign_in(self.editor, step_up=True)
        created = self._post("/proposals", self._flag_proposal(), editor)
        self.assertEqual(created.status_code, 201, created.content)
        proposal = created.json()
        self.assertEqual(proposal["proposedBy"]["id"], str(self.editor.id))
        self.assertEqual(proposal["origin"], "user")
        own = self._post(f"/proposals/{proposal['id']}/approve", {}, editor)
        self.assertEqual(own.status_code, 409, own.content)
        self.assertEqual(own.json()["code"], "four_eyes_violation")
        self.assertEqual(Proposal.objects.get(pk=proposal["id"]).status, ProposalStatus.OPEN.value)
        self.assertFalse(Flag.objects.filter(key="client_money").exists())
        # The check constraint on the proposal table refuses the row on its own.
        from django.db import connection, transaction

        with self.assertRaises(Exception) as caught:  # compliance: allow-broad-except the driver raises IntegrityError for a CHECK violation
            # A savepoint, so the refused statement does not abort the rest of the scenario.
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("UPDATE proposal SET reviewed_by_id = proposed_by_user_id WHERE id = %s", [proposal["id"]])
        self.assertIn("four_eyes", str(caught.exception))
        # A second editor approves with step-up; the audit event carries the assertion and
        # the applied change is in the same transaction.
        approved = self._post(f"/proposals/{proposal['id']}/approve", {"note": "Agreed."}, sign_in(self.second_editor, step_up=True))
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.json()["status"], "approved")
        self.assertEqual(approved.json()["reviewedBy"]["id"], str(self.second_editor.id))
        self.assertIsNotNone(approved.json()["appliedAt"])
        self.assertEqual(Flag.objects.get(key="client_money").labels.get(language="sv").text, "Kundmedel")
        event = AuditEvent.objects.get(action="proposal.approved", subject_id=proposal["id"])
        self.assertIsNotNone(event.step_up_assertion_id)
        self.assertIsNone(event.tenant_id)
        self.assertTrue(AuditEvent.objects.filter(action="vocabulary.created", subject_id=Flag.objects.get(key="client_money").id).exists())
        # Approving twice is an invalid transition.
        twice = self._post(f"/proposals/{proposal['id']}/approve", {}, sign_in(self.second_editor, step_up=True))
        self.assertEqual(twice.status_code, 409)
        self.assertEqual(twice.json()["code"], "invalid_transition")

    def test_pro_s6(self) -> None:
        """PRO-S6

        A retried submission with the same Idempotency-Key creates one proposal (PRO-01).
        """
        key = factories.api_key(self.tenant, scopes=("proposals:write",))
        agent = {"HTTP_X_API_KEY": key.plain_key, "HTTP_IDEMPOTENCY_KEY": "run-42-flag-7"}
        body = self._flag_proposal()
        first = self._post("/proposals", body, agent)
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(first.json()["origin"], "agent")
        self.assertIsNone(first.json()["proposedBy"])
        second = self._post("/proposals", body, agent)
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(second.json()["id"], first.json()["id"])
        self.assertEqual(Proposal.objects.filter(idempotency_key="run-42-flag-7").count(), 1)
        conflict = self._post("/proposals", {**body, "title": "Something else"}, agent)
        self.assertEqual(conflict.status_code, 409, conflict.content)
        self.assertEqual(conflict.json()["code"], "idempotency_conflict")
        # Without the scope the key is refused; an unknown kind is refused with the valid keys.
        no_scope = factories.api_key(self.tenant, scopes=("changes:write",))
        self.assertEqual(self._post("/proposals", body, {"HTTP_X_API_KEY": no_scope.plain_key}).status_code, 403)
        unknown = self._post("/proposals", {**body, "kind": "new_planet"}, agent)
        self.assertEqual(unknown.status_code, 422)
        self.assertEqual(unknown.json()["code"], "unknown_key")
        self.assertIn("vocabulary_create", unknown.json()["detail"])
        bad_payload = self._post("/proposals", {**body, "payload": {"list": "flag"}}, {"HTTP_X_API_KEY": key.plain_key})
        self.assertEqual(bad_payload.status_code, 422)
        self.assertEqual(bad_payload.json()["code"], "validation_error")
        # The queue lists it for the editor, filtered by status and kind.
        editor = sign_in(self.editor)
        listed = self.client.get(f"{V1}/proposals?status=open&kind=vocabulary_create", **editor)
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual(listed.json()["total"], 1)
        detail = self.client.get(f"{V1}/proposals/{first.json()['id']}", **editor)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["payload"]["key"], "client_money")
        # The vocabulary screen's "Suggested" tab: open proposals that would add to one list.
        suggested = self.client.get(f"{V1}/proposals?status=open&kind=vocabulary_create,term_create&targetList=flag", **editor)
        self.assertEqual(suggested.status_code, 200, suggested.content)
        self.assertEqual([p["payload"]["key"] for p in suggested.json()["items"]], ["client_money"])
        self.assertEqual(self.client.get(f"{V1}/proposals?targetList=urgency", **editor).json()["total"], 0)
        self.assertEqual(self.client.get(f"{V1}/proposals?status=approved,rejected", **editor).json()["total"], 0)
        with self.assertNumQueries(PROPOSAL_QUEUE_QUERIES):
            self.client.get(f"{V1}/proposals", **editor)

    def test_pro_s7(self) -> None:
        """PRO-S7

        The queue is in the console and tenants see updates and report problems (PRO-03).
        """
        obligation = self._obligation()
        self._version_one(obligation)
        proposal = self._version_proposal(obligation)
        officer = sign_in(self.officer, tenant=self.tenant)

        # The queue is the console's: a bank's compliance officer has no route into it.
        self.assertEqual(self.client.get(f"{V1}/proposals", **officer).status_code, 403)
        self.assertEqual(self.client.get(f"{V1}/proposals/{proposal['id']}", **officer).status_code, 403)

        # The editor opens it and sees the source beside the diff.
        editor = sign_in(self.editor)
        waiting = self.client.get(f"{V1}/proposals?status=open", **editor)
        self.assertEqual(waiting.status_code, 200, waiting.content)
        self.assertIn(proposal["id"], [row["id"] for row in waiting.json()["items"]])
        detail = self.client.get(f"{V1}/proposals/{proposal['id']}", **editor).json()
        self.assertEqual(detail["target"]["referenceLabel"], "9 kap. 6 §")
        self.assertEqual([source["field"] for source in detail["sources"]], ["effectiveFrom", "summaries.en", "summaries.sv", "terms"])
        self.assertEqual([segment["op"] for segment in detail["diff"]], ["delete", "insert"])

        approved = self._post(f"/proposals/{proposal['id']}/approve", {}, sign_in(self.second_editor, step_up=True))
        self.assertEqual(approved.status_code, 200, approved.content)

        # The bank reads it as a library update, under the record's own title.
        updates = self.client.get(f"{V1}/library-updates", **officer)
        self.assertEqual(updates.status_code, 200, updates.content)
        listed = [item for day in updates.json()["days"] for item in day["items"]]
        self.assertEqual([item["id"] for item in listed], [proposal["id"]])
        self.assertEqual(listed[0]["target"]["id"], str(obligation.id))
        self.assertEqual(listed[0]["versionNumber"], 2)
        self.assertNotIn(proposal["title"], repr(listed[0]), "an update is titled by the library record, never by the request")

        # "This looks wrong" files a report, and it stays inside the bank: no console
        # surface reads one, and nothing in the platform's own zone carries it.
        reported = self._post(
            f"/obligations/{obligation.id}/problem-reports",
            {"description": "The new wording drops the annual review the decision keeps."},
            officer,
        )
        self.assertEqual(reported.status_code, 201, reported.content)
        self.activate(self.tenant)
        report = ProblemReport.objects.get(subject_id=obligation.id)
        self.assertEqual(report.tenant_id, self.tenant.id)
        self.assertEqual(report.reporter_id, self.officer.id)
        reads = {(op.method, op.path) for op in iter_operations(api) if "problem-report" in op.path}
        self.assertEqual({method for method, _ in reads}, {"POST"}, "filing one is the only problem-report operation the console could reach")

    @skip("pending: PRO-S8 (PRO-04, R2)")
    def test_pro_s8(self) -> None:
        """PRO-S8

        A batch proposal previews and is approved whole or row by row (PRO-04).
        """

    def test_pro_s9(self) -> None:
        """PRO-S9

        A rejection needs a reason and is audited (PRO-01).
        """
        officer = sign_in(self.officer, tenant=self.tenant)
        proposal = self._post("/vocab/flag", {"labels": {"en": "Client money"}}, officer).json()["proposal"]
        editor = sign_in(self.editor)
        without = self._post(f"/proposals/{proposal['id']}/reject", {"rejectionCode": "duplicate", "note": "  "}, editor)
        self.assertEqual(without.status_code, 422, without.content)
        self.assertEqual(without.json()["code"], "reason_required")
        no_code = self._post(f"/proposals/{proposal['id']}/reject", {"rejectionCode": "", "note": "We have this already."}, editor)
        self.assertEqual(no_code.status_code, 422)
        # The reason is a key of the `rejection_reason` library list, not a word of the
        # reviewer's own: a code that list does not hold is refused the same way.
        invented = self._post(f"/proposals/{proposal['id']}/reject", {"rejectionCode": "just_because", "note": "We have this already."}, editor)
        self.assertEqual(invented.status_code, 422, invented.content)
        self.assertEqual(invented.json()["code"], "reason_required")
        rejected = self._post(f"/proposals/{proposal['id']}/reject", {"rejectionCode": "duplicate", "note": "We have this already."}, editor)
        self.assertEqual(rejected.status_code, 200, rejected.content)
        self.assertEqual(rejected.json()["status"], "rejected")
        self.assertEqual(rejected.json()["rejectionCode"], "duplicate")
        self.assertEqual(rejected.json()["reviewNote"], "We have this already.")
        self.assertFalse(Flag.objects.filter(key="client_money").exists())
        event = AuditEvent.objects.get(action="proposal.rejected", subject_id=proposal["id"])
        self.assertEqual(event.after["rejectionCode"], "duplicate")
        self.assertEqual(event.actor_id, self.editor.id)
        # The proposer is told: an outbox event carries the topic the notifier delivers.
        self.assertTrue(event.outbox_events.filter(topic="proposal.rejected").exists())
        # A rejected proposal cannot be approved afterwards.
        again = self._post(f"/proposals/{proposal['id']}/approve", {}, sign_in(self.second_editor, step_up=True))
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["code"], "invalid_transition")

    @skip("pending: PRO-S10 (INV-08, chunks 4 and 5)")
    def test_pro_s10(self) -> None:
        """PRO-S10

        Licensed text and extra obligations never enter a standard (INV-08, PRO-01, PRO-02).
        """

    @skip("pending: PRO-S11 (INV-08, chunk 4)")
    def test_pro_s11(self) -> None:
        """PRO-S11

        A standard term never sits on a law's obligation (FP-01, INV-08).
        """

    @skip("pending: PRO-S12 (INV-07, PRO-03, chunk 13)")
    def test_pro_s12(self) -> None:
        """PRO-S12

        A private proposal is approved inside the bank and never reaches the console (INV-07, PRO-03).
        """

    @skip("pending: PRO-S13 (D-62, chunk 4 c4-agent-approver)")
    def test_pro_s13(self) -> None:
        """PRO-S13

        An independent agent confirms a proposal from the same queue (PRO-01, PRO-02, AUD-02).
        """

    @skip("pending: PRO-S14 (D-62, chunk 4 c4-agent-approver)")
    def test_pro_s14(self) -> None:
        """PRO-S14

        The same principal can never both propose and approve (PRO-02, AC-PRO2).
        """
