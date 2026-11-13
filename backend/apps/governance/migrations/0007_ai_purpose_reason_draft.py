"""governance 0007: the AI log names one more purpose, `reason_draft`, the reason a model drafts
in the "Does it apply" dialog from the licence facts and the library's facts alone (REG-01,
D-143, ADR 0069). The column's choices only; no row changes."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("governance", "0001_squashed_0006_schema"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aigeneration",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("so_what", "so_what"),
                    ("change_summary", "change_summary"),
                    ("scope_suggestion", "scope_suggestion"),
                    ("link_suggestion", "link_suggestion"),
                    ("translation", "translation"),
                    ("answer", "answer"),
                    ("agent_review", "agent_review"),
                    ("what_applies", "what_applies"),
                    ("reason_draft", "reason_draft"),
                ],
                max_length=32,
            ),
        ),
    ]
