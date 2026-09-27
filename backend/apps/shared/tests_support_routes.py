"""The route sweep of a support session (TEN-06, ADR 0042, c8-support-session-guard): every
operation the API registers, called as a support session and split by `SUPPORT_READ_ROUTES`.

A GET on the list answers 2xx or 404, never 403 and never a crash, so a read the bank's own
members can do is never hidden behind the wrong code; the one exception is a published stub
that still answers 501 `not_built` (chunk 9's case reads until their logic lands). Every
other operation, GET or not, answers 403 `support_read_only` and writes nothing. A GET and a
POST planted on a router of the test's own are refused the same way, with no edit to the
guard or the list: refusal is the default.
"""

from __future__ import annotations

import datetime
import re
import uuid
from typing import Any

from django.test import override_settings
from django.urls import path
from ninja import NinjaAPI

from apps.identity import session_logic
from apps.shared import factories
from apps.shared.authentication import SessionAuth
from apps.shared.models import AuditEvent
from apps.shared.permissions import gate_of, step_up_of
from apps.shared.routes import SUPPORT_READ_ROUTES, SUPPORT_SESSION_ROUTES, iter_operations
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.shared.tests_support_session import grant
from config.api import api

PARAM = re.compile(r"\{(\w+)\}")

planted = NinjaAPI(urls_namespace="planted-support-probe")


@planted.get("/probe")
def planted_read(request: Any) -> dict[str, str]:
    return {"read": "nobody put this on the list"}


@planted.post("/probe")
def planted_write(request: Any) -> dict[str, str]:
    return {"wrote": "nobody put this on the list"}


def _urlpatterns() -> list[Any]:
    from config.urls import urlpatterns

    return [path("api/v1/planted/", planted.urls), *urlpatterns]


class PlantedUrls:
    urlpatterns = _urlpatterns()


def _value(name: str) -> str:
    if name == "week_start":
        return datetime.date.today().isoformat()
    return str(uuid.uuid4()) if name.endswith("_id") or name == "id" else "probe"


def concrete(template: str) -> str:
    return "/api/v1" + PARAM.sub(lambda match: _value(match.group(1)), template)


class SupportRouteSweepTests(ScenarioTestCase):
    def setUp(self) -> None:
        self.tenant = factories.tenant(slug="bank-a")
        admin = factories.member(self.tenant, roles=("admin",)).user
        self.platform = factories.platform_user()
        row = grant(self.tenant, self.platform, admin)
        entered = self.client.post(f"/api/v1/console/support-access/{row.id}/enter", **sign_in(self.platform, tenant=None, step_up=True))
        self.assertEqual(entered.status_code, 200, entered.content)
        self.support: dict[str, Any] = {"HTTP_AUTHORIZATION": f"Bearer {entered.json()['accessToken']}"}

    def reads(self) -> int:
        self.activate(self.tenant)
        return AuditEvent.objects.filter(action="support_access.read").count()

    def test_the_list_names_registered_session_reads_the_seven_permissions_cover(self) -> None:
        operations = {(op.method, op.path): op for op in iter_operations(api)}
        allowed = session_logic.SUPPORT_PERMISSIONS
        for key in sorted(SUPPORT_READ_ROUTES):
            with self.subTest(route=key):
                op = operations.get(key)
                self.assertIsNotNone(op, "every entry is a route the API registers")
                assert op is not None
                self.assertEqual(op.method, "GET")
                self.assertTrue(any(isinstance(auth, SessionAuth) for auth in op.auth), "a support session authenticates there")
                self.assertFalse(step_up_of(op.view_func))
                gate = gate_of(op.view_func)
                self.assertTrue(gate is None or gate.value in allowed, f"{key} needs {gate}")
        for key in SUPPORT_SESSION_ROUTES:
            self.assertIn(key, operations)
        for download in (("GET", "/evidence/{evidence_id}/download"), ("POST", "/search"), ("POST", "/ask")):
            self.assertNotIn(download, SUPPORT_READ_ROUTES)

    def test_every_get_on_the_list_answers_and_logs_and_every_other_is_refused(self) -> None:
        for op in sorted(iter_operations(api), key=lambda o: (o.path, o.method)):
            if op.method != "GET":
                continue
            with self.subTest(route=f"{op.method} {op.path}"):
                before = self.reads()
                response = self.client.get(concrete(op.path), **self.support)
                if (op.method, op.path) in SUPPORT_READ_ROUTES:
                    ok = 200 <= response.status_code < 300 or response.status_code == 404
                    stub = response.status_code == 501 and response.json()["code"] == "not_built"
                    self.assertTrue(ok or stub, f"{op.path} answered {response.status_code}: {response.content[:300]!r}")
                    if 200 <= response.status_code < 300:
                        self.assertEqual(self.reads(), before + 1, "one support_access.read row per request")
                else:
                    self.assertEqual((response.status_code, response.json()["code"]), (403, "support_read_only"), op.path)
                    self.assertEqual(self.reads(), before, "a refused request writes nothing")

    def test_every_write_is_refused_before_it_runs(self) -> None:
        self.activate(self.tenant)
        written = AuditEvent.objects.count()
        for op in sorted(iter_operations(api), key=lambda o: (o.path, o.method)):
            if op.method == "GET" or (op.method, op.path) in SUPPORT_SESSION_ROUTES:
                continue
            with self.subTest(route=f"{op.method} {op.path}"):
                response = self.client.generic(op.method, concrete(op.path), data="{}", content_type="application/json", **self.support)
                self.assertEqual((response.status_code, response.json()["code"]), (403, "support_read_only"))
        self.activate(self.tenant)
        self.assertEqual(AuditEvent.objects.count(), written)

    def test_a_planted_route_is_refused_with_no_edit_to_the_guard_or_the_list(self) -> None:
        with override_settings(ROOT_URLCONF=PlantedUrls):
            member = sign_in(factories.member(self.tenant, roles=("admin",)).user, tenant=self.tenant)
            self.assertEqual(self.client.get("/api/v1/planted/probe", **member).status_code, 200, "the route answers everyone else")
            for method in ("GET", "POST"):
                with self.subTest(method=method):
                    response = self.client.generic(method, "/api/v1/planted/probe", **self.support)
                    self.assertEqual((response.status_code, response.json()["code"]), (403, "support_read_only"))

    def test_a_path_id_cannot_smuggle_a_request_onto_the_list(self) -> None:
        # The template matched is the route Django resolved, never a raw path: an id shaped
        # like an allowed path still resolves to the refused route it is part of.
        response = self.client.get(f"/api/v1/evidence/{uuid.uuid4()}/download?next=/changes", **self.support)
        self.assertEqual((response.status_code, response.json()["code"]), (403, "support_read_only"))
        # A path that resolves to no route reaches no view at all: Django's own 404.
        response = self.client.get("/api/v1/nowhere/changes", **self.support)
        self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))
