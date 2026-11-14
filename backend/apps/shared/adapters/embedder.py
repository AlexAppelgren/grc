"""Embedder adapter (playbook 16, DECISIONS D-09): 1024 dimensions, mock in tests. The real
model is chosen against the evaluation set (ADR 0009); until then only the mock exists.

The mock behaves like a multilingual model rather than a hash, so hybrid search and its
evaluation gate can be tested: a text's vector sums its hashed stems (shared wording is a
little alike) and the concepts CONCEPT_TERMS finds in it (a Danish question and the Swedish
summary answering it are much alike). Unknown text keeps a vector of stem hashes.
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

# Test data sized to the evaluation corpus (backend/eval/), not a lexicon; a real embedder
# needs none of it. A term matches a word containing it from four characters up, so terms
# are the shortest safe stem; one of three characters or fewer must be the whole word.
# A multi-word term matches adjacent words; a concept counts once per text.
# The stems of German, Dutch, Estonian, Latvian and Lithuanian come last in an entry (D-145):
# those the questions in these languages need and no others. Each is the term of the EU act
# in its language, kept long enough to stay out of the other nine: "komplex" is in Swedish
# "komplexitet", "kosten" in Finnish "katkosten", and "Angemessenheit" alone is also the
# adequacy of a bank's capital.
CONCEPT_TERMS: dict[str, tuple[str, ...]] = {
    "appropriateness": (
        "appropriat", "passande", "hensigtsmæssig", "hensiktsmessig", "asianmukaisuus",
        "angemessenheitsprüf", "passendheid", "asjakohasus", "atbilstības novērtē", "priimtinum",
    ),
    "complex_instrument": (
        "complex", "komplicer", "kompleks", "monimutkais",
        "komplexe", "keeruka", "sarežģīt",
    ),
    "suitability": (
        "suitab", "suits", "lämplig", "egnet", "egnethet", "soveltuvuus",
        "geeignetheit", "sobivus", "piemērotīb",
    ),
    "investment_advice": (
        "advice", "advising", "rådgiv", "recommend", "rekommend", "sijoitusneuvo", "neuvonta",
        "anlageberat", "investeerimisnõust", "ieguldījumu konsultāc",
    ),
    "sustainability": ("sustainab", "hållbarhet", "kestävyys", "jätkusuutlik", "ilgtspēj"),
    "warning": ("warn", "varn", "advar", "varoit", "waarschuw", "įspė"),
    "nudging": (
        "nudg", "downplay", "encourage", "prominent", "misleading", "despite",
        "uppmuntra", "tona ned", "framträdande", "vilseledande", "klicka", "trots",
    ),
    "costs_charges": (
        "cost", "charge", "fees", "kostnad", "avgift", "omkostning", "gebyr", "kulu", "veloitu",
        "kosten und", "gebühr", "kosten en lasten", "izmaks un", "išlaid",
    ),
    "periodic": (
        "annual", "årlig", "vuosittai", "etukäteen", "in good time", "i god tid",
        "jährlich", "kord aastas", "kasmet",
    ),
    "research_payments": (
        "research", "inducement", "analys", "tutkimus",
        "onderzoek op beleggingsgebied", "ieguldījumu izpēt",
    ),
    "product_governance": (
        "target market", "målgrupp", "distributionsstrateg", "distribusjonsstrateg",
        "zielmarkt", "vertriebsstrategie", "tikslin rink", "platinimo strategij",
    ),
    "client_assets": (
        "separate", "reconcil", "segreger", "holdings", "åtskild", "stäms", "stämmas",
        "innehav", "adskil", "erottami", "täsmäyt",
        "getrennte verwahrung", "abgleich", "lahus hoid", "atskyrim",
    ),
    "investment_savings_account": ("investment savings account", "investeringssparkonto", "isk"),
    "approved_assets": ("approved", "godkänd"),
    "standard_income": ("standard income", "schablonintäkt", "kontrolluppgift", "skatteverket", "control statement"),
    "insurance_based_product": (
        "insurance based", "insurance-based", "försäkringsbaserad", "vakuutusmuoto",
        "kindlustuspõhi", "beleggingscomponent",
    ),
    "demands_and_needs": (
        "demands and needs", "krav och behov", "vaatimukset ja tarpeet",
        "nõudmis ja vajadus", "verlangens en behoeften",
    ),
    "switch_underlying": (
        "switch", "underlying", "underliggande", "underliggende", "byte", "bytet", "bytte",
        "pagrindinių investicij",
    ),
    "documentation": ("document", "dokument"),
    "key_information_document": (
        "key information", "faktablad", "investorinformation", "avaintieto",
        "basisinformationsbl", "informatiedocument", "põhiteabe", "pamatinformācijas dokument",
        "pagrindinės informacijos dokument",
    ),
    "before_bound": ("bound", "bunden", "bundna", "binder"),
    "pension_transfer": (
        "transfer", "flytt", "pension", "pensjon", "policyholder",
        "waardeoverdracht", "pensioen", "pensij",
    ),
    "ict_third_party": (
        "ict", "ikt", "cloud", "moln", "outsourc", "vendor", "dora",
        "leverantör", "leverandør", "palveluntarjoaj",
        "irt",
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
