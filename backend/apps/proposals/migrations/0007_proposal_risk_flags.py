import django.contrib.postgres.fields
from django.db import migrations, models

"""proposals 0007 (AGT-07, HARDENING H23): what the injection screen found in the texts a
proposal arrived with, shown in the queue and read by the approval gate. Existing rows
start with none; they were filed before the screen read proposals."""


class Migration(migrations.Migration):

    dependencies = [
        ("proposals", "0006_idempotency_key_per_proposer"),
    ]

    operations = [
        migrations.AddField(
            model_name="proposal",
            name="risk_flags",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=40), blank=True, default=list, size=None
            ),
        ),
    ]
