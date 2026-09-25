"""library 0005 (chunk 3, INV-06): what the reader was looking at when they said "this
looks wrong". The report keeps the version number and the language of the text on
screen, so an editor opens the same words. No problem-area column: nothing branches on
one, and an area belongs in a library vocabulary rather than a code enum. problem_report
already carries the mixed RLS policy from 0003; adding two nullable columns leaves it."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("library", "0004_append_only_versions"),
    ]

    operations = [
        migrations.AddField(
            model_name="problemreport",
            name="language",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="library.language",
                to_field="key",
            ),
        ),
        migrations.AddField(
            model_name="problemreport",
            name="version_number",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
