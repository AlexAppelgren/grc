"""taxonomy, squashed (review 2026-11-11 B-13): taxonomy's links to other apps' tables and
the rules that read them.

- Four eyes on the footprint (FP-02, playbook 4.2): the requester never decides, with one
  temporary exception, a bank's only `footprint.approve` holder approving their own request
  (D-125), marked on the row. 0015, kept after this squash, narrows the exception. Stated in SQL because Django spells "not equal" as
  NOT (a = b AND a IS NOT NULL), and the four-eyes guard reads the definition back from
  pg_constraint (apps/shared/tests_four_eyes.py).
- A team, an entity exclusion, an entity term and a history row name an organisation unit
  of their own bank, through composite `(tenant_id, org_unit_id)` keys (TEN-03, D-91).
- An agent access entry's scope, derived per request and never stored (ACC-02, D-70,
  AC-ACC1): `taxonomy_term_map_guard(allowed)` is the footprint guard over any term set,
  `taxonomy_entry_scope(tenant, entry)` derives the entry's terms from its products and the
  products under its departments, intersected with the footprint (an entry this session
  cannot see, or a revoked one, is narrowed to nothing), and `taxonomy_entry_admits(...)` is
  the verdict on one record. All SECURITY INVOKER, reading under row-level security."""

import django.db.models.deletion
from django.db import migrations, models

from apps.shared.migration_helpers import same_tenant_key

FOUR_EYES = "footprint_change_request_four_eyes"

# (table, column, target table, target column)
COMPOSITE_KEYS = (
    ("team", "org_unit_id", "org_unit", "id"),
    ("footprint_history", "org_unit_id", "org_unit", "id"),
    ("entity_scope_exclusion", "org_unit_id", "org_unit", "id"),
    ("footprint_change_entity_term", "org_unit_id", "org_unit", "id"),
)

ENTRY_SCOPE_FUNCTIONS = """
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

DROP_ENTRY_SCOPE_FUNCTIONS = """
DROP FUNCTION IF EXISTS taxonomy_entry_admits(uuid, uuid, uuid[]);
DROP FUNCTION IF EXISTS taxonomy_entry_scope(uuid, uuid);
DROP FUNCTION IF EXISTS taxonomy_term_map_guard(uuid[]);
"""


class Migration(migrations.Migration):

    replaces = [
        ('taxonomy', '0002_rejection_reason'),
        ('taxonomy', '0003_one_pending_request'),
        ('taxonomy', '0004_watched_market'),
        ('taxonomy', '0005_term_jurisdiction'),
        ('taxonomy', '0006_opt_in_footprint'),
        ('taxonomy', '0007_list_and_term_provenance'),
        ('taxonomy', '0008_set_based_footprint'),
        ('taxonomy', '0009_register_lists'),
        ('taxonomy', '0010_team_org_unit'),
        ('taxonomy', '0011_entry_scope_function'),
        ('taxonomy', '0012_scope_items'),
        ('taxonomy', '0013_entity_scope'),
        ('taxonomy', '0014_footprint_sole_approver'),
    ]

    dependencies = [
        ('agents', '0001_squashed_0001_tables'),
        ('agents', '0002_squashed_0009_links_and_rules'),
        ('identity', '0001_squashed_0001_tables'),
        ('library', '0001_squashed_0001_tables'),
        ('proposals', '0001_squashed_0001_tables'),
        ('taxonomy', '0001_squashed_0001_tables'),
        ('tenants', '0001_squashed_0001_tables'),
        ('tenants', '0002_squashed_0006_links_and_rules'),
    ]

    operations = [
        migrations.AddField(
            model_name='changetype',
            name='applied_by_proposal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='proposals.proposal'),
        ),
        migrations.AddField(
            model_name='changetype',
            name='verified_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='dutytype',
            name='applied_by_proposal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='proposals.proposal'),
        ),
        migrations.AddField(
            model_name='dutytype',
            name='verified_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='entityscopeexclusion',
            name='added_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='entityscopeexclusion',
            name='org_unit',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='scope_exclusions', to='tenants.orgunit'),
        ),
        migrations.AddField(
            model_name='flag',
            name='applied_by_proposal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='proposals.proposal'),
        ),
        migrations.AddField(
            model_name='flag',
            name='verified_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='footprintchangeentityterm',
            name='org_unit',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='tenants.orgunit'),
        ),
        migrations.AddField(
            model_name='footprintchangerequest',
            name='decided_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='footprintchangerequest',
            name='requested_by',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='footprinthistory',
            name='changed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='footprinthistory',
            name='org_unit',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='tenants.orgunit'),
        ),
        migrations.AddField(
            model_name='footprintterm',
            name='added_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='instrumentlevel',
            name='applied_by_proposal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='proposals.proposal'),
        ),
        migrations.AddField(
            model_name='instrumentlevel',
            name='verified_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='librarytag',
            name='applied_by_proposal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='proposals.proposal'),
        ),
        migrations.AddField(
            model_name='librarytag',
            name='verified_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='provisionkind',
            name='applied_by_proposal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='proposals.proposal'),
        ),
        migrations.AddField(
            model_name='provisionkind',
            name='jurisdiction',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.jurisdiction'),
        ),
        migrations.AddField(
            model_name='provisionkind',
            name='verified_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='rejectionreason',
            name='applied_by_proposal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='proposals.proposal'),
        ),
        migrations.AddField(
            model_name='rejectionreason',
            name='verified_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='relationtype',
            name='applied_by_proposal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='proposals.proposal'),
        ),
        migrations.AddField(
            model_name='relationtype',
            name='verified_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='scopeitem',
            name='jurisdiction',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.jurisdiction'),
        ),
        migrations.AddField(
            model_name='sourcekind',
            name='applied_by_proposal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='proposals.proposal'),
        ),
        migrations.AddField(
            model_name='sourcekind',
            name='verified_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='taxonomyterm',
            name='applied_by_proposal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='proposals.proposal'),
        ),
        migrations.AddField(
            model_name='taxonomyterm',
            name='jurisdiction',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.jurisdiction'),
        ),
        migrations.AddField(
            model_name='taxonomyterm',
            name='verified_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='team',
            name='org_unit',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='teams', to='tenants.orgunit'),
        ),
        migrations.AddField(
            model_name='termdimension',
            name='applied_by_proposal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='proposals.proposal'),
        ),
        migrations.AddField(
            model_name='termdimension',
            name='verified_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='urgency',
            name='applied_by_proposal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='proposals.proposal'),
        ),
        migrations.AddField(
            model_name='urgency',
            name='verified_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='vocabularysuggestion',
            name='suggested_by',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='watchedmarket',
            name='added_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='watchedmarket',
            name='jurisdiction',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.jurisdiction'),
        ),
        migrations.AddConstraint(
            model_name='footprintchangeentityterm',
            constraint=models.UniqueConstraint(fields=('request', 'org_unit', 'term'), name='footprint_change_entity_term_unique'),
        ),
        migrations.AddConstraint(
            model_name='entityscopeexclusion',
            constraint=models.UniqueConstraint(fields=('org_unit', 'term'), name='entity_scope_exclusion_unique'),
        ),
        migrations.AddConstraint(
            model_name='watchedmarket',
            constraint=models.UniqueConstraint(fields=('tenant', 'jurisdiction'), name='watched_market_unique'),
        ),
        migrations.RunSQL(
            sql=(
                f'ALTER TABLE "footprint_change_request" ADD CONSTRAINT {FOUR_EYES} '
                "CHECK (decided_by_id IS NULL OR decided_by_id <> requested_by_id OR sole_approver)"
            ),
            reverse_sql=f'ALTER TABLE "footprint_change_request" DROP CONSTRAINT IF EXISTS {FOUR_EYES}',
        ),
        *[same_tenant_key(*key) for key in COMPOSITE_KEYS],
        migrations.RunSQL(sql=ENTRY_SCOPE_FUNCTIONS, reverse_sql=DROP_ENTRY_SCOPE_FUNCTIONS),
    ]
