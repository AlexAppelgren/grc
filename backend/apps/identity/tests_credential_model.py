"""Two credential kinds on one `api_key` table (identity 0007; ACC-03, D-77, ADRs 0055 and
0056), proved as cw_app on committed rows.

A personal access token acts as a member of its own bank, always expires and is never one
of our agents; only a token acts as a person. A key bound to an agent access entry is a
bank's key and never an agent definition's. Both read and nothing else. Every rule is a
CHECK or a composite key the database holds, so no code path can mint a credential that
breaks it. The keys minted before identity 0007 become service keys.

The composite keys were proven to fail 2026-09-25 by leaving `SAME_TENANT_KEYS` out of a
scratch copy of the migration: the cross-tenant entry and person below went through."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

from django.db import DEFAULT_DB_ALIAS, IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

from apps.agents import testing as agent_testing
from apps.agents.models import AgentAccess
from apps.identity import tokens
from apps.identity.models import ApiKey, CredentialKind, LoginEvent, LoginEventKind, LoginMethod
from apps.shared import factories, permissions as perms, tenancy
from apps.shared.models import Tenant
from apps.taxonomy.models import Team

APP = "app"
BEFORE = ("identity", "0006_retire_applicability_request")
AFTER = ("identity", "0007_credential_kinds")


class Bank:
    def __init__(self, tenant: Tenant) -> None:
        self.tenant = tenant
        self.member_id = factories.member(tenant, roles=("compliance_officer",)).user_id
        with transaction.atomic(using=APP):
            tenancy.activate(tenant.id, using=APP)
            self.entry = AgentAccess.objects.using(APP).create(
                tenant_id=tenant.id,
                name="Trading platform coding agent",
                purpose="Builds the order-routing service.",
                owner_team_id=Team.objects.using(APP).get(key="compliance").id,
                created_by_id=self.member_id,
            )


def key(**fields: Any) -> ApiKey:
    _, prefix, key_hash = tokens.new_api_key()
    return ApiKey.objects.using(APP).create(name="Agent credential", key_prefix=prefix, key_hash=key_hash, **fields)


class CredentialKindsInTheDatabase(TransactionTestCase):
    databases = {DEFAULT_DB_ALIAS, APP}

    def setUp(self) -> None:
        self.a = Bank(factories.tenant(slug="credential-a"))
        self.b = Bank(factories.tenant(slug="credential-b"))
        self.agent = agent_testing.agent()
        self.expiry = timezone.now() + timedelta(days=90)

    def _token(self, **fields: Any) -> ApiKey:
        return key(
            **{
                "kind": CredentialKind.PERSONAL.value,
                "tenant_id": self.a.tenant.id,
                "acts_as_user_id": self.a.member_id,
                "expires_at": self.expiry,
                "scopes": [perms.SCOPE_LIBRARY_READ],
                **fields,
            }
        )

    def _refused(self, constraint: str, attempts: dict[str, Callable[[], object]], *, tenant: Tenant | None) -> None:
        for name, attempt in attempts.items():
            with self.subTest(name), transaction.atomic(using=APP):
                if tenant is not None:
                    tenancy.activate(tenant.id, using=APP)
                with self.assertRaisesMessage(IntegrityError, constraint), transaction.atomic(using=APP):
                    attempt()

    def test_a_token_and_an_entry_key_of_the_bank_are_accepted_and_a_key_is_a_service_key_by_default(self) -> None:
        with transaction.atomic(using=APP):
            tenancy.activate(self.a.tenant.id, using=APP)
            token = self._token(agent_access_id=self.a.entry.id)
            entry_key = key(tenant_id=self.a.tenant.id, agent_access_id=self.a.entry.id, scopes=sorted(perms.AGENT_ACCESS_SCOPES))
            plain = key(tenant_id=self.a.tenant.id, scopes=[perms.SCOPE_PROPOSALS_WRITE])
        self.assertEqual(token.kind, CredentialKind.PERSONAL.value)
        self.assertEqual((entry_key.kind, plain.kind), (CredentialKind.SERVICE.value, CredentialKind.SERVICE.value))

    def test_a_personal_token_needs_a_tenant_a_person_and_an_expiry_and_is_never_an_agents(self) -> None:
        self._refused(
            "api_key_personal_token_fenced",
            {
                "no person": lambda: self._token(acts_as_user_id=None),
                "no expiry": lambda: self._token(expires_at=None),
                "an agent's": lambda: self._token(agent_id=self.agent.id),
            },
            tenant=self.a.tenant,
        )
        # A token with no tenant is written from the platform zone, the only one that takes it.
        self._refused("api_key_personal_token_fenced", {"no tenant": lambda: self._token(tenant_id=None)}, tenant=None)

    def test_only_a_personal_token_acts_as_a_person(self) -> None:
        self._refused(
            "api_key_personal_token_fenced",
            {"a service key": lambda: key(tenant_id=self.a.tenant.id, acts_as_user_id=self.a.member_id)},
            tenant=self.a.tenant,
        )

    def test_a_key_bound_to_an_entry_is_a_banks_key_and_never_an_agents(self) -> None:
        self._refused(
            "api_key_entry_key_is_a_tenant_key",
            {"an agent's": lambda: key(tenant_id=self.a.tenant.id, agent_access_id=self.a.entry.id, agent_id=self.agent.id)},
            tenant=self.a.tenant,
        )
        self._refused(
            "api_key_entry_key_is_a_tenant_key",
            {"no tenant": lambda: key(agent_access_id=self.a.entry.id)},
            tenant=None,
        )

    def test_an_entry_key_and_a_token_hold_read_scopes_only(self) -> None:
        for scope in sorted(perms.ALL_SCOPES - perms.AGENT_ACCESS_SCOPES):
            self._refused(
                "api_key_agent_access_reads_only",
                {
                    f"entry key with {scope}": lambda scope=scope: key(  # type: ignore[misc]
                        tenant_id=self.a.tenant.id, agent_access_id=self.a.entry.id, scopes=[perms.SCOPE_LIBRARY_READ, scope]
                    ),
                    f"token with {scope}": lambda scope=scope: self._token(scopes=[scope]),  # type: ignore[misc]
                },
                tenant=self.a.tenant,
            )
        self.assertTrue(all(scope.endswith(":read") for scope in perms.AGENT_ACCESS_SCOPES))

    def test_the_database_refuses_another_banks_entry_or_person(self) -> None:
        self._refused(
            "api_key_agent_access_id_same_tenant",
            {"entry key": lambda: key(tenant_id=self.a.tenant.id, agent_access_id=self.b.entry.id)},
            tenant=self.a.tenant,
        )
        self._refused(
            "api_key_acts_as_user_id_same_tenant",
            {"token": lambda: self._token(acts_as_user_id=self.b.member_id)},
            tenant=self.a.tenant,
        )

    def test_the_security_log_takes_the_token_method_and_events(self) -> None:
        events = [
            LoginEventKind.TOKEN_CREATED,
            LoginEventKind.TOKEN_USED,
            LoginEventKind.TOKEN_REVOKED,
            LoginEventKind.CREDENTIAL_RATE_LIMITED,
        ]
        with transaction.atomic(using=APP):
            tenancy.activate(self.a.tenant.id, using=APP)
            token = self._token()
            for event in events:
                LoginEvent.objects.using(APP).create(
                    tenant_id=self.a.tenant.id,
                    user_id=self.a.member_id,
                    api_key=token,
                    method=LoginMethod.PERSONAL_TOKEN.value,
                    event=event.value,
                    success=event is not LoginEventKind.CREDENTIAL_RATE_LIMITED,
                )
            logged = list(LoginEvent.objects.using(APP).filter(api_key=token).values_list("method", "event"))
        self.assertEqual(logged, [(LoginMethod.PERSONAL_TOKEN.value, event.value) for event in events])


class KeysBeforeTheKindBecomeServiceKeys(TransactionTestCase):
    """Unapplies identity 0007, writes a platform and a bank's key the way they were written
    before it, and applies it again: both read `service`. The reverse migration is proven
    in passing."""

    databases = {DEFAULT_DB_ALIAS, APP}

    def tearDown(self) -> None:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_existing_keys_migrate_to_service(self) -> None:
        tenant = factories.tenant(slug="credential-before")
        executor = MigrationExecutor(connection)
        executor.migrate([BEFORE])
        with connection.cursor() as cursor:
            for tenant_id in (None, tenant.id):
                with transaction.atomic():
                    if tenant_id is not None:
                        tenancy.activate(tenant_id)
                    _, prefix, key_hash = tokens.new_api_key()
                    cursor.execute(
                        "INSERT INTO api_key (id, tenant_id, name, key_prefix, key_hash, scopes, created_at) "
                        "VALUES (gen_random_uuid(), %s, 'Before the kind', %s, %s, ARRAY['library:read'], now())",
                        [tenant_id, prefix, key_hash],
                    )
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([AFTER])
        with transaction.atomic():
            tenancy.activate(tenant.id)
            kinds = list(ApiKey.objects.filter(name="Before the kind").values_list("tenant_id", "kind"))
        self.assertCountEqual(kinds, [(None, CredentialKind.SERVICE.value), (tenant.id, CredentialKind.SERVICE.value)])
