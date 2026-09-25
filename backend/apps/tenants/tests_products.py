"""The bank's products outside the scenarios (TEN-02; c8-ten-organisation): status, launch
date, owner, offering unit and scope terms from the dimensions obligations are scoped with,
read from the dimension rows rather than listed. Writes need `vocab.manage`, check
`If-Match`, answer 422 `unknown_key` or `unknown_member`, and are audited with the fields
they changed before and after, the description named and never copied. A product is retired,
never deleted, and decides no applicability.

Operations exercised: listProducts, createProduct, updateProduct.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.core.exceptions import ValidationError

from apps.library.reading import today_for
from apps.shared import factories
from apps.shared import permissions as perms
from apps.shared.tenancy import library_write
from apps.taxonomy.models import TaxonomyTerm, TermDimension, TermDimensionKind
from apps.taxonomy.registry import REGISTRY
from apps.taxonomy.terms_logic import mirrored_dimensions
from apps.tenants.models import TenantProduct
from apps.tenants.tests_org_units import V1, OrganisationCase

PRODUCTS = f"{V1}/tenant/products"


class ProductWrites(OrganisationCase):
    def create(self, **fields: Any) -> dict[str, Any]:
        response = self.post(PRODUCTS, {"name": "Custody", **fields})
        self.assertEqual(response.status_code, 201, response.content)
        return dict(response.json())

    def test_a_product_carries_its_facts_and_scope_terms_of_the_scope_dimensions(self) -> None:
        owner = factories.member_user(self.tenant)
        unit = self.entity()
        launch = today_for(self.tenant) + timedelta(days=60)
        product = self.create(
            status="planned", launchDate=launch.isoformat(), orgUnitId=unit["id"], ownerUserId=str(owner.id), terms=["custody", "retail"], description="Safekeeping."
        )
        self.assertEqual(
            {key: product[key] for key in ("name", "status", "launchDate", "orgUnitId", "description", "version")},
            {"name": "Custody", "status": "planned", "launchDate": launch.isoformat(), "orgUnitId": unit["id"], "description": "Safekeeping.", "version": 1},
        )
        self.assertEqual(product["owner"], {"id": str(owner.id), "name": owner.name})
        self.assertEqual(sorted(term["key"] for term in product["terms"]), ["custody", "retail"])
        # Every term is of a dimension an obligation's scope is written with, read from the
        # dimension rows through the registry rather than from a list of keys.
        dimensions = REGISTRY["term_dimension"].model.objects.filter(terms__key__in=["custody", "retail"])
        self.assertTrue(dimensions.exists())
        self.assertLessEqual(set(dimensions.values_list("kind", flat=True)), {TermDimensionKind.SCOPE.value, TermDimensionKind.OPT_IN.value})
        [event] = self.events("product.created")
        self.assertEqual(event.after["terms"], ["custody", "retail"])
        self.assertEqual((event.after["status"], event.after["ownerUserId"], event.after["rewritten"]), ("planned", str(owner.id), ["description"]))
        self.assertNotIn("Safekeeping.", str(event.after))

    def test_a_classification_or_mirrored_term_is_unknown_key(self) -> None:
        with library_write("test builder"):
            theme, _ = TermDimension.objects.get_or_create(key="theme", defaults={"kind": TermDimensionKind.CLASSIFICATION.value, "restricts_footprint": False})
            TaxonomyTerm.objects.get_or_create(dimension=theme, key="sustainability")
        mirrored = TaxonomyTerm.objects.filter(dimension_id__in=mirrored_dimensions(TermDimension.objects.values_list("id", flat=True))).first()  # ordering: any one mirrored term
        assert mirrored is not None
        for key in ("sustainability", mirrored.key, "no_such_term"):
            with self.subTest(key=key):
                self.problem(self.post(PRODUCTS, {"name": "Custody", "terms": [key]}), 422, "unknown_key")
        self.assertEqual(self.events("product.created"), [])

    def test_a_name_the_bank_already_uses_is_refused(self) -> None:
        self.create()
        self.problem(self.post(PRODUCTS, {"name": "Custody"}), 422, "validation_error")

    def test_an_owner_or_unit_outside_the_bank_is_refused(self) -> None:
        self.problem(self.post(PRODUCTS, {"name": "Custody", "ownerUserId": str(factories.member_user(self.other).id)}), 422, "unknown_member")
        self.problem(self.post(PRODUCTS, {"name": "Custody", "orgUnitId": str(factories.org_unit(self.other).id)}), 404, "not_found")

    def test_a_product_is_retired_rescoped_and_never_deleted(self) -> None:
        product = self.create(terms=["custody"])
        url = f"{PRODUCTS}/{product['id']}"
        response = self.patch(url, {"status": "retired", "terms": ["custody", "professional"]}, version=1)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()["status"], response.json()["version"]), ("retired", 2))
        self.assertEqual(sorted(term["key"] for term in response.json()["terms"]), ["custody", "professional"])
        self.problem(self.patch(url, {"name": "Late"}, version=1), 409, "stale_write")
        listed = self.client.get(PRODUCTS, **self.headers).json()
        self.assertEqual([(row["id"], row["status"]) for row in listed["items"]], [(product["id"], "retired")])
        [event] = self.events("product.updated")
        self.assertEqual(event.before, {"status": "live", "terms": ["custody"]})
        self.assertEqual(event.after, {"status": "retired", "terms": ["custody", "professional"], "rewritten": []})
        self.activate(self.tenant)
        with self.assertRaises(ValidationError):
            TenantProduct.objects.get(pk=product["id"]).delete()

    def test_writes_need_vocab_manage_and_another_bank_sees_nothing(self) -> None:
        product = self.create()
        reader = self.reader()
        denied = self.post(PRODUCTS, {"name": "Lending"}, headers=reader)
        self.assertEqual((denied.status_code, denied.json()["requiredPermission"]), (403, perms.VOCAB_MANAGE))
        self.assertEqual([row["id"] for row in self.client.get(PRODUCTS, **reader).json()["items"]], [product["id"]])
        other_admin = self.other_admin()
        self.assertEqual(self.client.get(PRODUCTS, **other_admin).json(), {"items": [], "total": 0})
        self.problem(self.patch(f"{PRODUCTS}/{product['id']}", {"status": "retired"}, headers=other_admin), 404, "not_found")
