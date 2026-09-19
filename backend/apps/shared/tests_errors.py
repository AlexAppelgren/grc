"""One error shape everywhere (playbook 4.4): problem details with `code`, `errors[]` for
field validation, `requiredPermission` on a 403, and never a stack trace. Also the
OpenAPI export's normalisation and the migrate_from_zero URL helper."""

from __future__ import annotations

import json
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpRequest
from django.test import SimpleTestCase, TestCase
from ninja.errors import HttpError

from apps.shared.errors import PROBLEM_CONTENT_TYPE, ProblemError, problem_response
from apps.shared.management.commands.export_openapi import normalise
from apps.shared.management.commands.migrate_from_zero import _with_database
from config import api as api_module


class ProblemShape(SimpleTestCase):
    def test_as_dict_carries_the_contract_fields(self) -> None:
        error = ProblemError(
            status=409, code="four_eyes_violation", detail="The requester cannot approve.", errors=[{"field": "x", "message": "m"}]
        )
        body = error.as_dict()
        self.assertEqual(body["title"], "Conflict")
        self.assertEqual(body["status"], 409)
        self.assertEqual(body["code"], "four_eyes_violation")
        self.assertEqual(body["errors"], [{"field": "x", "message": "m"}])
        self.assertNotIn("requiredPermission", body)
        response = problem_response(error)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response["Content-Type"], PROBLEM_CONTENT_TYPE)

    def test_handlers_translate_ninja_and_django_errors(self) -> None:
        request = HttpRequest()
        response = api_module.handle_http_error(request, HttpError(418, "teapot"))
        self.assertEqual(response.status_code, 418)
        self.assertEqual(json.loads(response.content)["code"], "http_error")

        response = api_module.handle_django_validation(request, DjangoValidationError("Owner is required.", code="owner_required"))
        self.assertEqual(response.status_code, 422)
        self.assertEqual(json.loads(response.content)["code"], "owner_required")
        self.assertEqual(json.loads(response.content)["detail"], "Owner is required.")

        response = api_module.not_found(request, None)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(json.loads(response.content)["code"], "not_found")


class ValidationThroughTheApi(TestCase):
    def test_a_malformed_query_answers_422_with_errors(self) -> None:
        from ninja import Router
        from ninja.errors import ValidationError as NinjaValidationError

        request = HttpRequest()
        error = NinjaValidationError([{"loc": ("query", "limit"), "msg": "value is not a valid integer"}])
        response = api_module.handle_ninja_validation(request, error)
        self.assertEqual(response.status_code, 422)
        body = json.loads(response.content)
        self.assertEqual(body["code"], "validation_error")
        self.assertEqual(body["errors"], [{"field": "query.limit", "message": "value is not a valid integer"}])
        self.assertIsInstance(Router(), Router)

    def test_unauthenticated_handler(self) -> None:
        from ninja.errors import AuthenticationError

        response = api_module.handle_authentication(HttpRequest(), AuthenticationError())
        self.assertEqual(response.status_code, 401)


class OpenApiNormalisation(SimpleTestCase):
    def test_status_descriptions_are_replaced_and_servers_dropped(self) -> None:
        schema: dict[str, Any] = {
            "servers": [{"url": "http://x"}],
            "paths": {
                "/a": {
                    "get": {"responses": {"200": {"description": "Whatever the route said"}, "default": {"description": "d"}}},
                    "parameters": [],
                }
            },
        }
        out = normalise(schema)
        self.assertNotIn("servers", out)
        self.assertEqual(out["paths"]["/a"]["get"]["responses"]["200"]["description"], "OK")
        self.assertEqual(out["paths"]["/a"]["get"]["responses"]["default"]["description"], "Response")
        self.assertEqual(schema["paths"]["/a"]["get"]["responses"]["200"]["description"], "Whatever the route said")


class MigrateFromZeroHelpers(SimpleTestCase):
    def test_with_database_replaces_only_the_path(self) -> None:
        url = "postgres://cw_migrator:pw@localhost:5432/compliance_watch?sslmode=disable"
        self.assertEqual(_with_database(url, "scratch"), "postgres://cw_migrator:pw@localhost:5432/scratch?sslmode=disable")
