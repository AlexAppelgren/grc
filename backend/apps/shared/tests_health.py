"""Guard: health (playbook 5, 2.2).

`/health/` answers 200 with every component ok (database, pgvector, cache, worker), 503
with the failing component named, and the worker ping is bounded (`limit=1`) with the
timeout from settings. The worker ping is patched: the suite has no worker and no
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


class HealthGuard(TestCase):
    def test_200_with_every_component_ok(self) -> None:
        with mock.patch("config.celery.app.control.ping", return_value=PONG) as ping:
            response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["failing"], [])
        self.assertEqual(set(body["components"]), {"database", "pgvector", "cache", "worker"})
        self.assertTrue(all(c["ok"] for c in body["components"].values()))
        self.assertIn("vector", body["components"]["pgvector"]["detail"])
        self.assertEqual(response["Cache-Control"], "no-store")
        ping.assert_called_once()
        self.assertEqual(ping.call_args.kwargs["limit"], 1)

    @override_settings(HEALTH_WORKER_PING_TIMEOUT_S=0.25)
    def test_the_ping_timeout_is_a_setting(self) -> None:
        with mock.patch("config.celery.app.control.ping", return_value=PONG) as ping:
            self.client.get("/health/")
        self.assertEqual(ping.call_args.kwargs["timeout"], 0.25)

    def test_503_names_the_worker_when_nothing_answers(self) -> None:
        with mock.patch("config.celery.app.control.ping", return_value=[]):
            response = self.client.get("/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["failing"], ["worker"])
        self.assertEqual(response.json()["status"], "degraded")

    def test_503_names_the_worker_when_the_broker_is_down(self) -> None:
        with mock.patch("config.celery.app.control.ping", side_effect=OSError("broker down")):
            response = self.client.get("/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["components"]["worker"]["detail"], "OSError")

    def test_503_names_the_database_when_it_fails(self) -> None:
        def broken_database() -> ComponentStatus:
            return ComponentStatus("database", False, "OperationalError")

        checks = (broken_database, health_check.check_pgvector, health_check.check_cache, health_check.check_worker)
        with mock.patch.object(health_check, "CHECKS", checks), mock.patch(
            "config.celery.app.control.ping", return_value=PONG
        ):
            response = self.client.get("/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["failing"], ["database"])

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
