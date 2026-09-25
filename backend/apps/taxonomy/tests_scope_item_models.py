"""Scope items as rows of the regulatory scope request (taxonomy 0012; OWN-01, FP-02, D-89,
D-91, ADR 0059), proved as cw_app on committed rows: tenant B sees none of tenant A's scope
items or scope-item request rows, the database refuses a reference to another bank's item or
request, the four-eyes check on the request holds with scope-item rows on it, and a history
row names exactly one of a term or a scope item.

What is written here is written as cw_app with a tenant active, the way the request logic
writes it: the model is a person's request and never a key's or an agent's (the routes and
the agent paths that prove that are `d89-scope-items-logic`'s and `d89-agent-research`'s).

The composite keys were proven to fail 2026-09-25 by leaving `COMPOSITE_KEYS` out of a scratch
copy of taxonomy 0012: every cross-tenant reference below went through."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from django.core.exceptions import ValidationError
from django.db import DEFAULT_DB_ALIAS, IntegrityError, transaction
from django.db.models import Model
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.library import testing as library_testing
from apps.library.models import Jurisdiction
from apps.library.seeds import seed_jurisdictions, seed_languages
from apps.shared import factories, tenancy
from apps.shared.models import Tenant
from apps.taxonomy.models import (
    ApprovalStatus,
    FootprintAction,
    FootprintChangeRequest,
    FootprintChangeScopeItem,
    FootprintHistory,
    ScopeItem,
    ScopeItemStatus,
    validate_public_https_url,
)
from apps.taxonomy.seeds import seed_library_vocabularies, seed_taxonomy_terms

APP = "app"
SOURCE = "https://www.fi.se/sv/vara-register/"


class Bank:
    """One bank's waiting request with one scope item to add, as cw_app in its zone."""

    def __init__(self, tenant: Tenant, requester_id: uuid.UUID, approver_id: uuid.UUID) -> None:
        self.tenant = tenant
        self.requester_id = requester_id
        self.approver_id = approver_id
        with transaction.atomic(using=APP):
            tenancy.activate(tenant.id, using=APP)
            self.request = self.create(FootprintChangeRequest, requested_by_id=requester_id)
            self.item = self.scope_item(key=f"{tenant.slug}-crypto-assets")
            self.link = self.create(
                FootprintChangeScopeItem, request_id=self.request.id, scope_item_id=self.item.id, action=FootprintAction.ADDED.value
            )

    def create(self, model: type[Model], **fields: Any) -> Any:
        return model._default_manager.using(APP).create(tenant_id=self.tenant.id, **fields)

    def scope_item(self, **fields: Any) -> ScopeItem:
        values: dict[str, Any] = {
            "name": "Local crypto-asset rules",
            "jurisdiction_id": Jurisdiction.objects.get(key="se").id,
            "regime_term_id": library_testing.term("regime:securities").id,
            "official_reference": "FFFS 2026:1",
            "source_url": SOURCE,
            **fields,
        }
        item: ScopeItem = self.create(ScopeItem, **values)
        return item


class ScopeItemTablesUnderRowLevelSecurity(TransactionTestCase):
    databases = {DEFAULT_DB_ALIAS, APP}

    def setUp(self) -> None:
        with transaction.atomic():
            seed_languages()
            seed_jurisdictions()
            seed_library_vocabularies()
            seed_taxonomy_terms()
        tenant_a = factories.tenant(slug="scope-a")
        tenant_b = factories.tenant(slug="scope-b")
        self.a = Bank(tenant_a, factories.member(tenant_a).user_id, factories.member(tenant_a).user_id)
        self.b = Bank(tenant_b, factories.member(tenant_b).user_id, factories.member(tenant_b).user_id)

    def test_each_tenant_sees_only_its_own_scope_items_and_request_rows(self) -> None:
        for bank in (self.a, self.b):
            with transaction.atomic(using=APP):
                tenancy.activate(bank.tenant.id, using=APP)
                self.assertEqual(list(ScopeItem.objects.using(APP).values_list("id", flat=True)), [bank.item.id])
                self.assertEqual(list(FootprintChangeScopeItem.objects.using(APP).values_list("id", flat=True)), [bank.link.id])

    def test_tenant_b_cannot_change_tenant_a_s_scope_item(self) -> None:
        with transaction.atomic(using=APP):
            tenancy.activate(self.b.tenant.id, using=APP)
            self.assertEqual(ScopeItem.objects.using(APP).filter(pk=self.a.item.pk).update(name="Taken over"), 0)
        with transaction.atomic(using=APP):
            tenancy.activate(self.a.tenant.id, using=APP)
            self.assertEqual(ScopeItem.objects.using(APP).get(pk=self.a.item.pk).name, "Local crypto-asset rules")

    def test_the_database_refuses_a_reference_to_another_tenants_item_or_request(self) -> None:
        a, b = self.a, self.b
        attempts: dict[str, Callable[[], object]] = {
            "footprint_change_scope_item_scope_item_id_same_tenant": lambda: a.create(
                FootprintChangeScopeItem, request_id=a.request.id, scope_item_id=b.item.id, action=FootprintAction.REMOVED.value
            ),
            "footprint_change_scope_item_request_id_same_tenant": lambda: a.create(
                FootprintChangeScopeItem,
                request_id=b.request.id,
                scope_item_id=a.scope_item(key="second").id,
                action=FootprintAction.ADDED.value,
            ),
            "footprint_history_scope_item_id_same_tenant": lambda: a.create(
                FootprintHistory, scope_item_id=b.item.id, action=FootprintAction.ADDED.value, changed_by_id=a.approver_id
            ),
        }
        for constraint, attempt in attempts.items():
            with self.subTest(constraint), transaction.atomic(using=APP):
                tenancy.activate(a.tenant.id, using=APP)
                with self.assertRaisesMessage(IntegrityError, constraint), transaction.atomic(using=APP):
                    attempt()

    def test_the_requester_cannot_decide_a_request_that_carries_scope_items(self) -> None:
        a = self.a
        with transaction.atomic(using=APP):
            tenancy.activate(a.tenant.id, using=APP)
            requests = FootprintChangeRequest.objects.using(APP).filter(pk=a.request.pk)
            with self.assertRaisesMessage(IntegrityError, "footprint_change_request_four_eyes"), transaction.atomic(using=APP):
                requests.update(status=ApprovalStatus.APPROVED.value, decided_by_id=a.requester_id, decided_at=timezone.now())
            requests.update(status=ApprovalStatus.APPROVED.value, decided_by_id=a.approver_id, decided_at=timezone.now())
            self.assertEqual(requests.get().decided_by_id, a.approver_id)

    def test_a_history_row_names_exactly_one_of_a_term_or_a_scope_item(self) -> None:
        a = self.a
        term_id = library_testing.term("regime:securities").id
        with transaction.atomic(using=APP):
            tenancy.activate(a.tenant.id, using=APP)
            for label, subject in (("neither", {}), ("both", {"term_id": term_id, "scope_item_id": a.item.id})):
                with self.subTest(label), self.assertRaisesMessage(IntegrityError, "footprint_history_term_or_scope_item"):
                    with transaction.atomic(using=APP):
                        a.create(FootprintHistory, action=FootprintAction.ADDED.value, request_id=a.request.id, **subject)
            row = a.create(FootprintHistory, scope_item_id=a.item.id, action=FootprintAction.ADDED.value, request_id=a.request.id)
            self.assertIsNone(row.term_id)
            a.create(FootprintHistory, term_id=term_id, action=FootprintAction.ADDED.value, request_id=a.request.id)

    def test_an_item_is_on_a_request_once_and_its_key_is_the_banks_once(self) -> None:
        a = self.a
        with transaction.atomic(using=APP):
            tenancy.activate(a.tenant.id, using=APP)
            with self.assertRaisesMessage(IntegrityError, "footprint_change_scope_item_unique"), transaction.atomic(using=APP):
                a.create(FootprintChangeScopeItem, request_id=a.request.id, scope_item_id=a.item.id, action=FootprintAction.REMOVED.value)
            with self.assertRaisesMessage(IntegrityError, "scope_item_key_unique"), transaction.atomic(using=APP):
                a.scope_item(key=a.item.key)
        with transaction.atomic(using=APP):
            tenancy.activate(self.b.tenant.id, using=APP)
            self.b.scope_item(key=a.item.key)

    def test_a_new_item_waits_as_requested_and_its_address_is_https_in_the_database_too(self) -> None:
        a = self.a
        self.assertEqual(a.item.status, ScopeItemStatus.REQUESTED.value)
        with transaction.atomic(using=APP):
            tenancy.activate(a.tenant.id, using=APP)
            with self.assertRaisesMessage(IntegrityError, "scope_item_source_https"), transaction.atomic(using=APP):
                a.scope_item(key="plain-http", source_url="http://www.fi.se/")


class ScopeItemBoundaryChecks(SimpleTestCase):
    """The checks a request's fields pass before a scope item is written: the model's own
    validators, which `full_clean()` runs and the request logic calls at the boundary."""

    def item(self, **fields: Any) -> ScopeItem:
        values: dict[str, Any] = {
            "tenant_id": uuid.uuid4(),
            "key": "crypto-assets",
            "name": "Local crypto-asset rules",
            "jurisdiction_id": uuid.uuid4(),
            "regime_term_id": uuid.uuid4(),
            "source_url": SOURCE,
            **fields,
        }
        return ScopeItem(**values)

    def errors(self, item: ScopeItem) -> dict[str, list[str]]:
        try:
            item.clean_fields(exclude={"tenant", "jurisdiction", "regime_term"})
        except ValidationError as error:
            return error.message_dict
        return {}

    def test_a_public_https_address_passes(self) -> None:
        for url in (SOURCE, "https://eur-lex.europa.eu/eli/reg/2023/1114/oj", "https://8.8.8.8/rules"):
            with self.subTest(url):
                validate_public_https_url(url)

    def test_an_address_that_is_not_public_https_is_refused(self) -> None:
        refused = (
            "http://www.fi.se/",
            "ftp://www.fi.se/",
            "https://localhost/",
            "https://app.localhost/",
            "https://intranet/",
            "https://server.internal/",
            "https://printer.local/",
            "https://127.0.0.1/",
            "https://10.0.0.8/",
            "https://169.254.169.254/latest/meta-data/",
            "https://[::1]/",
            "https://[fd00::1]/",
            "https://user:secret@www.fi.se/",
        )
        for url in refused:
            with self.subTest(url), self.assertRaises(ValidationError):
                validate_public_https_url(url)
        self.assertIn("source_url", self.errors(self.item(source_url="https://10.0.0.8/")))

    @override_settings(SCOPE_ITEM_DESCRIPTION_MAX_CHARS=12)
    def test_the_description_is_capped_by_the_setting(self) -> None:
        self.assertEqual(self.errors(self.item(description="x" * 12)), {})
        self.assertIn("description", self.errors(self.item(description="x" * 13)))

    def test_the_cap_has_a_default_of_its_own(self) -> None:
        self.assertEqual(self.errors(self.item(description="A regulation the library has not covered yet.")), {})
