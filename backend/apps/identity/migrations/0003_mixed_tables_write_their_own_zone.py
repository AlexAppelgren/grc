"""identity 0003 (hardening H15, NFR-01): identity tables write only their own zone.

Five mixed tables (`invitation`, `invitation_role`, `user_session`, `api_key`,
`login_event`) checked every write with their read rule, so a bank session could insert,
change or delete a row without a tenant: the platform agent's API key, a platform sign-in
in the security log, an invitation into the console. `membership` was not mixed but carried
the identity-lookup clause in its write check, so anything holding the flag open could
write a membership of any tenant.

Both are now the same shape: `tenant_isolation` accepts only the session's own zone, and
what the auth layer reads before a tenant is known (`identity_lookup_visible`) and what
every tenant reads of the platform's rows (`library_rows_visible`) are policies that can
only read.
"""

from django.db import migrations

from apps.shared.migration_helpers import split_policy_operations


class Migration(migrations.Migration):
    dependencies = [("identity", "0002_api_key_agent")]

    operations = [
        *split_policy_operations("invitation", mixed=True, identity_lookup=True),
        *split_policy_operations("invitation_role", mixed=True),
        *split_policy_operations("user_session", mixed=True, identity_lookup=True),
        *split_policy_operations("api_key", mixed=True, identity_lookup=True),
        *split_policy_operations("login_event", mixed=True),
        *split_policy_operations("membership", identity_lookup=True),
    ]
