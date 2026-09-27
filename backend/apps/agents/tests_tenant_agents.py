"""A bank's own agents (AGT-04, ADR 0053, D-32, D-89): added from a tenant-scoped definition,
switched on and off, given a cadence within the plan and a scope of keys, and only ever in
the bank's own zone.

Written before the logic: against the contract's stubs every served call below answered 501
`not_built`, and the pause helper did not exist.
"""

from __future__ import annotations

import datetime
import uuid
from types import SimpleNamespace
from typing import Any
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import override_settings

from apps.agents import tenant_agents
from apps.agents import testing as agent_build
from apps.agents.models import Agent, AgentKind, AgentScopeKind, AgentWritesTo, TenantAgent, TenantAgentBudget
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.models import AuditEvent
from apps.shared.tenancy import library_write
from apps.shared.testing import ScenarioTestCase, stub_session, user_principal
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms, seed_term_dimensions

AGENTS = "/api/v1/agents"
JSON = "application/json"


def tenant_definition(key: str = "bank-source-watch") -> Agent:
    with library_write("test"):
        return Agent.objects.create(
            key=key,
            kind=AgentKind.RESEARCH.value,
            current_version=1,
            scope=AgentScopeKind.TENANT.value,
            tenant_configurable=True,
            writes_to=AgentWritesTo.TENANT.value,
        )


def frozen_wednesday_noon(zone: str) -> datetime.datetime:
    """The first Wednesday after the tenant-local today, at noon in the tenant's zone: a
    clock the test fixes, never the real today."""
    today = datetime.datetime.now(ZoneInfo(zone)).date()
    wednesday = today + datetime.timedelta(days=(3 - today.isoweekday()) % 7 or 7)
    return datetime.datetime.combine(wednesday, datetime.time(12), tzinfo=ZoneInfo(zone))


class TenantAgentCase(ScenarioTestCase):
    """Two banks, one tenant-scoped definition and one of bleqq's, and the vocabularies a
    scope names."""

    def setUp(self) -> None:
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_term_dimensions()
        seed_taxonomy_terms()
        self.definition = tenant_definition()
        self.bleqq = agent_build.agent(key="watch-sweeper")
        self.bank = factories.tenant(slug="own-agents-a")
        self.admin = factories.member_user(self.bank, roles=("admin",))
        self.other = factories.tenant(slug="own-agents-b")
        self.other_admin = factories.member_user(self.other, roles=("admin",))
        tenancy.clear_tenant()

    def principal(self, bank: Any = None, admin: Any = None) -> Any:
        return user_principal(
            permissions={perms.AGENTS_MANAGE}, tenant_id=(bank or self.bank).id, subject_id=(admin or self.admin).id
        )

    def call(self, method: str, url: str, body: Any = None, *, bank: Any = None, admin: Any = None) -> Any:
        with stub_session(self.principal(bank, admin)):
            if body is None:
                answer = getattr(self.client, method)(url, **self.as_user(self.principal()))
            else:
                answer = getattr(self.client, method)(url, data=body, content_type=JSON, **self.as_user(self.principal()))
        tenancy.clear_tenant()
        return answer

    def add(self, **body: Any) -> Any:  # compliance: allow-kwargs test helper building a request body
        return self.call("post", AGENTS, {"agent": self.definition.key, **body})

    def audit(self, action: str) -> list[AuditEvent]:
        self.activate(self.bank)
        rows = list(AuditEvent.objects.filter(action=action).order_by("created"))
        tenancy.clear_tenant()
        return rows

    def set_cap(self, bank: Any = None) -> None:
        tenancy.activate((bank or self.bank).id)
        TenantAgentBudget.objects.create(tenant=bank or self.bank, monthly_cap="100.00")
        tenancy.clear_tenant()


class AddingAnAgent(TenantAgentCase):
    def test_one_of_bleqqs_agents_is_refused_and_nothing_is_written(self) -> None:
        answer = self.call("post", AGENTS, {"agent": self.bleqq.key})
        self.assertEqual(answer.status_code, 403, answer.content)
        self.assertEqual(answer.json()["code"], "permission_denied")
        self.assertEqual(answer.json()["requiredPermission"], perms.AGENT_DEFINITIONS_MANAGE)
        self.activate(self.bank)
        self.assertFalse(TenantAgent.objects.exists())
        self.assertFalse(AuditEvent.objects.filter(action="agents.tenant_agent_added").exists())

    def test_a_definition_key_nobody_has_is_unknown(self) -> None:
        answer = self.call("post", AGENTS, {"agent": "no-such-agent"})
        self.assertEqual(answer.status_code, 422, answer.content)
        self.assertEqual(answer.json()["code"], "unknown_key")

    def test_a_tenant_definition_adds_a_switched_off_agent_with_one_audit_row(self) -> None:
        answer = self.add(cadence="weekly", scope={"jurisdictions": ["se"], "terms": []})
        self.assertEqual(answer.status_code, 201, answer.content)
        body = answer.json()
        self.assertEqual(body["agent"], self.definition.key)
        self.assertFalse(body["enabled"])
        self.assertEqual(body["cadence"], "weekly")
        self.assertEqual(body["runWeekday"], 1)
        self.assertEqual(body["runHour"], 6)
        self.assertIsNone(body["nextRunAt"], "an agent switched off has no run scheduled")
        self.assertEqual(body["scope"], {"jurisdictions": ["se"], "terms": []})
        self.assertIsNone(body["pausedAt"])
        [row] = self.audit("agents.tenant_agent_added")
        self.assertEqual(row.tenant_id, self.bank.id)
        self.assertEqual(str(row.actor_id), str(self.admin.id))
        self.assertEqual(row.after["agent"], self.definition.key)
        self.assertEqual(row.after["enabled"], False)

    def test_a_cadence_above_the_plan_is_refused_and_one_at_it_is_not(self) -> None:
        answer = self.add(cadence="daily")
        self.assertEqual(answer.status_code, 422, answer.content)
        self.assertEqual(answer.json()["code"], "above_plan_limit")
        self.assertEqual(self.add(cadence="weekly").status_code, 201)

    @override_settings(AGENT_MIN_CADENCE="daily")
    def test_the_plan_limit_is_the_setting(self) -> None:
        self.assertEqual(self.add(cadence="daily").status_code, 201)

    def test_manual_is_always_within_the_plan(self) -> None:
        with override_settings(AGENT_MIN_CADENCE="monthly"):
            answer = self.add(cadence="manual", runWeekday=3, runHour=9)
        self.assertEqual(answer.status_code, 201, answer.content)
        self.assertIsNone(answer.json()["runWeekday"])
        self.assertIsNone(answer.json()["runHour"])

    @override_settings(AGENTS_PER_TENANT_MAX=1)
    def test_one_agent_more_than_the_plan_allows_is_refused(self) -> None:
        self.assertEqual(self.add().status_code, 201)
        tenant_definition("bank-second-watch")
        answer = self.call("post", AGENTS, {"agent": "bank-second-watch"})
        self.assertEqual(answer.status_code, 422, answer.content)
        self.assertEqual(answer.json()["code"], "above_plan_limit")
        # The limit is per bank: another bank adds its own.
        self.assertEqual(self.call("post", AGENTS, {"agent": "bank-second-watch"}, bank=self.other, admin=self.other_admin).status_code, 201)

    def test_the_same_definition_twice_is_a_duplicate(self) -> None:
        self.assertEqual(self.add().status_code, 201)
        answer = self.add()
        self.assertEqual(answer.status_code, 409, answer.content)
        self.assertEqual(answer.json()["code"], "duplicate_key")

    def test_an_unknown_or_retired_scope_key_is_refused_with_the_valid_keys(self) -> None:
        answer = self.add(scope={"jurisdictions": ["se", "atlantis"], "terms": []})
        self.assertEqual(answer.status_code, 422, answer.content)
        self.assertEqual(answer.json()["code"], "unknown_key")
        self.assertIn("se", answer.json()["validKeys"])
        self.assertNotIn("atlantis", answer.json()["validKeys"])

        answer = self.add(scope={"jurisdictions": [], "terms": ["no-such-term"]})
        self.assertEqual(answer.status_code, 422, answer.content)
        self.assertEqual(answer.json()["code"], "unknown_key")
        self.assertEqual(answer.json()["vocabulary"], "taxonomy_term")
        self.assertIn("securities", answer.json()["validKeys"])

        with library_write("test"):
            from apps.library.models import Jurisdiction

            Jurisdiction.objects.filter(key="fi").update(active=False)
        answer = self.add(scope={"jurisdictions": ["fi"], "terms": []})
        self.assertEqual(answer.json()["code"], "unknown_key")
        self.activate(self.bank)
        self.assertFalse(TenantAgent.objects.exists())


class ChangingAnAgent(TenantAgentCase):
    def setUp(self) -> None:
        super().setUp()
        self.agent_id = self.add(cadence="weekly").json()["id"]

    def patch(self, body: dict[str, Any], **who: Any) -> Any:  # compliance: allow-kwargs test helper forwarding the caller
        return self.call("patch", f"{AGENTS}/{self.agent_id}", body, **who)

    def test_switching_on_needs_the_cap_first(self) -> None:
        answer = self.patch({"enabled": True})
        self.assertEqual(answer.status_code, 422, answer.content)
        self.assertEqual(answer.json()["code"], "budget_cap_required")
        self.set_cap()
        self.assertTrue(self.patch({"enabled": True}).json()["enabled"])
        # Switching off never needs anything.
        self.assertFalse(self.patch({"enabled": False}).json()["enabled"])

    def test_the_next_run_follows_the_cadence_in_the_banks_own_time_zone(self) -> None:
        self.set_cap()
        noon = frozen_wednesday_noon(self.bank.timezone)
        zone = ZoneInfo(self.bank.timezone)
        monday = noon.date() + datetime.timedelta(days=5)
        first_of_next = (noon.date().replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
        this_first_monday = noon.date().replace(day=1) + datetime.timedelta(days=(1 - noon.date().replace(day=1).isoweekday()) % 7)
        next_first_monday = first_of_next + datetime.timedelta(days=(1 - first_of_next.isoweekday()) % 7)
        first_monday = this_first_monday if this_first_monday > noon.date() else next_first_monday
        cases = [
            ({"enabled": True, "cadence": "weekly", "runWeekday": 1, "runHour": 6}, datetime.datetime.combine(monday, datetime.time(6), tzinfo=zone)),
            ({"cadence": "weekly", "runWeekday": 3, "runHour": 14}, datetime.datetime.combine(noon.date(), datetime.time(14), tzinfo=zone)),
            ({"cadence": "weekly", "runWeekday": 3, "runHour": 9}, datetime.datetime.combine(noon.date() + datetime.timedelta(days=7), datetime.time(9), tzinfo=zone)),
            ({"cadence": "monthly", "runWeekday": 1, "runHour": 6}, datetime.datetime.combine(first_monday, datetime.time(6), tzinfo=zone)),
        ]
        with mock.patch.object(tenant_agents, "timezone", SimpleNamespace(now=lambda: noon.astimezone(datetime.UTC))):
            for body, expected in cases:
                with self.subTest(body=body):
                    answer = self.patch(body)
                    self.assertEqual(answer.status_code, 200, answer.content)
                    self.assertEqual(datetime.datetime.fromisoformat(answer.json()["nextRunAt"]), expected)
            with override_settings(AGENT_MIN_CADENCE="daily"):
                answer = self.patch({"cadence": "daily", "runHour": 9})
            self.assertEqual(
                datetime.datetime.fromisoformat(answer.json()["nextRunAt"]),
                datetime.datetime.combine(noon.date() + datetime.timedelta(days=1), datetime.time(9), tzinfo=zone),
            )
            self.assertIsNone(answer.json()["runWeekday"], "a daily run has no day")
            self.assertIsNone(self.patch({"cadence": "manual"}).json()["nextRunAt"])
            self.patch({"cadence": "weekly"})
            self.assertIsNone(self.patch({"enabled": False}).json()["nextRunAt"])

    def test_a_cadence_above_the_plan_is_refused_on_change(self) -> None:
        answer = self.patch({"cadence": "daily"})
        self.assertEqual(answer.status_code, 422, answer.content)
        self.assertEqual(answer.json()["code"], "above_plan_limit")

    def test_an_unknown_scope_key_is_refused_on_change(self) -> None:
        answer = self.patch({"scope": {"jurisdictions": ["atlantis"], "terms": []}})
        self.assertEqual(answer.status_code, 422, answer.content)
        self.assertEqual(answer.json()["code"], "unknown_key")
        self.assertIn("se", answer.json()["validKeys"])

    def test_a_change_leaves_one_audit_row_with_before_and_after(self) -> None:
        answer = self.patch({"scope": {"jurisdictions": ["se", "fi"], "terms": ["securities"]}})
        self.assertEqual(answer.status_code, 200, answer.content)
        [row] = self.audit("agents.tenant_agent_changed")
        self.assertEqual(row.tenant_id, self.bank.id)
        self.assertEqual(row.before["scope"], {"jurisdictions": [], "terms": []})
        self.assertEqual(row.after["scope"], {"jurisdictions": ["se", "fi"], "terms": ["securities"]})
        # What the body left out stays as it was.
        self.assertEqual(answer.json()["cadence"], "weekly")

    def test_another_bank_gets_404_and_changes_nothing(self) -> None:
        answer = self.patch({"enabled": False, "cadence": "monthly"}, bank=self.other, admin=self.other_admin)
        self.assertEqual(answer.status_code, 404, answer.content)
        self.assertEqual(answer.json()["code"], "not_found")
        self.activate(self.bank)
        self.assertEqual(TenantAgent.objects.get(pk=self.agent_id).cadence, "weekly")
        self.assertEqual(self.patch({}, bank=self.other, admin=self.other_admin).status_code, 404)
        self.assertEqual(self.call("patch", f"{AGENTS}/{uuid.uuid4()}", {}).status_code, 404)


class ListingAgents(TenantAgentCase):
    def test_the_list_holds_the_banks_own_and_never_bleqqs_or_another_banks(self) -> None:
        mine = self.add().json()["id"]
        self.call("post", AGENTS, {"agent": self.definition.key}, bank=self.other, admin=self.other_admin)
        agent_build.platform_run(key=agent_build.agent_key(agent_row=self.bleqq))
        tenancy.clear_tenant()
        answer = self.call("get", AGENTS)
        self.assertEqual(answer.status_code, 200, answer.content)
        self.assertEqual([item["id"] for item in answer.json()["items"]], [mine])
        self.assertEqual(answer.json()["total"], 1)
        self.assertNotIn(self.bleqq.key, {item["agent"] for item in answer.json()["items"]})

    def test_an_empty_list_is_a_200(self) -> None:
        answer = self.call("get", AGENTS)
        self.assertEqual(answer.status_code, 200)
        self.assertEqual(answer.json(), {"items": [], "total": 0})


class PausingAnAgent(TenantAgentCase):
    """The helper the cap, the scheduler and the controls pause through."""

    def test_the_system_pauses_with_a_reason_key_and_one_audit_row(self) -> None:
        self.set_cap()
        agent_id = self.add().json()["id"]
        self.call("patch", f"{AGENTS}/{agent_id}", {"enabled": True})
        self.activate(self.bank)
        agent = TenantAgent.objects.select_related("agent").get(pk=agent_id)
        self.assertIsNotNone(agent.next_run_at)
        tenant_agents.pause(agent, "budget_cap")
        tenant_agents.pause(agent, "budget_cap")
        agent.refresh_from_db()
        self.assertIsNotNone(agent.paused_at)
        self.assertIsNone(agent.paused_by)
        self.assertEqual(agent.pause_reason, "budget_cap")
        self.assertIsNone(agent.next_run_at, "a paused agent has no run scheduled")
        [row] = AuditEvent.objects.filter(action="agents.tenant_agent_paused")
        self.assertEqual(row.tenant_id, self.bank.id)
        self.assertEqual(row.after["pauseReason"], "budget_cap")
        answer = self.call("get", AGENTS).json()["items"][0]
        self.assertIsNotNone(answer["pausedAt"])
        self.assertIsNone(answer["pausedBy"])

    def test_one_of_bleqqs_agents_is_never_paused_by_a_bank(self) -> None:
        from apps.shared.errors import ProblemError

        with self.assertRaises(ProblemError):
            tenant_agents.pause(TenantAgent(tenant=self.bank, agent=self.bleqq), "budget_cap")
