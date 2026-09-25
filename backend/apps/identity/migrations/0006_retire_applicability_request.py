"""identity 0006 (REG-01, D-75): `applicability.request` is retired, so no stored role holds it.

One person holding `applicability.approve` sets applicability after a confirmation dialog;
there is no request and no second approver, and the permission left the code in the same
commit. System roles and a bank's own roles alike still carry the key in their array, and
roles_logic refuses an unknown key when a role is saved, so the key is removed from every
`tenant_role` row here.

`tenant_role` is under forced row-level security, which binds the schema owner too, so the
statement visits each tenant with that tenant activated, then puts back whatever tenant the
session had. The reverse does nothing: which custom roles once held the key is not known,
and the permission no longer exists to grant.
"""

from django.db import migrations

FORWARD = """
DO $$
DECLARE
    previous text := current_setting('app.tenant_id', true);
    tenant_row record;
BEGIN
    FOR tenant_row IN SELECT id FROM tenant LOOP
        PERFORM set_config('app.tenant_id', tenant_row.id::text, true);
        UPDATE tenant_role
        SET permissions = array_remove(permissions, 'applicability.request')
        WHERE tenant_id = tenant_row.id AND 'applicability.request' = ANY(permissions);
    END LOOP;
    PERFORM set_config('app.tenant_id', coalesce(previous, ''), true);
END
$$;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0005_login_event_key_created_and_withheld'),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD, reverse_sql=migrations.RunSQL.noop),
    ]
