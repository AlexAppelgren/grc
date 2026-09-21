"""proposals 0003 (D-62, ADR 0054, PRO-02, AC-PRO2): the second pair of eyes may be an
independent agent.

`proposed_by_agent`, `reviewed_by_api_key` and `reviewed_by_agent` join the columns the
proposal already had, and `proposal_four_eyes` is widened from "never the same person" to
"never the same user, the same key or the same agent definition on both sides". It also
refuses a reviewing key that names no agent: an unbound key carries a NULL agent, and NULL
never equals NULL, so two such keys would pass the agent comparison on a missing value
rather than on independence. The database, not Python, stays the word on four eyes, and
`apps/shared/tests_four_eyes.py` reads the definition back.

A proposal an agent's key filed before this migration names the key and not its agent, so
the agent is copied from the key it was filed with: otherwise another key of the same agent
could approve it and the agent comparison would pass on that NULL. The agent is always the
key's own; nothing here is taken from a request.
"""

import django.db.models.deletion
from django.db import migrations, models

FOUR_EYES = (
    "reviewed_by_id IS NULL OR proposed_by_user_id IS NULL OR reviewed_by_id <> proposed_by_user_id"
)
FOUR_EYES_WITH_AGENTS = (
    "(reviewed_by_id IS NULL OR proposed_by_user_id IS NULL OR reviewed_by_id <> proposed_by_user_id)"
    " AND (reviewed_by_api_key_id IS NULL OR proposed_by_api_key_id IS NULL"
    " OR reviewed_by_api_key_id <> proposed_by_api_key_id)"
    " AND (reviewed_by_agent_id IS NULL OR proposed_by_agent_id IS NULL"
    " OR reviewed_by_agent_id <> proposed_by_agent_id)"
    " AND (reviewed_by_api_key_id IS NULL OR reviewed_by_agent_id IS NOT NULL)"
)


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0002_library_rows_visible"),
        ("identity", "0004_login_event_feed_used"),
        ("proposals", "0002_obligation_proposals"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposal",
            name="proposed_by_agent",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="agents.agent"
            ),
        ),
        migrations.AddField(
            model_name="proposal",
            name="reviewed_by_agent",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="agents.agent"
            ),
        ),
        migrations.AddField(
            model_name="proposal",
            name="reviewed_by_api_key",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="identity.apikey"
            ),
        ),
        migrations.AddConstraint(
            model_name="proposal",
            constraint=models.CheckConstraint(
                condition=models.Q(("reviewed_by__isnull", True), ("reviewed_by_api_key__isnull", True), _connector="OR"),
                name="proposal_one_reviewer",
            ),
        ),
        migrations.RunSQL(
            sql=(
                'UPDATE "proposal" SET proposed_by_agent_id = api_key.agent_id FROM "api_key" '
                "WHERE proposal.proposed_by_api_key_id = api_key.id AND api_key.agent_id IS NOT NULL"
            ),
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql=[
                'ALTER TABLE "proposal" DROP CONSTRAINT proposal_four_eyes',
                f'ALTER TABLE "proposal" ADD CONSTRAINT proposal_four_eyes CHECK ({FOUR_EYES_WITH_AGENTS})',
            ],
            reverse_sql=[
                'ALTER TABLE "proposal" DROP CONSTRAINT proposal_four_eyes',
                f'ALTER TABLE "proposal" ADD CONSTRAINT proposal_four_eyes CHECK ({FOUR_EYES})',
            ],
        ),
    ]
