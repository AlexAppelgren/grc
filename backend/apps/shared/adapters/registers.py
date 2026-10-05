"""Public registers seam (TEN-07, TEN-08, FP-05; PUBLIC_REGISTERS.md 5.3): who a bank's
companies are, from GLEIF, and what a Swedish company is licensed for and where it has
branches, from Finansinspektionen's company register.

`live` reads only the two configured hosts, over https, through one function (`_open`):
a timeout per socket operation, no redirects, a byte cap and a fixed user agent. Both
registers are read as untrusted content and answered as facts, never as HTML or JSON: a
GLEIF record or an FI file or page that is not the shape verified on 2026-10-05
(Verification_Log.md) raises `RegisterUnavailable` rather than guessing, and so does any
network failure, any status but 200 and any body over the cap. A registration number is
checked against `REGISTRATION_NUMBER` before it reaches a URL.

- GLEIF (JSON:API): `lei-records/{lei}`; `lei-records?filter[entity.registeredAs]=<number>`
  (the number as typed: GLEIF stores `502032-9081` with its hyphen); and
  `lei-records/{lei}/direct-children`, paged. Only children whose `entity.category` is
  `GENERAL` are companies: funds and branches are left out.
- FI: the register's search exported as text (`index?query=<number>&format=csv`): UTF-8
  with a BOM, `;`-separated, under exactly `FI_HEADER`, one row per company found by a free
  text search, so the row whose `Org.nummer` has the query's digits is the company. Each
  licence cell is `YYYY-MM-DD - <licence>`. A company's branches are on its page
  (`details?id=…`, found through the HTML search): the links under the heading "Filialer",
  each branch's name its heading after "Företagsregistret" and its country the last line of
  its address.

`mock` is deterministic and offline: the E2E seed's Example Group (`MOCK_COMPANIES`).
`MOCK_AMBIGUOUS` finds two companies and `MOCK_UNAVAILABLE` raises `RegisterUnavailable`, so
seeds and tests reach every branch; `MockRegisters.override()` changes what the next read of
one company's licences answers, and `reset()` puts it back.

Nothing here logs a query, a number or a name: a read logs its provider and the elapsed
milliseconds."""

from __future__ import annotations

import csv
import http.client
import io
import json
import logging
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from datetime import date
from html.parser import HTMLParser
from typing import IO, Any, ClassVar

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

LEI = re.compile(r"[A-Z0-9]{18}[0-9]{2}")
REGISTRATION_NUMBER = re.compile(r"[0-9A-Za-z][0-9A-Za-z\- ]{3,30}")
FI_HEADER = [
    "Namn", "Org.nummer", "LEI kod", "Huvudverksamhet", "Övriga verksamheter", "Tillstånd 1", "Tillstånd 2", "Tillstånd 3", "et.c.",
]  # fmt: skip
USER_AGENT = "bleqq-registers/1"
# The longest name and text kept from a register: what OrgUnit.name holds, and a licence's
# whole wording with its legal basis.
NAME_MAX = 200
TEXT_MAX = 1000
# How many hits of FI's HTML search are opened to find the company's own page: the search is
# free text, and the company is among the first. Part of reading the page, not policy.
DETAIL_CANDIDATES = 5
GLEIF_PAGE_SIZE = 100
_DETAILS_LINK = re.compile(r"(?:^|/)details\?id=(\d{1,12})(?:&|$)")
_LICENCE_CELL = re.compile(r"(\d{4}-\d{2}-\d{2}) -\s*(.*)", re.S)
_COUNTRY = re.compile(r"[A-Z]{2}")
_STATUS = re.compile(r"[A-Z_]{1,20}")


@dataclass(frozen=True)
class LeiCompany:
    """A company as GLEIF records it. `country` is the ISO 3166 alpha-2 part of its
    jurisdiction (`US-DE` is `US`), or empty; `parent_lei` is the company it was found under,
    None for the one a lookup started from."""

    lei: str
    name: str
    registration_number: str
    country: str
    parent_lei: str | None
    lei_status: str


@dataclass(frozen=True)
class RegisterLicence:
    """One licence line: its wording, legal basis included, and the date it was granted."""

    text: str
    granted_on: date | None


@dataclass(frozen=True)
class RegisterBranch:
    """A branch abroad: its name and its country as the register writes it (`Danmark`)."""

    name: str
    country_name: str


@dataclass(frozen=True)
class LicenceFacts:
    """What a supervisor's register holds on one company. `other_businesses` is the register's
    own comma-joined text, kept whole: a business name may hold a comma itself
    (`Riksbolag, livförsäkringar`), so splitting it is the mapping's job
    (apps/tenants/registers_logic.py)."""

    name: str
    registration_number: str
    lei: str
    main_business: str
    other_businesses: str
    licences: tuple[RegisterLicence, ...]
    branches: tuple[RegisterBranch, ...]
    source_url: str


class RegisterUnavailable(Exception):
    """A register could not be read, or what it sent is not what it publishes."""


class RegisterNotFound(RegisterUnavailable):
    """A 404: what a single record's address answers when there is no such record."""


class RegistersAdapter(ABC):
    name: str
    # The authorities, by library key, whose register this adapter reads licences from.
    authorities: frozenset[str] = frozenset({"fi"})

    @abstractmethod
    def find(self, query: str) -> list[LeiCompany]:
        """The companies an LEI or a registration number names: an LEI looks up that one
        record, a number every company registered under it. Empty when none is."""

    @abstractmethod
    def children(self, lei: str) -> list[LeiCompany]:
        """The companies directly under `lei`, each with `parent_lei=lei`; no funds, no
        branches."""

    @abstractmethod
    def licence_facts(self, authority_key: str, registration_number: str) -> LicenceFacts | None:
        """The authority's register on one company, or None when it has no such company."""


def _source_url(registration_number: str) -> str:
    return f"{settings.REGISTERS_FI_URL}/index?{urllib.parse.urlencode({'query': registration_number, 'format': 'csv'})}"


def _require_number(registration_number: str) -> None:
    if not REGISTRATION_NUMBER.fullmatch(registration_number):
        raise ValueError("a registration number is 4 to 31 letters, digits, hyphens and spaces")


def digits(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


def _clean(value: Any, cap: int) -> str:
    """Text from a register as one line: no control or format character (a bidi override can
    make a name read as another), white space collapsed, at most `cap` characters."""
    if not isinstance(value, str):
        raise RegisterUnavailable("a register sent a value that is not text")
    kept = "".join(character for character in value if character.isspace() or unicodedata.category(character) not in ("Cc", "Cf"))
    return " ".join(kept.split())[:cap]


# ---------------------------------------------------------------------------------------
# The network: one function, the only one that leaves the machine.
# ---------------------------------------------------------------------------------------
class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Neither register redirects what it is asked for; a redirect could only lead somewhere
    else, so it is a failed read like any other status (as apps/shared/adapters/llm.py)."""

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


def _allowed(url: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    hosts = {urllib.parse.urlsplit(base).netloc for base in (settings.REGISTERS_GLEIF_URL, settings.REGISTERS_FI_URL)}
    return parts.scheme == "https" and parts.netloc in hosts


def _open(url: str) -> bytes:
    """The body at `url`, at most REGISTERS_MAX_BYTES of it. Only an https address on one of
    the two configured hosts is opened; a test replaces this function."""
    if not _allowed(url):
        raise RegisterUnavailable("only the configured registers are read")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310 _allowed() admits https on the two configured hosts only
    started = time.monotonic()
    try:
        with _OPENER.open(request, timeout=settings.REGISTERS_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise RegisterUnavailable(f"a register answered {response.status}")
            body: bytes = response.read(settings.REGISTERS_MAX_BYTES + 1)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise RegisterNotFound("no such record") from None
        raise RegisterUnavailable(f"a register answered {error.code}") from None
    except (urllib.error.URLError, OSError, http.client.HTTPException):
        raise RegisterUnavailable("a register could not be reached") from None
    finally:
        logger.info("register read", extra={"provider": "live", "elapsed_ms": round((time.monotonic() - started) * 1000)})
    if len(body) > settings.REGISTERS_MAX_BYTES:
        raise RegisterUnavailable("a register sent more than REGISTERS_MAX_BYTES")
    return body


# ---------------------------------------------------------------------------------------
# GLEIF
# ---------------------------------------------------------------------------------------
def _json(body: bytes) -> Any:
    try:
        return json.loads(body)
    except ValueError:
        raise RegisterUnavailable("GLEIF sent something that is not JSON") from None


def _company(record: Any, parent_lei: str | None) -> LeiCompany:
    try:
        attributes = record["attributes"]
        entity = attributes["entity"]
        lei = attributes["lei"]
        jurisdiction = entity.get("jurisdiction") or ""
        status = attributes["registration"]["status"]
        name = _clean(entity["legalName"]["name"], NAME_MAX)
        number = _clean(entity.get("registeredAs") or "", 40)
    except (KeyError, TypeError, AttributeError):
        raise RegisterUnavailable("GLEIF sent a record of another shape") from None
    if not (isinstance(lei, str) and LEI.fullmatch(lei) and isinstance(status, str) and _STATUS.fullmatch(status) and name):
        raise RegisterUnavailable("GLEIF sent a record of another shape")
    country = jurisdiction.split("-")[0].upper() if isinstance(jurisdiction, str) else ""
    return LeiCompany(
        lei=lei,
        name=name,
        registration_number=number,
        country=country if _COUNTRY.fullmatch(country) else "",
        parent_lei=parent_lei,
        lei_status=status,
    )


def _records(document: Any) -> list[Any]:
    data = document.get("data") if isinstance(document, dict) else None
    if not isinstance(data, list):
        raise RegisterUnavailable("GLEIF sent a list of another shape")
    return data


def _category(record: Any) -> Any:
    try:
        return record["attributes"]["entity"]["category"]
    except (KeyError, TypeError):
        raise RegisterUnavailable("GLEIF sent a record of another shape") from None


# ---------------------------------------------------------------------------------------
# Finansinspektionen
# ---------------------------------------------------------------------------------------
def _fi_rows(body: bytes) -> list[list[str]]:
    """The data rows of FI's export, each at least the five fixed columns, or
    RegisterUnavailable when the file is not the one FI publishes."""
    try:
        rows = [row for row in csv.reader(io.StringIO(body.decode("utf-8-sig")), delimiter=";") if row]
    except (UnicodeDecodeError, csv.Error):
        raise RegisterUnavailable("FI's register sent a file that does not read") from None
    if not rows or rows[0] != FI_HEADER:
        raise RegisterUnavailable("FI's register changed its format")
    if any(len(row) < 5 for row in rows[1:]):
        raise RegisterUnavailable("FI's register changed its format")
    return rows[1:]


def _licence(cell: str) -> RegisterLicence | None:
    cell = cell.strip()
    match = _LICENCE_CELL.fullmatch(cell)
    granted: date | None = None
    if match:
        try:
            granted = date.fromisoformat(match.group(1))
            cell = match.group(2)
        except ValueError:
            granted = None
    text = _clean(cell, TEXT_MAX)
    return RegisterLicence(text=text, granted_on=granted) if text else None


@dataclass(frozen=True)
class _Line:
    """One run of text on a page: whether it is a heading or a label (`dt`), and the id of
    the `details?id=` link it sits in, if any."""

    text: str
    heading: bool = False
    label: bool = False
    link: str | None = None


class _PageText(HTMLParser):
    """A page as its lines of text; scripts and styles are skipped and nothing is executed."""

    HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[_Line] = []
        self._skip = 0
        self._heading = 0
        self._label = False
        self._link: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in self.HEADINGS:
            self._heading += 1
            self._label = False
        elif tag == "dt":
            self._label = True
        elif tag == "dd":
            self._label = False
        elif tag == "a":
            match = _DETAILS_LINK.search(dict(attrs).get("href") or "")
            self._link = match.group(1) if match else None

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = max(self._skip - 1, 0)
        elif tag in self.HEADINGS:
            self._heading = max(self._heading - 1, 0)
        elif tag == "dt":
            self._label = False
        elif tag == "a":
            self._link = None

    def handle_data(self, data: str) -> None:
        text = _clean(data, TEXT_MAX)
        if text and not self._skip:
            self.lines.append(_Line(text=text, heading=self._heading > 0, label=self._label, link=self._link))


def _page(body: bytes) -> list[_Line]:
    try:
        parser = _PageText()
        parser.feed(body.decode("utf-8"))
        parser.close()
    except UnicodeDecodeError:
        raise RegisterUnavailable("FI's register sent a page that does not read") from None
    return parser.lines


def _value(lines: list[_Line], label: str) -> list[str] | None:
    """The lines under the label `label` up to the next label or heading, or None when the
    page has no such label."""
    for index, line in enumerate(lines):
        if line.label and line.text == label:
            found: list[str] = []
            for following in lines[index + 1 :]:
                if following.label or following.heading:
                    break
                found.append(following.text)
            return found
    return None


def _links_under(lines: list[_Line], heading: str) -> list[str]:
    """The `details?id=` links after the heading `heading`, up to the next heading, in order."""
    for index, line in enumerate(lines):
        if line.heading and line.text == heading:
            found: list[str] = []
            for following in lines[index + 1 :]:
                if following.heading:
                    break
                if following.link and following.link not in found:
                    found.append(following.link)
            return found
    return []


class LiveRegisters(RegistersAdapter):
    name = "live"

    # --- GLEIF -------------------------------------------------------------------------
    def find(self, query: str) -> list[LeiCompany]:
        query = query.strip()
        base = settings.REGISTERS_GLEIF_URL
        if LEI.fullmatch(query.upper()):
            try:
                body = _open(f"{base}/lei-records/{query.upper()}")
            except RegisterNotFound:
                return []
            document = _json(body)
            return [_company(document.get("data") if isinstance(document, dict) else None, None)]
        _require_number(query)
        address = f"{base}/lei-records?{urllib.parse.urlencode({'filter[entity.registeredAs]': query, 'page[size]': 10})}"
        return [_company(record, None) for record in _records(_json(_open(address)))]

    def children(self, lei: str) -> list[LeiCompany]:
        if not LEI.fullmatch(lei):
            raise ValueError("an LEI is 20 letters and digits, ending in two digits")
        found: list[LeiCompany] = []
        page, last = 1, 1
        while page <= last and len(found) < settings.REGISTERS_MAX_ENTITIES:
            query = urllib.parse.urlencode({"page[size]": GLEIF_PAGE_SIZE, "page[number]": page})
            document = _json(_open(f"{settings.REGISTERS_GLEIF_URL}/lei-records/{lei}/direct-children?{query}"))
            records = _records(document)
            found.extend(_company(record, lei) for record in records if _category(record) == "GENERAL")
            try:
                last = document["meta"]["pagination"]["lastPage"]
            except (KeyError, TypeError):
                raise RegisterUnavailable("GLEIF sent a list of another shape") from None
            if not isinstance(last, int):
                raise RegisterUnavailable("GLEIF sent a list of another shape")
            # An empty page ends the list whatever `lastPage` claims.
            page = page + 1 if records else last + 1
        return found

    # --- Finansinspektionen ------------------------------------------------------------
    def licence_facts(self, authority_key: str, registration_number: str) -> LicenceFacts | None:
        if authority_key not in self.authorities:
            raise ValueError(f"no register is read for the authority {authority_key!r}")
        _require_number(registration_number)
        wanted = digits(registration_number)
        if not wanted:
            return None
        source = _source_url(registration_number)
        row = next((row for row in _fi_rows(_open(source)) if digits(row[1]) == wanted), None)
        if row is None:
            return None
        licences = tuple(licence for licence in (_licence(cell) for cell in row[5:]) if licence is not None)
        return LicenceFacts(
            name=_clean(row[0], NAME_MAX),
            registration_number=_clean(row[1], 40),
            lei=_clean(row[2], 20),
            main_business=_clean(row[3], NAME_MAX),
            other_businesses=_clean(row[4], TEXT_MAX),
            licences=licences,
            branches=self._branches(registration_number, wanted),
            source_url=source,
        )

    def _branches(self, registration_number: str, wanted: str) -> tuple[RegisterBranch, ...]:
        search = _page(_open(f"{settings.REGISTERS_FI_URL}/index?{urllib.parse.urlencode({'query': registration_number})}"))
        candidates = list(dict.fromkeys(line.link for line in search if line.link))[:DETAIL_CANDIDATES]
        for candidate in candidates:
            page = _page(_open(self._details(candidate)))
            number = _value(page, "Organisationsnummer")
            if number is None:
                raise RegisterUnavailable("FI's register changed its company page")
            if number and digits(number[0]) == wanted:
                links = _links_under(page, "Filialer")[: settings.REGISTERS_MAX_BRANCHES]
                return tuple(self._branch(link) for link in links)
        return ()

    def _branch(self, link: str) -> RegisterBranch:
        page = _page(_open(self._details(link)))
        headings = [line.text for line in page if line.heading]
        after = headings[headings.index("Företagsregistret") + 1 :] if "Företagsregistret" in headings else []
        address = _value(page, "Adress")
        if not after or address is None:
            raise RegisterUnavailable("FI's register changed its branch page")
        return RegisterBranch(name=_clean(after[0], NAME_MAX), country_name=address[-1] if address else "")

    @staticmethod
    def _details(link: str) -> str:
        return f"{settings.REGISTERS_FI_URL}/details?{urllib.parse.urlencode({'id': link})}"


# ---------------------------------------------------------------------------------------
# The mock: the E2E seed's Example Group, offline.
# ---------------------------------------------------------------------------------------
MOCK_ROOT = "549300EXAMPLEBANK001"
# A number two companies carry, so a lookup by it is ambiguous; and one whose read fails.
MOCK_AMBIGUOUS = "556000-9999"
MOCK_UNAVAILABLE = "556000-0666"
MOCK_COMPANIES: dict[str, LeiCompany] = {
    company.lei: company
    for company in (
        LeiCompany(MOCK_ROOT, "Example Bank AB", "556000-0001", "SE", None, "ISSUED"),
        LeiCompany("549300EXAMPLEFOND002", "Example Fonder AB", "556000-0003", "SE", MOCK_ROOT, "ISSUED"),
        LeiCompany("549300EXAMPLELIVF003", "Example Liv Försäkring AB", "516000-0002", "SE", MOCK_ROOT, "ISSUED"),
        LeiCompany("549300EXAMPLEHOLD004", "Example Holding AB", "556000-0004", "SE", MOCK_ROOT, "ISSUED"),
        LeiCompany("549300EXAMPLEPANK005", "Example Pank AS", "10000005", "EE", MOCK_ROOT, "ISSUED"),
    )
}
_MOCK_TWINS = (
    LeiCompany("549300EXAMPLETWIN006", "Example Twin AB", MOCK_AMBIGUOUS, "SE", None, "ISSUED"),
    LeiCompany("549300EXAMPLETWIN007", "Example Twin Holding AB", MOCK_AMBIGUOUS, "SE", None, "LAPSED"),
)
_SECURITIES_LAW = "lagen [2007:528] om värdepappersmarknaden"
_INSURANCE_LAW = "försäkringsrörelselagen (2010:2043)"
_MOCK_FACTS: dict[str, tuple[str, str, str, tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]] = {
    # digits of the number -> (LEI, main business, other businesses, licences, branches)
    "5560000001": (
        MOCK_ROOT,
        "Bankaktiebolag",
        "Värdepappersbolag, Försäkringsdistribution, Medelstort institut",
        (
            ("1995-03-01", "Tillstånd att driva bankrörelse, enligt lag 2004:297 om bank- och finansieringsrörelse"),
            ("2007-11-01", f"Investeringsrådgivning till kund beträffande finansiella instrument, enligt 2 kap. 1 § 5 p. {_SECURITIES_LAW}"),
            ("2007-11-01", f"Diskretionär portföljförvaltning beträffande finansiella instrument, enligt 2 kap. 1 § 4 p. {_SECURITIES_LAW}"),
            ("2018-10-01", "Tillstånd att bedriva försäkringsdistribution avseende försäkringsbaserade investeringsprodukter"),
            ("2016-06-26", "IM_MR_SA"),
        ),
        (("Example Bank AB, filial i Danmark", "Danmark"), ("Example Bank AB, filial i Norge", "Norge")),
    ),
    "5560000003": (
        "549300EXAMPLEFOND002",
        "Fondbolag",
        "Auktoriserad AIF-förvaltare",
        (
            ("2001-05-01", "Tillstånd att driva fondverksamhet, enligt lagen (2004:46) om värdepappersfonder"),
            ("2001-05-01", "Diskretionär portföljförvaltning avseende finansiella instrument"),
            ("2014-07-22", "Tillstånd att förvalta alternativa investeringsfonder"),
        ),
        (),
    ),
    "5160000002": (
        "549300EXAMPLELIVF003",
        "Riksbolag, livförsäkringar",
        "",
        (
            ("1992-01-01", f"Koncession, [2 kap. 1 § {_INSURANCE_LAW}]"),
            ("1992-01-01", f"Ia) Livförsäkring (direkt), [2 kap. 12 § {_INSURANCE_LAW}]"),
            ("1992-01-01", f"III. Försäkring anknuten till värdepappersfonder (direkt), [2 kap. 12 § {_INSURANCE_LAW}]"),
        ),
        (),
    ),
}


def _mock_facts(registration_number: str) -> LicenceFacts | None:
    spec = _MOCK_FACTS.get(digits(registration_number))
    if spec is None:
        return None
    lei, main, other, licences, branches = spec
    return LicenceFacts(
        name=MOCK_COMPANIES[lei].name,
        registration_number=MOCK_COMPANIES[lei].registration_number,
        lei=lei,
        main_business=main,
        other_businesses=other,
        licences=tuple(RegisterLicence(text=text, granted_on=date.fromisoformat(day)) for day, text in licences),
        branches=tuple(RegisterBranch(name=name, country_name=country) for name, country in branches),
        source_url=_source_url(MOCK_COMPANIES[lei].registration_number),
    )


class MockRegisters(RegistersAdapter):
    """Deterministic and offline. `override()` makes every later read of one company's
    licences answer other facts, None or an exception, until `reset()`."""

    name = "mock"
    _overrides: ClassVar[dict[str, LicenceFacts | None | Exception]] = {}

    def find(self, query: str) -> list[LeiCompany]:
        query = query.strip()
        if digits(query) == digits(MOCK_UNAVAILABLE) and not LEI.fullmatch(query.upper()):
            raise RegisterUnavailable("the mock register is down for this number")
        if digits(query) == digits(MOCK_AMBIGUOUS) and not LEI.fullmatch(query.upper()):
            return list(_MOCK_TWINS)
        return [
            replace(company, parent_lei=None)
            for company in MOCK_COMPANIES.values()
            if query.upper() == company.lei or (digits(query) and digits(query) == digits(company.registration_number))
        ]

    def children(self, lei: str) -> list[LeiCompany]:
        return [company for company in MOCK_COMPANIES.values() if company.parent_lei == lei]

    def licence_facts(self, authority_key: str, registration_number: str) -> LicenceFacts | None:
        if authority_key not in self.authorities:
            raise ValueError(f"no register is read for the authority {authority_key!r}")
        _require_number(registration_number)
        key = digits(registration_number)
        if key in self._overrides:
            outcome = self._overrides[key]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return _mock_facts(registration_number)

    @classmethod
    def override(cls, registration_number: str, outcome: LicenceFacts | None | Exception) -> None:
        cls._overrides[digits(registration_number)] = outcome

    @classmethod
    def reset(cls) -> None:
        cls._overrides.clear()


PROVIDERS: dict[str, type[RegistersAdapter]] = {"mock": MockRegisters, "live": LiveRegisters}


def get_registers() -> RegistersAdapter:
    """The configured registers. The mock answers a made-up group, so it is refused on every
    deployed environment but the one named `test` (production-safety rule 5 refuses it at boot
    as well)."""
    provider = settings.REGISTERS_PROVIDER
    if provider not in PROVIDERS:
        raise ValueError(f"REGISTERS_PROVIDER={provider!r} is not one of {sorted(PROVIDERS)}")
    if provider == "mock" and settings.IS_DEPLOYED_ENVIRONMENT and settings.ENVIRONMENT != settings.MOCKS_ALLOWED_DEPLOYED_ENVIRONMENT:
        raise ImproperlyConfigured(
            f"REGISTERS_PROVIDER=mock on deployed environment {settings.ENVIRONMENT!r}: set it to live (TEN-07)."
        )
    return PROVIDERS[provider]()
