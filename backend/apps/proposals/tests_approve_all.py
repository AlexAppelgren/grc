"""Approve all, run by the worker (apps/proposals/approve_all.py; PRO-02, D-128).

One step-up names the filters; the worker approves what was waiting then, each through
`logic.approve` with its own audit rows under that assertion, and leaves the reviewer's own.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.proposals import approve_all
from apps.proposals.models import Proposal, ProposalStatus
from apps.proposals.tests_decide import V1, _seed
from apps.shared import factories
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in

ROUTE = f"{V1}/proposals/approve-all"


class ApprovingAll(ScenarioTestCase):
    def setUp(self) -> None:
        _seed()
        cache.clear()
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")
        self.reviewer = factories.platform_user(roles=("library_editor",), email="editor2@bleqq.test")
        self.theirs = [self._proposed(self.editor, f"client_money_{n}") for n in range(3)]
        self.mine = self._proposed(self.reviewer, "client_assets")

    def _proposed(self, user: Any, key: str) -> str:
        body = {"kind": "vocabulary_create", "title": f"Add the flag {key}", "payload": {"list": "flag", "key": key, "labels": {"en": key}}}
        created = self.client.post(f"{V1}/proposals", data=body, content_type="application/json", **sign_in(user))
        self.assertEqual(created.status_code, 201, created.content)
        proposal_id: str = created.json()["id"]
        return proposal_id

    def _start(self, body: dict[str, Any] | None = None, step_up: bool = True) -> Any:
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(ROUTE, data=body or {}, content_type="application/json", **sign_in(self.reviewer, step_up=step_up))

    def _status(self, proposal_id: str) -> str:
        return Proposal.objects.get(pk=proposal_id).status

    def test_one_step_up_approves_everything_waiting_but_the_reviewers_own(self) -> None:
        started = self._start()
        self.assertEqual(started.status_code, 202, started.content)
        self.assertEqual((started.json()["status"], started.json()["total"]), ("running", 3))
        read = self.client.get(ROUTE, **sign_in(self.reviewer)).json()
        self.assertEqual((read["status"], read["total"], read["approved"], read["refused"]), ("finished", 3, 3, 0))
        self.assertEqual({self._status(pk) for pk in self.theirs}, {ProposalStatus.APPROVED.value})
        self.assertEqual(self._status(self.mine), ProposalStatus.OPEN.value)
        # Every approval wrote its own audit row, under the one assertion the decision gave.
        decision = AuditEvent.objects.get(action="proposal.approve_all_started")
        self.assertIsNotNone(decision.step_up_assertion_id)
        approvals = AuditEvent.objects.filter(action="proposal.approved", subject_id__in=self.theirs)
        self.assertEqual({row.step_up_assertion_id for row in approvals}, {decision.step_up_assertion_id})
        self.assertEqual(approvals.count(), 3)

    def test_it_needs_a_fresh_passkey_and_approves_nothing_without_one(self) -> None:
        refused = self._start(step_up=False)
        self.assertEqual(refused.status_code, 403, refused.content)
        self.assertEqual(refused.json()["code"], "step_up_required")
        self.assertEqual({self._status(pk) for pk in self.theirs}, {ProposalStatus.OPEN.value})
        self.assertEqual(self.client.get(ROUTE, **sign_in(self.reviewer)).json()["status"], "idle")

    def test_the_filters_narrow_what_it_approves(self) -> None:
        started = self._start({"kind": "new_obligation"})
        self.assertEqual(started.json(), {**started.json(), "status": "finished", "total": 0})
        self.assertEqual({self._status(pk) for pk in self.theirs}, {ProposalStatus.OPEN.value})
        self.assertEqual(self._start({"origin": "robot"}).json()["code"], "unknown_key")

    def test_a_row_decided_meanwhile_is_counted_with_its_reason_and_the_rest_go_on(self) -> None:
        Proposal.objects.filter(pk=self.theirs[0]).update(status=ProposalStatus.REJECTED.value)
        state = approve_all.approve_listed(user=self.reviewer, proposal_ids=self.theirs, step_up_assertion_id=uuid.uuid4())
        self.assertEqual((state["status"], state["approved"], state["refused"]), ("finished", 2, 1))
        self.assertEqual(state["refusals"][0]["id"], self.theirs[0])
        self.assertEqual(state["refusals"][0]["code"], "invalid_transition")

    def test_a_second_start_waits_for_a_running_run_unless_its_worker_went_quiet(self) -> None:
        running = {**approve_all.idle(), "status": "running", "total": 5}
        approve_all._save(self.reviewer.id, running)
        refused = self._start()
        self.assertEqual(refused.status_code, 409, refused.content)
        self.assertEqual(refused.json()["code"], "approval_running")
        # Nothing heard from its worker for longer than the setting: it stopped, so a new start runs.
        quiet = (timezone.now() - timedelta(seconds=settings.PROPOSALS_APPROVE_ALL_STALE_S + 1)).isoformat()
        cache.set(approve_all._key(self.reviewer.id), {**running, "updatedAt": quiet})
        self.assertEqual(self._start().status_code, 202)
