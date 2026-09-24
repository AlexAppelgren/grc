from django.db import migrations

"""taxonomy 0008 (FP-01, FP-03, NFR-02): the footprint rule, split so a list reads the
bank's footprint once per query instead of once per row. The rule is 0006's; only where
each half runs changes.

`taxonomy_footprint_guard(tenant)` reads the tables once: every term of every dimension that
narrows this bank's footprint, each paired with its dimension, and the terms the footprint
names. A dimension narrows it when it is active and restricts (its flag, or kind `opt_in`
whatever the flag says) and, unless it is opt-in, the footprint names a term in it.
`taxonomy_scope_admits(terms, guard terms, guard dimensions, allowed)` is the per-row half
and reads no table: for every guarded dimension the record carries terms in, one of those
terms must be named by the footprint. A list passes the guard as uncorrelated subqueries,
which PostgreSQL runs once per query (an InitPlan), so a list over 3000 obligations reads
the footprint once, not 3000 times.

`taxonomy_in_footprint(tenant, terms)` stays, now the two halves composed, so the surfaces
that decide one record at a time and apps/taxonomy/tests_matching.py, which pins the rule
to the Python mirror, run exactly what the lists run. Every body is frozen here (playbook
4.5); the reverse restores 0006's."""

FORWARD = """
CREATE OR REPLACE FUNCTION taxonomy_footprint_guard(
    p_tenant uuid, OUT terms uuid[], OUT dimensions uuid[], OUT allowed uuid[]
) LANGUAGE sql STABLE AS $$
    SELECT
        coalesce(array_agg(t.id ORDER BY t.id), '{}'),
        coalesce(array_agg(t.dimension_id ORDER BY t.id), '{}'),
        coalesce((SELECT array_agg(f.term_id) FROM footprint_term f WHERE f.tenant_id = p_tenant), '{}')
    FROM term_dimension d
    JOIN taxonomy_term t ON t.dimension_id = d.id
    WHERE d.active AND (d.restricts_footprint OR d.kind = 'opt_in') AND (
        d.kind = 'opt_in' OR EXISTS (
            SELECT 1 FROM footprint_term f
            JOIN taxonomy_term t2 ON t2.id = f.term_id
            WHERE f.tenant_id = p_tenant AND t2.dimension_id = d.id
        )
    )
$$;

-- A loop rather than a grouped subquery: it runs once per row of a list, and measured on
-- 3000 obligations it costs half as much (NFR-02).
CREATE OR REPLACE FUNCTION taxonomy_scope_admits(
    p_terms uuid[], p_guard_terms uuid[], p_guard_dimensions uuid[], p_allowed uuid[]
) RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    term uuid;
    slot int;
    wanting uuid[] := '{}';  -- guarded dimensions the record carries terms in
    met uuid[] := '{}';      -- those among them where the footprint names one of its terms
BEGIN
    FOREACH term IN ARRAY coalesce(p_terms, '{}') LOOP
        slot := array_position(p_guard_terms, term);
        CONTINUE WHEN slot IS NULL;
        wanting := wanting || p_guard_dimensions[slot];
        IF term = ANY(p_allowed) THEN
            met := met || p_guard_dimensions[slot];
        END IF;
    END LOOP;
    RETURN wanting <@ met;
END
$$;

CREATE OR REPLACE FUNCTION taxonomy_in_footprint(p_tenant uuid, p_terms uuid[]) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT taxonomy_scope_admits(p_terms, g.terms, g.dimensions, g.allowed)
    FROM taxonomy_footprint_guard(p_tenant) AS g
$$;
"""

# 0006's body, restored on the way back, and the two halves dropped after it.
REVERSE = """
CREATE OR REPLACE FUNCTION taxonomy_in_footprint(p_tenant uuid, p_terms uuid[]) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT NOT EXISTS (
        SELECT 1
        FROM (
            SELECT t.dimension_id, bool_or(f.id IS NOT NULL) AS hit
            FROM unnest(p_terms) AS wanted(term_id)
            JOIN taxonomy_term t ON t.id = wanted.term_id
            JOIN term_dimension d ON d.id = t.dimension_id AND (d.restricts_footprint OR d.kind = 'opt_in') AND d.active
            LEFT JOIN footprint_term f ON f.term_id = t.id AND f.tenant_id = p_tenant
            WHERE d.kind = 'opt_in' OR EXISTS (
                SELECT 1 FROM footprint_term f2
                JOIN taxonomy_term t2 ON t2.id = f2.term_id
                WHERE f2.tenant_id = p_tenant AND t2.dimension_id = t.dimension_id
            )
            GROUP BY t.dimension_id
        ) per_dimension
        WHERE NOT per_dimension.hit
    )
$$;
DROP FUNCTION IF EXISTS taxonomy_scope_admits(uuid[], uuid[], uuid[], uuid[]);
DROP FUNCTION IF EXISTS taxonomy_footprint_guard(uuid);
"""


class Migration(migrations.Migration):

    dependencies = [
        ("taxonomy", "0007_list_and_term_provenance"),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE),
    ]
