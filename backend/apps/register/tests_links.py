"""Linked internal items outside the scenario (REG-05; REG-S8 is in tests_scenarios.py).

A link picks one of the bank's internal items or creates it from the same call, each with its
own audit event; a removal stamps `removed_at` and leaves the link row and the item; another
bank's item or link is 404; a kind off the bank's list is 422 `unknown_key`; a second live
link of the same item is 409 `already_linked`; the read costs a fixed number of queries.

Operations exercised: listInternalLinks, addInternalLink, removeInternalLink.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from django.db import transaction

from apps.identity.models import User
from apps.library import testing as library_testing
from apps.library.models import Obligation
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.register import links
from apps.register.logic import ENTRY_CREATED
from apps.register.models import InternalLink
from apps.shared import factories
from apps.shared.models import AuditEvent, Tenant
from apps.shared.testing import ScenarioTestCase, sign_in
from apps.taxonomy.models import LinkKind
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms
from apps.tenants.models import InternalItem

V1 = "/api/v1"
POLICY = {"kind": "policy", "label": "Client asset policy", "externalRef": "POL-014", "url": "https://intranet.example-bank.test/pol-014"}
# The queries of one read however many links: the obligation and its titles, the page, the
# kinds' labels and the total.
LIST_QUERIES = 5


def seed_library() -> None:
    with transaction.atomic():
        seed_languages()
        seed_jurisdictions()
        seed_library_vocabularies()
        seed_taxonomy_terms()


def an_obligation(key: str) -> Obligation:
    act = library_testing.instrument(key=f"{key}-act", short_name="LVM", regime="regime:securities")
    return library_testing.obligation(act, key=key, ref_label="8 kap. 1 §")


@dataclass(frozen=True)
class World:
    """Two banks, each with a compliance officer and a reader, over one library obligation."""

    obligation: Obligation
    bank: Tenant
    officer: User
    reader: User
    other_bank: Tenant
    other_officer: User


def build_world() -> World:
    seed_library()
    bank = factories.tenant(slug="bank-a")
    other_bank = factories.tenant(slug="bank-b")
    return World(
        obligation=an_obligation("register-links-duty"),
        bank=bank,
        officer=factories.member_user(bank, roles=("compliance_officer",)),
        reader=factories.member_user(bank, roles=("reader",)),
        other_bank=other_bank,
        other_officer=factories.member_user(other_bank, roles=("compliance_officer",)),
    )


class RegisterWorld(ScenarioTestCase):
    """The world of `build_world()` and the requests these tests make in it."""

    w: ClassVar[World]

    @classmethod
    def setUpTestData(cls) -> None:
        cls.w = build_world()

    def url(self, suffix: str) -> str:
        return f"{V1}/obligations/{self.w.obligation.id}/{suffix}"

    def post(self, user: Any, tenant: Tenant, body: dict[str, Any]) -> Any:
        return self.client.post(self.url("internal-links"), data=body, content_type="application/json", **sign_in(user, tenant=tenant))

    def register_events(self) -> int:
        return AuditEvent.objects.filter(action__startswith="register.").count()

    def events(self, tenant: Tenant, action: str) -> list[AuditEvent]:
        self.activate(tenant)
        return list(AuditEvent.objects.filter(action=action).order_by("created", "id"))


class InternalLinks(RegisterWorld):
    def test_creating_an_item_from_the_call_writes_one_item_one_link_and_one_audit_event_each(self) -> None:
        response = self.post(self.w.officer, self.w.bank, {**POLICY, "reference": "POL-014", "externalSystem": "ServiceNow GRC"})
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.activate(self.w.bank)
        [item] = InternalItem.objects.all()
        [link] = InternalLink.objects.all()
        self.assertEqual((body["id"], body["internalItemId"]), (str(link.id), str(item.id)))
        self.assertEqual(body["kind"], {"key": "policy", "kind": None, "label": "Policy"})
        self.assertEqual((body["label"], body["externalRef"], body["externalSystem"]), ("Client asset policy", "POL-014", "ServiceNow GRC"))
        self.assertEqual((item.name, item.reference, item.kind.key, item.url), ("Client asset policy", "POL-014", "policy", POLICY["url"]))
        [item_event] = self.events(self.w.bank, links.ITEM_CREATED)
        [link_event] = self.events(self.w.bank, links.LINK_ADDED)
        self.assertEqual((item_event.subject_id, item_event.actor_id), (item.id, self.w.officer.id))
        self.assertEqual(item_event.after["kind"], "policy")
        self.assertEqual((link_event.subject_id, link_event.actor_id), (link.id, self.w.officer.id))
        self.assertEqual(link_event.after, {"obligationId": str(self.w.obligation.id), "internalItemId": str(item.id), "kind": "policy"})
        self.assertEqual(len(self.events(self.w.bank, ENTRY_CREATED)), 1)

    def test_picking_an_item_writes_one_link_and_one_audit_event_and_no_item(self) -> None:
        self.activate(self.w.bank)
        item = InternalItem.objects.create(
            tenant=self.w.bank, kind=LinkKind.objects.get(key="control"), name="Daily reconciliation", external_ref="CTL-7"
        )
        response = self.post(self.w.officer, self.w.bank, {"kind": "control", "label": "Daily reconciliation", "internalItemId": str(item.id)})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual((response.json()["internalItemId"], response.json()["externalRef"]), (str(item.id), "CTL-7"))
        self.activate(self.w.bank)
        self.assertEqual(InternalItem.objects.count(), 1)
        self.assertEqual(InternalLink.objects.get().internal_item_id, item.id)
        self.assertEqual(self.events(self.w.bank, links.ITEM_CREATED), [])
        self.assertEqual(len(self.events(self.w.bank, links.LINK_ADDED)), 1)

    def test_a_second_live_link_of_the_same_item_is_409_already_linked_and_stores_nothing(self) -> None:
        item_id = self.post(self.w.officer, self.w.bank, POLICY).json()["internalItemId"]
        response = self.post(self.w.officer, self.w.bank, {"kind": "policy", "label": "Again", "internalItemId": item_id})
        self.assertEqual((response.status_code, response.json()["code"]), (409, "already_linked"))
        self.activate(self.w.bank)
        self.assertEqual(InternalLink.objects.count(), 1)
        self.assertEqual(len(self.events(self.w.bank, links.LINK_ADDED)), 1)

    def test_a_kind_off_the_banks_list_is_422_unknown_key_and_stores_nothing(self) -> None:
        self.activate(self.w.bank)
        LinkKind.objects.filter(key="procedure").update(active=False)
        for kind in ("no_such_kind", "procedure"):
            response = self.post(self.w.officer, self.w.bank, {**POLICY, "kind": kind})
            self.assertEqual((response.status_code, response.json()["code"]), (422, "unknown_key"), kind)
        self.activate(self.w.bank)
        self.assertEqual((InternalItem.objects.count(), InternalLink.objects.count(), self.register_events()), (0, 0, 0))

    def test_another_banks_item_is_404_and_nothing_is_stored(self) -> None:
        self.activate(self.w.other_bank)
        theirs = InternalItem.objects.create(tenant=self.w.other_bank, kind=LinkKind.objects.get(key="policy"), name="Their policy")
        response = self.post(self.w.officer, self.w.bank, {"kind": "policy", "label": "Their policy", "internalItemId": str(theirs.id)})
        self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))
        self.activate(self.w.bank)
        self.assertEqual((InternalLink.objects.count(), self.register_events()), (0, 0))

    def test_each_refused_body_stores_no_item(self) -> None:
        item_id = self.post(self.w.officer, self.w.bank, POLICY).json()["internalItemId"]
        self.post(self.w.officer, self.w.bank, POLICY)  # the second create of the same name
        for body, code in (
            ({"kind": "policy", "label": "x", "internalItemId": item_id, "reference": "POL-1"}, "validation_error"),
            ({"kind": "control", "label": "x", "internalItemId": item_id}, "validation_error"),
            (POLICY, "duplicate_key"),
            ({**POLICY, "label": "Owned twice", "ownerId": str(self.w.officer.id), "ownerTeamId": str(self.w.officer.id)}, "validation_error"),
            ({**POLICY, "label": "Owned by a stranger", "ownerId": str(self.w.other_officer.id)}, "validation_error"),
            ({**POLICY, "label": "Scripted", "url": "javascript:alert(1)"}, "validation_error"),
        ):
            response = self.post(self.w.officer, self.w.bank, body)
            self.assertIn(response.status_code, (409, 422), body)
            self.assertEqual(response.json()["code"], code, body)
        self.activate(self.w.bank)
        self.assertEqual(InternalItem.objects.count(), 1)

    def test_removing_a_link_stamps_it_and_leaves_the_link_row_and_the_item(self) -> None:
        link_id = self.post(self.w.officer, self.w.bank, POLICY).json()["id"]
        headers = sign_in(self.w.officer, tenant=self.w.bank)
        response = self.client.delete(f"{V1}/internal-links/{link_id}", **headers)
        self.assertEqual(response.status_code, 204, response.content)
        self.activate(self.w.bank)
        link = InternalLink.objects.get(pk=link_id)
        self.assertIsNotNone(link.removed_at)
        self.assertEqual(link.removed_by_id, self.w.officer.id)
        self.assertTrue(link.internal_item is not None and link.internal_item.active)
        [event] = self.events(self.w.bank, links.LINK_REMOVED)
        self.assertEqual((event.subject_id, event.before), (link.id, {"removedAt": None}))
        self.assertEqual(self.client.get(self.url("internal-links"), **headers).json(), {"items": [], "total": 0})
        again = self.client.delete(f"{V1}/internal-links/{link_id}", **headers)
        self.assertEqual((again.status_code, again.json()["code"]), (404, "not_found"))
        relinked = self.post(self.w.officer, self.w.bank, {"kind": "policy", "label": "Back", "internalItemId": str(link.internal_item_id)})
        self.assertEqual(relinked.status_code, 201, relinked.content)

    def test_another_bank_gets_404_for_the_link_and_sees_none_of_it(self) -> None:
        body = self.post(self.w.officer, self.w.bank, POLICY).json()
        headers = sign_in(self.w.other_officer, tenant=self.w.other_bank)
        response = self.client.delete(f"{V1}/internal-links/{body['id']}", **headers)
        self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))
        self.assertEqual(self.client.get(self.url("internal-links"), **headers).json(), {"items": [], "total": 0})
        picked = self.post(self.w.other_officer, self.w.other_bank, {"kind": "policy", "label": "x", "internalItemId": body["internalItemId"]})
        self.assertEqual((picked.status_code, picked.json()["code"]), (404, "not_found"))
        self.activate(self.w.bank)
        self.assertIsNone(InternalLink.objects.get(pk=body["id"]).removed_at)

    def test_a_reader_reads_the_links_and_cannot_write_them(self) -> None:
        self.post(self.w.officer, self.w.bank, POLICY)
        headers = sign_in(self.w.reader, tenant=self.w.bank)
        self.assertEqual(self.client.get(self.url("internal-links"), **headers).json()["total"], 1)
        response = self.client.post(self.url("internal-links"), data=POLICY, content_type="application/json", **headers)
        self.assertEqual((response.status_code, response.json()["requiredPermission"]), (403, "register.edit"))

    def test_an_obligation_the_bank_cannot_see_is_404(self) -> None:
        private = library_testing.obligation(
            library_testing.instrument(key="private-act", regime="regime:securities", owner_tenant=self.w.other_bank),
            key="private-duty",
            owner_tenant=self.w.other_bank,
        )
        headers = sign_in(self.w.officer, tenant=self.w.bank)
        for response in (
            self.client.get(f"{V1}/obligations/{private.id}/internal-links", **headers),
            self.client.post(f"{V1}/obligations/{private.id}/internal-links", data=POLICY, content_type="application/json", **headers),
        ):
            self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))

    def test_the_read_costs_the_same_queries_for_one_link_or_many_and_pages(self) -> None:
        self.post(self.w.officer, self.w.bank, POLICY)
        self.activate(self.w.bank)
        with self.assertNumQueries(LIST_QUERIES):
            links.list_links(tenant=self.w.bank, order=["en"], obligation_id=self.w.obligation.id, limit=20, offset=0)
        for n in range(4):
            self.post(self.w.officer, self.w.bank, {**POLICY, "kind": "control", "label": f"Control {n}"})
        self.activate(self.w.bank)
        with self.assertNumQueries(LIST_QUERIES):
            page = links.list_links(tenant=self.w.bank, order=["en"], obligation_id=self.w.obligation.id, limit=2, offset=1)
        self.assertEqual((page.total, [row.label for row in page.items]), (5, ["Control 0", "Control 1"]))
