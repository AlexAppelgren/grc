from django.db import migrations, models


"""proposals 0005 (PRO-01, INV-02, INV-08): the kinds `new_provision` and
`new_provision_version`, a law's verbatim text through the same door as every other change.
Only the column's choices move; no row changes."""


class Migration(migrations.Migration):

    dependencies = [
        ("proposals", "0004_instrument_obligation_kinds"),
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
                ],
                max_length=40,
            ),
        ),
    ]
