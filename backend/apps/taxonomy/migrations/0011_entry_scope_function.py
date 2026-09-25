from django.db import migrations

"""taxonomy 0011 (acc-scope-and-reach; ACC-02, D-70, AC-ACC1): an agent access entry's scope,
derived per request and never stored, and FP-01's rule run over any term map.

`taxonomy_term_map_guard(allowed)` is `taxonomy_footprint_guard` (0008) with the footprint
handed in as a term set instead of read from `footprint_term`: every term of every dimension
that narrows it (active, restricting or opt-in, and unless opt-in, holding a term of the
set), paired with its dimension, and the set itself. With `taxonomy_scope_admits` it is the
same rule over any term map, so an empty dimension does not restrict and an opt-in one
matches only what the map names.

`taxonomy_entry_scope(tenant, entry)` derives the entry's terms: the terms of the products it
names and of the products under each department it names and every unit below it, then
intersects them with the tenant's footprint. A retired product or a deactivated unit derives
nothing. `narrowed` says whether the entry names any department or product; an entry that
names none takes the whole footprint, so both run the same code. An entry this session
cannot see, or one that was revoked, counts as narrowed to nothing, so an unknown id fails
closed rather than reading the whole footprint. Nothing here reads a term
from the caller: the entry's own rows and the footprint table are the only inputs, and the
intersection makes "only narrows" the database's property. Both functions are SECURITY
INVOKER, so they read under row-level security like every query of the app role.

`taxonomy_entry_admits(tenant, entry, terms)` is the verdict on one record: the footprint's
rule and then the same rule against the entry's terms. An entry that names departments or
products deriving no term reads nothing at all (`narrowed` with an empty set). The reverse
drops the three functions."""

FORWARD = """
CREATE OR REPLACE FUNCTION taxonomy_term_map_guard(
    p_allowed uuid[], OUT terms uuid[], OUT dimensions uuid[], OUT allowed uuid[]
) LANGUAGE sql STABLE AS $$
    SELECT
        coalesce(array_agg(t.id ORDER BY t.id), '{}'),
        coalesce(array_agg(t.dimension_id ORDER BY t.id), '{}'),
        coalesce(p_allowed, '{}')
    FROM term_dimension d
    JOIN taxonomy_term t ON t.dimension_id = d.id
    WHERE d.active AND (d.restricts_footprint OR d.kind = 'opt_in') AND (
        d.kind = 'opt_in' OR EXISTS (
            SELECT 1 FROM taxonomy_term t2 WHERE t2.id = ANY(p_allowed) AND t2.dimension_id = d.id
        )
    )
$$;

CREATE OR REPLACE FUNCTION taxonomy_entry_scope(
    p_tenant uuid, p_entry uuid, OUT narrowed boolean, OUT terms uuid[]
) LANGUAGE sql STABLE AS $$
    WITH RECURSIVE units AS (
        SELECT u.id
        FROM agent_access_department ad
        JOIN org_unit u ON u.id = ad.department_id AND u.tenant_id = p_tenant AND u.active
        WHERE ad.tenant_id = p_tenant AND ad.agent_access_id = p_entry
        UNION
        SELECT c.id FROM org_unit c JOIN units ON c.parent_id = units.id
        WHERE c.tenant_id = p_tenant AND c.active
    ),
    products AS (
        SELECT p.id FROM tenant_product p
        WHERE p.tenant_id = p_tenant AND p.status <> 'retired' AND (
            p.org_unit_id IN (SELECT id FROM units)
            OR p.id IN (
                SELECT ap.product_id FROM agent_access_product ap
                WHERE ap.tenant_id = p_tenant AND ap.agent_access_id = p_entry
            )
        )
    ),
    named AS (
        SELECT NOT EXISTS (
            SELECT 1 FROM agent_access a WHERE a.tenant_id = p_tenant AND a.id = p_entry AND a.active
        ) OR EXISTS (
            SELECT 1 FROM agent_access_department ad WHERE ad.tenant_id = p_tenant AND ad.agent_access_id = p_entry
        ) OR EXISTS (
            SELECT 1 FROM agent_access_product ap WHERE ap.tenant_id = p_tenant AND ap.agent_access_id = p_entry
        ) AS any_named
    )
    SELECT
        named.any_named,
        coalesce((
            SELECT array_agg(f.term_id ORDER BY f.term_id) FROM footprint_term f
            WHERE f.tenant_id = p_tenant AND (
                NOT named.any_named OR f.term_id IN (
                    SELECT pt.term_id FROM tenant_product_term pt
                    WHERE pt.tenant_id = p_tenant AND pt.product_id IN (SELECT id FROM products)
                )
            )
        ), '{}')
    FROM named
$$;

CREATE OR REPLACE FUNCTION taxonomy_entry_admits(p_tenant uuid, p_entry uuid, p_terms uuid[]) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT taxonomy_in_footprint(p_tenant, p_terms)
        AND NOT (s.narrowed AND cardinality(s.terms) = 0)
        AND taxonomy_scope_admits(p_terms, g.terms, g.dimensions, g.allowed)
    FROM taxonomy_entry_scope(p_tenant, p_entry) AS s, taxonomy_term_map_guard(s.terms) AS g
$$;
"""

REVERSE = """
DROP FUNCTION IF EXISTS taxonomy_entry_admits(uuid, uuid, uuid[]);
DROP FUNCTION IF EXISTS taxonomy_entry_scope(uuid, uuid);
DROP FUNCTION IF EXISTS taxonomy_term_map_guard(uuid[]);
"""


class Migration(migrations.Migration):

    dependencies = [
        ("taxonomy", "0010_team_org_unit"),
        ("agents", "0006_agent_access"),
        ("tenants", "0003_team_member"),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE),
    ]
