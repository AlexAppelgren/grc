"""The performance harness (NFR-02, playbook 10): backend/perf/harness.py measures one
route and backend/scripts/perf_report.py judges the list. They live outside apps/ so the
product never imports them; the proofs live here so `manage.py test apps` runs them.

Most proofs drive planted routes of a throwaway API mounted where the real one is, because
a harness that must fail a slow route, time a stream to its first chunk and count an N+1
needs routes that are slow, streamed and N+1 on purpose. The rest drive the real API as a
real person, and prove that nothing a measurement writes outlives it.

Proven to fail 2026-09-23 by timing the warm-up with the samples (the warm-up test saw the
300 ms request as the 95th percentile), by timing a stream to its headers alone (the
first-chunk test measured 2.4 ms) and by committing the harness's transaction instead of
rolling it back (the rollback tests found the session, its audit row and the planted banks).
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest import mock

from django.conf import settings
from django.http import HttpRequest, StreamingHttpResponse
from django.test import TestCase, override_settings
from django.urls import path
from ninja import NinjaAPI

from apps.identity.models import UserSession
from apps.shared import factories, tenancy
from apps.shared.models import AuditEvent, Tenant
from perf import harness
from perf.harness import Call, PerfRefused, PerfRoute, RouteFailed, anonymous, measure, person

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "backend" / "scripts" / "perf_report.py"
SETTINGS = ("API_BUDGET_MS", "SEARCH_BUDGET_MS", "SEARCH_RERANKED_BUDGET_MS", "ASK_FIRST_TOKEN_BUDGET_MS", "PERF_SAMPLES", "PERF_REGRESSION_PCT")
SAMPLES = 5  # PERF_SAMPLES in these tests: enough for a median and a 95th percentile, and quick


class Planted:
    """What the planted routes do, and what they saw. Reset before every test."""

    calls = 0
    delays_ms: list[float] = []  # one per request, in order; once empty, `steady_ms`
    steady_ms = 0.0


PLANTED = NinjaAPI(urls_namespace="perf-planted")


@PLANTED.get("/planted/sleep", operation_id="plantedSleep")
def planted_sleep(request: HttpRequest) -> dict[str, bool]:
    Planted.calls += 1
    time.sleep((Planted.delays_ms.pop(0) if Planted.delays_ms else Planted.steady_ms) / 1000)
    return {"ok": True}


@PLANTED.get("/planted/stream", operation_id="plantedStream")
def planted_stream(request: HttpRequest) -> StreamingHttpResponse:
    def body() -> Iterator[bytes]:
        time.sleep(0.04)
        yield b"first"
        time.sleep(0.15)
        yield b"rest"

    return StreamingHttpResponse(body(), content_type="text/plain")


@PLANTED.get("/planted/banks", operation_id="plantedBanks")
def planted_banks(request: HttpRequest, prefix: str) -> dict[str, list[str]]:
    """The N+1: one query for the list and one more for every row in it."""
    ids = Tenant.objects.filter(slug__startswith=prefix).order_by("slug").values_list("id", flat=True)
    return {"names": [Tenant.objects.get(id=bank_id).name for bank_id in ids]}


@PLANTED.post("/planted/banks/{slug}", operation_id="plantedWrite", response={201: dict[str, bool]})
def planted_write(request: HttpRequest, slug: str) -> tuple[int, dict[str, bool]]:
    Tenant.objects.get_or_create(slug=slug, defaults={"name": "Planted"})
    return 201, {"ok": True}


urlpatterns = [path("api/v1/", PLANTED.urls)]


def load_report() -> ModuleType:
    spec = importlib.util.spec_from_file_location("perf_report_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def banks(prefix: str, count: int) -> Call:
    """A fixture that writes `count` banks inside the measurement and asks for them."""
    for n in range(count):
        Tenant.objects.create(name=f"Bank {n}", slug=f"{prefix}-{n}")
    return Call(query={"prefix": prefix})


@override_settings(ROOT_URLCONF=__name__, PERF_SAMPLES=SAMPLES)
class PlantedRoutes(TestCase):
    """Runs against the planted API, which the harness resolves operation ids in."""

    def setUp(self) -> None:
        Planted.calls, Planted.delays_ms, Planted.steady_ms = 0, [], 0.0
        patcher = mock.patch.object(harness, "api", PLANTED)
        patcher.start()
        self.addCleanup(patcher.stop)


class HarnessMeasures(PlantedRoutes):
    @override_settings(API_BUDGET_MS=250)
    def test_the_warm_up_is_dropped_and_the_median_and_p95_come_from_server_timing(self) -> None:
        Planted.delays_ms = [300, 10, 10, 10, 10, 60]

        # The warm-up is a real request: the middleware logs it over the 250 ms budget.
        with self.assertLogs("apps.shared.middleware", "WARNING"):
            result = measure(PerfRoute("plantedSleep", anonymous))

        self.assertEqual(Planted.calls, SAMPLES + 1, "one warm-up and the samples")
        self.assertEqual((result.operation, result.budget, result.budget_ms), ("plantedSleep", "API_BUDGET_MS", 250))
        self.assertGreaterEqual(result.median_ms, 9)
        self.assertLess(result.median_ms, 55, "the median is the middle sample, not the slow one")
        self.assertGreaterEqual(result.p95_ms, 55, "the 95th percentile of five is the slowest of them")
        self.assertLess(result.p95_ms, 300, "and the 300 ms warm-up is none of them")

    def test_a_stream_is_timed_to_its_first_chunk(self) -> None:
        result = measure(PerfRoute("plantedStream", anonymous, budget="ASK_FIRST_TOKEN_BUDGET_MS"))

        self.assertGreaterEqual(result.median_ms, 35, "the headers leave before the first chunk is written")
        self.assertLess(result.median_ms, 150, "and the rest of the stream is not the first token")
        self.assertEqual(result.budget_ms, settings.ASK_FIRST_TOKEN_BUDGET_MS)

    def test_the_query_count_catches_an_n_plus_one(self) -> None:
        two = measure(PerfRoute("plantedBanks", anonymous, fixture=lambda: banks("perf-n1-a", 2)))
        five = measure(PerfRoute("plantedBanks", anonymous, fixture=lambda: banks("perf-n1-b", 5)))

        self.assertGreater(two.queries, 2)
        self.assertEqual(five.queries - two.queries, 3, "one more query for every row: the N+1 shows in the count")

    def test_what_the_fixture_and_the_route_write_is_rolled_back(self) -> None:
        measure(PerfRoute("plantedBanks", anonymous, fixture=lambda: banks("perf-kept", 3)))
        measure(PerfRoute("plantedWrite", anonymous, fixture=lambda: Call(params={"slug": "perf-written"}), status=201))

        self.assertFalse(Tenant.objects.filter(slug__startswith="perf-kept").exists(), "the fixture's rows")
        self.assertFalse(Tenant.objects.filter(slug="perf-written").exists(), "the route's own write")

    def test_a_route_answering_another_status_fails_instead_of_being_timed(self) -> None:
        with self.assertRaisesMessage(RouteFailed, "plantedWrite answered 201, not 200"):
            measure(PerfRoute("plantedWrite", anonymous, fixture=lambda: Call(params={"slug": "perf-status"})))

    def test_an_operation_the_api_does_not_have_fails(self) -> None:
        with self.assertRaisesMessage(RouteFailed, "getNothing is not an operation of the API"):
            measure(PerfRoute("getNothing", anonymous))

    @override_settings(IS_DEPLOYED_ENVIRONMENT=True, ENVIRONMENT="prod")
    def test_it_refuses_a_deployed_environment_before_doing_anything(self) -> None:
        principal = mock.Mock(return_value={})

        with self.assertRaisesMessage(PerfRefused, "'prod'"):
            measure(PerfRoute("plantedSleep", principal))

        principal.assert_not_called()
        self.assertEqual(Planted.calls, 0)


@override_settings(PERF_SAMPLES=SAMPLES)
class HarnessOnTheRealApi(TestCase):
    """The real API, the real middleware and a real session, as the report runs them."""

    tenant: Tenant
    email: str

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = factories.tenant(slug="perf-bank")
        cls.email = factories.member_user(cls.tenant, roles=("reader",)).email

    def written(self) -> tuple[int, int]:
        tenancy.activate(self.tenant.id)
        return UserSession.objects.filter(user__email=self.email).count(), AuditEvent.objects.count()

    def test_a_person_s_route_is_measured_and_their_session_does_not_outlive_it(self) -> None:
        before = self.written()

        result = measure(PerfRoute("getMe", person(self.email, "perf-bank")))

        self.assertGreater(result.queries, 0)
        self.assertGreater(result.median_ms, 0)
        self.assertLessEqual(result.median_ms, result.p95_ms)
        self.assertEqual(self.written(), before, "the session the harness minted, and its audit row, are rolled back")

    def test_a_refused_request_is_not_a_measurement(self) -> None:
        with self.assertRaisesMessage(RouteFailed, "getMe answered 401, not 200"), self.assertLogs("django.request", "WARNING"):
            measure(PerfRoute("getMe", anonymous))

    def test_a_person_the_database_does_not_hold_names_the_seed(self) -> None:
        with self.assertRaisesMessage(RouteFailed, "seed it with manage.py seed_e2e"):
            measure(PerfRoute("getMe", person("nobody@example-bank.test", "perf-bank")))

    def test_the_seeded_route_list_names_real_operations(self) -> None:
        from apps.shared.routes import iter_operations
        from config.api import api
        from perf.routes import ROUTES

        operations = {registered.operation_id for registered in iter_operations(api)}
        names = [route.operation for route in ROUTES]
        self.assertTrue(ROUTES)
        self.assertEqual([name for name in names if name not in operations], [])
        self.assertEqual(len(names), len(set(names)), "one row per operation: the baseline is keyed on it")

    def test_every_setting_has_an_env_override_and_is_documented(self) -> None:
        settings_source = (ROOT / "backend" / "config" / "settings.py").read_text(encoding="utf-8")
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        runbook = (ROOT / "docs" / "runbooks" / "RAILWAY_VARIABLES.md").read_text(encoding="utf-8")
        missing = [
            name
            for name in SETTINGS
            if f'{name} = env_int("{name}"' not in settings_source or f"{name}=" not in example or f"`{name}`" not in runbook
        ]
        self.assertEqual(missing, [], "each needs env_int in settings.py, a .env.example line and a runbook row")
        self.assertIn('ASK_FIRST_TOKEN_BUDGET_MS = env_int("ASK_FIRST_TOKEN_BUDGET_MS", 2000)', settings_source, "playbook 10")


@override_settings(API_BUDGET_MS=250, PERF_REGRESSION_PCT=20)
class ReportJudges(PlantedRoutes):
    """scripts/perf_report.py over planted rows and a baseline in a temporary directory."""

    route = PerfRoute("plantedSleep", anonymous)

    def setUp(self) -> None:
        super().setUp()
        self.report = load_report().report
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.baseline = Path(directory.name) / "baseline.json"

    def run_report(self, routes: list[PerfRoute], *, record: bool = False) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = self.report(routes, record=record, baseline_path=self.baseline)
        return code, output.getvalue()

    def recorded(self, median_ms: float) -> None:
        self.baseline.write_text(json.dumps({"plantedSleep": {"medianMs": median_ms, "p95Ms": median_ms, "queries": 0}}), encoding="utf-8")

    def test_record_writes_the_baseline_and_exits_zero(self) -> None:
        Planted.steady_ms = 20

        code, output = self.run_report([self.route], record=True)

        self.assertEqual(code, 0, output)
        entry: dict[str, Any] = json.loads(self.baseline.read_text(encoding="utf-8"))["plantedSleep"]
        self.assertEqual(set(entry), {"medianMs", "p95Ms", "queries"})
        self.assertGreaterEqual(entry["medianMs"], 18)
        self.assertIn("plantedSleep: median", output)

    def test_an_unchanged_route_passes_and_the_line_names_what_to_fix(self) -> None:
        Planted.steady_ms = 40
        self.recorded(40)

        code, output = self.run_report([self.route])

        self.assertEqual(code, 0, output)
        self.assertRegex(output, r"plantedSleep: median \d+\.\d ms, p95 \d+\.\d ms, budget 250 ms \(API_BUDGET_MS\), \d+ queries: ok")

    def test_a_route_25_percent_slower_than_its_baseline_fails(self) -> None:
        Planted.steady_ms = 50
        self.recorded(40)

        code, output = self.run_report([self.route])

        self.assertEqual(code, 1, output)
        self.assertIn("median is more than 20 % above its baseline of 40 ms", output)

    @override_settings(API_BUDGET_MS=20)
    def test_a_route_over_its_budget_fails(self) -> None:
        Planted.steady_ms = 40
        self.recorded(40)

        with self.assertLogs("apps.shared.middleware", "WARNING"):
            code, output = self.run_report([self.route])

        self.assertEqual(code, 1, output)
        self.assertIn("p95 is over the 20 ms budget", output)
        self.assertNotIn("baseline of", output, "only the budget failed")

    def test_a_route_with_no_baseline_fails(self) -> None:
        code, output = self.run_report([self.route])

        self.assertEqual(code, 1, output)
        self.assertIn("no baseline yet: record one with --record", output)

    def test_a_route_that_cannot_be_measured_fails_the_run_and_record_writes_nothing(self) -> None:
        broken = PerfRoute("plantedWrite", anonymous, fixture=lambda: Call(params={"slug": "perf-broken"}))

        code, output = self.run_report([self.route, broken], record=True)

        self.assertEqual(code, 1, output)
        self.assertIn("plantedWrite: FAIL plantedWrite answered 201, not 200", output)
        self.assertFalse(self.baseline.exists(), "a baseline never has a hole in it")

    @override_settings(IS_DEPLOYED_ENVIRONMENT=True)
    def test_the_report_refuses_a_deployed_environment(self) -> None:
        code, output = self.run_report([self.route], record=True)

        self.assertEqual(code, 1)
        self.assertIn("Refusing to measure on the deployed environment", output)
        self.assertEqual(Planted.calls, 0)
        self.assertFalse(self.baseline.exists())
