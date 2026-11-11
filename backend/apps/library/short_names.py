"""The name an instrument goes by on screen: one to three words (Alex, 2026-11-11, D-132).

A pill, a citation or a heading names an instrument by its short name, and the baseline
holds a descriptive title there for about half the library ("Bekendtgørelse om god skik
for finansielle virksomheder"), which no pill can hold. Until a person approves a shorter
name, an instrument whose short name runs past `INSTRUMENT_SHORT_NAME_MAX_WORDS` goes by a
compact form of its official reference, built only from what the reference itself says:

- a Danish reference, `BEK nr 330 af 07/04/2016`, by its kind, number and year: `BEK 330/2016`;
- a Union act, `Commission Delegated Regulation (EU) 2016/167` or `Council Directive
  2014/107/EU`, by the Union and its number: `EU 2016/167`, `EU 2014/107`, `EC 881/2002`;
  a CELEX number of a regulation, directive or decision, `CELEX 32017L0593`, the same way
  from its year and number: `EU 2017/593`;
- any other reference that is short enough by itself, as it is: `SFS 2023:677`,
  `FOR-2019-02-15-152`, `929/2021`, `EBA/GL/2021/02`.

A reference none of these fits leaves the short name as it is. Nothing is stored: the
short name the library holds is unchanged, a proposal still carries and shows it, and a
shorter one approved later takes over by itself.
"""

from __future__ import annotations

import re

from django.conf import settings

_DANISH = re.compile(r"^(?P<kind>[A-ZÆØÅ]{2,4}) nr\.? (?P<number>\d+) af \d{1,2}/\d{1,2}/(?P<year>\d{4})$")
_UNION_ACT = re.compile(r"\((?P<union>EU|EC|EEC)\)(?: No)? (?P<number>\d+/\d+)$")
_UNION_DIRECTIVE = re.compile(r"Directive (?P<number>\d{4}/\d+)/(?P<union>EU|EC|EEC)$")
# Sector 3 (legislation), the year, the type (R regulation, L directive, D decision), the number.
_CELEX = re.compile(r"^CELEX 3(?P<year>\d{4})[RLD](?P<number>\d{4})$")


def shown_short_name(short_name: str, official_ref: str) -> str:
    """The short name, when it is at most `INSTRUMENT_SHORT_NAME_MAX_WORDS` words, else the
    compact official reference the module docstring describes, else the short name."""
    limit = settings.INSTRUMENT_SHORT_NAME_MAX_WORDS
    if len(short_name.split()) <= limit:
        return short_name
    reference = official_ref.strip()
    if danish := _DANISH.match(reference):
        return f"{danish['kind']} {danish['number']}/{danish['year']}"
    if union := _UNION_ACT.search(reference) or _UNION_DIRECTIVE.search(reference):
        return f"{union['union']} {union['number']}"
    if celex := _CELEX.match(reference):
        return f"EU {celex['year']}/{int(celex['number'])}"
    if reference and len(reference.split()) <= limit:
        return reference
    return short_name
