"""The permission constants and decorators (PRD §6, ID-06, ID-09, playbook 4.2).

Pins the matrix against the PRD (every permission the PRD names exists, the system roles
hold exactly the PRD's grants), the structured 403, `@requires_scope` for agents, and
`@requires_step_up` with the freshness window read from settings (AC-ID3).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.test import SimpleTestCase, override_settings
from django.test.client import RequestFactory
from django.utils import timezone

from apps.shared import permissions as p
from apps.shared.errors import ProblemError
from apps.shared.testing import agent_principal, enrolment_principal, user_principal

PRD_TENANT_PERMISSIONS = {
    "library.read", "watch.read", "roadmap.read", "search.use", "comments.write", "problems.report",
    "register.read", "cases.read", "reports.read", "audit.read", "footprint.request", "footprint.approve",
    "cases.triage", "cases.work", "cases.contribute", "cases.signoff", "register.edit", "gaps.edit",
    "applicability.request", "applicability.approve", "risk.accept.approve", "proposals.create",
    "exports.create", "ai_log.read", "members.manage", "roles.manage", "security.manage", "vocab.manage",
    "workflow.manage", "agents.manage", "integrations.manage",
}  # fmt: skip
PRD_PLATFORM_PERMISSIONS = {
    "proposals.review", "library_vocab.manage", "sources.manage", "eval.manage",
    "tenants.manage", "agent_definitions.manage", "support_access.grant", "system.health",
}  # fmt: skip


class Matrix(SimpleTestCase):
    def test_the_constants_are_exactly_the_prd_matrix(self) -> None:
        self.assertEqual(p.TENANT_PERMISSIONS, PRD_TENANT_PERMISSIONS)
        self.assertEqual(p.PLATFORM_PERMISSIONS, PRD_PLATFORM_PERMISSIONS)
        self.assertEqual(p.ALL_PERMISSIONS, PRD_TENANT_PERMISSIONS | PRD_PLATFORM_PERMISSIONS)

    def test_system_roles_follow_the_prd_columns(self) -> None:
        self.assertEqual(set(p.SYSTEM_ROLES), {
            "admin", "compliance_officer", "owner", "approver", "contributor", "reader", "auditor",
            "library_editor", "platform_admin",
        })  # fmt: skip
        everyone = {"library.read", "watch.read", "roadmap.read", "search.use", "comments.write",
                    "problems.report", "register.read", "cases.read", "reports.read", "audit.read"}  # fmt: skip
        for role in ("admin", "compliance_officer", "owner", "approver", "contributor", "reader", "auditor"):
            self.assertTrue(everyone <= p.SYSTEM_ROLES[role], role)
        self.assertEqual(p.SYSTEM_ROLES["reader"], everyone)
        self.assertIn("cases.signoff", p.SYSTEM_ROLES["approver"])
        self.assertNotIn("cases.signoff", p.SYSTEM_ROLES["compliance_officer"])
        self.assertIn("cases.triage", p.SYSTEM_ROLES["compliance_officer"])
        self.assertNotIn("cases.triage", p.SYSTEM_ROLES["admin"])
        self.assertEqual(p.SYSTEM_ROLES["contributor"] - everyone, {"cases.contribute"})
        self.assertEqual(p.SYSTEM_ROLES["auditor"] - everyone, {"exports.create", "ai_log.read"})
        self.assertTrue({"members.manage", "roles.manage", "security.manage"} <= p.SYSTEM_ROLES["admin"])
        self.assertTrue(p.SYSTEM_ROLES["library_editor"] <= p.PLATFORM_PERMISSIONS)
        self.assertTrue(p.SYSTEM_ROLES["platform_admin"] <= p.PLATFORM_PERMISSIONS)

    def test_no_scope_allows_a_library_edit(self) -> None:
        for scope in p.ALL_SCOPES:
            self.assertNotIn("library", scope.split(".")[0], f"{scope} would let an agent edit the library (AC-PRO1)")


def _view(request: Any) -> str:
    return "ok"


class Decorators(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def _request(self, principal: Any) -> Any:
        request = self.factory.get("/")
        request.auth = principal  # type: ignore[attr-defined]
        return request

    def test_requires_permission_marks_the_view_and_enforces(self) -> None:
        gated = p.requires_permission(p.CASES_TRIAGE)(_view)
        self.assertEqual(p.gate_of(gated), p.Gate("permission", p.CASES_TRIAGE))
        self.assertEqual(gated(self._request(user_principal(permissions={p.CASES_TRIAGE}))), "ok")
        with self.assertRaises(ProblemError) as caught:
            gated(self._request(user_principal(permissions={p.CASES_READ})))
        self.assertEqual(caught.exception.status, 403)
        self.assertEqual(caught.exception.code, "permission_denied")
        self.assertEqual(caught.exception.required_permission, p.CASES_TRIAGE)
        self.assertEqual(caught.exception.as_dict()["requiredPermission"], p.CASES_TRIAGE)
        with self.assertRaises(ProblemError) as caught:
            gated(self._request(None))
        self.assertEqual(caught.exception.status, 401)
        with self.assertRaises(ProblemError):
            gated(self._request(agent_principal(scopes={"changes.write"})))

    def test_requires_permission_refuses_an_unknown_constant(self) -> None:
        with self.assertRaises(ValueError):
            p.requires_permission("cases.everything")

    def test_requires_scope_marks_the_view_and_enforces(self) -> None:
        gated = p.requires_scope(p.SCOPE_CHANGES_WRITE)(_view)
        self.assertEqual(p.gate_of(gated), p.Gate("scope", p.SCOPE_CHANGES_WRITE))
        self.assertEqual(gated(self._request(agent_principal(scopes={p.SCOPE_CHANGES_WRITE}))), "ok")
        with self.assertRaises(ProblemError) as caught:
            gated(self._request(agent_principal(scopes={p.SCOPE_VOCAB_READ})))
        self.assertEqual(caught.exception.status, 403)
        with self.assertRaises(ProblemError):
            gated(self._request(user_principal(permissions=p.ALL_PERMISSIONS)))
        with self.assertRaises(ValueError):
            p.requires_scope("library.write")

    @override_settings(STEP_UP_FRESHNESS_MINUTES=5)
    def test_requires_step_up_needs_a_fresh_assertion(self) -> None:
        gated = p.requires_step_up(_view)
        self.assertTrue(p.step_up_of(gated))
        self.assertIsNone(p.gate_of(gated))
        fresh = user_principal(step_up_at=timezone.now() - timedelta(minutes=1))
        stale = user_principal(step_up_at=timezone.now() - timedelta(minutes=6))
        self.assertEqual(gated(self._request(fresh)), "ok")
        for principal in (stale, user_principal(), agent_principal(), enrolment_principal()):
            with self.assertRaises(ProblemError) as caught:
                gated(self._request(principal))
            self.assertEqual(caught.exception.code, "step_up_required")
            self.assertEqual(caught.exception.status, 403)

    def test_decorators_compose_and_keep_their_marks(self) -> None:
        view = p.requires_permission(p.CASES_SIGNOFF)(p.requires_step_up(_view))
        self.assertEqual(p.gate_of(view).value, p.CASES_SIGNOFF)  # type: ignore[union-attr]
        self.assertTrue(p.step_up_of(view))
        self.assertEqual(view.__name__, "_view")

    def test_ungated_reasons_are_the_five_shapes(self) -> None:
        self.assertEqual(
            {r.value for r in p.UngatedReason}, {"self", "bootstrap", "capability", "logic-gate", "public-token"}
        )
