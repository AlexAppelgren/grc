"""Guard: the append-only escape hatch belongs to the schema owner (INV-02, playbook 14).

`SET LOCAL cw.maintenance = 'on'` states a conscious fix inside a migration and is visible
in the session's statement log. The application role must not be able to state it: one
stray `SET LOCAL` in request code, or an injected one, would otherwise switch every
append-only ledger off for the rest of that transaction, and a source lint is the only
thing that would have stood in the way. The trigger functions therefore honour the setting
for one role and no other, so the hatch is the migrator's alone.

The check is an allowlist on `session_user`, the role that authenticated (shared 0005,
from the H-B review). Naming the role to refuse left it to every other role there will be,
and `current_user` is not the role that arrived: a SECURITY DEFINER function runs as its
owner, and so does a cascading foreign key. `session_user` changes for neither, and the two
guards below close those doors on the way in as well, by proving that no SECURITY DEFINER
function exists and that no foreign key into an append-only table acts on delete or update.

PostgreSQL setting names are case-insensitive, so `CW.MAINTENANCE` is the same setting and
is proven beside the lower-case spelling. The library's five version tables are proven the
same way in apps/library/tests_versions.py; the enumeration below ties every other
append-only table to one of the two guard functions.

Proven to fail 2026-09-19 against the previous guard function, which honoured the setting
for whoever set it: as cw_app the rewrite went through in both spellings, and the delete
got past the trigger as far as the foreign key.
"""

from __future__ import annotations

import uuid

from django.db import DEFAULT_DB_ALIAS, DatabaseError, connections, transaction
from django.test import TestCase, TransactionTestCase

from apps.shared.audit import ActorType
from apps.shared.models import AuditEvent, OutboxEvent

# Both spellings of the same setting: PostgreSQL folds the name, so a lint that reads the
# source must too, and the guard must refuse both.
HATCHES = ("SET LOCAL cw.maintenance = 'on'", "SET LOCAL CW.MAINTENANCE = 'on'")

# A realistic rewrite and a delete per ledger: what "nothing overwritten" forbids.
REFUSED = {
    "audit_event": (
        "UPDATE audit_event SET summary = 'rewritten' WHERE id = %s",
        "DELETE FROM audit_event WHERE id = %s",
    ),
    "outbox_event": (
        "UPDATE outbox_event SET topic = 'rewritten' WHERE id = %s",
        "DELETE FROM outbox_event WHERE id = %s",
    ),
}

# Every table with an append-only trigger and the function it runs. A new append-only table
# belongs here, which is the review question: does its guard ignore the hatch for the app
# role? Both functions do; nothing else may be attached.
APPEND_ONLY_TRIGGERS = {
    "audit_event": "cw_append_only_guard",
    # What a week's briefing told a bank, which nothing may rewrite afterwards: a later
    # change to the feed leaves a sent briefing exactly as it was sent (HOM-02, HOM-S3).
    "briefing_item": "cw_append_only_guard",
    # Every move of a case between categories, so the time it spent in each stage cannot
    # be rewritten afterwards (CAS-08, c9-case-models).
    "case_transition": "cw_append_only_guard",
    # The text an edit of a comment replaced: an edit keeps it and nobody rewrites it
    # away (COL-01, CHUNK10_TASKS ruling 10).
    "comment_revision": "cw_append_only_guard",
    "footprint_history": "cw_append_only_guard",
    "login_event": "cw_append_only_guard",
    "obligation_summary": "cw_append_only_guard",
    "obligation_version": "cw_append_only_guard",
    "outbox_event": "cw_outbox_guard",
    "provision_text": "cw_append_only_guard",
    "provision_version": "cw_append_only_guard",
    "verification": "cw_append_only_guard",
}


class TheHatchIsTheSchemaOwnersAlone(TransactionTestCase):
    """Committed rows, so the proof runs on the `app` connection (cw_app) the way
    production does, beside the migrator connection a migration would use."""

    databases = {DEFAULT_DB_ALIAS, "app"}

    def _committed_rows(self) -> dict[str, uuid.UUID]:
        """One audit row to rewrite, and a second one carrying the outbox row: deleting a
        row another table references would fail on the foreign key instead of the trigger,
        which would prove nothing."""
        with transaction.atomic(using="app"):
            event = self._audit_event()
            outbox = OutboxEvent.objects.using("app").create(
                tenant_id=None, audit_event=self._audit_event(), topic="probe", payload={}
            )
        return {"audit_event": event.id, "outbox_event": outbox.id}

    def _audit_event(self) -> AuditEvent:
        return AuditEvent.objects.using("app").create(
            tenant_id=None,
            actor_type=ActorType.SYSTEM.value,
            action="append-only.probe",
            subject_type="probe",
            subject_id=uuid.uuid4(),
            summary="written once",
        )

    def test_the_app_role_cannot_switch_the_triggers_off(self) -> None:
        rows = self._committed_rows()
        with connections["app"].cursor() as cursor:
            cursor.execute("SELECT current_user")
            self.assertEqual(cursor.fetchone(), ("cw_app",))
            for table, statements in REFUSED.items():
                for statement in statements:
                    for hatch in HATCHES:
                        with self.subTest(statement=statement, hatch=hatch):
                            with (
                                self.assertRaisesMessage(DatabaseError, "append-only"),
                                transaction.atomic(using="app"),
                            ):
                                cursor.execute(hatch)
                                cursor.execute(statement, [str(rows[table])])
        self.assertEqual(
            AuditEvent.objects.using("app").get(id=rows["audit_event"]).summary, "written once"
        )
        self.assertEqual(OutboxEvent.objects.using("app").get(id=rows["outbox_event"]).topic, "probe")

    def test_the_app_role_may_set_the_setting_but_it_buys_nothing(self) -> None:
        """The setting is still settable, since nothing but a superuser could forbid that,
        and it reads back as set. It buys nothing, in that transaction or a later one."""
        rows = self._committed_rows()
        with connections["app"].cursor() as cursor:
            with (
                self.assertRaisesMessage(DatabaseError, "append-only"),
                transaction.atomic(using="app"),
            ):
                cursor.execute(HATCHES[0])
                cursor.execute("SELECT current_setting('cw.maintenance', true)")
                self.assertEqual(cursor.fetchone(), ("on",))
                cursor.execute("DELETE FROM audit_event WHERE id = %s", [str(rows["audit_event"])])
            with (
                self.assertRaisesMessage(DatabaseError, "append-only"),
                transaction.atomic(using="app"),
            ):
                cursor.execute("DELETE FROM audit_event WHERE id = %s", [str(rows["audit_event"])])
        self.assertEqual(AuditEvent.objects.using("app").filter(id=rows["audit_event"]).count(), 1)

    def test_the_migration_role_still_has_the_hatch_in_either_spelling(self) -> None:
        """The whole point of the hatch: the schema owner, inside a migration, fixing a row
        it can name. The default alias is cw_migrator, which is what a migration runs as.
        Both spellings work here, which is this schema's own proof that PostgreSQL folds a
        setting name, and therefore why the lint reads the source case-insensitively."""
        rows = self._committed_rows()
        for fix, hatch in enumerate(HATCHES):
            with self.subTest(hatch=hatch):
                with transaction.atomic(), connections[DEFAULT_DB_ALIAS].cursor() as cursor:
                    cursor.execute("SELECT current_user")
                    self.assertEqual(cursor.fetchone(), ("cw_migrator",))
                    cursor.execute(hatch)
                    cursor.execute(
                        "UPDATE audit_event SET summary = %s WHERE id = %s",
                        [f"fixed {fix}", str(rows["audit_event"])],
                    )
                self.assertEqual(AuditEvent.objects.get(id=rows["audit_event"]).summary, f"fixed {fix}")

    def test_the_migration_role_is_refused_without_the_hatch(self) -> None:
        rows = self._committed_rows()
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            with (
                self.assertRaisesMessage(DatabaseError, "append-only"),
                transaction.atomic(),
            ):
                cursor.execute(
                    "UPDATE audit_event SET summary = 'fixed' WHERE id = %s", [str(rows["audit_event"])]
                )


class NothingElseArrivesAsAnotherRole(TestCase):
    """The hatch reads `session_user`, so the two ways a statement can arrive under another
    role must stay shut anyway: belt and braces on the ledgers (H-B review)."""

    databases = {DEFAULT_DB_ALIAS}

    def test_no_security_definer_function_exists(self) -> None:
        """A SECURITY DEFINER function owned by the migrator would run every statement in its
        body as the migrator. Nothing in this schema needs one; the extensions' own functions
        are theirs, not ours."""
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute(
                "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'public' AND p.prosecdef "
                "AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = p.oid AND d.deptype = 'e') "
                "ORDER BY p.proname"
            )
            found = [name for (name,) in cursor.fetchall()]
        self.assertEqual(
            found,
            [],
            "A SECURITY DEFINER function runs as its owner, which is the role the append-only "
            "hatch allows. Write the function SECURITY INVOKER, or say here why it is safe.",
        )

    def test_no_foreign_key_into_an_append_only_table_acts_on_delete_or_update(self) -> None:
        """A cascade, a SET NULL or a SET DEFAULT is a statement the system runs itself, as
        the referencing table's owner. NO ACTION and RESTRICT run nothing: they refuse, and
        Django's own deletes go through the models, where AppendOnlyModel refuses first."""
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute(
                "SELECT referenced.relname, c.conname, c.confdeltype, c.confupdtype "
                "FROM pg_constraint c "
                "JOIN pg_class referenced ON referenced.oid = c.confrelid "
                "WHERE c.contype = 'f' AND referenced.relname = ANY(%s) "
                "AND (c.confdeltype NOT IN ('a', 'r') OR c.confupdtype NOT IN ('a', 'r')) "
                "ORDER BY referenced.relname, c.conname",
                [sorted(APPEND_ONLY_TRIGGERS)],
            )
            acting = cursor.fetchall()
        self.assertEqual(
            acting,
            [],
            "A foreign key into an append-only table acts on delete or update, so the system "
            "would rewrite a ledger row for the referencing table's owner. Use NO ACTION.",
        )


class EveryAppendOnlyTableRunsAGuard(TestCase):
    """The two proofs above run on two tables. This one ties every other append-only table
    to one of the same two functions, so the hatch is the schema owner's everywhere."""

    databases = {DEFAULT_DB_ALIAS}

    def test_every_append_only_trigger_runs_one_of_the_two_guard_functions(self) -> None:
        with connections[DEFAULT_DB_ALIAS].cursor() as cursor:
            cursor.execute(
                "SELECT c.relname, p.proname FROM pg_trigger t "
                "JOIN pg_class c ON c.oid = t.tgrelid JOIN pg_proc p ON p.oid = t.tgfoid "
                r"WHERE NOT t.tgisinternal AND t.tgname LIKE '%\_append\_only' "
                "ORDER BY c.relname"
            )
            found = dict(cursor.fetchall())
        self.assertEqual(
            found,
            APPEND_ONLY_TRIGGERS,
            "An append-only table gained or lost its trigger. Every one of them must run a "
            "guard the application role cannot switch off with cw.maintenance.",
        )
