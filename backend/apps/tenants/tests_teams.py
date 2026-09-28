"""A bank's teams, who is in them, putting a member in teams and the departments a person
heads (TEN-02, TEN-03, HOM-05, D-21; `c8-ten-teams-people`).

`GET /tenant/teams` and `GET /tenant/teams/{key}/members` are any member's reads;
`PUT /tenant/members/{userId}/teams` needs `members.manage` and writes one audit event with
the team keys before and after; `GET /me` names the departments the caller heads. Written
before the logic: every read answered 501 `not_built` and the write 404 until it existed.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.test import TestCase
from django.utils import timezone

from apps.identity.models import Membership, User
from apps.library.seeds import seed_languages
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.models import AuditEvent, Tenant
from apps.shared.testing import sign_in
from apps.taxonomy.models import Team
from apps.tenants.models import OrgUnit, OrgUnitKind, TeamMember

V1 = "/api/v1"


def _deactivate(tenant: Tenant, person: User) -> None:
    tenancy.activate(tenant.id)
    Membership.objects.filter(tenant=tenant, user=person).update(deactivated_at=timezone.now())


class Bank(TestCase):
    tenant: Tenant
    other: Tenant
    admin: User
    reader: User
    anna: User
    johan: User
    erik: User
    stranger: User
    retail: Team
    theirs: Team

    @classmethod
    def setUpTestData(cls) -> None:
        seed_languages()
        cls.tenant = factories.tenant(slug="teams-a")
        cls.other = factories.tenant(slug="teams-b")
        cls.admin = factories.member_user(cls.tenant, roles=("admin",))
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        cls.anna = factories.member(cls.tenant, user_row=factories.user(name="Anna Berg")).user
        cls.johan = factories.member(cls.tenant, user_row=factories.user(name="Johan Ek")).user
        cls.erik = factories.member(cls.tenant, user_row=factories.user(name="Erik Dahl")).user
        cls.stranger = factories.member_user(cls.other, roles=("admin",))
        unit = factories.headed_unit(cls.tenant, name="Retail Banking", head=None)
        cls.retail = factories.team(
            cls.tenant, key="retail-compliance", label="Retail compliance", org_unit=unit, members=(cls.johan, cls.anna, cls.erik)
        )
        _deactivate(cls.tenant, cls.erik)
        cls.theirs = factories.team(cls.other, key="their-team", label="Their team", members=(cls.stranger,))

    def get(self, url: str, user: User | None = None) -> Any:
        return self.client.get(V1 + url, **sign_in(user or self.reader, tenant=self.tenant))

    def put_teams(self, person_id: uuid.UUID, teams: list[str], user: User | None = None) -> Any:
        return self.client.put(
            f"{V1}/tenant/members/{person_id}/teams",
            data={"teams": teams},
            content_type="application/json",
            **sign_in(user or self.admin, tenant=self.tenant),
        )

    def keys_of(self, person: User) -> list[str]:
        tenancy.activate(self.tenant.id)
        return sorted(TeamMember.objects.filter(user=person).values_list("team__key", flat=True))


class ListTeams(Bank):
    def test_any_member_reads_the_banks_teams_with_labels_and_active_member_counts(self) -> None:
        response = self.get("/tenant/teams")
        self.assertEqual(response.status_code, 200, response.content)
        page = response.json()
        by_key = {row["key"]: row for row in page["items"]}
        self.assertEqual(page["total"], len(page["items"]))
        self.assertEqual(
            by_key["retail-compliance"],
            {
                "key": "retail-compliance",
                "label": "Retail compliance",
                "orgUnitId": str(self.retail.org_unit_id),
                "email": "",
                "memberCount": 2,
                "active": True,
            },
        )
        self.assertIn("compliance", by_key, "the system team every bank has")
        self.assertNotIn("their-team", by_key, "another bank's team never shows")

    def test_a_retired_team_is_listed_as_inactive(self) -> None:
        tenancy.activate(self.tenant.id)
        Team.objects.filter(pk=self.retail.pk).update(active=False)
        rows = {row["key"]: row for row in self.get("/tenant/teams").json()["items"]}
        self.assertFalse(rows["retail-compliance"]["active"])

    def test_the_page_is_limited_and_total_counts_every_team(self) -> None:
        everything = self.get("/tenant/teams").json()
        page = self.get("/tenant/teams?limit=1&offset=1").json()
        self.assertEqual(page, {"items": everything["items"][1:2], "total": everything["total"]})


class ListTeamMembers(Bank):
    def test_a_teams_active_members_by_name_as_ids_and_names_only(self) -> None:
        response = self.get("/tenant/teams/retail-compliance/members")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json(),
            {"items": [{"id": str(self.anna.id), "name": "Anna Berg"}, {"id": str(self.johan.id), "name": "Johan Ek"}], "total": 2},
        )

    def test_an_empty_team_is_a_200_with_nobody(self) -> None:
        self.assertEqual(self.get("/tenant/teams/compliance/members").json(), {"items": [], "total": 0})

    def test_another_banks_team_is_404(self) -> None:
        response = self.get("/tenant/teams/their-team/members")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "not_found")


class SetMemberTeams(Bank):
    def test_puts_a_member_in_teams_with_one_audit_event_holding_the_keys_before_and_after(self) -> None:
        response = self.put_teams(self.anna.id, ["compliance", "retail-compliance", "compliance"])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["teams"], ["compliance", "retail-compliance"])
        self.assertEqual(self.keys_of(self.anna), ["compliance", "retail-compliance"])
        events = AuditEvent.objects.filter(action="member.teams_changed", tenant_id=self.tenant.id)
        self.assertEqual(events.count(), 1)
        event = events.get()
        self.assertEqual(event.before, {"teams": ["retail-compliance"]})
        self.assertEqual(event.after, {"teams": ["compliance", "retail-compliance"]})
        self.assertEqual(event.subject_type, "membership")

    def test_the_set_replaces_the_old_one_and_an_empty_list_empties_it(self) -> None:
        self.assertEqual(self.put_teams(self.johan.id, ["compliance"]).status_code, 200)
        self.assertEqual(self.keys_of(self.johan), ["compliance"])
        self.assertEqual(self.put_teams(self.johan.id, []).json()["teams"], [])
        self.assertEqual(self.keys_of(self.johan), [])

    def test_a_person_who_is_no_member_here_is_422_unknown_member_and_nothing_is_written(self) -> None:
        for person_id in (self.stranger.id, self.erik.id, uuid.uuid4()):
            with self.subTest(person=person_id):
                response = self.put_teams(person_id, ["compliance"])
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["code"], "unknown_member")
        tenancy.activate(self.other.id)
        self.assertEqual(TeamMember.objects.filter(user=self.stranger).count(), 1)
        self.assertEqual(self.keys_of(self.erik), ["retail-compliance"])
        self.assertFalse(AuditEvent.objects.filter(action="member.teams_changed").exists())

    def test_a_team_the_bank_does_not_have_is_422_unknown_key_and_nothing_is_written(self) -> None:
        for key in ("their-team", "no-such-team"):
            with self.subTest(key=key):
                response = self.put_teams(self.anna.id, ["compliance", key])
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["code"], "unknown_key")
        self.assertEqual(self.keys_of(self.anna), ["retail-compliance"])

    def test_a_retired_team_takes_nobody_new_but_keeps_who_is_in_it(self) -> None:
        tenancy.activate(self.tenant.id)
        Team.objects.filter(pk=self.retail.pk).update(active=False)
        refused = self.put_teams(self.admin.id, ["retail-compliance"])
        self.assertEqual((refused.status_code, refused.json()["code"]), (422, "unknown_key"))
        kept = self.put_teams(self.anna.id, ["retail-compliance", "compliance"])
        self.assertEqual(kept.json()["teams"], ["compliance", "retail-compliance"])

    def test_without_members_manage_it_is_403(self) -> None:
        for user in (self.reader, self.anna):
            with self.subTest(user=user.name):
                response = self.put_teams(self.johan.id, ["compliance"], user=user)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json()["requiredPermission"], perms.MEMBERS_MANAGE)
        self.assertEqual(self.keys_of(self.johan), ["retail-compliance"])

    def test_a_long_or_missing_team_list_is_a_validation_error(self) -> None:
        for body in ({}, {"teams": ["x" * 81]}, {"teams": [f"team-{n}" for n in range(51)]}):
            with self.subTest(body=str(body)[:40]):
                response = self.client.put(
                    f"{V1}/tenant/members/{self.anna.id}/teams",
                    data=body,
                    content_type="application/json",
                    **sign_in(self.admin, tenant=self.tenant),
                )
                self.assertEqual((response.status_code, response.json()["code"]), (422, "validation_error"))

    def test_member_rows_show_their_team_keys(self) -> None:
        rows = {row["userId"]: row for row in self.get("/tenant/members", user=self.admin).json()["items"]}
        self.assertEqual(rows[str(self.anna.id)]["teams"], ["retail-compliance"])
        self.assertEqual(rows[str(self.admin.id)]["teams"], [])
        self.assertEqual(rows[str(self.erik.id)]["teams"], ["retail-compliance"], "a deactivated member's row still says where they were")


class HeadOf(Bank):
    def test_me_names_the_active_departments_the_caller_heads(self) -> None:
        karin = factories.member(self.tenant, user_row=factories.user(name="Karin Holm")).user
        retail = factories.headed_unit(self.tenant, name="Retail Banking", head=karin)
        legal = factories.headed_unit(self.tenant, name="Legal", head=karin, kind=OrgUnitKind.FUNCTION)
        factories.headed_unit(self.tenant, name="Closed unit", head=karin)
        tenancy.activate(self.tenant.id)
        OrgUnit.objects.filter(name="Closed unit").update(active=False)
        factories.headed_unit(self.tenant, name="Example Bank AB", head=karin, kind=OrgUnitKind.LEGAL_ENTITY)
        factories.headed_unit(self.tenant, name="Cards", head=self.anna)
        factories.headed_unit(self.other, name="Their department", head=self.stranger)

        me = self.get("/me", user=karin).json()
        self.assertEqual(me["headOf"], [{"id": str(legal.id), "name": "Legal"}, {"id": str(retail.id), "name": "Retail Banking"}])

    def test_someone_who_heads_nothing_reads_an_empty_list(self) -> None:
        self.assertEqual(self.get("/me").json()["headOf"], [])


class TeamDepartment(Bank):
    """TEN-02 (`ten02-team-department`): a team is put in a department, moved to another or
    taken out of one on the team list's own create and edit routes, `extra.orgUnitId`.
    Written before the logic: the department was dropped as a column the list did not have."""

    retail_unit: OrgUnit
    cards_unit: OrgUnit

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.retail_unit = factories.headed_unit(cls.tenant, name="Retail department", head=None)
        cls.cards_unit = factories.headed_unit(cls.tenant, name="Cards department", head=None, kind=OrgUnitKind.FUNCTION)

    def create(self, extra: dict[str, Any], user: User | None = None) -> Any:
        return self.client.post(
            f"{V1}/vocab/team",
            data={"labels": {"en": "Payments compliance"}, "key": "payments_compliance", "extra": extra},
            content_type="application/json",
            **sign_in(user or self.admin, tenant=self.tenant),
        )

    def patch(self, key: str, extra: dict[str, Any], version: int | None = None, user: User | None = None) -> Any:
        headers = sign_in(user or self.admin, tenant=self.tenant)
        if version is not None:
            headers["HTTP_IF_MATCH"] = f'"{version}"'
        return self.client.patch(f"{V1}/vocab/team/{key}", data={"extra": extra}, content_type="application/json", **headers)

    def department_of(self, key: str) -> uuid.UUID | None:
        tenancy.activate(self.tenant.id)
        return Team.objects.get(tenant=self.tenant, key=key).org_unit_id

    def events(self, action: str, key: str) -> list[AuditEvent]:
        tenancy.activate(self.tenant.id)
        return list(AuditEvent.objects.filter(action=action, subject_title=f"team:{key}").order_by("created", "id"))

    def test_a_team_is_created_in_a_department_with_one_audit_row_naming_it(self) -> None:
        response = self.create({"orgUnitId": str(self.retail_unit.id)})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["extra"]["orgUnitId"], str(self.retail_unit.id))
        self.assertEqual(self.department_of("payments_compliance"), self.retail_unit.id)
        [event] = self.events("vocabulary.created", "payments_compliance")
        self.assertEqual(event.after["extra"], {"email": "", "orgUnitId": str(self.retail_unit.id)})
        listed = {row["key"]: row for row in self.get("/tenant/teams").json()["items"]}
        self.assertEqual(listed["payments_compliance"]["orgUnitId"], str(self.retail_unit.id))

    def test_a_team_is_still_created_without_a_department(self) -> None:
        response = self.create({})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertIsNone(response.json()["extra"]["orgUnitId"])
        self.assertIsNone(self.department_of("payments_compliance"))

    def test_an_edit_moves_the_team_under_if_match_with_the_department_before_and_after(self) -> None:
        response = self.patch("retail-compliance", {"orgUnitId": str(self.cards_unit.id)}, version=1)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()["extra"]["orgUnitId"], response.json()["version"]), (str(self.cards_unit.id), 2))
        self.assertEqual(self.department_of("retail-compliance"), self.cards_unit.id)
        [event] = self.events("vocabulary.updated", "retail-compliance")
        self.assertEqual(event.before["extra"]["orgUnitId"], str(self.retail.org_unit_id))
        self.assertEqual(event.after["extra"]["orgUnitId"], str(self.cards_unit.id))

    def test_a_stale_if_match_is_409_and_the_team_stays_where_it_was(self) -> None:
        response = self.patch("retail-compliance", {"orgUnitId": str(self.cards_unit.id)}, version=7)
        self.assertEqual((response.status_code, response.json()["code"]), (409, "stale_write"))
        self.assertEqual(self.department_of("retail-compliance"), self.retail.org_unit_id)

    def test_null_takes_the_team_out_of_its_department_and_a_rename_alone_keeps_it(self) -> None:
        renamed = self.client.patch(
            f"{V1}/vocab/team/retail-compliance",
            data={"labels": {"en": "Retail team"}},
            content_type="application/json",
            **sign_in(self.admin, tenant=self.tenant),
        )
        self.assertEqual(renamed.status_code, 200, renamed.content)
        self.assertEqual(self.department_of("retail-compliance"), self.retail.org_unit_id)
        cleared = self.patch("retail-compliance", {"orgUnitId": None})
        self.assertEqual(cleared.status_code, 200, cleared.content)
        self.assertIsNone(self.department_of("retail-compliance"))
        self.assertIsNone(self.events("vocabulary.updated", "retail-compliance")[-1].after["extra"]["orgUnitId"])

    def test_another_banks_department_is_404_and_nothing_is_written(self) -> None:
        theirs = factories.headed_unit(self.other, name="Their department", head=None)
        renamed = self.client.patch(
            f"{V1}/vocab/team/retail-compliance",
            data={"labels": {"en": "Their retail team"}, "extra": {"orgUnitId": str(theirs.id)}},
            content_type="application/json",
            **sign_in(self.admin, tenant=self.tenant),
        )
        for response in (self.create({"orgUnitId": str(theirs.id)}), self.patch("retail-compliance", {"orgUnitId": str(theirs.id)}), renamed):
            self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))
        self.assertEqual(self.get("/tenant/teams/retail-compliance/members").status_code, 200)
        labels = {row["key"]: row["label"] for row in self.get("/tenant/teams").json()["items"]}
        self.assertEqual(labels["retail-compliance"], "Retail compliance", "a refused department leaves the name as it was")
        self.assertFalse(Team.objects.filter(key="payments_compliance").exists())
        self.assertEqual(self.department_of("retail-compliance"), self.retail.org_unit_id)
        self.assertEqual(self.events("vocabulary.updated", "retail-compliance"), [])
        unknown = self.create({"orgUnitId": str(uuid.uuid4())})
        self.assertEqual((unknown.status_code, unknown.json()["code"]), (404, "not_found"))

    def test_a_unit_that_is_no_active_department_is_422(self) -> None:
        entity = factories.headed_unit(self.tenant, name="Example Bank AB", head=None, kind=OrgUnitKind.LEGAL_ENTITY)
        group = factories.headed_unit(self.tenant, name="Example Group", head=None, kind=OrgUnitKind.GROUP)
        closed = factories.headed_unit(self.tenant, name="Closed department", head=None)
        tenancy.activate(self.tenant.id)
        OrgUnit.objects.filter(pk=closed.pk).update(active=False)
        for unit in (entity, group, closed):
            response = self.patch("retail-compliance", {"orgUnitId": str(unit.id)})
            self.assertEqual((response.status_code, response.json()["code"]), (422, "validation_error"), unit.name)
        garbled = self.patch("retail-compliance", {"orgUnitId": "not-a-uuid"})
        self.assertEqual((garbled.status_code, garbled.json()["code"]), (422, "validation_error"))
        self.assertEqual(self.department_of("retail-compliance"), self.retail.org_unit_id)

    def test_without_vocab_manage_it_is_403(self) -> None:
        response = self.patch("retail-compliance", {"orgUnitId": str(self.cards_unit.id)}, user=self.reader)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.department_of("retail-compliance"), self.retail.org_unit_id)
