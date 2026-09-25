"""The bank's products, described in the terms obligations are scoped with (TEN-02). A
product is retired, never deleted, and a retired product scopes nothing. Written under
`vocab.manage` and audited with the fields it changed before and after; the description a
person typed never enters the audit row, which names it in `rewritten` instead. A product
decides no applicability in R2: nothing here reads or writes the register.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from django.core.exceptions import ValidationError
from django.db.models import Prefetch

from apps.shared.audit import Actor, record
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.tenants.models import TenantProduct, TenantProductTerm
from apps.tenants.organisation import active_member, changed, iso, locked, org_unit_of, person, ref
from apps.tenants.terms import Term, scope_terms, term_refs
from apps.tenants.schemas import ProductStatusValue, TenantProductBody, TenantProductOut, TenantProductPage, TenantProductPatch


def product_of(tenant: Tenant, product_id: uuid.UUID) -> TenantProduct:
    """The product, in the caller's bank and under its row-level security, or 404."""
    product = TenantProduct.objects.filter(tenant=tenant, pk=product_id).first()  # ordering: pk lookup, at most one row
    if product is None:
        raise ProblemError(status=404, code="not_found", detail="Not found.")
    return product


def _snapshot(product: TenantProduct, terms: list[Term]) -> dict[str, Any]:
    return {
        "name": product.name,
        "status": product.status,
        "launchDate": iso(product.launch_date),
        "orgUnitId": ref(product.org_unit_id),
        "ownerUserId": ref(product.owner_user_id),
        "terms": [term.key for term in terms],
    }


def _terms_of(product: TenantProduct) -> list[Term]:
    return [row.term for row in TenantProductTerm.objects.filter(product=product).select_related("term").order_by("term__key")]


def _products(tenant: Tenant) -> Any:
    terms = TenantProductTerm.objects.select_related("term").order_by("term__sort_order", "term__key")
    return TenantProduct.objects.filter(tenant=tenant).select_related("owner_user").prefetch_related(Prefetch("terms", queryset=terms))


def _products_out(products: list[TenantProduct], order: list[str]) -> list[TenantProductOut]:
    refs = term_refs(list({row.term_id: row.term for product in products for row in product.terms.all()}.values()), order)
    return [
        TenantProductOut(
            id=product.id,
            name=product.name,
            description=product.description,
            status=cast(ProductStatusValue, product.status),
            launch_date=product.launch_date,
            org_unit_id=product.org_unit_id,
            owner=person(product.owner_user),
            terms=[refs[row.term_id] for row in product.terms.all()],
            version=product.version,
        )
        for product in products
    ]


def _product_out(tenant: Tenant, product_id: uuid.UUID, order: list[str]) -> TenantProductOut:
    return _products_out([_products(tenant).get(pk=product_id)], order)[0]


def _apply(tenant: Tenant, product: TenantProduct, fields: dict[str, Any]) -> list[str]:
    """Set the fields a create or change sends; `description` when it changed."""
    name = fields.get("name")
    if name is not None and name != product.name:
        if TenantProduct.objects.filter(tenant=tenant, name=name).exists():
            raise ValidationError("Your organisation already has a product with that name.", code="validation_error")
        product.name = name
    for field in ("status", "launch_date"):
        if fields.get(field) is not None:
            setattr(product, field, fields[field])
    if fields.get("org_unit_id") is not None:
        product.org_unit = org_unit_of(tenant, fields["org_unit_id"])
    if fields.get("owner_user_id") is not None:
        product.owner_user = active_member(tenant, fields["owner_user_id"])
    if fields.get("description") is not None and fields["description"] != product.description:
        product.description = fields["description"]
        return ["description"]
    return []


def _set_terms(tenant: Tenant, product: TenantProduct, terms: list[Term]) -> None:
    TenantProductTerm.objects.filter(tenant=tenant, product=product).exclude(term__in=terms).delete()
    held = set(TenantProductTerm.objects.filter(tenant=tenant, product=product).values_list("term_id", flat=True))
    TenantProductTerm.objects.bulk_create(
        [TenantProductTerm(tenant=tenant, product=product, term=term) for term in terms if term.id not in held]
    )


def list_products(*, tenant: Tenant, order: list[str], limit: int, offset: int) -> TenantProductPage:
    """`GET /tenant/products`: planned, live and retired, by name."""
    queryset = _products(tenant)
    products = list(queryset.order_by("name", "id")[offset : offset + limit])
    return TenantProductPage(items=_products_out(products, order), total=queryset.count())


def create_product(*, tenant: Tenant, actor: Actor, order: list[str], body: TenantProductBody) -> TenantProductOut:
    """`POST /tenant/products`."""
    product = TenantProduct(tenant=tenant)
    rewritten = _apply(tenant, product, body.model_dump())
    terms = scope_terms(body.terms)
    product.save()
    _set_terms(tenant, product, terms)
    record(
        action="product.created",
        actor=actor,
        subject_type="product",
        subject_id=product.id,
        subject_title=product.name,
        summary="Added a product.",
        tenant_id=tenant.id,
        after={**_snapshot(product, _terms_of(product)), "rewritten": rewritten},
    )
    return _product_out(tenant, product.id, order)


def update_product(
    *,
    tenant: Tenant,
    actor: Actor,
    order: list[str],
    product_id: uuid.UUID,
    body: TenantProductPatch,
    expected_version: int | None,
) -> TenantProductOut:
    """`PATCH /tenant/products/{productId}`: retired with `status: retired`, never deleted."""
    product: TenantProduct = locked(TenantProduct, tenant, product_id, expected_version)
    before = _snapshot(product, _terms_of(product))
    rewritten = _apply(tenant, product, body.model_dump())
    if body.terms is not None:
        _set_terms(tenant, product, scope_terms(body.terms))
    before_changed, after_changed = changed(before, _snapshot(product, _terms_of(product)))
    product.version += 1
    product.save()
    record(
        action="product.updated",
        actor=actor,
        subject_type="product",
        subject_id=product.id,
        subject_title=product.name,
        summary="Changed a product.",
        tenant_id=tenant.id,
        before=before_changed,
        after={**after_changed, "rewritten": rewritten},
    )
    return _product_out(tenant, product.id, order)
