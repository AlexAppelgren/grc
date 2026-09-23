"""The bank's AI switch (D-07, owner item 14, SRC-03): a bank that switched its own AI
features off reaches no model, and bleqq's own platform calls never read any bank's switch.

The switch is read by `apps/shared/ai.py`, the one door to a model, before the model is
reached and only when a bank is active. What these tests hold in place:

1. **Off means no model call and no log row**, through both doors: the whole answer
   (`generate`) and the streamed one (`stream`), which refuses when it is called and not
   when its first word is wanted, so the refusal is still a status the route can send.
2. **A bank whose row cannot be read is off**, because the switch is what decides whether
   a bank's own words leave it for a model.
3. **A platform call reads no bank's switch.** A library run has no bank active, so the
   watch agents that feed the shared library answer exactly as before, whatever every bank
   decided, and not one query touches the `tenant` table on their behalf.
"""

from __future__ import annotations

import uuid
from typing import ClassVar
from unittest import mock

from django.db import connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.governance.models import AiGeneration, AiPurpose
from apps.shared import ai, factories, tenancy
from apps.shared.adapters import llm
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant

PROMPT = "Passages:\n[1] FI decided to amend three regulations. (FI Dnr 25-12345, 1 §)"


def switch_off(tenant: Tenant) -> None:
    """What the bank's own administrator does with the switch, written straight to the row
    here because the route that writes it is proved where it lives."""
    with transaction.atomic():
        tenancy.activate(tenant.id)
        Tenant.objects.filter(pk=tenant.id).update(ai_enabled=False)


def generate(tenant_id: uuid.UUID | None) -> ai.Generation:
    return ai.generate(
        purpose=AiPurpose.ANSWER if tenant_id else AiPurpose.CHANGE_SUMMARY,
        system="You answer from the passages only.",
        prompt=PROMPT,
        prompt_template="ask/answer/v1",
        citations=[],
        tenant_id=tenant_id,
    )


class AiSwitchTests(TestCase):
    on: ClassVar[Tenant]
    off: ClassVar[Tenant]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.on = factories.tenant(slug="ai-switch-on")
        cls.off = factories.tenant(slug="ai-switch-off")
        switch_off(cls.off)

    def assert_refused(self, refused: ProblemError) -> None:
        self.assertEqual((refused.status, refused.code), (403, "feature_off"))

    def test_a_bank_with_its_ai_on_is_answered_and_the_call_logged(self) -> None:
        with transaction.atomic():
            tenancy.activate(self.on.id)
            result = generate(self.on.id)

        self.assertTrue(result.text)
        self.assertEqual(result.generation.tenant_id, self.on.id)

    def test_a_bank_that_switched_its_ai_off_reaches_no_model(self) -> None:
        with (
            mock.patch.object(llm.MockLlm, "stream", autospec=True) as model,
            self.assertRaises(ProblemError) as refused,
            transaction.atomic(),
        ):
            tenancy.activate(self.off.id)
            generate(self.off.id)

        self.assert_refused(refused.exception)
        model.assert_not_called()
        self.assertFalse(AiGeneration.objects.exists())

    def test_the_streamed_door_refuses_when_it_is_called_not_when_it_is_read(self) -> None:
        with mock.patch.object(llm.MockLlm, "stream", autospec=True) as model, transaction.atomic():
            tenancy.activate(self.off.id)
            with self.assertRaises(ProblemError) as refused:
                ai.stream(
                    purpose=AiPurpose.ANSWER,
                    system="s",
                    prompt=PROMPT,
                    prompt_template="ask/answer/v1",
                    cite=lambda text: [],
                    tenant_id=self.off.id,
                    asker_id=None,
                    generation_id=uuid.uuid4(),
                    max_tokens=64,
                )

        self.assert_refused(refused.exception)
        model.assert_not_called()

    def test_a_bank_whose_row_cannot_be_read_is_treated_as_off(self) -> None:
        with self.assertRaises(ProblemError) as refused, transaction.atomic():
            tenancy.activate(uuid.uuid4())
            generate(None)

        self.assert_refused(refused.exception)

    def test_a_platform_call_reads_no_banks_switch(self) -> None:
        """Every bank has switched off, and the library's own call still answers: the switch
        is each bank's over its own features, never over bleqq's watch of the law."""
        switch_off(self.on)
        with transaction.atomic():
            tenancy.clear_tenant()  # a library run, as the worker runs one: no bank active
            with CaptureQueriesContext(connection) as queries:
                result = generate(None)

        self.assertTrue(result.text)
        self.assertIsNone(result.generation.tenant_id)
        self.assertEqual(
            [query["sql"] for query in queries.captured_queries if 'FROM "tenant"' in query["sql"]],
            [],
            "a platform call never reads a bank's switch",
        )
