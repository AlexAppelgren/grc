"""A correction and a confirmation of one change's type at the same moment (WAT-03, D-74).

Both writes read what is confirmed and then act on it, so each takes the change's row lock
first (`keys.change_for_update`). Without it, each read a stale row: a key's correction
that read the type as a suggestion went on to overwrite a confirmation that landed while it
waited, clearing the confirmer's columns, and a confirmation that read the old type put a
machine's confirmation on a type nobody had checked. Two real sessions on the app role
prove the lock, the first holding its transaction open until the second waits on it
(apps/proposals/tests_decide.py races proposals the same way).

Proven red 2026-09-24 with `change_for_update` reading without `select_for_update`: both
races landed twice.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.core.exceptions import ValidationError
from django.db import DEFAULT_DB_ALIAS, connections, transaction
from django.test import TransactionTestCase

from apps.agents import testing as agent_build
from apps.shared import permissions as perms, tenancy
from apps.shared.audit import Actor, ActorType
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.testing import LANDED, RACE_WAIT_SECONDS, backend_pid, hold_until_waiting_on_me
from apps.watch import curation, testing as watch_build
from apps.watch.models import RegulatoryChange
from apps.watch.schemas import WatchChangePatch, WatchCurationConfirmInput

DECISION: dict[str, Any] = {
    "model": "claude-opus-5",
    "modelVersion": "2026-05-01",
    "output": "Confirm. The memorandum adopts the rule.",
    "citations": [{"label": "Finansinspektionen, decision memorandum", "url": "https://www.fi.se/en/published/news/2026/reporting/"}],
}


def _platform_session(work: Callable[[], object]) -> str:
    """Run `work` in one transaction on a fresh cw_app connection of this thread's own, in
    the platform's zone as a key's request is. Answers "landed" when it committed, or the
    refusal's code."""
    connections[DEFAULT_DB_ALIAS] = connections.create_connection("app")
    try:
        with transaction.atomic():
            tenancy.clear_tenant()
            work()
        return LANDED
    except ValidationError as refusal:
        return str(refusal.code)
    finally:
        connections[DEFAULT_DB_ALIAS].close()


def _race(first: Callable[[], object], second: Callable[[], object]) -> tuple[str, str]:
    """`first` writes and keeps its transaction open until `second` waits on it."""
    acted = threading.Event()
    second_pid: list[int] = []

    def lead() -> None:
        first()
        acted.set()
        hold_until_waiting_on_me(second_pid)

    def follow() -> None:
        second_pid.append(backend_pid())
        if not acted.wait(RACE_WAIT_SECONDS):
            raise AssertionError("the first session never wrote")
        second()

    with ThreadPoolExecutor(max_workers=2) as pool:
        leading = pool.submit(_platform_session, lead)
        following = pool.submit(_platform_session, follow)
        return leading.result(), following.result()


def _key(key: Any, scopes: set[str]) -> tuple[Principal, Actor]:
    """The principal and the audit actor a request from this agent-bound key carries."""
    who = Principal(
        kind=PrincipalKind.AGENT, subject_id=key.id, scopes=frozenset(scopes), agent_id=key.agent.id, agent_label=key.agent.key
    )
    return who, Actor(kind=ActorType.AGENT, id=key.agent.id, label=key.agent.key)


class TypeCurationRaces(TransactionTestCase):
    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        with transaction.atomic():
            tenancy.clear_tenant()
            watch_build.seed_watch_reference()
            sweeper = agent_build.agent_key()
            self.change = watch_build.change_with_timeline(run=agent_build.platform_run(key=sweeper))
            confirmer = agent_build.agent_key(
                agent_row=agent_build.agent(key="library-confirmer"), scopes=("agent-runs:write", perms.SCOPE_PROPOSALS_REVIEW)
            )
            self.review = agent_build.platform_run(key=confirmer)
        self.sweeper = _key(sweeper, {perms.SCOPE_CHANGES_WRITE})
        self.confirmer = _key(confirmer, {perms.SCOPE_PROPOSALS_REVIEW})

    def _correct_type(self) -> Callable[[], object]:
        who, actor = self.sweeper
        return lambda: curation.update_change_facts(
            who=who, actor=actor, order=["en"], change_id=self.change.id, body=WatchChangePatch(change_type="proposal"), step_up_assertion_id=None
        )

    def _confirm_type(self) -> Callable[[], object]:
        who, actor = self.confirmer
        body = WatchCurationConfirmInput.model_validate({"changeType": "adopted", "decision": DECISION, "agentRunId": str(self.review.id)})
        return lambda: curation.confirm_curation(
            who=who, actor=actor, order=["en"], change_id=self.change.id, body=body, step_up_assertion_id=None
        )

    def _stored(self) -> RegulatoryChange:
        with transaction.atomic():
            tenancy.clear_tenant()
            return RegulatoryChange.objects.select_related("change_type").get(pk=self.change.pk)

    def test_a_key_correcting_the_type_while_it_is_confirmed_leaves_the_confirmation(self) -> None:
        outcomes = _race(self._confirm_type(), self._correct_type())
        self.assertEqual(outcomes, (LANDED, "confirmed_fact"))
        stored = self._stored()
        self.assertEqual((stored.change_type.key, stored.change_type_suggested), ("adopted", False))
        self.assertIsNotNone(stored.change_type_confirmed_by_agent_id, "the machine's confirmation stands")

    def test_a_type_corrected_while_it_is_confirmed_is_not_confirmed_unread(self) -> None:
        outcomes = _race(self._correct_type(), self._confirm_type())
        self.assertEqual(outcomes, (LANDED, "validation_error"))
        stored = self._stored()
        self.assertEqual((stored.change_type.key, stored.change_type_suggested), ("proposal", True))
        self.assertIsNone(stored.change_type_confirmed_at, "nobody checked the corrected type")
