"""tenants, squashed (review 2026-11-11 B-13): tenants' links to other apps' tables and the
rules that read them.

- A head, an owner, an updater, a support approver, whoever ended a grant, a team member
  and whoever started a register lookup are members of the same bank, through composite
  keys into `membership (tenant_id, user_id)`; an owning team and an internal item's link
  kind are the bank's own (TEN-02, TEN-03, TEN-06, TEN-07).
- A legal entity's term comes from the `legal_entity` dimension, which a trigger checks
  because a CHECK cannot read another table.
- A platform person reads the support grants that name them, keyed on
  `app.platform_user_id`, before any bank is active (ADR 0042); `tests_rls.OTHER_POLICIES`
  pins the policy."""

import django.db.models.deletion
from django.db import migrations, models

from apps.shared.migration_helpers import same_tenant_key

OWN_GRANTS_POLICY = "support_access_own_grants"
PLATFORM_USER_EXPRESSION = "NULLIF(current_setting('app.platform_user_id', true), '')::uuid"

# (table, column, target table, target column)
COMPOSITE_KEYS = (
    ("org_unit", "head_user_id", "membership", "user_id"),
    ("licence", "owner_user_id", "membership", "user_id"),
    ("licence", "owner_team_id", "team", "id"),
    ("tenant_product", "owner_user_id", "membership", "user_id"),
    ("internal_item", "kind_id", "link_kind", "id"),
    ("internal_item", "owner_user_id", "membership", "user_id"),
    ("internal_item", "owner_team_id", "team", "id"),
    ("security_policy", "updated_by_id", "membership", "user_id"),
    ("team_member", "team_id", "team", "id"),
    ("team_member", "user_id", "membership", "user_id"),
    ("support_access", "approved_by_id", "membership", "user_id"),
    ("support_access", "ended_by_id", "membership", "user_id"),
    ("register_lookup", "requested_by_id", "membership", "user_id"),
)

ENTITY_TERM_GUARD_SQL = """
CREATE FUNCTION cw_org_unit_entity_term_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.entity_term_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM taxonomy_term t JOIN term_dimension d ON d.id = t.dimension_id
        WHERE t.id = NEW.entity_term_id AND d.key = 'legal_entity'
    ) THEN
        RAISE EXCEPTION 'org_unit.entity_term must be a term of the legal_entity dimension'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER org_unit_entity_term_guard BEFORE INSERT OR UPDATE OF entity_term_id ON org_unit
    FOR EACH ROW EXECUTE FUNCTION cw_org_unit_entity_term_guard();
"""
ENTITY_TERM_GUARD_REVERSE_SQL = """
DROP TRIGGER IF EXISTS org_unit_entity_term_guard ON org_unit;
DROP FUNCTION IF EXISTS cw_org_unit_entity_term_guard();
"""


class Migration(migrations.Migration):

    replaces = [
        ('tenants', '0002_organisation'),
        ('tenants', '0003_team_member'),
        ('tenants', '0004_support_grants'),
        ('tenants', '0005_licence_product_version'),
        ('tenants', '0006_register_lookup_entry'),
    ]

    dependencies = [
        ('identity', '0001_squashed_0001_tables'),
        ('library', '0001_squashed_0001_tables'),
        ('taxonomy', '0001_squashed_0001_tables'),
        ('tenants', '0001_squashed_0001_tables'),
    ]

    operations = [
        migrations.AddField(
            model_name='orgunit',
            name='entity_term',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.taxonomyterm'),
        ),
        migrations.AddField(
            model_name='orgunit',
            name='head_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='licence',
            name='authority',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.authority'),
        ),
        migrations.AddField(
            model_name='licence',
            name='licence_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.taxonomyterm'),
        ),
        migrations.AddField(
            model_name='licence',
            name='owner_team',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.team'),
        ),
        migrations.AddField(
            model_name='licence',
            name='owner_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='internalitem',
            name='kind',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.linkkind'),
        ),
        migrations.AddField(
            model_name='internalitem',
            name='owner_team',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.team'),
        ),
        migrations.AddField(
            model_name='internalitem',
            name='owner_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='registerentry',
            name='authority',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='library.authority'),
        ),
        migrations.AddField(
            model_name='registerlookup',
            name='requested_by',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='securitypolicy',
            name='updated_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='supportaccess',
            name='approved_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='supportaccess',
            name='ended_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='supportaccess',
            name='platform_user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='support_accesses', to='identity.user'),
        ),
        migrations.AddField(
            model_name='teammember',
            name='team',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='members', to='taxonomy.team'),
        ),
        migrations.AddField(
            model_name='teammember',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='tenantproduct',
            name='owner_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='tenantproductterm',
            name='term',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.taxonomyterm'),
        ),
        migrations.AddField(
            model_name='licenceserviceterm',
            name='term',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.taxonomyterm'),
        ),
        migrations.AddConstraint(
            model_name='licenceserviceterm',
            constraint=models.UniqueConstraint(fields=('licence', 'term'), name='licence_service_term_unique'),
        ),
        migrations.AddConstraint(
            model_name='orgunit',
            constraint=models.CheckConstraint(condition=models.Q(('entity_term__isnull', True), ('kind', 'legal_entity'), _connector='OR'), name='org_unit_entity_term_on_legal_entity'),
        ),
        migrations.AddConstraint(
            model_name='licence',
            constraint=models.CheckConstraint(condition=models.Q(('owner_user__isnull', True), ('owner_team__isnull', True), _connector='OR'), name='licence_one_owner'),
        ),
        migrations.AddConstraint(
            model_name='internalitem',
            constraint=models.UniqueConstraint(fields=('tenant', 'kind', 'name'), name='internal_item_kind_name_unique'),
        ),
        migrations.AddConstraint(
            model_name='internalitem',
            constraint=models.CheckConstraint(condition=models.Q(('owner_user__isnull', True), ('owner_team__isnull', True), _connector='OR'), name='internal_item_one_owner'),
        ),
        migrations.AddConstraint(
            model_name='registerentry',
            constraint=models.UniqueConstraint(fields=('org_unit', 'authority'), name='register_entry_unique'),
        ),
        migrations.AddConstraint(
            model_name='supportaccess',
            constraint=models.CheckConstraint(condition=models.Q(('approved_by__isnull', True), models.Q(('approved_by', models.F('platform_user')), _negated=True), _connector='OR'), name='support_access_approver_is_not_the_requester'),
        ),
        migrations.AddConstraint(
            model_name='supportaccess',
            constraint=models.CheckConstraint(condition=models.Q(('access_level', 'read'), ('approved_by__isnull', True), _connector='OR'), name='support_access_only_a_read_is_approved'),
        ),
        migrations.AddConstraint(
            model_name='teammember',
            constraint=models.UniqueConstraint(fields=('team', 'user'), name='team_member_unique'),
        ),
        migrations.AddConstraint(
            model_name='tenantproductterm',
            constraint=models.UniqueConstraint(fields=('product', 'term'), name='tenant_product_term_unique'),
        ),
        migrations.AlterModelOptions(
            name='registerentry',
            options={'ordering': ['org_unit', 'authority', 'id']},
        ),
        migrations.AlterModelOptions(
            name='teammember',
            options={'ordering': ['team', 'user']},
        ),
        migrations.AlterModelOptions(
            name='tenantproductterm',
            options={'ordering': ['product', 'term']},
        ),
        migrations.AlterModelOptions(
            name='licenceserviceterm',
            options={'ordering': ['licence', 'term']},
        ),
        *[same_tenant_key(*key) for key in COMPOSITE_KEYS],
        migrations.RunSQL(sql=ENTITY_TERM_GUARD_SQL, reverse_sql=ENTITY_TERM_GUARD_REVERSE_SQL),
        migrations.RunSQL(
            sql=(
                f'CREATE POLICY {OWN_GRANTS_POLICY} ON "support_access" FOR SELECT '
                f"USING (platform_user_id = {PLATFORM_USER_EXPRESSION})"
            ),
            reverse_sql=f'DROP POLICY IF EXISTS {OWN_GRANTS_POLICY} ON "support_access"',
        ),
    ]
