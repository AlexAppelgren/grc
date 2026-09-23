"""Models of the search app: the derived index the hybrid query reads (SRC-01, SRC-02).

`SearchChunk` is one row per legal unit per language, copied from the shared library:
an obligation version, a provision version or a registered change. It is derived data,
not a library record and not a tenant record, so it extends neither `LibraryModel` nor
`TenantModel` (owner item 4, H7). Three things keep it honest, and each is proven:

- **One door.** Only `apps/search/indexing.py` may write a chunk, inside `index_write()`.
  The runtime refusal is below; the AST guard is `tests_index_fence.py`.
- **Row-level security, enabled and forced, in the split shape of hardening H15**
  (migration 0001): one `FOR ALL` policy whose USING and WITH CHECK are the session's own
  zone, so a bank writes only its own zone and the indexer, running with no tenant active,
  writes the shared one; plus `library_rows_visible`, a `FOR SELECT` policy that adds the
  shared chunks to every bank's reads.
- **`owner_tenant_id` is always NULL in R1.** Only shared records are indexed (D-10), so
  nothing a bank writes reaches a chunk. The column exists so the rule is enforceable in
  the database rather than only in Python, and so the shape is final before ADR 0010 is
  superseded (owner items 4 and 10).
"""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.db import models
from django.db.models import Case, Value, When
from django.utils import timezone
from pgvector.django import HnswIndex, VectorField

from apps.search.indexing import SearchChunkQuerySet, assert_index_write
from apps.search.schemas import EvalVia, SearchMatchKind

# The content language's own PostgreSQL text search configuration, so a Swedish chunk is
# stemmed as Swedish and a Finnish one as Finnish (INPUT_DELTAS §3). This departs from
# `docs/inputs/schema.sql`, which checks `lang IN ('sv', 'en')` and branches on two
# configurations; R1 has five content languages. The keys are the seeded `Language` rows',
# and `SearchChunkLanguageTests` fails if this mapping and those rows ever disagree.
TEXT_SEARCH_CONFIGS: dict[str, str] = {
    "en": "english",
    "sv": "swedish",
    "da": "danish",
    "nb": "norwegian",
    "fi": "finnish",
}

# The title carries more weight than the body, as schema.sql §6 has it: a reader searching
# "costs and charges" wants the obligation named that before one that mentions it.
TITLE_WEIGHT = "A"
BODY_WEIGHT = "B"


def _tsv_expression() -> Case:
    """The generated `tsv` column: the title and the body, each in the chunk's own
    language configuration. One `When` per seeded language, and English for anything else,
    because a generated column cannot read the `language` table to find out."""
    return Case(
        *(
            When(
                language=key,
                then=SearchVector("title", weight=TITLE_WEIGHT, config=Value(config))
                + SearchVector("body", weight=BODY_WEIGHT, config=Value(config)),
            )
            for key, config in TEXT_SEARCH_CONFIGS.items()
        ),
        default=SearchVector("title", weight=TITLE_WEIGHT, config=Value("english"))
        + SearchVector("body", weight=BODY_WEIGHT, config=Value("english")),
    )


class SearchSource(models.TextChoices):
    """Tier-one kind (apps/shared/kinds.py, `search_source`): which library record a chunk
    was built from. The retrieval query branches on it to open the right card, and the
    rebuild branches on it to know what to re-read."""

    PROVISION_VERSION = "provision_version", "Provision version"
    OBLIGATION_VERSION = "obligation_version", "Obligation version"
    CHANGE = "change", "Regulatory change"


class SearchChunk(models.Model):
    """One indexed legal unit in one language. Rebuilt from the library, never edited."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_type = models.CharField(max_length=20, choices=SearchSource.choices)
    source_id = models.UUIDField()
    language = models.ForeignKey(
        "library.Language", to_field="key", db_column="lang", on_delete=models.PROTECT, related_name="+"
    )
    title = models.TextField()
    body = models.TextField()
    hierarchy_path = models.TextField(blank=True, default="")
    # Copied from the version the chunk was built from, so an "as of" search filters on
    # the chunk itself and never joins back to the library (SRC-02, AC-SRC "mechanics").
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)  # schema: SearchChunkMetadata
    tsv = models.GeneratedField(expression=_tsv_expression(), output_field=SearchVectorField(), db_persist=True)
    # 1024 dimensions (D-09, EMBEDDING_DIMENSIONS): enough for a multilingual model and
    # well under the 2000 an HNSW index accepts. Empty until the worker fills it from the
    # outbox event; a chunk without one is still found by the keyword leg.
    embedding = VectorField(dimensions=1024, null=True, blank=True)
    embedding_model = models.CharField(max_length=120, blank=True, default="")
    embedding_version = models.CharField(max_length=40, blank=True, default="")
    embedded_at = models.DateTimeField(null=True, blank=True)
    # The zone the indexed record belongs to: NULL is the shared library, which in R1 is
    # every chunk there is. The policies in migration 0001 make this the database's rule.
    owner_tenant = models.ForeignKey(
        "shared.Tenant", db_column="owner_tenant_id", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    # Annotated because the manager is built from the queryset in indexing.py, which is
    # where the fence lives; `all()` still hands back the guarded queryset.
    objects: ClassVar[models.Manager["SearchChunk"]] = SearchChunkQuerySet.as_manager()

    class Meta:
        db_table = "search_chunk"
        ordering = ["source_type", "source_id", "language_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_type", "source_id", "language"], name="search_chunk_source_unique"
            )
        ]
        indexes = [
            GinIndex(fields=["tsv"], name="search_chunk_tsv_idx"),
            HnswIndex(
                name="search_chunk_embedding_idx",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
            models.Index(fields=["valid_from", "valid_to"], name="search_chunk_validity_idx"),
        ]

    def __str__(self) -> str:
        # The source it was built from, never its text: a chunk's body is a library record
        # and a __str__ ends up in places (a repr, a traceback) that are not for content.
        return f"{self.source_type}:{self.source_id}:{self.language_id}"

    def save(self, *args: Any, **kwargs: Any) -> None:  # compliance: allow-kwargs Django Model.save signature
        assert_index_write(type(self).__name__)
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:  # compliance: allow-kwargs Django Model.delete signature
        assert_index_write(type(self).__name__)
        return super().delete(*args, **kwargs)


class EvalQuestion(models.Model):
    """One labelled question of the retrieval evaluation set (SRC-05, ADM-02).

    A platform record, kept by platform staff in the console: it has no tenant column and is
    not a library record, so it extends neither `TenantModel` nor `LibraryModel`. Migration
    0002 enables and forces row-level security with one policy that refuses any session with
    a tenant active, so no bank can read or write the set. `backend/eval/retrieval.jsonl` is
    what the release gate reads; `seed_eval_questions` files its rows here, create-only, and
    `dump_eval_questions` writes the active rows back. `key` is the line's `id` and never
    changes; `expected` names library records by stable key, never by id, because the ids of
    the corpus differ in every database the gate builds.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.SlugField(max_length=40, unique=True)
    language = models.ForeignKey(
        "library.Language", to_field="key", db_column="lang", on_delete=models.PROTECT, related_name="+"
    )
    question = models.TextField()
    expected = ArrayField(models.CharField(max_length=200), default=list, blank=True)
    match_kind = models.CharField(max_length=10, choices=[(kind.value, kind.value) for kind in SearchMatchKind])
    as_of = models.DateField(null=True, blank=True)
    # Which read the gate scores the question on: the search page's hits or Ask's passages.
    via = models.CharField(max_length=6, choices=[(via.value, via.value) for via in EvalVia], default=EvalVia.SEARCH.value)
    notes = models.TextField(blank=True, default="")
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "eval_question"
        ordering = ["key"]

    def __str__(self) -> str:
        return self.key


class EvalRun(models.Model):
    """One scored run of the evaluation set against a retriever (SRC-05): which chain ran,
    the metrics, and what each question got back. Written by `record_eval_run`, whose audit
    row names who ran it; a platform record under the same policy as `EvalQuestion`, and
    never changed once written."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run_at = models.DateTimeField(default=timezone.now)
    config = models.JSONField()  # schema: EvalRunConfig
    metrics = models.JSONField()  # schema: EvalRunMetrics
    results = models.JSONField()  # schema: EvalQuestionResult, one per question asked

    class Meta:
        db_table = "eval_run"
        ordering = ["-run_at", "id"]

    def __str__(self) -> str:
        return f"eval run {self.id}"
