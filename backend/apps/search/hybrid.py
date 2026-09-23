"""Hybrid search (SRC-01, SRC-02): one SQL statement over the chunk table, the keyword and
the vector leg fused by reciprocal rank and reranked, filtered by validity and by what the
caller may see before anything is ranked.

**One statement.** Both legs, every filter and everything a hit shows are one SELECT. The
legs are ranked by window functions over the filtered rows, so the fusion is arithmetic the
database already has the numbers for, and the facts the chunk does not carry — the record's
own heading, its version number, its instrument's short name — come back as correlated
subqueries beside it. Chaining a query per hit would cost a round trip per row and put the
800 ms budget (NFR-02) in the hands of the page size; `SearchHybridQueryCountTests` pins the
count at two page sizes so it can never start growing with the answer.

**A leg either found a row or it did not.** `SEARCH_RETRIEVAL_DEPTH` is how deep each leg
reaches, and `SEARCH_CONCEPT_SCORE_FLOOR` is the least similarity that counts as a concept
match: the vector leg always has a nearest neighbour, however far away, so without a floor
every query would report every embedded chunk as matched by meaning and `matchKind` would
say nothing. What is left is honest: an identifier is won by the words (AC-SRC1), and a
chunk whose vector has not arrived yet is still found by them. A missing vector makes an
answer narrower, never wrong.

**Narrower, never wider.** The read is confined to `owner_tenant_id IS NULL` in code as well
as by the policy, so a row a bank owns cannot be reached by a query written before such a
row existed (D-10, H7). The regulatory scope is chunk 3's one rule — `taxonomy_in_footprint`
over the record's own terms plus its instrument's regime and the jurisdictions its rules
reach, from the SQL twins the obligations list hands the same function — and never a second
copy of it here. Every filter compares a key or an id, so renaming a vocabulary row changes
nothing a caller sent.

**Ties are broken on what a rebuild keeps.** Two chunks may score the same on a leg, and
the rank each gets decides its fused score. Every ranking here therefore breaks a tie on
`TIE_BREAK` — the record's stable key, the kind, the language and the start date — and never
on a uuid, so the same library answers in the same order on every fresh database, which is
what lets the evaluation set gate a release (SRC-05).

**One hit per record.** A duty is indexed once per language it is summarised in, and the
reader asked about the duty. The page therefore carries the chunk whose own language read
the query best and not its translations beside it, which is also why a Swedish query lands
on the Swedish text and a Finnish one on the Finnish text (SRC-S2).

**The query text is the bank's own.** It reaches the text search, the embedder and nothing
else: no log line, no audit row, no outbox payload and no URL (playbook 4.7). `POST /search`
writes nothing at all, which is why its scenarios assert the audit count is unchanged.

**`find_similar` is the same statement, read by an agent.** `POST /search/similar` is the
agents' route (AGT-02): a watch agent sends a passage it fetched and asks which library
records are nearest it. Three things differ from a reader's search, and nothing else does.
A key belongs to no bank, so there is no regulatory scope to apply and no bank to read;
the passage carries no language, so the keyword leg reads it in all five content
configurations rather than one; and there is no `asOf`, so the ranking is taken at today.
The vector leg leads, as it must for a paragraph, and the words catch what it cannot
reach — a chunk whose embedding has not arrived, and a deployment with no embedding model
contracted at all (D-09). Both routes spend from the same per-caller bucket in
`limits.py`: an agent in a retry loop must not cost readers their budget.
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
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.core.exceptions import ValidationError
from django.db.models import (
    BooleanField,
    Case,
    Exists,
    F,
    FloatField,
    Func,
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
from apps.library.reading import instrument_scope_term_ids, scope_term_ids, today_for
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
from apps.shared.errors import ProblemError
from apps.shared.models import Tenant
from apps.taxonomy import matching
from apps.taxonomy.models import InstrumentLevelKind
from apps.watch.models import RegulatoryChange
from apps.watch.reading import _scope_term_ids as change_scope_term_ids  # the feed's own rule, never a copy

# Which chunk a caller means by a hit kind, and which kind a chunk answers as. One mapping,
# read both ways, so a `types` filter and a hit can never disagree about what a chunk is.
SOURCE_OF_HIT: dict[SearchHitType, str] = {
    SearchHitType.OBLIGATION: SearchSource.OBLIGATION_VERSION.value,
    SearchHitType.PROVISION: SearchSource.PROVISION_VERSION.value,
    SearchHitType.CHANGE: SearchSource.CHANGE.value,
}
HIT_OF_SOURCE: dict[str, SearchHitType] = {source: hit for hit, source in SOURCE_OF_HIT.items()}

# What the fused query brings back. The chunk's own `tsv` and `embedding` are deliberately
# not here: they are the two widest columns in the table and nothing above the database
# reads them, so a page of fifty hits does not carry fifty 1024-dimension vectors.
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
# What a tie is broken on wherever rows are ranked: the record's stable key, the kind of
# chunk, its language and the day its text took effect. A rebuilt library reproduces all
# four, where a chunk's or a record's uuid comes out different on every fresh database and
# put two of the evaluation set's questions in another order from one run to the next.
TIE_BREAK = ("record_key", "source_type", "language_id", "valid_from")
WORDS = re.compile(r"\w+", re.UNICODE)
ELLIPSIS = "…"


# ---------------------------------------------------------------------------------------
# POST /search, POST /search/similar
# ---------------------------------------------------------------------------------------
def run_search(body: SearchRequest, *, tenant_id: uuid.UUID | None, user_id: uuid.UUID) -> SearchResponse:
    """`POST /search`. The tenant scopes the footprint filter; the chunks are the
    library's (D-10: only the library is indexed in R1). The reader's own bucket is spent
    before any of it runs, so a runaway client is refused at the door (NFR-02)."""
    limits.search_bucket(user_id)
    tenant = tenant_of(tenant_id)
    as_of = body.as_of or today_for(tenant)
    found = _candidates(
        body.q,
        configurations=(_configuration(body.lang, tenant),),
        types=body.types,
        filters=body.filters or SearchFilters(),
        tenant=tenant,
        as_of=as_of,
        limit=body.limit,
    )
    ranked = _best_per_record(_reranked(body.q, found))
    return SearchResponse(items=[_hit(row, body.q) for row in ranked[: body.limit]], as_of=as_of)


def find_similar(body: SimilarRequest, *, caller_id: uuid.UUID) -> SearchResponse:
    """`POST /search/similar`. The agents' nearest-neighbour read over library chunks
    (AGT-02): no tenant row is read, and none is returned.

    The passage carries no language and no `asOf`, because an agent has neither: it sends
    what it fetched and asks what the library holds near it today. So the words are read
    in every content language's configuration and the ranking is taken at today, UTC.
    """
    limits.search_bucket(caller_id)
    as_of = timezone.localdate()
    found = _candidates(
        body.text,
        configurations=tuple(TEXT_SEARCH_CONFIGS.values()),
        types=body.types,
        filters=SearchFilters(),
        tenant=None,
        as_of=as_of,
        limit=body.limit,
    )
    ranked = _best_per_record(_reranked(body.text, found))
    return SearchResponse(items=[_hit(row, body.text) for row in ranked[: body.limit]], as_of=as_of)


def passages(
    question: str, *, tenant: Tenant, lang: str | None, as_of: datetime.date, depth: int
) -> list[dict[str, Any]]:
    """What Ask may ground an answer in (SRC-03): the obligations the reader's own search
    would rank first for the question, one row per obligation, best first, at most `depth`.

    The same statement, the same regulatory scope and the same "as of" as `POST /search`,
    so an answer can never rest on a record the reader could not have found, and nothing
    outside the bank's scope is read at all. Obligations only, because a citation points at
    an obligation version. A row carries the chunk's whole `body` rather than a snippet,
    since that is the text the model is given. It spends no search bucket: `POST /ask`
    spends its own (`limits.ask_bucket`).

    Never an obligation under a standard (INV-08, D-81). The library holds a standard's
    conformance duty and never its clauses, so a model given that duty for a question about
    a control would answer from what it remembers of licensed text and cite the duty for
    it. Leaving those rows out before anything is ranked is what makes such a question "no
    answer" with no model asked, while `POST /search` still finds the duty.
    """
    found = _candidates(
        question,
        configurations=(_configuration(lang, tenant),),
        types=[SearchHitType.OBLIGATION],
        filters=SearchFilters(),
        tenant=tenant,
        as_of=as_of,
        limit=depth,
        standards=False,
    )
    return _best_per_record(_reranked(question, found))[:depth]


# ---------------------------------------------------------------------------------------
# The one statement
# ---------------------------------------------------------------------------------------
def _candidates(
    text: str,
    *,
    configurations: tuple[str, ...],
    types: list[SearchHitType],
    filters: SearchFilters,
    tenant: Tenant | None,
    as_of: datetime.date,
    limit: int,
    standards: bool = True,
) -> list[dict[str, Any]]:
    """The rows either leg found, best fused first. One query, however many hits."""
    asked = _asked(text, configurations)
    rows = _filtered(types=types, filters=filters, tenant=tenant, as_of=as_of, standards=standards)
    rows = rows.annotate(
        keyword_score=SearchRank(F("tsv"), asked),
        similarity=_similarity(text),
        record_key=_record_key(),
    )
    rows = rows.annotate(
        keyword_rank=Window(RowNumber(), order_by=(F("keyword_score").desc(), *TIE_BREAK)),
        concept_rank=Window(RowNumber(), order_by=(F("similarity").desc(nulls_last=True), *TIE_BREAK)),
    )
    depth = settings.SEARCH_RETRIEVAL_DEPTH
    # Whether the words matched is `@@` and not the rank: `ts_rank` answers 1e-20 rather
    # than nothing for a row the query misses entirely, so a rank above zero would make
    # every chunk in the library a keyword hit for every query.
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
    # Enough for the reranker's window and for the page, whichever is larger, times the
    # languages a record may be summarised in: the page carries one hit per record, and
    # without the multiplier a corpus in five languages could answer a page of twenty with
    # four records and call it the end of the list. The widest columns are left behind
    # (COLUMNS), so the extra rows cost a few kilobytes and no round trip.
    wanted = max(reranker.get_reranker().top_k, limit) * len(TEXT_SEARCH_CONFIGS)
    page = rows.order_by(F("fused").desc(), *TIE_BREAK).values(*COLUMNS)[:wanted]
    return [row for row in page if row["by_keyword"] or row["by_concept"]]


def _asked(text: str, configurations: tuple[str, ...]) -> SearchQuery:
    """The text as PostgreSQL reads it, stemmed in each configuration given and OR-ed.

    A reader tells the screen which language they are reading in, so their search is
    stemmed once, in that language. An agent tells us nothing: it posts a paragraph it
    fetched, in whatever language the supervisor published it. Stemming that as English
    would put a Swedish passage next to no Swedish chunk at all, because the chunk's own
    `tsv` holds Swedish stems, so the passage is read in all five and the tsqueries are
    OR-ed into one. It stays one statement; only the query on the left of `@@` is wider.
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
) -> QuerySet[SearchChunk]:
    """Everything the caller may see and asked for, before a single row is ranked. A filter
    applied after ranking would answer a short page of a long list and call it the answer.
    `standards=False` leaves out every chunk whose instrument sits at a level of the kind
    `standard`: the kind decides, never the level's key (D-81)."""
    rows = SearchChunk.objects.filter(owner_tenant__isnull=True)
    rows = rows.filter(Q(valid_from__isnull=True) | Q(valid_from__lte=as_of))
    rows = rows.filter(Q(valid_to__isnull=True) | Q(valid_to__gte=as_of))
    if types:
        rows = rows.filter(source_type__in=[SOURCE_OF_HIT[kind] for kind in types])
    if filters.instrument_id is not None:
        rows = rows.filter(metadata__instrument_id=str(filters.instrument_id))
    if filters.jurisdiction is not None:
        rows = rows.filter(metadata__jurisdiction=filters.jurisdiction)
    if filters.duty_type is not None:
        rows = rows.filter(metadata__duty_type=filters.duty_type)
    if filters.binding is not None:
        rows = rows.filter(metadata__binding=filters.binding)
    if filters.term_ids:
        rows = rows.filter(metadata__term_ids__contains=[str(term_id) for term_id in filters.term_ids])
    if not standards:
        rows = rows.exclude(
            Exists(
                Instrument.objects.filter(
                    id=_outer_metadata_uuid("instrument_id"), level__kind=InstrumentLevelKind.STANDARD.value
                )
            )
        )
    if tenant is None:
        # The agents' read. An API key belongs to no bank, so there is no regulatory scope
        # to apply — not a wider read, because `owner_tenant_id IS NULL` above has already
        # confined it to the shared library, which is what an agent is asking about.
        return rows
    rows = rows.annotate(in_scope=_in_footprint(tenant))
    # Absent and true are both the bank's standing scope; false is the reader asking to see
    # what the scope holds back, which is the screen's "Search outside our scope".
    return rows.filter(in_scope=filters.in_footprint is not False)


def _in_footprint(tenant: Tenant) -> Func:
    """FP-03's verdict, from the database function the obligations list and the watch feed
    use, over the scope the inventory hands it: `library.reading`'s SQL twins, read for the
    chunk's own record and never copied here. An obligation's chunk is judged by the
    obligation's own terms plus its instrument's scope; a provision's, which has no terms of
    its own, by its instrument's scope alone; a registered change's by the scope the watch
    feed judges it by (`watch.reading`); a chunk that names none of them carries no scope
    and matches every bank. So the regime and the jurisdictions an
    instrument's rules reach (D-28, D-29) narrow a search exactly as they narrow the
    inventory."""
    obligation = Obligation.objects.filter(id=_outer_metadata_uuid("obligation_id")).values(scope=scope_term_ids())
    instrument = Instrument.objects.filter(id=_outer_metadata_uuid("instrument_id")).values(scope=instrument_scope_term_ids())
    change = RegulatoryChange.objects.filter(id=OuterRef("source_id")).values(scope=change_scope_term_ids())
    scope = Coalesce(
        Subquery(obligation[:1]),
        Subquery(instrument[:1]),
        Subquery(change[:1]),
        Value([], output_field=ArrayField(UUIDField())),
        output_field=ArrayField(UUIDField()),
    )
    return Func(
        Value(tenant.id, output_field=UUIDField()),
        scope,
        function=matching.SQL_FUNCTION,
        output_field=BooleanField(),
    )


def _similarity(query: str) -> Any:
    """How near the query the chunk's meaning is, as cosine similarity, or nothing at all
    while no embedding model is contracted (D-09, `EMBEDDER_PROVIDER=none`). A deployment
    without one searches by keyword, which is narrower and still right."""
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
    """The stable key of the record the chunk was built from, the first thing a tie is
    broken on (`TIE_BREAK`): one branch per kind of chunk, a change's included, so ties
    stay broken the day changes are indexed."""
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
    """The record's own heading in the language searched, which is what the screen puts in
    the hit's title: the chunk's own `title` is the citation line the keyword leg is built
    on, and a reader recognises a duty by its words, not by its reference."""
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


# ---------------------------------------------------------------------------------------
# Ranking and the hit
# ---------------------------------------------------------------------------------------
def _reranked(query: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The reranker's verdict on the fused window, added to the fused score.

    A row the reranker did not judge keeps its fused score alone, and since the window is
    the top of the fused order it can never overtake one that was judged. That is what
    makes `RERANKER_PROVIDER=none` a contracted state rather than a broken one: it scores
    every candidate 0.0, and the fused order stands.
    """
    adapter = reranker.get_reranker()
    window = rows[: adapter.top_k]
    judged = (
        {candidate.index: candidate.score for candidate in adapter.rerank(query=query, documents=_documents(window))}
        if window
        else {}
    )
    for index, row in enumerate(rows):
        row["score"] = row["fused"] + judged.get(index, 0.0)
    # sorted() is stable: rows the scores cannot separate keep the database's order, which
    # broke every tie on `TIE_BREAK` and never on an id.
    return sorted(rows, key=lambda row: -row["score"])


def _documents(rows: list[dict[str, Any]]) -> list[str]:
    return [f"{row['heading']}\n\n{row['body']}" for row in rows]


def _best_per_record(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One hit per record: the language that answered the query best.

    A duty is indexed once per language it is summarised in, so a corpus in five languages
    would otherwise answer one obligation five times and fill a page of twenty with four
    records. The reader asked about the duty, not about its translations, and the hit they
    get is the chunk whose own language read their query best (SRC-S2). The card they open
    shows every language the library holds.
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
        # The library's own view of how soon a record deserves attention lives on a
        # registered change (`watch.RegulatoryChange.suggested_urgency`). An obligation
        # and a provision carry none; a change hit does not carry its label yet, which
        # needs the reader's language here, so the change it opens is where it is shown.
        urgency=None,
    )


def _match_kind(row: dict[str, Any]) -> SearchMatchKind:
    if row["by_keyword"] and row["by_concept"]:
        return SearchMatchKind.BOTH
    return SearchMatchKind.CONCEPT if row["by_concept"] else SearchMatchKind.KEYWORD


def _snippet(body: str, query: str) -> str:
    """The chunk's text around what matched, capped by `SEARCH_SNIPPET_CHARS`. A concept
    hit has no word to centre on, so it shows the opening, which is where a summary says
    what it is about."""
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


# ---------------------------------------------------------------------------------------
# The caller
# ---------------------------------------------------------------------------------------
def tenant_of(tenant_id: uuid.UUID | None) -> Tenant:
    """The bank whose scope and time zone a search or a question is read in. A session in no
    bank is a 404 and not a 403, exactly as every other tenant read answers it."""
    tenant = (
        Tenant.objects.filter(pk=tenant_id).first()  # ordering: pk lookup, at most one row
        if tenant_id is not None
        else None
    )
    if tenant is None:
        raise ProblemError(status=404, code="not_found", detail="Sign in to a company to search the library.")
    return tenant


def _configuration(lang: str | None, tenant: Tenant) -> str:
    """The PostgreSQL text search configuration the query is stemmed in: the language the
    caller asked for, else the bank's default content language, else English.

    The language chooses how the query is read, not which chunks are read. A Swedish bank
    reads EU material in five languages (INPUT_DELTAS §3), so a search stemmed as Swedish
    still ranks an English summary that answers it — below the Swedish one, because the
    Swedish text and the Swedish query are stemmed by the same rules (SRC-S2).
    """
    if lang is not None and lang not in TEXT_SEARCH_CONFIGS:
        raise ValidationError(
            f"{lang!r} is not a language of the library. GET /languages lists them.", code="unknown_key"
        )
    return TEXT_SEARCH_CONFIGS.get(str(lang or tenant.default_language_id or ""), "english")
