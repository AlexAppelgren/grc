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

import json
import re
import uuid
from datetime import date
from typing import Any
from unittest import mock, skip

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.agents import testing as agents_testing
from apps.governance.models import AiGeneration
from apps.identity import tokens
from apps.library import testing as library_build
from apps.identity.models import ApiKey
from apps.library.models import (
    Instrument,
    ProblemReport,
    Jurisdiction,
    Obligation,
    ObligationSummary,
    ObligationTerm,
    ObligationVersion,
    Provision,
)
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.library.seeds.library import seed_authorities
from apps.proposals import apply, logic, standards
from apps.proposals.models import Proposal, ProposalStatus, ProposalTenant
from apps.shared import factories, tenancy, permissions as perms
from apps.shared.audit import Actor
from apps.shared.models import AuditEvent, OutboxEvent
from apps.shared.routes import iter_operations
from apps.shared.tenancy import library_write
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.proposals.tests_kinds import (
    INSTRUMENT_KEY,
    OBLIGATION_KEY,
    PARENT_KEY,
    PROVISION_KEY,
    SOURCE,
    STANDARD_KEY,
    STANDARD_TERM,
    instrument_body,
    obligation_body,
    provision_body,
)
from apps.search.models import SearchChunk
from apps.taxonomy.models import DutyType, Flag, InstrumentLevel, TaxonomyTerm
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies
from config.api import api

V1 = "/api/v1"
# Queries per queue read, re-measured 2026-09-22 after chunk4-T25 (D-62, ADR 0054): the
# scenario client's audit count (1), the request's savepoint pair (2), the auth layer for a
# platform session with no tenant (identity flag on, the session row, flag off, platform
# roles, latest step-up: 5), `require_reviewer`'s own fetch of the caller's `User` row for
# the audit actor's label (1, new: the dual-principal gate needs the real row, not just the
# session's already-joined columns), the reader's own locale for the language the rows are
# titled in (1), how many proposals match (1, since listProposals pages like every list)
# and the page with the people and agents who filed, corrected and decided it (1). The
# library records the rows name cost two more, for the whole page at once rather than per
# row, and this queue holds a vocabulary proposal, which names none
# (apps/proposals/tests_reading.py pins that the cost does not grow with the row count).
PROPOSAL_QUEUE_QUERIES = 1 + 2 + 5 + 1 + 1 + 1 + 1
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
                regime=TaxonomyTerm.objects.get(dimension__key="regime", key="securities"),
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

    def _version_proposal(self, obligation: Obligation, *, scoped: bool = True, key: Any = None) -> dict[str, Any]:
        """An agent's proposal of a new version, sourced field by field, waiting in the
        queue. `scoped=False` leaves the scope alone, and then names no source for it.
        `key` lets a caller file it through a specific platform key, for example one bound
        to an agent definition (PRO-S13, PRO-S14); left out, a fresh tenant key is used, as
        before."""
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
        key = key or factories.api_key(self.tenant, scopes=("proposals:write",))
        # A key bound to an agent files under an open run of its own (AGT-01); a bank's own
        # key is bound to none and names no run.
        run = {"agentRunId": str(agents_testing.platform_run(key=key).id)} if getattr(key, "agent", None) else {}
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
                **run,
            },
            {"HTTP_X_API_KEY": key.plain_key},
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.activate(self.tenant)
        row: dict[str, Any] = created.json()
        return row

    def _unbound_platform_key(self, *, scopes: tuple[str, ...]) -> str:
        """A live platform key bound to no agent definition, as a key created before keys
        were bound would be; no route creates one. Written with no tenant activated (H15).
        Returns the value a caller sends as `X-Api-Key`."""
        tenancy.clear_tenant()
        plain, prefix, key_hash = tokens.new_api_key()
        ApiKey.objects.create(tenant=None, agent=None, name="Unbound reviewer", key_prefix=prefix, key_hash=key_hash, scopes=list(scopes))
        return plain

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

        # A new record carries a source for every fact it sets, an https link each, since
        # there is no provision of its own to cite yet.
        seed_authorities()
        new = instrument_body()
        for missing in ("titles.sv", "regime"):
            without = self._post("/proposals", {**new, "fieldSources": {f: u for f, u in new["fieldSources"].items() if f != missing}}, agent)
            self.assertEqual(without.status_code, 422, without.content)
            self.assertEqual(without.json()["code"], "source_missing")
            self.assertIn(missing, without.json()["detail"])
        not_a_link = self._post("/proposals", {**new, "fieldSources": {**new["fieldSources"], "level": "n/a"}}, agent)
        self.assertEqual(not_a_link.json()["code"], "validation_error")
        self.assertFalse(Proposal.objects.filter(kind="new_instrument").exists())
        filed = self._post("/proposals", new, agent)
        self.assertEqual(filed.status_code, 201, filed.content)
        self.assertEqual(filed.json()["fieldSources"], new["fieldSources"])
        waiting = self.client.get(f"{V1}/proposals?status=open&kind=new_instrument", **editor)
        self.assertEqual([row["id"] for row in waiting.json()["items"]], [filed.json()["id"]])

    def test_pro_s2(self) -> None:
        """PRO-S2

        No scope and no tenant role can change a library record directly (PRO-01, AC-PRO1).
        """
        # The library vocabulary half (chunk 2): an API key with every scope and a tenant admin
        # holding every tenant permission. Instruments, provisions and obligations follow in
        # chunk 3 and reuse the same fence. Only a platform key bound to an agent can hold every
        # scope; a bank's key holds at most the bank's share, so both are tried (ID-S21).
        tenancy.clear_tenant()  # a platform key is written with no tenant activated (H15)
        every_scope = agents_testing.agent_key(scopes=tuple(sorted(perms.ALL_SCOPES)))
        bank_key = factories.api_key(self.tenant, scopes=tuple(sorted(perms.TENANT_KEY_SCOPES)))
        for key in (every_scope, bank_key):
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

        # A new obligation arrives the same way: the record, its first version, the audit
        # row and the re-index in one transaction, or none of them.
        key = factories.api_key(self.tenant, scopes=("proposals:write",))
        new = self._post("/proposals", obligation_body(obligation.instrument.stable_key), {"HTTP_X_API_KEY": key.plain_key})
        self.assertEqual(new.status_code, 201, new.content)
        with mock.patch.object(apply, "reindex", side_effect=RuntimeError("index unavailable")):
            failed = self._post(f"/proposals/{new.json()['id']}/approve", {}, sign_in(self.second_editor, step_up=True))
        self.assertEqual(failed.status_code, 500, failed.content)
        self.assertFalse(Obligation.objects.filter(stable_key=OBLIGATION_KEY).exists())
        self.assertEqual(Proposal.objects.get(pk=new.json()["id"]).status, ProposalStatus.OPEN.value)
        approved = self._post(f"/proposals/{new.json()['id']}/approve", {}, sign_in(self.second_editor, step_up=True))
        self.assertEqual(approved.status_code, 200, approved.content)
        created = Obligation.objects.get(stable_key=OBLIGATION_KEY)
        first_version = ObligationVersion.objects.get(obligation=created)
        self.assertEqual((first_version.version_number, first_version.effective_from), (1, date(2027, 1, 1)))
        self.assertEqual(str(first_version.applied_by_proposal_id), new.json()["id"])
        self.assertEqual(first_version.approved_by_id, self.second_editor.id)
        self.assertTrue(SearchChunk.objects.filter(source_id=first_version.id).exists())
        self.assertIsNotNone(AuditEvent.objects.get(action="obligation.created", subject_id=created.id).step_up_assertion_id)
        self.assertTrue(OutboxEvent.objects.filter(topic="obligation.created").exists())

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
                # Every corrected value names the source it was read in (H35).
                "fieldSources": {field: "https://www.fi.se/" for field in ("summaries.sv", "summaries.en", "terms")},
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
        # A new record is no different: its proposer cannot approve it, and nothing is written.
        seed_authorities()
        filed = self._post("/proposals", instrument_body(), editor)
        self.assertEqual(filed.status_code, 201, filed.content)
        own_record = self._post(f"/proposals/{filed.json()['id']}/approve", {}, editor)
        self.assertEqual(own_record.status_code, 409, own_record.content)
        self.assertEqual(own_record.json()["code"], "four_eyes_violation")
        self.assertFalse(Instrument.objects.filter(stable_key=INSTRUMENT_KEY).exists())

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
        # A new record retried under one key is one proposal, and the key cannot carry another.
        self._obligation()
        retried = {"HTTP_X_API_KEY": key.plain_key, "HTTP_IDEMPOTENCY_KEY": "run-42-obl-7"}
        new = obligation_body("fffs-2017-2")
        once = self._post("/proposals", new, retried)
        self.assertEqual(once.status_code, 201, once.content)
        again = self._post("/proposals", new, retried)
        self.assertEqual((again.status_code, again.json()["id"]), (200, once.json()["id"]))
        self.assertEqual(Proposal.objects.filter(idempotency_key="run-42-obl-7").count(), 1)
        other = self._post("/proposals", obligation_body("fffs-2017-2", refLabel="4 kap. 3 §"), retried)
        self.assertEqual(other.status_code, 409, other.content)
        self.assertEqual(other.json()["code"], "idempotency_conflict")

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

        # "This looks wrong" files a report, and it stays inside the bank (AUD-03).
        words = "The new wording drops the annual review the decision keeps."
        reported = self._post(f"/obligations/{obligation.id}/problem-reports", {"description": words}, officer)
        self.assertEqual(reported.status_code, 201, reported.content)
        report_id = reported.json()["id"]
        self.activate(self.tenant)
        report = ProblemReport.objects.get(subject_id=obligation.id)
        self.assertEqual((str(report.id), report.tenant_id, report.reporter_id), (report_id, self.tenant.id, self.officer.id))

        # No platform session returns it, proven by behaviour rather than by the routes'
        # methods: each platform role signs in and drives every problem-report route the API
        # serves, which refuses it; the console has no problem-report route at all; and no
        # read a platform session can make, on its own or naming the reported duty, its
        # instrument or the proposal the editor just opened, answers with the report's id
        # or its words.
        ids = {
            "obligation_id": str(obligation.id),
            "instrument_id": str(obligation.instrument_id),
            "proposal_id": proposal["id"],
            "report_id": report_id,
        }
        # Each route's body is one its schema accepts, so the refusal is the gate's and not a 422.
        bodies = {"PATCH": {"status": "fixed", "resolutionNote": "A platform note."}}
        filing = [op for op in iter_operations(api) if "problem-report" in op.path]
        self.assertTrue(filing, "the report routes are what this drives")
        reads = [
            op.path.format(**ids)
            for op in iter_operations(api)
            if op.method == "GET" and all(name in ids for name in re.findall(r"{(\w+)}", op.path))
        ]
        self.assertIn(f"/proposals/{proposal['id']}", reads, "the proposal beside the reported duty is read too")
        for person in (self.editor, factories.platform_user(roles=("platform_admin",))):
            platform = sign_in(person)
            for op in filing:
                answer = self.client.generic(
                    op.method,
                    V1 + op.path.format(**ids),
                    json.dumps(bodies.get(op.method, {"description": "A platform note."})),
                    content_type="application/json",
                    **platform,
                )
                self.assertIn(answer.status_code, (403, 404), f"{op.method} {op.path}: {answer.content!r}")
            for path in ("/console/problem-reports", f"/console/problem-reports/{report_id}", "/console/reports"):
                self.assertEqual(self.client.get(f"{V1}{path}", **platform).status_code, 404, path)
            for path in reads:
                body = self.client.get(f"{V1}{path}", **platform).content.decode()
                self.assertNotIn(report_id, body, path)
                self.assertNotIn(words, body, path)
        # The editor's read of that proposal is a full answer, not a refusal, so its body was really searched.
        self.assertEqual(self.client.get(f"{V1}/proposals/{proposal['id']}", **sign_in(self.editor)).status_code, 200)
        self.activate(self.tenant)
        self.assertEqual(ProblemReport.objects.filter(subject_id=obligation.id).count(), 1, "no platform session filed one either")

    def test_pro_s8(self) -> None:
        """PRO-S8

        A batch proposal previews and is approved whole or row by row (PRO-04).
        """
        # Given a re-tag request that would add a term to twelve obligations.
        seed_authorities()
        tenancy.clear_tenant()
        law = library_build.instrument(key="fffs-2017-2", short_name="FFFS 2017:2", regime="regime:securities")
        obligations = [library_build.obligation(law, key=f"obl-client-money-{n:02d}", terms=("client_category:retail",)) for n in range(12)]
        source = "https://www.fi.se/en/published/news/2026/client-money/"
        changes = [{"obligationId": str(o.id), "add": ["service_type:custody"], "source": source} for o in obligations]
        filed = self._post("/proposal-batches", {"kind": "obligation_scope", "title": "Re-tag the client money duties", "payload": {"changes": changes}}, sign_in(self.editor))
        self.assertEqual(filed.status_code, 201, filed.content)
        tenancy.clear_tenant()

        # When the second editor opens it, the preview lists the twelve rows with before and after.
        reviewer = sign_in(self.second_editor, step_up=True)
        preview = self.client.get(f"{V1}/proposal-batches/{filed.json()['id']}", **reviewer).json()
        self.assertEqual({row["subjectId"] for row in preview["rows"]}, {str(o.id) for o in obligations})
        for row in preview["rows"]:
            self.assertEqual((row["before"]["terms"], row["after"]["terms"]), (["client_category:retail"], ["client_category:retail", "service_type:custody"]))

        # When they reject two rows and approve the rest.
        rejected = preview["rows"][:2]
        decided = self._post(
            f"/proposal-batches/{preview['id']}/decide",
            {"rows": [{"rowId": row["id"], "decision": "rejected", "rejectionCode": "wrong_scope"} for row in rejected], "rest": "approved"},
            reviewer,
        )
        self.assertEqual(decided.status_code, 200, decided.content)
        tenancy.clear_tenant()

        # Then ten obligations change, two do not.
        custody = set(ObligationTerm.objects.filter(term__dimension__key="service_type", term__key="custody").values_list("obligation_id", flat=True))
        self.assertEqual(custody, {o.id for o in obligations} - {uuid.UUID(row["subjectId"]) for row in rejected})
        # And one audit event records the batch with each row's outcome.
        (event,) = AuditEvent.objects.filter(action="proposal.batch_decided", subject_id=preview["id"])
        outcomes = {row["subjectId"]: row["decision"] for row in event.after["rows"]}
        self.assertEqual(sorted(outcomes.values()), ["approved"] * 10 + ["rejected"] * 2)
        self.assertEqual({outcomes[row["subjectId"]] for row in rejected}, {"rejected"})

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
        # The reason list holds the sector scope as a system row of its own, whose usage note
        # names the PRD's sector scope, so a reviewer can say why an off-sector record is refused.
        listed = self.client.get(f"{V1}/vocab/rejection_reason", **editor)
        self.assertEqual(listed.status_code, 200, listed.content)
        reason = {row["key"]: row for row in listed.json()["items"]}["outside_sector_scope"]
        self.assertTrue(reason["isSystem"])
        self.assertEqual(reason["labels"], {"en": "Outside the sector scope", "sv": "Utanför sektorsomfattningen"})
        self.assertIn("sector scope", reason["usageNote"])
        self.assertIn("regulated financial services only", reason["usageNote"])

    def test_pro_s10(self) -> None:
        """PRO-S10

        Licensed text and extra obligations never enter a standard (INV-08, PRO-01, PRO-02).
        """
        seed_authorities()
        with library_write("scenario"):
            TaxonomyTerm.objects.filter(dimension__key="standard", key="iso_iec_27001").update(active=True)
            second_standard = TaxonomyTerm.objects.create(dimension=self._term("standard", "iso_iec_27001").dimension, key="iso_22301", sort_order=2)
        standard = library_build.instrument(key=STANDARD_KEY, short_name="ISO/IEC 27001:2022", official_ref="ISO/IEC 27001:2022", regime="regime:ai_ict", level="standard", binding=False)
        self.assertEqual(standard.level.kind, "standard")
        conformance = library_build.obligation(standard, key="obl-iso-iec-27001-2022-conformance", ref_label="ISO/IEC 27001:2022", terms=[STANDARD_TERM])
        law = library_build.instrument(key=PARENT_KEY, regime="regime:securities")
        tenancy.clear_tenant()
        agent_key = agents_testing.agent_key(scopes=(perms.SCOPE_PROPOSALS_WRITE,))
        run = {"agentRunId": str(agents_testing.platform_run(key=agent_key).id)}
        agent = {"HTTP_X_API_KEY": agent_key.plain_key}
        reviewer = sign_in(self.second_editor, step_up=True)

        # A provision of the standard is refused at creation, through POST /proposals as a
        # person and as an agent, and nothing is stored.
        for caller, extra in ((sign_in(self.editor), {}), (agent, run)):
            refused = self._post("/proposals", {**provision_body(STANDARD_KEY), **extra}, caller)
            self.assertEqual(refused.status_code, 422, refused.content)
            self.assertEqual(refused.json()["code"], "licensed_text")
        # A provision version is refused by the same check; the database holds no provision
        # of a standard to version (the last step below).
        with self.assertRaises(ValidationError) as caught:
            standards.check("new_provision_version", standard, None, {})
        self.assertEqual(caught.exception.code, "licensed_text")
        self.assertFalse(Proposal.objects.exists())
        self.assertFalse(AuditEvent.objects.filter(action="proposal.created").exists())

        # A field source on its conformance obligation that is not a link: licensed text.
        cited = library_build.provision(law, key="fffs-2017-2-9-kap")
        version: dict[str, Any] = {
            "kind": "new_obligation_version",
            "title": "Version 2 of the ISO/IEC 27001 conformance duty",
            "targetType": "obligation",
            "targetId": str(conformance.id),
            "payload": {"summaries": {"en": "The bank keeps its certification current."}, "originalLanguage": "en"},
            "sourceLabel": "ISO, catalogue page",
            "sourceUrl": "https://www.iso.org/standard/27001",
        }
        for source in (cited.stable_key, "Clause 5.1: top management shall demonstrate leadership"):
            refused = self._post("/proposals", {**version, "fieldSources": {"summaries.en": source}, **run}, agent)
            self.assertEqual(refused.status_code, 422, refused.content)
            self.assertEqual(refused.json()["code"], "licensed_text")
        self.assertFalse(Proposal.objects.exists())

        # A reviewer's correction that moves a law's provision under the standard is refused
        # at approval, and nothing is written.
        filed = self._post("/proposals", provision_body(), sign_in(self.editor))
        self.assertEqual(filed.status_code, 201, filed.content)
        corrected = self._post(f"/proposals/{filed.json()['id']}/approve", {"payloadOverrides": {"instrument": STANDARD_KEY}}, reviewer)
        self.assertEqual(corrected.status_code, 422, corrected.content)
        self.assertEqual(corrected.json()["code"], "licensed_text")
        self.assertEqual(Proposal.objects.get(pk=filed.json()["id"]).status, ProposalStatus.OPEN.value)
        self.assertFalse(Provision.objects.filter(stable_key=PROVISION_KEY).exists())
        self.assertFalse(AuditEvent.objects.filter(action__in=("proposal.approved", "provision.created")).exists())

        # A second active obligation under the standard: refused where it is made, and where a
        # proposal stored before the rule is applied.
        second = obligation_body(STANDARD_KEY, key="obl-iso-iec-27001-2022-second", refLabel="ISO/IEC 27001:2022", terms=[STANDARD_TERM])
        refused = self._post("/proposals", {**second, **run}, agent)
        self.assertEqual(refused.status_code, 422, refused.content)
        self.assertEqual(refused.json()["code"], "one_conformance_obligation")
        waiting = self._stored(second, agent_key)
        applied = self._post(f"/proposals/{waiting.id}/approve", {}, reviewer)
        self.assertEqual(applied.status_code, 422, applied.content)
        self.assertEqual(applied.json()["code"], "one_conformance_obligation")
        self.assertEqual(list(Obligation.objects.filter(instrument=standard)), [conformance])

        # Its obligation with no standard term, or two, is refused at apply.
        for terms in (["legal_entity:bank"], [STANDARD_TERM, f"standard:{second_standard.key}"]):
            stored = self._stored({**version, "payload": {**version["payload"], "terms": terms}, "fieldSources": {"summaries.en": SOURCE, "terms": SOURCE}}, agent_key)
            applied = self._post(f"/proposals/{stored.id}/approve", {}, reviewer)
            self.assertEqual(applied.status_code, 422, applied.content)
            self.assertEqual(applied.json()["code"], "standard_term_required")
        self.assertEqual([row.version_number for row in conformance.versions.all()], [1])
        self.assertEqual([f"{link.term.dimension.key}:{link.term.key}" for link in ObligationTerm.objects.filter(obligation=conformance)], [STANDARD_TERM])

        # And a provision inserted under it directly, as a seed would, the database refuses.
        with self.assertRaises(IntegrityError) as refused_row, transaction.atomic():
            library_build.provision(standard, key="iso-iec-27001-2022-5-1", ref_label="5.1")
        self.assertIn("provision_not_under_standard", str(refused_row.exception))
        self.assertFalse(Provision.objects.filter(instrument=standard).exists())

    def _stored(self, body: dict[str, Any], key: Any) -> Proposal:
        """A proposal stored as it arrived before a rule existed, bypassing the creation
        check, so the apply's own check is what answers."""
        return Proposal.objects.create(
            kind=body["kind"],
            title=body["title"],
            target_type=body.get("targetType", ""),
            target_id=body.get("targetId"),
            payload=body["payload"],
            field_sources=body["fieldSources"],
            source_url=body["sourceUrl"],
            source_label=body["sourceLabel"],
            origin="agent",
            proposed_by_api_key_id=key.id,
            proposed_by_agent=getattr(key, "agent", None),
        )

    def test_pro_s11(self) -> None:
        """PRO-S11

        A standard term never sits on a law's obligation (FP-01, INV-08).
        """
        obligation = self._obligation()
        self._version_one(obligation)
        # The seeds keep the one standard term switched off until its records exist (D-47);
        # the rule is about the term's dimension being opt-in, so the scenario switches it on.
        with library_write("scenario"):
            TaxonomyTerm.objects.filter(dimension__key="standard", key="iso_iec_27001").update(active=True)
        with_standard = ["legal_entity:bank", "standard:iso_iec_27001"]
        body: dict[str, Any] = {
            "kind": "new_obligation_version",
            "title": "Version 2 of the advice obligation, citing ISO/IEC 27001",
            "targetType": "obligation",
            "targetId": str(obligation.id),
            "payload": {
                "summaries": {"sv": "Institutet bedömer kunden innan rådgivning."},
                "originalLanguage": "sv",
                "effectiveFrom": "2026-10-01",
                "effectiveFromPrecision": "day",
                "terms": with_standard,
            },
            "fieldSources": {"summaries.sv": "https://www.fi.se/", "effectiveFrom": "https://www.fi.se/", "terms": "https://www.fi.se/"},
            "sourceLabel": "FFFS 2017:2",
            "sourceUrl": "https://www.fi.se/",
        }

        # Refused at creation, through a bank's key and through a person's session alike, and
        # nothing is stored.
        key = factories.api_key(self.tenant, scopes=("proposals:write",))
        for caller in ({"HTTP_X_API_KEY": key.plain_key}, sign_in(self.officer, tenant=self.tenant)):
            refused = self._post("/proposals", body, caller)
            self.assertEqual(refused.status_code, 422, refused.content)
            self.assertEqual(refused.json()["code"], "standard_term_only_on_standards")
        self.activate(self.tenant)
        self.assertFalse(Proposal.objects.filter(kind="new_obligation_version").exists())
        self.assertFalse(AuditEvent.objects.filter(action="proposal.created").exists())

        # A reviewer's correction that adds the term is refused at approval: nothing is
        # written, the proposal stays open and uncorrected, and no decision is audited.
        proposal = self._version_proposal(obligation)
        reviewer = sign_in(self.second_editor, step_up=True)
        corrected = self._post(f"/proposals/{proposal['id']}/approve", {"payloadOverrides": {"terms": with_standard}}, reviewer)
        self.assertEqual(corrected.status_code, 422, corrected.content)
        self.assertEqual(corrected.json()["code"], "standard_term_only_on_standards")
        row = Proposal.objects.get(pk=proposal["id"])
        self.assertEqual((row.status, row.corrected_payload), (ProposalStatus.OPEN.value, None))
        self.assertEqual([version.version_number for version in obligation.versions.all()], [1])
        self.assertFalse(AuditEvent.objects.filter(action__in=("proposal.approved", "obligation.version_applied")).exists())
        # The correction is refused on its own, before anything reaches the apply.
        with self.assertRaises(ValidationError) as caught:
            logic.corrected(row, logic.as_reviewer(self.second_editor, Actor.system("test")), {"terms": with_standard})
        self.assertEqual(caught.exception.code, "standard_term_only_on_standards")

        # A proposal that asked for the term before this rule existed is refused where it is
        # applied, with the same code and nothing written.
        Proposal.objects.filter(pk=proposal["id"]).update(payload={**row.payload, "terms": with_standard})
        waited = self._post(f"/proposals/{proposal['id']}/approve", {}, reviewer)
        self.assertEqual(waited.status_code, 422, waited.content)
        self.assertEqual(waited.json()["code"], "standard_term_only_on_standards")
        self.assertEqual(Proposal.objects.get(pk=proposal["id"]).status, ProposalStatus.OPEN.value)
        self.assertEqual([version.version_number for version in obligation.versions.all()], [1])
        self.assertEqual(
            [f"{link.term.dimension.key}:{link.term.key}" for link in ObligationTerm.objects.filter(obligation=obligation)],
            ["legal_entity:bank"],
        )

        # A new obligation under the law that carries the standard's term is refused where it
        # is made, and where one stored before the rule is applied (f03-T42).
        seed_authorities()
        library_build.instrument(key=PARENT_KEY, regime="regime:securities")
        tenancy.clear_tenant()
        new_duty = obligation_body(terms=with_standard)
        editor = sign_in(self.editor)
        refused = self._post("/proposals", new_duty, editor)
        self.assertEqual(refused.status_code, 422, refused.content)
        self.assertEqual(refused.json()["code"], "standard_term_only_on_standards")
        self.assertFalse(Proposal.objects.filter(kind="new_obligation").exists())
        waiting = self._stored(new_duty, factories.api_key(self.tenant, scopes=("proposals:write",)))
        tenancy.clear_tenant()
        applied = self._post(f"/proposals/{waiting.id}/approve", {}, reviewer)
        self.assertEqual(applied.status_code, 422, applied.content)
        self.assertEqual(applied.json()["code"], "standard_term_only_on_standards")
        self.assertFalse(Obligation.objects.filter(stable_key=OBLIGATION_KEY).exists())

        # A bank whose regulatory scope names no standard still sees the duty.
        officer = sign_in(self.officer, tenant=self.tenant)
        listed = self.client.get(f"{V1}/obligations", **officer)
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertIn(str(obligation.id), [item["id"] for item in listed.json()["items"]])

    @skip("pending: PRO-S12 (INV-07, PRO-03, chunk 13)")
    def test_pro_s12(self) -> None:
        """PRO-S12

        A private proposal is approved inside the bank and never reaches the console (INV-07, PRO-03).
        """

    def test_pro_s13(self) -> None:
        """PRO-S13

        An independent agent confirms a proposal from the same queue (PRO-01, PRO-02, AUD-02).
        """
        obligation = self._obligation()
        self._version_one(obligation)
        tenancy.clear_tenant()  # a platform key is written with no tenant activated (H15)
        proposing_agent = agents_testing.agent(key="watch-sweeper-pro-s13")
        proposer_key = agents_testing.agent_key(agent_row=proposing_agent, scopes=(perms.SCOPE_PROPOSALS_WRITE,))
        proposal = self._version_proposal(obligation, key=proposer_key)
        # _version_proposal() re-activates self.tenant for its ordinary callers; a platform
        # key is written with no tenant activated (H15).
        tenancy.clear_tenant()

        # A second platform key, bound to a different agent definition, holds proposals:review.
        # Every decision it makes carries the model call behind it and names the open run of
        # its own key it was made in (AUD-02, D-80).
        reviewer_key = agents_testing.reviewer_api_key()
        reviewer_headers = {"HTTP_X_API_KEY": reviewer_key.plain_key}
        sent = agents_testing.decision(reviewer_key)
        another_agents_run = agents_testing.decision(agents_testing.reviewer_api_key())["agentRunId"]

        # It reads the pending proposals through the queue route a person reads, with the
        # same source beside the same diff.
        listed = self.client.get(f"{V1}/proposals?status=open", **reviewer_headers)
        self.assertEqual(listed.status_code, 200, listed.content)
        row = next(item for item in listed.json()["items"] if item["id"] == proposal["id"])
        self.assertEqual(row["fieldSources"], proposal["fieldSources"])
        self.assertEqual(row["payload"], proposal["payload"])
        self.assertFalse(row["isMine"], "another agent filed it, so it is not this one's own")
        # It opens the proposal as a person does: what the library says today, the diff
        # against it and the source behind every changed field.
        opened = self.client.get(f"{V1}/proposals/{proposal['id']}", **reviewer_headers)
        self.assertEqual(opened.status_code, 200, opened.content)
        detail = opened.json()
        self.assertEqual(detail["fieldSources"], proposal["fieldSources"])
        self.assertEqual(detail["currentSummary"]["text"], VERSION_ONE_SV)
        self.assertEqual([segment["op"] for segment in detail["diff"]], ["delete", "insert"])
        self.assertEqual([source["field"] for source in detail["sources"]], ["effectiveFrom", "summaries.en", "summaries.sv", "terms"])

        # A decision without the model call behind it is refused, and so is one counted in a
        # run of another agent's key, as a run that never existed is (AUD-02, D-80).
        for without, status, code in (
            ({"agentRunId": sent["agentRunId"]}, 422, "validation_error"),
            ({**sent, "agentRunId": another_agents_run}, 404, "not_found"),
        ):
            refused = self._post(f"/proposals/{proposal['id']}/approve", without, reviewer_headers)
            self.assertEqual((refused.status_code, refused.json()["code"]), (status, code), refused.content)

        # Its correction may not move which language the summary was written in: that would
        # store the machine translation as the unlabelled original (INV-05). Refused, and
        # like the two above, nothing applies.
        moved = self._post(f"/proposals/{proposal['id']}/approve", {"payloadOverrides": {"originalLanguage": "en"}, **sent}, reviewer_headers)
        self.assertEqual(moved.status_code, 422, moved.content)
        self.assertEqual(moved.json()["code"], "validation_error")
        self.assertEqual(Proposal.objects.get(pk=proposal["id"]).status, ProposalStatus.OPEN.value)
        self.assertEqual(list(obligation.versions.values_list("version_number", flat=True)), [1])
        self.assertFalse(AiGeneration.objects.filter(subject_id=proposal["id"]).exists(), "a refused decision logs no model call")

        # It corrects the wording and approves through the same route a person calls, and
        # the decision applies exactly as a person's does, in one transaction. Its
        # correction claims the translation is a person's; no person confirmed it, so the
        # translation stays labelled machine-made (INV-05).
        corrected_sv = "Institutet bedömer kundens kunskap och erfarenhet innan rådgivning."
        approved = self._post(
            f"/proposals/{proposal['id']}/approve",
            {
                "note": "Confirmed against the source.",
                "payloadOverrides": {
                    "summaries": {"sv": corrected_sv, "en": "The institution assesses the client's knowledge and experience before advising."},
                    "isMachine": False,
                },
                "fieldSources": {"summaries.sv": "https://www.fi.se/", "summaries.en": "https://www.fi.se/"},
                **sent,
            },
            reviewer_headers,
        )
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.json()["status"], "approved")
        # The model call behind the approval is in the AI output log, as the agent's own
        # report, about this proposal and counted in the run it named (AUD-02, D-80).
        logged = AiGeneration.objects.get(subject_id=proposal["id"])
        self.assertEqual(
            (logged.purpose, logged.subject_type, str(logged.agent_run_id), logged.model_metadata_reported_by_agent),
            ("agent_review", "proposal", sent["agentRunId"], True),
        )
        self.assertEqual((logged.model, logged.citations), (agents_testing.DECISION["model"], agents_testing.DECISION["citations"]))
        version = obligation.versions.order_by("-version_number").first()
        assert version is not None
        self.assertEqual(version.version_number, 2)
        self.assertEqual(
            {text.language_id: (text.text, text.is_original, text.is_machine) for text in version.summaries.all()},
            {
                "sv": (corrected_sv, True, False),
                "en": ("The institution assesses the client's knowledge and experience before advising.", False, True),
            },
        )
        self.assertIsNone(version.approved_by_id)
        self.assertEqual(version.verified_by_agent_id, reviewer_key.agent.id)
        # The correction is the agent's: no person is named as its author, and the decision
        # names the key and the agent definition that made it.
        decided = Proposal.objects.get(pk=proposal["id"])
        self.assertEqual((decided.corrected_payload or {})["summaries"]["sv"], corrected_sv)
        self.assertIsNotNone(decided.corrected_at)
        self.assertIsNone(decided.corrected_by_id)
        self.assertIsNone(decided.reviewed_by_id)
        self.assertEqual(decided.reviewed_by_api_key_id, reviewer_key.id)
        self.assertEqual(decided.reviewed_by_agent_id, reviewer_key.agent.id)

        # The audit row names the confirming agent, its definition version, its key and the
        # run it decided in, and carries no step-up assertion.
        event = AuditEvent.objects.get(action="proposal.approved", subject_id=proposal["id"])
        self.assertEqual(event.actor_type, "agent")
        self.assertEqual(event.actor_id, reviewer_key.agent.id)
        self.assertIn(reviewer_key.agent.key, event.actor_label)
        self.assertIn(f"v{reviewer_key.agent.current_version}", event.actor_label)
        self.assertEqual(event.after["reviewingApiKeyPrefix"], reviewer_key.row.key_prefix)
        self.assertEqual(event.after["agentRunId"], sent["agentRunId"])
        self.assertIsNone(event.step_up_assertion_id)
        self.assertTrue(event.after["corrected"])

        # A platform key bound to an agent but without the review scope answers 403 naming
        # the scope, on every route of the queue, and leaves the proposal as it was, even
        # when it sends its decision in a run of its own.
        waiting = self._version_proposal(obligation, key=proposer_key)
        tenancy.clear_tenant()
        watcher_key = agents_testing.agent_key()
        watcher = {"HTTP_X_API_KEY": watcher_key.plain_key}
        watched = agents_testing.decision(watcher_key)
        for method, path, body in (
            ("GET", "/proposals", None),
            ("GET", f"/proposals/{waiting['id']}", None),
            ("POST", f"/proposals/{waiting['id']}/approve", watched),
            ("POST", f"/proposals/{waiting['id']}/reject", {"rejectionCode": "duplicate", "note": "Already filed.", **watched}),
        ):
            with self.subTest(route=f"{method} {path}"):
                refused = self.client.get(f"{V1}{path}", **watcher) if body is None else self._post(path, body, watcher)
                self.assertEqual(refused.status_code, 403, refused.content)
                self.assertEqual(refused.json()["requiredPermission"], perms.SCOPE_PROPOSALS_REVIEW)
        self.assertEqual(Proposal.objects.get(pk=waiting["id"]).status, ProposalStatus.OPEN.value)

        # It rejects through the same route a person calls: the decision names the agent,
        # and the library is left exactly as it was.
        rejected = self._post(
            f"/proposals/{waiting['id']}/reject",
            {"rejectionCode": "duplicate", "note": "Version 2 already says this.", **sent, "decision": agents_testing.REJECTION_DECISION},
            reviewer_headers,
        )
        self.assertEqual(rejected.status_code, 200, rejected.content)
        self.assertEqual(rejected.json()["status"], "rejected")
        refused_row = Proposal.objects.get(pk=waiting["id"])
        self.assertEqual((refused_row.reviewed_by_api_key_id, refused_row.reviewed_by_agent_id), (reviewer_key.id, reviewer_key.agent.id))
        self.assertEqual(sorted(obligation.versions.values_list("version_number", flat=True)), [1, 2])
        # Its run counts both of its decisions, the approval and the rejection (D-80).
        self.assertEqual(
            sorted(str(row.subject_id) for row in AiGeneration.objects.filter(agent_run_id=sent["agentRunId"])),
            sorted([proposal["id"], waiting["id"]]),
        )

        # It approves a vocabulary proposal from the same queue too, since every list row
        # records who confirmed it (D-79, lifted 2026-09-23): the row names the confirming
        # agent and the proposal, every label it wrote is stored machine-made, and the list
        # read names both agents and no person.
        flag = self._post(
            "/proposals",
            {
                "kind": "vocabulary_create",
                "title": "Add the flag Client money",
                "payload": {"list": "flag", "key": "client_money", "labels": {"en": "Client money", "sv": "Kundmedel"}},
                "agentRunId": str(agents_testing.platform_run(key=proposer_key).id),
            },
            {"HTTP_X_API_KEY": proposer_key.plain_key},
        )
        self.assertEqual(flag.status_code, 201, flag.content)
        tenancy.clear_tenant()
        confirmed = self._post(f"/proposals/{flag.json()['id']}/approve", {"note": "Confirmed.", **sent}, reviewer_headers)
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        self.assertEqual((confirmed.json()["reviewedBy"], confirmed.json()["reviewedByAgent"]["key"]), (None, reviewer_key.agent.key))
        tenancy.clear_tenant()
        row = Flag.objects.get(key="client_money")
        self.assertEqual(
            (row.verified_origin, row.verified_by_agent_id, str(row.applied_by_proposal_id)), ("agent", reviewer_key.agent.id, flag.json()["id"])
        )
        self.assertEqual({label.language: label.is_machine for label in row.labels.all()}, {"en": True, "sv": True})
        console = factories.platform_user(roles=("library_editor",), email="console-pro-s13@bleqq.test")
        read = self.client.get(f"{V1}/vocab/flag/client_money", **sign_in(console))
        self.assertEqual(read.status_code, 200, read.content)
        self.assertEqual(
            (read.json()["verifiedOrigin"], read.json()["confirmedByAgent"]["key"], read.json()["proposedByAgent"]["key"]),
            ("agent", reviewer_key.agent.key, proposing_agent.key),
        )
        self.assertEqual(read.json()["machineLanguages"], ["en", "sv"])
        tenancy.clear_tenant()
        self.assertEqual(AuditEvent.objects.get(action="proposal.approved", subject_id=flag.json()["id"]).after["agentRunId"], sent["agentRunId"])

        # A bank's key without the review scope answers 403; no route under it writes a
        # library row except through apply, which the fence guard proves structurally.
        no_scope = factories.api_key(self.tenant, scopes=("changes:write",))
        self.assertEqual(self.client.get(f"{V1}/proposals", **{"HTTP_X_API_KEY": no_scope.plain_key}).status_code, 403)

    def test_pro_s14(self) -> None:
        """PRO-S14

        The same principal can never both propose and approve (PRO-02, AC-PRO2).
        """
        obligation = self._obligation()
        self._version_one(obligation)
        tenancy.clear_tenant()  # a platform key is written with no tenant activated (H15)
        agent_definition = agents_testing.agent(key="watch-sweeper-pro-s14")
        # A key of the proposing agent, holding both scopes, so it can try to review its own
        # filing: four eyes refuses that by identity, never by a missing scope.
        proposer_key = agents_testing.agent_key(
            agent_row=agent_definition, scopes=(perms.SCOPE_PROPOSALS_WRITE, perms.SCOPE_PROPOSALS_REVIEW)
        )
        proposal = self._version_proposal(obligation, key=proposer_key)
        # _version_proposal() re-activates self.tenant for its ordinary callers; a platform
        # key is written with no tenant activated (H15).
        tenancy.clear_tenant()

        # Each key sends its decision in an open run of its own (D-80), so what refuses it is
        # four eyes and never a missing decision.
        same_key = self._post(
            f"/proposals/{proposal['id']}/approve", agents_testing.decision(proposer_key), {"HTTP_X_API_KEY": proposer_key.plain_key}
        )
        self.assertEqual(same_key.status_code, 409, same_key.content)
        self.assertEqual(same_key.json()["code"], "four_eyes_violation")

        # A second key of the same agent definition is refused the same way.
        tenancy.clear_tenant()
        second_key_same_agent = agents_testing.agent_key(agent_row=agent_definition, scopes=(perms.SCOPE_PROPOSALS_REVIEW,))
        same_agent = self._post(
            f"/proposals/{proposal['id']}/approve",
            agents_testing.decision(second_key_same_agent),
            {"HTTP_X_API_KEY": second_key_same_agent.plain_key},
        )
        self.assertEqual(same_agent.status_code, 409, same_agent.content)
        self.assertEqual(same_agent.json()["code"], "four_eyes_violation")
        self.assertEqual(Proposal.objects.get(pk=proposal["id"]).status, ProposalStatus.OPEN.value)
        self.assertFalse(AiGeneration.objects.filter(subject_id=proposal["id"]).exists(), "a refused decision logs no model call")

        # A platform key holding the review scope but bound to no agent definition is
        # refused at the gate, on every route of the queue, with its own code: nothing it
        # confirmed could be told apart from what it proposed. It has no agent to open a run
        # for, so the run it names is one it never opened; the gate answers first.
        headers: dict[str, Any] = {"HTTP_X_API_KEY": self._unbound_platform_key(scopes=(perms.SCOPE_PROPOSALS_REVIEW,))}
        unbound = {"decision": agents_testing.DECISION, "agentRunId": str(uuid.uuid4())}
        for method, path, body in (
            ("GET", "/proposals", None),
            ("GET", f"/proposals/{proposal['id']}", None),
            ("POST", f"/proposals/{proposal['id']}/approve", unbound),
            ("POST", f"/proposals/{proposal['id']}/reject", {"rejectionCode": "duplicate", "note": "Already filed.", **unbound}),
        ):
            with self.subTest(route=f"{method} {path}"):
                refused = self.client.get(f"{V1}{path}", **headers) if body is None else self._post(path, body, headers)
                self.assertEqual(refused.status_code, 403, refused.content)
                self.assertEqual(refused.json()["code"], "agent_not_bound")
        self.assertEqual(Proposal.objects.get(pk=proposal["id"]).status, ProposalStatus.OPEN.value)

        # A third, unrelated agent, used below only to give an isolating proof its own
        # distinct id: never the reviewer that actually decides this proposal.
        third_reviewer = agents_testing.reviewer_api_key()

        # The queue says so before a different agent approves it: under every key of the
        # proposing definition the proposal is the reader's own and `notMine` drops it; under
        # another agent's key it is neither.
        for reader, own in ((proposer_key, True), (second_key_same_agent, True), (third_reviewer, False)):
            key_headers = {"HTTP_X_API_KEY": reader.plain_key}
            row = next(item for item in self.client.get(f"{V1}/proposals", **key_headers).json()["items"] if item["id"] == proposal["id"])
            self.assertEqual(row["isMine"], own)
            left = [item["id"] for item in self.client.get(f"{V1}/proposals?notMine=true", **key_headers).json()["items"]]
            self.assertEqual(proposal["id"] in left, not own)
            tenancy.clear_tenant()

        # The row is written directly, bypassing the logic: the check constraint refuses it
        # for a repeated user, key or agent alike, and it refuses a reviewing key that names
        # no agent, so two unbound keys cannot pass on nulls.
        from django.db import connection, transaction

        def _refused_by_four_eyes(sql: str, params: list[Any]) -> None:
            with self.assertRaises(Exception) as caught:  # compliance: allow-broad-except the driver raises IntegrityError for a CHECK violation
                with transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute(sql, params)
            self.assertIn("four_eyes", str(caught.exception))

        # Same key: isolated by naming a different agent on the review side too.
        _refused_by_four_eyes(
            "UPDATE proposal SET reviewed_by_api_key_id = %s, reviewed_by_agent_id = %s WHERE id = %s",
            [str(proposer_key.id), str(third_reviewer.agent.id), proposal["id"]],
        )
        # Same agent: isolated by naming a different key on the review side.
        _refused_by_four_eyes(
            "UPDATE proposal SET reviewed_by_api_key_id = %s, reviewed_by_agent_id = %s WHERE id = %s",
            [str(second_key_same_agent.id), str(agent_definition.id), proposal["id"]],
        )
        # A reviewing key that names no agent at all.
        _refused_by_four_eyes(
            "UPDATE proposal SET reviewed_by_api_key_id = %s WHERE id = %s",
            [str(second_key_same_agent.id), proposal["id"]],
        )
        self.assertEqual(Proposal.objects.get(pk=proposal["id"]).status, ProposalStatus.OPEN.value)
        self.assertIsNone(Proposal.objects.get(pk=proposal["id"]).reviewed_by_api_key_id)

        # A key of a different agent definition approves, and the change applies.
        approved = self._post(
            f"/proposals/{proposal['id']}/approve", agents_testing.decision(third_reviewer), {"HTTP_X_API_KEY": third_reviewer.plain_key}
        )
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.json()["status"], "approved")
