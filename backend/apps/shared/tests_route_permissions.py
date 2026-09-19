"""Guard: route permissions (playbook 5).

Enumerates every operation Ninja registered on the one NinjaAPI (the same objects that
produce openapi.json) and demands that each is gated by `@requires_permission` or
`@requires_scope`, or is listed in `UNGATED_BY_DESIGN` with a reason of one of the five
shapes. An allowlist of bare paths decays into a rubber stamp; a reason can be read back
and disagreed with. It also fails on a stale allowlist entry that names no route, so the
list cannot rot.

Proven to fail 2026-09-19 by removing the ("GET", "/me") entry from UNGATED_BY_DESIGN:
the test named the route and the two ways to fix it.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.shared.permissions import UNGATED_BY_DESIGN, UngatedReason, gate_of
from apps.shared.routes import iter_operations
from config.api import api


class RoutePermissionsGuard(SimpleTestCase):
    def test_every_operation_is_gated_or_ungated_by_design(self) -> None:
        operations = list(iter_operations(api))
        self.assertGreater(len(operations), 0, "the API registered no operations; the enumeration is broken")
        unexplained: list[str] = []
        for operation in operations:
            key = (operation.method, operation.path)
            if gate_of(operation.view_func) is not None:
                continue
            if key in UNGATED_BY_DESIGN:
                continue
            unexplained.append(f"{operation.method} {operation.path} ({operation.operation_id})")
        self.assertEqual(
            unexplained,
            [],
            "Routes with no permission gate and no entry in UNGATED_BY_DESIGN:\n  "
            + "\n  ".join(unexplained)
            + "\nAdd @requires_permission / @requires_scope in api.py, or register the route in "
            "apps/shared/permissions.py with one of the five reasons.",
        )

    def test_every_ungated_entry_names_a_real_route_with_a_valid_reason(self) -> None:
        registered = {(op.method, op.path) for op in iter_operations(api)}
        stale = [f"{m} {p}" for (m, p) in UNGATED_BY_DESIGN if (m, p) not in registered]
        self.assertEqual(stale, [], f"UNGATED_BY_DESIGN names routes that do not exist: {stale}")
        for key, entry in UNGATED_BY_DESIGN.items():
            with self.subTest(route=key):
                self.assertIsInstance(entry.reason, UngatedReason)
                self.assertGreater(len(entry.note.strip()), 20, "the note must be a sentence a reviewer can disagree with")

    def test_a_gated_route_is_not_also_listed_as_ungated(self) -> None:
        for operation in iter_operations(api):
            if gate_of(operation.view_func) is not None:
                self.assertNotIn(
                    (operation.method, operation.path),
                    UNGATED_BY_DESIGN,
                    "a route cannot be both gated and ungated by design; delete the entry",
                )
