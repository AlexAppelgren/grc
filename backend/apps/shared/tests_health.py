"""Guard: health (playbook 5, 2.2).

`/health/` answers 200 with every component ok (database, pgvector, cache, worker) and 503
otherwise, with the status alone in the body and the failing component named in the log
only, reuses a result for HEALTH_CACHE_SECONDS, and the worker ping is bounded (`limit=1`)
with the timeout from settings. The worker ping is patched: the suite has no worker and no
broker; the other three checks run for real against the test database and the locmem
cache.

Proven to fail 2026-09-19 by dropping `limit=` from the ping call: the test asserted
the keyword.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase, override_settings

from apps.shared import health_check
from apps.shared.health_check import ComponentStatus

PONG = [{"worker@host": {"ok": "pong"}}]


@override_settings(HEALTH_CACHE_SECONDS=0)
class HealthGuard(TestCase):
    def setUp(self) -> None:
        health_check._last = None

    def test_200_with_every_component_ok(self) -> None:
        with mock.patch("config.celery.app.control.ping", return_value=PONG) as ping:
            response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response["Cache-Control"], "no-store")
        ping.assert_called_once()
        self.assertEqual(ping.call_args.kwargs["limit"], 1)

    def test_the_body_names_no_component_and_the_log_does(self) -> None:
        """Review 2026-11-11 L-8: the open route named the pgvector version and exception
        classes. The status is all a caller sees; the operator reads the log."""
        with mock.patch("config.celery.app.control.ping", side_effect=OSError("broker down")), self.assertLogs(
            "apps.shared.health_check", "WARNING"
        ) as logs:
            response = self.client.get("/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "degraded"})
        self.assertEqual(logs.records[0].failing, {"worker": "OSError"})  # type: ignore[attr-defined]

    @override_settings(HEALTH_CACHE_SECONDS=5)
    def test_a_result_is_reused_for_the_configured_seconds(self) -> None:
        """Review 2026-11-11 L-8: every call pinged the worker and queried the database."""
        with mock.patch("config.celery.app.control.ping", return_value=PONG) as ping:
            for _ in range(3):
                self.assertEqual(self.client.get("/health/").status_code, 200)
            self.assertEqual(ping.call_count, 1)
            with mock.patch.object(health_check.time, "monotonic", return_value=health_check.time.monotonic() + 6):
                self.client.get("/health/")
            self.assertEqual(ping.call_count, 2)

    @override_settings(HEALTH_WORKER_PING_TIMEOUT_S=0.25)
    def test_the_ping_timeout_is_a_setting(self) -> None:
        with mock.patch("config.celery.app.control.ping", return_value=PONG) as ping:
            self.client.get("/health/")
        self.assertEqual(ping.call_args.kwargs["timeout"], 0.25)

    def test_503_when_no_worker_answers(self) -> None:
        with mock.patch("config.celery.app.control.ping", return_value=[]), self.assertLogs(
            "apps.shared.health_check", "WARNING"
        ) as logs:
            response = self.client.get("/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(logs.records[0].failing, {"worker": "no worker answered the ping"})  # type: ignore[attr-defined]

    def test_503_when_the_database_fails(self) -> None:
        def broken_database() -> ComponentStatus:
            return ComponentStatus("database", False, "OperationalError")

        checks = (broken_database, health_check.check_pgvector, health_check.check_cache, health_check.check_worker)
        with mock.patch.object(health_check, "CHECKS", checks), mock.patch(
            "config.celery.app.control.ping", return_value=PONG
        ), self.assertLogs("apps.shared.health_check", "WARNING") as logs:
            response = self.client.get("/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(logs.records[0].failing, {"database": "OperationalError"})  # type: ignore[attr-defined]

    def test_pgvector_check_names_the_installed_version(self) -> None:
        self.assertIn("vector", health_check.check_pgvector().detail)

    def test_pgvector_check_reports_a_missing_extension(self) -> None:
        with mock.patch("apps.shared.health_check.connections") as connections:
            cursor = connections.__getitem__.return_value.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = None
            status = health_check.check_pgvector()
        self.assertFalse(status.ok)
        self.assertIn("not installed", status.detail)

    def test_cache_check_reports_a_value_that_does_not_round_trip(self) -> None:
        with mock.patch("apps.shared.health_check.cache") as cache:
            cache.get.return_value = None
            status = health_check.check_cache()
        self.assertFalse(status.ok)

    def test_only_get_is_allowed(self) -> None:
        response = self.client.post("/health/")
        self.assertEqual(response.status_code, 405)
