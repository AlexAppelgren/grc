"""shared 0010 (ADM-02, VOC-07, PRO-01, ADR 0058, D-94 amending D-83): the proposal door opens
on `jurisdiction` and `jurisdiction_label`.

Shared 0008 held both behind the seed door alone, because no proposal wrote them. A
jurisdiction is now relabelled, retired and restored through an approved proposal
(apps/proposals/apply.py), and the approval writes the row and its labels inside
`library_write(door="proposal")`, so both tables take the doors every library vocabulary
takes: an approved proposal or a reference seed. The seed door stays, because the reference
seed still files the rows. `language` keeps the seed door alone: no proposal writes a language.

Each trigger is dropped and attached again with the new arguments, in one migration so no
moment passes with either table unguarded; reversing puts the seed door back alone."""

from django.db import migrations

from apps.shared.migration_helpers import INVENTORY_DOORS, REFERENCE_DOORS, library_door_trigger_operations

TABLES = ("jurisdiction", "jurisdiction_label")


def _reattached(table: str, doors: tuple[str, ...], was: tuple[str, ...]) -> list[migrations.RunSQL]:
    """Drop `table`'s door trigger and attach it again accepting `doors`; the reverse
    attaches it again accepting `was`."""
    attach, restore = library_door_trigger_operations(table, doors)[0], library_door_trigger_operations(table, was)[0]
    drop = f'DROP TRIGGER IF EXISTS {table}_library_door ON "{table}"'
    return [migrations.RunSQL(sql=[drop, attach.sql], reverse_sql=[drop, restore.sql])]


class Migration(migrations.Migration):
    dependencies = [
        ("shared", "0009_tenant_workflow_policy"),
        ("library", "0011_jurisdiction_provenance"),
    ]

    operations = [operation for table in TABLES for operation in _reattached(table, INVENTORY_DOORS, REFERENCE_DOORS)]
