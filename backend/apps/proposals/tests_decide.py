"""Deciding a proposal (PRO-02, AC-PRO1, AC-PRO2): the row lock that lets one
decision land, and the person's fresh passkey on approval.

The races run two sessions at once, each on its own cw_app connection in its own thread and
transaction, the way two requests reach production (the pattern of
apps/taxonomy/tests_footprint.py). The first session decides and holds its transaction open
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

from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.proposals import logic
from apps.proposals.models import Proposal, ProposalStatus
from apps.shared import factories, tenancy
from apps.shared.audit import Actor, ActorType
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import Flag
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions
from apps.taxonomy.tests_footprint import LANDED, WAIT_SECONDS, _backend_pid, _hold_until_waiting_on_me

V1 = "/api/v1"
DECISIONS = ("proposal.approved", "proposal.rejected")
FLAG = {"list": "flag", "key": "client_money", "labels": {"en": "Client money", "sv": "Kundmedel"}}


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
        # What the route does: an unlocked read by id, then the decision.
        return lambda: logic.approve(
            proposal=logic.by_id(self.proposal.id),
            reviewer=reviewer,
            actor=_actor(reviewer),
            note="",
            step_up_assertion_id=uuid.uuid4(),
        )

    def _reject(self, reviewer: Any) -> Callable[[], object]:
        return lambda: logic.reject(
            proposal=logic.by_id(self.proposal.id),
            reviewer=reviewer,
            actor=_actor(reviewer),
            rejection_code="duplicate",
            note="We have this already.",
        )

    def _race(self, first: Callable[[], object], second: Callable[[], object]) -> tuple[str, str]:
        """`first` decides and keeps its transaction open until `second` waits on it."""
        acted = threading.Event()
        second_pid: list[int] = []

        def lead() -> None:
            first()
            acted.set()
            _hold_until_waiting_on_me(second_pid)

        def follow() -> None:
            second_pid.append(_backend_pid())
            if not acted.wait(WAIT_SECONDS):
                raise AssertionError("the first session never decided")
            second()

        with ThreadPoolExecutor(max_workers=2) as pool:
            leading = pool.submit(_platform_session, lead)
            following = pool.submit(_platform_session, follow)
            return leading.result(), following.result()

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
        outcomes = self._race(self._approve(self.first), self._reject(self.second))
        self.assertEqual(outcomes, (LANDED, "invalid_transition"))
        self._assert_approved_once()

    def test_two_approvals_at_once_apply_once(self) -> None:
        outcomes = self._race(self._approve(self.first), self._approve(self.second))
        self.assertEqual(outcomes, (LANDED, "invalid_transition"))
        self._assert_approved_once()


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
