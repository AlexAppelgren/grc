"""governance 0003 (AUD-02, D-82): how a model call ended, on its AI log row.

`stop_reason` is the provider's own word when the model finished (`end_turn`, or
`max_tokens` when it stopped at its limit), `aborted` when the caller stopped reading
before it finished, which for Ask is a reader closing the answer, and `failed` when the
model failed once it had been asked. Without it a call cut short read in the log exactly
as a finished one, free of charge. Existing rows keep an empty value: nobody recorded how
they ended, and the column says so rather than guessing."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("governance", "0002_ai_purpose_agent_review")]

    operations = [
        migrations.AddField(
            model_name="aigeneration",
            name="stop_reason",
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
