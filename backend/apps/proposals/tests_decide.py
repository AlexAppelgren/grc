"""Deciding a proposal (PRO-02, AC-PRO1, AC-PRO2, INV-05): the row locks that let one
decision land and number one obligation's versions in turn, the person's fresh passkey on
approval, and the kinds an agent may confirm.

The races run two sessions at once, each on its own cw_app connection in its own thread and
transaction, the way two requests reach production (the helpers in apps/shared/testing.py,
shared with apps/taxonomy/tests_footprint.py). The first session decides and holds its transaction open
until PostgreSQL reports the second one waiting on it, then commits: the interleaving in
which a status check on an unlocked row lets both through, because the second session read
"open" before the first committed.

Proven to fail 2026-09-23 without the row lock in `logic._decidable`: the rejection landed
on top of the approval (both decisions recorded, the proposal rejected with its change
applied), and the second approval died on the flag's unique key rather than answering
`invalid_transition`.

The step-up half is the runtime twin of the library fence's structural check that
approveProposal names `enforce_step_up` (apps/shared/tests_library_fence.py): a person's
approval without an assertion, or with one older than STEP_UP_FRESHNESS_MINUTES, is refused
and applies nothing.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any
import threading
from unittest import mock

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DEFAULT_DB_ALIAS, IntegrityError, connection, connections, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from apps.agents import testing as agents_testing
from apps.governance.models import AiGeneration, AiPurpose
from apps.library import testing as build
from apps.library.models import ObligationVersion
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.proposals import logic
from apps.proposals.models import Proposal, ProposalStatus
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.audit import Actor, ActorType
from apps.shared.models import AuditEvent
from apps.shared.schemas import AgentDecision
from apps.shared.testing import LANDED, RACE_WAIT_SECONDS, ScenarioTestCase, backend_pid, hold_until_waiting_on_me, sign_in
from apps.taxonomy.models import Flag, TaxonomyTerm
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions

V1 = "/api/v1"
DECISIONS = ("proposal.approved", "proposal.rejected")
FLAG = {"list": "flag", "key": "client_money", "labels": {"en": "Client money", "sv": "Kundmedel"}}
TERM = {"dimension": "regime", "key": "crypto_assets", "labels": {"en": "Crypto-assets"}}


def _seed() -> None:
    seed_languages()
    seed_jurisdictions()
    seed_library_vocabularies()
    seed_term_dimensions()
    seed_taxonomy_terms()


def _actor(user: Any) -> Actor:
    return Actor(kind=ActorType.USER, id=user.id, label=user.name)


def _agent_actor(key: Any) -> Actor:
    return Actor(kind=ActorType.AGENT, id=key.agent.id, label=key.agent.key)


def _platform_session(work: Callable[[], object]) -> str:
    """Run `work` in one transaction on a fresh cw_app connection of this thread's own, in
    the platform's zone as a console request is. Answers "landed" when it committed, or the
    refusal's code."""
    connections[DEFAULT_DB_ALIAS] = connections.create_connection("app")
    try:
        with transaction.atomic():
            tenancy.clear_tenant()
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_user")
                assert cursor.fetchone()[0] == connections.settings["app"]["USER"], "a racing session must be cw_app"
            work()
        return LANDED
    except ValidationError as refusal:
        return str(refusal.code)
    finally:
        connections[DEFAULT_DB_ALIAS].close()


def _race(first: Callable[[], object], second: Callable[[], object]) -> tuple[str, str]:
    """`first` decides and keeps its transaction open until `second` waits on it."""
    acted = threading.Event()
    second_pid: list[int] = []

    def lead() -> None:
        first()
        acted.set()
        hold_until_waiting_on_me(second_pid)

    def follow() -> None:
        second_pid.append(backend_pid())
        if not acted.wait(RACE_WAIT_SECONDS):
            raise AssertionError("the first session never decided")
        second()

    with ThreadPoolExecutor(max_workers=2) as pool:
        leading = pool.submit(_platform_session, lead)
        following = pool.submit(_platform_session, follow)
        return leading.result(), following.result()


def _approval(proposal_id: uuid.UUID, reviewer: Any) -> Callable[[], object]:
    # What the route does: an unlocked read by id, then the decision.
    return lambda: logic.approve(
        proposal=logic.by_id(proposal_id),
        reviewer=reviewer,
        actor=_actor(reviewer),
        note="",
        step_up_assertion_id=uuid.uuid4(),
    )


class ProposalDecisionRaces(TransactionTestCase):
    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        with transaction.atomic():
            _seed()
        with transaction.atomic():
            tenancy.clear_tenant()
            proposer = factories.platform_user(roles=("library_editor",), email="proposer@bleqq.test")
            self.first = factories.platform_user(roles=("library_editor",), email="first@bleqq.test")
            self.second = factories.platform_user(roles=("library_editor",), email="second@bleqq.test")
            self.proposal, _ = logic.create(
                kind="vocabulary_create",
                title="Add the flag Client money",
                payload=FLAG,
                proposer=logic.Proposer(actor=_actor(proposer), user=proposer),
            )

    # --- helpers --------------------------------------------------------------------------
    def _approve(self, reviewer: Any) -> Callable[[], object]:
        return _approval(self.proposal.id, reviewer)

    def _reject(self, reviewer: Any) -> Callable[[], object]:
        return lambda: logic.reject(
            proposal=logic.by_id(self.proposal.id),
            reviewer=reviewer,
            actor=_actor(reviewer),
            rejection_code="duplicate",
            note="We have this already.",
        )

    def _assert_approved_once(self) -> None:
        with transaction.atomic():
            tenancy.clear_tenant()
            decided = Proposal.objects.get(pk=self.proposal.id)
            self.assertEqual((decided.status, decided.reviewed_by_id), (ProposalStatus.APPROVED.value, self.first.id))
            events = AuditEvent.objects.filter(subject_id=self.proposal.id, action__in=DECISIONS)
            self.assertEqual([event.action for event in events], ["proposal.approved"])
            self.assertEqual(Flag.objects.filter(key=FLAG["key"]).count(), 1)

    # --- the races ------------------------------------------------------------------------
    def test_an_approval_and_a_rejection_at_once_land_one_decision(self) -> None:
        outcomes = _race(self._approve(self.first), self._reject(self.second))
        self.assertEqual(outcomes, (LANDED, "invalid_transition"))
        self._assert_approved_once()

    def test_two_approvals_at_once_apply_once(self) -> None:
        outcomes = _race(self._approve(self.first), self._approve(self.second))
        self.assertEqual(outcomes, (LANDED, "invalid_transition"))
        self._assert_approved_once()


class ObligationVersionRaces(TransactionTestCase):
    """Two approvals of different proposals on one obligation at once (PRO-02, INV-04):
    each version is numbered after the one before it, rather than both claiming the same
    number and one dying on the version's unique key as a 500. Agents working the queue in
    parallel make this the ordinary case.

    Proven to fail 2026-09-23 without the obligation's row lock in
    `apply._obligation_version`: the second approval raised IntegrityError on
    `obligation_version_unique`."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        with transaction.atomic():
            _seed()
        with transaction.atomic():
            tenancy.clear_tenant()
            self.obligation = build.obligation(build.instrument(key="race-instrument", regime="regime:securities"), key="obl-race")
            proposer = factories.platform_user(roles=("library_editor",), email="proposer@bleqq.test")
            self.first = factories.platform_user(roles=("library_editor",), email="first@bleqq.test")
            self.second = factories.platform_user(roles=("library_editor",), email="second@bleqq.test")
            self.proposals = [
                logic.create(
                    kind="new_obligation_version",
                    title=f"Reword the duty, take {take}",
                    payload={"summaries": {"en": f"The duty, reworded (take {take})."}, "originalLanguage": "en"},
                    field_sources={"summaries.en": "https://www.fi.se/"},
                    target_type="obligation",
                    target_id=self.obligation.id,
                    proposer=logic.Proposer(actor=_actor(proposer), user=proposer),
                )[0]
                for take in (1, 2)
            ]

    def test_two_approvals_on_one_obligation_at_once_add_two_versions(self) -> None:
        first, second = self.proposals
        outcomes = _race(_approval(first.id, self.first), _approval(second.id, self.second))
        self.assertEqual(outcomes, (LANDED, LANDED))
        with transaction.atomic():
            tenancy.clear_tenant()
            applied = {
                version.applied_by_proposal_id: version.version_number
                for version in ObligationVersion.objects.filter(obligation=self.obligation, applied_by_proposal__isnull=False)
            }
            self.assertEqual(applied, {first.id: 2, second.id: 3})
            self.assertEqual(
                set(Proposal.objects.filter(pk__in=[first.id, second.id]).values_list("status", flat=True)),
                {ProposalStatus.APPROVED.value},
            )


class DecidingOutsideARequest(TransactionTestCase):
    """PRO-02: `logic.approve` and `logic.reject` own their transaction, so a caller with no
    request around them, a worker or a shell, gets the whole decision or none of it, and a
    retry after a failure writes the version once.

    A request runs under ATOMIC_REQUESTS, which hid that neither opened a transaction of its
    own. Outside one, `_decidable`'s row lock refused to run at all; inside a caller's own
    transaction that carried on past a failure, an apply that failed part way kept the
    version it had written, and the retry wrote a second one. Proven to fail 2026-09-23
    without the `transaction.atomic()` in `approve`: the call with no transaction raised
    TransactionManagementError at the row lock, every retry included, and the caller that
    carried on was left with versions 2 and 3 for one approval."""

    databases = {DEFAULT_DB_ALIAS}

    def setUp(self) -> None:
        with transaction.atomic():
            _seed()
        with transaction.atomic():
            tenancy.clear_tenant()
            self.obligation = build.obligation(build.instrument(key="shell-instrument", regime="regime:securities"), key="obl-shell")
            filer = agents_testing.agent_key(scopes=(perms.SCOPE_PROPOSALS_WRITE,))
            self.proposal, _ = logic.create(
                kind="new_obligation_version",
                title="Reword the duty",
                payload={"summaries": {"en": "The duty, reworded."}, "originalLanguage": "en"},
                field_sources={"summaries.en": "https://www.fi.se/"},
                target_type="obligation",
                target_id=self.obligation.id,
                proposer=logic.Proposer(actor=_agent_actor(filer), api_key_id=filer.id, agent_id=filer.agent.id),
                agent_run_id=agents_testing.platform_run(key=filer).id,
            )
            confirmer = agents_testing.reviewer_api_key()
            self.review_run = agents_testing.platform_run(key=confirmer)
            self.reviewer = logic.Reviewer(
                actor=_agent_actor(confirmer), api_key_id=confirmer.id, agent_id=confirmer.agent.id, api_key_prefix=confirmer.row.key_prefix
            )

    def _decide(self, verb: str) -> Proposal:
        common: dict[str, Any] = {
            "proposal": logic.by_id(self.proposal.id),
            "reviewer": self.reviewer,
            "actor": self.reviewer.actor,
            "decision": AgentDecision.model_validate(
                agents_testing.DECISION if verb == "approve" else agents_testing.REJECTION_DECISION
            ),
            "agent_run_id": self.review_run.id,
        }
        if verb == "approve":
            return logic.approve(**common, note="", step_up_assertion_id=None)
        return logic.reject(**common, rejection_code="duplicate", note="Version 2 already says this.")

    def _written(self) -> tuple[list[int], str, int, int]:
        """The versions, the proposal's status, its decisions' audit rows and its logged
        model calls, read in a transaction of the test's own."""
        with transaction.atomic():
            tenancy.clear_tenant()
            return (
                sorted(ObligationVersion.objects.filter(obligation=self.obligation).values_list("version_number", flat=True)),
                Proposal.objects.get(pk=self.proposal.id).status,
                AuditEvent.objects.filter(subject_id=self.proposal.id, action__in=DECISIONS).count(),
                AiGeneration.objects.filter(subject_id=self.proposal.id, purpose=AiPurpose.AGENT_REVIEW.value).count(),
            )

    def test_an_approval_that_fails_part_way_writes_nothing_and_a_retry_writes_one_version(self) -> None:
        self.assertFalse(connection.in_atomic_block, "a worker or a shell calls with no transaction open")
        # The search index fails after the version and its summaries are written.
        with mock.patch("apps.proposals.apply.reindex", side_effect=RuntimeError("the search index is down")):
            with self.assertRaises(RuntimeError):
                self._decide("approve")
        self.assertEqual(self._written(), ([1], ProposalStatus.OPEN.value, 0, 0), "nothing of the failed approval was kept")
        self._decide("approve")
        self.assertEqual(self._written(), ([1, 2], ProposalStatus.APPROVED.value, 1, 1), "the retry wrote the version once")

    def test_a_caller_that_carries_on_after_a_failed_approval_keeps_none_of_it(self) -> None:
        """A worker deciding in one transaction of its own, which catches a failure and
        retries: what the failed approval wrote is not kept beside what the retry writes."""
        with transaction.atomic():
            with mock.patch("apps.proposals.apply.reindex", side_effect=RuntimeError("the search index is down")):
                with self.assertRaises(RuntimeError):
                    self._decide("approve")
            self._decide("approve")
        self.assertEqual(self._written(), ([1, 2], ProposalStatus.APPROVED.value, 1, 1), "one approval, one version")

    def test_a_rejection_outside_a_request_lands_whole(self) -> None:
        self.assertFalse(connection.in_atomic_block, "a worker or a shell calls with no transaction open")
        self._decide("reject")
        self.assertEqual(self._written(), ([1], ProposalStatus.REJECTED.value, 1, 1))

    def test_a_decision_whose_audit_row_fails_keeps_no_logged_model_call(self) -> None:
        """AUD-02, D-80: the model call is logged inside the decision's transaction, not
        beside it. The audit row is the decision's last write, so a failure there comes after
        the call was logged; the log row goes with the rest, and the retry logs one. Proven
        to fail 2026-09-23 with the call logged and committed on a connection of its own: both
        failed decisions kept their log rows."""
        logged_before_the_failure: list[int] = []

        def audit_row_fails(**fields: Any) -> None:
            logged_before_the_failure.append(AiGeneration.objects.filter(subject_id=self.proposal.id).count())
            raise RuntimeError("the audit write failed")

        with mock.patch("apps.proposals.logic.record", side_effect=audit_row_fails):
            for verb in ("approve", "reject"):
                with self.subTest(verb=verb), self.assertRaises(RuntimeError):
                    self._decide(verb)
        self.assertEqual(logged_before_the_failure, [1, 1], "each decision had logged its model call when its audit row failed")
        self.assertEqual(self._written(), ([1], ProposalStatus.OPEN.value, 0, 0), "and neither kept it")
        self._decide("approve")
        self.assertEqual(self._written(), ([1, 2], ProposalStatus.APPROVED.value, 1, 1), "the retry logged one")


class DecidingAProposal(ScenarioTestCase):
    def setUp(self) -> None:
        _seed()
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        self.second_editor = factories.platform_user(roles=("library_editor",), email="editor2@bleqq.test")

    def _post(self, path: str, body: dict[str, Any], headers: dict[str, Any]) -> Any:
        return self.client.post(f"{V1}{path}", data=body, content_type="application/json", **headers)

    def _proposed(self, kind: str, title: str, payload: dict[str, Any]) -> str:
        created = self._post("/proposals", {"kind": kind, "title": title, "payload": payload}, sign_in(self.editor))
        self.assertEqual(created.status_code, 201, created.content)
        proposal_id: str = created.json()["id"]
        return proposal_id

    def _assert_untouched(self, proposal_id: str) -> None:
        self.assertEqual(Proposal.objects.get(pk=proposal_id).status, ProposalStatus.OPEN.value)
        self.assertFalse(AuditEvent.objects.filter(subject_id=proposal_id, action__in=DECISIONS).exists())
        self.assertFalse(Flag.objects.filter(key=FLAG["key"]).exists())

    def test_a_person_approving_without_a_step_up_is_refused_and_nothing_applies(self) -> None:
        proposal_id = self._proposed("vocabulary_create", "Add the flag Client money", FLAG)
        refused = self._post(f"/proposals/{proposal_id}/approve", {}, sign_in(self.second_editor))
        self.assertEqual(refused.status_code, 403, refused.content)
        self.assertEqual(refused.json()["code"], "step_up_required")
        self._assert_untouched(proposal_id)

    def test_a_step_up_older_than_the_window_is_refused_and_nothing_applies(self) -> None:
        proposal_id = self._proposed("vocabulary_create", "Add the flag Client money", FLAG)
        headers = sign_in(self.second_editor, step_up=True)
        later = timezone.now() + timedelta(minutes=settings.STEP_UP_FRESHNESS_MINUTES + 1)
        with mock.patch.object(timezone, "now", return_value=later):
            refused = self._post(f"/proposals/{proposal_id}/approve", {}, headers)
        self.assertEqual(refused.status_code, 403, refused.content)
        self.assertEqual(refused.json()["code"], "step_up_required")
        self._assert_untouched(proposal_id)
        # The same assertion inside the window approves: the refusal above was its age.
        approved = self._post(f"/proposals/{proposal_id}/approve", {}, headers)
        self.assertEqual(approved.status_code, 200, approved.content)

    def test_an_independent_agent_approves_every_vocabulary_and_term_kind_and_the_rows_say_a_machine_did(self) -> None:
        """D-79 as lifted on 2026-09-23: every library list row and taxonomy term records who
        confirmed it, so an agent of another definition and key approves every `vocabulary_*`
        and `term_*` kind through the route a person calls. What it writes names the
        confirming agent, never a person, and every label it writes is stored machine-made
        (INV-05, D-62, ADR 0054); the console's queue read names the agent as the decider."""
        tenancy.clear_tenant()  # a platform key is written with no tenant activated (H15)
        proposing = agents_testing.agent_key(scopes=(perms.SCOPE_PROPOSALS_WRITE,))
        proposing_run = str(agents_testing.platform_run(key=proposing).id)
        confirming = agents_testing.reviewer_api_key()
        decided = agents_testing.decision(confirming)
        dimension, key = TERM["dimension"], TERM["key"]
        into = {"list": "flag", "key": "client_assets", "labels": {"en": "Client assets"}}
        kinds: list[tuple[str, dict[str, Any]]] = [
            ("vocabulary_create", FLAG),
            ("vocabulary_create", into),
            ("vocabulary_relabel", {"list": "flag", "key": FLAG["key"], "labels": {"fi": "Asiakasvarat"}}),
            ("vocabulary_retire", {"list": "flag", "key": FLAG["key"]}),
            ("vocabulary_restore", {"list": "flag", "key": FLAG["key"]}),
            ("vocabulary_merge", {"list": "flag", "key": into["key"], "into": FLAG["key"]}),
            ("term_create", TERM),
            ("term_update", {"dimension": dimension, "key": key, "labels": {"sv": "Kryptotillgångar"}}),
        ]
        approved: dict[str, str] = {}
        for kind, payload in kinds:
            with self.subTest(kind=kind, key=payload["key"]):
                filed = self._post(
                    "/proposals",
                    {"kind": kind, "title": f"{kind} {payload['key']}", "payload": payload, "agentRunId": proposing_run},
                    {"HTTP_X_API_KEY": proposing.plain_key},
                )
                self.assertEqual(filed.status_code, 201, filed.content)
                tenancy.clear_tenant()
                answer = self._post(f"/proposals/{filed.json()['id']}/approve", {"note": "Agreed.", **decided}, {"HTTP_X_API_KEY": confirming.plain_key})
                self.assertEqual(answer.status_code, 200, answer.content)
                tenancy.clear_tenant()
                # The console's read of the decision names the agent in the agent's slot and
                # no person at all.
                self.assertEqual(answer.json()["status"], ProposalStatus.APPROVED.value)
                self.assertIsNone(answer.json()["reviewedBy"])
                self.assertEqual(answer.json()["reviewedByAgent"]["key"], confirming.agent.key)
                approved[f"{kind}:{payload['key']}"] = filed.json()["id"]

        confirmed_by_agent = ("agent", confirming.agent.id)
        flag = Flag.objects.get(key=FLAG["key"])
        self.assertTrue(flag.active)
        # The relabel wrote wording, so the stamp names it; the retire, restore and merge
        # after it wrote none and left it.
        self.assertEqual(
            (flag.verified_origin, flag.verified_by_agent_id, str(flag.applied_by_proposal_id)),
            (*confirmed_by_agent, approved["vocabulary_relabel:client_money"]),
        )
        self.assertEqual(
            {label.language: (label.is_original, label.is_machine) for label in flag.labels.all()},
            {"en": (True, True), "sv": (False, True), "fi": (False, True)},
        )
        merged = Flag.objects.get(key=into["key"])
        self.assertFalse(merged.active)
        self.assertEqual((merged.verified_origin, merged.verified_by_agent_id), confirmed_by_agent)
        term = TaxonomyTerm.objects.get(dimension__key=dimension, key=key)
        self.assertEqual(
            (term.verified_origin, term.verified_by_agent_id, str(term.applied_by_proposal_id)),
            (*confirmed_by_agent, approved["term_update:crypto_assets"]),
        )
        self.assertEqual(
            {label.language: (label.is_original, label.is_machine) for label in term.labels.all()},
            {"en": (True, True), "sv": (False, True)},
        )
        # Every decision is the agent's: no person reviewed, the key and agent are named, and
        # the model call behind it is logged in the run it named (AUD-02, D-80).
        rows = Proposal.objects.filter(pk__in=approved.values())
        self.assertEqual(
            set(rows.values_list("status", "reviewed_by_id", "reviewed_by_api_key_id", "reviewed_by_agent_id")),
            {(ProposalStatus.APPROVED.value, None, confirming.id, confirming.agent.id)},
        )
        self.assertEqual(
            sorted(str(subject) for subject in AiGeneration.objects.filter(purpose=AiPurpose.AGENT_REVIEW.value).values_list("subject_id", flat=True)),
            sorted(approved.values()),
        )

    def test_the_same_principal_twice_is_still_refused_on_a_vocabulary_or_term_proposal(self) -> None:
        """Lifting D-79 widened which kinds an agent approves, not who counts as a second
        principal: the key that filed, a second key of its definition, and a row written
        straight past the logic are all refused by four eyes (D-62, ADR 0054)."""
        tenancy.clear_tenant()
        definition = agents_testing.agent()
        both = agents_testing.agent_key(agent_row=definition, scopes=(perms.SCOPE_PROPOSALS_WRITE, perms.SCOPE_PROPOSALS_REVIEW))
        sibling = agents_testing.agent_key(agent_row=definition, scopes=(perms.SCOPE_PROPOSALS_REVIEW,))
        run = str(agents_testing.platform_run(key=both).id)
        for kind, payload in (("vocabulary_create", FLAG), ("term_create", TERM)):
            with self.subTest(kind=kind):
                filed = self._post("/proposals", {"kind": kind, "title": f"Add {payload['key']}", "payload": payload, "agentRunId": run}, {"HTTP_X_API_KEY": both.plain_key})
                self.assertEqual(filed.status_code, 201, filed.content)
                proposal_id = filed.json()["id"]
                for key in (both, sibling):
                    tenancy.clear_tenant()
                    refused = self._post(f"/proposals/{proposal_id}/approve", agents_testing.decision(key), {"HTTP_X_API_KEY": key.plain_key})
                    self.assertEqual(refused.status_code, 409, refused.content)
                    self.assertEqual(refused.json()["code"], "four_eyes_violation")
                tenancy.clear_tenant()
                with self.assertRaises(IntegrityError) as caught, transaction.atomic():
                    Proposal.objects.filter(pk=proposal_id).update(
                        status=ProposalStatus.APPROVED.value, reviewed_by_api_key=sibling.row, reviewed_by_agent=definition, reviewed_at=timezone.now()
                    )
                self.assertIn("proposal_four_eyes", str(caught.exception))
                self._assert_untouched(proposal_id)
        self.assertFalse(TaxonomyTerm.objects.filter(dimension__key=TERM["dimension"], key=TERM["key"]).exists())

    def test_a_kind_whose_record_cannot_name_its_confirming_agent_waits_for_a_person(self) -> None:
        """The rule stays keyed on the kinds that carry machine-confirmed provenance
        (`AGENT_CONFIRMABLE_KINDS`), so a kind added without it is refused to an agent with
        409 `person_review_required`, applies nothing, and a person still approves it. Every
        vocabulary kind carries it, so the proof narrows the set to the obligation kind alone."""
        flag = self._proposed("vocabulary_create", "Add the flag Client money", FLAG)
        tenancy.clear_tenant()
        key = agents_testing.reviewer_api_key()
        with mock.patch.object(logic, "AGENT_CONFIRMABLE_KINDS", logic.OBLIGATION_KINDS):
            refused = self._post(f"/proposals/{flag}/approve", agents_testing.decision(key), {"HTTP_X_API_KEY": key.plain_key})
        self.assertEqual(refused.status_code, 409, refused.content)
        self.assertEqual(refused.json()["code"], "person_review_required")
        self._assert_untouched(flag)
        self.assertFalse(AiGeneration.objects.filter(subject_id=flag).exists(), "a refused decision logs no model call")
        approved = self._post(f"/proposals/{flag}/approve", {}, sign_in(self.second_editor, step_up=True))
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertTrue(Flag.objects.filter(key=FLAG["key"]).exists())
