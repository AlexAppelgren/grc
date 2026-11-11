"""Models of the search app: the derived index the hybrid query reads (SRC-01, SRC-02).

`SearchChunk` is one row per legal unit per language, copied from the shared library. It is
derived data, neither `LibraryModel` nor `TenantModel` (H7):

- One door: only `indexing.py` writes, inside `index_write()` (runtime refusal below, AST
  guard in `tests_index_fence.py`).
- Forced row-level security in the split shape of H15 (migration 0001): writes stay in the
  session's own zone, and `library_rows_visible` adds shared chunks to every bank's reads.
- `owner_tenant_id` is always NULL: only shared records are indexed (D-10); the column makes
  that enforceable in the database.
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

# Each content language's own text search configuration (INPUT_DELTAS §3: five languages,
# not schema.sql's two). Keys are the seeded `Language` rows'; `SearchChunkLanguageTests`
# fails if they disagree.
TEXT_SEARCH_CONFIGS: dict[str, str] = {
    "en": "english",
    "sv": "swedish",
    "da": "danish",
    "nb": "norwegian",
    "fi": "finnish",
}

# The title weighs more than the body (schema.sql §6).
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
    # Copied from the version, so an "as of" search never joins back to the library (SRC-02).
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)  # schema: SearchChunkMetadata
    tsv = models.GeneratedField(expression=_tsv_expression(), output_field=SearchVectorField(), db_persist=True)
    # 1024 dimensions (D-09): enough for a multilingual model, under HNSW's 2000. Empty until
    # the worker fills it; the keyword leg still finds the chunk.
    embedding = VectorField(dimensions=1024, null=True, blank=True)
    embedding_model = models.CharField(max_length=120, blank=True, default="")
    embedding_version = models.CharField(max_length=40, blank=True, default="")
    embedded_at = models.DateTimeField(null=True, blank=True)
    # NULL is the shared library, every chunk in R1; migration 0001's policies enforce it.
    owner_tenant = models.ForeignKey(
        "shared.Tenant", db_column="owner_tenant_id", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    # Annotated because the manager is built from the fenced queryset in indexing.py.
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
        # The source, never its text: a __str__ reaches reprs and tracebacks.
        return f"{self.source_type}:{self.source_id}:{self.language_id}"

    def save(self, *args: Any, **kwargs: Any) -> None:  # compliance: allow-kwargs Django Model.save signature
        assert_index_write(type(self).__name__)
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:  # compliance: allow-kwargs Django Model.delete signature
        assert_index_write(type(self).__name__)
        return super().delete(*args, **kwargs)


class EvalQuestion(models.Model):
    """One labelled question of the retrieval evaluation set (SRC-05, ADM-02).

    A platform record: no tenant column, not a library record. Migration 0002 forces
    row-level security with a policy that refuses any session with a tenant active. The gate
    reads `backend/eval/retrieval.jsonl`; `seed_eval_questions` and `dump_eval_questions` keep
    the two in step. `key` is the line's `id` and never changes; `expected` names stable keys,
    since ids differ in every database the gate builds.
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
