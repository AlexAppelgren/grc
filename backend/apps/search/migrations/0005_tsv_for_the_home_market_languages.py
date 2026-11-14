"""The keyword column reads the five languages of the other home markets (D-145, I18N-01).

`search_chunk.tsv` is a generated column with one branch per content language, and
PostgreSQL 16 cannot change a generated column's expression, so the column is dropped and
added again with its index. The index is derived data (ADR 0044): the stored values are
recomputed from `title` and `body` as the column is added, and nothing is re-embedded.

Estonian and Latvian have no text search configuration in PostgreSQL 16 and are matched word
for word with `simple`. The configurations are spelled out here, never imported from the
model, so a later language leaves this migration as it ran."""

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.db import migrations, models

CONFIGS = {
    "en": "english",
    "sv": "swedish",
    "da": "danish",
    "nb": "norwegian",
    "fi": "finnish",
    "et": "simple",
    "lv": "simple",
    "lt": "lithuanian",
    "de": "german",
    "nl": "dutch",
}


def _vector(config: str) -> SearchVector:
    return SearchVector("title", weight="A", config=models.Value(config)) + SearchVector("body", weight="B", config=models.Value(config))


class Migration(migrations.Migration):
    dependencies = [
        ("search", "0001_squashed_0004_schema"),
    ]

    operations = [
        migrations.RemoveIndex(model_name="searchchunk", name="search_chunk_tsv_idx"),
        migrations.RemoveField(model_name="searchchunk", name="tsv"),
        migrations.AddField(
            model_name="searchchunk",
            name="tsv",
            field=models.GeneratedField(
                db_persist=True,
                expression=models.Case(
                    *(models.When(language=key, then=_vector(config)) for key, config in CONFIGS.items()),
                    default=_vector("english"),
                ),
                output_field=SearchVectorField(),
            ),
        ),
        migrations.AddIndex(model_name="searchchunk", index=GinIndex(fields=["tsv"], name="search_chunk_tsv_idx")),
    ]
