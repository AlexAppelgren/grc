"""Removing a member who owns open work (TEN-05, TEN-03, COL-04; `c8-ten-reassignment`).

`GET /tenant/members/{userId}/open-work` counts what a member owns by kind, the items they
take part in and their teams, and changes nothing. `DELETE /tenant/members/{userId}` refuses
a member with open work, 422 `reassignment_required` with the counts. `POST
/tenant/members/{userId}/remove` names a new owner per kind and, with a fresh step-up, moves
every item, ends the member's participations and team memberships and deactivates them in
one transaction: one audit event per item and one for the removal. A team keeps what it
owns. Written before the logic, when both routes answered 501 `not_built`.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.collab import testing as collab_testing
from apps.collab.models import Participant
from apps.identity.models import Membership, User
from apps.register.logic import ensure_register_entry
from apps.register.models import Gap, TenantObligation, TenantObligationScope
from apps.shared import factories, tenancy
from apps.shared.models import AuditEvent, Tenant
from apps.shared.testing import sign_in
from apps.taxonomy.models import ComplianceStatus, GapCategory, GapSource, GapStatus, LinkKind, RiskRating, Team
from apps.tenants.models import InternalItem, OrgUnitKind, TeamMember

V1 = "/api/v1"


def owned_work(tenant: Tenant, erik: User, officer: User) -> SimpleNamespace:
    """Erik's work in `tenant`: first-line owner of two register entries and contact on a
    third, owner of one legal entity's row, of an open and a closed gap and of an active and
    a retired internal item, taking part in three entries, and in the teams "Legal" and
    "Cards". "Cards" owns an entry of its own and takes part in one. TEN-S9's Erik."""
    legal = factories.team(tenant, key="legal", label="Legal", members=(erik,))
    cards = factories.team(tenant, key="cards", label="Cards", members=(erik, officer))
    duties = [collab_testing.obligation() for _ in range(5)]
    entity = factories.department(tenant, name="Example Bank AB", head=None, kind=OrgUnitKind.LEGAL_ENTITY)
    with transaction.atomic():
        tenancy.activate(tenant.id)
        actor = factories.user_actor(user_id=officer.id)
        entries = [ensure_register_entry(tenant_id=tenant.id, obligation_id=duty.id, actor=actor) for duty in duties]
        owned, contact, team_owned = entries[0:2], entries[2], entries[3]
        TenantObligation.objects.filter(pk__in=[e.pk for e in owned]).update(first_line_owner=erik)
        TenantObligation.objects.filter(pk=contact.pk).update(compliance_contact=erik, first_line_owner=officer)
        TenantObligation.objects.filter(pk=team_owned.pk).update(owner_team=cards)
        scope = TenantObligationScope.objects.create(
            tenant=tenant,
            tenant_obligation=owned[0],
            org_unit=entity,
            compliance_status=ComplianceStatus.objects.get(is_default=True, active=True),
            owner=erik,
        )
        statuses = {row.kind: row for row in GapStatus.objects.filter(active=True).order_by("sort_order")}
        gap_fields = {
            "tenant": tenant,
            "tenant_obligation": owned[1],
            "severity": RiskRating.objects.order_by("sort_order").first(),
            "source": GapSource.objects.order_by("sort_order").first(),
            "identified_by": officer,
            "owner": erik,
        }
        gap = Gap.objects.create(title="Retention schedule missing", status=statuses[GapCategory.OPEN.value], **gap_fields)
        closed_gap = Gap.objects.create(
            title="Old gap", status=statuses[GapCategory.CLOSED.value], closed_by=officer, closed_at=timezone.now(), **gap_fields
        )
        policy = LinkKind.objects.get(key="policy")
        item = InternalItem.objects.create(tenant=tenant, kind=policy, name="Complaints policy", owner_user=erik)
        retired_item = InternalItem.objects.create(tenant=tenant, kind=policy, name="Old policy", owner_user=erik, active=False)
        takes_part = [
            Participant.objects.create(tenant=tenant, tenant_obligation=entry, user=erik, added_by=officer)
            for entry in (entries[2], entries[3], entries[4])
        ]
        team_part = Participant.objects.create(tenant=tenant, tenant_obligation=entries[4], team=cards, added_by=officer)
    return SimpleNamespace(
        legal=legal,
        cards=cards,
        owned=owned,
        contact=contact,
        team_owned=team_owned,
        scope=scope,
        gap=gap,
        closed_gap=closed_gap,
        item=item,
        retired_item=retired_item,
        takes_part=takes_part,
        team_part=team_part,
    )


EVERY_KIND = {
    "register_entry": 3,
    "register_entity": 1,
    "gap": 1,
    "internal_item": 1,
    "participation": 3,
    "team_membership": 2,
}


class Removal(TestCase):
    tenant: Tenant
    other: Tenant
    admin: User
    officer: User
    erik: User
    anna: User
    stranger: User
    work: SimpleNamespace

    @classmethod
    def setUpTestData(cls) -> None:
        cls.tenant = factories.tenant(slug="removal-a")
        cls.other = factories.tenant(slug="removal-b")
        cls.admin = factories.member_user(cls.tenant, roles=("admin",))
        cls.officer = factories.member_user(cls.tenant, roles=("compliance_officer",))
        cls.erik = factories.member(cls.tenant, roles=("compliance_officer",), user_row=factories.user(name="Erik Dahl")).user
        cls.anna = factories.member(cls.tenant, roles=("compliance_officer",), user_row=factories.user(name="Anna Berg")).user
        cls.stranger = factories.member_user(cls.other, roles=("admin",))
        cls.work = owned_work(cls.tenant, cls.erik, cls.officer)

    # -- helpers ---------------------------------------------------------------------------
    def open_work(self, person: User, user: User | None = None) -> Any:
        return self.client.get(f"{V1}/tenant/members/{person.id}/open-work", **sign_in(user or self.admin, tenant=self.tenant))

    def remove(self, owners: list[dict[str, Any]], *, step_up: bool = True, person: User | None = None) -> Any:
        return self.client.post(
            f"{V1}/tenant/members/{(person or self.erik).id}/remove",
            data={"owners": owners},
            content_type="application/json",
            **sign_in(self.admin, tenant=self.tenant, step_up=step_up),
        )

    def all_owners(self) -> list[dict[str, Any]]:
        return [
            {"kind": "register_entry", "userId": str(self.anna.id)},
            {"kind": "register_entity", "teamKey": "legal"},
            {"kind": "gap", "userId": str(self.anna.id)},
            {"kind": "internal_item", "teamKey": "cards"},
        ]

    def snapshot(self) -> dict[str, Any]:
        """Every row the removal may touch, read back, and the length of the audit trail."""
        tenancy.activate(self.tenant.id)
        return {
            "entries": list(TenantObligation.objects.order_by("id").values_list("id", "first_line_owner_id", "compliance_contact_id", "owner_team_id", "version")),
            "scopes": list(TenantObligationScope.objects.order_by("id").values_list("id", "owner_id", "owner_team_id", "version")),
            "gaps": list(Gap.objects.order_by("id").values_list("id", "owner_id", "owner_team_id", "version")),
            "items": list(InternalItem.objects.order_by("id").values_list("id", "owner_user_id", "owner_team_id")),
            "participants": list(Participant.objects.order_by("id").values_list("id", "removed_at")),
            "teams": list(TeamMember.objects.order_by("id").values_list("id", flat=True)),
            "membership": Membership.objects.get(user=self.erik).deactivated_at,
            # Signing in for each request writes `session.created`; nothing else may be written.
            "audit": AuditEvent.objects.exclude(action="session.created").count(),
        }

    # -- the preview -----------------------------------------------------------------------
    def test_the_preview_counts_every_kind_and_names_the_teams_without_changing_anything(self) -> None:
        before = self.snapshot()
        response = self.open_work(self.erik)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["member"], {"id": str(self.erik.id), "name": "Erik Dahl"})
        self.assertEqual({row["kind"]: row["count"] for row in body["items"]}, EVERY_KIND)
        self.assertEqual(sorted(body["teams"]), ["cards", "legal"])
        self.assertEqual(self.snapshot(), before)

    def test_a_member_who_holds_nothing_has_an_empty_preview(self) -> None:
        body = self.open_work(self.anna).json()
        self.assertEqual((body["items"], body["teams"]), ([], []))

    def test_the_preview_needs_members_manage_and_never_reaches_another_bank(self) -> None:
        self.assertEqual(self.open_work(self.erik, user=self.officer).status_code, 403)
        self.assertEqual(self.open_work(self.stranger).status_code, 404)

    # -- the plain removal -----------------------------------------------------------------
    def test_a_plain_removal_of_a_member_with_open_work_answers_reassignment_required_with_the_counts(self) -> None:
        before = self.snapshot()
        response = self.client.delete(f"{V1}/tenant/members/{self.erik.id}", **sign_in(self.admin, tenant=self.tenant))
        self.assertEqual(response.status_code, 422, response.content)
        problem = response.json()
        self.assertEqual(problem["code"], "reassignment_required")
        self.assertEqual({row["field"]: row["count"] for row in problem["errors"]}, EVERY_KIND)
        self.assertEqual(self.snapshot(), before)

    def test_a_plain_removal_of_a_member_who_holds_nothing_still_deactivates_them(self) -> None:
        response = self.client.delete(f"{V1}/tenant/members/{self.anna.id}", **sign_in(self.admin, tenant=self.tenant))
        self.assertEqual(response.status_code, 204, response.content)
        tenancy.activate(self.tenant.id)
        self.assertIsNotNone(Membership.objects.get(user=self.anna).deactivated_at)

    # -- refusals, each changing nothing ---------------------------------------------------
    def test_a_removal_without_a_fresh_step_up_is_refused(self) -> None:
        before = self.snapshot()
        response = self.remove(self.all_owners(), step_up=False)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "step_up_required")
        self.assertEqual(self.snapshot(), before)

    def test_a_kind_the_member_owns_with_no_new_owner_is_refused(self) -> None:
        before = self.snapshot()
        response = self.remove(self.all_owners()[:3])
        self.assertEqual(response.status_code, 422, response.content)
        problem = response.json()
        self.assertEqual(problem["code"], "reassignment_required")
        self.assertEqual([row["field"] for row in problem["errors"]], ["internal_item"])
        self.assertEqual(self.snapshot(), before)

    def test_a_kind_named_twice_is_refused(self) -> None:
        response = self.remove([*self.all_owners(), {"kind": "gap", "teamKey": "legal"}])
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_a_new_owner_must_be_another_active_member_of_the_bank(self) -> None:
        tenancy.activate(self.tenant.id)
        gone = factories.member(self.tenant).user
        Membership.objects.filter(user=gone).update(deactivated_at=timezone.now())
        before = self.snapshot()
        for target in (self.erik, self.stranger, gone, SimpleNamespace(id=uuid.uuid4())):
            with self.subTest(target=target.id):
                owners = [{**self.all_owners()[0], "userId": str(target.id)}, *self.all_owners()[1:]]
                response = self.remove(owners)
                self.assertEqual(response.status_code, 422, response.content)
                self.assertEqual(response.json()["code"], "unknown_member")
        self.assertEqual(self.snapshot(), before)

    def test_a_new_owning_team_must_be_an_active_team_of_the_bank(self) -> None:
        factories.team(self.other, key="their-team", label="Their team")
        tenancy.activate(self.tenant.id)
        factories.team(self.tenant, key="retired", label="Retired")
        tenancy.activate(self.tenant.id)
        Team.objects.filter(key="retired").update(active=False)
        before = self.snapshot()
        for key in ("their-team", "retired", "nobody"):
            with self.subTest(team=key):
                response = self.remove([*self.all_owners()[:3], {"kind": "internal_item", "teamKey": key}])
                self.assertEqual(response.status_code, 422, response.content)
                self.assertEqual(response.json()["code"], "unknown_key")
        self.assertEqual(self.snapshot(), before)

    def test_another_banks_member_is_not_found(self) -> None:
        self.assertEqual(self.remove(self.all_owners(), person=self.stranger).status_code, 404)

    def test_a_failure_halfway_leaves_nothing_changed(self) -> None:
        """The last step, the deactivation, refuses after every item has moved: all of it
        rolls back with it."""
        before = self.snapshot()
        refused = ValidationError("A tenant always keeps one administrator.", code="last_admin")
        with mock.patch("apps.identity.members_logic.deactivate_member", side_effect=refused):
            response = self.remove(self.all_owners())
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(self.snapshot(), before)

    # -- the confirm -----------------------------------------------------------------------
    def test_the_confirm_moves_every_item_ends_the_rest_and_deactivates_in_one_audited_step(self) -> None:
        tenancy.activate(self.tenant.id)
        earlier = set(AuditEvent.objects.values_list("id", flat=True))
        response = self.remove(self.all_owners())
        self.assertEqual(response.status_code, 204, response.content)
        tenancy.activate(self.tenant.id)
        work, anna = self.work, self.anna
        for entry in TenantObligation.objects.filter(pk__in=[e.pk for e in work.owned]):
            self.assertEqual((entry.first_line_owner_id, entry.version), (anna.id, 2))
        contact = TenantObligation.objects.get(pk=work.contact.pk)
        self.assertEqual((contact.compliance_contact_id, contact.first_line_owner_id), (anna.id, self.officer.id))
        scope = TenantObligationScope.objects.get(pk=work.scope.pk)
        self.assertEqual((scope.owner_id, scope.owner_team_id, scope.version), (None, work.legal.id, 2))
        self.assertEqual(Gap.objects.get(pk=work.gap.pk).owner_id, anna.id)
        item = InternalItem.objects.get(pk=work.item.pk)
        self.assertEqual((item.owner_user_id, item.owner_team_id), (None, work.cards.id))
        # Closed and retired work is history, and stays as it was.
        self.assertEqual(Gap.objects.get(pk=work.closed_gap.pk).owner_id, self.erik.id)
        self.assertEqual(InternalItem.objects.get(pk=work.retired_item.pk).owner_user_id, self.erik.id)
        ended = Participant.objects.filter(pk__in=[p.pk for p in work.takes_part])
        self.assertEqual({(p.removed_by_id, p.removed_at is not None) for p in ended}, {(self.admin.id, True)})
        self.assertFalse(TeamMember.objects.filter(user=self.erik).exists())
        self.assertIsNotNone(Membership.objects.get(user=self.erik).deactivated_at)

        events = AuditEvent.objects.filter(tenant_id=self.tenant.id).exclude(id__in=earlier).exclude(action="session.created")
        by_action: dict[str, int] = {}
        for event in events:
            by_action[event.action] = by_action.get(event.action, 0) + 1
        self.assertEqual(
            by_action,
            {
                "register_entry.reassigned": 3,
                "register_entity.reassigned": 1,
                "gap.reassigned": 1,
                "internal_item.reassigned": 1,
                "participant.removed": 3,
                "team_member.removed": 2,
                "member.deactivated": 1,
            },
        )
        removal = events.get(action="member.deactivated")
        self.assertIsNotNone(removal.step_up_assertion_id)
        self.assertEqual({e.step_up_assertion_id for e in events}, {removal.step_up_assertion_id})
        moved = events.get(action="gap.reassigned")
        self.assertEqual((moved.before, moved.after), ({"ownerId": str(self.erik.id), "ownerTeamId": None}, {"ownerId": str(anna.id), "ownerTeamId": None}))

    def test_what_a_team_owns_and_takes_part_in_is_untouched(self) -> None:
        """TEN-S3: the team "Cards" keeps its entry and its participation when Erik leaves it."""
        self.assertEqual(self.remove(self.all_owners()).status_code, 204)
        tenancy.activate(self.tenant.id)
        self.assertEqual(TenantObligation.objects.get(pk=self.work.team_owned.pk).owner_team_id, self.work.cards.id)
        self.assertIsNone(Participant.objects.get(pk=self.work.team_part.pk).removed_at)
        self.assertTrue(TeamMember.objects.filter(team=self.work.cards, user=self.officer).exists())

    def test_a_removed_member_is_not_removed_twice(self) -> None:
        self.assertEqual(self.remove(self.all_owners()).status_code, 204)
        self.assertEqual(self.remove(self.all_owners()).status_code, 404)

