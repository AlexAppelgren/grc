"""`GET /me` counts and `lastVisitAt` (f03-T48, HOM-01, ID-04, AC-HOM1, D-23).

`Home` carries no `decideNow` field (chunk 6 ruling 1): the queue counts Today's "Decide
now" panel reads live here instead, so a number has one source. These tests prove the
counts are independently permission-filtered (0, never a 403), that they read under
row-level security so a second tenant's rows never reach them, that the read writes
nothing, and that the reads cost a fixed, pinned number of queries. The four decision
counts R2 adds (x-decide-now-counts: CAS-06, REG-03, TEN-06, ACC-08) count only what the
caller may decide, never a request the caller made themselves (four eyes).
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from django.test import TestCase
from django.utils import timezone

from apps.cases import testing as cases_build
from apps.cases.models import ChangeCase
from apps.collab.logic import notify
from apps.collab.models import Notification, NotificationKind
from apps.identity import me_logic
from apps.identity.models import Membership, User
from apps.governance.models import TenantReachRequest
from apps.proposals.models import OriginType, Proposal, ProposalKind, ProposalStatus, ProposalTenant
from apps.register.models import Gap
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.authentication import Principal, PrincipalKind
from apps.shared.models import AuditEvent, Tenant
from apps.shared.testing import sign_in
from apps.taxonomy.models import ApprovalStatus, CaseStatusCategory, GapStatus
from apps.tenants.models import SupportAccess, SupportAccessLevel, SupportAccessStatus
from apps.watch import testing as watch_build

V1 = "/api/v1"
# `_counts()`'s own eight independent reads, one query each: pinned so a future one that
# chains a ninth behind another has to look at this number rather than drift past it.
COUNTS_QUERIES = 8
ZEROS = {
    "triage": 0,
    "proposals": 0,
    "assignedToMe": 0,
    "unreadNotifications": 0,
    "signoffs": 0,
    "riskAcceptances": 0,
    "supportAccessRequests": 0,
    "tenantReachRequests": 0,
}


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


def _notify(tenant: Tenant, case_id: uuid.UUID, *people: User) -> None:
    tenancy.activate(tenant.id)
    notify(
        tenant_id=tenant.id,
        kind=NotificationKind.ASSIGNED,
        subject_type="change_case",
        subject_id=case_id,
        candidates=[(person.id, "owner") for person in people],
    )


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
        self.assertEqual(body["counts"], ZEROS)

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

        self.assertEqual(self.me(self.officer)["counts"], ZEROS)

    def test_unread_notifications_counts_the_callers_own_unread_rows_in_this_bank(self) -> None:
        case = cases_build.case(self.tenant, watch_build.change(stable_key="chg-me-counts-unread"))
        _notify(self.tenant, case.id, self.reader, self.officer)
        _notify(self.tenant, case.id, self.reader)
        # Another bank's notification of the same person never reaches this count.
        factories.member(self.other_tenant, user_row=self.reader)
        other_case = cases_build.case(self.other_tenant, watch_build.change(stable_key="chg-me-counts-unread-other"))
        _notify(self.other_tenant, other_case.id, self.reader)

        self.assertEqual(self.me(self.reader)["counts"]["unreadNotifications"], 2)
        tenancy.activate(self.tenant.id)
        Notification.objects.filter(user=self.reader).update(read_at=timezone.now())
        self.assertEqual(self.me(self.reader)["counts"]["unreadNotifications"], 0, "a read notification leaves the count")
        self.assertEqual(self.me(self.officer)["counts"]["unreadNotifications"], 1, "one person's reads are their own")

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

    def test_the_four_reads_fan_out_at_a_fixed_query_count(self) -> None:
        """None chained behind another: the same four queries whether the caller has open
        work or not, called the way `me()` calls it rather than through the whole route, so
        this pin only moves when `_counts()` itself changes shape."""
        change = watch_build.change(stable_key="chg-me-counts-cost")
        case = cases_build.case(self.tenant, change, owner=self.officer)
        _open_proposal(tenant=self.tenant, proposer=self.officer)
        _notify(self.tenant, case.id, self.officer)
        principal = Principal(
            kind=PrincipalKind.USER,
            subject_id=self.officer.id,
            tenant_id=self.tenant.id,
            permissions=frozenset(
                {perms.CASES_TRIAGE, perms.PROPOSALS_CREATE, perms.CASES_SIGNOFF, perms.RISK_ACCEPT_APPROVE, perms.SECURITY_MANAGE}
            ),
        )

        tenancy.activate(self.tenant.id)
        with self.assertNumQueries(COUNTS_QUERIES):
            counts = me_logic._counts(principal)  # noqa: SLF001 the module's own test
        self.assertEqual(counts, {**ZEROS, "triage": 1, "proposals": 1, "assignedToMe": 1, "unreadNotifications": 1})



def _waiting_signoff(tenant: Tenant, stable_key: str, *, requester: User) -> None:
    """A case in the `signoff` category, sent for sign-off by `requester`, its owner."""
    case = cases_build.case(tenant, watch_build.change(stable_key=stable_key), owner=requester)
    cases_build.in_category(case, CaseStatusCategory.SIGNOFF)
    tenancy.activate(tenant.id)
    ChangeCase.objects.filter(pk=case.pk).update(signoff_requested_by=requester, signoff_requested_at=timezone.now())


def _support_request(tenant: Tenant, *, requested_at: datetime.datetime | None = None, level: str = SupportAccessLevel.READ.value) -> SupportAccess:
    """Platform support's request to read `tenant`, written as `support_access.request_access`
    writes it: pending until `SUPPORT_ACCESS_REQUEST_TTL_HOURS` after it was asked."""
    now = requested_at or timezone.now()
    requester = factories.platform_user(email=f"support-{uuid.uuid4().hex[:8]}@bleqq.test")
    tenancy.activate(tenant.id)
    return SupportAccess.objects.create(
        tenant=tenant,
        platform_user=requester,
        reason="The bank's watch feed stopped updating.",
        access_level=level,
        status=SupportAccessStatus.REQUESTED.value,
        hours=2,
        requested_at=now,
        request_expires_at=now + datetime.timedelta(hours=24),
    )


class DecisionCounts(TestCase):
    """Sign-offs, risk acceptances, support access and tenant reach (x-decide-now-counts,
    CAS-06, REG-03, TEN-06, ACC-08): each counts what the caller's own permission lets them
    decide, and never a request the caller made, which the four-eyes rule would refuse them."""

    tenant: Tenant
    other_tenant: Tenant
    approver: User
    officer: User
    admin: User
    reader: User

    @classmethod
    def setUpTestData(cls) -> None:
        watch_build.seed_watch_reference()
        cls.tenant = factories.tenant(slug="me-decide")
        cls.other_tenant = factories.tenant(slug="me-decide-other")
        cls.approver = factories.member_user(cls.tenant, roles=("approver",))
        cls.officer = factories.member_user(cls.tenant, roles=("compliance_officer",))
        cls.admin = factories.member_user(cls.tenant, roles=("admin",))
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))

    def counts(self, user: User) -> dict[str, int]:
        response = self.client.get(f"{V1}/me", **sign_in(user, tenant=self.tenant))
        self.assertEqual(response.status_code, 200)
        counts: dict[str, int] = response.json()["counts"]
        return counts

    def test_signoffs_count_cases_waiting_for_someone_else_and_need_cases_signoff(self) -> None:
        _waiting_signoff(self.tenant, "chg-me-decide-signoff", requester=self.officer)
        # A case still being worked is not waiting for a sign-off.
        cases_build.in_category(
            cases_build.case(self.tenant, watch_build.change(stable_key="chg-me-decide-implementing"), owner=self.officer),
            CaseStatusCategory.IMPLEMENTING,
        )

        self.assertEqual(self.counts(self.approver)["signoffs"], 1)
        self.assertEqual(self.counts(self.officer)["signoffs"], 0, "the officer lacks cases.signoff: a true 0, not a refusal")

    def test_a_signoff_the_caller_asked_for_is_not_theirs_to_decide(self) -> None:
        _waiting_signoff(self.tenant, "chg-me-decide-own-signoff", requester=self.approver)

        self.assertEqual(self.counts(self.approver)["signoffs"], 0)

    def test_risk_acceptances_count_waiting_approvals_asked_by_someone_else(self) -> None:
        waiting = factories.gap(self.tenant)
        own = factories.gap(self.tenant)
        accepted = factories.gap(self.tenant)
        tenancy.activate(self.tenant.id)
        Gap.objects.filter(pk=own.pk).update(acceptance_requested_by=self.approver)
        Gap.objects.filter(pk=accepted.pk).update(
            accepted_by=self.approver,
            accepted_at=timezone.now(),
            status=GapStatus.objects.get(tenant=self.tenant, key="risk_accepted"),
        )

        self.assertEqual(self.counts(self.approver)["riskAcceptances"], 1, f"only {waiting.id} waits for the approver")
        self.assertEqual(self.counts(self.admin)["riskAcceptances"], 0, "the admin lacks risk.accept.approve")

    def test_a_closed_gap_with_an_old_request_waits_for_nobody(self) -> None:
        closed = factories.gap(self.tenant)
        tenancy.activate(self.tenant.id)
        Gap.objects.filter(pk=closed.pk).update(status=GapStatus.objects.get(tenant=self.tenant, key="closed"))

        self.assertEqual(self.counts(self.approver)["riskAcceptances"], 0)

    def test_support_access_counts_pending_requests_for_security_manage(self) -> None:
        _support_request(self.tenant)
        # Lapsed, decided and chunk 1's write-level recovery rows wait for nobody.
        _support_request(self.tenant, requested_at=timezone.now() - datetime.timedelta(hours=25))
        declined = _support_request(self.tenant)
        declined.status = SupportAccessStatus.DECLINED.value
        declined.save(update_fields=["status"])
        _support_request(self.tenant, level=SupportAccessLevel.WRITE.value)

        self.assertEqual(self.counts(self.admin)["supportAccessRequests"], 1)
        self.assertEqual(self.counts(self.officer)["supportAccessRequests"], 0, "the officer lacks security.manage")

    def test_tenant_reach_counts_a_pending_request_someone_else_made(self) -> None:
        request = factories.tenant_reach_request(self.tenant)

        self.assertEqual(self.counts(self.admin)["tenantReachRequests"], 1)
        requester = User.objects.get(pk=request.requested_by_id)
        self.assertEqual(self.counts(requester)["tenantReachRequests"], 0, "the requester never decides their own request")
        self.assertEqual(self.counts(self.officer)["tenantReachRequests"], 0, "the officer lacks security.manage")

    def test_a_decided_reach_request_waits_for_nobody(self) -> None:
        request = factories.tenant_reach_request(self.tenant)
        tenancy.activate(self.tenant.id)
        TenantReachRequest.objects.filter(pk=request.pk).update(
            status=ApprovalStatus.REJECTED.value, decided_by=self.admin, decided_at=timezone.now()
        )

        self.assertEqual(self.counts(self.admin)["tenantReachRequests"], 0)

    def test_another_banks_decisions_never_reach_the_count(self) -> None:
        other_owner = factories.member_user(self.other_tenant, roles=("compliance_officer",))
        _waiting_signoff(self.other_tenant, "chg-me-decide-other-signoff", requester=other_owner)
        factories.gap(self.other_tenant)
        _support_request(self.other_tenant)
        factories.tenant_reach_request(self.other_tenant)
        everything = factories.member_user(self.tenant, roles=("approver", "admin"))

        self.assertEqual(self.counts(everything), ZEROS)
