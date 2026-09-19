"""Embedder adapter (playbook 16, DECISIONS D-09): 1024 dimensions, mock in tests. The
real model is chosen against the evaluation set from candidates covering all five
languages (ADR 0009); until then the provider list holds only the mock.

The mock has to behave the way a real multilingual model behaves, not the way a hash
does. Chunk 7 builds hybrid search, its scenarios and the evaluation gate against it, and
a hash of the whole text scores every concept question at zero, so nothing about the
vector leg could be tested before the first key arrives. A text's vector is therefore the
sum of two kinds of feature: its hashed stems, which make two texts that share wording a
little alike, and the concepts CONCEPT_TERMS finds in it, which make a Danish question
and the Swedish summary that answers it much alike. Text the table does not know has no
concept and keeps a vector of stem hashes, which is what the mock was before.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from abc import ABC, abstractmethod
from functools import lru_cache

from django.conf import settings

# A concept weighs an order of magnitude more than a stem: a question and a summary that
# say the same thing in two languages share concepts and almost no stems, and a text that
# merely repeats a word should not outrank one that means the same thing.
CONCEPT_WEIGHT = 1.0
STEM_WEIGHT = 0.08
STEM_LENGTH = 7
WORDS = re.compile(r"\w+", re.UNICODE)

# The concept table is test data, sized to the evaluation corpus (backend/eval/) and the
# prototype library it is drawn from, the way a fixture is sized to the tests that read
# it. It is not a lexicon of the five languages and is never a substitute for the model
# D-09 chooses; a real embedder needs none of it. A term matches a word it is contained
# in from four characters up ("varn" matches "varningar", "rådgiv" matches the tail of
# "investeringsrådgivning"), so terms are written as the shortest safe stem; a term of
# three characters or fewer must be the whole word. Several words in a term must appear
# next to each other. A concept counts once however many of its terms a text uses.
CONCEPT_TERMS: dict[str, tuple[str, ...]] = {
    "appropriateness": ("appropriat", "passande", "hensigtsmæssig", "hensiktsmessig", "asianmukaisuus"),
    "complex_instrument": ("complex", "komplicer", "kompleks", "monimutkais"),
    "suitability": ("suitab", "lämplig", "egnet", "egnethet", "soveltuvuus"),
    "investment_advice": ("advice", "advising", "rådgiv", "recommend", "rekommend", "sijoitusneuvo", "neuvonta"),
    "sustainability": ("sustainab", "hållbarhet", "kestävyys"),
    "warning": ("warn", "varn", "advar", "varoit"),
    "nudging": (
        "nudg", "downplay", "encourage", "prominent", "misleading", "despite",
        "uppmuntra", "tona ned", "framträdande", "vilseledande", "klicka", "trots",
    ),
    "costs_charges": ("cost", "charge", "fees", "kostnad", "avgift", "omkostning", "gebyr", "kulu", "veloitu"),
    "periodic": ("annual", "årlig", "vuosittai", "etukäteen", "in good time", "i god tid"),
    "research_payments": ("research", "inducement", "analys", "tutkimus"),
    "product_governance": ("target market", "målgrupp", "distributionsstrateg", "distribusjonsstrateg"),
    "client_assets": (
        "separate", "reconcil", "segreger", "holdings", "åtskild", "stäms", "stämmas",
        "innehav", "adskil", "erottami", "täsmäyt",
    ),
    "investment_savings_account": ("investment savings account", "investeringssparkonto", "isk"),
    "approved_assets": ("approved", "godkänd"),
    "standard_income": ("standard income", "schablonintäkt", "kontrolluppgift", "skatteverket", "control statement"),
    "insurance_based_product": ("insurance based", "insurance-based", "försäkringsbaserad", "vakuutusmuoto"),
    "demands_and_needs": ("demands and needs", "krav och behov", "vaatimukset ja tarpeet"),
    "switch_underlying": ("switch", "underlying", "underliggande", "underliggende", "byte", "bytet", "bytte"),
    "documentation": ("document", "dokument"),
    "key_information_document": ("key information", "faktablad", "investorinformation", "avaintieto"),
    "before_bound": ("bound", "bunden", "bundna", "binder"),
    "pension_transfer": ("transfer", "flytt", "pension", "pensjon", "policyholder"),
    "ict_third_party": (
        "ict", "ikt", "cloud", "moln", "outsourc", "vendor", "dora",
        "leverantör", "leverandør", "palveluntarjoaj",
    ),
    "register": ("register", "rekisteri", "förteckning"),
    "automated_decision": ("automat", "profiling", "human", "mänsklig", "människa", "beslut", "afgørelse"),
}


def _words(text: str) -> list[str]:
    return WORDS.findall(unicodedata.normalize("NFKC", text).casefold())


# CONCEPT_TERMS split into words once, at import, because concepts() runs per text.
_TERMS: dict[str, tuple[tuple[str, ...], ...]] = {
    concept: tuple(tuple(_words(term)) for term in terms) for concept, terms in CONCEPT_TERMS.items()
}


def _word_matches(term: str, word: str) -> bool:
    return term in word if len(term) >= 4 else term == word


def _term_matches(term: tuple[str, ...], words: list[str]) -> bool:
    return any(
        all(_word_matches(part, words[start + offset]) for offset, part in enumerate(term))
        for start in range(len(words) - len(term) + 1)
    )


def concepts(text: str) -> list[str]:
    """The concepts CONCEPT_TERMS finds in the text, in table order. Empty for text the
    table does not know, which is most text, and for an identifier such as "FFFS 2017:2":
    an identifier is won by the keyword leg (AC-SRC1), never by this."""
    words = _words(text)
    return [concept for concept, terms in _TERMS.items() if any(_term_matches(term, words) for term in terms)]


@lru_cache(maxsize=4096)
def _feature_vector(feature: str, dimensions: int) -> tuple[float, ...]:
    """A unit vector for one feature, the same one on every machine and every run. SHAKE-256
    gives as many bytes as the dimension asks for from one hash."""
    raw = hashlib.shake_256(feature.encode("utf-8")).digest(dimensions)
    values = [(byte - 127.5) / 127.5 for byte in raw]
    norm = math.sqrt(sum(value * value for value in values))
    return tuple(value / norm for value in values)


class EmbedderAdapter(ABC):
    name: str
    dimensions: int

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class MockEmbedder(EmbedderAdapter):
    """Deterministic: the same text always maps to the same unit vector. Concept-aware:
    texts that mean the same thing in different languages point the same way."""

    name = "mock"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        features = [(f"concept:{concept}", CONCEPT_WEIGHT) for concept in concepts(text)]
        features += [(f"stem:{stem}", STEM_WEIGHT) for stem in {word[:STEM_LENGTH] for word in _words(text)}]
        total = [0.0] * self.dimensions
        for feature, weight in features:
            for index, value in enumerate(_feature_vector(feature, self.dimensions)):
                total[index] += weight * value
        norm = math.sqrt(sum(value * value for value in total))
        if not norm:  # text with no word at all: the hash of the text itself, as before.
            return list(_feature_vector(text, self.dimensions))
        return [value / norm for value in total]


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
