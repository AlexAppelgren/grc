"""The summary drafted above what applies (ACC-06, ACC-09): labelled, logged, costed, and
never able to shorten the list.

A summary is drafted by the one logged door (`apps/shared/ai.generate`) from the
description and the list's first shared obligations, and from nothing of the bank's own:
not its register, not its private records. It is labelled AI-drafted with a fixed sentence,
cites by stable key, and its cost counts against the bank's monthly cap. Every way it can
fail leaves the list exactly as it would be without it, with the reason in the slot."""

from __future__ import annotations

import time
from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.agents import budget
from apps.agents.models import TenantAgentBudget
from apps.agents.schemas import WHAT_APPLIES_NOTICE
from apps.agents.tests_what_applies import ORDER_ROUTING, TradingBank, keys
from apps.governance.models import AiGeneration
from apps.shared import tenancy
from apps.shared.adapters.llm import Completion, LlmError, MockLlm
from apps.shared.models import Tenant

REASON = "We route client orders on regulated venues"


class Recording(MockLlm):
    """The mock, remembering every prompt and deadline it was given."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def stream(self, *, system: str, prompt: str, max_tokens: int, deadline_s: float | None = None) -> Iterator[str | Completion]:
        self.calls.append({"system": system, "prompt": prompt, "max_tokens": max_tokens, "deadline_s": deadline_s})
        return super().stream(system=system, prompt=prompt, max_tokens=max_tokens, deadline_s=deadline_s)


class Failing(Recording):
    def stream(self, *, system: str, prompt: str, max_tokens: int, deadline_s: float | None = None) -> Iterator[str | Completion]:
        self.calls.append({"prompt": prompt})
        raise LlmError("the model API returned 529 (overloaded_error)")


class Slow(Recording):
    """A model that is still silent when the caller's deadline passes, as the adapter's own
    deadline then refuses it."""

    def stream(self, *, system: str, prompt: str, max_tokens: int, deadline_s: float | None = None) -> Iterator[str | Completion]:
        self.calls.append({"deadline_s": deadline_s})
        time.sleep(deadline_s or 0)
        raise LlmError("the model API did not finish before the call's deadline")


def cap(tenant: Tenant, amount: str) -> None:
    tenancy.activate(tenant.id)
    TenantAgentBudget.objects.update_or_create(tenant=tenant, defaults={"monthly_cap": Decimal(amount)})


class Summarised(TestCase):
    def setUp(self) -> None:
        self.bank = TradingBank()
        self.bank.decide(self.bank.execution, REASON)
        cap(self.bank.tenant, "5.00")

    def ask(self, llm: Recording, **page: Any) -> dict[str, Any]:
        with patch("apps.shared.ai.get_llm", return_value=llm):
            response = self.bank.ask(self.client, self.bank.trading_key, **page)
        self.assertEqual(response.status_code, 200, response.content)
        return dict(response.json())

    def generations(self) -> list[AiGeneration]:
        tenancy.activate(self.bank.tenant.id)
        return list(AiGeneration.objects.filter(purpose="what_applies"))

    def test_a_drafted_summary_is_labelled_and_cites_the_list_by_stable_key(self) -> None:
        body = self.ask(Recording())
        summary = body["summary"]
        self.assertEqual((summary["status"], summary["reason"], summary["aiGenerated"]), ("drafted", None, True))
        self.assertEqual(summary["notice"], WHAT_APPLIES_NOTICE)
        self.assertTrue(summary["citations"])
        self.assertLessEqual(set(summary["citations"]), set(keys(body)))
        for key in summary["citations"]:
            self.assertIn(f"[{key}]", summary["text"])
        self.assertNotRegex(summary["text"], r"\[\d+\]", "no bare number is left for a reader to decode")

    def test_the_call_is_logged_with_model_version_purpose_citations_and_cost(self) -> None:
        body = self.ask(Recording())
        [row] = self.generations()
        self.assertEqual((row.tenant_id, row.model, row.model_version, row.status), (self.bank.tenant.id, "mock", "0", "draft"))
        self.assertFalse(row.model_metadata_reported_by_agent)
        self.assertEqual({citation["label"] for citation in row.citations}, set(keys(body)))
        self.assertGreater(row.cost_minor, 0)
        self.assertEqual(row.prompt_template, "agent-access/what-applies/v1")

    def test_the_prompt_is_the_description_and_library_facts_and_nothing_of_the_bank_s(self) -> None:
        llm = Recording()
        self.ask(llm)
        [call] = llm.calls
        self.assertIn(f"Description: {ORDER_ROUTING}", call["prompt"])
        self.assertIn("Best execution of client orders", call["prompt"])
        for secret in (REASON, self.bank.private.stable_key, self.bank.card.stable_key, "Trading platform coding agent"):
            self.assertNotIn(secret, call["prompt"])
            self.assertNotIn(secret, call["system"])
        self.assertEqual(call["deadline_s"], 2.0, "WHAT_APPLIES_SUMMARY_DEADLINE_MS reaches the adapter")
        self.assertEqual(call["max_tokens"], 400)

    def test_the_description_is_never_stored(self) -> None:
        self.ask(Recording())
        [row] = self.generations()
        self.assertNotIn(ORDER_ROUTING, " ".join((row.output, row.prompt_hash, str(row.citations))))

    def test_a_standard_s_obligation_never_reaches_the_model(self) -> None:
        from apps.library import testing as library_testing

        standard = library_testing.instrument(key="iso-iec-27001-2022", short_name="ISO/IEC 27001:2022", regime="regime:securities", level="standard", binding=False)
        clause = library_testing.obligation(standard, key="iso-27001-conformance", titles={"en": "Conform to the standard"})
        llm = Recording()
        with patch("apps.shared.ai.get_llm", return_value=llm):
            body = self.bank.ask(self.client, self.bank.general_key).json()
        self.assertIn(clause.stable_key, keys(body), "the list keeps it")
        self.assertNotIn("Conform to the standard", llm.calls[0]["prompt"])

    def test_its_cost_counts_against_the_monthly_cap(self) -> None:
        before = budget.spend(self.bank.tenant)
        self.ask(Recording())
        [row] = self.generations()
        self.assertEqual(budget.spend(self.bank.tenant) - before, Decimal(row.cost_minor) / 100)

    def test_a_later_page_asks_no_model(self) -> None:
        llm = Recording()
        body = self.ask(llm, limit=1, offset=1)
        self.assertEqual((body["summary"]["status"], body["summary"]["reason"]), ("not_drafted", "later_page"))
        self.assertEqual(llm.calls, [])


class TheListSurvives(TestCase):
    """Every fallback answers the same list as a drafted answer, with the reason."""

    def setUp(self) -> None:
        self.bank = TradingBank()
        cap(self.bank.tenant, "5.00")
        with patch("apps.shared.ai.get_llm", return_value=Recording()):
            self.whole = self.bank.ask(self.client, self.bank.trading_key).json()
        self.assertEqual(self.whole["summary"]["status"], "drafted")

    def fallback(self, llm: Recording, reason: str) -> None:
        with patch("apps.shared.ai.get_llm", return_value=llm):
            response = self.bank.ask(self.client, self.bank.trading_key)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(
            body["summary"],
            {"status": "not_drafted", "reason": reason, "aiGenerated": False, "notice": WHAT_APPLIES_NOTICE, "text": None, "citations": []},
        )
        self.assertEqual((keys(body), body["total"]), (keys(self.whole), self.whole["total"]))

    def test_a_model_that_fails(self) -> None:
        self.fallback(Failing(), "model_failed")

    @override_settings(WHAT_APPLIES_SUMMARY_DEADLINE_MS=50)
    def test_a_model_that_does_not_answer_in_time(self) -> None:
        llm = Slow()
        self.fallback(llm, "timeout")
        self.assertEqual(llm.calls, [{"deadline_s": 0.05}])

    def test_the_ai_off_switch_asks_no_model(self) -> None:
        Tenant.objects.filter(pk=self.bank.tenant.id).update(ai_enabled=False)
        llm = Recording()
        self.fallback(llm, "ai_off")
        self.assertEqual(llm.calls, [])

    def test_a_reached_cap_asks_no_model(self) -> None:
        cap(self.bank.tenant, "0.00")
        llm = Recording()
        self.fallback(llm, "budget_cap")
        self.assertEqual(llm.calls, [])

    def test_no_cap_set_asks_no_model(self) -> None:
        tenancy.activate(self.bank.tenant.id)
        TenantAgentBudget.objects.filter(tenant=self.bank.tenant).delete()
        llm = Recording()
        self.fallback(llm, "budget_cap")
        self.assertEqual(llm.calls, [])

    def test_no_fallback_writes_a_log_row(self) -> None:
        self.fallback(Failing(), "model_failed")
        tenancy.activate(self.bank.tenant.id)
        self.assertEqual(AiGeneration.objects.filter(purpose="what_applies").count(), 1, "only the drafted answer's")
