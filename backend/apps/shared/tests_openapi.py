"""The published contract's own additions (apps/shared/openapi.py, review 2026-11-11 B-2 and
B-10): no component schema that no operation reaches, and every gate a route's auth class
and decorators enforce is written into its description from those decorators."""

from __future__ import annotations

import json
import re
from typing import Any

from django.test import SimpleTestCase

from apps.shared.permissions import gate_of, step_up_of
from apps.shared.routes import iter_operations
from config.api import api


class PublishedContract(SimpleTestCase):
    document: dict[str, Any]
    operations: dict[str, dict[str, Any]]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.document = api.get_openapi_schema(path_prefix="/api/v1")
        cls.operations = {
            operation["operationId"]: operation
            for item in cls.document["paths"].values()
            for operation in item.values()
            if isinstance(operation, dict) and "operationId" in operation
        }

    def test_every_published_schema_is_reached_by_an_operation(self) -> None:
        """Review 2026-11-11 B-2: a Query model Ninja inlines into `parameters` is no schema
        an integrator can send or receive."""
        schemas = self.document["components"]["schemas"]
        reached = set(re.findall(r'"#/components/schemas/([^"]+)"', json.dumps(self.document["paths"])))
        pending = set(reached)
        while pending:
            found = set(re.findall(r'"#/components/schemas/([^"]+)"', json.dumps(schemas[pending.pop()]))) - reached
            reached |= found
            pending |= found
        self.assertEqual(set(schemas) - reached, set())
        self.assertNotIn("PageQuery", schemas)

    def test_every_gate_is_published_from_its_decorator(self) -> None:
        """Review 2026-11-11 B-10: the decorators are the source of truth, so no route can
        describe a gate it lacks or leave out one it has."""
        for registered in iter_operations(api):
            description = self.operations[registered.operation_id]["description"]
            with self.subTest(operation=registered.operation_id):
                if registered.auth:
                    self.assertIn("`unauthenticated` (401) without", description)
                gate = gate_of(registered.view_func)
                if gate is not None:
                    self.assertIn("`permission_denied` (403)", description)
                    self.assertIn(f"`{gate.value}`", description)
                self.assertEqual("`step_up_required` (403) without a passkey assertion younger" in description, step_up_of(registered.view_func))

    def test_a_page_and_an_if_match_are_published(self) -> None:
        members = self.operations["listMembers"]["description"]
        self.assertIn("`validation_error` (422) when `limit` is above", members)
        self.assertIn("`stale_write` (409) when `If-Match`", self.operations["updateOrgUnit"]["description"])
        self.assertNotIn("`stale_write`", self.operations["listMembers"]["description"])
