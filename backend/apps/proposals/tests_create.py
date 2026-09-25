"""Creating an obligation proposal (chunk 4, PRO-01, PRO-02, AUD-01, INV-04, INV-05).

What a proposal must carry before it is allowed into the queue: a target obligation that
is here and in force, a payload the kind's named schema accepts, and a source for every
field it changes (422 `source_missing`) that a reader can actually follow, for that field
and no other (422 `validation_error`). The same check runs again over a reviewer's
corrections at approval, so it is one importable function.

The payload comes from an agent over the network, so its unbounded parts are bounded
here too: a source is at most `PROPOSAL_SOURCE_MAX_CHARS`, the scope terms at most
`PROPOSAL_SCOPE_MAX_TERMS` and resolved in one query however many there are.

The tenant half: a proposal made inside a tenant is linked to it through `proposal_tenant`
and audited under it, while `proposal` itself keeps no tenant id; a proposal made in the
console is linked to nobody. The policy on the link table is the RLS guard's
(apps/shared/tests_rls.py).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any
from unittest import mock

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.agents import testing as agent_build
from apps.agents.models import RunStatus
from apps.identity.models import ApiKey
from apps.library import testing as library_build
from apps.library.models import Instrument, Jurisdiction, Obligation, ObligationVersion, Provision, RecordStatus
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.proposals import apply, logic
from apps.proposals.models import Proposal, ProposalTenant
from apps.proposals.schemas import ProposalObligationVersionPayload
from apps.shared import factories, tenancy
from apps.shared.errors import ProblemError
from apps.shared.models import AuditEvent
from apps.shared.tenancy import library_write
from apps.taxonomy.models import DutyType, InstrumentLevel, ProvisionKind, TaxonomyTerm
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions

SUMMARIES = {
    "en": "The institution assesses the client before advising.",
    "sv": "Institutet bedömer kunden innan rådgivning.",
}
SOURCE = "https://www.fi.se/"
ALL_SOURCES = {
    "summaries.en": SOURCE,
    "summaries.sv": SOURCE,
    "effectiveFrom": SOURCE,
    "terms": SOURCE,
}


def payload(**overrides: Any) -> dict[str, Any]:  # compliance: allow-kwargs test helper building a payload
    body: dict[str, Any] = {
        "summaries": dict(SUMMARIES),
        "originalLanguage": "sv",
        "isMachine": True,
        "effectiveFrom": "2026-10-01",
        "effectiveFromPrecision": "day",
        "terms": ["legal_entity:bank", "client_category:retail"],
    }
    body.update(overrides)
    return body


class ObligationProposalCreation(TestCase):
    """The rules at `POST /proposals` for kind new_obligation_version."""

    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        self.obligation = self._obligation("obl-proposal-target")
        self.proposer = logic.Proposer(actor=factories.user_actor(), user=None)

    def _obligation(self, stable_key: str, *, status: str = RecordStatus.ACTIVE.value) -> Obligation:
        with library_write("test"):
            instrument, _ = Instrument.objects.get_or_create(
                stable_key="fffs-2017-2",
                defaults={
                    "short_name": "FFFS 2017:2",
                    "official_ref": "FFFS 2017:2",
                    "source_url": SOURCE,
                    "level": InstrumentLevel.objects.get(key="act"),
                    "binding": True,
                    "jurisdiction": Jurisdiction.objects.get(key="se"),
                    "regime": TaxonomyTerm.objects.get(dimension__key="regime", key="securities"),
                    "created_origin": "user",
                },
            )
            return Obligation.objects.create(
                stable_key=stable_key,
                instrument=instrument,
                ref_label="9 kap. 6 §",
                duty_type=DutyType.objects.get(key="conduct"),
                created_origin="user",
                source_url=SOURCE,
                source_label="FFFS 2017:2, 9 kap. 6 §",
                status=status,
            )

    def _create(self, **overrides: Any) -> Proposal:  # compliance: allow-kwargs test helper forwarding create() arguments
        arguments: dict[str, Any] = {
            "kind": "new_obligation_version",
            "title": "Version 2 of the advice obligation",
            "payload": payload(),
            "proposer": self.proposer,
            "target_type": "obligation",
            "target_id": self.obligation.id,
            "field_sources": dict(ALL_SOURCES),
        }
        arguments.update(overrides)
        proposal, _ = logic.create(**arguments)
        return proposal

    def _refused(self, **overrides: Any) -> ValidationError:  # compliance: allow-kwargs test helper forwarding create() arguments
        with self.assertRaises(ValidationError) as caught:
            self._create(**overrides)
        return caught.exception

    # -----------------------------------------------------------------------------------
    # A source per changed field
    # -----------------------------------------------------------------------------------
    def test_every_changed_field_needs_a_source(self) -> None:
        for dropped in ("summaries.en", "summaries.sv", "effectiveFrom", "terms"):
            with self.subTest(field=dropped):
                sources = {field: url for field, url in ALL_SOURCES.items() if field != dropped}
                error = self._refused(field_sources=sources)
                self.assertEqual(error.code, "source_missing")
                self.assertIn(dropped, str(error))
        blank = self._refused(field_sources={**ALL_SOURCES, "terms": "   "})
        self.assertEqual(blank.code, "source_missing")
        self.assertFalse(Proposal.objects.exists())

    def test_a_field_the_payload_leaves_out_needs_no_source(self) -> None:
        proposal = self._create(
            payload=payload(effectiveFrom=None, terms=None),
            field_sources={"summaries.en": SOURCE, "summaries.sv": SOURCE},
        )
        self.assertEqual(proposal.field_sources, {"summaries.en": SOURCE, "summaries.sv": SOURCE})
        self.assertNotIn("terms", proposal.payload)

    def test_the_source_check_is_one_function_review_runs_too(self) -> None:
        # Approval runs the same function over a reviewer's corrected payload: one rule,
        # one implementation, so a correction cannot slip a sourceless field past it.
        corrected = ProposalObligationVersionPayload.model_validate(payload(terms=["legal_entity:insurer"]))
        logic.check_field_sources(corrected, ALL_SOURCES)
        self.assertEqual(
            logic.sourced_fields(corrected), ["summaries.en", "summaries.sv", "effectiveFrom", "terms"]
        )
        with self.assertRaises(ValidationError) as caught:
            logic.check_field_sources(corrected, {field: SOURCE for field in ALL_SOURCES if field != "terms"})
        self.assertEqual(caught.exception.code, "source_missing")

    def test_a_source_is_a_link_or_a_provision_the_library_holds(self) -> None:
        # An agent writes these, and a reviewer and the console read them as the source of
        # the fact. A note nobody can follow is not a source, and neither is a scheme a
        # browser would execute or an unencrypted link.
        for value in ("n/a", "see above", "javascript:alert(1)", "http://www.fi.se/", "fffs-2017-2/9"):
            with self.subTest(source=value):
                refused = self._refused(field_sources={**ALL_SOURCES, "terms": value})
                self.assertEqual(refused.code, "validation_error")
        self.assertFalse(Proposal.objects.exists())
        # The stable key of a provision the library holds is a source a reader can follow.
        with library_write("test"):
            Provision.objects.create(
                stable_key="fffs-2017-2/9",
                instrument=self.obligation.instrument,
                kind=ProvisionKind.objects.get(key="chapter"),
                ref_label="9 kap.",
                path="FFFS 2017:2 > 9 kap.",
            )
        self.assertEqual(self._create(field_sources={**ALL_SOURCES, "terms": "fffs-2017-2/9"}).field_sources["terms"], "fffs-2017-2/9")

    def test_a_source_names_a_field_the_proposal_changes(self) -> None:
        # A source beside a field this proposal never touches is a claim about nothing.
        refused = self._refused(field_sources={**ALL_SOURCES, "dutyType": SOURCE})
        self.assertEqual(refused.code, "validation_error")
        self.assertIn("dutyType", str(refused))
        self.assertFalse(Proposal.objects.exists())

    def test_a_source_longer_than_the_cap_is_refused(self) -> None:
        too_long = SOURCE + "a" * settings.PROPOSAL_SOURCE_MAX_CHARS
        refused = self._refused(field_sources={**ALL_SOURCES, "summaries.en": too_long})
        self.assertEqual(refused.code, "validation_error")
        self.assertFalse(Proposal.objects.exists())

    # -----------------------------------------------------------------------------------
    # The scope terms
    # -----------------------------------------------------------------------------------
    def test_the_scope_terms_are_deduplicated_capped_and_resolved_in_one_query(self) -> None:
        # Stored once, so the apply that replaces the obligation's term links cannot fail
        # on its uniqueness constraint after a reviewer approved it.
        repeated = self._create(payload=payload(terms=["legal_entity:bank", "legal_entity:bank", "client_category:retail"]))
        self.assertEqual(repeated.payload["terms"], ["legal_entity:bank", "client_category:retail"])
        # However many terms, the same number of queries: a long list is never a long
        # transaction holding the proposal's row.
        with CaptureQueriesContext(connection) as few:
            self._create(payload=payload(terms=["legal_entity:bank"]))
        with CaptureQueriesContext(connection) as many:
            self._create(payload=payload(terms=["legal_entity:bank", "client_category:retail", "service_type:advice", "channel:digital"]))
        self.assertEqual(len(many.captured_queries), len(few.captured_queries))
        # And the count is capped, so a payload of a hundred thousand never reaches them.
        over = self._refused(payload=payload(terms=["legal_entity:bank"] * (settings.PROPOSAL_SCOPE_MAX_TERMS + 1)))
        self.assertEqual(over.code, "validation_error")

    # -----------------------------------------------------------------------------------
    # The effective date
    # -----------------------------------------------------------------------------------
    def test_the_date_on_the_row_is_the_date_in_the_payload(self) -> None:
        # The queue shows the reviewer one effective date; approval writes the payload's.
        # Two different dates would make the screen lie, so they are refused.
        mismatch = self._refused(effective_from=date(2027, 1, 1))
        self.assertEqual(mismatch.code, "validation_error")
        self.assertFalse(Proposal.objects.exists())
        self.assertEqual(self._create().effective_from, date(2026, 10, 1))
        self.assertEqual(self._create(effective_from=date(2026, 10, 1)).effective_from, date(2026, 10, 1))

    # -----------------------------------------------------------------------------------
    # Applying a kind nothing can write yet
    # -----------------------------------------------------------------------------------
    def test_a_kind_whose_apply_is_not_built_is_refused_where_a_reviewer_sees_it(self) -> None:
        # A kind can reach the deployed queue before the apply that writes it exists, as
        # new_obligation_version itself did between chunk 4's first and second tasks. An
        # approval of one is refused where a reviewer can act on it, never applied in part
        # and never silently approved with nothing written.
        proposal = self._create()
        proposal.kind = "retire_obligation"
        with mock.patch.dict(logic.PAYLOAD_SCHEMAS, {proposal.kind: ProposalObligationVersionPayload}):
            with self.assertRaises(ValidationError) as caught:
                apply.apply(proposal, actor=factories.user_actor(), reviewer=None, step_up=uuid.uuid4())
        self.assertEqual(caught.exception.code, "unknown_key")
        self.assertEqual(ObligationVersion.objects.count(), 0)

    # -----------------------------------------------------------------------------------
    # Idempotency
    # -----------------------------------------------------------------------------------
    def test_a_retry_that_changes_the_target_or_a_source_is_a_conflict(self) -> None:
        # Answering the first proposal would lose the second one silently, and the target
        # and the sources are as much of the proposal as its payload is.
        other = self._obligation("obl-proposal-other")
        self._create(idempotency_key="run-7-version-2")
        cases: dict[str, dict[str, Any]] = {
            "target": {"target_id": other.id},
            "sources": {"field_sources": {**ALL_SOURCES, "terms": "https://www.regeringen.se/"}},
        }
        for name, overrides in cases.items():
            with self.subTest(differs=name):
                conflict = self._refused(idempotency_key="run-7-version-2", **overrides)
                self.assertEqual(conflict.code, "idempotency_conflict")
        self.assertEqual(Proposal.objects.count(), 1)

    # -----------------------------------------------------------------------------------
    # The target
    # -----------------------------------------------------------------------------------
    def test_the_target_obligation_is_here_and_in_force(self) -> None:
        unknown = self._refused(target_id=uuid.uuid4())
        self.assertEqual(unknown.code, "unknown_key")
        retired = self._obligation("obl-proposal-retired", status=RecordStatus.RETIRED.value)
        self.assertEqual(self._refused(target_id=retired.id).code, "unknown_key")
        self.assertEqual(self._refused(target_type="", target_id=None).code, "validation_error")
        self.assertEqual(self._refused(target_type="instrument").code, "validation_error")
        self.assertFalse(Proposal.objects.exists())

    # -----------------------------------------------------------------------------------
    # The payload schema
    # -----------------------------------------------------------------------------------
    def test_the_payload_is_the_kind_s_named_schema(self) -> None:
        stored = self._create().payload
        self.assertEqual(stored["summaries"], SUMMARIES)
        self.assertEqual(stored["originalLanguage"], "sv")
        self.assertTrue(stored["isMachine"])
        self.assertEqual(stored["terms"], ["legal_entity:bank", "client_category:retail"])
        self.assertEqual(stored["effectiveFromPrecision"], "day")

    def test_the_payload_refuses_what_the_library_could_not_carry(self) -> None:
        cases = {
            "summaryEn": (payload(summaryEn="Text."), "validation_error"),
            "no summary": (payload(summaries={}), "validation_error"),
            "unknown language": (payload(summaries={"de": "Text."}, originalLanguage="de"), "unknown_key"),
            "original not written": (payload(originalLanguage="en", summaries={"sv": "Text."}), "validation_error"),
            "precision": (payload(effectiveFromPrecision="decade"), "unknown_key"),
            "term without a dimension": (payload(terms=["bank"]), "validation_error"),
            "unknown term": (payload(terms=["legal_entity:spaceline"]), "unknown_key"),
        }
        for name, (body, code) in cases.items():
            with self.subTest(case=name):
                self.assertEqual(self._refused(payload=body).code, code)
        self.assertFalse(Proposal.objects.exists())

    def test_the_vocabulary_kinds_keep_their_chunk_two_rules(self) -> None:
        # No source is asked of a label a person writes, and the list check still bites.
        proposal, created = logic.create(
            kind="vocabulary_create",
            title="Add the flag Client money",
            payload={"list": "flag", "key": "client_money", "labels": {"en": "Client money"}},
            proposer=self.proposer,
        )
        self.assertTrue(created)
        self.assertEqual(proposal.field_sources, {})
        self.assertEqual(logic.sourced_fields(logic.parsed_payload(proposal.kind, proposal.payload)), [])
        with self.assertRaises(ValidationError) as caught:
            logic.create(
                kind="vocabulary_create",
                title="Add a row to a list nobody has",
                payload={"list": "planet", "key": "mars", "labels": {"en": "Mars"}},
                proposer=self.proposer,
            )
        self.assertEqual(caught.exception.code, "unknown_key")


class AnAgentsProposalNamesItsRun(TestCase):
    """AGT-01, PRO-01: a proposal from a key bound to an agent names an open run of that
    key, so every proposal an agent filed traces to the night that produced it. The check
    is `runs.require_open_run_of_key`, the one every agent write asks."""

    FLAG = {"list": "flag", "key": "client_money", "labels": {"en": "Client money"}}

    def setUp(self) -> None:
        seed_languages()
        seed_library_vocabularies()
        tenancy.clear_tenant()  # a platform key is written with no tenant activated (H15)
        self.key = agent_build.agent_key(scopes=("proposals:write",))
        self.open_run = agent_build.platform_run(key=self.key)
        self.proposer = logic.Proposer(actor=factories.agent_actor(), api_key_id=self.key.id, agent_id=self.key.agent.id)

    def _create(self, proposer: logic.Proposer, agent_run_id: uuid.UUID | None) -> Proposal:
        proposal, _ = logic.create(
            kind="vocabulary_create",
            title="Add the flag Client money",
            payload=dict(self.FLAG),
            proposer=proposer,
            agent_run_id=agent_run_id,
        )
        return proposal

    def test_an_open_run_of_the_key_is_stored_on_the_proposal(self) -> None:
        self.assertEqual(self._create(self.proposer, self.open_run.id).agent_run_id, self.open_run.id)

    def test_naming_no_run_or_a_closed_one_is_refused(self) -> None:
        with self.assertRaises(ValidationError) as missing:
            self._create(self.proposer, None)
        self.assertEqual(missing.exception.code, "run_not_open")
        self.open_run.status = RunStatus.SUCCEEDED.value
        self.open_run.save(update_fields=["status"])
        with self.assertRaises(ValidationError) as closed:
            self._create(self.proposer, self.open_run.id)
        self.assertEqual(closed.exception.code, "run_not_open")
        self.assertFalse(Proposal.objects.exists())

    def test_a_run_of_another_key_or_a_person_naming_one_is_not_found(self) -> None:
        """404 and never 422: which run ids exist is not something a caller may probe for,
        and a person opens no run at all."""
        stranger = agent_build.agent_key(scopes=("proposals:write",))
        editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        others = {
            "another key": logic.Proposer(actor=factories.agent_actor(), api_key_id=stranger.id, agent_id=stranger.agent.id),
            "a person": logic.Proposer(actor=factories.user_actor(user_id=editor.id), user=editor),
        }
        for name, proposer in others.items():
            with self.subTest(caller=name):
                with self.assertRaises(ProblemError) as caught:
                    self._create(proposer, self.open_run.id)
                self.assertEqual(caught.exception.status, 404)
        self.assertFalse(Proposal.objects.exists())


class ProposalTenantLink(TestCase):
    """Who a proposal was made by, without telling the console which bank (PRO-03)."""

    def setUp(self) -> None:
        seed_languages()
        seed_library_vocabularies()

    def _vocabulary_proposal(self, proposer: logic.Proposer) -> Proposal:
        proposal, _ = logic.create(
            kind="vocabulary_create",
            title="Add the flag Client money",
            payload={"list": "flag", "key": "client_money", "labels": {"en": "Client money"}},
            proposer=proposer,
        )
        return proposal

    def test_a_proposal_made_inside_a_tenant_is_linked_to_it_and_audited_under_it(self) -> None:
        tenant = factories.tenant(slug="link-a")  # leaves the tenant activated, as a request does
        person = factories.member_user(tenant, roles=("compliance_officer",))
        proposal = self._vocabulary_proposal(logic.Proposer(actor=factories.user_actor(user_id=person.id), user=person))
        self.assertTrue(proposal.proposed_in_tenant)
        links = list(ProposalTenant.objects.filter(proposal=proposal))
        self.assertEqual([link.tenant_id for link in links], [tenant.id])
        event = AuditEvent.objects.get(action="proposal.created", subject_id=proposal.id)
        self.assertEqual(event.tenant_id, tenant.id)
        # The proposal row itself never learns the tenant: only the boolean.
        self.assertNotIn("tenant", {field.name for field in Proposal._meta.get_fields()})

    def test_a_proposal_made_in_the_console_is_linked_to_nobody(self) -> None:
        editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        proposal = self._vocabulary_proposal(logic.Proposer(actor=factories.user_actor(user_id=editor.id), user=editor))
        self.assertFalse(proposal.proposed_in_tenant)
        self.assertFalse(ProposalTenant.objects.filter(proposal=proposal).exists())
        self.assertIsNone(AuditEvent.objects.get(action="proposal.created", subject_id=proposal.id).tenant_id)

    def test_a_platform_key_s_proposal_is_linked_to_nobody(self) -> None:
        # A key with no tenant (ID-10) is the platform's own agent: nothing to link it to.
        key = ApiKey.objects.create(name="Platform agent", key_prefix="plat1234", key_hash="x" * 64, scopes=["proposals:write"])
        proposal = self._vocabulary_proposal(logic.Proposer(actor=factories.agent_actor(), api_key_id=key.id))
        self.assertFalse(proposal.proposed_in_tenant)
        self.assertFalse(ProposalTenant.objects.exists())
        self.assertIsNone(AuditEvent.objects.get(action="proposal.created", subject_id=proposal.id).tenant_id)

    def test_a_replayed_submission_is_audited_under_the_proposer_s_tenant(self) -> None:
        tenant = factories.tenant(slug="link-b")
        proposer = logic.Proposer(actor=factories.agent_actor(), api_key_id=factories.api_key(tenant).id)
        body: dict[str, Any] = {
            "kind": "vocabulary_create",
            "title": "Add the flag Client money",
            "payload": {"list": "flag", "key": "client_money", "labels": {"en": "Client money"}},
            "proposer": proposer,
            "idempotency_key": "run-42-flag-7",
        }
        first, created = logic.create(**body)
        again, created_again = logic.create(**body)
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(again.id, first.id)
        self.assertEqual(ProposalTenant.objects.filter(proposal=first).count(), 1)
        replayed = AuditEvent.objects.get(action="proposal.replayed", subject_id=first.id)
        self.assertEqual(replayed.tenant_id, tenant.id)

    def test_a_retry_key_answers_only_the_proposer_that_sent_it(self) -> None:
        """An `Idempotency-Key` is the caller's own (playbook 4.3): another bank, or the
        platform's agent, sending the same value files its own proposal and is never handed
        the first one, its status or the note it was decided with."""
        body: dict[str, Any] = {
            "kind": "vocabulary_create",
            "title": "Add the flag Client money",
            "payload": {"list": "flag", "key": "client_money", "labels": {"en": "Client money"}},
            "idempotency_key": "flag-client-money",
        }
        bank_a = factories.tenant(slug="key-a")
        officer_a = factories.member_user(bank_a, roles=("compliance_officer",))
        first, _ = logic.create(**body, proposer=logic.Proposer(actor=factories.user_actor(user_id=officer_a.id), user=officer_a))
        Proposal.objects.filter(pk=first.pk).update(status="rejected", review_note="Covered by Bank A's own flag")

        bank_b = factories.tenant(slug="key-b")
        officer_b = factories.member_user(bank_b, roles=("compliance_officer",))
        theirs, created = logic.create(**body, proposer=logic.Proposer(actor=factories.user_actor(user_id=officer_b.id), user=officer_b))
        self.assertTrue(created)
        self.assertNotEqual(theirs.id, first.id)
        self.assertEqual(theirs.review_note, "")
        other_body = {**body, "title": "Add the flag Client assets"}
        other, created = logic.create(**other_body, proposer=logic.Proposer(actor=factories.agent_actor(), api_key_id=factories.api_key(bank_b).id))
        self.assertTrue(created, "the same value from another caller is never a conflict with someone else's")

        tenancy.clear_tenant()
        key = ApiKey.objects.create(name="Platform agent", key_prefix="plat5678", key_hash="y" * 64, scopes=["proposals:write"])
        platform, created = logic.create(**body, proposer=logic.Proposer(actor=factories.agent_actor(), api_key_id=key.id))
        self.assertTrue(created)
        self.assertEqual(len({first.id, theirs.id, other.id, platform.id}), 4)

        with self.assertRaises(ValidationError) as caught:
            logic.create(**{**body, "idempotency_key": "k" * 201}, proposer=logic.Proposer(actor=factories.agent_actor(), api_key_id=key.id))
        self.assertEqual(caught.exception.code, "validation_error")


class ProposalInputAtTheBoundary(TestCase):
    """What every proposal carries across the trust boundary, whatever its kind (PRO-01,
    INV-08, H35, security-review-c4 L2 to L4): its `sourceUrl` is an https link or nothing,
    because the console renders it as the proposal's source link; a text per language is at
    most `PROPOSAL_TEXT_MAX_CHARS`, so nothing is queued that approval could not write; and
    under a standard the free-text `sourceLabel` names the standard by its official
    reference and nothing else, since it lands on the standard's obligation."""

    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        self.law = library_build.obligation(library_build.instrument(key="fffs-2017-2", regime="regime:securities"), key="obl-boundary")
        self.conformance = library_build.standard()
        self.proposer = logic.Proposer(actor=factories.user_actor(), user=None)

    def _version(self, obligation: Obligation, **overrides: Any) -> Proposal:  # compliance: allow-kwargs test helper forwarding create() arguments
        arguments: dict[str, Any] = {
            "kind": "new_obligation_version",
            "title": "A new version",
            "payload": {"summaries": {"en": "The institution keeps a register."}, "originalLanguage": "en"},
            "proposer": self.proposer,
            "target_type": "obligation",
            "target_id": obligation.id,
            "field_sources": {"summaries.en": SOURCE},
        }
        arguments.update(overrides)
        proposal, _ = logic.create(**arguments)
        return proposal

    def _refused(self, code: str, work: Any) -> None:
        with self.assertRaises(ValidationError) as caught:
            work()
        self.assertEqual(caught.exception.code, code)
        self.assertFalse(Proposal.objects.exists(), "a refused proposal is never queued")

    def test_a_source_url_that_is_not_an_https_link_is_refused_on_every_kind(self) -> None:
        flag = {"list": "flag", "key": "client_money", "labels": {"en": "Client money"}}
        for url in ("http://www.fi.se/", "javascript:alert(1)", "ftp://www.fi.se/", "www.fi.se"):
            with self.subTest(kind="new_obligation_version", url=url):
                self._refused("validation_error", lambda url=url: self._version(self.law, source_url=url))
            with self.subTest(kind="vocabulary_create", url=url):
                self._refused(
                    "validation_error",
                    lambda url=url: logic.create(kind="vocabulary_create", title="Add a flag", payload=flag, proposer=self.proposer, source_url=url),
                )
        # An https link, or none at all, is what a version or a vocabulary row may carry.
        self.assertEqual(self._version(self.law, source_url=f" {SOURCE} ").source_url, SOURCE)
        self.assertEqual(logic.create(kind="vocabulary_create", title="Add a flag", payload=flag, proposer=self.proposer)[0].source_url, "")

    def test_a_text_longer_than_the_cap_is_refused_before_it_is_queued(self) -> None:
        provision = library_build.provision(self.law.instrument, key="fffs-2017-2-9-kap")
        with self.settings(PROPOSAL_TEXT_MAX_CHARS=40):
            long = "x" * 41
            self._refused("validation_error", lambda: self._version(self.law, payload={"summaries": {"en": long}, "originalLanguage": "en"}))
            self._refused(
                "validation_error",
                lambda: logic.create(
                    kind="new_provision_version",
                    title="New text",
                    payload={"texts": {"sv": "Kort.", "en": long}, "originalLanguage": "sv"},
                    proposer=self.proposer,
                    target_type="provision",
                    target_id=provision.id,
                    field_sources={"texts.sv": SOURCE, "texts.en": SOURCE},
                ),
            )
            # At the cap is not over it.
            self.assertTrue(self._version(self.law, payload={"summaries": {"en": "x" * 40}, "originalLanguage": "en"}).id)

    def test_a_source_label_under_a_standard_is_its_official_reference_alone(self) -> None:
        reference = self.conformance.instrument.official_ref
        pasted = "5.1 Leadership and commitment: top management shall demonstrate leadership"
        self._refused("licensed_text", lambda: self._version(self.conformance, source_label=pasted, source_url=SOURCE))
        self.assertEqual(self._version(self.conformance, source_label=reference).source_label, reference)
        self.assertEqual(self._version(self.conformance).source_label, "")
        # A law's label names its source in words, as before.
        self.assertEqual(self._version(self.law, source_label=pasted).source_label, pasted)
