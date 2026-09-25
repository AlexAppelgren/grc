"""LLM adapter: the Anthropic provider and the grounded mock (playbook 16, D-07, E3).

Every Anthropic case runs against a stubbed transport (`llm._open`) except two, which run
the real opener against a server on 127.0.0.1: the redirect case and a chunked stream.
The provider is never called from a test. The cases prove the wire shape fetched from the provider's documentation on
2026-09-19 (docs/plans/Verification_Log.md): the headers, `stream: true`, the SSE event
flow, cumulative usage and the stop reason on `message_delta`, a refusal that can follow
partial output, mid-stream error events, unknown events ignored per the versioning
policy, and the retry classes. They also pin what a body off the network cannot make the
adapter do (security review of E3, 2026-09-19): send the key after a redirect, end a
stream with neither a completion nor an error, fail as anything but `LlmError`, retry
once the answer has started, or read past the size and time limits.

The mock's cases pin what Ask's scenarios assert on (SRC-S4, SRC-S5): an answer built only
from the numbered context chunks in the prompt, one cited statement each, nothing at all
when the prompt carries no chunks.
"""

from __future__ import annotations

import email.message
import http.client
import http.server
import io
import json
import threading
import urllib.error
from collections.abc import Iterable, Iterator
from typing import Any
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from apps.shared.adapters import llm

API_KEY = "anthropic-test-key"


def _sse(*events: tuple[str, dict[str, Any]]) -> list[bytes]:
    """The wire form: an `event:` line, a `data:` line, a blank line."""
    lines: list[bytes] = []
    for name, data in events:
        lines.append(f"event: {name}\n".encode())
        lines.append(f"data: {json.dumps(data, ensure_ascii=False)}\n".encode())
        lines.append(b"\n")
    return lines


def _hello_stream(text: str = "Hello", output_tokens: int = 15, stop_reason: str = "end_turn") -> list[bytes]:
    return _sse(
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "content": [],
                    "model": "claude-opus-5",
                    "stop_reason": None,
                    "usage": {"input_tokens": 25, "output_tokens": 1},
                },
            },
        ),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        ("ping", {"type": "ping"}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": output_tokens},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    )


class _StubResponse:
    """What the opener gives back: a context manager read one `read1` at a time. Each item
    of `reads` is what one read returns, or an exception that read raises; after the last
    item the body reads as b"", the end of the stream."""

    def __init__(self, reads: Iterable[bytes | BaseException]) -> None:
        self.reads = iter(reads)
        self.closed = False

    def __enter__(self) -> _StubResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        self.closed = True

    def read1(self, size: int = -1) -> bytes:
        read = next(self.reads, b"")
        if isinstance(read, BaseException):
            raise read
        return read


class _Clock:
    """Stands in for the `time` module inside `llm`: `sleep` records the wait and moves the
    clock on, so retries and the deadline are tested without waiting."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def _http_error(code: int, error_type: str, retry_after: str | None = None) -> urllib.error.HTTPError:
    """A real `HTTPError`, so the adapter's own except clauses are the ones under test."""
    headers = email.message.Message()
    if retry_after is not None:
        headers["retry-after"] = retry_after
    body = json.dumps(
        {"type": "error", "error": {"type": error_type, "message": "a message that may quote the prompt"}}
    ).encode("utf-8")
    return urllib.error.HTTPError(
        url=llm.ANTHROPIC_MESSAGES_URL, code=code, msg="error", hdrs=headers, fp=io.BytesIO(body)
    )


class _Transport:
    """Replaces `llm._open`: returns each queued outcome in turn and records the requests."""

    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[Any] = []

    def __call__(self, request: Any, timeout: float) -> Any:
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    @property
    def body(self) -> dict[str, Any]:
        return json.loads(self.requests[-1].data.decode("utf-8"))


def _stub(*outcomes: Any) -> tuple[_Transport, Any]:
    transport = _Transport(*outcomes)
    return transport, mock.patch.object(llm, "_open", transport)


def _serve(test: SimpleTestCase, handler: type[http.server.BaseHTTPRequestHandler]) -> str:
    """Runs `handler` on 127.0.0.1 for the length of the test and returns its origin."""
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    test.addCleanup(server.server_close)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    test.addCleanup(server.shutdown)
    return f"http://127.0.0.1:{server.server_port}"


@override_settings(LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY=API_KEY, LLM_RETRY_BACKOFF_S=0.0)
class AnthropicProvider(SimpleTestCase):
    def setUp(self) -> None:
        self.clock = _Clock()
        mock.patch.object(llm, "time", self.clock).start()
        self.addCleanup(mock.patch.stopall)

    def test_the_request_carries_the_three_required_headers_and_the_key(self) -> None:
        transport, patched = _stub(_StubResponse(_hello_stream()))
        with patched:
            llm.get_llm().complete(system="s", prompt="p", max_tokens=10)
        request = transport.requests[0]
        self.assertEqual(request.full_url, llm.ANTHROPIC_MESSAGES_URL)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("X-api-key"), API_KEY)
        self.assertEqual(request.get_header("Anthropic-version"), llm.ANTHROPIC_API_VERSION)
        self.assertEqual(request.get_header("Content-type"), "application/json")

    def test_the_key_is_a_header_no_redirected_request_would_carry(self) -> None:
        transport, patched = _stub(_StubResponse(_hello_stream()))
        with patched:
            llm.get_llm().complete(system="s", prompt="p", max_tokens=10)
        request = transport.requests[0]
        self.assertEqual(request.unredirected_hdrs.get("X-api-key"), API_KEY)
        self.assertNotIn("X-api-key", request.headers)

    @override_settings(LLM_MAX_RETRIES=0)
    def test_a_redirect_is_refused_so_neither_the_request_nor_the_key_follows_it(self) -> None:
        # urllib's default handler turns a 301, 302 or 303 answer to a POST into a GET to
        # the `location` carrying the request's headers, the key among them (security
        # review of E3, 2026-09-19). The real opener, against a server on this machine.
        seen: list[tuple[str, str | None]] = []
        location = ""

        class Redirector(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                seen.append((self.path, self.headers.get("x-api-key")))
                self.send_response(302)
                self.send_header("Location", location)
                self.send_header("Content-Length", "0")
                self.end_headers()

            do_GET = do_POST

            def log_message(self, format: str, *args: Any) -> None:
                """Quiet: the test asserts on `seen`."""

        origin = _serve(self, Redirector)
        location = f"{origin}/elsewhere"
        with (
            mock.patch.object(llm, "ANTHROPIC_MESSAGES_URL", f"{origin}/v1/messages"),
            self.assertRaises(llm.LlmError) as raised,
        ):
            llm.get_llm().complete(system="s", prompt="p", max_tokens=10)
        self.assertIn("302", str(raised.exception))
        self.assertEqual(seen, [("/v1/messages", API_KEY)])

    def test_the_real_opener_reads_a_chunked_stream_one_read_at_a_time(self) -> None:
        # The stubs stand in for `read1`; this proves it on http.client's own response,
        # with the body in chunks that split lines and letters.
        body = b"".join(_hello_stream(text="Förbudet gäller"))

        class Streamer(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self) -> None:
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Connection", "close")
                self.end_headers()
                for start in range(0, len(body), 50):
                    chunk = body[start : start + 50]
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                self.wfile.write(b"0\r\n\r\n")

            def log_message(self, format: str, *args: Any) -> None:
                """Quiet: the test asserts on the completion."""

        origin = _serve(self, Streamer)
        with mock.patch.object(llm, "ANTHROPIC_MESSAGES_URL", f"{origin}/v1/messages"):
            completion = llm.get_llm().complete(system="s", prompt="p", max_tokens=10)
        self.assertEqual(completion.text, "Förbudet gäller")
        self.assertEqual(completion.stop_reason, "end_turn")

    @override_settings(LLM_MODEL="claude-opus-5", LLM_MAX_TOKENS=1000)
    def test_the_body_is_a_streaming_messages_request_built_from_the_settings(self) -> None:
        transport, patched = _stub(_StubResponse(_hello_stream()))
        with patched:
            llm.get_llm().complete(system="only the library", prompt="a question", max_tokens=200)
        self.assertEqual(
            transport.body,
            {
                "model": "claude-opus-5",
                "max_tokens": 200,
                "system": "only the library",
                "messages": [{"role": "user", "content": "a question"}],
                "stream": True,
            },
        )

    @override_settings(LLM_MAX_TOKENS=64)
    def test_the_max_tokens_setting_is_a_ceiling_a_caller_cannot_raise(self) -> None:
        transport, patched = _stub(_StubResponse(_hello_stream()))
        with patched:
            llm.get_llm().complete(system="s", prompt="p", max_tokens=100_000)
        self.assertEqual(transport.body["max_tokens"], 64)

    def test_streaming_yields_text_deltas_then_the_completion_with_its_usage(self) -> None:
        lines = _sse(
            (
                "message_start",
                {
                    "type": "message_start",
                    "message": {"model": "claude-opus-5", "usage": {"input_tokens": 25, "output_tokens": 1}},
                },
            ),
            ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hel"}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "lo"}}),
            ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 7}}),
            ("message_stop", {"type": "message_stop"}),
        )
        _, patched = _stub(_StubResponse(lines))
        with patched:
            events = list(llm.get_llm().stream(system="s", prompt="p", max_tokens=10))
        self.assertEqual(events[:2], ["Hel", "lo"])
        self.assertEqual(
            events[2],
            llm.Completion(
                text="Hello",
                model="claude-opus-5",
                model_version=llm.ANTHROPIC_API_VERSION,
                input_tokens=25,
                output_tokens=7,
                stop_reason="end_turn",
            ),
        )

    def test_complete_returns_the_final_completion_of_the_same_stream(self) -> None:
        _, patched = _stub(_StubResponse(_hello_stream(text="Hello there", output_tokens=9)))
        with patched:
            completion = llm.get_llm().complete(system="s", prompt="p", max_tokens=10)
        self.assertEqual(completion.text, "Hello there")
        self.assertEqual(completion.output_tokens, 9)
        self.assertEqual(completion.input_tokens, 25)

    def test_ping_thinking_and_unknown_events_never_reach_the_caller(self) -> None:
        lines = _sse(
            ("message_start", {"type": "message_start", "message": {"model": "m", "usage": {"input_tokens": 1}}}),
            ("ping", {"type": "ping"}),
            (
                "content_block_delta",
                {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "reasoning"}},
            ),
            (
                "content_block_delta",
                {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "sig"}},
            ),
            ("a_future_event", {"type": "a_future_event", "whatever": 1}),
            ("content_block_delta", {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "answer"}}),
            ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 3}}),
            ("message_stop", {"type": "message_stop"}),
        )
        _, patched = _stub(_StubResponse(lines))
        with patched:
            events = list(llm.get_llm().stream(system="s", prompt="p", max_tokens=10))
        self.assertEqual(events[:-1], ["answer"])
        self.assertEqual(
            events[-1],
            llm.Completion(
                text="answer",
                model="m",
                model_version=llm.ANTHROPIC_API_VERSION,
                input_tokens=1,
                output_tokens=3,
                stop_reason="end_turn",
            ),
        )

    def test_a_mid_stream_error_event_fails_loudly_without_quoting_the_message(self) -> None:
        lines = _sse(
            ("message_start", {"type": "message_start", "message": {"model": "m", "usage": {"input_tokens": 1}}}),
            ("error", {"type": "error", "error": {"type": "overloaded_error", "message": "a message that may quote the prompt"}}),
        )
        _, patched = _stub(_StubResponse(lines))
        with patched, self.assertRaises(llm.LlmError) as raised:
            list(llm.get_llm().stream(system="s", prompt="p", max_tokens=10))
        self.assertIn("overloaded_error", str(raised.exception))
        self.assertNotIn("quote the prompt", str(raised.exception))

    def test_a_stream_that_stops_before_the_completion_is_an_error(self) -> None:
        lines = _sse(("message_start", {"type": "message_start", "message": {"model": "m", "usage": {"input_tokens": 1}}}))
        _, patched = _stub(_StubResponse(lines))
        with patched, self.assertRaises(llm.LlmError):
            llm.get_llm().complete(system="s", prompt="p", max_tokens=10)

    def test_a_stream_cut_before_message_stop_raises_rather_than_going_quiet(self) -> None:
        # The connection ends after the text: without this a streaming caller saw the
        # deltas end with neither a Completion nor an error, and could take them as whole.
        _, patched = _stub(_StubResponse(_hello_stream()[:-3]))
        received: list[str | llm.Completion] = []
        with patched, self.assertRaises(llm.LlmError):
            for event in llm.get_llm().stream(system="s", prompt="p", max_tokens=10):
                received.append(event)
        self.assertEqual(received, ["Hello"])

    def test_a_refusal_after_partial_output_is_an_error_never_an_answer(self) -> None:
        # The refusals page: a refusal can arrive mid-stream after partial output, and that
        # output is incomplete and discarded. The deltas already yielded are followed by an
        # LlmError, never by a Completion.
        _, patched = _stub(_StubResponse(_hello_stream(text="Firms must warn consumers about", stop_reason="refusal")))
        received: list[str | llm.Completion] = []
        with patched, self.assertRaises(llm.LlmError) as raised:
            for event in llm.get_llm().stream(system="s", prompt="p", max_tokens=10):
                received.append(event)
        self.assertEqual(received, ["Firms must warn consumers about"])
        self.assertIn("refusal", str(raised.exception))
        self.assertNotIn("warn consumers", str(raised.exception))

    def test_complete_never_returns_a_refused_answer(self) -> None:
        _, patched = _stub(_StubResponse(_hello_stream(text="Firms must warn", stop_reason="refusal")))
        with patched, self.assertRaises(llm.LlmError):
            llm.get_llm().complete(system="s", prompt="p", max_tokens=10)

    def test_an_answer_cut_off_at_max_tokens_says_so_on_its_completion(self) -> None:
        _, patched = _stub(_StubResponse(_hello_stream(text="Firms must warn [1", stop_reason="max_tokens")))
        with patched:
            completion = llm.get_llm().complete(system="s", prompt="p", max_tokens=10)
        self.assertEqual(completion.text, "Firms must warn [1")
        self.assertEqual(completion.stop_reason, "max_tokens")

    def test_a_stream_that_never_gives_a_stop_reason_is_an_error(self) -> None:
        lines = _sse(
            ("message_start", {"type": "message_start", "message": {"model": "m", "usage": {"input_tokens": 1}}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "a"}}),
            ("message_delta", {"type": "message_delta", "delta": {}, "usage": {"output_tokens": 1}}),
            ("message_stop", {"type": "message_stop"}),
        )
        _, patched = _stub(_StubResponse(lines))
        with patched, self.assertRaises(llm.LlmError):
            llm.get_llm().complete(system="s", prompt="p", max_tokens=10)

    def test_lines_split_across_reads_are_joined_before_they_are_parsed(self) -> None:
        # Seven bytes a read splits events, lines and the two-byte UTF-8 letters alike.
        body = b"".join(_hello_stream(text="Förbudet gäller"))
        _, patched = _stub(_StubResponse(body[start : start + 7] for start in range(0, len(body), 7)))
        with patched:
            completion = llm.get_llm().complete(system="s", prompt="p", max_tokens=10)
        self.assertEqual(completion.text, "Förbudet gäller")

    def test_a_failure_after_the_answer_starts_is_an_llm_error_and_never_retried(self) -> None:
        for failure in (
            ConnectionResetError(104, "Connection reset by peer"),
            TimeoutError("timed out"),
            http.client.IncompleteRead(b""),
        ):
            with self.subTest(type(failure).__name__):
                transport, patched = _stub(_StubResponse([*_hello_stream()[:12], failure]), _StubResponse(_hello_stream()))
                with patched, self.assertRaises(llm.LlmError):
                    list(llm.get_llm().stream(system="s", prompt="p", max_tokens=10))
                self.assertEqual(len(transport.requests), 1)

    def test_a_malformed_event_is_an_llm_error_whatever_its_shape(self) -> None:
        start = b'data: {"type": "message_start", "message": {"model": "m", "usage": {"input_tokens": 1}}}\n'
        end = [
            b'data: {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 1}}\n',
            b'data: {"type": "message_stop"}\n',
        ]
        malformed = {
            "not an object": b"data: [1]\n",
            "a null message": b'data: {"type": "message_start", "message": null}\n',
            "an error that is a string": b'data: {"type": "error", "error": "x"}\n',
            "bytes that are not UTF-8": b"data: \xff\xfe\n",
            "a text that is not a string": (
                b'data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": 7}}\n'
            ),
            "a model that is not a string": b'data: {"type": "message_start", "message": {"model": ["m"]}}\n',
            "a token count that is not a number": (
                b'data: {"type": "message_delta", "delta": {}, "usage": {"output_tokens": "many"}}\n'
            ),
        }
        for case, line in malformed.items():
            with self.subTest(case):
                _, patched = _stub(_StubResponse([start, line, *end]))
                with patched, self.assertRaises(llm.LlmError):
                    list(llm.get_llm().stream(system="s", prompt="p", max_tokens=10))

    @override_settings(LLM_MAX_RETRIES=0)
    def test_a_provider_kind_that_is_not_a_plain_word_is_reported_as_unknown(self) -> None:
        # The error type is copied into the LlmError, so nothing else off the network rides
        # along with it.
        odd = {"type": "error", "error": {"type": "the tenant question, quoted", "message": "m"}}
        mid_stream = _StubResponse(_sse(("error", odd)))
        failing = urllib.error.HTTPError(
            url=llm.ANTHROPIC_MESSAGES_URL,
            code=400,
            msg="error",
            hdrs=email.message.Message(),
            fp=io.BytesIO(json.dumps(odd).encode("utf-8")),
        )
        for outcome in (mid_stream, failing):
            with self.subTest(type(outcome).__name__):
                _, patched = _stub(outcome)
                with patched, self.assertRaises(llm.LlmError) as raised:
                    llm.get_llm().complete(system="s", prompt="p", max_tokens=10)
                self.assertIn("unknown", str(raised.exception))
                self.assertNotIn("tenant question", str(raised.exception))

    @override_settings(LLM_MAX_RESPONSE_BYTES=500)
    def test_a_stream_larger_than_the_response_limit_is_refused(self) -> None:
        cases: dict[str, list[bytes | BaseException]] = {
            "many small events": [*[b'event: ping\ndata: {"type": "ping"}\n\n'] * 100, *_hello_stream()],
            "one line that never ends": [b"data: " + b"x" * 400, b"x" * 400],
        }
        for case, reads in cases.items():
            with self.subTest(case):
                _, patched = _stub(_StubResponse(reads))
                with patched, self.assertRaises(llm.LlmError) as raised:
                    list(llm.get_llm().stream(system="s", prompt="p", max_tokens=10))
                self.assertIn("limit", str(raised.exception))

    @override_settings(LLM_DEADLINE_S=100.0)
    def test_a_stream_that_keeps_pinging_is_cut_off_at_the_deadline(self) -> None:
        def a_ping_every_thirty_seconds() -> Iterator[bytes]:
            for _ in range(1000):
                self.clock.now += 30.0
                yield b'event: ping\ndata: {"type": "ping"}\n\n'

        _, patched = _stub(_StubResponse(a_ping_every_thirty_seconds()))
        with patched, self.assertRaises(llm.LlmError) as raised:
            list(llm.get_llm().stream(system="s", prompt="p", max_tokens=10))
        self.assertIn("deadline", str(raised.exception))
        self.assertLessEqual(self.clock.now, 100.0 + 30.0)

    @override_settings(LLM_MAX_RETRIES=5, LLM_DEADLINE_S=5.0)
    def test_no_retry_is_made_whose_wait_would_end_after_the_deadline(self) -> None:
        transport, patched = _stub(*[_http_error(529, "overloaded_error", retry_after="3") for _ in range(6)])
        with patched, self.assertRaises(llm.LlmError) as raised:
            llm.get_llm().complete(system="s", prompt="p", max_tokens=10)
        self.assertEqual(len(transport.requests), 2)
        self.assertEqual(self.clock.slept, [3.0])
        self.assertIn("529", str(raised.exception))

    @override_settings(LLM_MAX_RETRIES=2)
    def test_a_rate_limit_is_retried_and_the_retry_after_header_is_honoured(self) -> None:
        transport, patched = _stub(
            _http_error(429, "rate_limit_error", retry_after="3"),
            _StubResponse(_hello_stream()),
        )
        with patched:
            completion = llm.get_llm().complete(system="s", prompt="p", max_tokens=10)
        self.assertEqual(completion.text, "Hello")
        self.assertEqual(len(transport.requests), 2)
        self.assertEqual(self.clock.slept, [3.0])

    @override_settings(LLM_MAX_RETRIES=1, LLM_RETRY_BACKOFF_S=0.5)
    def test_a_retry_after_that_is_not_plain_seconds_falls_back_to_the_backoff(self) -> None:
        # "²" passes str.isdigit() and then fails float(); an HTTP-date is valid HTTP but
        # not worth a parser here.
        for value in ("²", "1.5", "Wed, 21 Oct 2026 07:28:00 GMT"):
            with self.subTest(value):
                self.clock.slept.clear()
                _, patched = _stub(_http_error(429, "rate_limit_error", retry_after=value), _StubResponse(_hello_stream()))
                with patched:
                    llm.get_llm().complete(system="s", prompt="p", max_tokens=10)
                self.assertEqual(self.clock.slept, [0.5])

    @override_settings(LLM_MAX_RETRIES=2, LLM_TIMEOUT_S=5.0)
    def test_a_retry_after_header_never_makes_us_wait_longer_than_one_call(self) -> None:
        _, patched = _stub(_http_error(529, "overloaded_error", retry_after="86400"), _StubResponse(_hello_stream()))
        with patched:
            llm.get_llm().complete(system="s", prompt="p", max_tokens=10)
        self.assertEqual(self.clock.slept, [5.0])

    @override_settings(LLM_MAX_RETRIES=3, LLM_RETRY_BACKOFF_S=0.5)
    def test_a_server_error_backs_off_exponentially_until_the_retries_run_out(self) -> None:
        transport, patched = _stub(*[_http_error(500, "api_error") for _ in range(4)])
        with patched:
            with self.assertRaises(llm.LlmError) as raised:
                llm.get_llm().complete(system="s", prompt="p", max_tokens=10)
        self.assertEqual(len(transport.requests), 4)
        self.assertEqual(self.clock.slept, [0.5, 1.0, 2.0])
        self.assertIn("api_error", str(raised.exception))

    def test_a_bad_request_is_never_retried(self) -> None:
        transport, patched = _stub(_http_error(400, "invalid_request_error"))
        with patched:
            with self.assertRaises(llm.LlmError) as raised:
                llm.get_llm().complete(system="s", prompt="p", max_tokens=10)
        self.assertEqual(len(transport.requests), 1)
        self.assertIn("400", str(raised.exception))

    @override_settings(LLM_MAX_RETRIES=1)
    def test_a_connection_failure_is_retried_and_then_reported(self) -> None:
        transport, patched = _stub(TimeoutError("timed out"), TimeoutError("timed out"))
        with patched, self.assertRaises(llm.LlmError) as raised:
            llm.get_llm().complete(system="s", prompt="p", max_tokens=10)
        self.assertEqual(len(transport.requests), 2)
        self.assertIn("could not be reached", str(raised.exception))

    @override_settings(LLM_MAX_RETRIES=1)
    def test_a_connection_dropped_before_the_answer_starts_is_retried(self) -> None:
        for failure in (
            http.client.RemoteDisconnected("Remote end closed connection without response"),
            http.client.BadStatusLine("garbage"),
            ConnectionResetError(104, "Connection reset by peer"),
        ):
            with self.subTest(type(failure).__name__):
                transport, patched = _stub(failure, _StubResponse(_hello_stream()))
                with patched:
                    completion = llm.get_llm().complete(system="s", prompt="p", max_tokens=10)
                self.assertEqual(completion.text, "Hello")
                self.assertEqual(len(transport.requests), 2)

    def test_no_failure_ever_carries_the_api_key_the_prompt_or_the_answer(self) -> None:
        _, patched = _stub(_http_error(403, "permission_error"))
        with patched:
            with self.assertRaises(llm.LlmError) as raised:
                llm.get_llm().complete(system="the system prompt", prompt="the tenant question", max_tokens=10)
        message = str(raised.exception)
        self.assertNotIn(API_KEY, message)
        self.assertNotIn("tenant question", message)
        self.assertNotIn("system prompt", message)

    @override_settings(LLM_MAX_RETRIES=0)
    def test_a_failure_whose_body_is_not_the_documented_shape_is_still_reported(self) -> None:
        # A gateway in front of the API answers with HTML, not the documented error object.
        broken = urllib.error.HTTPError(
            url=llm.ANTHROPIC_MESSAGES_URL,
            code=502,
            msg="error",
            hdrs=email.message.Message(),
            fp=io.BytesIO(b"<html>a gateway said no</html>"),
        )
        _, patched = _stub(broken)
        with patched, self.assertRaises(llm.LlmError) as raised:
            llm.get_llm().complete(system="s", prompt="p", max_tokens=10)
        self.assertIn("502", str(raised.exception))
        self.assertIn("unreadable", str(raised.exception))
        self.assertNotIn("gateway said no", str(raised.exception))

    @override_settings(LLM_MAX_RETRIES=0, LLM_MAX_ERROR_BODY_BYTES=1024)
    def test_an_error_body_is_read_no_further_than_its_limit(self) -> None:
        body = io.BytesIO(b"<html>" + b"x" * 100_000 + b"</html>")
        broken = urllib.error.HTTPError(
            url=llm.ANTHROPIC_MESSAGES_URL, code=502, msg="error", hdrs=email.message.Message(), fp=body
        )
        _, patched = _stub(broken)
        with patched, self.assertRaises(llm.LlmError):
            llm.get_llm().complete(system="s", prompt="p", max_tokens=10)
        self.assertEqual(body.tell(), 1024)

    def test_an_event_that_is_not_json_fails_loudly(self) -> None:
        _, patched = _stub(_StubResponse([b"event: message_start\n", b"data: {not json\n", b"\n"]))
        with patched, self.assertRaises(llm.LlmError) as raised:
            llm.get_llm().complete(system="s", prompt="p", max_tokens=10)
        self.assertIn("JSONDecodeError", str(raised.exception))

    @override_settings(ANTHROPIC_API_KEY="")
    def test_the_provider_refuses_to_run_without_a_key_from_the_environment(self) -> None:
        with self.assertRaises(ImproperlyConfigured):
            llm.get_llm()


class GroundedMock(SimpleTestCase):
    """The mock answers from the prompt's numbered chunks and nothing else, so Ask's
    scenarios can assert on an answer without a model call."""

    def _prompt(self, *chunks: str) -> str:
        return f"Answer from the context only.\n\n{llm.format_context(list(chunks))}\n\nQuestion: does it?"

    def test_context_chunks_are_numbered_from_one_on_their_own_line(self) -> None:
        self.assertEqual(
            llm.format_context(["Firms must warn consumers.", "FFFS 2017:2\napplies."]),
            "[1] Firms must warn consumers.\n[2] FFFS 2017:2 applies.",
        )

    def test_every_statement_cites_the_chunk_it_came_from(self) -> None:
        completion = llm.MockLlm().complete(
            system="s",
            prompt=self._prompt("Firms must warn consumers. The warning is prominent.", "FFFS 2017:2 applies from 1 January."),
            max_tokens=100,
        )
        self.assertEqual(
            completion.text,
            "Firms must warn consumers. [1] FFFS 2017:2 applies from 1 January. [2]",
        )
        self.assertEqual(completion.model, "mock")
        self.assertEqual(completion.stop_reason, "end_turn")

    def test_nothing_is_answered_when_the_prompt_carries_no_chunks(self) -> None:
        completion = llm.MockLlm().complete(system="s", prompt="Question: what does the inventory say?", max_tokens=100)
        self.assertEqual(completion.text, "")
        self.assertEqual(completion.output_tokens, 0)

    def test_the_answer_never_borrows_a_word_that_is_not_in_a_chunk(self) -> None:
        completion = llm.MockLlm().complete(system="a system prompt", prompt=self._prompt("Only this sentence."), max_tokens=100)
        self.assertEqual(completion.text, "Only this sentence. [1]")

    def test_the_same_prompt_always_gives_the_same_answer(self) -> None:
        prompt = self._prompt("A chunk.", "Another chunk.")
        first = llm.MockLlm().complete(system="s", prompt=prompt, max_tokens=10)
        second = llm.MockLlm().complete(system="s", prompt=prompt, max_tokens=10)
        self.assertEqual(first, second)

    def test_streaming_yields_one_delta_per_citation_then_the_completion(self) -> None:
        events = list(llm.MockLlm().stream(system="s", prompt=self._prompt("A chunk.", "Another chunk."), max_tokens=10))
        self.assertEqual(events[:-1], ["A chunk. [1] ", "Another chunk. [2]"])
        self.assertEqual(
            events[-1],
            llm.Completion(
                text="A chunk. [1] Another chunk. [2]",
                model="mock",
                model_version="0",
                input_tokens=14,
                output_tokens=6,
                stop_reason="end_turn",
            ),
        )
