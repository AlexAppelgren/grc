"""proposals 0013 (INV-05, I18N-01, D-129): the `new_translations` kind, machine translations
of an existing shared record's title and summary in the content languages it lacks. The
choices change and nothing else."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("proposals", "0012_instrument_summary_kind"),
    ]

    operations = [
        migrations.AlterField(
            model_name="proposal",
            name="kind",
            field=models.CharField(
                choices=[
                    ("vocabulary_create", "vocabulary_create"),
                    ("vocabulary_relabel", "vocabulary_relabel"),
                    ("vocabulary_retire", "vocabulary_retire"),
                    ("vocabulary_merge", "vocabulary_merge"),
                    ("vocabulary_restore", "vocabulary_restore"),
                    ("term_create", "term_create"),
                    ("term_update", "term_update"),
                    ("new_obligation_version", "new_obligation_version"),
                    ("new_instrument", "new_instrument"),
                    ("new_obligation", "new_obligation"),
                    ("new_provision", "new_provision"),
                    ("new_provision_version", "new_provision_version"),
                    ("obligation_scope", "obligation_scope"),
                    ("new_recurring_duty", "new_recurring_duty"),
                    ("new_control", "new_control"),
                    ("new_instrument_summary", "new_instrument_summary"),
                    ("new_translations", "new_translations"),
                ],
                max_length=40,
            ),
        ),
    ]
