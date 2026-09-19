"""Business logic of the library app. Raises ValidationError with user-facing text; every
write goes through record(); every threshold comes from settings (playbook 3)."""

from __future__ import annotations

import datetime
import difflib
import re
from collections.abc import Iterable
from typing import Literal, Protocol, TypeVar

from django.conf import settings


class Versioned(Protocol):
    @property
    def version_number(self) -> int: ...

    @property
    def effective_from(self) -> datetime.date | None: ...


V = TypeVar("V", bound=Versioned)


def in_force(versions: Iterable[V], on: datetime.date) -> V | None:
    """The version in force on `on` (AC-INV1, data-model §4): the one with the latest
    `effective_from` on or before the date, a null meaning since always. Two versions
    effective the same day: the later version number is the correction and wins. None
    when every version starts after the date."""
    candidates = [v for v in versions if v.effective_from is None or v.effective_from <= on]
    return max(candidates, key=lambda v: (v.effective_from or datetime.date.min, v.version_number), default=None)


# ---------------------------------------------------------------------------------------
# "Show what changed" (INV-04, AC-INV1): a sentence-level diff between two versions, in a
# language both have (INV-05). Pure: the read routes resolve the versions and serialize.
# Nothing here logs, because the texts are the library's content. The texts come from
# fetched sources through proposals, so both functions stay fast on hostile input:
# splitting is linear, and aligning is capped at LIBRARY_DIFF_MAX_SENTENCES.
# ---------------------------------------------------------------------------------------
DiffOp = Literal["equal", "insert", "delete"]
Segment = tuple[DiffOp, str]

# Legal abbreviations a sentence never ends on, lower case with their dot.
_ABBREVIATIONS = frozenset({"kap.", "art.", "p.", "nr.", "t.ex.", "bl.a.", "m.m.", "jfr.", "e.g.", "i.e."})
# A word ending in ".", "!" or "?" and the white space after it. The word comes from the
# match itself, so a refused boundary costs nothing more than the scan.
_SENTENCE_END = re.compile(r"(?<!\S)(\S*?[.!?])\s+")


def split_sentences(text: str) -> list[str]:
    """A sentence ends at ".", "!" or "?" followed by white space and an upper-case letter:
    so never before a digit or "§" ("9 kap. 6 §"), nor inside a Danish or Norwegian date
    ("1. januar"), and never after a legal abbreviation ("bl.a. Finansinspektionen")."""
    sentences: list[str] = []
    start = 0
    for end in _SENTENCE_END.finditer(text):
        word = end.group(1).lstrip("(").lower()
        if text[end.end() : end.end() + 1].isupper() and word not in _ABBREVIATIONS:
            sentences.append(text[start : end.end(1)].strip())
            start = end.end()
    rest = text[start:].strip()
    return [*sentences, rest] if rest else sentences


def sentence_diff(old: str, new: str) -> list[Segment]:
    """The two texts sentence by sentence: a changed sentence is a delete then an insert.
    Aligning repeated sentences costs up to the cube of their number, so above
    LIBRARY_DIFF_MAX_SENTENCES on either side the old text is one delete and the new one
    one insert: coarse, still correct. autojunk=False because from 200 sentences difflib
    would treat a sentence repeated in over 1% of the new text ("Upphävd.") as junk that
    never matches, and show it as changed; it only matters if the cap is raised past 200."""
    before, after = split_sentences(old), split_sentences(new)
    if before == after:
        return [("equal", sentence) for sentence in before]
    if max(len(before), len(after)) > settings.LIBRARY_DIFF_MAX_SENTENCES:
        whole: list[Segment] = [("delete", old.strip()), ("insert", new.strip())]
        return [segment for segment in whole if segment[1]]
    segments: list[Segment] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=before, b=after, autojunk=False).get_opcodes():
        if op == "equal":
            segments.extend(("equal", sentence) for sentence in before[i1:i2])
        else:
            segments.extend(("delete", sentence) for sentence in before[i1:i2])
            segments.extend(("insert", sentence) for sentence in after[j1:j2])
    return segments


class TranslatedText(Protocol):
    """One language's text of a version: an ObligationSummary or a ProvisionText row."""

    @property
    def language_id(self) -> str: ...

    @property
    def text(self) -> str: ...

    @property
    def is_original(self) -> bool: ...

    @property
    def is_machine(self) -> bool: ...


def version_diff(
    from_texts: Iterable[TranslatedText], to_texts: Iterable[TranslatedText], language_order: list[str], lang: str | None
) -> tuple[str, bool, list[Segment]] | None:
    """The diff in the first language both versions have: `lang` (the reader's ?lang=),
    then their language order, then an original before a machine translation, then any.
    Machine translated when either side is. None when the versions share no language."""
    before = {text.language_id: text for text in from_texts}
    after = {text.language_id: text for text in to_texts}
    shared = before.keys() & after.keys()
    fallback = sorted(shared, key=lambda key: (not (before[key].is_original or after[key].is_original), key))
    language = next((key for key in (lang, *language_order, *fallback) if key in shared), None)
    if language is None:
        return None
    old, new = before[language], after[language]
    return language, old.is_machine or new.is_machine, sentence_diff(old.text, new.text)
