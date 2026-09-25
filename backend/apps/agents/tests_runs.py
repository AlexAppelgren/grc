"""Opening, closing and reading an agent run (AGT-01, AGT-02, ID-10, AUD-01).

This is where an agent's work first reaches a bank, so what is proved here is mostly what
a run may *not* do:

- only a platform key opens one. bleqq's watch agents are part of the base package
  (Alex's item 14), so a tenant-bound key is refused with the reason named and a tenant's
  session never reaches the logic at all: the route takes an API key alone;
- a key runs the agent it is bound to and no other, and it acts only on its own run;
  another key's run answers 404, so no run id can be probed for;
- a retry replays. The same `Idempotency-Key` returns the run it already opened, and a
  close repeated with the same values returns the run it already closed, so a lost answer
  never becomes a second run or a reopened one;
- every open and close writes its audit row and its outbox row in the same transaction,
  with the agent behind the key as the actor and not the key's id;
- a tenant reads its own runs, never the library's (ADR 0053) and never another bank's.

The requests carry a real key (`X-API-Key`), never a stubbed principal, so the resolver,
row-level security and the mixed write rule all run exactly as they do in production.

Proven to fail 2026-09-21 against the declared contract: every test below answered 501
`not_built` before `runs.py` was written.
"""

from __future__ import annotations

import datetime
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.core.exceptions import ValidationError
from django.db import DEFAULT_DB_ALIAS, connection, connections, transaction
from django.test import TestCase, TransactionTestCase

from apps.agents import runs, testing as agent_build
from apps.agents.models import AgentRun, RunStatus
from apps.agents.schemas import AgentRunFinish, AgentRunInput
from apps.identity.api_keys_logic import resolve_api_key
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.errors import ProblemError
from apps.shared.models import AuditEvent, OutboxEvent
from apps.shared.testing import (
    LANDED,
    RACE_WAIT_SECONDS,
    ScenarioTestCase,
    backend_pid,
    hold_until_waiting_on_me,
    stub_session,
    user_principal,
)
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions

RUNS = "/api/v1/agent-runs"
JSON = "application/json"

STATS = {"modelCalls": 42, "fetches": 118, "sourcesChecked": 31, "changesRegistered": 2, "proposalsSubmitted": 5, "outOfScope": 3, "recordsRechecked": 12, "correctionsProposed": 1}
# Two fixed nights rather than "now", so a fixture cannot drift as the clock moves.
FIRST_SWEEP = datetime.datetime(2026, 9, 19, 2, 0, tzinfo=datetime.UTC)
SECOND_SWEEP = datetime.datetime(2026, 9, 20, 2, 0, tzinfo=datetime.UTC)


def open_body(agent_key: str) -> dict[str, Any]:
    """One night's sweep by the shipped definition, as the prototype's data reads it."""
    return {"agent": agent_key, "model": "regwatch-2026-08", "pipelineVersion": "watch-1.4.2"}


class AgentRunCase(ScenarioTestCase):
    """A platform agent, a key bound to it, and the reference rows every agent test needs."""

    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        # A platform key's own session carries no tenant: the mixed write rule accepts a
        # library row only from a session in the library's zone (hardening H15).
        tenancy.clear_tenant()
        self.key = agent_build.agent_key()
        self.agent = self.key.agent

    def as_key(self, plain: str | None = None) -> dict[str, Any]:
        return {"HTTP_X_API_KEY": plain or self.key.plain_key}

    def post(self, body: dict[str, Any], *, plain: str | None = None, retry: str | None = None) -> Any:
        headers = self.as_key(plain)
        if retry is not None:
            headers["HTTP_IDEMPOTENCY_KEY"] = retry
        return self.client.post(RUNS, data=body, content_type=JSON, **headers)

    def patch(self, run_id: Any, body: dict[str, Any], *, plain: str | None = None) -> Any:
        return self.client.patch(f"{RUNS}/{run_id}", data=body, content_type=JSON, **self.as_key(plain))

    def opened(self) -> Any:
        response = self.post(open_body(self.agent.key))
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()


class OpeningARun(AgentRunCase):
    def test_a_platform_key_opens_a_run_that_belongs_to_no_bank(self) -> None:
        body = self.opened()
        self.assertEqual(body["agent"], self.agent.key)
        self.assertEqual(body["status"], "running")
        self.assertEqual(body["model"], "regwatch-2026-08")
        self.assertEqual(body["pipelineVersion"], "watch-1.4.2")
        self.assertIsNone(body["finishedAt"])
        self.assertIsNone(body["error"])
        self.assertIsNone(body["outputRef"])
        self.assertEqual(body["stats"]["changesRegistered"], 0, "an open run has counted nothing yet")
        run = AgentRun.objects.get(pk=body["id"])
        self.assertIsNone(run.tenant_id, "in R1 every run is a platform run (item 14)")
        self.assertEqual(run.api_key_id, self.key.id)

    def test_opening_writes_its_audit_row_and_its_outbox_row_naming_the_agent(self) -> None:
        body = self.opened()
        event = AuditEvent.objects.get(action="agent_run.opened", subject_id=body["id"])
        self.assertEqual(event.actor_type, "agent")
        self.assertEqual(event.actor_id, self.agent.id, "the agent behind the key, never the key's id")
        self.assertEqual(event.actor_label, self.agent.key)
        self.assertIsNone(event.tenant_id)
        self.assertEqual(event.after["model"], "regwatch-2026-08")
        self.assertTrue(OutboxEvent.objects.filter(audit_event=event, topic="agent_run.opened").exists())

    def test_a_retry_with_the_same_key_answers_the_run_it_already_opened(self) -> None:
        first = self.post(open_body(self.agent.key), retry="sweep-2026-09-20")
        self.assertEqual(first.status_code, 201, first.content)
        second = self.post(open_body(self.agent.key), retry="sweep-2026-09-20")
        self.assertEqual(second.status_code, 201, second.content)
        self.assertEqual(second.json()["id"], first.json()["id"])
        self.assertEqual(AgentRun.objects.count(), 1, "a retry replays; it never opens a second run")

    def test_the_same_key_with_a_different_body_is_a_conflict(self) -> None:
        self.post(open_body(self.agent.key), retry="sweep-2026-09-20")
        changed = open_body(self.agent.key) | {"model": "regwatch-2026-09"}
        response = self.post(changed, retry="sweep-2026-09-20")
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["code"], "idempotency_conflict")
        self.assertEqual(AgentRun.objects.count(), 1)

    def test_a_tenant_bound_key_is_refused_with_the_reason_named(self) -> None:
        """Item 14: bleqq's agents are platform-owned, so a bank's key opens no run in R1.
        A bank's key never holds `agent-runs:write` (D-61, PLATFORM_ONLY_SCOPES): one that
        was given it before that rule has it withheld, and the route names the reason before
        it reads the scopes. The logic refuses on its own too, for a principal that somehow
        carries the scope."""
        tenant = factories.tenant(slug="opens-nothing")
        tenancy.clear_tenant()
        bank = agent_build.tenant_key(tenant, scopes=(perms.SCOPE_AGENT_RUNS_WRITE,))
        response = self.post(open_body(self.agent.key), plain=bank.plain_key)
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.json()["code"], "tenant_agents_not_available")
        carrying = Principal(
            kind=PrincipalKind.AGENT, subject_id=bank.id, tenant_id=tenant.id, scopes=frozenset({perms.SCOPE_AGENT_RUNS_WRITE})
        )
        with self.assertRaises(ProblemError) as refused:
            runs.open_run(who=carrying, body=AgentRunInput.model_validate(open_body(self.agent.key)), idempotency_key=None)
        self.assertEqual(refused.exception.code, "tenant_agents_not_available")
        self.assertEqual(AgentRun.objects.count(), 0, "a refusal writes nothing")

    def test_a_tenant_session_never_reaches_the_logic(self) -> None:
        """The route takes an API key alone, so a person's session — tenant or platform —
        is refused before any logic runs (`c5-contract-api-agent`, tests_contract.py)."""
        principal = user_principal(permissions=perms.ALL_PERMISSIONS, tenant_id=uuid.uuid4())
        with stub_session(principal):
            response = self.client.post(
                RUNS,
                data=open_body(self.agent.key),
                content_type=JSON,
                HTTP_AUTHORIZATION="Bearer test-session-token",
            )
        self.assertEqual(response.status_code, 401, response.content)
        self.assertEqual(AgentRun.objects.count(), 0)

    def test_a_key_runs_only_the_agent_it_is_bound_to(self) -> None:
        """A key is bound to exactly one definition, so a name that belongs to another key
        and a name this build never shipped are deliberately the same refusal: trying names
        tells a caller nothing about which definitions exist."""
        for wanted in (agent_build.agent().key, "nordic-watch-that-never-shipped"):
            with self.subTest(agent=wanted):
                response = self.post(open_body(wanted))
                self.assertEqual(response.status_code, 403, response.content)
                self.assertEqual(response.json()["code"], "permission_denied")
        self.assertEqual(AgentRun.objects.count(), 0)


class ClosingARun(AgentRunCase):
    def setUp(self) -> None:
        super().setUp()
        self.run_id = self.opened()["id"]

    def test_a_run_closes_with_its_counters_and_where_its_output_went(self) -> None:
        body = {
            "status": "succeeded",
            "stats": STATS,
            "outputRef": "runs/2026-09-20/watch-sweeper/5f1c2a80.jsonl",
            "error": None,
        }
        response = self.patch(self.run_id, body)
        self.assertEqual(response.status_code, 200, response.content)
        closed = response.json()
        self.assertEqual(closed["status"], "succeeded")
        self.assertIsNotNone(closed["finishedAt"])
        # What the server can count it counts (H41): this run filed nothing, whatever it
        # says; the rest is the run's own account (`tests_budgets.py`).
        counted = {"sourcesChecked": 0, "changesRegistered": 0, "proposalsSubmitted": 0, "recordsRechecked": 0}
        self.assertEqual(closed["stats"], {**STATS, **counted})
        self.assertEqual(closed["outputRef"], "runs/2026-09-20/watch-sweeper/5f1c2a80.jsonl")
        self.assertIsNone(closed["error"])

    def test_closing_writes_its_audit_row_naming_the_agent(self) -> None:
        self.patch(self.run_id, {"status": "failed", "error": "The source refused the fetch."})
        event = AuditEvent.objects.get(action="agent_run.closed", subject_id=self.run_id)
        self.assertEqual(event.actor_id, self.agent.id)
        self.assertEqual(event.after["status"], "failed")
        self.assertTrue(OutboxEvent.objects.filter(audit_event=event, topic="agent_run.closed").exists())

    def test_the_same_close_repeated_answers_the_run_it_already_closed(self) -> None:
        first = self.patch(self.run_id, {"status": "succeeded", "stats": STATS})
        self.assertEqual(first.status_code, 200, first.content)
        second = self.patch(self.run_id, {"status": "succeeded", "stats": STATS})
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(second.json(), first.json(), "a retried close replays; it never moves the row")

    def test_closing_a_closed_run_into_something_else_is_refused(self) -> None:
        self.patch(self.run_id, {"status": "succeeded", "stats": STATS})
        response = self.patch(self.run_id, {"status": "failed", "error": "second thoughts"})
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["code"], "invalid_transition")
        self.assertEqual(AgentRun.objects.get(pk=self.run_id).status, RunStatus.SUCCEEDED.value)

    def test_another_keys_run_answers_not_found(self) -> None:
        stranger = agent_build.agent_key()
        response = self.patch(self.run_id, {"status": "succeeded"}, plain=stranger.plain_key)
        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(response.json()["code"], "not_found")
        self.assertEqual(AgentRun.objects.get(pk=self.run_id).status, RunStatus.RUNNING.value)

    def test_a_run_that_does_not_exist_answers_not_found(self) -> None:
        response = self.patch(uuid.uuid4(), {"status": "succeeded"})
        self.assertEqual(response.status_code, 404, response.content)


class TheProvenanceAnchor(AgentRunCase):
    """`regulatory_change.agent_run_id` and `source_check.agent_run_id` point at a run, so
    the writers of chunk 5 ask this guard before they file anything against one."""

    def principal(self, plain: str | None = None) -> Principal:
        with transaction.atomic():
            resolved = resolve_api_key(plain or self.key.plain_key)
        assert resolved is not None
        return resolved

    def test_an_open_run_of_this_key_resolves(self) -> None:
        run_id = self.opened()["id"]
        with transaction.atomic():
            run = runs.require_open_run(self.principal(), uuid.UUID(run_id))
        self.assertEqual(str(run.id), run_id)

    def test_a_closed_run_refuses_the_write_that_names_it(self) -> None:
        run_id = self.opened()["id"]
        self.patch(run_id, {"status": "succeeded"})
        with self.assertRaises(ValidationError) as caught:
            with transaction.atomic():
                runs.require_open_run(self.principal(), uuid.UUID(run_id))
        self.assertEqual(caught.exception.code, "run_not_open")

    def test_a_run_of_another_key_is_not_found_rather_than_closed(self) -> None:
        """404 and never 422: which run ids exist is not something a key may probe for."""
        stranger = agent_build.agent_key()
        other_principal = self.principal(stranger.plain_key)
        run_id = self.opened()["id"]
        with self.assertRaises(ProblemError) as caught:
            with transaction.atomic():
                runs.require_open_run(other_principal, uuid.UUID(run_id))
        self.assertEqual(caught.exception.status, 404)


class ReadingTheRunLog(TestCase):
    """A bank reads its own runs and no library run (ADR 0053); the console reads the library's."""

    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        self.tenant = factories.tenant(slug="reads-runs")
        self.other = factories.tenant(slug="reads-nothing")
        tenancy.clear_tenant()
        self.platform_run = agent_build.platform_run()

    def read(self, principal: Any, query: str = "") -> Any:
        with stub_session(principal):
            return self.client.get(f"{RUNS}{query}", HTTP_AUTHORIZATION="Bearer test-session-token")

    def test_a_bank_sees_no_library_run(self) -> None:
        response = self.read(user_principal(permissions={perms.AGENTS_MANAGE}, tenant_id=self.tenant.id))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {"items": [], "total": 0})

    def test_the_console_reads_them_with_system_health(self) -> None:
        response = self.read(user_principal(permissions={perms.SYSTEM_HEALTH}))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["total"], 1)

    def test_another_banks_run_is_invisible(self) -> None:
        with transaction.atomic():
            tenancy.activate(self.other.id)
            bank_key = agent_build.tenant_key(self.other, scopes=(perms.SCOPE_AGENT_RUNS_WRITE,))
            AgentRun.objects.create(
                agent=self.platform_run.agent, api_key=bank_key.row, model="own", pipeline_version="1"
            )
        response = self.read(user_principal(permissions={perms.AGENTS_MANAGE}, tenant_id=self.tenant.id))
        ids = [item["id"] for item in response.json()["items"]]
        self.assertEqual(ids, [], "a bank never reads another bank's run")

    def test_the_page_is_ordered_and_bounded(self) -> None:
        tenancy.clear_tenant()
        later = agent_build.platform_run()
        # `started_at` is set by the database clock, and two runs opened inside one test are
        # microseconds apart — on Windows often the same tick. Anchoring both is what makes
        # this an assertion about the order the contract promises rather than about a race.
        AgentRun.objects.filter(pk=self.platform_run.pk).update(started_at=FIRST_SWEEP)
        AgentRun.objects.filter(pk=later.pk).update(started_at=SECOND_SWEEP)
        principal = user_principal(permissions={perms.SYSTEM_HEALTH})
        first_page = self.read(principal, "?limit=1").json()
        self.assertEqual(first_page["total"], 2, "total counts what the caller may see, not the page")
        self.assertEqual(first_page["items"][0]["id"], str(self.platform_run.id))
        second_page = self.read(principal, "?limit=1&offset=1").json()
        self.assertEqual(second_page["items"][0]["id"], str(later.id))

    def test_a_page_size_above_the_maximum_is_refused(self) -> None:
        response = self.read(user_principal(permissions={perms.SYSTEM_HEALTH}), "?limit=1000")
        self.assertEqual(response.status_code, 422, response.content)

    def test_nothing_has_run_yet_is_a_200_with_an_empty_list(self) -> None:
        AgentRun.objects.all().delete()
        response = self.read(user_principal(permissions={perms.SYSTEM_HEALTH}))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {"items": [], "total": 0})


def _app_session(work: Callable[[], object]) -> str:
    """Run `work` in one transaction on a fresh cw_app connection of this thread's own, in
    the platform's zone as a key's request is. Answers "landed" when it committed, or the
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
    """`first` acts and keeps its transaction open until `second` waits on it; a second
    session that never waited fails the race, because it was never serialized."""
    acted = threading.Event()
    second_pid: list[int] = []

    def lead() -> None:
        first()
        acted.set()
        hold_until_waiting_on_me(second_pid)

    def follow() -> None:
        second_pid.append(backend_pid())
        if not acted.wait(RACE_WAIT_SECONDS):
            raise AssertionError("the first session never acted")
        second()

    with ThreadPoolExecutor(max_workers=2) as pool:
        leading = pool.submit(_app_session, lead)
        following = pool.submit(_app_session, follow)
        return leading.result(), following.result()


class ARunLocksOnWrite(TransactionTestCase):
    """H36: a filing and a close of the same run are serialized on the run's row, so a
    filing never lands in a run another request is closing and the close counts it, and
    two closes never both land."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        with transaction.atomic():
            tenancy.clear_tenant()
            self.key = agent_build.agent_key()
            who = resolve_api_key(self.key.plain_key)
            assert who is not None
            self.who: Principal = who
            body = AgentRunInput.model_validate(open_body(self.key.agent.key))
            self.run_id = runs.open_run(who=self.who, body=body, idempotency_key=None).id

    def _file(self) -> None:
        runs.require_open_run(self.who, self.run_id)

    def _close(self, status: str) -> Callable[[], object]:
        return lambda: runs.finish_run(who=self.who, run_id=self.run_id, body=AgentRunFinish.model_validate({"status": status}))

    def _stored_status(self) -> str:
        with transaction.atomic():
            tenancy.clear_tenant()
            return AgentRun.objects.get(pk=self.run_id).status

    def test_a_close_waits_for_a_filing_in_flight(self) -> None:
        self.assertEqual(_race(self._file, self._close("succeeded")), (LANDED, LANDED))
        self.assertEqual(self._stored_status(), RunStatus.SUCCEEDED.value)

    def test_a_filing_that_waited_on_a_close_reads_the_run_closed(self) -> None:
        self.assertEqual(_race(self._close("succeeded"), self._file), (LANDED, "run_not_open"))

    def test_two_different_closes_at_once_land_one(self) -> None:
        self.assertEqual(_race(self._close("succeeded"), self._close("failed")), (LANDED, "invalid_transition"))
        self.assertEqual(self._stored_status(), RunStatus.SUCCEEDED.value)
        with transaction.atomic():
            tenancy.clear_tenant()
            self.assertEqual(AuditEvent.objects.filter(subject_id=self.run_id, action="agent_run.closed").count(), 1)
