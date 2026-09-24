"""search 0004 (SRC-05, SRC-S12, D-81): a question of the evaluation set says which read it
is scored on.

ask-standard-no-answer gave the release gate's file a `via` field, `ask` for a question
scored on the passages Ask would give a model, and the console's copy of the set had no
column for it: seeding the file and dumping it back dropped the field, so the row that
proves Ask answers nothing about a standard's control would have been scored on search.
`search` is the default, which every earlier row is."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("search", "0003_eval_sets_door"),
    ]

    operations = [
        migrations.AddField(
            model_name="evalquestion",
            name="via",
            field=models.CharField(choices=[("search", "search"), ("ask", "ask")], default="search", max_length=6),
        ),
    ]
