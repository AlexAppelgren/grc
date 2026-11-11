"""Review 2026-11-11 B-13: `migrate` refuses a database where a squashed migration is partly
applied, which Django would otherwise skip without a word, leaving the rest of that squash
unbuilt on a deployed database.

Proven to fail 2026-11-11 with the check unregistered: the second test fails, and `migrate`
on a copy of a database built by the pre-squash files with `library 0012` (the private-child
policies) unrecorded reported "No migrations to apply"; with it, `migrate` stops at shared.E001."""

from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import SystemCheckError
from django.db import DEFAULT_DB_ALIAS, connection
from django.db.migrations.recorder import MigrationRecorder
from django.test import TestCase

from apps.shared.migration_guard import squashes_applied_whole

SQUASH = "taxonomy.0002_squashed_0014_links_and_rules"
REPLACED = ("taxonomy", "0014_footprint_sole_approver")


class PartlyAppliedSquash(TestCase):
    def test_a_database_built_from_the_squashes_passes(self) -> None:
        self.assertEqual(squashes_applied_whole(app_configs=None, databases=[DEFAULT_DB_ALIAS]), [])

    def test_a_squash_missing_one_replaced_migration_is_refused_by_name(self) -> None:
        MigrationRecorder(connection).record_unapplied(*REPLACED)
        errors = squashes_applied_whole(app_configs=None, databases=[DEFAULT_DB_ALIAS])
        self.assertEqual([error.id for error in errors], ["shared.E001"])
        self.assertIn(SQUASH, errors[0].msg)
        self.assertIn("taxonomy.0014_footprint_sole_approver", errors[0].msg)
        with self.assertRaises(SystemCheckError):
            call_command("migrate", "--plan", verbosity=0, skip_checks=False)
