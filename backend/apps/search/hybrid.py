"""Hybrid search (SRC-01, SRC-02): one SQL statement over the chunk table, the keyword and
vector legs fused by reciprocal rank and reranked, filtered by validity and visibility before
anything is ranked.

- One statement: both legs, every filter and every hit fact (heading, version, instrument)
  in one SELECT, so the 800 ms budget (NFR-02) does not depend on page size
  (`SearchHybridQueryCountTests`).
- A leg either found a row or it did not: `SEARCH_RETRIEVAL_DEPTH` bounds each leg and
  `SEARCH_CONCEPT_SCORE_FLOOR` stops the vector leg calling everything a concept match. A
  chunk without a vector is still found by its words: narrower, never wrong.
- Narrower, never wider: `owner_tenant_id IS NULL` in code as well as policy (D-10, H7). The
  regulatory scope is the one rule, `taxonomy_in_footprint`, over the record's terms, its
  instrument's regime and its rules' jurisdictions; filters are the obligations list's own,
  compared by key.
- Ties break on `TIE_BREAK` (stable key, kind, language, start date), never a uuid, so a
  fresh database answers in the same order and the evaluation set can gate (SRC-05).
- One hit per record: the language that read the query best (SRC-S2).
- The query is the bank's own text: it reaches text search, embedder and reranker only,
  never a log, audit row, payload or URL (playbook 4.7); with AI features off it reaches
  no model (D-07). `POST /search` writes nothing.
- A bank's own agent (`search:read`, ACC-04, ACC-05) gets the same statement plus its
  entry's scope (`entry_admits()`, ACC-02); `footprint` `all` or `watched` is refused.
- `find_similar` (`POST /search/similar`, AGT-02) is the agents' read: no bank scope, the
  passage read in all five language configurations, ranked at today, vector leg leading.
  Both routes share the per-caller bucket in `limits.py`.
"""

from __future__ import annotations

import datetime
import functools
import operator
import re
import uuid
from typing import Any

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.lookups import DataContains
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.core.exceptions import ValidationError
from django.db.models import (
    BooleanField,
    Case,
    Exists,
    F,
    FloatField,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    TextField,
    UUIDField,
    Value,
    When,
    Window,
)
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce, NullIf, RowNumber
from django.utils import timezone
from pgvector.django import CosineDistance

from apps.library.models import Instrument, Obligation, ObligationTitle, ObligationVersion, Provision
from apps.library.reading import OPEN, Reader, entry_admits, in_view, instrument_scope_term_ids, scope_term_ids, terms_of, today_for
from apps.search import limits
from apps.search.models import TEXT_SEARCH_CONFIGS, SearchChunk, SearchSource
from apps.search.schemas import (
    SearchFilters,
    SearchHit,
    SearchHitType,
    SearchMatchKind,
    SearchRequest,
    SearchResponse,
    SimilarRequest,
)
from apps.shared.adapters import embedder, reranker
from apps.shared.errors import not_found
from apps.shared.models import Tenant
from apps.taxonomy import matching
from apps.taxonomy.models import InstrumentLevelKind
from apps.watch.models import RegulatoryChange
from apps.watch.reading import _scope_term_ids as change_scope_term_ids  # the feed's own rule, never a copy

# Which chunk a hit kind means and which kind a chunk answers as: one mapping, read both ways.
SOURCE_OF_HIT: dict[SearchHitType, str] = {
    SearchHitType.OBLIGATION: SearchSource.OBLIGATION_VERSION.value,
    SearchHitType.PROVISION: SearchSource.PROVISION_VERSION.value,
    SearchHitType.CHANGE: SearchSource.CHANGE.value,
}
HIT_OF_SOURCE: dict[str, SearchHitType] = {source: hit for hit, source in SOURCE_OF_HIT.items()}

# What the fused query returns. `tsv` and `embedding` are left out: the widest columns, and
# nothing above the database reads them.
COLUMNS = (
    "id",
    "source_type",
    "body",
    "valid_from",
    "valid_to",
    "metadata",
    "record_id",
    "heading",
    "version_no",
    "instrument_short_name",
    "by_keyword",
    "by_concept",
    "fused",
)
# What a tie is broken on wherever rows are ranked: all four survive a rebuild, where a uuid
# changes on every fresh database (SRC-05).
TIE_BREAK = ("record_key", "source_type", "language_id", "valid_from")
WORDS = re.compile(r"\w+", re.UNICODE)
ELLIPSIS = "…"


# --- POST /search, POST /search/similar ---
def run_search(body: SearchRequest, *, tenant_id: uuid.UUID | None, user_id: uuid.UUID, reader: Reader = OPEN) -> SearchResponse:
    """`POST /search`. The tenant scopes the footprint filter; the chunks are the library's
    (D-10). The reader's bucket is spent first (NFR-02). A confined reader (a bank's own
    agent) stays inside the footprint and its entry's scope."""
    limits.search_bucket(user_id)
    tenant = tenant_of(tenant_id)
    if reader.confined and body.filters is not None and body.filters.footprint != "in":
        raise ValidationError(
            "An agent access credential searches inside the bank's regulatory scope only, so footprint is in.",
            code="unknown_filter",
        )
    as_of = body.as_of or today_for(tenant)
    found = _candidates(
        body.q,
        configurations=(_configuration(body.lang, tenant),),
        types=body.types,
        filters=body.filters or SearchFilters(),
        tenant=tenant,
        as_of=as_of,
        limit=body.limit,
        models=tenant.ai_enabled,
        entry_id=reader.entry_id,
    )
    ranked = _best_per_record(_reranked(body.q, found, models=tenant.ai_enabled))
    return SearchResponse(items=[_hit(row, body.q) for row in ranked[: body.limit]], as_of=as_of)


def find_similar(body: SimilarRequest, *, caller_id: uuid.UUID, tenant_id: uuid.UUID | None) -> SearchResponse:
    """`POST /search/similar`: the agents' nearest-neighbour read over library chunks
    (AGT-02); no bank record is read or returned. No language and no `asOf`, so the words are
    read in every content configuration and ranked at today, UTC. A bank's own key reaches the
    models only while that bank's AI features are on.
    """
    limits.search_bucket(caller_id)
    as_of = timezone.localdate()
    models = tenant_id is None or Tenant.objects.filter(pk=tenant_id, ai_enabled=True).exists()
    found = _candidates(
        body.text,
        configurations=tuple(TEXT_SEARCH_CONFIGS.values()),
        types=body.types,
        filters=SearchFilters(),
        tenant=None,
        as_of=as_of,
        limit=body.limit,
        models=models,
    )
    ranked = _best_per_record(_reranked(body.text, found, models=models))
    return SearchResponse(items=[_hit(row, body.text) for row in ranked[: body.limit]], as_of=as_of)


def passages(
    question: str, *, tenant: Tenant, lang: str | None, as_of: datetime.date, depth: int
) -> list[dict[str, Any]]:
    """What Ask may ground an answer in (SRC-03): the obligations the reader's own search
    ranks first, one row each, at most `depth`, with the chunk's whole `body`.

    Same statement, scope and "as of" as `POST /search`, so an answer never rests on a record
    the reader could not have found. `ask.answer_events` already checked the AI switch and
    spent `limits.ask_bucket`. Never an obligation under a standard (INV-08, D-81): the
    library holds only the conformance duty, so a control question is "no answer" rather than
    one cited to the duty from licensed text the model remembers.
    """
    found = _candidates(
        question,
        configurations=(_configuration(lang, tenant),),
        types=[SearchHitType.OBLIGATION],
        filters=SearchFilters(),
        tenant=tenant,
        as_of=as_of,
        limit=depth,
        models=True,
        standards=False,
    )
    return _best_per_record(_reranked(question, found, models=True))[:depth]


# --- The one statement ---
def _candidates(
    text: str,
    *,
    configurations: tuple[str, ...],
    types: list[SearchHitType],
    filters: SearchFilters,
    tenant: Tenant | None,
    as_of: datetime.date,
    limit: int,
    models: bool,
    standards: bool = True,
    entry_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """The rows either leg found, best fused first. One query, however many hits. With
    `models` false the query reaches no embedder: the vector leg finds nothing."""
    asked = _asked(text, configurations)
    rows = _filtered(types=types, filters=filters, tenant=tenant, as_of=as_of, standards=standards, entry_id=entry_id)
    rows = rows.annotate(
        keyword_score=SearchRank(F("tsv"), asked),
        similarity=_similarity(text) if models else Value(None, output_field=FloatField()),
        record_key=_record_key(),
    )
    rows = rows.annotate(
        keyword_rank=Window(RowNumber(), order_by=(F("keyword_score").desc(), *TIE_BREAK)),
        concept_rank=Window(RowNumber(), order_by=(F("similarity").desc(nulls_last=True), *TIE_BREAK)),
    )
    depth = settings.SEARCH_RETRIEVAL_DEPTH
    # Whether the words matched is `@@`, not the rank: `ts_rank` answers 1e-20 for a miss.
    rows = rows.annotate(
        by_keyword=_found(Q(tsv=asked) & Q(keyword_rank__lte=depth)),
        by_concept=_found(Q(similarity__gte=settings.SEARCH_CONCEPT_SCORE_FLOOR) & Q(concept_rank__lte=depth)),
    )
    rows = rows.annotate(
        record_id=_record_id(),
        heading=_heading(),
        version_no=Subquery(ObligationVersion.objects.filter(id=OuterRef("source_id")).values("version_number")[:1]),
        instrument_short_name=Subquery(
            Instrument.objects.filter(id=_outer_metadata_uuid("instrument_id")).values("short_name")[:1]
        ),
        fused=_rank_score("by_keyword", "keyword_rank") + _rank_score("by_concept", "concept_rank"),
    )
    # The reranker's window or the page, whichever is larger, times the languages a record
    # may be summarised in, since the page keeps one hit per record.
    wanted = max(reranker.get_reranker().top_k, limit) * len(TEXT_SEARCH_CONFIGS)
    page = rows.order_by(F("fused").desc(), *TIE_BREAK).values(*COLUMNS)[:wanted]
    return [row for row in page if row["by_keyword"] or row["by_concept"]]


def _asked(text: str, configurations: tuple[str, ...]) -> SearchQuery:
    """The text as PostgreSQL reads it, stemmed in each configuration given and OR-ed. A
    reader names their language; an agent's passage could be any, and its chunks hold
    their own language's stems, so it is read in all five. Still one statement.
    """
    return functools.reduce(
        operator.or_,
        (SearchQuery(text, search_type="websearch", config=config) for config in configurations),
    )


def _filtered(
    *,
    types: list[SearchHitType],
    filters: SearchFilters,
    tenant: Tenant | None,
    as_of: datetime.date,
    standards: bool = True,
    entry_id: uuid.UUID | None = None,
) -> QuerySet[SearchChunk]:
    """Everything the caller may see and asked for, filtered before ranking, so a filter
    never answers a short page of a long list. `standards=False` drops chunks whose
    instrument's level is of kind `standard` (D-81). `entry_id` narrows by an agent access
    entry's scope (ACC-02)."""
    rows = SearchChunk.objects.filter(owner_tenant__isnull=True)
    rows = rows.filter(Q(valid_from__isnull=True) | Q(valid_from__lte=as_of))
    rows = rows.filter(Q(valid_to__isnull=True) | Q(valid_to__gte=as_of))
    if types:
        rows = rows.filter(source_type__in=[SOURCE_OF_HIT[kind] for kind in types])
    if filters.instrument is not None:
        rows = rows.filter(Exists(Instrument.objects.filter(id=_outer_metadata_uuid("instrument_id"), stable_key=filters.instrument)))
    if filters.jurisdiction is not None:
        rows = rows.filter(metadata__jurisdiction=filters.jurisdiction)
    if filters.duty_type is not None:
        rows = rows.filter(metadata__duty_type=filters.duty_type)
    if filters.binding is not None:
        rows = rows.filter(metadata__binding=filters.binding)
    if filters.term:
        wanted = Value([term.id for term in terms_of(filters.term)], output_field=ArrayField(UUIDField()))
        rows = rows.filter(DataContains(_record_scope(), wanted))
    if not standards:
        rows = rows.exclude(
            Exists(
                Instrument.objects.filter(
                    id=_outer_metadata_uuid("instrument_id"), level__kind=InstrumentLevelKind.STANDARD.value
                )
            )
        )
    if tenant is None or filters.footprint == "all":
        # The agents' read, or a reader who lifted the scope. Still confined to the shared
        # library by `owner_tenant_id IS NULL` above.
        return rows
    if filters.footprint == "in":
        rows = rows.annotate(in_scope=matching.in_footprint_expression(tenant.id, _record_scope())).filter(in_scope=True)
        if entry_id is not None:
            rows = rows.filter(*entry_admits(tenant.id, entry_id, _record_scope()))
        return rows
    # `watched`: asked of the inventory's own rule for the chunk's record (FP-04).
    obligations = in_view(Obligation.objects.filter(id=_outer_metadata_uuid("obligation_id")), tenant, "watched")
    instruments = in_view(Instrument.objects.filter(id=_outer_metadata_uuid("instrument_id")), tenant, "watched")
    return rows.filter(
        Q(source_type=SOURCE_OF_HIT[SearchHitType.OBLIGATION]) & Exists(obligations)
        | Q(source_type=SOURCE_OF_HIT[SearchHitType.PROVISION]) & Exists(instruments)
    )


def _record_scope() -> Coalesce:
    """The scope the inventory judges the chunk's record by, from `library.reading`'s SQL
    twins: an obligation's terms plus its instrument's scope; a provision's instrument scope;
    a change's watch scope (`watch.reading`); none matches every bank. The regime and
    jurisdictions narrow a search exactly as they narrow the inventory (D-28, D-29)."""
    obligation = Obligation.objects.filter(id=_outer_metadata_uuid("obligation_id")).values(scope=scope_term_ids())
    instrument = Instrument.objects.filter(id=_outer_metadata_uuid("instrument_id")).values(scope=instrument_scope_term_ids())
    change = RegulatoryChange.objects.filter(id=OuterRef("source_id")).values(scope=change_scope_term_ids())
    return Coalesce(
        Subquery(obligation[:1]),
        Subquery(instrument[:1]),
        Subquery(change[:1]),
        Value([], output_field=ArrayField(UUIDField())),
        output_field=ArrayField(UUIDField()),
    )


def _similarity(query: str) -> Any:
    """Cosine similarity to the query, or nothing while no embedding model is contracted
    (D-09); a deployment without one searches by keyword."""
    adapter = embedder.get_embedder()
    if isinstance(adapter, embedder.NoEmbedder):
        return Value(None, output_field=FloatField())
    return Value(1.0, output_field=FloatField()) - CosineDistance("embedding", adapter.embed([query])[0])


def _found(condition: Q) -> Case:
    return Case(When(condition, then=Value(True)), default=Value(False), output_field=BooleanField())


def _rank_score(leg: str, rank: str) -> Case:
    """One leg's share of the reciprocal rank fusion: `1 / (k + rank)` where it found the
    row, nothing where it did not."""
    return Case(
        When(**{leg: True}, then=1.0 / (Value(float(settings.SEARCH_RRF_K)) + F(rank))),
        default=Value(0.0),
        output_field=FloatField(),
    )


def _metadata_uuid(key: str) -> Cast:
    """One id the indexer copied onto the chunk, as the uuid the library stores: read from
    the chunk the row under construction is."""
    return Cast(KeyTextTransform(key, "metadata"), UUIDField())


def _outer_metadata_uuid(key: str) -> Cast:
    """The same id, read from inside a subquery correlated to that chunk."""
    return Cast(KeyTextTransform(key, OuterRef("metadata")), UUIDField())


def _record_id() -> Case:
    """What the hit points at and what opens when the reader clicks it: the obligation, the
    provision, or the change the chunk was built from."""
    return Case(
        When(
            source_type=SearchSource.OBLIGATION_VERSION.value,
            then=_metadata_uuid("obligation_id"),
        ),
        When(
            source_type=SearchSource.PROVISION_VERSION.value,
            then=Subquery(Provision.objects.filter(versions__id=OuterRef("source_id")).values("id")[:1]),
        ),
        default=F("source_id"),
        output_field=UUIDField(),
    )


def _record_key() -> Case:
    """The stable key of the chunk's record, the first `TIE_BREAK`, one branch per kind."""
    return Case(
        When(
            source_type=SearchSource.OBLIGATION_VERSION.value,
            then=Subquery(Obligation.objects.filter(id=_outer_metadata_uuid("obligation_id")).values("stable_key")[:1]),
        ),
        When(
            source_type=SearchSource.PROVISION_VERSION.value,
            then=Subquery(Provision.objects.filter(versions__id=OuterRef("source_id")).values("stable_key")[:1]),
        ),
        When(
            source_type=SearchSource.CHANGE.value,
            then=Subquery(RegulatoryChange.objects.filter(id=OuterRef("source_id")).values("stable_key")[:1]),
        ),
        output_field=TextField(),
    )


def _heading() -> Coalesce:
    """The record's own heading in the language searched, for the hit's title; the chunk's
    `title` is the citation line the keyword leg is built on."""
    titles = ObligationTitle.objects.filter(obligation_id=_outer_metadata_uuid("obligation_id"))
    return Coalesce(
        Subquery(titles.filter(language=OuterRef("language_id")).values("text")[:1]),
        Subquery(titles.filter(is_original=True).values("text")[:1]),
        NullIf(
            Subquery(Provision.objects.filter(versions__id=OuterRef("source_id")).values("heading")[:1]),
            Value("", output_field=TextField()),
        ),
        F("title"),
        output_field=TextField(),
    )


# --- Ranking and the hit ---
def _reranked(query: str, rows: list[dict[str, Any]], *, models: bool) -> list[dict[str, Any]]:
    """The reranker's verdict on the fused window, added to the fused score. An unjudged row
    keeps its fused score and cannot overtake a judged one, so `RERANKER_PROVIDER=none`
    (every score 0.0) and `models` false leave the fused order standing.
    """
    adapter = reranker.get_reranker() if models else reranker.NoReranker(settings.RERANKER_TOP_K)
    window = rows[: adapter.top_k]
    judged = (
        {candidate.index: candidate.score for candidate in adapter.rerank(query=query, documents=_documents(window))}
        if window
        else {}
    )
    for index, row in enumerate(rows):
        row["score"] = row["fused"] + judged.get(index, 0.0)
    # sorted() is stable: the database already broke every tie on `TIE_BREAK`.
    return sorted(rows, key=lambda row: -row["score"])


def _documents(rows: list[dict[str, Any]]) -> list[str]:
    return [f"{row['heading']}\n\n{row['body']}" for row in rows]


def _best_per_record(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One hit per record: the chunk whose language read the query best (SRC-S2), so five
    translations never fill a page. The card shows every language.
    """
    best: dict[Any, dict[str, Any]] = {}
    for row in rows:
        best.setdefault(row["record_id"], row)
    return list(best.values())


def _hit(row: dict[str, Any], query: str) -> SearchHit:
    metadata = row["metadata"]
    return SearchHit(
        type=HIT_OF_SOURCE[row["source_type"]],
        id=row["record_id"],
        title=row["heading"],
        snippet=_snippet(row["body"], query),
        match_kind=_match_kind(row),
        score=row["score"],
        version_no=row["version_no"],
        instrument_short_name=row["instrument_short_name"],
        binding=metadata.get("binding"),
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        # A change's urgency label needs the reader's language; the change page shows it.
        urgency=None,
    )


def _match_kind(row: dict[str, Any]) -> SearchMatchKind:
    if row["by_keyword"] and row["by_concept"]:
        return SearchMatchKind.BOTH
    return SearchMatchKind.CONCEPT if row["by_concept"] else SearchMatchKind.KEYWORD


def _snippet(body: str, query: str) -> str:
    """The chunk's text around the match, capped by `SEARCH_SNIPPET_CHARS`; a concept hit
    shows the opening."""
    cap = settings.SEARCH_SNIPPET_CHARS
    if len(body) <= cap:
        return body
    start = max(_first_match(body, query) - cap // 4, 0)
    cut = body[start : start + cap].strip()
    return f"{ELLIPSIS if start else ''}{cut}{ELLIPSIS if start + cap < len(body) else ''}"


def _first_match(body: str, query: str) -> int:
    """Where the first word of the query appears in the text, or the start of the text."""
    folded = body.casefold()
    positions = [found for word in WORDS.findall(query.casefold()) if (found := folded.find(word)) >= 0]
    return min(positions, default=0)


# --- The caller ---
def tenant_of(tenant_id: uuid.UUID | None) -> Tenant:
    """The bank whose scope and time zone a search or a question is read in. A session in no
    bank is a 404 and not a 403, exactly as every other tenant read answers it."""
    tenant = (
        Tenant.objects.filter(pk=tenant_id).first()  # ordering: pk lookup, at most one row
        if tenant_id is not None
        else None
    )
    if tenant is None:
        raise not_found("Sign in to a company to search the library.")
    return tenant


def _configuration(lang: str | None, tenant: Tenant) -> str:
    """The text search configuration the query is stemmed in: the asked language, else the
    bank's default content language, else English. It chooses how the query is read, not
    which chunks are read (INPUT_DELTAS §3, SRC-S2).
    """
    if lang is not None and lang not in TEXT_SEARCH_CONFIGS:
        raise ValidationError(
            f"{lang!r} is not a language of the library. GET /languages lists them.", code="unknown_key"
        )
    return TEXT_SEARCH_CONFIGS.get(str(lang or tenant.default_language_id or ""), "english")
