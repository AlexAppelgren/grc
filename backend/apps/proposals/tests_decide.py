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
from django.db import DEFAULT_DB_ALIAS, connection, connections, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from apps.agents import testing as agents_testing
from apps.library import testing as build
from apps.library.models import ObligationVersion
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.proposals import logic
from apps.proposals.models import Proposal, ProposalStatus
from apps.shared import factories, tenancy
from apps.shared.audit import Actor, ActorType
from apps.shared.models import AuditEvent
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

    def test_an_agent_cannot_approve_a_vocabulary_or_term_proposal_which_waits_for_a_person(self) -> None:
        """D-79: an agent approves obligation versions only until the owner opens the list
        and term kinds to it. The rows now record who confirmed them (taxonomy 0007,
        apps/proposals/tests_provenance.py), but that decision is not taken: an agent's
        approval is refused with its own code, applies nothing, and the proposal waits for a
        person."""
        flag = self._proposed("vocabulary_create", "Add the flag Client money", FLAG)
        term = self._proposed("term_create", "Add the regime Crypto-assets", TERM)
        tenancy.clear_tenant()  # a platform key is written with no tenant activated (H15)
        reviewer = {"HTTP_X_API_KEY": agents_testing.reviewer_api_key().plain_key}
        for proposal_id in (flag, term):
            with self.subTest(proposal=proposal_id):
                refused = self._post(f"/proposals/{proposal_id}/approve", {}, reviewer)
                self.assertEqual(refused.status_code, 409, refused.content)
                self.assertEqual(refused.json()["code"], "person_review_required")
        self._assert_untouched(flag)
        self._assert_untouched(term)
        self.assertFalse(TaxonomyTerm.objects.filter(dimension__key=TERM["dimension"], key=TERM["key"]).exists())
        # An agent may still reject one: a rejection writes no library row.
        rejected = self._post(f"/proposals/{term}/reject", {"rejectionCode": "duplicate", "note": "Covered by an existing regime."}, reviewer)
        self.assertEqual(rejected.status_code, 200, rejected.content)
        # A person approves the other, as before.
        approved = self._post(f"/proposals/{flag}/approve", {}, sign_in(self.second_editor, step_up=True))
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertTrue(Flag.objects.filter(key=FLAG["key"]).exists())
