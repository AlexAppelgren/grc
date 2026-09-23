"""LLM adapter (playbook 16, DECISIONS D-07). `anthropic` is the Messages API over the
standard library's HTTP client; `mock` answers from the prompt's own context chunks;
`bedrock` is named now and implemented when D-07's EU path is contracted.

The wire shape was fetched from the provider's documentation on 2026-09-19 and each claim
relied on has a row in docs/plans/Verification_Log.md: `POST /v1/messages` with the key in
`x-api-key` (the documented fallback for `Authorization`, still supported) and the
required `anthropic-version` and `content-type`; the SSE event flow of `message_start` /
`content_block_delta` / `message_delta` / `message_stop`; usage that is cumulative, and
the stop reason, on `message_delta`; errors that arrive mid-stream as an `error` event
after a 200; a refusal that can arrive after partial output, which is then incomplete and
discarded; and unknown event types that must be handled gracefully (versioning policy).
Every call is streamed, which is also the documentation's advice for anything with a
large `max_tokens`, so there is one transport path: `complete()` consumes `stream()`.

Whatever comes off the network is untrusted (security review of E3, 2026-09-19): a
redirect is refused, a body is read within a byte limit and before a deadline, every value
copied out of it is checked for its type, and any failure to read it is an `LlmError`.

No prompt and no answer ever reaches a log, Sentry or an exception message; an API error
contributes its `type` only, because its `message` can quote the request. The API key is
read from the environment and appears nowhere else.

No tenant-zone text is sent to a model except the question typed into Ask, which a tenant
can switch off (D-07). That rule lives in the caller, not here; this module only moves
prompts. Every real call writes `ai_generation` (AUD-02) from the caller too.
"""

from __future__ import annotations

import http.client
import json
import logging
import re
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from typing import IO, Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"
# The statuses the provider's own SDK retries: 408 (RFC 9110: the server stopped waiting
# for the request, which may be repeated), 409, 429 and the 5xx family. 400, 401, 403,
# 404 and 413 are ours to fix, so retrying them only spends money.
RETRYABLE_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504, 529})
# `retry-after` as delay-seconds (RFC 9110 10.2.3) in ASCII digits. "²" passes
# str.isdigit() and then fails float(); an HTTP-date falls back to the backoff.
_RETRY_AFTER = re.compile(r"[0-9]{1,6}")
# The only shape in which a provider kind (an error type, a stop reason) is copied out.
_KIND = re.compile(r"[a-z_]{1,64}")
# What reading a body off the network can raise: the connection, a read timeout included
# (OSError); the HTTP framing (HTTPException); bytes that are not UTF-8 JSON (ValueError);
# JSON of the wrong shape (AttributeError, TypeError).
_UNREADABLE = (OSError, http.client.HTTPException, ValueError, AttributeError, TypeError)


class LlmError(RuntimeError):
    """The model could not answer. Carries a status and an error kind, never the prompt,
    the answer, the provider's message or the key."""


@dataclass(frozen=True)
class Completion:
    """A whole answer. `stop_reason` is the provider's: `end_turn` when the model finished,
    `max_tokens` or `model_context_window_exceeded` when the answer was cut off, which the
    call's AI log row records (`stop_reason`). A refusal never becomes a Completion: it
    raises."""

    text: str
    model: str
    model_version: str
    input_tokens: int
    output_tokens: int
    stop_reason: str


class LlmAdapter(ABC):
    name: str

    @abstractmethod
    def stream(self, *, system: str, prompt: str, max_tokens: int) -> Iterator[str | Completion]:
        """Yield each text delta as it arrives, then one `Completion` carrying the whole
        answer, its usage and its stop reason. The `Completion` is always the last event;
        a stream that cannot end in one raises `LlmError` instead, and the deltas already
        yielded are then not a whole answer: the caller never treats them as one."""

    def complete(self, *, system: str, prompt: str, max_tokens: int) -> Completion:
        for event in self.stream(system=system, prompt=prompt, max_tokens=max_tokens):
            if isinstance(event, Completion):
                return event
        raise LlmError("the model stream ended before the answer was complete")

    def asked_model(self) -> tuple[str, str]:
        """The model and version a call is addressed to. A finished call is logged with
        what its `Completion` reports instead; this names the model on the log row of a
        call that never reached one: a stream the reader left early, or one that failed
        (AUD-02)."""
        raise NotImplementedError(f"the {self.name} provider does not name the model it asks")


# ---------------------------------------------------------------------------------------
# The prompt's context chunks. Ask retrieves chunks and renders them with `format_context`;
# an answer cites chunk n as "[n]" (AC-SRC2). The mock reads the same markers back, which
# is what makes it grounded rather than inventive.
# ---------------------------------------------------------------------------------------
CONTEXT_LINE = re.compile(r"^\[(\d+)\] (.+)$", re.MULTILINE)
_FIRST_SENTENCE = re.compile(r"^(.*?\.)(?:\s|$)")


def format_context(chunks: list[str]) -> str:
    """One numbered line per chunk, numbered from 1, so a citation is a position."""
    return "\n".join(f"[{number}] {' '.join(chunk.split())}" for number, chunk in enumerate(chunks, start=1))


def _first_sentence(text: str) -> str:
    match = _FIRST_SENTENCE.match(text)
    return match.group(1) if match else text


class MockLlm(LlmAdapter):
    """Deterministic and grounded: it answers only from the context chunks in the prompt,
    one statement per chunk with its `[n]` marker, and says nothing at all when the prompt
    carries no chunks. Ask's scenarios assert on that answer (SRC-S4, SRC-S5) without a
    model call, and a deployed environment refuses this provider at boot."""

    name = "mock"

    def asked_model(self) -> tuple[str, str]:
        return "mock", "0"

    def stream(self, *, system: str, prompt: str, max_tokens: int) -> Iterator[str | Completion]:
        statements = [f"{_first_sentence(text)} [{number}]" for number, text in CONTEXT_LINE.findall(prompt)]
        for index, statement in enumerate(statements):
            yield statement if index == len(statements) - 1 else f"{statement} "
        text = " ".join(statements)
        yield Completion(
            text=text,
            model="mock",
            model_version="0",
            input_tokens=len(prompt.split()),
            output_tokens=len(text.split()),
            stop_reason="end_turn",
        )


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """The Messages API does not redirect. urllib's own handler turns a 301, 302 or 303
    answer to a POST into a GET to the `location` carrying the request's headers, so a
    redirect is a failed status like any other (security review of E3, 2026-09-19)."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)


_OPENER = urllib.request.build_opener(_RefuseRedirects)


def _open(request: urllib.request.Request, timeout: float) -> Any:
    """The one call that reaches the network, so a test can replace it with a transport
    that never leaves the machine."""
    return _OPENER.open(request, timeout=timeout)


def _kind(value: object) -> str:
    """A provider kind as the snake_case word it is documented to be, or `unknown`: it is
    copied into an error message or a record, so nothing else off the network rides along."""
    return value if isinstance(value, str) and _KIND.fullmatch(value) else "unknown"


def _typed[T](value: object, kind: type[T]) -> T:
    """A value copied out of the stream has the type the documentation gives it."""
    if not isinstance(value, kind):
        raise TypeError(f"a {kind.__name__} was expected")
    return value


def _error_type(error: urllib.error.HTTPError) -> str:
    """The failing response's `error.type` and nothing else: its `message` can quote the
    request, and the body comes off the network, so it is read only so far and nothing
    about its shape is assumed."""
    try:
        payload = json.loads(error.read(settings.LLM_MAX_ERROR_BODY_BYTES).decode("utf-8"))
    except (OSError, http.client.HTTPException, ValueError):
        return "unreadable"
    reported = payload.get("error") if isinstance(payload, dict) else None
    return _kind(reported.get("type")) if isinstance(reported, dict) else "unknown"


def _delay(attempt: int, retry_after: str | None) -> float:
    """`retry-after` is honoured when the provider sends a plain number of seconds, and is
    never allowed to hold the request longer than one socket read may take."""
    seconds = (retry_after or "").strip()
    if _RETRY_AFTER.fullmatch(seconds):
        return min(float(seconds), settings.LLM_TIMEOUT_S)
    return settings.LLM_RETRY_BACKOFF_S * (2**attempt)


def _may_retry(attempt: int, delay: float, deadline: float) -> bool:
    """Within the setting's count, and only when the wait ends before the call's deadline."""
    return attempt < settings.LLM_MAX_RETRIES and time.monotonic() + delay <= deadline


def _lines(response: Any, deadline: float) -> Iterator[bytes]:
    """The body's lines, read one socket read at a time so both limits hold while the
    stream is still arriving: no read starts after the deadline, so a call ends within
    LLM_DEADLINE_S plus one LLM_TIMEOUT_S, and no more than LLM_MAX_RESPONSE_BYTES is read
    in all, so no line can be longer either."""
    budget = settings.LLM_MAX_RESPONSE_BYTES
    pending = b""
    while True:
        if time.monotonic() > deadline:
            raise LlmError("the model API did not finish before the call's deadline")
        chunk = response.read1()
        if not chunk:
            break
        budget -= len(chunk)
        if budget < 0:
            raise LlmError("the model API sent more than the response limit")
        *complete, pending = (pending + chunk).split(b"\n")
        yield from complete
    if pending:
        yield pending


def _read_events(response: Any, deadline: float) -> Iterator[str | Completion]:
    """Parse the SSE body. The `event:` lines are ignored: every event repeats its name in
    the JSON of its `data:` line, and an event type this code does not know is skipped.
    The stream ends in a Completion or raises; it never just stops."""
    model = settings.LLM_MODEL
    input_tokens = 0
    output_tokens = 0
    stop_reason: str | None = None
    parts: list[str] = []
    for raw_line in _lines(response, deadline):
        line = raw_line.decode("utf-8").strip()
        if not line.startswith("data:"):
            continue
        event = json.loads(line[len("data:") :])
        kind = event.get("type")
        if kind == "message_start":
            message = event.get("message", {})
            model = _typed(message.get("model", model), str)
            input_tokens = _typed(message.get("usage", {}).get("input_tokens", 0), int)
        elif kind == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                parts.append(_typed(delta.get("text", ""), str))
                yield parts[-1]
        elif kind == "message_delta":
            # Documented as cumulative, so the last one wins rather than a running total.
            output_tokens = _typed(event.get("usage", {}).get("output_tokens", output_tokens), int)
            reason = event.get("delta", {}).get("stop_reason")
            if reason is not None:
                stop_reason = _kind(reason)
            if stop_reason == "refusal":
                # The model declined, possibly after partial output, which the provider
                # says is incomplete and discarded: the caller gets no Completion.
                raise LlmError("the model declined to answer (refusal)")
        elif kind == "error":
            raise LlmError(f"the model API failed mid-stream ({_kind(event.get('error', {}).get('type'))})")
        elif kind == "message_stop":
            if stop_reason is None:
                raise LlmError("the model stream ended without a stop reason")
            yield Completion(
                text="".join(parts),
                model=model,
                model_version=ANTHROPIC_API_VERSION,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                stop_reason=stop_reason,
            )
            return
    raise LlmError("the model stream ended before the answer was complete")


class AnthropicLlm(LlmAdapter):
    """`model_version` is the API version the answer was produced under; the resolved model
    id the response reports is `model`. Both go on the `ai_generation` row (AUD-02)."""

    name = "anthropic"

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ImproperlyConfigured("ANTHROPIC_API_KEY is not set; it is read from the environment only")
        self._api_key = api_key

    def asked_model(self) -> tuple[str, str]:
        return settings.LLM_MODEL, ANTHROPIC_API_VERSION

    def stream(self, *, system: str, prompt: str, max_tokens: int) -> Iterator[str | Completion]:
        deadline = time.monotonic() + settings.LLM_DEADLINE_S
        body = {
            "model": settings.LLM_MODEL,
            # A setting is the ceiling, so no caller can spend more than the budget allows.
            "max_tokens": min(max_tokens, settings.LLM_MAX_TOKENS),
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
        request = urllib.request.Request(  # noqa: S310 the URL is this module's own https constant
            ANTHROPIC_MESSAGES_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={"anthropic-version": ANTHROPIC_API_VERSION, "content-type": "application/json"},
            method="POST",
        )
        # Never copied onto a redirected request, should an opener ever follow one.
        request.add_unredirected_header("x-api-key", self._api_key)
        with self._open_with_retries(request, deadline) as response:
            try:
                yield from _read_events(response, deadline)
            except _UNREADABLE as exc:
                # Once the body has started nothing is retried: the caller may already hold
                # deltas, and a second answer would be spliced onto the first.
                raise LlmError(f"the model API sent a stream that could not be read ({type(exc).__name__})") from exc

    def _open_with_retries(self, request: urllib.request.Request, deadline: float) -> Any:
        """Retries happen here, before the body starts, and nowhere else: a transient
        status, or a connection that failed, was reset or answered with a broken status."""
        attempt = 0
        while True:
            try:
                return _open(request, settings.LLM_TIMEOUT_S)
            except urllib.error.HTTPError as exc:
                delay = _delay(attempt, exc.headers.get("retry-after"))
                if exc.code not in RETRYABLE_STATUSES or not _may_retry(attempt, delay, deadline):
                    raise LlmError(f"the model API returned {exc.code} ({_error_type(exc)})") from exc
            except (OSError, http.client.HTTPException) as exc:
                delay = _delay(attempt, None)
                if not _may_retry(attempt, delay, deadline):
                    raise LlmError("the model API could not be reached") from exc
            logger.warning("the model API call was retried", extra={"attempt": attempt + 1})
            time.sleep(delay)
            attempt += 1


class BedrockLlm(LlmAdapter):
    name = "bedrock"

    def stream(self, *, system: str, prompt: str, max_tokens: int) -> Iterator[str | Completion]:
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
