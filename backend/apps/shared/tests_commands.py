"""The management commands the entrypoint and the gates call: seed_reference (the loop and
its "what breaks without it" line), migrate_from_zero (the subprocess it spawns and the
scratch database it drops), export_openapi (writes the normalised document), and
bootstrap_platform's --role option (which platform role it grants, the audit row the
grant leaves, in each of a bank member's banks too since D-122, and --add-role for a second
role), and its --reenrol option (platform staff's own recovery, ID-05)."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings

from apps.identity import invitation_logic
from apps.identity.models import Invitation, PlatformRoleAssignment, User, WebAuthnCredential
from apps.shared import factories, tenancy
from apps.shared.testing import sign_in
from apps.shared.management.commands import migrate_from_zero, seed_reference
from apps.shared.models import AuditEvent


class SeedReference(TestCase):
    def test_the_registered_seeds_run_and_report(self) -> None:
        from apps.shared import factories

        factories.tenant(slug="seeded")
        out = StringIO()
        call_command("seed_reference", stdout=out)
        self.assertIn("languages: 5 rows", out.getvalue())
        self.assertIn("platform_roles: 2 rows", out.getvalue())
        self.assertIn("tenant_system_roles: 7 rows", out.getvalue())

    def test_each_seed_runs_in_order_and_prints_what_breaks_without_it(self) -> None:
        order: list[str] = []

        def first() -> int:
            order.append("first")
            return 3

        def second() -> int:
            order.append("second")
            return 1

        seeds = (
            ("permissions", first, "every route 403s"),
            ("system_roles", second, "invitations cannot assign a role"),
        )
        out = StringIO()
        with mock.patch.object(seed_reference, "REFERENCE_SEEDS", seeds):
            call_command("seed_reference", stdout=out)
        self.assertEqual(order, ["first", "second"])
        self.assertIn("permissions: 3 rows (without it: every route 403s)", out.getvalue())
        self.assertIn("system_roles: 1 rows", out.getvalue())


class MigrateFromZero(SimpleTestCase):
    @override_settings(IS_DEPLOYED_ENVIRONMENT=True)
    def test_refuses_a_deployed_environment(self) -> None:
        with self.assertRaises(CommandError):
            call_command("migrate_from_zero")

    @override_settings(MIGRATOR_DATABASE_URL="postgres://cw_migrator:pw@db:5432/compliance_watch")
    def test_recreates_the_scratch_database_and_migrates_it_in_a_subprocess(self) -> None:
        executed: list[str] = []
        conn = mock.MagicMock()
        conn.__enter__.return_value.execute.side_effect = lambda sql: executed.append(sql)
        completed = mock.Mock(returncode=0)
        with mock.patch.object(migrate_from_zero.psycopg, "connect", return_value=conn) as connect, mock.patch.object(
            migrate_from_zero.subprocess, "run", return_value=completed
        ) as run:
            call_command("migrate_from_zero", stdout=StringIO())
        self.assertEqual(connect.call_args_list[0].args[0], "postgres://cw_migrator:pw@db:5432/postgres")
        self.assertTrue(any("DROP DATABASE IF EXISTS" in sql for sql in executed))
        self.assertTrue(any("CREATE DATABASE" in sql and "TEMPLATE template1" in sql for sql in executed))
        self.assertEqual(executed.count('DROP DATABASE IF EXISTS "compliance_watch_scratch" WITH (FORCE)'), 2)
        env = run.call_args.kwargs["env"]
        scratch = "postgres://cw_migrator:pw@db:5432/compliance_watch_scratch"
        self.assertEqual(env["DATABASE_URL"], scratch)
        self.assertEqual(env["MIGRATOR_DATABASE_URL"], scratch)
        self.assertIn("migrate", run.call_args.args[0])

    @override_settings(MIGRATOR_DATABASE_URL="postgres://cw_migrator:pw@db:5432/compliance_watch")
    def test_keep_leaves_the_scratch_database_and_a_failed_migrate_raises(self) -> None:
        executed: list[str] = []
        conn = mock.MagicMock()
        conn.__enter__.return_value.execute.side_effect = lambda sql: executed.append(sql)
        with mock.patch.object(migrate_from_zero.psycopg, "connect", return_value=conn), mock.patch.object(
            migrate_from_zero.subprocess, "run", return_value=mock.Mock(returncode=0)
        ):
            call_command("migrate_from_zero", "--keep", stdout=StringIO())
        self.assertEqual(executed.count('DROP DATABASE IF EXISTS "compliance_watch_scratch" WITH (FORCE)'), 1)
        with mock.patch.object(migrate_from_zero.psycopg, "connect", return_value=conn), mock.patch.object(
            migrate_from_zero.subprocess, "run", return_value=mock.Mock(returncode=1)
        ):
            with self.assertRaises(CommandError):
                call_command("migrate_from_zero", stdout=StringIO())


    @override_settings(MIGRATOR_DATABASE_URL="postgres://cw_migrator:pw@db:5432/compliance_watch")
    def test_name_picks_the_database_and_refuses_an_unsafe_one(self) -> None:
        """The E2E boot builds `compliance_watch_e2e` with `--name` and `--keep`
        (frontend/tests/e2e/support/start-backend.sh). Before this option existed the boot
        migrated the scratch database, dropped it, and seeded an unmigrated one:
        'relation "tenant" does not exist' on the first E2E run, 2026-09-19."""
        executed: list[str] = []
        conn = mock.MagicMock()
        conn.__enter__.return_value.execute.side_effect = lambda sql: executed.append(sql)
        with mock.patch.object(migrate_from_zero.psycopg, "connect", return_value=conn), mock.patch.object(
            migrate_from_zero.subprocess, "run", return_value=mock.Mock(returncode=0)
        ) as run:
            call_command("migrate_from_zero", "--name", "compliance_watch_e2e", "--keep", stdout=StringIO())
        self.assertEqual(executed.count('DROP DATABASE IF EXISTS "compliance_watch_e2e" WITH (FORCE)'), 1)
        self.assertIn('CREATE DATABASE "compliance_watch_e2e" TEMPLATE template1', executed)
        env = run.call_args.kwargs["env"]
        self.assertEqual(env["DATABASE_URL"], "postgres://cw_migrator:pw@db:5432/compliance_watch_e2e")
        self.assertEqual(env["MIGRATOR_DATABASE_URL"], "postgres://cw_migrator:pw@db:5432/compliance_watch_e2e")
        with mock.patch.object(migrate_from_zero.psycopg, "connect", return_value=conn):
            with self.assertRaises(CommandError):
                call_command("migrate_from_zero", "--name", 'x"; DROP DATABASE postgres; --', stdout=StringIO())


class ScratchNameFollowsTheConfiguredDatabase(SimpleTestCase):
    """Parallel worktrees each get their own database (scripts/worktree.sh). A fixed scratch
    name would let one worktree's `migrate_from_zero` drop another's scratch database in the
    middle of its run, so the default derives from the configured database instead. Added
    2026-09-19 with the worktree workflow."""

    def test_default_scratch_name_is_the_configured_name_plus_scratch(self) -> None:
        self.assertEqual(
            migrate_from_zero.default_scratch_name("postgres://u:p@db:5432/compliance_watch"),
            "compliance_watch_scratch",
        )
        self.assertEqual(
            migrate_from_zero.default_scratch_name("postgres://u:p@db:5432/compliance_watch_wt3"),
            "compliance_watch_wt3_scratch",
        )

    @override_settings(MIGRATOR_DATABASE_URL="postgres://cw_migrator:pw@db:5432/compliance_watch_wt3")
    def test_a_worktree_slot_migrates_its_own_scratch_database(self) -> None:
        executed: list[str] = []
        conn = mock.MagicMock()
        conn.__enter__.return_value.execute.side_effect = lambda sql: executed.append(sql)
        with mock.patch.object(migrate_from_zero.psycopg, "connect", return_value=conn), mock.patch.object(
            migrate_from_zero.subprocess, "run", return_value=mock.Mock(returncode=0)
        ):
            call_command("migrate_from_zero", stdout=StringIO())
        self.assertIn('CREATE DATABASE "compliance_watch_wt3_scratch" TEMPLATE template1', executed)
        self.assertNotIn('CREATE DATABASE "compliance_watch_scratch" TEMPLATE template1', executed)


class ExportOpenApi(SimpleTestCase):
    def test_writes_a_sorted_normalised_document(self) -> None:
        from django.conf import settings

        out = Path(settings.MEDIA_ROOT) / "openapi-test.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        stdout = StringIO()
        call_command("export_openapi", "--out", str(out), stdout=stdout)
        document = json.loads(out.read_text(encoding="utf-8"))
        self.assertIn("/api/v1/me", document["paths"])
        self.assertIn("/api/v1/reference/product", document["paths"])
        self.assertNotIn("servers", document)
        self.assertEqual(document["paths"]["/api/v1/me"]["get"]["responses"]["200"]["description"], "OK")
        self.assertEqual(list(document), sorted(document))
        from apps.shared.routes import iter_operations
        from config.api import api

        self.assertIn(f"{len(list(iter_operations(api)))} operations", stdout.getvalue())
        out.unlink()


class BootstrapPlatformRole(TestCase):
    """`bootstrap_platform --role` (D-14, ADM-02): the owner invites the library editors the
    same way they were invited themselves. The grant itself is audited, which it was not
    before: without a row nobody can tell afterwards who gave a person the console.
    The rest of the command (one-time link, refusal of a live passkey, the platform session
    it leads to) is pinned in apps/identity/tests_policies.py."""

    def _granted(self, email: str) -> list[str]:
        return sorted(
            PlatformRoleAssignment.objects.filter(user__email=email).values_list("role__key", flat=True)
        )

    def _assigned_rows(self, email: str) -> list[AuditEvent]:
        user = User.objects.get(email=email)
        return list(AuditEvent.objects.filter(action="platform_role.assigned", subject_id=user.id).order_by("created"))

    def test_no_role_is_granted_by_default_and_a_named_one_is_audited(self) -> None:
        """Review 2026-11-11 S-15: `--role` has no default, so a run that names none grants
        nothing, and the strongest role is given only when the owner names it."""
        with self.assertRaises(CommandError):
            call_command("bootstrap_platform", "--admin-email", "root@bleqq.test", stdout=StringIO())
        self.assertFalse(User.objects.filter(email="root@bleqq.test").exists())
        call_command("bootstrap_platform", "--admin-email", "root@bleqq.test", "--role", "platform_admin", stdout=StringIO())
        self.assertEqual(self._granted("root@bleqq.test"), ["platform_admin"])
        rows = self._assigned_rows("root@bleqq.test")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].after["role"], "platform_admin")
        self.assertIsNone(rows[0].tenant_id)
        self.assertEqual(rows[0].actor_type, "system")

    def test_role_library_editor_invites_an_editor_and_audits_the_role_key(self) -> None:
        out = StringIO()
        call_command("bootstrap_platform", "--admin-email", "Editor@Bleqq.test", "--role", "library_editor", stdout=out)
        self.assertEqual(self._granted("editor@bleqq.test"), ["library_editor"])
        invitation = Invitation.objects.get(email="editor@bleqq.test", tenant__isnull=True)
        self.assertEqual(invitation.title, "Library editor")
        self.assertIn("/invite#", out.getvalue())
        rows = self._assigned_rows("editor@bleqq.test")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].after["role"], "library_editor")
        self.assertIn("library_editor", rows[0].summary)

    def test_a_second_run_re_invites_without_a_second_grant_row(self) -> None:
        call_command("bootstrap_platform", "--admin-email", "editor@bleqq.test", "--role", "library_editor", stdout=StringIO())
        call_command("bootstrap_platform", "--admin-email", "editor@bleqq.test", "--role", "library_editor", stdout=StringIO())
        self.assertEqual(self._granted("editor@bleqq.test"), ["library_editor"])
        self.assertEqual(len(self._assigned_rows("editor@bleqq.test")), 1, "the grant is recorded when it happens, not on every run")

    def test_a_tenant_role_key_or_an_unknown_key_is_refused_and_nothing_is_written(self) -> None:
        for key in ("admin", "compliance_officer", "librarian"):
            with self.subTest(role=key):
                with self.assertRaises(CommandError):
                    call_command("bootstrap_platform", "--admin-email", "nobody@bleqq.test", "--role", key, stdout=StringIO())
        self.assertFalse(User.objects.filter(email="nobody@bleqq.test").exists())
        self.assertFalse(AuditEvent.objects.filter(action="platform_role.assigned").exists())

    def test_a_bank_member_is_granted_the_role_and_each_of_their_banks_sees_the_grant(self) -> None:
        """D-122: a bank's member may be platform staff too. The grant's row without a tenant
        never showed in the bank's log, so it is written in each bank they are an active
        member of as well, and in no other bank. One partway through re-enrolment holds no
        live passkey and is invited; a deactivated membership's bank is not told."""
        bank = factories.tenant()
        other = factories.tenant()
        left = factories.tenant()
        factories.member(bank, roles=("admin",))
        member = factories.member(bank, user_row=factories.user(email="anna@bank.test")).user
        factories.member(other, user_row=member)
        gone = factories.member(left, user_row=member)
        gone.deactivated_at = gone.created_at
        gone.save(update_fields=["deactivated_at"])
        # Partway through re-enrolment: no live passkey, awaiting enrolment again (a bank no
        # longer re-enrols a member of two banks, review 2026-11-11 S-2; the state is the same).
        WebAuthnCredential.objects.filter(pk=factories.passkey(member).pk).update(retired_at=gone.created_at)
        User.objects.filter(pk=member.pk).update(status="invited")
        tenancy.clear_tenant()  # the owner's shell stands in no bank
        out = StringIO()
        call_command("bootstrap_platform", "--admin-email", "anna@bank.test", "--role", "platform_admin", "--yes", stdout=out)
        self.assertEqual(self._granted("anna@bank.test"), ["platform_admin"])
        self.assertIn("/invite#", out.getvalue())
        self.assertTrue(Invitation.objects.filter(email="anna@bank.test", tenant__isnull=True).exists())
        for zone, expected in ((None, 1), (bank, 1), (other, 1), (left, 0)):
            with self.subTest(zone=zone and zone.slug):
                if zone is None:
                    tenancy.clear_tenant()
                else:
                    tenancy.activate(zone.id)
                rows = [row for row in self._assigned_rows("anna@bank.test") if row.tenant_id == (zone and zone.id)]
                self.assertEqual(len(rows), expected)

    def test_a_second_platform_role_needs_add_role_and_every_role_held_is_printed(self) -> None:
        """Granting platform_admin to a library editor used to happen without a word."""
        out = StringIO()
        call_command("bootstrap_platform", "--admin-email", "editor@bleqq.test", "--role", "library_editor", stdout=out)
        self.assertIn("platform roles: library_editor\n", out.getvalue())
        with self.assertRaisesMessage(CommandError, "--add-role"):
            call_command("bootstrap_platform", "--admin-email", "editor@bleqq.test", "--role", "platform_admin", stdout=StringIO())
        self.assertEqual(self._granted("editor@bleqq.test"), ["library_editor"])
        self.assertEqual(len(self._assigned_rows("editor@bleqq.test")), 1)
        out = StringIO()
        call_command("bootstrap_platform", "--admin-email", "editor@bleqq.test", "--role", "platform_admin", "--add-role", "--yes", stdout=out)
        self.assertEqual(self._granted("editor@bleqq.test"), ["library_editor", "platform_admin"])
        self.assertEqual([row.after["role"] for row in self._assigned_rows("editor@bleqq.test")], ["library_editor", "platform_admin"])
        self.assertIn("platform roles: library_editor, platform_admin\n", out.getvalue())


class BootstrapPlatformReenrol(TestCase):
    """`bootstrap_platform --reenrol` (ID-05) re-enrols platform staff only; the re-enrolment
    itself is ID-S33 in apps/identity/tests_scenarios.py."""

    def test_an_address_without_a_platform_role_is_refused_and_nothing_is_written(self) -> None:
        bank = factories.tenant()
        member = factories.member(bank, user_row=factories.user(email="anna@bank.test")).user
        factories.passkey(member)
        audit_rows = AuditEvent.objects.count()
        for email in ("nobody@bleqq.test", "anna@bank.test"):
            with self.subTest(email=email):
                with self.assertRaisesMessage(CommandError, "holds no platform role and is a member of at most one bank"):
                    call_command("bootstrap_platform", "--admin-email", email, "--reenrol", stdout=StringIO())
        self.assertFalse(User.objects.filter(email="nobody@bleqq.test").exists())
        self.assertTrue(WebAuthnCredential.objects.filter(user=member, retired_at__isnull=True).exists())
        self.assertEqual(AuditEvent.objects.count(), audit_rows)


class BootstrapPlatformConfirmsAndRevokes(TestCase):
    """Review 2026-11-11 S-15: a grant to an account that exists is confirmed after the
    account is printed, a platform role can be taken away with an audit row, and a
    re-enrolment ends the person's personal tokens in each bank as well."""

    def setUp(self) -> None:
        self.bank = factories.tenant()
        self.anna = factories.member(self.bank, user_row=factories.user(email="anna@bank.test", name="Anna Berg")).user
        factories.passkey(self.anna)
        tenancy.clear_tenant()

    def _roles(self) -> list[str]:
        return sorted(PlatformRoleAssignment.objects.filter(user=self.anna).values_list("role__key", flat=True))

    def test_a_grant_to_an_existing_account_without_confirmation_writes_nothing(self) -> None:
        rows = AuditEvent.objects.count()
        out = StringIO()
        with mock.patch("sys.stdin.isatty", return_value=False), self.assertRaisesMessage(CommandError, "--yes"):
            call_command("bootstrap_platform", "--admin-email", "anna@bank.test", "--role", "platform_admin", stdout=out)
        self.assertIn(f"account: Anna Berg <anna@bank.test> ({self.anna.id}), active; banks: {self.bank.name}; platform roles: none", out.getvalue())
        self.assertEqual(self._roles(), [])
        self.assertEqual(AuditEvent.objects.count(), rows)

    def test_an_interactive_answer_confirms_or_refuses_the_grant(self) -> None:
        with mock.patch("sys.stdin.isatty", return_value=True), mock.patch("builtins.input", return_value="n"):
            with self.assertRaisesMessage(CommandError, "Nothing changed."):
                call_command("bootstrap_platform", "--admin-email", "anna@bank.test", "--role", "library_editor", stdout=StringIO())
        self.assertEqual(self._roles(), [])
        with mock.patch("sys.stdin.isatty", return_value=True), mock.patch("builtins.input", return_value="y"):
            call_command("bootstrap_platform", "--admin-email", "anna@bank.test", "--role", "library_editor", stdout=StringIO())
        self.assertEqual(self._roles(), ["library_editor"])

    def test_a_new_address_needs_no_confirmation(self) -> None:
        with mock.patch("sys.stdin.isatty", return_value=False):
            call_command("bootstrap_platform", "--admin-email", "new@bleqq.test", "--role", "library_editor", stdout=StringIO())
        self.assertTrue(PlatformRoleAssignment.objects.filter(user__email="new@bleqq.test").exists())

    def test_revoke_role_removes_the_grant_with_an_audit_row_and_ends_the_console_sessions(self) -> None:
        call_command("bootstrap_platform", "--admin-email", "anna@bank.test", "--role", "library_editor", "--yes", stdout=StringIO())
        tenancy.clear_tenant()
        console = sign_in(self.anna, tenant=None)
        self.assertEqual(self.client.get("/api/v1/me", **console).status_code, 200)
        out = StringIO()
        call_command("bootstrap_platform", "--admin-email", "anna@bank.test", "--revoke-role", "library_editor", "--yes", stdout=out)
        self.assertEqual(self._roles(), [])
        self.assertIn("platform roles: none", out.getvalue())
        tenancy.clear_tenant()
        row = AuditEvent.objects.get(action="platform_role.revoked", subject_id=self.anna.id, tenant__isnull=True)
        self.assertEqual((row.after["role"], row.after["consoleSessionsRevoked"], row.actor_type), ("library_editor", 1, "system"))
        self.assertEqual(self.client.get("/api/v1/me", **console).status_code, 401)
        tenancy.activate(self.bank.id)
        self.assertTrue(AuditEvent.objects.filter(action="platform_role.revoked", subject_id=self.anna.id, tenant=self.bank).exists())
        with self.assertRaisesMessage(CommandError, "does not hold library_editor"):
            call_command("bootstrap_platform", "--admin-email", "anna@bank.test", "--revoke-role", "library_editor", "--yes", stdout=StringIO())

    def test_reenrol_revokes_personal_tokens_and_takes_a_member_of_two_banks(self) -> None:
        """S-2 leaves an account in two banks to the owner's path; it re-enrols it in both."""
        other = factories.tenant()
        factories.member(other, user_row=self.anna)
        token = factories.personal_token(self.bank, person=self.anna)
        tenancy.clear_tenant()
        out = StringIO()
        call_command("bootstrap_platform", "--admin-email", "anna@bank.test", "--reenrol", stdout=out)
        self.assertIn("1 personal token(s) revoked", out.getvalue())
        self.assertFalse(invitation_logic.has_live_passkey(self.anna))
        tenancy.activate(self.bank.id)
        token.row.refresh_from_db()
        self.assertIsNotNone(token.row.revoked_at)
        row = AuditEvent.objects.get(action="platform_staff.enrolment_reissued", subject_id=self.anna.id, tenant=self.bank)
        self.assertEqual(row.after["tokensRevoked"], 1)
