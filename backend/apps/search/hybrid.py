"""Hybrid search (SRC-01, SRC-02): one SQL statement over the chunk table, keyword and
vector legs fused by reciprocal rank and reranked, filtered by validity before ranking.

Contract only. `c7-hybrid-search-backend` builds these two functions; until it lands they
answer 501 `not_built`, behind the gates api.py already applies (PARALLEL_PLAN rule 3).
Nothing here reads a chunk, calls the embedder or decides how the index is fenced.
"""

from __future__ import annotations

from apps.search.schemas import SearchRequest, SearchResponse, SimilarRequest
from apps.shared.errors import ProblemError

NOT_BUILT = "Search is not switched on yet."


def run_search(body: SearchRequest, *, tenant_id: object) -> SearchResponse:
    """`POST /search`. The tenant scopes the footprint filter; the chunks are the
    library's (D-10: only the library is indexed in R1)."""
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)


def find_similar(body: SimilarRequest) -> SearchResponse:
    """`POST /search/similar`. The agents' nearest-neighbour read over library chunks
    (AGT-02): no tenant row is read, and none is returned."""
    raise ProblemError(status=501, code="not_built", detail=NOT_BUILT)
