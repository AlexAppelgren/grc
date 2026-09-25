"""The participant table and its logic (collab 0002, `collab/participants.py`; COL-04, D-18,
D-19). The scenarios themselves are COL-S6 to COL-S8 in tests_scenarios.py; these pin what
they rest on.

The table: the database refuses every reference to another bank's register entry, case,
team or person, and anyone who is not a member (walking the migration's own
`COMPOSITE_KEYS`, so a key added there is proved here without a line of its own); a row
names exactly one subject and exactly one participant; one live row per subject and
participant; a row is never deleted.

The logic: a read never creates a register entry, a refused add leaves none behind, a team
is added without a read check, an ended participation leaves the list and may be added
again, and a removal of someone else's row by a holder of `register.edit` is `removed`,
not `left`.

Proven to fail 2026-09-25: with the composite-key operations left out of a scratch copy of
collab 0002 the cross-tenant test named each key that went through; with `num_nonnulls`
replaced by `true` the check test named both constraints."""

from __future__ import annotations

import importlib
import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.cases import testing as cases_testing
from apps.collab import testing as collab_testing
from apps.collab.models import Participant
from apps.identity import session_logic
from apps.identity.models import Membership
from apps.register.logic import ensure_register_entry
from apps.register.models import TenantObligation
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.authentication import PrincipalKind
from apps.shared.models import AuditEvent, Tenant
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.shared.routes import iter_operations
from apps.watch import testing as watch_build
from config.api import api

COMPOSITE_KEYS = importlib.import_module("apps.collab.migrations.0002_participant").COMPOSITE_KEYS


class Bank:
    """One bank with a register entry, a case, a team and two members, and one live
    participation of each kind. The case's row names a remover too, so the remover's key
    has a row to be proved on."""

    def __init__(self, tenant: Tenant, obligation_id: uuid.UUID) -> None:
        self.tenant = tenant
        self.officer = factories.member_user(tenant, roles=("compliance_officer",))
        self.person = factories.member_user(tenant)
        self.team = collab_testing.team(tenant, f"legal-{tenant.slug}", "Legal")
        change = watch_build.change()
        self.case = cases_testing.case(tenant, change)
        with transaction.atomic():
            tenancy.activate(tenant.id)
            self.entry = ensure_register_entry(
                tenant_id=tenant.id, obligation_id=obligation_id, actor=factories.user_actor(user_id=self.officer.id)
            )
            self.on_entry = self.create(tenant_obligation_id=self.entry.id, user_id=self.person.id)
            self.on_case = self.create(case_id=self.case.id, team_id=self.team.id, removed_by_id=self.officer.id)

    def create(self, **fields: Any) -> Participant:  # compliance: allow-kwargs test helper forwarding model fields
        return Participant.objects.create(tenant_id=self.tenant.id, added_by_id=self.officer.id, **fields)

    def target(self, table: str) -> uuid.UUID:
        return {
            "tenant_obligation": self.entry.id,
            "change_case": self.case.id,
            "team": self.team.id,
            "membership": self.person.id,
        }[table]


class ParticipantTable(TestCase):
    a: Bank
    b: Bank

    @classmethod
    def setUpTestData(cls) -> None:
        obligation = collab_testing.obligation()
        cls.a = Bank(factories.tenant(slug="participants-a"), obligation.id)
        cls.b = Bank(factories.tenant(slug="participants-b"), obligation.id)

    def test_each_bank_sees_only_its_own_participants(self) -> None:
        for bank in (self.a, self.b):
            tenancy.activate(bank.tenant.id)
            self.assertEqual(set(Participant.objects.values_list("id", flat=True)), {bank.on_entry.id, bank.on_case.id})

    def test_the_database_refuses_every_reference_to_another_banks_row(self) -> None:
        a, b = self.a, self.b
        tenancy.activate(a.tenant.id)
        for column, target, _ in COMPOSITE_KEYS:
            constraint = f"participant_{column}_same_tenant"
            row = a.on_case if column in ("case_id", "team_id") else a.on_entry
            with self.subTest(constraint), self.assertRaisesMessage(IntegrityError, constraint), transaction.atomic():
                Participant.objects.filter(pk=row.pk).update(**{column: b.target(target)})
        outsider = factories.user()
        with self.assertRaisesMessage(IntegrityError, "participant_user_id_same_tenant"), transaction.atomic():
            a.create(tenant_obligation_id=a.entry.id, user_id=outsider.id)

    def test_a_row_names_one_subject_and_one_participant(self) -> None:
        a = self.a
        tenancy.activate(a.tenant.id)
        rows = Participant.objects.filter(pk=a.on_entry.pk)
        for constraint, changes in (
            ("participant_one_subject", {"case_id": a.case.id}),
            ("participant_one_subject", {"tenant_obligation_id": None}),
            ("participant_one_member", {"team_id": a.team.id}),
            ("participant_one_member", {"user_id": None}),
        ):
            with self.subTest(constraint, changes=changes), self.assertRaisesMessage(IntegrityError, constraint), transaction.atomic():
                rows.update(**changes)

    def test_one_live_row_per_subject_and_participant_and_none_is_deleted(self) -> None:
        a = self.a
        tenancy.activate(a.tenant.id)
        for again in ({"tenant_obligation_id": a.entry.id, "user_id": a.person.id}, {"case_id": a.case.id, "team_id": a.team.id}):
            with self.subTest(again), self.assertRaisesMessage(IntegrityError, "participant_live_unique"), transaction.atomic():
                a.create(**again)
        with self.assertRaises(ValidationError) as refused:
            a.on_entry.delete()
        self.assertEqual(refused.exception.code, "remove_not_delete")
        Participant.objects.filter(pk=a.on_entry.pk).update(removed_at=timezone.now(), removed_by_id=a.officer.id)
        a.create(tenant_obligation_id=a.entry.id, user_id=a.person.id)
        self.assertEqual(Participant.objects.filter(tenant_obligation=a.entry, user_id=a.person.id).count(), 2)


class ParticipantLogic(ScenarioTestCase):
    obligation: Any
    tenant: Tenant
    officer: Any
    reader: Any
    team: Any
    url: str

    @classmethod
    def setUpTestData(cls) -> None:
        cls.obligation = collab_testing.obligation()
        cls.tenant = factories.tenant(slug="participant-logic")
        cls.officer = factories.member_user(cls.tenant, roles=("compliance_officer",))
        cls.reader = factories.member_user(cls.tenant)
        cls.team = collab_testing.team(cls.tenant, "legal", "Legal")
        cls.url = f"/api/v1/obligations/{cls.obligation.id}/participants"

    def setUp(self) -> None:
        self.officer_headers = sign_in(self.officer, tenant=self.tenant)
        self.activate(self.tenant)

    def entries(self) -> int:
        self.activate(self.tenant)
        return TenantObligation.objects.filter(obligation_id=self.obligation.id).count()

    def test_a_read_never_creates_an_entry_and_a_refused_add_leaves_none(self) -> None:
        listed = self.client.get(self.url, **self.officer_headers)
        self.assertEqual((listed.status_code, listed.json()), (200, {"items": [], "total": 0}))
        refused = self.client.post(self.url, {"teamKey": "no-such-team"}, content_type="application/json", **self.officer_headers)
        self.assertEqual((refused.status_code, refused.json()["code"]), (422, "unknown_key"))
        both = self.client.post(
            self.url, {"teamKey": "legal", "userId": str(self.reader.id)}, content_type="application/json", **self.officer_headers
        )
        self.assertEqual((both.status_code, both.json()["code"]), (422, "validation_error"))
        self.assertEqual(self.entries(), 0)
        self.activate(self.tenant)
        self.assertFalse(AuditEvent.objects.filter(action__startswith="participant.").exists())

    def test_a_team_is_added_without_a_read_check_and_reads_back_with_its_label(self) -> None:
        added = self.client.post(self.url, {"teamKey": "legal"}, content_type="application/json", **self.officer_headers)
        self.assertEqual(added.status_code, 201, added.content)
        body = added.json()
        self.assertEqual(
            {key: body[key] for key in ("person", "team", "addedBy")},
            {"person": None, "team": {"key": "legal", "kind": None, "label": "Legal"}, "addedBy": {"id": str(self.officer.id), "name": self.officer.name}},
        )
        listed = self.client.get(self.url, **self.officer_headers).json()
        self.assertEqual([item["id"] for item in listed["items"]], [body["id"]])

    def test_an_ended_participation_leaves_the_list_and_may_be_added_again(self) -> None:
        payload = {"userId": str(self.reader.id)}
        first = self.client.post(self.url, payload, content_type="application/json", **self.officer_headers).json()
        removed = self.client.delete(f"{self.url}/{first['id']}", **self.officer_headers)
        self.assertEqual(removed.status_code, 204)
        self.activate(self.tenant)
        self.assertEqual(AuditEvent.objects.filter(action="participant.removed").count(), 1)
        self.assertEqual(self.client.get(self.url, **self.officer_headers).json(), {"items": [], "total": 0})
        again = self.client.delete(f"{self.url}/{first['id']}", **self.officer_headers)
        self.assertEqual(again.status_code, 404)
        second = self.client.post(self.url, payload, content_type="application/json", **self.officer_headers)
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(second.json()["id"], first["id"])

    def test_a_participant_on_another_obligation_is_not_found_here(self) -> None:
        other = collab_testing.obligation()
        added = self.client.post(
            f"/api/v1/obligations/{other.id}/participants", {"userId": str(self.reader.id)}, content_type="application/json", **self.officer_headers
        ).json()
        response = self.client.delete(f"{self.url}/{added['id']}", **self.officer_headers)
        self.assertEqual(response.status_code, 404)


class ParticipantRouteGates(TestCase):
    def test_reading_and_leaving_need_register_read_and_adding_register_edit(self) -> None:
        """Every write under /obligations carries a gate (ID-S21), so removal is gated on
        `register.read`, which every participant held when added; the logic still asks
        `register.edit` for anyone else's row (c8-ten-reassignment, on merging with ID-S21)."""
        routes = {op.operation_id: op for op in iter_operations(api) if "/participants" in op.path and op.path.startswith("/obligations/")}
        gates = {name: perms.gate_of(op.view_func) for name, op in routes.items()}
        self.assertEqual(
            {name: (gate.kind, gate.value) if gate else None for name, gate in gates.items()},
            {
                "listObligationParticipants": ("permission", perms.REGISTER_READ),
                "addObligationParticipant": ("permission", perms.REGISTER_EDIT),
                "removeObligationParticipant": ("permission", perms.REGISTER_READ),
            },
        )
        self.assertNotIn(("DELETE", routes["removeObligationParticipant"].path), perms.UNGATED_BY_DESIGN)
        for name, op in routes.items():
            with self.subTest(operation=name):
                self.assertFalse(perms.step_up_of(op.view_func), "participation approves nothing")


# ---------------------------------------------------------------------------------------
# COL-S6 to COL-S8, run by tests_scenarios.py (one method per scenario there). The bodies
# live here, beside the table they rest on, so the shared scenario module stays a list.
# ---------------------------------------------------------------------------------------
def _post(case: ScenarioTestCase, url: str, payload: dict[str, str], headers: dict[str, Any]) -> Any:
    return case.client.post(url, payload, content_type="application/json", **headers)


def _token(headers: dict[str, Any]) -> str:
    return str(headers["HTTP_AUTHORIZATION"]).removeprefix("Bearer ")


def run_col_s6(case: ScenarioTestCase) -> None:
    tenant = factories.tenant(slug="col-s6")
    anna = factories.member_user(tenant, roles=("compliance_officer",))
    erik = factories.member_user(tenant, roles=("contributor",))
    legal = collab_testing.team(tenant, "legal", "Legal")
    obligation = collab_testing.obligation()
    url = f"/api/v1/obligations/{obligation.id}/participants"
    as_anna = sign_in(anna, tenant=tenant)
    as_erik = sign_in(erik, tenant=tenant)
    erik_before = session_logic.resolve_access_token(_token(as_erik), want=PrincipalKind.USER)
    case.activate(tenant)
    case.assertFalse(TenantObligation.objects.filter(obligation_id=obligation.id).exists())

    person = _post(case, url, {"userId": str(erik.id)}, as_anna)
    team = _post(case, url, {"teamKey": "legal"}, as_anna)
    case.assertEqual((person.status_code, team.status_code), (201, 201), (person.content, team.content))

    case.activate(tenant)
    entry = TenantObligation.objects.get(obligation_id=obligation.id)
    created = AuditEvent.objects.filter(action="register.entry_created", subject_id=entry.id)
    case.assertEqual(created.count(), 1)
    rows = {row.id: row for row in Participant.objects.filter(tenant_obligation=entry)}
    case.assertEqual(set(rows), {uuid.UUID(person.json()["id"]), uuid.UUID(team.json()["id"])})
    case.assertEqual({(row.user_id, row.team_id, row.added_by_id) for row in rows.values()}, {(erik.id, None, anna.id), (None, legal.id, anna.id)})
    added = AuditEvent.objects.filter(action="participant.added", subject_id=entry.id, subject_type="tenant_obligation")
    case.assertEqual(
        sorted((event.after or {}).get("participantId") for event in added), sorted(str(row_id) for row_id in rows)
    )
    for event in added:
        case.assertEqual(set(event.after or {}), {"participantId", "userId", "teamId"}, "ids only, never a name")
        case.assertEqual(event.actor_id, anna.id)
    # Taking part grants nothing: Erik's session holds exactly what it held, and a register
    # write still answers 403 naming the permission his role lacks.
    erik_after = session_logic.resolve_access_token(_token(as_erik), want=PrincipalKind.USER)
    assert erik_before is not None and erik_after is not None
    case.assertEqual(erik_after.permissions, erik_before.permissions)
    case.assertNotIn(perms.REGISTER_EDIT, erik_after.permissions)

    again = _post(case, url, {"userId": str(erik.id)}, as_anna)
    case.assertEqual((again.status_code, again.json()["code"]), (409, "already_participant"))

    refused = _post(case, url, {"userId": str(anna.id)}, as_erik)
    case.assertEqual(refused.status_code, 403)
    case.assertEqual(refused.json()["requiredPermission"], perms.REGISTER_EDIT)
    listed = case.client.get(url, **as_erik).json()
    case.assertEqual(listed["total"], 2)


def run_col_s7(case: ScenarioTestCase) -> None:
    tenant = factories.tenant(slug="col-s7")
    anna = factories.member_user(tenant, roles=("compliance_officer",))
    erik = factories.member_user(tenant, roles=("reader",))
    johan = factories.member_user(tenant, roles=("reader",))
    obligation = collab_testing.obligation()
    url = f"/api/v1/obligations/{obligation.id}/participants"
    as_anna = sign_in(anna, tenant=tenant)
    as_erik = sign_in(erik, tenant=tenant)
    erik_row = _post(case, url, {"userId": str(erik.id)}, as_anna).json()["id"]
    johan_row = _post(case, url, {"userId": str(johan.id)}, as_anna).json()["id"]

    left = case.client.delete(f"{url}/{erik_row}", **as_erik)
    case.assertEqual(left.status_code, 204, left.content)
    case.activate(tenant)
    row = Participant.objects.get(id=erik_row)
    case.assertIsNotNone(row.removed_at)
    case.assertEqual(row.removed_by_id, erik.id)
    # The history still shows that Erik took part until he left: his row stays, and the
    # entry's audit trail holds his add and his leave, in that order.
    history = list(
        AuditEvent.objects.filter(subject_id=row.tenant_obligation_id, action__startswith="participant.")
        .filter(after__participantId=erik_row)
        .order_by("created", "id")
        .values_list("action", flat=True)
    )
    case.assertEqual(history, ["participant.added", "participant.left"])
    case.assertEqual([item["id"] for item in case.client.get(url, **as_erik).json()["items"]], [johan_row])

    refused = case.client.delete(f"{url}/{johan_row}", **as_erik)
    case.assertEqual(refused.status_code, 403)
    case.assertEqual(refused.json()["requiredPermission"], perms.REGISTER_EDIT)
    case.activate(tenant)
    case.assertIsNone(Participant.objects.get(id=johan_row).removed_at)


def run_col_s8(case: ScenarioTestCase) -> None:
    tenant_a = factories.tenant(slug="col-s8-a")
    tenant_b = factories.tenant(slug="col-s8-b")
    owner_a = factories.member_user(tenant_a, roles=("owner",))
    owner_b = factories.member_user(tenant_b, roles=("owner",))
    reader_a = factories.member_user(tenant_a)
    only_in_b = factories.member_user(tenant_b)
    gone = factories.member(tenant_a)
    case.activate(tenant_a)
    Membership.objects.filter(pk=gone.pk).update(deactivated_at=timezone.now())
    blind_role = factories.tenant_role_key(tenant_a)  # cases.read only, no register.read
    blind = factories.member_user(tenant_a, roles=(blind_role.id,))
    their_team = collab_testing.team(tenant_b, "b-only-team", "Their team")
    private = collab_testing.obligation(owner_tenant=tenant_a)
    shared = collab_testing.obligation()
    as_a = sign_in(owner_a, tenant=tenant_a)
    as_b = sign_in(owner_b, tenant=tenant_b)
    private_url = f"/api/v1/obligations/{private.id}/participants"
    shared_url = f"/api/v1/obligations/{shared.id}/participants"
    a_on_shared = _post(case, shared_url, {"userId": str(reader_a.id)}, as_a).json()["id"]
    a_on_private = _post(case, private_url, {"userId": str(reader_a.id)}, as_a)
    case.assertEqual(a_on_private.status_code, 201)

    # Another bank's private obligation is not there for tenant B, to add, read or remove.
    case.assertEqual(_post(case, private_url, {"userId": str(only_in_b.id)}, as_b).status_code, 404)
    case.assertEqual(case.client.get(private_url, **as_b).status_code, 404)
    case.assertEqual(case.client.delete(f"{private_url}/{a_on_private.json()['id']}", **as_b).status_code, 404)

    # On a shared obligation B's add lands on B's own entry, and A's list is unchanged.
    b_added = _post(case, shared_url, {"userId": str(only_in_b.id)}, as_b)
    case.assertEqual(b_added.status_code, 201)
    case.activate(tenant_b)
    b_entry = TenantObligation.objects.get(obligation_id=shared.id)
    case.assertEqual(Participant.objects.get(id=b_added.json()["id"]).tenant_obligation_id, b_entry.id)
    case.assertEqual([item["id"] for item in case.client.get(shared_url, **as_a).json()["items"]], [a_on_shared])
    case.assertEqual([item["id"] for item in case.client.get(shared_url, **as_b).json()["items"]], [b_added.json()["id"]])

    removed = case.client.delete(f"{shared_url}/{a_on_shared}", **as_b)
    case.assertEqual((removed.status_code, removed.json()["code"]), (404, "not_found"))
    case.activate(tenant_a)
    case.assertIsNone(Participant.objects.get(id=a_on_shared).removed_at)

    # A stranger, a deactivated member and an unknown id are one answer.
    answers = [
        _post(case, shared_url, {"userId": str(user_id)}, as_a).json()
        for user_id in (only_in_b.id, gone.user_id, uuid.uuid4())
    ]
    case.assertEqual({(answer["code"], answer["detail"]) for answer in answers}, {("unknown_member", answers[0]["detail"])})
    case.assertEqual(answers[0]["status"], 422)
    team = _post(case, shared_url, {"teamKey": "b-only-team"}, as_a)
    case.assertEqual((team.status_code, team.json()["code"]), (422, "unknown_key"))
    cannot_read = _post(case, shared_url, {"userId": str(blind.id)}, as_a)
    case.assertEqual((cannot_read.status_code, cannot_read.json()["code"]), (422, "participant_cannot_read"))

    # The cap: an entry already holding the configured maximum refuses the next add.
    with override_settings(MAX_PARTICIPANTS_PER_RECORD=2):
        second = _post(case, shared_url, {"userId": str(owner_a.id)}, as_a)
        case.assertEqual(second.status_code, 201)
        over = _post(case, shared_url, {"teamKey": "compliance"}, as_a)
        case.assertEqual((over.status_code, over.json()["code"]), (422, "too_many_participants"))

    # And the database itself refuses a row naming another bank's person, team or entry.
    case.activate(tenant_a)
    a_entry = TenantObligation.objects.get(obligation_id=shared.id)
    for fields, constraint in (
        ({"tenant_obligation_id": a_entry.id, "user_id": only_in_b.id}, "participant_user_id_same_tenant"),
        ({"tenant_obligation_id": a_entry.id, "team_id": their_team.id}, "participant_team_id_same_tenant"),
        ({"tenant_obligation_id": b_entry.id, "user_id": owner_a.id}, "participant_tenant_obligation_id_same_tenant"),
    ):
        with case.subTest(constraint), case.assertRaisesMessage(IntegrityError, constraint), transaction.atomic():
            Participant.objects.create(tenant_id=tenant_a.id, added_by_id=owner_a.id, **fields)
