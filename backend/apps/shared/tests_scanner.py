"""The malware scanner seam (CAS-05, playbook 16). The mock is deterministic and offline;
clamd is spoken to over INSTREAM against a stub server on a loopback socket, and every
answer that is not a well-formed OK or FOUND is `error`, never `clean`. The factory
refuses an unknown provider and the mock on a deployed environment, and nothing a scan
logs carries a filename or a byte of the file."""

from __future__ import annotations

import logging
import socket
import struct
import threading
from collections.abc import Callable
from datetime import UTC, datetime

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from apps.shared.adapters import scanner
from apps.shared.adapters.scanner import ScanState

# The EICAR anti-malware test file (eicar.org): harmless by design, flagged by every engine.
EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
SECRET_NAME = "board-minutes-q3-confidential.pdf"
SECRET_BYTES = b"the bank's unique board minutes 7f3a91"


def read_instream(conn: socket.socket) -> tuple[bytes, bytes]:
    """Read one INSTREAM request as clamd does: the command up to its NUL, then
    length-prefixed chunks until a zero-length one."""
    buffer = b""

    def take(size: int) -> bytes:
        nonlocal buffer
        while len(buffer) < size:
            part = conn.recv(65536)
            if not part:
                raise ConnectionError("client closed early")
            buffer += part
        head, buffer = buffer[:size], buffer[size:]
        return head

    command = b""
    while not command.endswith(b"\0"):
        command += take(1)
    content = b""
    while True:
        (length,) = struct.unpack("!I", take(4))
        if length == 0:
            return command, content
        content += take(length)


def answer(reply: bytes | None) -> Callable[[bytes], bytes | None]:
    return lambda _: reply


class StubClamd:
    """A one-connection clamd on a loopback port. `reply` receives what was streamed and
    returns the bytes to answer, or None to answer nothing and hold the socket open."""

    def __init__(self, reply: Callable[[bytes], bytes | None]) -> None:
        self.reply = reply
        self.received: tuple[bytes, bytes] | None = None
        self.release = threading.Event()
        self.server = socket.create_server(("127.0.0.1", 0))
        self.port = self.server.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        conn, _ = self.server.accept()
        with conn:
            self.received = read_instream(conn)
            answer = self.reply(self.received[1])
            if answer is None:
                self.release.wait(5)
            else:
                conn.sendall(answer)

    def close(self) -> None:
        self.release.set()
        self.thread.join(5)
        self.server.close()


class ScanWithStub(SimpleTestCase):
    def scan_against(self, reply: Callable[[bytes], bytes | None], content: bytes = b"hello") -> scanner.ScanResult:
        stub = StubClamd(reply)
        self.addCleanup(stub.close)
        with override_settings(SCANNER_HOST="127.0.0.1", SCANNER_PORT=stub.port, SCANNER_TIMEOUT_SECONDS=0.5):
            result = scanner.ClamdScanner().scan(content, filename="report.pdf")
        self.last_stub = stub
        return result


class MockScannerOutcomes(SimpleTestCase):
    def test_clean_bytes_are_clean(self) -> None:
        result = scanner.MockScanner().scan(b"%PDF-1.7 an ordinary report", filename="report.pdf")
        self.assertEqual(result.state, ScanState.CLEAN)
        self.assertIsNone(result.signature)

    def test_eicar_is_infected_wherever_it_sits_in_the_file(self) -> None:
        for content in (EICAR, b"header " + EICAR + b" trailer"):
            result = scanner.MockScanner().scan(content, filename="report.pdf")
            self.assertEqual(result.state, ScanState.INFECTED)
            self.assertEqual(result.signature, scanner.MockScanner.EICAR_SIGNATURE)

    def test_the_infected_marker_name_is_infected(self) -> None:
        name = f"quarterly-{scanner.MOCK_INFECTED_MARKER}.pdf"
        result = scanner.MockScanner().scan(b"plain bytes", filename=name)
        self.assertEqual(result.state, ScanState.INFECTED)
        self.assertEqual(result.signature, scanner.MockScanner.MARKER_SIGNATURE)

    def test_the_error_marker_name_is_an_error(self) -> None:
        name = f"quarterly-{scanner.MOCK_ERROR_MARKER}.pdf"
        result = scanner.MockScanner().scan(b"plain bytes", filename=name)
        self.assertEqual(result.state, ScanState.ERROR)
        self.assertIsNone(result.signature)

    def test_the_answer_is_deterministic_and_stamped_in_utc(self) -> None:
        before = datetime.now(UTC)
        a = scanner.MockScanner().scan(EICAR, filename="a.txt")
        b = scanner.MockScanner().scan(EICAR, filename="a.txt")
        self.assertEqual((a.state, a.signature), (b.state, b.signature))
        self.assertEqual(a.scanned_at.tzinfo, UTC)
        self.assertGreaterEqual(a.scanned_at, before)

    def test_the_mock_never_answers_pending(self) -> None:
        names = ["a.pdf", scanner.MOCK_INFECTED_MARKER, scanner.MOCK_ERROR_MARKER]
        states = {scanner.MockScanner().scan(b"x", filename=name).state for name in names}
        self.assertNotIn(ScanState.PENDING, states)


class ClamdVerdicts(ScanWithStub):
    def test_bytes_are_streamed_as_length_prefixed_chunks_after_zinstream(self) -> None:
        content = bytes(range(256)) * 1000  # larger than one chunk
        result = self.scan_against(lambda _: b"stream: OK\0", content=content)
        self.assertEqual(result.state, ScanState.CLEAN)
        self.assertEqual(self.last_stub.received, (b"zINSTREAM\0", content))

    def test_empty_content_is_streamed_as_the_terminating_chunk_alone(self) -> None:
        result = self.scan_against(lambda _: b"stream: OK\0", content=b"")
        self.assertEqual(result.state, ScanState.CLEAN)
        self.assertEqual(self.last_stub.received, (b"zINSTREAM\0", b""))

    def test_found_is_infected_with_the_signature(self) -> None:
        result = self.scan_against(lambda _: b"stream: Eicar-Test-Signature FOUND\0")
        self.assertEqual(result.state, ScanState.INFECTED)
        self.assertEqual(result.signature, "Eicar-Test-Signature")

    def test_found_with_the_hash_suffix_keeps_the_signature_name(self) -> None:
        reply = b"stream: Win.Test.EICAR_HDB-1(44d88612fea8a8f36de82e1278abb02f:68) FOUND\0"
        result = self.scan_against(lambda _: reply)
        self.assertEqual(result.state, ScanState.INFECTED)
        self.assertEqual(result.signature, "Win.Test.EICAR_HDB-1")

    def test_a_reply_without_the_nul_but_closed_is_still_read(self) -> None:
        result = self.scan_against(lambda _: b"stream: OK")
        self.assertEqual(result.state, ScanState.CLEAN)


class ClamdNeverSaysCleanOnDoubt(ScanWithStub):
    def assert_error(self, result: scanner.ScanResult) -> None:
        self.assertEqual(result.state, ScanState.ERROR)
        self.assertIsNone(result.signature)

    def test_a_timeout_is_an_error(self) -> None:
        self.assert_error(self.scan_against(lambda _: None))

    def test_a_refused_connection_is_an_error(self) -> None:
        with socket.create_server(("127.0.0.1", 0)) as probe:
            port = probe.getsockname()[1]
        with override_settings(SCANNER_HOST="127.0.0.1", SCANNER_PORT=port, SCANNER_TIMEOUT_SECONDS=0.5):
            self.assert_error(scanner.ClamdScanner().scan(b"x", filename="a.pdf"))

    def test_a_truncated_reply_is_an_error(self) -> None:
        self.assert_error(self.scan_against(lambda _: b"stream: O"))

    def test_an_empty_reply_is_an_error(self) -> None:
        self.assert_error(self.scan_against(lambda _: b""))

    def test_clamd_reporting_an_error_is_an_error(self) -> None:
        self.assert_error(self.scan_against(lambda _: b"INSTREAM size limit exceeded. ERROR\0"))
        self.assert_error(self.scan_against(lambda _: b"stream: Can't allocate memory ERROR\0"))

    def test_unparsable_replies_are_errors(self) -> None:
        for reply in (
            b"stream: FOUND\0",
            b"stream: OK OK\0",
            b"OK\0",
            b"stream: OK\nstream: Eicar FOUND\0",
            b"stream: Eicar\x00FOUND\0",
            b"stream: \xff\xfe FOUND\0",
            b"stream: " + b"A" * 300 + b" FOUND\0",
        ):
            with self.subTest(reply=reply[:40]):
                self.assert_error(self.scan_against(answer(reply)))

    def test_a_reply_longer_than_the_cap_is_an_error(self) -> None:
        self.assert_error(self.scan_against(lambda _: b"stream: OK" + b" " * scanner.MAX_REPLY_BYTES))


class ScannerFactory(SimpleTestCase):
    @override_settings(SCANNER_PROVIDER="mock", IS_DEPLOYED_ENVIRONMENT=False)
    def test_mock_is_chosen_off_a_deployed_environment(self) -> None:
        self.assertIsInstance(scanner.get_scanner(), scanner.MockScanner)

    @override_settings(SCANNER_PROVIDER="clamd", IS_DEPLOYED_ENVIRONMENT=True)
    def test_clamd_is_chosen_anywhere(self) -> None:
        self.assertIsInstance(scanner.get_scanner(), scanner.ClamdScanner)

    @override_settings(SCANNER_PROVIDER="virustotal")
    def test_unknown_provider_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            scanner.get_scanner()

    def test_mock_on_any_deployed_environment_is_refused(self) -> None:
        # `test` may run the other mocks (production-safety rule 5), but a mock scanner
        # would pass real files there too, so it is refused on every deployed name.
        for environment in ("prod", "demo", "test"):
            with (
                self.subTest(environment=environment),
                override_settings(SCANNER_PROVIDER="mock", IS_DEPLOYED_ENVIRONMENT=True, ENVIRONMENT=environment),
                self.assertRaises(ImproperlyConfigured),
            ):
                scanner.get_scanner()


class NothingOfTheFileIsLogged(ScanWithStub):
    def captured(self, scan: Callable[[], scanner.ScanResult]) -> list[logging.LogRecord]:
        with self.assertLogs("apps", level=logging.DEBUG) as logs:
            scan()
        return logs.records

    def assert_nothing_of_the_file(self, records: list[logging.LogRecord]) -> None:
        self.assertTrue(records, "a scan logs its provider, state and elapsed time")
        for record in records:
            text = record.getMessage() + " " + " ".join(repr(value) for value in vars(record).values())
            self.assertNotIn(SECRET_NAME, text)
            self.assertNotIn("board-minutes", text)
            self.assertNotIn(SECRET_BYTES.decode(), text)
            self.assertNotIn(repr(SECRET_BYTES), text)

    def test_the_mock_logs_provider_state_and_time_only(self) -> None:
        records = self.captured(lambda: scanner.MockScanner().scan(SECRET_BYTES, filename=SECRET_NAME))
        self.assert_nothing_of_the_file(records)
        record = records[-1]
        self.assertEqual((record.provider, record.state), ("mock", "clean"))  # type: ignore[attr-defined]
        self.assertIsInstance(record.elapsed_ms, int)  # type: ignore[attr-defined]

    def test_clamd_logs_nothing_of_the_file_on_success_or_failure(self) -> None:
        for reply in (b"stream: OK\0", b"stream: Eicar FOUND\0", b"garbage", None):
            stub = StubClamd(answer(reply))
            self.addCleanup(stub.close)
            with (
                self.subTest(reply=reply),
                override_settings(SCANNER_HOST="127.0.0.1", SCANNER_PORT=stub.port, SCANNER_TIMEOUT_SECONDS=0.3),
            ):
                records = self.captured(lambda: scanner.ClamdScanner().scan(SECRET_BYTES, filename=SECRET_NAME))
                self.assert_nothing_of_the_file(records)
                self.assertEqual(records[-1].provider, "clamd")  # type: ignore[attr-defined]
