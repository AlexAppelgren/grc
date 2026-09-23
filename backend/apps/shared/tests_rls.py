"""Guard: row-level security (playbook 5, 14, NFR-01).

Enumerates every model with a foreign key to `shared.Tenant` (TenantModel subclasses and
the mixed tables) and demands, from `pg_class` and `pg_policies` on the real database,
that RLS is enabled and forced and a `tenant_isolation` policy exists whose expression
reads `app.tenant_id`.  A new tenant table without a policy fails here, not in production.

Since the split of 2026-09-20 (hardening H15) `tenant_isolation` is the write rule and
nothing else: one FOR ALL policy that matches only the session's own zone, its tenant's
rows or, with no tenant active, the rows without one. Everything a table shows beyond that
zone is a policy of its own, FOR SELECT: `library_rows_visible` on a mixed table and
`identity_lookup_visible` on the five tables read before a tenant is known — the four the
auth layer reads, and the calendar subscription a client fetches with the token in its
address. Permissive policies OR together per command, so reads stay mixed while writes are
not, and a second policy can only ever widen a read.

The second class proves the policy on the `app` alias (cw_app, no ownership): rows of
tenant A are invisible and unwritable unless tenant A is activated, and library rows
(tenant_id NULL) are visible to everyone. The third proves the write rule per mixed table:
under tenant A a platform row cannot be written, changed, deleted or pulled into the
tenant, and no row can be moved between the zones. Both are TransactionTestCases because
the proof needs committed rows visible across two connections.

Proven to fail 2026-09-19 by dropping the FORCE clause for audit_event in a scratch
copy of the migration: the first test named the table and the missing clause. The write rule
was proven to fail 2026-09-20 by handing every mixed table the old single policy again: from
tenant A's session the insert of a platform row went through, so did the update and the
delete of one on api_key, invitation, invitation_role, user_session and problem_report, and
on the three ledgers the update got past the policy as far as the append-only trigger.

The watch list was proven to fail 2026-09-20 by giving ChangeTerm a tenant foreign key: the
watch test named the table and the missing policy, and the enumeration named it too. `source`
was proven to fail the same day by leaving the hand-written policies of watch 0001 in place:
the read policy's name was not the shared one, so the policy census and the mixed-table
write proof both named it.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from django.db import DEFAULT_DB_ALIAS, DatabaseError, ProgrammingError, connections, transaction
from django.db.models import ForeignKey, Model
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.governance.models import AiGeneration, AiPurpose
from apps.identity.models import (
    ApiKey,
    Invitation,
    InvitationRole,
    LoginEvent,
    LoginEventKind,
    LoginMethod,
    SessionKind,
    TenantRole,
    UserSession,
)
from apps.library.models import ProblemReport, SubjectType
from apps.shared import factories, tenancy
from apps.shared.audit import ActorType
from apps.shared.migration_helpers import (
    IDENTITY_LOOKUP_POLICY,
    IDENTITY_LOOKUP_SETTING,
    LIBRARY_READ_POLICY,
    POLICY_NAME,
    TENANT_SETTING,
)
from apps.shared.models import AuditEvent, OutboxEvent, Tenant
from apps.shared.tenancy import library_write
from apps.shared.testing import production_models
from apps.taxonomy.models import SourceKind
from apps.watch.models import Source
from apps.watch.write import watch_write

# The only tables whose policy carries the identity-lookup clause (apps/shared/tenancy.py):
# the auth layer reads them before a tenant is known. Adding one here is a review question.
# `calendar_feed` is the fifth (D-52, ADR 0045): a calendar client presents no session and
# no key, so the subscription has to be found by the token in its address before anything
# knows which bank it belongs to.
IDENTITY_LOOKUP_TABLES = frozenset({"invitation", "membership", "user_session", "api_key", "calendar_feed"})

# Every table that holds both zones, and the column that says which zone a row is in: a row
# without a tenant is the library's, visible to everyone, and a row with one belongs to that
# tenant (playbook 14). The write rule is the same for all of them; `library_rows_visible`
# adds the read. A new mixed table belongs here, and the universal test below fails on one
# that took the old single-policy shape whether or not it was added.
MIXED_TABLES = {
    "agent_run": "tenant_id",
    # The AI output log (AUD-02, chunk 5, governance 0001). A row with no tenant is the
    # library's — the drafted "So what?" of a change, shared by every bank — and a row with
    # a tenant is that bank's own. The split shape is what keeps a bank from confirming,
    # rewriting or deleting the platform's row: its confirmation lives on its own case
    # (ruling I).
    "ai_generation": "tenant_id",
    "api_key": "tenant_id",
    "audit_event": "tenant_id",
    "invitation": "tenant_id",
    "invitation_role": "tenant_id",
    "login_event": "tenant_id",
    "outbox_event": "tenant_id",
    "problem_report": "tenant_id",
    # The derived search index (SRC-01, H7). Its zone column is always NULL in R1, so
    # `library_rows_visible` is what every bank reads a chunk through; the FOR ALL policy
    # keeps a bank session out of the shared zone it would otherwise be able to rewrite.
    "search_chunk": "owner_tenant_id",
    "source": "owner_tenant_id",
    "user_session": "tenant_id",
}

# The watch zone is library-only (chunk 5, watch 0001): its seven tables carry no tenant
# column, so a bank's judgement cannot hide in them — it lives on change_case. `source`
# alone carries the nullable owner_tenant_id of WAT-06 (INPUT_DELTAS §5), which makes it a
# mixed table and puts it in MIXED_TABLES above. Adding a table here is a review question.
WATCH_LIBRARY_TABLES = frozenset(
    {"source", "source_check", "regulatory_change", "change_event", "change_document", "change_term", "change_obligation"}
)

# instrument and obligation are mixed on `owner_tenant_id` ("shared or mine", INPUT_DELTAS
# §5, INV-07) and still carry the old single policy, so their write rule accepts the
# library's rows from a tenant session. What stands in the way there is the library fence
# (PRO-01): `library_write()` and its AST guard. Splitting them needs the fence's own zone
# switch, because the reference seed, the E2E seed and most tests write a library record
# with a tenant activated; HARDENING.md H16 carries it.
LIBRARY_OWNED_TABLES = frozenset({"instrument", "obligation"})

# Tables that hold one bank's rows and nothing else, named here so the enumeration cannot
# quietly stop seeing one. `change_case` and `case_obligation_link` are chunk 5's: a bank's
# case for a library change and its own decision about a suggested obligation link. They
# are deliberately not mixed — a change is shared and a case is not, which is why the case
# is a tenant table and not part of the watch zone (CAS-01, WAT-04, ruling C).
# `briefing`, `briefing_item` and `calendar_feed` are chunk 6's: what one bank was told
# about a week, which cases that telling named, and the calendar addresses its people
# subscribed with. None of the three ever holds a library row - a week that holds nothing
# for one bank holds three reforms for another, because the footprint behind it is its own
# (HOM-02, HOM-04).
TENANT_ONLY_TABLES = [
    "membership",
    "tenant_role",
    "support_access",
    "proposal_tenant",
    "change_case",
    "case_obligation_link",
    "briefing",
    "briefing_item",
    "calendar_feed",
]

# agent_run has carried the split since the E5 fix (agents 0001) and its write rule also
# demands a key of the same zone; agents 0002 renamed its read policy to the shared name.
# Permissive policies OR together, so any policy beside tenant_isolation widens what a
# tenant table shows. Adding one here is a review question; the test below also demands
# that every one of them is FOR SELECT, so a widening can never reach a write.
OTHER_POLICIES = frozenset(
    [(table, LIBRARY_READ_POLICY) for table in MIXED_TABLES]
    + [(table, IDENTITY_LOOKUP_POLICY) for table in IDENTITY_LOOKUP_TABLES]
)

# Platform-only tables (SRC-05, search 0002): no tenant column, so the enumeration above
# never sees them. Each carries forced row-level security and exactly one policy,
# `platform_only`, FOR ALL, refusing any session with a tenant active: a bank never reads or
# writes the evaluation set. Adding a table here is a review question.
PLATFORM_ONLY_TABLES = frozenset({"eval_question", "eval_run"})
PLATFORM_ONLY_POLICY = "platform_only"


def own_zone_rule(column: str) -> str:
    """`<column> IS NOT DISTINCT FROM <the session's tenant>` as PostgreSQL renders it back
    in pg_policies, which is with the negation on the outside."""
    return f"NOT ({column} IS DISTINCT FROM"


def tenant_scoped_models() -> list[type[Model]]:
    """Every concrete model with a foreign key to shared.Tenant."""
    found = []
    for model in production_models():
        if model is Tenant or model._meta.abstract:
            continue
        for field in model._meta.get_fields():
            if isinstance(field, ForeignKey) and field.related_model is Tenant:
                found.append(model)
                break
    return found


class RowLevelSecurityGuard(TestCase):
    databases = {DEFAULT_DB_ALIAS}

    def _policies(self, table: str) -> dict[str, tuple[str, str, str]]:
        """Every policy on `table` as PostgreSQL itself renders it: name to (command,
        USING, WITH CHECK)."""
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute("SELECT policyname, cmd, qual, with_check FROM pg_policies WHERE tablename = %s", [table])
            return {name: (cmd, qual or "", check or "") for name, cmd, qual, check in cursor.fetchall()}

    def test_enumeration_finds_the_mixed_tables(self) -> None:
        tables = sorted(model._meta.db_table for model in tenant_scoped_models())
        for table in sorted(MIXED_TABLES) + sorted(LIBRARY_OWNED_TABLES) + TENANT_ONLY_TABLES:
            self.assertIn(table, tables)

    def test_the_watch_tables_are_library_tables_and_only_source_holds_a_tenant_column(self) -> None:
        tables = {model._meta.db_table for model in tenant_scoped_models()}
        self.assertEqual(
            WATCH_LIBRARY_TABLES & tables,
            {"source"},
            "a watch table grew a tenant column; the tenant's judgement belongs on change_case (WAT-03, CAS-01)",
        )
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute("SELECT relname FROM pg_class WHERE relname = ANY(%s)", [sorted(WATCH_LIBRARY_TABLES)])
            found = {row[0] for row in cursor.fetchall()}
        self.assertEqual(found, set(WATCH_LIBRARY_TABLES), "the watch migration did not create every table it guards")

    def test_only_the_named_tables_carry_the_identity_lookup_clause(self) -> None:
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute("SELECT tablename, qual, with_check FROM pg_policies")
            with_clause = {
                table
                for table, qual, check in cursor.fetchall()
                if IDENTITY_LOOKUP_SETTING in (qual or "") or IDENTITY_LOOKUP_SETTING in (check or "")
            }
        self.assertEqual(
            with_clause,
            IDENTITY_LOOKUP_TABLES,
            "the identity-lookup clause is for the tables the auth layer reads before a tenant is known; "
            "update IDENTITY_LOOKUP_TABLES and say why",
        )

    def test_only_the_named_policies_sit_beside_the_tenant_policy_and_all_of_them_read(self) -> None:
        tables = [model._meta.db_table for model in tenant_scoped_models()]
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute(
                "SELECT tablename, policyname, cmd FROM pg_policies WHERE tablename = ANY(%s) AND policyname <> %s",
                [tables, POLICY_NAME],
            )
            found = cursor.fetchall()
        self.assertEqual(
            frozenset((table, policy) for table, policy, _ in found),
            OTHER_POLICIES,
            "a second policy widens its table; update OTHER_POLICIES and say why",
        )
        self.assertEqual(
            sorted((table, policy) for table, policy, cmd in found if cmd != "SELECT"),
            [],
            f"a policy beside {POLICY_NAME} may widen a read, never a write: make it FOR SELECT",
        )

    def test_every_tenant_table_has_forced_rls_and_a_tenant_policy(self) -> None:
        problems: list[str] = []
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            for model in tenant_scoped_models():
                table = model._meta.db_table
                cursor.execute(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s", [table]
                )
                row = cursor.fetchone()
                if row is None:
                    problems.append(f"{table}: table not found")
                    continue
                enabled, forced = row
                if not enabled:
                    problems.append(f"{table}: ROW LEVEL SECURITY is not enabled")
                if not forced:
                    problems.append(f"{table}: ROW LEVEL SECURITY is not forced (the owner would bypass it)")
                policy = self._policies(table).get(POLICY_NAME)
                if policy is None:
                    problems.append(f"{table}: no policy named {POLICY_NAME}")
                    continue
                _, qual, with_check = policy
                if TENANT_SETTING not in qual:
                    problems.append(f"{table}: policy USING does not read {TENANT_SETTING}: {qual}")
                if TENANT_SETTING not in with_check:
                    problems.append(f"{table}: policy WITH CHECK does not read {TENANT_SETTING}: {with_check}")
        self.assertEqual(
            problems,
            [],
            "Tenant tables without forced RLS and a tenant policy:\n  "
            + "\n  ".join(problems)
            + "\nAppend rls_operations(<table>) from apps.shared.migration_helpers to the migration.",
        )

    def test_every_mixed_table_writes_only_its_own_zone(self) -> None:
        """The shape H15 asks for, per mixed table, so a new one cannot take the old one:
        `tenant_isolation` FOR ALL on the session's own zone, and the library's rows added
        by a policy that can only read."""
        problems: list[str] = []
        for table, column in sorted(MIXED_TABLES.items()):
            policies = self._policies(table)
            if POLICY_NAME not in policies:
                problems.append(f"{table}: no policy named {POLICY_NAME}")
                continue
            own_zone = own_zone_rule(column)
            cmd, qual, with_check = policies[POLICY_NAME]
            if cmd != "ALL":
                problems.append(f"{table}: {POLICY_NAME} is FOR {cmd}, not FOR ALL")
            if own_zone not in qual:
                problems.append(f"{table}: {POLICY_NAME} USING is not the own-zone rule: {qual}")
            if own_zone not in with_check:
                problems.append(f"{table}: {POLICY_NAME} WITH CHECK is not the own-zone rule: {with_check}")
            read = policies.get(LIBRARY_READ_POLICY)
            if read is None:
                problems.append(f"{table}: no {LIBRARY_READ_POLICY} policy, so the library's rows read as gone")
            elif read[0] != "SELECT" or f"{column} IS NULL" not in read[1]:
                problems.append(f"{table}: {LIBRARY_READ_POLICY} is FOR {read[0]} USING {read[1]}")
        self.assertEqual(
            problems,
            [],
            "Mixed tables that do not carry the split of H15:\n  "
            + "\n  ".join(problems)
            + "\nUse rls_operations(<table>, mixed=True) on a new table, or "
            "split_policy_operations(<table>, mixed=True) on one that already exists.",
        )

    def test_no_write_rule_accepts_the_other_zone_or_the_lookup_flag(self) -> None:
        """The universal form of H15, which a new mixed table cannot slip past by staying
        out of MIXED_TABLES: no table's write rule may accept a row of the zone the session
        is not in, and none may lean on the identity-lookup flag, which the auth layer
        switches on to read."""
        problems: list[str] = []
        for model in tenant_scoped_models():
            table = model._meta.db_table
            if table in LIBRARY_OWNED_TABLES:
                continue
            policy = self._policies(table).get(POLICY_NAME)
            if policy is None:
                continue  # the test above names it
            with_check = policy[2]
            if "IS NULL" in with_check:
                problems.append(f"{table}: WITH CHECK accepts a row of the other zone: {with_check}")
            if IDENTITY_LOOKUP_SETTING in with_check:
                problems.append(f"{table}: WITH CHECK accepts anything while the lookup flag is on: {with_check}")
        self.assertEqual(
            problems,
            [],
            "Write rules that accept more than the session's own zone:\n  " + "\n  ".join(problems),
        )

    def test_every_platform_only_table_refuses_any_tenant_session(self) -> None:
        """RLS enabled and forced, and one policy whose USING and WITH CHECK both demand
        that the tenant setting is empty; the same policy name on any other table fails."""
        problems: list[str] = []
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = ANY(%s)",
                [sorted(PLATFORM_ONLY_TABLES)],
            )
            flags = {name: (enabled, forced) for name, enabled, forced in cursor.fetchall()}
            cursor.execute("SELECT DISTINCT tablename FROM pg_policies WHERE policyname = %s", [PLATFORM_ONLY_POLICY])
            carriers = {row[0] for row in cursor.fetchall()}
        for table in sorted(PLATFORM_ONLY_TABLES):
            if flags.get(table) != (True, True):
                problems.append(f"{table}: row-level security is not enabled and forced: {flags.get(table)}")
            policies = self._policies(table)
            if set(policies) != {PLATFORM_ONLY_POLICY}:
                problems.append(f"{table}: policies {sorted(policies)}, not {PLATFORM_ONLY_POLICY} alone")
                continue
            cmd, qual, with_check = policies[PLATFORM_ONLY_POLICY]
            for part, rule in (("USING", qual), ("WITH CHECK", with_check)):
                if TENANT_SETTING not in rule or "IS NULL" not in rule:
                    problems.append(f"{table}: {PLATFORM_ONLY_POLICY} {part} does not refuse a tenant session: {rule}")
            if cmd != "ALL":
                problems.append(f"{table}: {PLATFORM_ONLY_POLICY} is FOR {cmd}, not FOR ALL")
        if carriers - PLATFORM_ONLY_TABLES:
            problems.append(f"{sorted(carriers - PLATFORM_ONLY_TABLES)} carry {PLATFORM_ONLY_POLICY}; list them in PLATFORM_ONLY_TABLES")
        self.assertEqual(problems, [], "Platform-only tables a tenant session could reach:\n  " + "\n  ".join(problems))


class RowLevelSecurityEnforcement(TransactionTestCase):
    """Proves the policy bites for cw_app (the `app` alias), not just that it exists."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def setUp(self) -> None:
        self.tenant_a = factories.tenant(slug="rls-a")
        self.tenant_b = factories.tenant(slug="rls-b")

    def _insert(self, tenant_id: uuid.UUID | None, *, using: str) -> AuditEvent:
        return AuditEvent.objects.using(using).create(
            tenant_id=tenant_id,
            actor_type=ActorType.SYSTEM.value,
            action="rls.probe",
            subject_type="probe",
            subject_id=uuid.uuid4(),
        )

    def _rows_of_both_zones(self) -> None:
        """One row of tenant A and one of the platform. Each goes in from a session of its
        own zone, because the write rule accepts nothing else (H15)."""
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_a.id, using="app")
            self._insert(self.tenant_a.id, using="app")
        with transaction.atomic(using="app"):
            self._insert(None, using="app")

    def test_activated_tenant_sees_only_its_rows_and_library_rows(self) -> None:
        self._rows_of_both_zones()
        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_b.id, using="app")
            self._insert(self.tenant_b.id, using="app")

        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_a.id, using="app")
            visible = set(AuditEvent.objects.using("app").values_list("tenant_id", flat=True))
        self.assertEqual(visible, {self.tenant_a.id, None})

        with transaction.atomic(using="app"):
            tenancy.activate(self.tenant_b.id, using="app")
            visible = set(AuditEvent.objects.using("app").values_list("tenant_id", flat=True))
        self.assertEqual(visible, {self.tenant_b.id, None})

    def test_no_activation_sees_only_library_rows_and_cannot_write_tenant_rows(self) -> None:
        self._rows_of_both_zones()
        with transaction.atomic(using="app"):
            self.assertIsNone(tenancy.database_tenant_id(using="app"))
            visible = set(AuditEvent.objects.using("app").values_list("tenant_id", flat=True))
            self.assertEqual(visible, {None}, "an unset tenant must match no tenant rows (fail closed)")
        with self.assertRaises(ProgrammingError):
            with transaction.atomic(using="app"):
                self._insert(self.tenant_a.id, using="app")

    def test_activated_tenant_cannot_write_another_tenants_rows(self) -> None:
        with self.assertRaises(ProgrammingError):
            with transaction.atomic(using="app"):
                tenancy.activate(self.tenant_a.id, using="app")
                self._insert(self.tenant_b.id, using="app")


class MixedTablesWriteOnlyTheirOwnZone(TransactionTestCase):
    """The write rule per mixed table, as cw_app, in SQL rather than through the ORM: the
    policy is what must refuse this, not `AppendOnlyQuerySet` or a model's save (H15).

    One row per table in each zone, then, with tenant A activated: the platform row cannot
    be written, changed, deleted or pulled into the tenant, tenant A's own row cannot be
    moved into the library, and both rows still read exactly as before.

    agent_run is not here: it has carried this rule since the E5 fix and is proven, with the
    key of its own zone, in apps/agents/tests_models.py. `search_chunk` is not here either:
    it is written only inside `index_write()` (SRC-01, H7), so a row of it cannot be built
    here without reaching through that fence, and the same four refusals are proven as
    cw_app in apps/search/tests_index_model.py. `source` is: it is the one watch table with
    a zone column (WAT-06), and a bank must not be able to reach the shared source registry
    the sweeps read.
    """

    databases = {DEFAULT_DB_ALIAS, "app"}

    # These three also carry the append-only trigger, which runs before the policy's WITH
    # CHECK and refuses the move with its own message. Either way the row stays put.
    LEDGERS = frozenset({"audit_event", "login_event", "outbox_event"})

    def setUp(self) -> None:
        self.tenant_a = factories.tenant(slug="zone-a")
        self.tenant_b = factories.tenant(slug="zone-b")
        self.user = factories.user(email="zone-probe@example.test")
        with transaction.atomic():
            tenancy.activate(self.tenant_a.id)
            self.role_id = TenantRole.objects.filter(tenant=self.tenant_a).order_by("key").values_list("id", flat=True)[0]
        with library_write("a zone probe"):
            self.source_kind = SourceKind.objects.create(key="zone-probe")
        self.platform = self._rows(None)
        self.own = self._rows(self.tenant_a.id)

    def _tables(self) -> list[str]:
        return [table for table in sorted(MIXED_TABLES) if table not in {"agent_run", "search_chunk"}]

    def _rows(self, tenant_id: uuid.UUID | None) -> dict[str, Any]:
        """One committed row per table in the zone `tenant_id` names."""
        with transaction.atomic(using="app"):
            if tenant_id is not None:
                tenancy.activate(tenant_id, using="app")
            return {table: self._build(table, tenant_id).pk for table in self._tables()}

    def _build(self, table: str, tenant_id: uuid.UUID | None) -> Any:
        """A realistic row of `table`, written on the cw_app connection."""
        now = timezone.now()
        token = uuid.uuid4().hex
        if table == "audit_event":
            return self._audit_event(tenant_id)
        if table == "ai_generation":
            # Written here rather than through `log_generation()`, which has no second
            # connection to write on: the row this guard needs is a realistic one on the
            # cw_app connection, and what is under test is the policy, not the writer.
            return AiGeneration.objects.using("app").create(
                tenant_id=tenant_id,
                purpose=AiPurpose.SO_WHAT.value,
                model="mock",
                model_version="0",
                output="A probe, not a draft.",
            )
        if table == "outbox_event":
            return OutboxEvent.objects.using("app").create(
                tenant_id=tenant_id, audit_event=self._audit_event(tenant_id), topic="rls.probe", payload={}
            )
        if table == "invitation":
            return Invitation.objects.using("app").create(
                tenant_id=tenant_id,
                email=f"{token}@example.test",
                token_hash=token,
                expires_at=now + timedelta(hours=72),
            )
        if table == "invitation_role":
            return InvitationRole.objects.using("app").create(
                tenant_id=tenant_id, invitation=self._build("invitation", tenant_id), role_id=self.role_id
            )
        if table == "user_session":
            return UserSession.objects.using("app").create(
                user=self.user,
                tenant_id=tenant_id,
                kind=SessionKind.FULL.value,
                refresh_token_hash=token,
                last_seen_at=now,
                expires_at=now + timedelta(days=1),
            )
        if table == "api_key":
            return ApiKey.objects.using("app").create(
                tenant_id=tenant_id, name="Zone probe", key_prefix=token[:8], key_hash=token, scopes=[]
            )
        if table == "source":
            # The one watch table with a zone column (WAT-06). It is a library record, so the
            # Python fence has to be open too; the door it belongs behind is watch_write().
            with watch_write("a zone probe"):
                return Source.objects.using("app").create(
                    owner_tenant_id=tenant_id, name=f"Probe {token}", kind=self.source_kind
                )
        if table == "login_event":
            return LoginEvent.objects.using("app").create(
                tenant_id=tenant_id,
                method=LoginMethod.PASSKEY.value,
                event=LoginEventKind.SIGNIN.value,
                success=True,
            )
        if table == "problem_report":
            return ProblemReport.objects.using("app").create(
                tenant_id=tenant_id,
                reporter=self.user,
                subject_type=SubjectType.OBLIGATION.value,
                subject_id=uuid.uuid4(),
                text="A probe, not a report.",
            )
        raise AssertionError(f"{table} is mixed and has no row builder here")

    def _audit_event(self, tenant_id: uuid.UUID | None) -> AuditEvent:
        return AuditEvent.objects.using("app").create(
            tenant_id=tenant_id,
            actor_type=ActorType.SYSTEM.value,
            action="rls.probe",
            subject_type="probe",
            subject_id=uuid.uuid4(),
        )

    def test_a_tenant_cannot_write_a_platform_row(self) -> None:
        for table in self._tables():
            with self.subTest(table=table):
                with self.assertRaises(ProgrammingError):
                    with transaction.atomic(using="app"):
                        tenancy.activate(self.tenant_a.id, using="app")
                        self._build(table, None)

    def test_a_tenant_cannot_change_delete_or_claim_a_platform_row(self) -> None:
        for table in self._tables():
            column = MIXED_TABLES[table]
            with self.subTest(table=table), transaction.atomic(using="app"):
                tenancy.activate(self.tenant_a.id, using="app")
                with connections["app"].cursor() as cursor:
                    for statement, parameters, why in (
                        (f'UPDATE "{table}" SET {column} = {column} WHERE id = %s', [self.platform[table]], "changed"),
                        (
                            f'UPDATE "{table}" SET {column} = %s WHERE id = %s',
                            [str(self.tenant_a.id), self.platform[table]],
                            "claimed by the tenant",
                        ),
                        (f'DELETE FROM "{table}" WHERE id = %s', [self.platform[table]], "deleted"),
                    ):
                        cursor.execute(statement, parameters)
                        self.assertEqual(cursor.rowcount, 0, f"a platform row was {why} from tenant A's session")

    def test_a_tenant_cannot_move_its_own_row_into_the_library(self) -> None:
        for table in self._tables():
            column = MIXED_TABLES[table]
            refusal = "append-only" if table in self.LEDGERS else "row-level security"
            with self.subTest(table=table):
                with self.assertRaisesMessage(DatabaseError, refusal):
                    with transaction.atomic(using="app"), connections["app"].cursor() as cursor:
                        tenancy.activate(self.tenant_a.id, using="app")
                        cursor.execute(f'UPDATE "{table}" SET {column} = NULL WHERE id = %s', [self.own[table]])

    def test_the_reads_are_unchanged(self) -> None:
        """The whole point of a mixed table: the platform's rows are everybody's to read,
        a tenant's are its own. Splitting the write rule off must not touch that."""
        for table in self._tables():
            with self.subTest(table=table):
                self.assertEqual(self._visible(table, self.tenant_a.id), {self.platform[table], self.own[table]})
                self.assertEqual(self._visible(table, self.tenant_b.id), {self.platform[table]})
                self.assertEqual(self._visible(table, None), {self.platform[table]})

    def _visible(self, table: str, tenant_id: uuid.UUID | None) -> set[Any]:
        probes = [self.platform[table], self.own[table]]
        with transaction.atomic(using="app"), connections["app"].cursor() as cursor:
            if tenant_id is not None:
                tenancy.activate(tenant_id, using="app")
            cursor.execute(f'SELECT id FROM "{table}" WHERE id = ANY(%s)', [probes])
            return {row[0] for row in cursor.fetchall()}
