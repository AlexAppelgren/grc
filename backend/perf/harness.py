"""One way to measure an API route against its budget (NFR-02, playbook 10).

`measure(route)` drives one operation of the API in process, through the whole middleware
stack, as the person its principal factory signs in, against the database the settings name
(the slot a task loaded, seeded with `manage.py seed_e2e`). It sends one warm-up request and
drops it, because the first call pays for imports, a cold connection and cold caches that no
reader pays twice, then takes `PERF_SAMPLES` timed requests and reports:

- the median and the 95th percentile (nearest rank) of the `Server-Timing: app` value the
  middleware writes on every response, which is the number every budget is stated in. For a
  streamed answer it is that value plus the wait for the first chunk: a stream's headers
  leave before any of its body is written, and Ask's budget is its first token;
- the most queries any one sample ran, from `CaptureQueriesContext`, so an N+1 shows as a
  count that grows with the data. The count includes the savepoint a request opens inside
  the harness's transaction.

Everything runs inside one transaction that is rolled back, principal and fixture included:
the session the harness mints, the audit row that session writes and whatever the route
writes are gone when `measure` returns. Each request also runs in a savepoint of its own
that is rolled back, so every sample starts from the seeded state plus the fixture: a
reject, a create or an If-Match update answers the twentieth time as it did the first.

A response with any status but the one its row expects fails the route, because a fast 401
or 429 is not a measurement; an exception that escapes the route arrives as a 500 and fails
it the same way. So does a row that names a budget no setting holds or leaves a path
parameter unfilled, before any request is sent. The harness reads a budget and never changes
one, and it refuses to run where `IS_DEPLOYED_ENVIRONMENT` is true or with fewer than one
sample.
"""

from __future__ import annotations

import json
import math
import statistics
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import partial
from typing import Any
from urllib.parse import quote, urlencode

from django.conf import settings
from django.db import connection, transaction
from django.http import HttpResponseBase, StreamingHttpResponse
from django.test import Client
from django.test.utils import CaptureQueriesContext

from apps.identity.models import User
from apps.shared.models import Tenant
from apps.shared.routes import iter_operations
from apps.shared.testing import sign_in
from config.api import api

# Where config/urls.py mounts the API; iter_operations() gives each path below it.
API_PREFIX = "/api/v1"

# Returns the request headers of whoever calls the route.
PrincipalFactory = Callable[[], dict[str, Any]]


class PerfRefused(RuntimeError):
    """The harness was asked to measure on a deployed environment, or with fewer than one
    sample: nothing it could report would be a measurement."""


class RouteFailed(RuntimeError):
    """A route could not be measured: no such operation, a budget no setting holds, a path
    parameter the fixture left out, a principal the database does not hold, or a response
    with another status than the one its row expects."""


@dataclass(frozen=True)
class Call:
    """What every request of one measurement sends: the values of the path's
    `{placeholders}`, the query string and a JSON body."""

    params: Mapping[str, object] = field(default_factory=dict)
    query: Mapping[str, str] = field(default_factory=dict)
    body: object = None


@dataclass(frozen=True)
class PerfRoute:
    """One row of the measured route list (perf/routes.py)."""

    operation: str  # its operationId in openapi.json
    principal: PrincipalFactory
    # Runs inside the rolled-back transaction after the principal signed in, so it can look
    # up seeded rows or write rows of its own.
    fixture: Callable[[], Call] = Call
    budget: str = "API_BUDGET_MS"  # the name of the setting that holds the budget
    status: int = 200


@dataclass(frozen=True)
class Measurement:
    operation: str
    median_ms: float
    p95_ms: float
    queries: int
    budget: str
    budget_ms: int


def person(email: str, tenant: str | None = None) -> PrincipalFactory:
    """A real session of the person `email` in the bank whose slug is `tenant`, or in none
    for platform staff: the tokens a passkey sign-in hands out, minted inside the harness's
    transaction and rolled back with it."""

    def headers() -> dict[str, Any]:
        user = User.objects.filter(email=email).first()
        bank = Tenant.objects.filter(slug=tenant).first() if tenant else None
        if user is None or (tenant and bank is None):
            raise RouteFailed(f"{email} in {tenant or 'the platform'} is not in this database: seed it with manage.py seed_e2e")
        return sign_in(user, tenant=bank)

    return headers


def anonymous() -> dict[str, Any]:
    """A caller with no session and no key."""
    return {}


def measure(route: PerfRoute) -> Measurement:
    if settings.IS_DEPLOYED_ENVIRONMENT:
        raise PerfRefused(f"Refusing to measure on the deployed environment {settings.ENVIRONMENT!r}: the harness is local tooling.")
    if settings.PERF_SAMPLES < 1:
        raise PerfRefused(f"PERF_SAMPLES is {settings.PERF_SAMPLES}: a measurement needs at least one sample.")
    method, path = _resolve(route.operation)
    budget_ms = getattr(settings, route.budget, None)
    if not isinstance(budget_ms, int):
        raise RouteFailed(f"{route.operation} names {route.budget} as its budget, which is not a setting in milliseconds")
    timings: list[float] = []
    counts: list[int] = []
    with transaction.atomic():
        try:
            headers = route.principal()
            call = route.fixture()
            try:
                filled = path.format_map({name: quote(str(value), safe="") for name, value in call.params.items()})
            except KeyError as missing:
                raise RouteFailed(f"{route.operation} needs the path parameter {missing} in its fixture's Call.params") from None
            url = API_PREFIX + filled
            if call.query:
                url += "?" + urlencode(call.query)
            data = "" if call.body is None else json.dumps(call.body)
            # An exception that escapes the route becomes the 500 a caller would get, which
            # fails this row instead of ending the whole report with a traceback.
            client = Client(raise_request_exception=False)
            send = partial(client.generic, method, url, data=data, content_type="application/json", **headers)
            for sample in range(settings.PERF_SAMPLES + 1):  # sample 0 is the warm-up, dropped
                with transaction.atomic():  # rolled back: the next request finds what this one found
                    with CaptureQueriesContext(connection) as queries:
                        elapsed = _elapsed(send(), route)
                    transaction.set_rollback(True)
                if sample:
                    timings.append(elapsed)
                    counts.append(len(queries.captured_queries))
        finally:
            transaction.set_rollback(True)
    ordered = sorted(timings)
    return Measurement(
        operation=route.operation,
        median_ms=statistics.median(ordered),
        p95_ms=ordered[math.ceil(0.95 * len(ordered)) - 1],
        queries=max(counts),
        budget=route.budget,
        budget_ms=budget_ms,
    )


def _resolve(operation: str) -> tuple[str, str]:
    for registered in iter_operations(api):
        if registered.operation_id == operation:
            return registered.method, registered.path
    raise RouteFailed(f"{operation} is not an operation of the API")


def _elapsed(response: HttpResponseBase, route: PerfRoute) -> float:
    if response.status_code != route.status:
        raise RouteFailed(f"{route.operation} answered {response.status_code}, not {route.status}")
    elapsed = float(response["Server-Timing"].removeprefix("app;dur="))  # apps/shared/middleware.py
    if isinstance(response, StreamingHttpResponse):
        chunks = iter(response)
        started = time.perf_counter()
        next(chunks, None)
        elapsed += (time.perf_counter() - started) * 1000
        for _ in chunks:  # the rest of the stream, so its queries count and the response closes
            pass
    return elapsed
