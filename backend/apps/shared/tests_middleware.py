"""Request ID, Server-Timing, CSP and the Sentry scrubbers (playbook 4.7, 10, 11.2).

The middleware classes are exercised directly (test_settings strips CORS and CSP from
the stack, override 9) and through the client where the runner keeps them.
"""

from __future__ import annotations

import copy
import json
import logging
import sys
from typing import Any, cast

from django.db import IntegrityError
from django.http import HttpRequest, HttpResponse
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.client import RequestFactory
from sentry_sdk.integrations import logging as sentry_logging
from sentry_sdk.utils import event_from_exception

from apps.shared import middleware, sentry_scrub
from apps.shared.logging import JsonFormatter
from apps.shared.testing import sentry_init_kwargs


class RequestId(TestCase):
    def test_a_supplied_request_id_is_echoed_and_a_missing_one_is_minted(self) -> None:
        response = self.client.get("/api/v1/reference/product", HTTP_X_REQUEST_ID="abc-123")
        self.assertEqual(response["X-Request-ID"], "abc-123")
        response = self.client.get("/api/v1/reference/product")
        self.assertEqual(len(response["X-Request-ID"]), 32)

    def test_a_hostile_request_id_is_replaced(self) -> None:
        response = self.client.get("/api/v1/reference/product", HTTP_X_REQUEST_ID="x\ninjected")
        self.assertNotIn("\n", response["X-Request-ID"])
        response = self.client.get("/api/v1/reference/product", HTTP_X_REQUEST_ID="a" * 300)
        self.assertEqual(len(response["X-Request-ID"]), 32)

    def test_log_records_carry_the_request_id(self) -> None:
        captured: list[logging.LogRecord] = []

        class Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured.append(record)

        handler = Capture()
        handler.addFilter(middleware.RequestIdLogFilter())
        logger = logging.getLogger("apps.shared.tests_middleware")
        logger.addHandler(handler)
        try:

            def view(request: object) -> HttpResponse:
                logger.warning("inside")
                return HttpResponse("ok")

            request = RequestFactory().get("/", HTTP_X_REQUEST_ID="req-1")
            middleware.RequestIdMiddleware(view)(request)
        finally:
            logger.removeHandler(handler)
        self.assertEqual(getattr(captured[-1], "request_id"), "req-1")  # noqa: B009
        self.assertIsNone(middleware.current_request_id())
        formatter = JsonFormatter()
        line = formatter.format(captured[-1])
        self.assertIn('"request_id": "req-1"', line)
        self.assertIn('"level": "WARNING"', line)


class ServerTiming(TestCase):
    def test_every_response_carries_app_timing(self) -> None:
        response = self.client.get("/api/v1/reference/product")
        self.assertRegex(response["Server-Timing"], r"^app;dur=\d+\.\d$")

    @override_settings(API_BUDGET_MS=0)
    def test_over_budget_logs_a_warning_with_the_route_only(self) -> None:
        with self.assertLogs("apps.shared.middleware", level="WARNING") as logs:
            self.client.get("/api/v1/reference/product?secret=1")
        record = logs.records[0]
        self.assertIn("reference/product", getattr(record, "route"))  # noqa: B009
        self.assertFalse(hasattr(record, "path"))
        self.assertEqual(getattr(record, "budget_ms"), 0)  # noqa: B009
        self.assertNotIn("secret", record.getMessage())

    @override_settings(API_BUDGET_MS=0)
    def test_over_budget_never_logs_a_path_parameter(self) -> None:
        """Security review 2026-09-19, finding F6: a path parameter can carry a value a
        caller chose, so the over-budget warning logs the matched route, not the concrete
        path, and a 404 logs no more than the first two segments. (The invitation token
        left every path with F29; this guards the rule for any later path parameter.)"""
        token = "secret-value-123"
        with self.assertLogs("apps.shared.middleware", level="WARNING") as logs:
            self.client.get(f"/api/v1/vocab/tenant_tag/{token}")
        route = getattr(logs.records[0], "route")  # noqa: B009
        self.assertNotIn(token, route)
        self.assertIn("vocab", route)
        with self.assertLogs("apps.shared.middleware", level="WARNING") as logs:
            self.client.get(f"/no/such/{token}")
        self.assertNotIn(token, getattr(logs.records[0], "route"))  # noqa: B009


class ContentSecurityPolicy(SimpleTestCase):
    def _run(self, path: str) -> HttpResponse:
        request = RequestFactory().get(path)
        return middleware.ContentSecurityPolicyMiddleware(lambda r: HttpResponse("ok"))(request)

    def test_the_strict_policy_is_set_by_default(self) -> None:
        response = self._run("/api/v1/me")
        self.assertIn("default-src 'none'", response["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", response["Content-Security-Policy"])

    def test_every_response_carries_no_referrer_and_nosniff(self) -> None:
        """Security review 2026-09-19, F28 (backend half): the invitation token is a URL
        segment on the web app, so the API never lets a referrer out, and nothing it
        answers may be sniffed into another content type."""
        from django.conf import settings

        response = self._run("/api/v1/reference/product")
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(settings.SECURE_REFERRER_POLICY, "no-referrer")
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        request = RequestFactory().get("/api/v1/me")

        def already_set(_request: HttpRequest) -> HttpResponse:
            answer = HttpResponse("ok")
            answer["Referrer-Policy"] = "same-origin"
            return answer

        self.assertEqual(middleware.ContentSecurityPolicyMiddleware(already_set)(request)["Referrer-Policy"], "same-origin")

    @override_settings(CONTENT_SECURITY_POLICY_DOCS_PREFIXES=("/api/v1/docs",))
    def test_the_docs_page_gets_the_relaxed_policy(self) -> None:
        response = self._run("/api/v1/docs")
        self.assertIn("cdn.jsdelivr.net", response["Content-Security-Policy"])

    def test_an_existing_header_is_kept(self) -> None:
        def view(request: object) -> HttpResponse:
            response = HttpResponse("ok")
            response["Content-Security-Policy"] = "custom"
            return response

        request = RequestFactory().get("/")
        self.assertEqual(middleware.ContentSecurityPolicyMiddleware(view)(request)["Content-Security-Policy"], "custom")


class SentryScrubbers(SimpleTestCase):
    def _event(self) -> dict:
        return {
            "request": {
                "headers": {"Authorization": "Bearer x", "X-API-Key": "k", "Accept": "json"},
                "cookies": {"refresh": "r"},
                "data": {"assessment": "confidential"},
                "query_string": "q=1",
            },
            "user": {"id": "u1", "email": "a@b.c", "ip_address": "1.2.3.4"},
            "extra": {"summary": "tenant text", "record_id": "r1", "nested": {"comment": "x", "ok": 1}},
            "breadcrumbs": {"values": [{"data": {"question": "asked", "path": "/x"}}]},
        }

    def test_before_send_and_before_send_transaction_scrub_the_same_way(self) -> None:
        for hook in (sentry_scrub.before_send, sentry_scrub.before_send_transaction):
            event = cast(dict, hook(cast(Any, self._event()), {}))
            self.assertEqual(event["request"]["headers"]["Authorization"], sentry_scrub.REDACTED)
            self.assertEqual(event["request"]["headers"]["X-API-Key"], sentry_scrub.REDACTED)
            self.assertEqual(event["request"]["headers"]["Accept"], "json")
            self.assertEqual(event["request"]["cookies"], sentry_scrub.REDACTED)
            self.assertEqual(event["request"]["data"], sentry_scrub.REDACTED)
            self.assertEqual(event["user"], {"id": "u1"})
            self.assertEqual(event["extra"]["summary"], sentry_scrub.REDACTED)
            self.assertEqual(event["extra"]["record_id"], "r1")
            self.assertEqual(event["extra"]["nested"], {"comment": sentry_scrub.REDACTED, "ok": 1})
            self.assertEqual(event["breadcrumbs"]["values"][0]["data"]["question"], sentry_scrub.REDACTED)

    def test_the_invitation_token_never_leaves_in_the_request_url(self) -> None:
        """Security review 2026-09-19, finding F6: `request.url` is not covered by
        `max_request_body_size`, and the invitation path carries the single-use token."""
        event = self._event()
        event["request"]["url"] = "https://api.example/api/v1/auth/invitations/tok-123_abc/open"
        for hook in (sentry_scrub.before_send, sentry_scrub.before_send_transaction):
            scrubbed = cast(dict, hook(cast(Any, dict(event, request=dict(event["request"]))), {}))
            self.assertEqual(scrubbed["request"]["url"], f"https://api.example/api/v1/auth/invitations/{sentry_scrub.REDACTED}/open")
        self.assertEqual(sentry_scrub.scrub_url("https://api.example/api/v1/reference/product?x=1"), "https://api.example/api/v1/reference/product?x=1")

    def test_an_access_line_breadcrumb_loses_its_query_and_addresses(self) -> None:
        """Security review 2026-09-19: gunicorn's access line reached a captured event as a
        breadcrumb message, search text and client address included. The logger is ignored
        now (below); the message is scrubbed as well, whatever logger wrote it."""
        message = (
            '203.0.113.7 - - [19/Sep/2026:09:00:00 +0000] "GET /api/v1/obligations?q=secret+text HTTP/1.1" '
            '200 512 "https://app.example/inventory?q=secret+text" "Mozilla/5.0" from 2001:db8::7 via ::1 '
            "and ::ffff:198.51.100.9."
        )
        for hook in (sentry_scrub.before_send, sentry_scrub.before_send_transaction):
            event = {
                "breadcrumbs": {
                    "values": [
                        {"category": "gunicorn.access", "message": message, "data": {}},
                        {"category": "django", "message": "Not Found: /api/v1/x", "data": {"request": "<WSGIRequest: GET '/api/v1/x?q=secret'>"}},
                    ]
                }
            }
            crumbs = cast(dict, hook(cast(Any, event), {}))["breadcrumbs"]["values"]
            scrubbed = crumbs[0]["message"]
            self.assertIn("GET /api/v1/obligations", scrubbed)
            for leaked in ("secret", "203.0.113.7", "2001:db8::7", "::1", "51.100.9"):
                self.assertNotIn(leaked, scrubbed)
            self.assertEqual(crumbs[1]["message"], "Not Found: /api/v1/x")
            self.assertEqual(crumbs[1]["data"]["request"], sentry_scrub.REDACTED)

    def test_settings_initialise_sentry_with_the_safe_flags_only_when_a_dsn_is_set(self) -> None:
        kwargs = sentry_init_kwargs()
        self.assertFalse(kwargs["send_default_pii"])
        self.assertEqual(kwargs["max_request_body_size"], "never")
        self.assertFalse(kwargs["include_local_variables"])
        self.assertIs(kwargs["before_send"], sentry_scrub.before_send)
        self.assertIs(kwargs["before_send_transaction"], sentry_scrub.before_send_transaction)
        # gunicorn writes its access line outside any request scope, so as a breadcrumb it
        # rides on later events, another tenant's included. It is never recorded.
        self.assertIn("gunicorn.access", sentry_logging._IGNORED_LOGGERS)

    def test_exception_messages_and_interpolated_log_text_never_leave(self) -> None:
        """Security review 2026-09-19: a Postgres error's message carries row values
        (`DETAIL: Failing row contains (...)`, every column), and exception values went out
        untouched. The type, module and frames stay: they say where, never what."""
        secret = "tenant-" + "secret-row"  # built, so no source line the frames quote holds it
        options = {
            "include_local_variables": sentry_init_kwargs()["include_local_variables"],
            "include_source_context": True,
            "max_value_length": 1024,
        }

        def insert(row: str) -> None:
            try:
                raise ValueError(f"invalid input value: {row}")
            except ValueError as exc:
                raise IntegrityError(f'null value in column "title"\nDETAIL:  Failing row contains ({row}).') from exc

        try:
            insert(secret)
        except IntegrityError:
            event, _ = event_from_exception(sys.exc_info(), client_options=options)
        event["logentry"] = {"message": "Task %s raised: %r", "formatted": f"Task t1 raised: {secret!r}", "params": ["t1", secret]}
        for hook in (sentry_scrub.before_send, sentry_scrub.before_send_transaction):
            scrubbed = cast(dict, hook(cast(Any, copy.deepcopy(event)), {}))
            self.assertNotIn(secret, json.dumps(scrubbed, default=str))
            values = scrubbed["exception"]["values"]
            self.assertEqual([value["type"] for value in values], ["ValueError", "IntegrityError"])
            self.assertEqual({value["value"] for value in values}, {sentry_scrub.REDACTED})
            self.assertTrue(all(value["stacktrace"]["frames"] for value in values))
            self.assertEqual(scrubbed["logentry"], {"message": "Task %s raised: %r"})

