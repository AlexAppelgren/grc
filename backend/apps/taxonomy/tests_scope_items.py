"""Scope items through the regulatory scope request (OWN-01, FP-02, D-89, D-91; d89-scope-items-logic).

A person holding `footprint.request` asks for a scope item on the regulatory scope request,
a second person holding `footprint.approve` approves it with a passkey, and the item enters
the scope as `in_scope`, with a history row and one `scope_item.added` audit and outbox row
carrying ids and keys only. Rejecting or withdrawing declines it; an approved removal takes
it out. No API key reaches any of it, and no module but the request logic writes a scope
item (`NoOtherWriter`), so no agent path can. H24's caps on the request's lists and on the
decision note are proven over the real routes.

Operations exercised (the audit-on-write guard reads these names): createFootprintRequest,
approveFootprintRequest, rejectFootprintRequest, withdrawFootprintRequest, getScopeItem.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.test import Client, SimpleTestCase

from apps.shared import factories, tenancy
from apps.shared.audit import Actor
from apps.shared.models import AuditEvent, OutboxEvent
from apps.shared.tenancy import library_write
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.shared.tests_library_fence import WRITE_METHODS, production_modules
from apps.taxonomy.models import FootprintChangeRequest, FootprintHistory, ScopeItem, TaxonomyTerm
from apps.taxonomy.schemas import FOOTPRINT_NOTE_MAX_CHARS
from apps.taxonomy.tenant_hooks import ensure_tenant_vocabularies
from apps.taxonomy.tests_scenarios import _seed_library

V1 = "/api/v1"
APPS_DIR = Path(__file__).resolve().parent.parent
REQUESTS = "/tenant/footprint/requests"
ITEM: dict[str, Any] = {
    "name": "Local crypto-asset rules",
    "description": "Finansinspektionen's rules for crypto-asset service providers.",
    "jurisdiction": "se",
    "regimeTerm": "securities",
    "officialReference": "FFFS 2026:1",
    "sourceUrl": "https://www.fi.se/sv/vara-register/",
}
# What a person typed, which no audit value and no outbox payload may carry (rule m).
TYPED = (ITEM["name"], ITEM["description"])


class ScopeItemBank(ScenarioTestCase):
    def setUp(self) -> None:
        _seed_library()
        self.tenant = factories.tenant(slug="bank")
        self.activate(self.tenant)
        ensure_tenant_vocabularies(self.tenant, actor=Actor.system("test"))
        self.officer = factories.member(self.tenant, roles=("compliance_officer",), user_row=factories.user(name="Sara Lindqvist")).user
        self.approver = factories.member(self.tenant, roles=("approver",), user_row=factories.user(name="Maria Ek")).user
        self.reader = factories.member(self.tenant, roles=("reader",), user_row=factories.user(name="Oskar Lund")).user

    def post(self, path: str, body: dict[str, Any], headers: dict[str, Any]) -> Any:
        return self.client.post(f"{V1}{path}", data=body, content_type="application/json", **headers)

    def preview(self, body: dict[str, Any], headers: dict[str, Any]) -> Any:
        # A dry run writes no audit row, which the scenario client would refuse.
        return Client().post(f"{V1}{REQUESTS}?dryRun=true", data=body, content_type="application/json", **headers)

    def get(self, path: str, headers: dict[str, Any]) -> Any:
        return self.client.get(f"{V1}{path}", **headers)

    def ask(self, body: dict[str, Any]) -> dict[str, Any]:
        response = self.post(REQUESTS, body, sign_in(self.officer, tenant=self.tenant))
        self.assertEqual(response.status_code, 201, response.content)
        return dict(response.json())

    def approve(self, request: dict[str, Any], note: str = "") -> Any:
        return self.post(f"{REQUESTS}/{request['id']}/approve", {"note": note}, sign_in(self.approver, tenant=self.tenant, step_up=True))

    def in_scope(self) -> list[dict[str, Any]]:
        response = self.get("/tenant/footprint", sign_in(self.reader, tenant=self.tenant))
        self.assertEqual(response.status_code, 200, response.content)
        return list(response.json()["scopeItems"])

    def assert_no_typed_text(self, values: list[Any]) -> None:
        for value in values:
            for text in TYPED:
                self.assertNotIn(text, str(value))


class AskingForAScopeItem(ScopeItemBank):
    def test_a_dry_run_shows_the_item_as_it_would_be_and_stores_nothing(self) -> None:
        dry = self.preview({"scopeItemAdds": [ITEM]}, sign_in(self.officer, tenant=self.tenant))
        self.assertEqual(dry.status_code, 200, dry.content)
        item = dry.json()["scopeItemAdds"][0]
        self.assertEqual((item["id"], item["key"], item["status"], item["research"]), (None, "local_crypto_asset_rules", "requested", None))
        self.assertEqual((item["jurisdiction"]["key"], item["regimeTerm"]["key"]), ("se", "securities"))
        # An item is researched, never matched: it moves no count.
        self.assertEqual(dry.json()["preview"]["obligations"], {"hidden": 0, "revealed": 0, "available": True})
        self.activate(self.tenant)
        self.assertFalse(ScopeItem.objects.exists())
        self.assertFalse(FootprintChangeRequest.objects.exists())

    def test_the_request_stores_the_item_as_requested_and_audits_keys_only(self) -> None:
        request = self.ask({"scopeItemAdds": [ITEM]})
        self.assertEqual(request["status"], "pending")
        self.assertEqual([i["status"] for i in request["scopeItemAdds"]], ["requested"])
        self.activate(self.tenant)
        item = ScopeItem.objects.get(tenant=self.tenant)
        self.assertEqual((item.key, item.name, item.status), ("local_crypto_asset_rules", ITEM["name"], "requested"))
        asked = AuditEvent.objects.get(tenant=self.tenant, action="footprint.change_requested")
        self.assertEqual(asked.after["scopeItemAdds"], [{"scopeItemId": str(item.id), "key": item.key, "jurisdiction": "se", "regimeTerm": "securities"}])
        self.assert_no_typed_text([asked.after, asked.subject_title, asked.summary])
        # Not in scope until a second person approves it.
        self.assertEqual(self.in_scope(), [])
        pending = self.get("/tenant/footprint", sign_in(self.reader, tenant=self.tenant)).json()["pendingRequest"]
        self.assertEqual([i["key"] for i in pending["scopeItemAdds"]], [item.key])

    def test_the_requester_cannot_approve_and_the_approver_needs_a_passkey(self) -> None:
        request = self.ask({"scopeItemAdds": [ITEM]})
        own = self.post(f"{REQUESTS}/{request['id']}/approve", {}, sign_in(self.officer, tenant=self.tenant, step_up=True))
        self.assertEqual((own.status_code, own.json()["code"]), (409, "four_eyes_violation"))
        bare = self.post(f"{REQUESTS}/{request['id']}/approve", {}, sign_in(self.approver, tenant=self.tenant))
        self.assertEqual((bare.status_code, bare.json()["code"]), (403, "step_up_required"))
        self.activate(self.tenant)
        self.assertEqual(ScopeItem.objects.get(tenant=self.tenant).status, "requested")

    def test_approval_puts_the_item_in_scope_with_history_audit_and_outbox(self) -> None:
        terms_before = self.get("/tenant/footprint", sign_in(self.reader, tenant=self.tenant)).json()["dimensions"]
        request = self.ask({"scopeItemAdds": [ITEM]})
        approved = self.approve(request, note="Our crypto desk opens in November.")
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual([i["status"] for i in approved.json()["scopeItemAdds"]], ["in_scope"])
        [item] = self.in_scope()
        self.assertEqual((item["key"], item["status"], item["research"]), ("local_crypto_asset_rules", "in_scope", "waiting_for_agent"))
        # Approving an item changes no term of the scope.
        self.assertEqual(self.get("/tenant/footprint", sign_in(self.reader, tenant=self.tenant)).json()["dimensions"], terms_before)
        self.activate(self.tenant)
        row = ScopeItem.objects.get(tenant=self.tenant)
        history = FootprintHistory.objects.get(tenant=self.tenant, request_id=request["id"])
        self.assertEqual((history.scope_item_id, history.term_id, history.action, history.changed_by_id), (row.id, None, "added", self.approver.id))
        self.assertIsNotNone(history.step_up_assertion_id)
        added = AuditEvent.objects.get(tenant=self.tenant, action="scope_item.added")
        self.assertEqual((added.subject_id, added.step_up_assertion_id), (row.id, history.step_up_assertion_id))
        self.assertEqual(added.actor_id, self.approver.id)
        event = OutboxEvent.objects.get(tenant=self.tenant, topic="scope_item.added")
        self.assertEqual(
            event.payload,
            {"scopeItemId": str(row.id), "key": row.key, "jurisdiction": "se", "regimeTerm": "securities", "request": request["id"], "tenantId": str(self.tenant.id)},
        )
        decision = AuditEvent.objects.get(tenant=self.tenant, action="footprint.change_approved")
        self.assert_no_typed_text([added.after, added.summary, added.subject_title, event.payload, decision.after])
        self.assertNotIn("Our crypto desk", str(decision.after))

    def test_a_rejected_or_withdrawn_request_declines_its_items(self) -> None:
        rejected = self.ask({"scopeItemAdds": [ITEM]})
        no = self.post(f"{REQUESTS}/{rejected['id']}/reject", {"note": "Not ours."}, sign_in(self.approver, tenant=self.tenant))
        self.assertEqual(no.status_code, 200, no.content)
        self.assertEqual([i["status"] for i in no.json()["scopeItemAdds"]], ["declined"])
        withdrawn = self.ask({"scopeItemAdds": [ITEM]})
        # A declined item's key is never reused: the second ask gets the next one.
        self.assertEqual([i["key"] for i in withdrawn["scopeItemAdds"]], ["local_crypto_asset_rules_2"])
        back = self.post(f"{REQUESTS}/{withdrawn['id']}/withdraw", {}, sign_in(self.officer, tenant=self.tenant))
        self.assertEqual(back.status_code, 200, back.content)
        self.assertEqual([i["status"] for i in back.json()["scopeItemAdds"]], ["declined"])
        self.assertEqual(self.in_scope(), [])
        self.activate(self.tenant)
        decisions = AuditEvent.objects.filter(tenant=self.tenant, action__in=("footprint.change_rejected", "footprint.change_withdrawn"))
        self.assertEqual(
            sorted(entry["key"] for event in decisions for entry in event.after["scopeItemsDeclined"]),
            ["local_crypto_asset_rules", "local_crypto_asset_rules_2"],
        )
        self.assertFalse(OutboxEvent.objects.filter(topic__startswith="scope_item.").exists())

    def test_an_approved_removal_takes_the_item_out(self) -> None:
        self.approve(self.ask({"scopeItemAdds": [ITEM]}))
        unknown = self.post(REQUESTS, {"scopeItemRemoves": ["not_an_item"]}, sign_in(self.officer, tenant=self.tenant))
        self.assertEqual((unknown.status_code, unknown.json()["code"]), (422, "unknown_key"))
        self.assertIn("local_crypto_asset_rules", unknown.json()["detail"])
        twice = self.post(REQUESTS, {"scopeItemRemoves": ["local_crypto_asset_rules"] * 2}, sign_in(self.officer, tenant=self.tenant))
        self.assertEqual((twice.status_code, twice.json()["code"]), (422, "validation_error"))
        removal = self.ask({"scopeItemRemoves": ["local_crypto_asset_rules"]})
        self.assertEqual([i["status"] for i in removal["scopeItemRemoves"]], ["in_scope"])
        approved = self.approve(removal)
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual([i["status"] for i in approved.json()["scopeItemRemoves"]], ["removed"])
        self.assertEqual(self.in_scope(), [])
        self.activate(self.tenant)
        self.assertEqual(
            list(FootprintHistory.objects.filter(tenant=self.tenant, scope_item__isnull=False).order_by("id").values_list("action", flat=True)),
            ["added", "removed"],
        )
        self.assertEqual(OutboxEvent.objects.get(tenant=self.tenant, topic="scope_item.removed").payload["key"], "local_crypto_asset_rules")

    def test_a_regime_term_retired_while_the_request_waits_stops_the_approval(self) -> None:
        request = self.ask({"scopeItemAdds": [ITEM]})
        with library_write("test"):
            TaxonomyTerm.objects.filter(dimension__key="regime", key="securities").update(active=False)
        stale = self.approve(request)
        self.assertEqual((stale.status_code, stale.json()["code"]), (409, "stale_write"))
        self.activate(self.tenant)
        self.assertEqual(ScopeItem.objects.get(tenant=self.tenant).status, "requested")

    def test_another_bank_reads_none_of_the_items(self) -> None:
        self.approve(self.ask({"scopeItemAdds": [ITEM]}))
        self.activate(self.tenant)
        item = ScopeItem.objects.get(tenant=self.tenant)
        own = self.get(f"/tenant/footprint/scope-items/{item.id}", sign_in(self.reader, tenant=self.tenant))
        self.assertEqual((own.status_code, own.json()["key"], own.json()["research"]), (200, item.key, "waiting_for_agent"))
        other = factories.tenant(slug="other-bank")
        stranger = factories.member(other, roles=("admin",)).user
        headers = sign_in(stranger, tenant=other)
        fetched = self.get(f"/tenant/footprint/scope-items/{item.id}", headers)
        self.assertEqual((fetched.status_code, fetched.json()["code"]), (404, "not_found"))
        self.assertEqual(self.get("/tenant/footprint", headers).json()["scopeItems"], [])
        self.assertEqual(self.get("/tenant/footprint/scope-items/not-a-uuid", headers).status_code, 404)


class TheBoundaryRefuses(ScopeItemBank):
    def refused(self, body: dict[str, Any], code: str) -> dict[str, Any]:
        response = self.post(REQUESTS, body, sign_in(self.officer, tenant=self.tenant))
        self.assertEqual((response.status_code, response.json()["code"]), (422, code), response.content)
        self.activate(self.tenant)
        self.assertFalse(ScopeItem.objects.exists())
        self.assertFalse(FootprintChangeRequest.objects.exists())
        return dict(response.json())

    def test_an_address_that_is_not_a_public_https_page(self) -> None:
        for address in (
            "http://www.fi.se/sv/",
            "https://localhost/rules",
            "https://10.0.0.8/rules",
            "https://intranet/rules",
            "https://rules.internal/",
            "https://user:secret@www.fi.se/",
            "https://www.fi.se:8443/",
            "ftp://www.fi.se/",
        ):
            with self.subTest(address=address):
                self.refused({"scopeItemAdds": [{**ITEM, "sourceUrl": address}]}, "source_not_public")

    def test_an_unknown_jurisdiction_or_regime_term(self) -> None:
        self.assertIn("se", self.refused({"scopeItemAdds": [{**ITEM, "jurisdiction": "atlantis"}]}, "unknown_key")["detail"])
        self.assertIn("securities", self.refused({"scopeItemAdds": [{**ITEM, "regimeTerm": "atlantis"}]}, "unknown_key")["detail"])

    def test_a_name_on_more_than_one_line_a_long_description_or_an_unknown_field(self) -> None:
        self.refused({"scopeItemAdds": [{**ITEM, "name": "Local\ncrypto rules"}]}, "validation_error")
        self.refused({"scopeItemAdds": [{**ITEM, "name": ""}]}, "validation_error")
        self.refused({"scopeItemAdds": [{**ITEM, "description": "x" * (settings.SCOPE_ITEM_DESCRIPTION_MAX_CHARS + 1)}]}, "validation_error")
        self.refused({"scopeItemAdds": [{**ITEM, "status": "in_scope"}]}, "validation_error")
        self.refused({"scopeItemAdds": [ITEM], "tenantId": str(self.tenant.id)}, "validation_error")
        self.refused({}, "validation_error")

    def test_h24_each_list_is_capped_by_the_setting(self) -> None:
        over = settings.FOOTPRINT_CHANGE_MAX_TERMS + 1
        term = {"dimension": "service_type", "key": "advice"}
        for body in (
            {"adds": [term] * over},
            {"removes": [term] * over},
            {"scopeItemAdds": [ITEM] * over},
            {"scopeItemRemoves": ["local_crypto_asset_rules"] * over},
        ):
            with self.subTest(list=next(iter(body))):
                self.refused(body, "validation_error")

    def test_h24_the_decision_note_is_capped(self) -> None:
        request = self.ask({"scopeItemAdds": [ITEM]})
        long_note = {"note": "x" * (FOOTPRINT_NOTE_MAX_CHARS + 1)}
        approve = self.post(f"{REQUESTS}/{request['id']}/approve", long_note, sign_in(self.approver, tenant=self.tenant, step_up=True))
        reject = self.post(f"{REQUESTS}/{request['id']}/reject", long_note, sign_in(self.approver, tenant=self.tenant))
        for response in (approve, reject):
            self.assertEqual((response.status_code, response.json()["code"]), (422, "validation_error"))
        self.activate(self.tenant)
        self.assertEqual(FootprintChangeRequest.objects.get(pk=request["id"]).status, "pending")
        self.assertEqual(self.approve(request, note="x" * FOOTPRINT_NOTE_MAX_CHARS).status_code, 200)


class NoKeyReachesAScopeItem(ScopeItemBank):
    """Every route that reads or writes a scope item takes a person's session: a bank's key
    and a platform agent's key, however scoped, are refused and store nothing (D-89)."""

    def test_every_route_refuses_every_key(self) -> None:
        from apps.agents import testing as agent_build

        waiting = self.ask({"scopeItemAdds": [ITEM]})
        self.activate(self.tenant)
        item = ScopeItem.objects.get(tenant=self.tenant)
        bank_key = factories.api_key(self.tenant, scopes=("library:read", "search:read"))
        with tenancy.platform_zone():
            platform_key = agent_build.agent_key(scopes=("proposals:write", "proposals:review", "library:read"))
        routes = (
            ("GET", "/tenant/footprint", None),
            ("GET", REQUESTS, None),
            ("GET", f"/tenant/footprint/scope-items/{item.id}", None),
            ("POST", REQUESTS, {"scopeItemAdds": [{**ITEM, "name": "Another rule"}]}),
            ("POST", f"{REQUESTS}?dryRun=true", {"scopeItemAdds": [ITEM]}),
            ("POST", f"{REQUESTS}/{waiting['id']}/approve", {}),
            ("POST", f"{REQUESTS}/{waiting['id']}/reject", {}),
            ("POST", f"{REQUESTS}/{waiting['id']}/withdraw", {}),
        )
        before = (ScopeItem.objects.count(), AuditEvent.objects.count(), FootprintHistory.objects.count())
        for key in (bank_key, platform_key):
            for headers in ({"HTTP_AUTHORIZATION": f"Bearer {key.plain_key}"}, {"HTTP_X_API_KEY": key.plain_key}):
                for method, path, body in routes:
                    with self.subTest(route=f"{method} {path}", key=key.row.tenant_id):
                        response = Client().generic(method, f"{V1}{path}", data=json.dumps(body or {}), content_type="application/json", **headers)
                        self.assertIn(response.status_code, (401, 403), response.content)
        self.activate(self.tenant)
        self.assertEqual((ScopeItem.objects.count(), AuditEvent.objects.count(), FootprintHistory.objects.count()), before)
        self.assertEqual(FootprintChangeRequest.objects.get(pk=waiting["id"]).status, "pending")


# The one production module that writes a scope item or a request's scope-item row: the
# regulatory scope request's logic, which only a person's session reaches. The test
# factory writes one for the tenant-isolation guard and is never imported by a route.
SCOPE_ITEM_WRITERS = frozenset({"taxonomy/footprint_logic.py", "shared/factories.py"})
SCOPE_ITEM_MODELS = frozenset({"ScopeItem", "FootprintChangeScopeItem"})


def writes_a_scope_item(source: str) -> int | None:
    """The line of the first write call in a module that names a scope item model, or None."""
    tree = ast.parse(source)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    writes = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in WRITE_METHODS
    ]
    return min(writes) if names & SCOPE_ITEM_MODELS and writes else None


class NoOtherWriter(SimpleTestCase):
    """No agent path writes a scope item (D-89): any module outside `SCOPE_ITEM_WRITERS`
    that names a scope item model and calls a write method fails here, the agents' and the
    proposals' modules included, the way the library fence guards the library."""

    def test_only_the_request_logic_writes_a_scope_item(self) -> None:
        offenders = []
        for path in production_modules():
            rel = path.relative_to(APPS_DIR).as_posix()
            if rel in SCOPE_ITEM_WRITERS or rel.endswith("/models.py"):
                continue
            line = writes_a_scope_item(path.read_text(encoding="utf-8"))
            if line is not None:
                offenders.append(f"apps/{rel}:{line}")
        self.assertEqual(offenders, [], "a module outside the regulatory scope request writes a scope item")

    def test_the_guard_sees_a_write(self) -> None:
        self.assertEqual(writes_a_scope_item("from apps.taxonomy.models import ScopeItem\nScopeItem.objects.create(key='x')\n"), 2)
        self.assertIsNone(writes_a_scope_item("from apps.taxonomy.models import ScopeItem\nScopeItem.objects.filter(key='x')\n"))
        self.assertIsNotNone(writes_a_scope_item((APPS_DIR / "taxonomy" / "footprint_logic.py").read_text(encoding="utf-8")))
