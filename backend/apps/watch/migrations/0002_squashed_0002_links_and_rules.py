"""watch, squashed (review 2026-11-11 B-13): the watch tables' links to other apps' tables."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    replaces = [
        ('watch', '0002_curation_confirmation'),
    ]

    dependencies = [
        ('agents', '0001_squashed_0001_tables'),
        ('identity', '0001_squashed_0001_tables'),
        ('library', '0001_squashed_0001_tables'),
        ('taxonomy', '0001_squashed_0001_tables'),
        ('watch', '0001_squashed_0001_tables'),
    ]

    operations = [
        migrations.AddField(
            model_name='regulatorychange',
            name='agent_run',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='changes', to='agents.agentrun'),
        ),
        migrations.AddField(
            model_name='regulatorychange',
            name='authority',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='changes', to='library.authority'),
        ),
        migrations.AddField(
            model_name='regulatorychange',
            name='change_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.changetype'),
        ),
        migrations.AddField(
            model_name='regulatorychange',
            name='change_type_confirmed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='regulatorychange',
            name='change_type_confirmed_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='regulatorychange',
            name='change_type_confirmed_by_api_key',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.apikey'),
        ),
        migrations.AddField(
            model_name='regulatorychange',
            name='change_type_suggested_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='regulatorychange',
            name='change_type_suggested_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='regulatorychange',
            name='change_type_suggested_by_api_key',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.apikey'),
        ),
        migrations.AddField(
            model_name='regulatorychange',
            name='suggested_urgency',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.urgency'),
        ),
        migrations.AddField(
            model_name='changeterm',
            name='confirmed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='changeterm',
            name='confirmed_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='changeterm',
            name='confirmed_by_api_key',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.apikey'),
        ),
        migrations.AddField(
            model_name='changeterm',
            name='flag',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.flag'),
        ),
        migrations.AddField(
            model_name='changeterm',
            name='suggested_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='changeterm',
            name='suggested_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='changeterm',
            name='suggested_by_api_key',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.apikey'),
        ),
        migrations.AddField(
            model_name='changeterm',
            name='term',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.taxonomyterm'),
        ),
        migrations.AddField(
            model_name='changeobligation',
            name='confirmed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='changeobligation',
            name='confirmed_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='changeobligation',
            name='confirmed_by_api_key',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.apikey'),
        ),
        migrations.AddField(
            model_name='changeobligation',
            name='obligation',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='change_links', to='library.obligation'),
        ),
        migrations.AddField(
            model_name='changeobligation',
            name='suggested_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.user'),
        ),
        migrations.AddField(
            model_name='changeobligation',
            name='suggested_by_agent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='agents.agent'),
        ),
        migrations.AddField(
            model_name='changeobligation',
            name='suggested_by_api_key',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.apikey'),
        ),
        migrations.AddField(
            model_name='source',
            name='authority',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sources', to='library.authority'),
        ),
        migrations.AddField(
            model_name='source',
            name='kind',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='taxonomy.sourcekind'),
        ),
        migrations.AddField(
            model_name='sourcecheck',
            name='agent_run',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='source_checks', to='agents.agentrun'),
        ),
        migrations.AddConstraint(
            model_name='regulatorychange',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('change_type_suggested', True), ('change_type_confirmed_at__isnull', True), ('change_type_confirmed_by__isnull', True), ('change_type_confirmed_by_api_key__isnull', True), ('change_type_confirmed_by_agent__isnull', True)), models.Q(('change_type_suggested', False), models.Q(models.Q(('change_type_confirmed_at__isnull', False), ('change_type_confirmed_by__isnull', False), ('change_type_confirmed_by_api_key__isnull', True), ('change_type_confirmed_by_agent__isnull', True)), models.Q(('change_type_confirmed_at__isnull', False), ('change_type_confirmed_by__isnull', True), ('change_type_confirmed_by_api_key__isnull', False), ('change_type_confirmed_by_agent__isnull', False)), _connector='OR')), _connector='OR'), name='regulatory_change_type_confirmation_names_a_person_or_an_agent'),
        ),
        migrations.AddConstraint(
            model_name='regulatorychange',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('change_type_confirmed_by__isnull', True), ('change_type_suggested_by__isnull', True), models.Q(('change_type_confirmed_by', models.F('change_type_suggested_by')), _negated=True), _connector='OR'), models.Q(('change_type_confirmed_by_agent__isnull', True), ('change_type_suggested_by_agent__isnull', True), models.Q(('change_type_confirmed_by_agent', models.F('change_type_suggested_by_agent')), _negated=True), _connector='OR'), models.Q(('change_type_confirmed_by_api_key__isnull', True), ('change_type_suggested_by_api_key__isnull', True), models.Q(('change_type_confirmed_by_api_key', models.F('change_type_suggested_by_api_key')), _negated=True), _connector='OR')), name='regulatory_change_type_confirmer_is_not_the_suggester'),
        ),
        migrations.AddConstraint(
            model_name='changeterm',
            constraint=models.UniqueConstraint(fields=('change', 'term'), name='change_term_term_unique'),
        ),
        migrations.AddConstraint(
            model_name='changeterm',
            constraint=models.UniqueConstraint(fields=('change', 'flag'), name='change_term_flag_unique'),
        ),
        migrations.AddConstraint(
            model_name='changeterm',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('flag__isnull', False), ('term__isnull', True)), models.Q(('flag__isnull', True), ('term__isnull', False)), _connector='OR'), name='change_term_one_subject'),
        ),
        migrations.AddConstraint(
            model_name='changeterm',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('suggested', True), ('confirmed_at__isnull', True), ('confirmed_by__isnull', True), ('confirmed_by_api_key__isnull', True), ('confirmed_by_agent__isnull', True)), models.Q(('suggested', False), models.Q(models.Q(('confirmed_at__isnull', False), ('confirmed_by__isnull', False), ('confirmed_by_api_key__isnull', True), ('confirmed_by_agent__isnull', True)), models.Q(('confirmed_at__isnull', False), ('confirmed_by__isnull', True), ('confirmed_by_api_key__isnull', False), ('confirmed_by_agent__isnull', False)), _connector='OR')), _connector='OR'), name='change_term_confirmation_names_a_person_or_an_agent'),
        ),
        migrations.AddConstraint(
            model_name='changeterm',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('confirmed_by__isnull', True), ('suggested_by__isnull', True), models.Q(('confirmed_by', models.F('suggested_by')), _negated=True), _connector='OR'), models.Q(('confirmed_by_agent__isnull', True), ('suggested_by_agent__isnull', True), models.Q(('confirmed_by_agent', models.F('suggested_by_agent')), _negated=True), _connector='OR'), models.Q(('confirmed_by_api_key__isnull', True), ('suggested_by_api_key__isnull', True), models.Q(('confirmed_by_api_key', models.F('suggested_by_api_key')), _negated=True), _connector='OR')), name='change_term_confirmer_is_not_the_suggester'),
        ),
        migrations.AddConstraint(
            model_name='changeobligation',
            constraint=models.UniqueConstraint(fields=('change', 'obligation'), name='change_obligation_unique'),
        ),
        migrations.AddConstraint(
            model_name='changeobligation',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('confirmed_at__isnull', True), ('confirmed_by__isnull', True), ('confirmed_by_api_key__isnull', True), ('confirmed_by_agent__isnull', True)), models.Q(('confirmed_at__isnull', False), ('confirmed_by__isnull', False), ('confirmed_by_api_key__isnull', True), ('confirmed_by_agent__isnull', True)), models.Q(('confirmed_at__isnull', False), ('confirmed_by__isnull', True), ('confirmed_by_api_key__isnull', False), ('confirmed_by_agent__isnull', False)), _connector='OR'), name='change_obligation_confirmation_names_a_person_or_an_agent'),
        ),
        migrations.AddConstraint(
            model_name='changeobligation',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('confirmed_by__isnull', True), ('suggested_by__isnull', True), models.Q(('confirmed_by', models.F('suggested_by')), _negated=True), _connector='OR'), models.Q(('confirmed_by_agent__isnull', True), ('suggested_by_agent__isnull', True), models.Q(('confirmed_by_agent', models.F('suggested_by_agent')), _negated=True), _connector='OR'), models.Q(('confirmed_by_api_key__isnull', True), ('suggested_by_api_key__isnull', True), models.Q(('confirmed_by_api_key', models.F('suggested_by_api_key')), _negated=True), _connector='OR')), name='change_obligation_confirmer_is_not_the_suggester'),
        ),
        migrations.AlterModelOptions(
            name='changeterm',
            options={'ordering': ['flag__sort_order', 'term__sort_order', 'id']},
        ),
        migrations.AlterModelOptions(
            name='changeobligation',
            options={'ordering': [models.OrderBy(models.F('confidence'), descending=True, nulls_last=True), 'obligation__stable_key']},
        ),
    ]
