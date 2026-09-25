"""Marking the library as seen (POST /me/visit; PRO-03, AUD-01, AC-AUD1).

The bookmark the library-updates screen reads is a column of the caller's own membership,
so these prove the three things that makes it: the bookmark moves for the caller and for
nobody else, the move leaves exactly one audit row in the caller's own bank, and a session
that belongs to no bank has no bookmark to move and writes nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from django.utils import timezone

from apps.identity.models import Membership
from apps.library.seeds import seed_languages
from apps.shared import factories, tenancy
from apps.shared.models import AuditEvent
from apps.shared.testing import ScenarioTestCase, sign_in

V1 = "/api/v1"
# The bookmark starts here, months before any test runs: a move is proven by the stamp
# leaving this anchor, never by comparing it with today (plan rule 8, CLAUDE.md §11).
WAS_SEEN_AT = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)


class MarkVisit(ScenarioTestCase):
    def setUp(self) -> None:
        seed_languages()
        self.tenant = factories.tenant(slug="bank")
        self.other_tenant = factories.tenant(slug="other-bank")
        self.activate(self.tenant)
        self.reader = factories.member(self.tenant, roles=("reader",), user_row=factories.user(name="Sara Lindqvist")).user
        self.colleague = factories.member(self.tenant, roles=("reader",), user_row=factories.user(name="Nils Berg")).user
        self.editor = factories.platform_user(roles=("library_editor",), email="editor@bleqq.test")

    def _visit(self, headers: dict[str, Any]) -> Any:
        return self.client.post(f"{V1}/me/visit", data={}, content_type="application/json", **headers)

    def _membership(self, user: Any, tenant: Any = None) -> Membership:
        self.activate(tenant or self.tenant)
        return Membership.objects.get(tenant=tenant or self.tenant, user=user)

    def test_the_bookmark_moves_and_leaves_one_audit_row_in_the_callers_bank(self) -> None:
        membership = self._membership(self.reader)
        membership.last_visit_at = WAS_SEEN_AT
        membership.save(update_fields=["last_visit_at"])
        before = timezone.now()

        answered = self._visit(sign_in(self.reader, tenant=self.tenant))

        self.assertEqual(answered.status_code, 204, answered.content)
        self.assertEqual(answered.content, b"")
        moved = self._membership(self.reader).last_visit_at
        assert moved is not None
        self.assertGreaterEqual(moved, before)
        rows = list(AuditEvent.objects.filter(action="member.visited"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].tenant_id, self.tenant.id)
        self.assertEqual(rows[0].actor_id, self.reader.id)
        self.assertEqual(rows[0].subject_id, membership.id)
        self.assertEqual(rows[0].before["lastVisitAt"], WAS_SEEN_AT.isoformat())
        self.assertEqual(rows[0].after["lastVisitAt"], moved.isoformat())

    def test_a_first_visit_moves_a_bookmark_that_was_never_set(self) -> None:
        self.assertIsNone(self._membership(self.reader).last_visit_at)

        self.assertEqual(self._visit(sign_in(self.reader, tenant=self.tenant)).status_code, 204)

        self.assertIsNotNone(self._membership(self.reader).last_visit_at)
        self.assertIsNone(AuditEvent.objects.get(action="member.visited").before["lastVisitAt"])

    def test_nobody_elses_bookmark_moves(self) -> None:
        self.assertEqual(self._visit(sign_in(self.reader, tenant=self.tenant)).status_code, 204)

        self.assertIsNone(self._membership(self.colleague).last_visit_at)

    def test_the_same_person_in_another_bank_keeps_their_own_bookmark(self) -> None:
        """A person may be a member of two banks; the session says which bookmark moves."""
        tenancy.activate(self.other_tenant.id)
        factories.member(self.other_tenant, roles=("reader",), user_row=self.reader)

        self.assertEqual(self._visit(sign_in(self.reader, tenant=self.other_tenant)).status_code, 204)

        self.assertIsNone(self._membership(self.reader, self.tenant).last_visit_at)
        self.assertIsNotNone(self._membership(self.reader, self.other_tenant).last_visit_at)

    def test_a_session_without_a_bank_is_a_404_and_writes_nothing(self) -> None:
        """Platform staff read the library itself, not a bank's view of it: there is no
        membership to bookmark, so the route answers like every other tenant route."""
        refused = self._visit(sign_in(self.editor))

        self.assertEqual(refused.status_code, 404, refused.content)
        self.assertEqual(refused.json()["code"], "not_found")
        self.activate(self.tenant)
        self.assertFalse(AuditEvent.objects.filter(action="member.visited").exists())
