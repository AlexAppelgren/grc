"""The content screen (AGT-07, playbook 11.2): fetched text is data, never instructions.

`screen(text)` returns the risk-flag keys a fetched body earns, today only
`embedded_instructions`. It is deterministic and pure: no model call, no network, no
state, and the text it is given is never altered. A hit is recorded beside the stored
document in `change_document.risk_flags`; the change is still registered from the
factual content around the hit and the passage is never followed
(`agents/watch-sweeper/v1/prompt.md`).

The screen reads a normalised copy of the text so that casing, irregular spacing,
invisible characters and compatibility forms cannot hide a phrase, and it looks for the
six shapes an injection takes: an instruction phrase, a role or system prefix, a claim of
authority, an aside addressed to an AI, a tool-call shaped payload, and HTML comments or
hidden elements. Phrases are matched in the five content languages (en, sv, da, nb, fi).

Every pattern is a bounded alternation over fixed words: no nested quantifier, so a
hostile page cannot make the screen backtrack (`tests_screen.py` screens 200 KB well
inside a tenth of its budget).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

EMBEDDED_INSTRUCTIONS = "embedded_instructions"

# Invisible characters hidden inside a word ("ig<ZWSP>nore"): soft hyphen, the Mongolian
# vowel separator, the zero-width and bidi controls, the word joiner and the invisible
# operators, and the byte-order mark. NFKC folds the rest (full width, compatibility forms).
_INVISIBLE = re.compile(
    "[\u00ad\u180e\u200b-\u200f\u202a-\u202e\u2060-\u2064\u206a-\u206f\ufeff]"
)
_HORIZONTAL_SPACE = re.compile(r"[^\S\n]+")
# Four or more single letters spaced apart ("i g n o r e") are one word.
_SPACED_LETTERS = re.compile(r"(?<![^\W\d_])((?:[^\W\d_] ){3,}[^\W\d_])(?![^\W\d_])")

# Up to three characters of spacing, punctuation or markup between the words of a phrase.
_GAP = r"[\s\W_]{0,3}"
# A colon that ends a word rather than sitting inside an abbreviation ("AI:s", "FI:s").
_END_OF_WORD = r"(?![^\W\d_])"


def _phrase(*parts: str) -> str:
    """One phrase: the parts in order, whatever spacing, punctuation or markup separates them."""
    return _GAP.join(parts)


_INSTRUCTION_PHRASE = "|".join(
    (
        # "Ignore previous instructions", and the rest of the override family.
        _phrase(
            r"(?:ignore|disregard|forget|override|bypass)",
            r"(?:all|any|the|your|these|those)?",
            r"(?:previous|prior|earlier|preceding|above|foregoing|original|system|standing)",
            r"(?:instruction|prompt|rule|direction|guideline|guidance|message|context)",
        ),
        # The same in the four Nordic languages: "bortse från", "ignorer alle", "ohita kaikki".
        _phrase(
            r"(?:bortse|se" + _GAP + r"bort|ignorera|ignorer|ignoroi|ohita|unohda|glem|glöm"
            r"|overse|strunta" + _GAP + r"i|jätä" + _GAP + r"huomiotta)",
            r"(?:från|fra|frå|i)?",
            r"(?:tidigare|tidligere|aiemmat|aiemmista|edelliset|edellinen|föregående|forrige"
            r"|ovanstående|ovenstående|alla|alle|kaikki|dina|dine|instruktion\w*|instruks\w*"
            r"|ohje\w*|vokabulär\w*|vokabular\w*|ordlist\w*|sanast\w*|prompt\w*|reglerna"
            r"|reglene|säännöt)",
        ),
        # Steering the classification, the confidence or the decision.
        _phrase(
            r"(?:classify|klassificer\w*|klassifiser\w*|luokittele)",
            r"(?:this|detta|dette|denne|tämä|tätä)",
        ),
        _phrase(
            r"(?:confidence|konfidens|luottamus\w*|tillit)",
            r"(?:to|till|til|=)?",
            r"(?:1\.0|1,0|100)",
        ),
        _phrase(
            r"(?:approve\w*|godkänn\w*|godkend\w*|godkjenn\w*|hyväksy\w*)",
            r"(?:every|all|alla|alle|kaikki|samtliga|hvert|hver|jokainen|pending|väntande)",
        ),
        _phrase(
            r"(?:skip|hoppa" + _GAP + r"över|hopp" + _GAP + r"over|spring" + _GAP + r"over"
            r"|ohita)",
            r"(?:the|den|det)?",
            r"(?:human|manual|manuell\w*|review|granskning\w*|gjennomgang\w*|gennemgang\w*"
            r"|tarkastus\w*|arviointi\w*)",
        ),
        _phrase(
            r"(?:do" + _GAP + r"not|don'?t|never)",
            r"(?:ask|tell|inform|notify|involve|consult|alert)",
            r"(?:a|an|the)?",
            r"(?:human|person|people|reviewer|editor|user|anyone|operator)",
        ),
        # Asking for what the run holds, or for a different mode.
        _phrase(
            r"(?:print|reveal|show|output|repeat|list|disclose)",
            r"(?:your|the)",
            r"(?:api" + _GAP + r"key|system" + _GAP + r"prompt|prompt|instructions|tools"
            r"|secret\w*|credential\w*)",
        ),
        _phrase(r"you", r"are", r"now", r"(?:in|a|the)"),
        _phrase(r"(?:maintenance|developer|debug|god|admin)", r"mode"),
    )
)

# "SYSTEM:", "assistant:", "<!-- agent:": a turn label pasted into the page. Allowed after a
# line start, a fence, a bracket or a sentence end, and never inside an abbreviation.
_ROLE_PREFIX = (
    r"(?:^|[`>\[\](){}\"'|*#~]|[.!?…]\s)"
    r"[\s>\-*#`|]{0,8}"
    r"(?:system|assistenten|assistentti|assistent|assistant|developer|agent|ai"
    r"|instruktioner|instruktion|instructions|instruction|ohjeet|ohje)"
    r"\s{0,3}:" + _END_OF_WORD
)

_AUTHORITY = "|".join(
    (
        _phrase(
            r"as",
            r"the",
            r"(?:platform|system|site|tenant|library|super)",
            r"(?:administrator|admin|owner|operator|developer|editor)",
        ),
        _phrase(
            r"(?:i|jag|jeg|minä)",
            r"(?:hereby)?",
            r"(?:authorise|authorize|instruct|permit|order|direct|auktoriserar|autoriserer"
            r"|beordrar|befaler|valtuutan)",
            r"(?:you|dig|deg|sinut)",
        ),
        _phrase(
            r"(?:supersede\w*|åsidosätt\w*|tilsidesæt\w*|overstyr\w*|ohittaa|kumoaa)",
            r"(?:your|my|the|din|dit|denne|deres)?",
            r"(?:system\w*)?",
            r"(?:prompt\w*|instruction\w*|instruks\w*|instruktion\w*|ohje\w*)",
        ),
    )
)

# "Til AI-assistenten:", "Huomio tekoälylle:", "Note to the assistant:".
_ADDRESS = (
    r"(?:(?:note|attention|obs|nb|meddelande|melding|besked|viesti|huomio)"
    r"(?:" + _GAP + r"(?:to|til|till|for|för))?"
    r"|to|til|till|för|for)"
)
_AI_ASIDE = "|".join(
    (
        _phrase(
            _ADDRESS,
            r"(?:the|den|det|de)?",
            r"(?:a\.?i\.?|ki)?",
            r"(?:assistent\w*|assistant\w*|tekoäly\w*|kielimalli\w*|språkmodell\w*"
            r"|sprogmodel\w*|kunstig" + _GAP + r"intelligens|artificiell" + _GAP
            + r"intelligens|language" + _GAP + r"model|llm|chatbot|agent\w*)",
            r"[:,]",
        )
        + _END_OF_WORD,
        _phrase(_ADDRESS, r"(?:the|den|det)?", r"a\.?i\.?", r"[:,]") + _END_OF_WORD,
    )
)

# A tool call pasted into the page, as JSON or as markup.
_TOOL_CALL = "|".join(
    (
        r"(?<![^\W\d_])[\"'`]?"
        r"(?:tool_name|toolname|tool_call|toolcall|tool_use|tooluse|tool"
        r"|function_call|functioncall|function|action|instruction|command)"
        r"[\"'`]?\s{0,3}:\s{0,3}[\"'{\[]",
        r"</?(?:tool_use|tool_call|function_calls?|invoke)\b",
    )
)

# Text a reader never sees: a comment, a hidden element, a visually-hidden class.
_HIDDEN_MARKUP = "|".join(
    (
        r"<!--",
        r"display\s{0,3}:\s{0,3}none",
        r"visibility\s{0,3}:\s{0,3}hidden",
        r"opacity\s{0,3}:\s{0,3}0(?![.,][1-9])",
        r"font-size\s{0,3}:\s{0,3}0(?![.,][1-9])",
        r"text-indent\s{0,3}:\s{0,3}-",
        r"aria-hidden\s{0,3}=\s{0,3}[\"']?true",
        r"<[a-z][a-z0-9]{0,15}[^<>]{0,300}\shidden(?=[\s/>=])",
        r"class\s{0,3}=\s{0,3}[\"'][^\"']{0,120}"
        r"(?:sr-only|visually-hidden|visuallyhidden|screen-reader|screenreader)",
    )
)

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("instruction phrase", re.compile(_INSTRUCTION_PHRASE)),
    ("role prefix", re.compile(_ROLE_PREFIX, re.MULTILINE)),
    ("claim of authority", re.compile(_AUTHORITY)),
    ("aside to an AI", re.compile(_AI_ASIDE)),
    ("tool-call payload", re.compile(_TOOL_CALL)),
    ("hidden markup", re.compile(_HIDDEN_MARKUP)),
)


def _normalise(text: str) -> str:
    """A copy to read the rules against. The caller's text is untouched."""
    folded = unicodedata.normalize("NFKC", _INVISIBLE.sub("", text)).casefold()
    folded = _HORIZONTAL_SPACE.sub(" ", folded)
    return _SPACED_LETTERS.sub(lambda m: m.group(1).replace(" ", ""), folded)


def matched_rules(text: str) -> list[str]:
    """Which of the screen's rules the text trips, for a person reading a hit and for tests."""
    normalised = _normalise(text)
    return [name for name, pattern in _RULES if pattern.search(normalised)]


def screen(text: str) -> list[str]:
    """The risk-flag keys the text earns. Fetched content only; the text itself is stored as is."""
    return [EMBEDDED_INSTRUCTIONS] if matched_rules(text) else []


def screen_all(texts: Iterable[str]) -> list[str]:
    """The risk-flag keys any of `texts` earns, sorted: the screen over every text a caller
    copied from what it fetched, for a record that keeps one set of flags."""
    return sorted({flag for text in texts for flag in screen(text)})
