from django.db import migrations

"""taxonomy 0006 (FP-01, D-36, AC-FP3): `taxonomy_in_footprint` learns opt-in dimensions,
the SQL twin of the rule apps/taxonomy/matching.in_footprint() now applies. A dimension of
kind `opt_in` (the standards a bank follows) restricts whatever its `restricts_footprint`
flag says, and it restricts even when the footprint names no term in it: a record carrying
one of its terms matches only when the footprint names that term. Every other dimension
keeps 0001's rule. The kind itself needs no schema change, because a vocabulary's `kind`
column carries no database choices.

Both bodies are frozen here on purpose (playbook 4.5: a migration declares what its
operations need inline): the forward one below, and the reverse one, which is 0001's text
word for word. apps/taxonomy/tests_matching.py pins the forward body to the Python rule."""

# As 0001, with two changes: the dimension join admits an opt-in dimension whatever its
# flag, and an opt-in dimension skips the "the footprint has a term in it" test, so an
# empty opt-in group in the footprint hides every record that carries one of its terms.
IN_FOOTPRINT_FUNCTION = """
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
"""

# 0001's body, restored on the way back.
IN_FOOTPRINT_FUNCTION_0001 = """
CREATE OR REPLACE FUNCTION taxonomy_in_footprint(p_tenant uuid, p_terms uuid[]) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT NOT EXISTS (
        SELECT 1
        FROM (
            SELECT t.dimension_id, bool_or(f.id IS NOT NULL) AS hit
            FROM unnest(p_terms) AS wanted(term_id)
            JOIN taxonomy_term t ON t.id = wanted.term_id
            JOIN term_dimension d ON d.id = t.dimension_id AND d.restricts_footprint AND d.active
            LEFT JOIN footprint_term f ON f.term_id = t.id AND f.tenant_id = p_tenant
            WHERE EXISTS (
                SELECT 1 FROM footprint_term f2
                JOIN taxonomy_term t2 ON t2.id = f2.term_id
                WHERE f2.tenant_id = p_tenant AND t2.dimension_id = t.dimension_id
            )
            GROUP BY t.dimension_id
        ) per_dimension
        WHERE NOT per_dimension.hit
    )
$$;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('taxonomy', '0005_term_jurisdiction'),
    ]

    operations = [
        migrations.RunSQL(sql=IN_FOOTPRINT_FUNCTION, reverse_sql=IN_FOOTPRINT_FUNCTION_0001),
    ]
