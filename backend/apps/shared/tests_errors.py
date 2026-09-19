"""One error shape everywhere (playbook 4.4): problem details with `code`, `errors[]` for
field validation, `requiredPermission` on a 403, and never a stack trace. A logged
exception keeps its frames and types, never a message a row or a request put there. Also
the OpenAPI export's normalisation and the migrate_from_zero URL helper."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from django.core.exceptions import BadRequest, RequestDataTooBig, TooManyFieldsSent
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpRequest
from django.http.multipartparser import MultiPartParserError
from django.test import SimpleTestCase, TestCase, override_settings
from ninja.errors import HttpError

from apps.shared.errors import PROBLEM_CONTENT_TYPE, ProblemError, problem_response
from apps.shared.logging import JsonFormatter
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


class UnhandledErrors(TestCase):
    def test_an_unexpected_error_is_a_problem_without_a_trace_and_writes_nothing(self) -> None:
        from unittest import mock

        from django.test import Client

        from apps.identity.models import User
        from apps.shared import factories
        from apps.shared.testing import sign_in

        editor = sign_in(factories.platform_user(roles=("library_editor",), email="editor@bleqq.test"))

        def write_then_fail(**_: Any) -> Any:
            factories.user(name="Written before the failure")
            raise RuntimeError("tenant secret in the message")

        body = {"kind": "vocabulary_retire", "title": "Retire ai", "payload": {"list": "flag", "key": "ai"}}
        with mock.patch("apps.proposals.logic.create", side_effect=write_then_fail), self.assertLogs("config.api", "ERROR"):
            response = Client().post("/api/v1/proposals", body, content_type="application/json", **editor)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response["Content-Type"], PROBLEM_CONTENT_TYPE)
        problem = json.loads(response.content)
        self.assertEqual((problem["status"], problem["code"]), (500, "internal_error"))
        self.assertNotIn("secret", response.content.decode())
        self.assertNotIn("Traceback", response.content.decode())
        self.assertFalse(User.objects.filter(name="Written before the failure").exists(), "the request's writes roll back")

    def test_an_unexpected_error_logs_the_route_pattern_and_the_type_never_the_path_or_message(self) -> None:
        from unittest import mock

        from django.test import Client

        from apps.shared import factories
        from apps.shared.testing import sign_in

        tenant = factories.tenant(slug="bank")
        admin = sign_in(factories.member(tenant, roles=("admin",)).user, tenant=tenant)
        key = "project_" + "falcon"  # a tenant's own key, which the path carries
        failure = RuntimeError(f"Failing row contains ({key}, confidential note)")
        with (
            mock.patch("apps.taxonomy.tenant_lists_logic.patch_row", side_effect=failure),
            self.assertLogs("config.api", "ERROR") as logs,
            self.assertLogs("django.request", "ERROR") as django_logs,
        ):
            response = Client().patch(f"/api/v1/vocab/tenant_tag/{key}", {"labels": {"en": "x"}}, content_type="application/json", **admin)
        self.assertEqual(response.status_code, 500)
        self.assertIn("<key>", getattr(logs.records[0], "route"))  # noqa: B009
        line = JsonFormatter().format(logs.records[0])
        self.assertIn("RuntimeError", line)
        # Django's own line for the 500 names the route too, never the path it was asked for.
        django_line = JsonFormatter().format(django_logs.records[0])
        self.assertIn("<key>", django_line)
        for written in (line, django_line):
            self.assertNotIn(key, written)
            self.assertNotIn("confidential", written)


class ExceptionsInLogLines(SimpleTestCase):
    def test_a_logged_exception_keeps_its_frames_and_types_and_drops_every_message(self) -> None:
        row = "Project " + "Falcon acquisition"  # what a database error's DETAIL line carries
        try:
            try:
                try:
                    raise KeyError(row)
                except KeyError as missing:
                    raise ValueError(f"Failing row contains (-1, {row})") from missing
            except ValueError:
                raise RuntimeError(f"Key (name)=({row}) already exists.")  # noqa: B904 the implicit context is what is under test
        except RuntimeError:
            record = logging.LogRecord("apps.test", logging.ERROR, __file__, 1, "failed", None, sys.exc_info())
        line = JsonFormatter().format(record)
        self.assertNotIn("Falcon", line)
        for kind in ("KeyError", "ValueError", "RuntimeError"):
            self.assertIn(kind, line)
        self.assertIn("test_a_logged_exception_keeps_its_frames_and_types_and_drops_every_message", line)


class DjangoRequestLines(TestCase):
    def test_a_4xx_line_carries_neither_the_query_nor_the_request(self) -> None:
        from django.test import Client

        with self.assertLogs("django.request", "WARNING") as logs:
            response = Client().get("/api/v1/no-such-route?q=secret-search-text")
        self.assertEqual(response.status_code, 404)
        line = JsonFormatter().format(logs.records[0])
        self.assertNotIn("secret-search-text", line)
        self.assertNotIn("WSGIRequest", line)
        self.assertNotIn("request", json.loads(line))
        self.assertEqual(json.loads(line)["message"], "404 GET /api/v1")


class UnreadableRequests(TestCase):
    @override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=64)
    def test_an_oversized_body_is_a_400_problem(self) -> None:
        from django.test import Client

        body = {"email": "someone." * 20 + "@bank.example"}
        response = Client().post("/api/v1/auth/code/request", body, content_type="application/json")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response["Content-Type"], PROBLEM_CONTENT_TYPE)
        self.assertEqual(json.loads(response.content)["code"], "bad_request")

    def test_a_request_django_cannot_read_is_a_400_problem(self) -> None:
        for error in (RequestDataTooBig("big"), TooManyFieldsSent("many"), BadRequest("bad"), MultiPartParserError("parts")):
            with self.subTest(error=type(error).__name__):
                response = api_module.api.on_exception(HttpRequest(), error)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(json.loads(response.content)["code"], "bad_request")


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
