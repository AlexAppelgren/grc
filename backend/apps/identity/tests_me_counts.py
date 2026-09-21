"""`GET /me` counts and `lastVisitAt` (f03-T48, HOM-01, ID-04, AC-HOM1, D-23).

`Home` carries no `decideNow` field (chunk 6 ruling 1): the queue counts Today's "Decide
now" panel reads live here instead, so a number has one source. These tests prove the
three counts are independently permission-filtered (0, never a 403), that they read under
row-level security so a second tenant's rows never reach them, that the read writes
nothing, and that the three reads cost a fixed, pinned number of queries.
"""

from __future__ import annotations

from typing import Any

from django.test import TestCase

from apps.cases import testing as cases_build
from apps.identity import me_logic
from apps.identity.models import Membership, User
from apps.proposals.models import OriginType, Proposal, ProposalKind, ProposalStatus, ProposalTenant
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.models import AuditEvent, Tenant
from apps.shared.testing import sign_in
from apps.watch import testing as watch_build

V1 = "/api/v1"
# `_counts()`'s own three independent reads: pinned so a future one that chains a fourth
# behind another has to look at this number rather than drift past it.
COUNTS_QUERIES = 3


def _open_proposal(*, tenant: Tenant, proposer: User) -> Proposal:
    """A tenant's own open proposal, filed exactly as `logic.propose()` files one: the
    `proposal` row and its `ProposalTenant` link, so the count reads the same table the
    console's per-tenant filter does."""
    proposal = Proposal.objects.create(
        kind=ProposalKind.NEW_OBLIGATION_VERSION.value,
        title="A proposed change to an obligation",
        origin=OriginType.USER.value,
        proposed_by_user=proposer,
        proposed_in_tenant=True,
        status=ProposalStatus.OPEN.value,
    )
    tenancy.activate(tenant.id)
    ProposalTenant.objects.create(tenant=tenant, proposal=proposal)
    return proposal


class MeCounts(TestCase):
    tenant: Tenant
    other_tenant: Tenant
    officer: User
    reader: User

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug="me-counts")
        cls.other_tenant = factories.tenant(slug="me-counts-other")
        cls.officer = factories.member_user(cls.tenant, roles=("compliance_officer",))
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))

    def me(self, user: User) -> dict[str, Any]:
        response = self.client.get(f"{V1}/me", **sign_in(user, tenant=self.tenant))
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_a_platform_session_gets_null_counts_and_null_last_visit(self) -> None:
        editor = factories.platform_user(roles=("library_editor",), email="editor-me-counts@bleqq.test")
        body = self.client.get(f"{V1}/me", **sign_in(editor)).json()
        self.assertIsNone(body["counts"])
        self.assertIsNone(body["lastVisitAt"])

    def test_a_member_with_no_open_work_reads_zeros_not_a_403(self) -> None:
        body = self.me(self.reader)
        self.assertEqual(body["counts"], {"triage": 0, "proposals": 0, "assignedToMe": 0})

    def test_triage_counts_new_cases_and_needs_cases_triage(self) -> None:
        change = watch_build.change(stable_key="chg-me-counts-triage")
        cases_build.case(self.tenant, change)

        self.assertEqual(self.me(self.officer)["counts"]["triage"], 1)
        self.assertEqual(self.me(self.reader)["counts"]["triage"], 0, "the reader lacks cases.triage: a true 0, not a refusal")

    def test_proposals_counts_this_banks_open_proposals_and_needs_proposals_create(self) -> None:
        _open_proposal(tenant=self.tenant, proposer=self.officer)
        # A closed proposal and one nobody in this bank filed do not count.
        outsider = factories.member_user(self.other_tenant, roles=("compliance_officer",))
        _open_proposal(tenant=self.other_tenant, proposer=outsider)
        closed = _open_proposal(tenant=self.tenant, proposer=self.officer)
        closed.status = ProposalStatus.APPROVED.value
        closed.save(update_fields=["status"])

        self.assertEqual(self.me(self.officer)["counts"]["proposals"], 1)
        self.assertEqual(self.me(self.reader)["counts"]["proposals"], 0, "the reader lacks proposals.create: a true 0, not a refusal")

    def test_assigned_to_me_counts_every_members_own_open_cases_no_permission_needed(self) -> None:
        change = watch_build.change(stable_key="chg-me-counts-assigned")
        case = cases_build.case(self.tenant, change, owner=self.reader)
        watch_build.change(stable_key="chg-me-counts-assigned-closed")

        self.assertEqual(self.me(self.reader)["counts"]["assignedToMe"], 1)
        case.status = "closed"
        case.save(update_fields=["status"])
        self.assertEqual(self.me(self.reader)["counts"]["assignedToMe"], 0, "a closed case leaves the owner's queue")

    def test_another_tenants_rows_never_reach_the_count(self) -> None:
        """Row-level security, not a filter this module writes: a case and a proposal of a
        second bank must not be countable from the first."""
        other_officer = factories.member_user(self.other_tenant, roles=("compliance_officer",))
        other_change = watch_build.change(stable_key="chg-me-counts-isolation")
        cases_build.case(self.other_tenant, other_change, owner=other_officer)
        _open_proposal(tenant=self.other_tenant, proposer=other_officer)

        self.assertEqual(self.me(self.officer)["counts"], {"triage": 0, "proposals": 0, "assignedToMe": 0})

    def test_the_read_writes_nothing(self) -> None:
        headers = sign_in(self.reader, tenant=self.tenant)
        before = AuditEvent.objects.count()

        self.client.get(f"{V1}/me", **headers)

        self.assertEqual(AuditEvent.objects.count(), before)

    def test_last_visit_at_is_the_callers_own_bookmark(self) -> None:
        self.assertIsNone(self.me(self.reader)["lastVisitAt"])

        self.client.post(f"{V1}/me/visit", data={}, content_type="application/json", **sign_in(self.reader, tenant=self.tenant))

        moved = self.me(self.reader)["lastVisitAt"]
        self.assertIsNotNone(moved)
        tenancy.activate(self.tenant.id)
        self.assertIsNone(Membership.objects.get(tenant=self.tenant, user=self.officer).last_visit_at, "one person's visit moves only their own bookmark")

    def test_the_three_reads_fan_out_at_a_fixed_query_count(self) -> None:
        """None chained behind another: the same three queries whether the caller has open
        work or not, called the way `me()` calls it rather than through the whole route, so
        this pin only moves when `_counts()` itself changes shape."""
        change = watch_build.change(stable_key="chg-me-counts-cost")
        cases_build.case(self.tenant, change, owner=self.officer)
        _open_proposal(tenant=self.tenant, proposer=self.officer)
        principal = Principal(
            kind=PrincipalKind.USER,
            subject_id=self.officer.id,
            tenant_id=self.tenant.id,
            permissions=frozenset({perms.CASES_TRIAGE, perms.PROPOSALS_CREATE}),
        )

        tenancy.activate(self.tenant.id)
        with self.assertNumQueries(COUNTS_QUERIES):
            counts = me_logic._counts(principal)  # noqa: SLF001 the module's own test
        self.assertEqual(counts, {"triage": 1, "proposals": 1, "assignedToMe": 1})

