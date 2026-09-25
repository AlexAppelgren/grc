"""What bleqq watches, as a bank reads it (AGT-03, AGT-04, ruling 6): `GET /agents/platform`.

A bank cannot change bleqq's watch, so it must at least be able to see what it covers:
each active platform agent's key, name, purpose, jurisdictions, cadence, when it next runs
and how its last run ended. Nothing else: no prompt, tool, model, version, budget, cost,
finding or setting, and no bank's row feeds the answer. Every member reads it, because
every system role holds `watch.read`.

Proven to fail 2026-09-25 against the contract: the route answered 501 `not_built`.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any
from unittest import mock

from django.test import TestCase

from apps.agents import testing as agent_build
from apps.agents.models import Agent, AgentCadence, AgentKind, AgentRun, AgentScopeKind, AgentVersion, AgentWritesTo, RunStatus
from apps.agents.schemas import PlatformWatchItem, PlatformWatchLastRun
from apps.identity.models import User
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.models import Tenant
from apps.shared.tenancy import library_write
from apps.shared.testing import sign_in

WATCH = "/api/v1/agents/platform"
# The clock the answer is computed against, frozen so `nextRunAt` is an assertion about the
# cadence and never about when the suite ran.
NOW = datetime.datetime(2026, 9, 25, 9, 0, tzinfo=datetime.UTC)
SWEPT = NOW - datetime.timedelta(hours=7)


def _agent(key: str, *, cadence: AgentCadence = AgentCadence.DAILY, active: bool = True, **fields: Any) -> Agent:
    with library_write("test"):
        return Agent.objects.create(
            key=key,
            kind=fields.pop("kind", AgentKind.WATCH.value),
            description=f"What {key} watches for.",
            active=active,
            current_version=1,
            default_cadence=cadence.value,
            **fields,
        )


def _closed(run: AgentRun, *, started_at: datetime.datetime, status: RunStatus, finished: bool = True) -> AgentRun:
    AgentRun.objects.filter(pk=run.pk).update(
        started_at=started_at,
        status=status.value,
        finished_at=started_at + datetime.timedelta(minutes=18) if finished else None,
        cost=Decimal("40.0000"),
        tokens_in=900_000,
    )
    run.refresh_from_db()
    return run


class WhatBleqqWatches(TestCase):
    bank: Tenant
    other: Tenant
    reader: User
    sweeper: Agent
    confirmer: Agent
    manual: Agent
    swept: AgentRun

    @classmethod
    def setUpTestData(cls) -> None:
        cls.bank = factories.tenant(slug="watch-panel-a")
        cls.other = factories.tenant(slug="watch-panel-b")
        cls.reader = factories.member_user(cls.bank, roles=("reader",))
        cls.sweeper = _agent("watch-sweeper", platform_scope={"jurisdictions": ["se", "eu"]}, platform_monthly_budget=Decimal("250.00"))
        cls.confirmer = _agent("library-confirmer", cadence=AgentCadence.WEEKLY, kind=AgentKind.REVIEW.value)
        cls.manual = _agent("backfill-on-demand", cadence=AgentCadence.MANUAL, kind=AgentKind.BACKFILL.value)
        _agent("switched-off", active=False)
        retired = _agent("retired-sweeper")
        with library_write("test"):
            AgentVersion.objects.create(agent=retired, version_no=1, model="m", prompt_path="p.md", retired_at=NOW)
        _agent(
            "bank-watch",
            scope=AgentScopeKind.TENANT.value,
            tenant_configurable=True,
            writes_to=AgentWritesTo.TENANT.value,
            kind=AgentKind.RESEARCH.value,
        )
        tenancy.clear_tenant()
        key = agent_build.agent_key(agent_row=cls.sweeper)
        _closed(agent_build.platform_run(key=key), started_at=SWEPT - datetime.timedelta(days=1), status=RunStatus.FAILED)
        cls.swept = _closed(agent_build.platform_run(key=key), started_at=SWEPT, status=RunStatus.SUCCEEDED)
        _closed(agent_build.platform_run(key=agent_build.agent_key(agent_row=cls.manual)), started_at=SWEPT, status=RunStatus.RUNNING, finished=False)
        # A bank's run of the same definition, newer than the platform's: what a bank asked
        # its own key to run is never "how bleqq's watch last ended".
        for tenant in (cls.bank, cls.other):
            tenancy.activate(tenant.id)
            bank_key = agent_build.tenant_key(tenant, scopes=(perms.SCOPE_AGENT_RUNS_WRITE,))
            bank_run = AgentRun.objects.create(agent=cls.sweeper, api_key=bank_key.row, model="bank", pipeline_version="1")
            AgentRun.objects.filter(pk=bank_run.pk).update(started_at=NOW, status=RunStatus.FAILED.value, finished_at=NOW)
        tenancy.clear_tenant()

    def read(self, query: str = "", *, user: User | None = None) -> Any:
        headers = sign_in(user or self.reader, tenant=self.bank)
        with mock.patch("apps.agents.platform_read.clock", return_value=NOW):
            response = self.client.get(f"{WATCH}{query}", **headers)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def item(self, key: str) -> dict[str, Any]:
        return next(row for row in self.read()["items"] if row["key"] == key)

    def test_every_system_role_of_a_bank_reads_the_same_list(self) -> None:
        expected = self.read()
        bank_roles = [role for role, grants in perms.SYSTEM_ROLES.items() if grants <= perms.TENANT_PERMISSIONS]
        self.assertIn("reader", bank_roles)
        for role in bank_roles:
            with self.subTest(role=role):
                self.assertIn(perms.WATCH_READ, perms.SYSTEM_ROLES[role])
                self.assertEqual(self.read(user=factories.member_user(self.bank, roles=(role,))), expected)

    def test_an_anonymous_request_is_401(self) -> None:
        response = self.client.get(WATCH)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "unauthenticated")

    def test_only_active_platform_agents_are_listed(self) -> None:
        body = self.read()
        self.assertEqual(
            [row["key"] for row in body["items"]], ["backfill-on-demand", "library-confirmer", "watch-sweeper"]
        )
        self.assertEqual(body["total"], len(body["items"]))

    def test_each_agent_carries_exactly_the_pinned_fields(self) -> None:
        pinned = {"key", "name", "purpose", "jurisdictions", "cadence", "nextRunAt", "lastRun"}
        self.assertEqual(set(PlatformWatchItem.model_json_schema(by_alias=True)["properties"]), pinned)
        self.assertEqual(set(PlatformWatchLastRun.model_json_schema(by_alias=True)["properties"]), {"finishedAt", "status"})
        for row in self.read()["items"]:
            self.assertEqual(set(row), pinned)
            if row["lastRun"] is not None:
                self.assertEqual(set(row["lastRun"]), {"finishedAt", "status"})

    def test_the_sweeper_reads_as_its_definition_says(self) -> None:
        row = self.item("watch-sweeper")
        self.assertEqual(row["name"], "watch-sweeper")
        self.assertEqual(row["purpose"], self.sweeper.description)
        self.assertEqual(row["jurisdictions"], ["se", "eu"])
        self.assertEqual(row["cadence"], "daily")

    def test_the_last_run_is_the_platforms_status_only(self) -> None:
        row = self.item("watch-sweeper")
        self.assertEqual(row["lastRun"], {"finishedAt": "2026-09-25T02:18:00Z", "status": "succeeded"})

    def test_a_run_still_going_has_no_finish(self) -> None:
        self.assertEqual(self.item("backfill-on-demand")["lastRun"], {"finishedAt": None, "status": "running"})

    def test_an_agent_that_never_ran_carries_a_null_last_run(self) -> None:
        row = self.item("library-confirmer")
        self.assertIn("lastRun", row)
        self.assertIsNone(row["lastRun"])

    def test_the_next_run_follows_the_cadence(self) -> None:
        self.assertEqual(self.item("watch-sweeper")["nextRunAt"], "2026-09-26T02:00:00Z", "a day after the last start")
        self.assertEqual(self.item("library-confirmer")["nextRunAt"], "2026-09-25T09:00:00Z", "never ran, so it is due now")
        self.assertIsNone(self.item("backfill-on-demand")["nextRunAt"], "a manual agent is started by nobody's schedule")

    def test_an_overdue_agent_is_due_now_rather_than_in_the_past(self) -> None:
        AgentRun.objects.filter(pk=self.swept.pk).update(started_at=NOW - datetime.timedelta(days=3))
        self.assertEqual(self.item("watch-sweeper")["nextRunAt"], "2026-09-25T09:00:00Z")

    def test_no_bank_figure_feeds_the_answer_and_both_banks_read_the_same(self) -> None:
        other_reader = factories.member_user(self.other, roles=("reader",))
        headers = sign_in(other_reader, tenant=self.other)
        with mock.patch("apps.agents.platform_read.clock", return_value=NOW):
            theirs = self.client.get(WATCH, **headers).json()
        self.assertEqual(theirs, self.read())
        self.assertEqual(self.item("watch-sweeper")["lastRun"]["status"], "succeeded", "the banks' newer failed runs are not bleqq's")

    def test_paging(self) -> None:
        everything = self.read()
        self.assertEqual(self.read("?limit=1&offset=1")["items"], everything["items"][1:2])
        self.assertEqual(self.read("?limit=1")["total"], everything["total"], "total counts the list, not the page")
        headers = sign_in(self.reader, tenant=self.bank)
        self.assertEqual(self.client.get(f"{WATCH}?limit=101", **headers).status_code, 422)

    def test_nothing_is_writable(self) -> None:
        headers = sign_in(self.reader, tenant=self.bank)
        for method in ("put", "patch", "post", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(WATCH, data={}, content_type="application/json", **headers)
                self.assertEqual(response.status_code, 405, response.content)
