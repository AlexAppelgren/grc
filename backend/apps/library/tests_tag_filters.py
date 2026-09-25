"""The obligation row's R2 fields (VOC-08, INV-03, INV-07, FP-03, D-75) and the bounded
string filters (hardening H27): the bank's own tags on a row and a card, read in one query
for the page; the `tag` and `tenantTag` filters with their refusals; `privateToUs` on
obligations and instruments; and a length limit on every string filter of
`GET /obligations` and `GET /instruments`. Another bank's tags are proven unreadable as the
app role under forced row-level security.

Proven to fail 2026-09-25 in a scratch copy: with the unknown-key check removed from the
two tag filters, four tests failed. The tenant-tag read also filters by the bank's id; with
that filter dropped the suite stays green, because row-level security alone keeps another
bank's taggings out, which is what `TenantTagIsolation` proves as the app role. The filter
is defence in depth, not the proof.
"""

from __future__ import annotations

from typing import Any

from django.db import DEFAULT_DB_ALIAS, transaction
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext

from apps.agents import testing as agents_testing
from apps.identity.models import User
from apps.library import testing as build
from apps.library.models import Obligation
from apps.library.tests_reading import FOOTPRINT, URL, as_app_role, keys, seed_obligations, seed_reference, set_footprint
from apps.shared import factories, tenancy
from apps.shared import permissions as perms
from apps.shared.models import Tenant
from apps.shared.testing import sign_in
from apps.taxonomy.models import Tagging, TenantTag, TenantTagLabel

INSTRUMENTS = "/api/v1/instruments"


def tenant_tag(tenant: Tenant, key: str, labels: dict[str, str]) -> TenantTag:
    tenancy.activate(tenant.id)
    row = TenantTag.objects.create(tenant=tenant, key=key)
    for index, (language, text) in enumerate(labels.items()):
        TenantTagLabel.objects.create(tenant=tenant, vocabulary=row, language=language, text=text, is_original=index == 0)
    return row


def tag_with(tenant: Tenant, tag: TenantTag, *obligations: Obligation) -> None:
    tenancy.activate(tenant.id)
    for obligation in obligations:
        Tagging.objects.create(tenant=tenant, tag=tag, subject_type="obligation", subject_id=obligation.id)


class TenantTagsAndFilters(TestCase):
    tenant: Tenant
    other: Tenant
    reader: User

    @classmethod
    def setUpTestData(cls) -> None:
        seed_reference()
        cls.tenant = factories.tenant(slug="tags-a")
        cls.other = factories.tenant(slug="tags-b")
        set_footprint(cls.tenant, FOOTPRINT)
        cls.reader = factories.member_user(cls.tenant, roles=("reader",))
        seed_obligations()
        by_key = {obligation.stable_key: obligation for obligation in Obligation.objects.all()}
        custody = tenant_tag(cls.tenant, "custody", {"en": "Custody", "sv": "Förvaring"})
        kyc = tenant_tag(cls.tenant, "kyc", {"sv": "Kundkännedom"})
        tag_with(cls.tenant, custody, by_key["obl-a-appropriateness"], by_key["obl-d-research"])
        tag_with(cls.tenant, kyc, by_key["obl-a-appropriateness"])
        # Another bank tags the same shared record with a key of its own and one A also has.
        tag_with(cls.other, tenant_tag(cls.other, "b-only", {"en": "Bank B only"}), by_key["obl-a-appropriateness"])
        tag_with(cls.other, tenant_tag(cls.other, "custody", {"en": "B's custody"}), by_key["obl-e-guidance"])
        tenancy.activate(cls.tenant.id)

    def get(self, params: dict[str, Any], url: str = URL) -> Any:
        return self.client.get(url, params, **sign_in(self.reader, tenant=self.tenant))

    def rows(self, params: dict[str, Any]) -> dict[str, dict[str, Any]]:
        response = self.get({"footprint": "all", **params})
        self.assertEqual(response.status_code, 200, response.content)
        return {row["stableKey"]: row for row in response.json()["items"]}

    def test_a_row_and_a_card_carry_the_banks_own_tags_and_no_other_banks(self) -> None:
        rows = self.rows({})
        self.assertEqual(
            rows["obl-a-appropriateness"]["tenantTags"],
            [{"key": "custody", "kind": None, "label": "Custody"}, {"key": "kyc", "kind": None, "label": "Kundkännedom"}],
            "the reader's language, then the original",
        )
        self.assertEqual([tag["key"] for tag in rows["obl-d-research"]["tenantTags"]], ["custody"])
        self.assertEqual(rows["obl-e-guidance"]["tenantTags"], [], "B's tag on a shared record stays B's")
        self.assertEqual(rows["obl-a-appropriateness"]["tags"][0]["key"], "appropriateness", "the library's own tags are kept apart")
        card = self.get({}, f"{URL}/{Obligation.objects.get(stable_key='obl-a-appropriateness').id}").json()
        self.assertEqual([tag["key"] for tag in card["tenantTags"]], ["custody", "kyc"])

    def test_the_tenant_tags_are_one_query_whatever_the_page(self) -> None:
        # Twenty tagged rows cost the same one tagging query as a single row does.
        tag = TenantTag.objects.get(tenant=self.tenant, key="custody")
        tag_with(self.tenant, tag, *build.library_of(20))
        counts = []
        for limit in (1, 20):
            with self.subTest(limit=limit), CaptureQueriesContext(transaction.get_connection()) as captured:
                response = self.get({"footprint": "all", "limit": limit, "q": "Duty"})
            self.assertEqual(len(response.json()["items"]), limit)
            self.assertTrue(all(row["tenantTags"] for row in response.json()["items"]))
            self.assertEqual(sum('"tagging"' in query["sql"] for query in captured.captured_queries), 1)
            counts.append(len(captured.captured_queries))
        self.assertEqual(counts[0], counts[1])

    def test_the_library_tag_filter(self) -> None:
        self.assertEqual(keys(self.get({"tag": "appropriateness"})), ["obl-a-appropriateness"])
        self.assertEqual(keys(self.get({"tag": "advice", "footprint": "all"})), ["obl-b-advice"])
        self.assertEqual(keys(self.get({"tag": ["appropriateness", "advice"], "footprint": "all"})), [], "every tag must match")
        unknown = self.get({"tag": ["advice", "astrology", "zodiac"]})
        self.assertEqual((unknown.status_code, unknown.json()["code"]), (422, "unknown_key"))
        for key in ("astrology", "zodiac"):
            self.assertIn(key, unknown.json()["detail"])
        self.assertNotIn("advice", unknown.json()["detail"].split(":", 1)[1])

    def test_the_tenant_tag_filter(self) -> None:
        self.assertEqual(keys(self.get({"tenantTag": "custody"})), ["obl-a-appropriateness", "obl-d-research"])
        self.assertEqual(keys(self.get({"tenantTag": ["custody", "kyc"]})), ["obl-a-appropriateness"], "every tag must match")
        # B's `custody` sits on obl-e; A's filter by the same key reads A's tag alone.
        self.assertNotIn("obl-e-guidance", keys(self.get({"tenantTag": "custody", "footprint": "all"})))
        for missing in (["nope"], ["custody", "b-only"]):
            with self.subTest(missing=missing):
                refused = self.get({"tenantTag": missing})
                self.assertEqual((refused.status_code, refused.json()["code"]), (422, "unknown_key"))
                self.assertIn(missing[-1], refused.json()["detail"])

    def test_a_key_with_no_tenant_is_refused_the_banks_filter(self) -> None:
        with tenancy.platform_zone():
            key = agents_testing.agent_key(scopes=(perms.SCOPE_LIBRARY_READ,))
        refused = self.client.get(URL, {"tenantTag": "custody"}, HTTP_X_API_KEY=key.plain_key)
        self.assertEqual((refused.status_code, refused.json()["code"]), (422, "unknown_filter"))
        # Without it the key still belongs to no bank, so it reads no row and no tag at all.
        for url in (URL, f"{URL}/{Obligation.objects.get(stable_key='obl-a-appropriateness').id}", INSTRUMENTS):
            with self.subTest(url=url):
                response = self.client.get(url, HTTP_X_API_KEY=key.plain_key)
                self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))
                self.assertNotIn("tenantTags", response.json())

    def test_a_shared_record_is_never_private_to_us(self) -> None:
        self.assertEqual({row["privateToUs"] for row in self.rows({}).values()}, {False})
        obligation = Obligation.objects.get(stable_key="obl-a-appropriateness")
        self.assertIs(self.get({}, f"{URL}/{obligation.id}").json()["privateToUs"], False)
        instruments = self.get({"footprint": "all"}, INSTRUMENTS).json()["items"]
        self.assertEqual({row["privateToUs"] for row in instruments}, {False})
        self.assertIs(self.get({}, f"{INSTRUMENTS}/{obligation.instrument_id}").json()["privateToUs"], False)

    def test_every_string_filter_is_bounded(self) -> None:
        long = "x" * 81
        for url, params in (
            (URL, {"instrument": long}),
            (URL, {"dutyType": long}),
            (URL, {"term": ["regime:securities", f"regime:{long[:74]}"]}),
            (URL, {"tag": long}),
            (URL, {"tenantTag": long}),
            (INSTRUMENTS, {"regime": long}),
        ):
            with self.subTest(url=url, params=params):
                refused = self.get(params, url)
                self.assertEqual((refused.status_code, refused.json()["code"]), (422, "validation_error"))
        # Eighty characters is still a key, answered as one: nothing matches it.
        self.assertEqual(keys(self.get({"instrument": long[:80]})), [])
        self.assertEqual(self.get({"regime": long[:80]}, INSTRUMENTS).json()["items"], [])


class TenantTagIsolation(TransactionTestCase):
    """VOC-08, INV-07 as the app role under forced row-level security: tenant A's tags never
    reach tenant B, not on a row, a card or through the filter, and a bank's own private
    record reads `privateToUs` true for it alone."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        with transaction.atomic():
            seed_reference()
        self.tenant_a = factories.tenant(slug="tags-iso-a")
        self.tenant_b = factories.tenant(slug="tags-iso-b")
        set_footprint(self.tenant_a, FOOTPRINT)
        set_footprint(self.tenant_b, FOOTPRINT)
        with transaction.atomic():
            seed_obligations()
        self.shared = Obligation.objects.get(stable_key="obl-a-appropriateness")
        with transaction.atomic():
            tag_with(self.tenant_a, tenant_tag(self.tenant_a, "a-secret", {"en": "A's secret"}), self.shared)
        with transaction.atomic():
            tenancy.activate(self.tenant_b.id)
            self.private_instrument = build.instrument(key="bank-b-own", regime="regime:securities", owner_tenant=self.tenant_b)
            self.private = build.obligation(
                self.private_instrument, key="obl-b-own", terms=("service_type:non_advised",), owner_tenant=self.tenant_b
            )
        self.key_a = factories.api_key(self.tenant_a, scopes=(perms.SCOPE_LIBRARY_READ,))
        self.key_b = factories.api_key(self.tenant_b, scopes=(perms.SCOPE_LIBRARY_READ,))

    def read(self, key: Any, url: str, params: dict[str, Any] | None = None) -> Any:
        return self.client.get(url, params or {}, HTTP_X_API_KEY=key.plain_key)

    def test_one_banks_tags_never_reach_another(self) -> None:
        with as_app_role():
            rows = {row["stableKey"]: row for row in self.read(self.key_b, URL, {"footprint": "all"}).json()["items"]}
            self.assertEqual(rows["obl-a-appropriateness"]["tenantTags"], [])
            self.assertEqual(self.read(self.key_b, f"{URL}/{self.shared.id}").json()["tenantTags"], [])
            refused = self.read(self.key_b, URL, {"tenantTag": "a-secret"})
            self.assertEqual((refused.status_code, refused.json()["code"]), (422, "unknown_key"))
            # The owner reads it, so the proof above is not vacuous.
            own = {row["stableKey"]: row for row in self.read(self.key_a, URL, {"tenantTag": "a-secret"}).json()["items"]}
            self.assertEqual([tag["key"] for tag in own["obl-a-appropriateness"]["tenantTags"]], ["a-secret"])

    def test_a_banks_own_record_is_private_to_it_alone(self) -> None:
        with as_app_role():
            rows = {row["stableKey"]: row for row in self.read(self.key_b, URL, {"footprint": "all"}).json()["items"]}
            self.assertIs(rows["obl-b-own"]["privateToUs"], True)
            self.assertIs(rows["obl-a-appropriateness"]["privateToUs"], False)
            self.assertIs(self.read(self.key_b, f"{URL}/{self.private.id}").json()["privateToUs"], True)
            instruments = {row["stableKey"]: row for row in self.read(self.key_b, INSTRUMENTS, {"footprint": "all"}).json()["items"]}
            self.assertIs(instruments["bank-b-own"]["privateToUs"], True)
            self.assertIs(self.read(self.key_b, f"{INSTRUMENTS}/{self.private_instrument.id}").json()["privateToUs"], True)
            seen_by_a = self.read(self.key_a, URL, {"footprint": "all"}).json()["items"]
            self.assertNotIn("obl-b-own", [row["stableKey"] for row in seen_by_a])
