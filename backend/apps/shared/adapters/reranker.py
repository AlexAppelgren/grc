"""Reranker adapter (playbook 16, DECISIONS D-09, SRC-01). Hybrid search fuses the keyword
and vector legs by reciprocal rank and reranks the top window; the window and the provider
are settings, so swapping the model is a measured change (ADR 0009) and never a code change.

`mock` scores by how much of the question a candidate repeats: enough for chunk 7's
scenarios to prove the reranker ran, never a real model. `none` is the contracted state
until D-09 names one: the fused order stands, which is the sub-800 ms budget in playbook 10.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from django.conf import settings

WORDS = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class RerankedCandidate:
    """Where the candidate sat in the fused list, and what the reranker made of it. A score
    of 0.0 means the reranker found nothing to prefer, so the fused order decides."""

    index: int
    score: float


class RerankerAdapter(ABC):
    name: str
    top_k: int

    def __init__(self, top_k: int) -> None:
        self.top_k = top_k

    @abstractmethod
    def rerank(self, *, query: str, documents: list[str]) -> list[RerankedCandidate]: ...


class MockReranker(RerankerAdapter):
    """The share of the question's words the candidate repeats. Deterministic, and stable:
    candidates the reranker cannot separate keep the order the fusion gave them."""

    name = "mock"

    def rerank(self, *, query: str, documents: list[str]) -> list[RerankedCandidate]:
        asked = set(WORDS.findall(query.casefold()))
        scored = [
            RerankedCandidate(index, len(asked & set(WORDS.findall(document.casefold()))) / len(asked) if asked else 0.0)
            for index, document in enumerate(documents)
        ]
        return sorted(scored, key=lambda candidate: -candidate.score)[: self.top_k]


class NoReranker(RerankerAdapter):
    """`RERANKER_PROVIDER=none`: no reranker is contracted (D-09), so the fused order is the
    answer. Not a mock, it never pretends to have judged: every score is 0.0."""

    name = "none"

    def rerank(self, *, query: str, documents: list[str]) -> list[RerankedCandidate]:
        return [RerankedCandidate(index, 0.0) for index in range(len(documents))][: self.top_k]


PROVIDERS: dict[str, type[RerankerAdapter]] = {"mock": MockReranker, "none": NoReranker}


def get_reranker() -> RerankerAdapter:
    provider = settings.RERANKER_PROVIDER
    if provider not in PROVIDERS:
        raise ValueError(f"RERANKER_PROVIDER={provider!r} is not one of {sorted(PROVIDERS)}")
    return PROVIDERS[provider](settings.RERANKER_TOP_K)
