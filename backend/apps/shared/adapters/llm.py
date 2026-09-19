"""LLM adapter (playbook 16, DECISIONS D-07). `mock` answers deterministically; `anthropic`
and `bedrock` are named now and implemented in chunk 7 (Ask) after fetching current docs.

No tenant-zone text is sent to a model except the question typed into Ask, which a
tenant can switch off (D-07). That rule lives in the caller, not here; this module only
moves prompts. Every real call writes `ai_generation` (AUD-02) from the caller too.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    model_version: str
    input_tokens: int
    output_tokens: int


class LlmAdapter(ABC):
    name: str

    @abstractmethod
    def complete(self, *, system: str, prompt: str, max_tokens: int) -> Completion: ...


class MockLlm(LlmAdapter):
    """Deterministic: the same prompt always yields the same text, so E2E journeys and
    the evaluation harness can assert on it."""

    name = "mock"

    def complete(self, *, system: str, prompt: str, max_tokens: int) -> Completion:
        digest = hashlib.sha256((system + "\n" + prompt).encode("utf-8")).hexdigest()[:12]
        return Completion(
            text=f"[mock completion {digest}]",
            model="mock",
            model_version="0",
            input_tokens=len(prompt.split()),
            output_tokens=3,
        )


class AnthropicLlm(LlmAdapter):
    name = "anthropic"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def complete(self, *, system: str, prompt: str, max_tokens: int) -> Completion:
        raise NotImplementedError("Anthropic provider lands in chunk 7 (Search and ask)")


class BedrockLlm(LlmAdapter):
    name = "bedrock"

    def complete(self, *, system: str, prompt: str, max_tokens: int) -> Completion:
        raise NotImplementedError("Bedrock provider lands when D-07's EU path is contracted")


PROVIDERS: dict[str, type[LlmAdapter]] = {
    "mock": MockLlm,
    "anthropic": AnthropicLlm,
    "bedrock": BedrockLlm,
}


def get_llm() -> LlmAdapter:
    provider = settings.LLM_PROVIDER
    if provider == "anthropic":
        return AnthropicLlm(api_key=settings.ANTHROPIC_API_KEY)
    if provider not in PROVIDERS:
        raise ValueError(f"LLM_PROVIDER={provider!r} is not one of {sorted(PROVIDERS)}")
    return PROVIDERS[provider]()
