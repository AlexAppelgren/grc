"""The public registers adapter (TEN-07, TEN-08; PUBLIC_REGISTERS.md 5.3).

The live provider is driven through its one network function, `_open`, replaced by a table
of synthetic answers in GLEIF's and Finansinspektionen's published shapes (made-up companies,
never a real bank's data), so no test touches the network. `_open` itself is proven against a
stubbed opener: only the two configured hosts over https, no redirect, a byte cap, and every
failure a `RegisterUnavailable`."""

from __future__ import annotations

import http.client
import io
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from typing import Any
from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.shared.adapters import registers
from apps.shared.adapters.registers import (
    LiveRegisters,
    MockRegisters,
    RegisterBranch,
    RegisterLicence,
    RegisterNotFound,
    RegisterUnavailable,
)

GLEIF = "https://api.gleif.org/api/v1"
FI = "https://www.fi.se/sv/vara-register/foretagsregistret"
BANK_LEI = "549300EXAMPLEBANK001"
HEADER = "Namn;Org.nummer;LEI kod;Huvudverksamhet;Övriga verksamheter;Tillstånd 1;Tillstånd 2;Tillstånd 3;et.c."


def record(lei: str, name: str, number: str, *, jurisdiction: str = "SE", category: str = "GENERAL", status: str = "ISSUED") -> dict[str, Any]:
    return {
        "type": "lei-records",
        "id": lei,
        "attributes": {
            "lei": lei,
            "entity": {
                "legalName": {"name": name, "language": "sv"},
                "jurisdiction": jurisdiction,
                "registeredAs": number,
                "category": category,
            },
            "registration": {"status": status},
        },
    }


def page(records: list[dict[str, Any]], *, last: int = 1) -> bytes:
    return json.dumps({"meta": {"pagination": {"currentPage": 1, "lastPage": last}}, "data": records}).encode()


def fi_csv(*rows: str, header: str = HEADER) -> bytes:
    return ("﻿" + "\r\n".join([header, *rows]) + "\r\n").encode("utf-8")


def details(*, name: str, number: str, address: tuple[str, ...] = ("Box 1", "106 40 Stockholm", "Sverige"), extra: str = "") -> bytes:
    lines = "".join(f"<dd>{line}</dd>" for line in address)
    return f"""<html><head><title>Företagsregistret | Finansinspektionen</title>
<script>var x = "<h2>Filialer</h2>";</script><style>h1 {{ color: red }}</style></head><body>
<nav><a href="/sv/vara-register/foretagsregistret/">Företagsregistret</a></nav>
<h1>Företagsregistret</h1><h2>{name}</h2>
<dl><dt>Adress</dt>{lines}<dt>Telefon</dt><dd>08-000 00 00</dd>
<dt>Kategori</dt><dd>Bankaktiebolag</dd><dt>Organisationsnummer</dt><dd>{number}</dd></dl>
{extra}</body></html>""".encode()


BANK_ROW = (
    "Example Bank AB;556000-0001;549300EXAMPLEBANK001;Bankaktiebolag;Värdepappersbolag, Riksbolag, livförsäkringar;"
    "1995-03-01 - Tillstånd att driva bankrörelse, enligt lag (2004:297) om bank- och finansieringsrörelse;"
    "2016-06-26 - IM_MR_SA;Ett tillstånd utan datum;;"
)
OTHER_ROW = "Example Bank AB Fonder;556000-0011;549300EXAMPLEOTHR009;Fondbolag;;2001-05-01 - Tillstånd att driva fondverksamhet"
BANK_PAGE = details(
    name="Example Bank AB",
    number="556000-0001",
    extra="""<h3>Tillstånd</h3><p>1995-03-01</p>
<h3>Filialer</h3><ul><li><a href="details?id=21">Example Bank AB, filial i Danmark</a></li>
<li><a href="details?id=22">Example Bank AB, filial i Norge</a></li><li><a href="details?id=21">again</a></li></ul>
<h3>Förvarade fonder</h3><ul><li><a href="details?id=31">Example Fond</a></li></ul><h2>Övrigt</h2>""",
)


def answers() -> dict[str, bytes]:
    """The registers as the live provider reads them, by address."""
    search = urllib.parse.urlencode({"filter[entity.registeredAs]": "556000-0001", "page[size]": 10})
    children = f"{GLEIF}/lei-records/{BANK_LEI}/direct-children"
    return {
        f"{GLEIF}/lei-records?{search}": page([record(BANK_LEI, "Example Bank AB", "556000-0001")]),
        f"{GLEIF}/lei-records/{BANK_LEI}": json.dumps({"data": record(BANK_LEI, "Example Bank AB", "556000-0001")}).encode(),
        f"{children}?page%5Bsize%5D=100&page%5Bnumber%5D=1": page(
            [
                record("549300EXAMPLEFOND002", "Example Fonder AB", "556000-0003"),
                record("549300EXAMPLEFUND099", "Example Fund One", "", category="FUND"),
            ],
            last=2,
        ),
        f"{children}?page%5Bsize%5D=100&page%5Bnumber%5D=2": page(
            [record("549300EXAMPLESECS008", "Example Securities Inc.", "2179242", jurisdiction="US-DE", status="LAPSED")], last=2
        ),
        f"{FI}/index?query=556000-0001&format=csv": fi_csv(OTHER_ROW, BANK_ROW),
        f"{FI}/index?query=556000-0001": b'<html><body><a href="details?id=11">Example Bank AB Fonder</a> <a href="/sv/vara-register/foretagsregistret/details?id=12">Example Bank AB</a></body></html>',
        f"{FI}/details?id=11": details(name="Example Bank AB Fonder", number="556000-0011"),
        f"{FI}/details?id=12": BANK_PAGE,
        f"{FI}/details?id=21": details(
            name="Example Bank AB, filial i Danmark", number="", address=("Bernstorffsgade 50", "1577 Copenhagen V", "Danmark")
        ),
        f"{FI}/details?id=22": details(name="Example Bank AB, filial i Norge", number="", address=("Postboks 1", "0123 Oslo", "Norge")),
    }


class Opened:
    """`_open` replaced by a table: an address it does not hold is a test failure, never a read."""

    def __init__(self, table: dict[str, bytes]) -> None:
        self.table = table
        self.urls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        if url not in self.table:
            raise AssertionError(f"the adapter read an address the test did not expect: {url}")
        return self.table[url]


class LiveGleif(SimpleTestCase):
    def setUp(self) -> None:
        self.opened = Opened(answers())
        patcher = mock.patch.object(registers, "_open", self.opened)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_number_is_searched_as_typed_and_answers_every_company_carrying_it(self) -> None:
        [bank] = LiveRegisters().find(" 556000-0001 ")
        self.assertEqual(bank, registers.LeiCompany(BANK_LEI, "Example Bank AB", "556000-0001", "SE", None, "ISSUED"))
        self.assertIn("filter%5Bentity.registeredAs%5D=556000-0001", self.opened.urls[0])

    def test_an_lei_looks_up_that_record_and_a_missing_one_is_empty(self) -> None:
        self.assertEqual([company.name for company in LiveRegisters().find(BANK_LEI.lower())], ["Example Bank AB"])
        with mock.patch.object(registers, "_open", side_effect=RegisterNotFound("gone")):
            self.assertEqual(LiveRegisters().find("549300EXAMPLEGONE010"), [])

    def test_children_read_every_page_keep_companies_only_and_name_their_parent(self) -> None:
        children = LiveRegisters().children(BANK_LEI)
        self.assertEqual([child.lei for child in children], ["549300EXAMPLEFOND002", "549300EXAMPLESECS008"])
        self.assertEqual({child.parent_lei for child in children}, {BANK_LEI})
        # A subdivision is read as its country.
        self.assertEqual((children[1].country, children[1].lei_status), ("US", "LAPSED"))

    @override_settings(REGISTERS_MAX_ENTITIES=1)
    def test_children_stop_reading_pages_once_the_cap_is_reached(self) -> None:
        self.assertEqual(len(LiveRegisters().children(BANK_LEI)), 1)
        self.assertEqual(len([url for url in self.opened.urls if "direct-children" in url]), 1)

    def test_an_empty_page_ends_the_list_whatever_last_page_claims(self) -> None:
        with mock.patch.object(registers, "_open", return_value=page([], last=1_000_000)) as opened:
            self.assertEqual(LiveRegisters().children(BANK_LEI), [])
        self.assertEqual(opened.call_count, 1)
        with mock.patch.object(registers, "_open", return_value=json.dumps({"data": [], "meta": {}}).encode()):
            with self.assertRaises(RegisterUnavailable):
                LiveRegisters().children(BANK_LEI)

    def test_a_record_of_another_shape_or_not_json_is_unavailable(self) -> None:
        broken = {
            "not json": b"<html>",
            "no data": json.dumps({"errors": []}).encode(),
            "no name": json.dumps({"data": [{"attributes": {"lei": BANK_LEI, "entity": {}, "registration": {"status": "ISSUED"}}}]}).encode(),
            "bad lei": page([record("NOT-AN-LEI", "Example Bank AB", "556000-0001")]),
        }
        for case, body in broken.items():
            with self.subTest(case), mock.patch.object(registers, "_open", return_value=body):
                with self.assertRaises(RegisterUnavailable):
                    LiveRegisters().find("556000-0001")

    def test_a_number_that_is_not_one_never_reaches_a_url(self) -> None:
        for query in ("55/../x", "a", "556000-0001&format=x"):
            with self.subTest(query), self.assertRaises(ValueError):
                LiveRegisters().find(query)
        with self.assertRaises(ValueError):
            LiveRegisters().children("../x")
        self.assertEqual(self.opened.urls, [])


class LiveFinansinspektionen(SimpleTestCase):
    def setUp(self) -> None:
        self.table = answers()
        self.opened = Opened(self.table)
        patcher = mock.patch.object(registers, "_open", self.opened)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_row_with_the_numbers_digits_is_the_company_and_its_cells_are_read_strictly(self) -> None:
        facts = LiveRegisters().licence_facts("fi", "556000-0001")
        assert facts is not None
        self.assertEqual((facts.name, facts.registration_number, facts.lei), ("Example Bank AB", "556000-0001", BANK_LEI))
        self.assertEqual(facts.main_business, "Bankaktiebolag")
        # Kept raw: a business name may hold a comma; the mapping splits it.
        self.assertEqual(facts.other_businesses, "Värdepappersbolag, Riksbolag, livförsäkringar")
        self.assertEqual(
            facts.licences,
            (
                RegisterLicence("Tillstånd att driva bankrörelse, enligt lag (2004:297) om bank- och finansieringsrörelse", date(1995, 3, 1)),
                RegisterLicence("IM_MR_SA", date(2016, 6, 26)),
                RegisterLicence("Ett tillstånd utan datum", None),
            ),
        )
        self.assertEqual(facts.source_url, f"{FI}/index?query=556000-0001&format=csv")

    def test_the_branches_are_the_links_under_filialer_each_with_its_country(self) -> None:
        facts = LiveRegisters().licence_facts("fi", "556000-0001")
        assert facts is not None
        self.assertEqual(
            facts.branches,
            (RegisterBranch("Example Bank AB, filial i Danmark", "Danmark"), RegisterBranch("Example Bank AB, filial i Norge", "Norge")),
        )
        # The search's other hit was opened and passed over; the funds' links were never read.
        self.assertIn(f"{FI}/details?id=11", self.opened.urls)
        self.assertNotIn(f"{FI}/details?id=31", self.opened.urls)

    @override_settings(REGISTERS_MAX_BRANCHES=1)
    def test_the_branches_stop_at_the_cap(self) -> None:
        facts = LiveRegisters().licence_facts("fi", "556000-0001")
        assert facts is not None
        self.assertEqual([branch.country_name for branch in facts.branches], ["Danmark"])

    def test_a_company_the_register_does_not_hold_is_none_and_no_page_is_read(self) -> None:
        self.table[f"{FI}/index?query=556000-0004&format=csv"] = fi_csv(OTHER_ROW)
        self.assertIsNone(LiveRegisters().licence_facts("fi", "556000-0004"))
        self.assertEqual(self.opened.urls, [f"{FI}/index?query=556000-0004&format=csv"])

    def test_a_company_without_a_page_of_its_own_has_no_branches(self) -> None:
        self.table[f"{FI}/index?query=556000-0001"] = "<html><body><p>Inga träffar</p></body></html>".encode()
        facts = LiveRegisters().licence_facts("fi", "556000-0001")
        assert facts is not None
        self.assertEqual(facts.branches, ())

    def test_a_changed_format_is_unavailable_never_a_guess(self) -> None:
        cases = {
            "another header": (f"{FI}/index?query=556000-0001&format=csv", fi_csv(BANK_ROW, header=HEADER.replace("Org.nummer", "Organisationsnummer"))),
            "an empty file": (f"{FI}/index?query=556000-0001&format=csv", b""),
            "a short row": (f"{FI}/index?query=556000-0001&format=csv", fi_csv("Example Bank AB;556000-0001")),
            "not utf-8": (f"{FI}/index?query=556000-0001&format=csv", HEADER.encode("utf-16")),
            "a company page without its number": (f"{FI}/details?id=11", b"<html><h1>Foretagsregistret</h1></html>"),
            "a branch page without an address": (f"{FI}/details?id=21", "<html><h1>Företagsregistret</h1><h2>Filial</h2></html>".encode()),
            "a branch page without a name": (f"{FI}/details?id=22", "<html><h1>Företagsregistret</h1><dl><dt>Adress</dt><dd>Norge</dd></dl></html>".encode()),
        }
        for case, (url, body) in cases.items():
            with self.subTest(case), mock.patch.object(registers, "_open", Opened({**answers(), url: body})):
                with self.assertRaises(RegisterUnavailable):
                    LiveRegisters().licence_facts("fi", "556000-0001")

    def test_a_register_text_is_one_clean_line_of_bounded_length(self) -> None:
        row = "Example\u202e Bank\tAB;556000-0001;;Bankaktiebolag;;2001-05-01 - " + "x" * 2000
        self.table[f"{FI}/index?query=556000-0001&format=csv"] = fi_csv(row)
        facts = LiveRegisters().licence_facts("fi", "556000-0001")
        assert facts is not None
        self.assertEqual(facts.name, "Example Bank AB")
        self.assertEqual(len(facts.licences[0].text), registers.TEXT_MAX)

    def test_only_the_authorities_it_reads_and_a_real_number(self) -> None:
        with self.assertRaises(ValueError):
            LiveRegisters().licence_facts("finanstilsynet-dk", "556000-0001")
        with self.assertRaises(ValueError):
            LiveRegisters().licence_facts("fi", "556000-0001;x=1")
        self.assertIsNone(LiveRegisters().licence_facts("fi", "ABCD"))
        self.assertEqual(self.opened.urls, [])


class Response(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200) -> None:
        super().__init__(body)
        self.status = status


class OneNetworkFunction(SimpleTestCase):
    """`_open`: the configured hosts over https, no redirect, a byte cap, a timeout, a fixed
    user agent, and any failure `RegisterUnavailable`."""

    def opener(self, outcome: Any) -> Any:
        return mock.patch.object(registers._OPENER, "open", side_effect=[outcome] if isinstance(outcome, BaseException) else None, return_value=outcome)

    def test_a_read_carries_the_user_agent_and_the_timeout(self) -> None:
        with self.opener(Response(b"{}")) as opened:
            self.assertEqual(registers._open(f"{GLEIF}/lei-records/{BANK_LEI}"), b"{}")
        request, = opened.call_args.args
        self.assertEqual(request.get_header("User-agent"), "bleqq-registers/1")
        self.assertEqual(opened.call_args.kwargs["timeout"], 10)

    def test_another_host_a_port_or_plain_http_is_refused_before_any_connection(self) -> None:
        for url in (
            "https://example.com/lei-records",
            "http://api.gleif.org/api/v1/lei-records",
            "https://api.gleif.org:8443/api/v1/lei-records",
            "https://user@www.fi.se/sv/",
            "file:///etc/passwd",
        ):
            with self.subTest(url), self.opener(Response(b"")) as opened:
                with self.assertRaises(RegisterUnavailable):
                    registers._open(url)
                opened.assert_not_called()

    @override_settings(REGISTERS_MAX_BYTES=10_000)
    def test_more_than_the_cap_is_unavailable(self) -> None:
        with self.opener(Response(b"x" * 10_001)):
            with self.assertRaises(RegisterUnavailable):
                registers._open(f"{FI}/index?query=1")
        with self.opener(Response(b"x" * 10_000)):
            self.assertEqual(len(registers._open(f"{FI}/index?query=1")), 10_000)

    def test_a_redirect_is_refused_as_a_failed_read(self) -> None:
        request = urllib.request.Request(f"{FI}/index")  # noqa: S310 an https constant, never opened
        with self.assertRaises(urllib.error.HTTPError):
            registers._RefuseRedirects().redirect_request(request, io.BytesIO(), 302, "Found", http.client.HTTPMessage(), "https://example.com/")
        self.assertTrue(any(isinstance(handler, registers._RefuseRedirects) for handler in vars(registers._OPENER)["handlers"]))
        with self.opener(urllib.error.HTTPError(f"{FI}/index", 302, "Found", http.client.HTTPMessage(), None)):
            with self.assertRaises(RegisterUnavailable) as caught:
                registers._open(f"{FI}/index")
        self.assertNotIsInstance(caught.exception, RegisterNotFound)

    def test_a_404_is_not_found_and_every_other_failure_is_unavailable(self) -> None:
        with self.opener(urllib.error.HTTPError(f"{GLEIF}/x", 404, "Not Found", http.client.HTTPMessage(), None)):
            with self.assertRaises(RegisterNotFound):
                registers._open(f"{GLEIF}/x")
        for failure in (
            urllib.error.HTTPError(f"{GLEIF}/x", 503, "Unavailable", http.client.HTTPMessage(), None),
            urllib.error.URLError("refused"),
            TimeoutError(),
            ConnectionResetError(),
        ):
            with self.subTest(type(failure).__name__), self.opener(failure):
                with self.assertRaises(RegisterUnavailable):
                    registers._open(f"{GLEIF}/x")
        with self.opener(Response(b"", status=203)):
            with self.assertRaises(RegisterUnavailable):
                registers._open(f"{GLEIF}/x")


class MockIsTheE2EGroup(SimpleTestCase):
    def tearDown(self) -> None:
        MockRegisters.reset()

    def test_find_by_number_with_or_without_the_hyphen_or_by_lei(self) -> None:
        for query in ("556000-0001", "5560000001", BANK_LEI, BANK_LEI.lower()):
            with self.subTest(query):
                self.assertEqual([company.name for company in MockRegisters().find(query)], ["Example Bank AB"])
        self.assertEqual(MockRegisters().find("556000-0000"), [])
        self.assertEqual(len(MockRegisters().find(registers.MOCK_AMBIGUOUS)), 2)
        with self.assertRaises(RegisterUnavailable):
            MockRegisters().find(registers.MOCK_UNAVAILABLE)

    def test_the_group_and_its_facts_are_the_same_every_time(self) -> None:
        names = [child.name for child in MockRegisters().children(BANK_LEI)]
        self.assertEqual(names, ["Example Fonder AB", "Example Liv Försäkring AB", "Example Holding AB", "Example Pank AS"])
        self.assertEqual(MockRegisters().children("549300EXAMPLEFOND002"), [])
        bank = MockRegisters().licence_facts("fi", "556000-0001")
        self.assertEqual(bank, MockRegisters().licence_facts("fi", "5560000001"))
        assert bank is not None
        self.assertEqual([branch.country_name for branch in bank.branches], ["Danmark", "Norge"])
        self.assertEqual(bank.licences[-1], RegisterLicence("IM_MR_SA", date(2016, 6, 26)))
        self.assertEqual(bank.source_url, f"{FI}/index?query=556000-0001&format=csv")
        self.assertIsNone(MockRegisters().licence_facts("fi", "556000-0004"))
        with self.assertRaises(ValueError):
            MockRegisters().licence_facts("eba", "556000-0001")

    def test_an_override_answers_until_reset(self) -> None:
        MockRegisters.override("556000-0001", None)
        self.assertIsNone(MockRegisters().licence_facts("fi", "5560000001"))
        MockRegisters.override("556000-0001", RegisterUnavailable("down"))
        with self.assertRaises(RegisterUnavailable):
            MockRegisters().licence_facts("fi", "556000-0001")
        MockRegisters.reset()
        self.assertIsNotNone(MockRegisters().licence_facts("fi", "556000-0001"))
