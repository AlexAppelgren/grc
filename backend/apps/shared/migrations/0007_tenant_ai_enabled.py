"""shared 0007 (chunk 7, SRC-03, TEN-01): `tenant.ai_enabled`, the bank's one switch over
its own AI features (D-07, owner item 14). On by default, so every existing bank keeps
Ask exactly as it was; `tenant` already sits under forced row-level security (0002), and
a plain boolean needs no policy of its own."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("shared", "0006_outboxcursor")]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="ai_enabled",
            field=models.BooleanField(default=True),
        ),
    ]
