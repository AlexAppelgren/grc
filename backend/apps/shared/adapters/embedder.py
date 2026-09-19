"""Embedder adapter (playbook 16, DECISIONS D-09): 1024 dimensions, mock in tests. The
real model is chosen against the evaluation set from candidates covering all five
languages; until then the provider list holds only the mock."""

from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod

from django.conf import settings


class EmbedderAdapter(ABC):
    name: str
    dimensions: int

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class MockEmbedder(EmbedderAdapter):
    """Deterministic unit vectors derived from the text's hash, so similar texts are not
    similar (nothing to tune against) but the same text always maps to the same vector."""

    name = "mock"

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            seed = hashlib.sha256(text.encode("utf-8")).digest()
            raw = [((seed[i % len(seed)] / 255.0) * 2 - 1) for i in range(self.dimensions)]
            norm = math.sqrt(sum(value * value for value in raw)) or 1.0
            vectors.append([value / norm for value in raw])
        return vectors


class NoEmbedder(EmbedderAdapter):
    """`EMBEDDER_PROVIDER=none`: no model is contracted yet (D-09), search is keyword-only
    and any attempt to embed fails loudly. Not a mock: it never pretends to answer, which
    is why a deployed environment may run it while TODO_FOR_alex waits on the first key."""

    name = "none"

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("No embedding model is configured (EMBEDDER_PROVIDER=none, D-09)")


PROVIDERS: dict[str, type[EmbedderAdapter]] = {"mock": MockEmbedder, "none": NoEmbedder}


def get_embedder() -> EmbedderAdapter:
    provider = settings.EMBEDDER_PROVIDER
    if provider not in PROVIDERS:
        raise ValueError(f"EMBEDDER_PROVIDER={provider!r} is not one of {sorted(PROVIDERS)}")
    return PROVIDERS[provider](settings.EMBEDDING_DIMENSIONS)
