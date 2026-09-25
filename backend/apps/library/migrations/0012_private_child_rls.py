"""library 0012 (INV-07, OWN-04, D-57, D-89; ADR 0050 tranche 2; hardening H7's private half):
a child of an instrument or an obligation lives in its parent's zone.

`instrument` and `obligation` carry `owner_tenant_id`: NULL for the shared library, a bank for
that bank's own record. Their children — titles, versions, summaries, provisions and their
texts, terms, tags, relations, recurring duties and a change's coverage row — hold no zone
column of their own, so until now a child was hidden only because every read reached it
through its parent. Now the database says so. Each child gets forced row-level security and
two policies:

- `parent_visible`, FOR SELECT: the parent is visible, which is the parent's own policy asked
  through a subquery, so a child reads exactly as far as its parent does (a grandchild asks its
  own parent, which asks the root).
- `parent_owned`, FOR ALL: the root's `owner_tenant_id` is the session's own zone — the bank
  that is active, or the shared library for a session with no bank. So a bank cannot insert,
  change or delete a child under a shared parent or under another bank's parent, and a platform
  session cannot write under a bank's.

A link row has an owning end and a referenced end: a relation is its `from_` record's, a
provision link its obligation's, a coverage row its obligation's. The owning end decides the
write, and the referenced end must also be visible, for the write and for the read, so a
bank's link from its own record to a shared one stays its own and no bank reads a link to a
record it cannot see.

`change_obligation` is the watch coverage row of a change and an obligation. Only its
obligation parent is written here: `regulatory_change` holds no zone yet, and the package that
gives it one (c13-private-child-rls) replaces these two policies with one pair naming both
parents, because two permissive FOR ALL policies would OR together. The RLS guard pins the
exact pair per table, so a second pair beside this one fails it.

The library door trigger (shared 0008, ADR 0058) runs before any of this, per statement: a
write outside a door is refused whatever zone it names. These policies decide which rows a
write inside a door may touch, which the door alone never did.

One trigger of library 0008 read `provision` as a table every zone sees whole:
`instrument_level_kind_not_standard_with_provisions`, which refuses giving a level the kind
`standard` while a provision sits under an instrument at that level (D-35). A bank's own
provisions are now hidden from every other zone, the reference seed's included, so the
function is replaced by one that asks each zone in turn — the shared library's and every
bank's — and puts the session's own zone back before it answers. Its sibling on
`instrument.level_id` is unchanged: whoever moves an instrument sees that instrument, and so
its provisions.
"""

from django.db import migrations

from apps.shared.migration_helpers import TENANT_EXPRESSION, TENANT_SETTING

READ_POLICY = "parent_visible"
WRITE_POLICY = "parent_owned"

# child: (the path from the child to its root, each hop a column and the table it names;
#         the referenced ends that must also be visible, each a column and its table)
CHILDREN: dict[str, tuple[list[tuple[str, str]], list[tuple[str, str]]]] = {
    "instrument_title": ([("instrument_id", "instrument")], []),
    "instrument_relation": ([("from_instrument_id", "instrument")], [("to_instrument_id", "instrument")]),
    "provision": ([("instrument_id", "instrument")], []),
    "provision_version": ([("provision_id", "provision"), ("instrument_id", "instrument")], []),
    "provision_text": (
        [("version_id", "provision_version"), ("provision_id", "provision"), ("instrument_id", "instrument")],
        [],
    ),
    "obligation_title": ([("obligation_id", "obligation")], []),
    "obligation_version": ([("obligation_id", "obligation")], []),
    "obligation_summary": ([("version_id", "obligation_version"), ("obligation_id", "obligation")], []),
    "obligation_provision": ([("obligation_id", "obligation")], [("provision_id", "provision")]),
    "obligation_term": ([("obligation_id", "obligation")], []),
    "obligation_tag": ([("obligation_id", "obligation")], []),
    "obligation_relation": ([("from_obligation_id", "obligation")], [("to_obligation_id", "obligation")]),
    "recurring_duty": ([("obligation_id", "obligation")], []),
    "change_obligation": ([("obligation_id", "obligation")], []),
}


def _exists(child: str, column: str, parent: str, *, owned: list[tuple[str, str]] | None = None) -> str:
    """`EXISTS` the row of `parent` that `child.column` names, visible under its own policy.
    With `owned`, the rest of the path is joined to the root and the root must be the
    session's own zone."""
    joins = ""
    where = f'p0.id = "{child}"."{column}"'
    if owned is not None:
        for depth, (hop_column, hop_table) in enumerate(owned, start=1):
            joins += f' JOIN "{hop_table}" p{depth} ON p{depth}.id = p{depth - 1}."{hop_column}"'
        where += f" AND p{len(owned)}.owner_tenant_id IS NOT DISTINCT FROM {TENANT_EXPRESSION}"
    return f'EXISTS (SELECT 1 FROM "{parent}" p0{joins} WHERE {where})'


def _rules(child: str) -> tuple[str, str]:
    """The read rule and the write rule of `child`."""
    path, references = CHILDREN[child]
    (column, parent), rest = path[0], path[1:]
    seen = [_exists(child, ref_column, ref_table) for ref_column, ref_table in references]
    read = " AND ".join([_exists(child, column, parent), *seen])
    write = " AND ".join([_exists(child, column, parent, owned=rest), *seen])
    return read, write


def _operations(child: str) -> list[migrations.RunSQL]:
    read, write = _rules(child)
    return [
        migrations.RunSQL(
            sql=f'ALTER TABLE "{child}" ENABLE ROW LEVEL SECURITY',
            reverse_sql=f'ALTER TABLE "{child}" DISABLE ROW LEVEL SECURITY',
        ),
        migrations.RunSQL(
            sql=f'ALTER TABLE "{child}" FORCE ROW LEVEL SECURITY',
            reverse_sql=f'ALTER TABLE "{child}" NO FORCE ROW LEVEL SECURITY',
        ),
        migrations.RunSQL(
            sql=f'CREATE POLICY {READ_POLICY} ON "{child}" FOR SELECT USING ({read})',
            reverse_sql=f'DROP POLICY IF EXISTS {READ_POLICY} ON "{child}"',
        ),
        migrations.RunSQL(
            sql=f'CREATE POLICY {WRITE_POLICY} ON "{child}" FOR ALL USING ({write}) WITH CHECK ({write})',
            reverse_sql=f'DROP POLICY IF EXISTS {WRITE_POLICY} ON "{child}"',
        ),
    ]


LEVEL_KIND_FUNCTION = "cw_instrument_level_kind_not_standard_with_provisions"
REFUSED = "USING ERRCODE = 'check_violation', CONSTRAINT = 'provision_not_under_standard'"

LEVEL_KIND_EVERY_ZONE = f"""
CREATE OR REPLACE FUNCTION {LEVEL_KIND_FUNCTION}() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    own_zone text := coalesce(current_setting('{TENANT_SETTING}', true), '');
    zone uuid;
    held boolean := false;
BEGIN
    IF NEW.kind = 'standard' AND OLD.kind IS DISTINCT FROM 'standard' THEN
        FOR zone IN SELECT NULL::uuid UNION ALL SELECT id FROM tenant LOOP
            PERFORM set_config('{TENANT_SETTING}', coalesce(zone::text, ''), true);
            held := EXISTS (
                SELECT 1 FROM provision JOIN instrument ON instrument.id = provision.instrument_id
                WHERE instrument.level_id = NEW.id
            );
            EXIT WHEN held;
        END LOOP;
        PERFORM set_config('{TENANT_SETTING}', own_zone, true);
        IF held THEN
            RAISE EXCEPTION 'provision_not_under_standard: level % refused the kind standard, because provisions sit under it', NEW.key
                {REFUSED};
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
"""

# library 0008's own body, put back on a reverse.
LEVEL_KIND_ONE_ZONE = f"""
CREATE OR REPLACE FUNCTION {LEVEL_KIND_FUNCTION}() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.kind = 'standard' AND OLD.kind IS DISTINCT FROM 'standard' AND EXISTS (
        SELECT 1
        FROM provision
        LEFT JOIN instrument ON instrument.id = provision.instrument_id
        WHERE instrument.id IS NULL OR instrument.level_id = NEW.id
    ) THEN
        RAISE EXCEPTION 'provision_not_under_standard: level % refused the kind standard, because provisions sit under it or under an instrument not visible from this zone', NEW.key
            {REFUSED};
    END IF;
    RETURN NEW;
END;
$$;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0011_jurisdiction_provenance"),
        ("watch", "0002_curation_confirmation"),
    ]

    operations = [
        *(operation for child in CHILDREN for operation in _operations(child)),
        migrations.RunSQL(sql=LEVEL_KIND_EVERY_ZONE, reverse_sql=LEVEL_KIND_ONE_ZONE),
    ]
