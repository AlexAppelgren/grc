"""The content screen (AGT-07, playbook 11.2): fetched text is data, never instructions.

`screen(text)` returns the risk-flag keys a fetched body earns (`embedded_instructions`).
Pure and deterministic: no model, network or state, and the text is never altered. A hit is
recorded in `change_document.risk_flags`; the passage is never followed.

It reads a normalised copy, so casing, spacing, invisible characters and compatibility forms
cannot hide a phrase, and looks for six shapes: an instruction phrase, a role prefix, a claim
of authority, an aside to an AI, a tool-call payload, and HTML comments or hidden elements,
in every content language. Every pattern is a bounded alternation with no nested
quantifier, so a hostile page cannot make it backtrack (`tests_screen.py`).
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
_START_OF_WORD = r"(?<![^\W\d_])"
# The ending of an inflected word that more of the phrase follows (D-145). Bounded: an
# open-ended one is read again, to the end of a long run of letters, from every stem in it.
_ENDING = r"\w{0,6}"
# Where a command in German, Dutch, Estonian, Latvian or Lithuanian starts (D-145). At the
# start of a word, because Latvian and Lithuanian negate with a prefix ("nepamirškite" asks
# the reader to remember); and not after Estonian "ei" or "ega", which negate with the very
# form that commands ("ei kiida heaks" approves nothing).
_COMMAND_START = _START_OF_WORD + r"(?<!\bei\s)(?<!\bega\s)"


def _phrase(*parts: str) -> str:
    """One phrase: the parts in order, whatever spacing, punctuation or markup separates them."""
    return _GAP.join(parts)


# The same commands in German, Dutch, Estonian, Latvian and Lithuanian (D-145), in the order
# of the phrases below. Only the forms that command: "das Institut missachtet die bisherigen
# Vorgaben" reports, and "missachte die ..." orders. They share one start, read once a word.
_COMMANDS = "|".join(
    (
        # To ignore, disregard or forget; then what is previous, the reader's own or the
        # system's; then the instructions.
        _phrase(
            r"(?:ignoriere?|missachte|vergiss|vergesst|übergehe?"
            r"|(?:ignorieren|missachten|vergessen|übergehen)" + _GAP + r"sie|negeer|vergeet"
            r"|eira(?:ke)?|ignoreeri(?:ge)?|unusta(?:ge)?|ignorē(?:jiet)?"
            r"|neņem(?:iet)?" + _GAP + r"vērā|aizmirsti(?:et)?|ignoruok(?:ite)?"
            r"|nepaisyk(?:ite)?|pamiršk(?:ite)?)",
            r"(?:alle|sämtliche|kõiki?|visas|visus|visų)?",
            r"(?:die|den|das|diese[nrs]?|deine[nrs]?|ihre[nrs]?|de|het|deze|je|jouw|uw|need"
            r"|neid|oma|sinu|teie|šīs|šos|savas|savus|tavas|tavus|jūsu|šias|šiuos|savo|tavo"
            r"|jūsų)?",
            r"(?:vorherig|vorig|bisherig|früher|obig|vorangegangen|vorstehend|ursprünglich"
            r"|voorgaand|eerder|bovenstaand|oorspronkelijk|eelnev|eelmi|varasema|ülaltoodud"
            r"|senis|esialg|iepriekšēj|agrāk|sākotnēj|ankstesn|pirmesn|pradin|dein|je|jouw|uw"
            r"|oma|sinu|teie|sav|tav|jūsu|savo|tavo|jūsų|system|systeem|süsteemi|sistēmas"
            r"|sistemos|sistemin)" + _ENDING,
            r"(?:anweisung|instruktion|vorgabe|regel|richtlinie|prompt|vokabular|instructie"
            r"|aanwijzing|richtlijn|vocabulaire|woordenlijst|juhis|juhend|reegl|reegel|viip"
            r"|viiba|sõnavara|instrukcij|norādījum|noteikum|uzvedn|vārdnīc|nurodym|taisykl"
            r"|raginim|žodyn)\w*",
        ),
        _phrase(
            r"(?:klassifiziere|kategorisiere|(?:klassifizieren|kategorisieren)" + _GAP + r"sie"
            r"|classificeer|categoriseer|klassifitseeri(?:ge)?|liigita(?:ge)?|klasificējiet"
            r"|klasifikuok(?:ite)?)",
            r"(?:dies|das|dit|deze|see|seda|selle|šo|šī|tai|šį|šią|šiuos|šias)",
        ),
        # Latvian commands one reader with the form that also reports ("banka klasificē šos
        # aktīvus kā ..."), so the singular counts only as "classify this as".
        _phrase(r"klasificē", r"šo", r"kā"),
        # Estonian approves with "heaks", before or after what is approved.
        _phrase(
            r"(?:genehmige|billige|genehmigen" + _GAP + r"sie|keur|accordeer|kiida|kiitke"
            r"|apstiprini(?:et)?|patvirtink(?:ite)?)",
            r"(?:heaks)?",
            r"(?:alle|jede|sämtliche|elk|ieder|kõik|iga|vis[au]s|katr|kiekvien)",
        ),
        # Dutch "sla ... op" saves, so Dutch names the manual or the human check and no bare
        # noun; Estonian skips with "vahele", before or after what is skipped.
        _phrase(
            r"(?:überspringe?|überspringen" + _GAP + r"sie|sla|jäta|jätke|izlaid(?:iet)?"
            r"|praleisk(?:ite)?)",
            r"(?:die|den|das|de|het|vahele)?",
            r"(?:manuell|menschlich|händisch|prüfung|überprüfung|handmatig|menselijk|inim"
            r"|käsitsi|ülevaatus|läbivaatus|manuāl|cilvēk|pārbaud|pārskatīšan|rankin|žmog"
            r"|peržiūr|patikr)\w*",
        ),
    )
)

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
        # The confidence of the other home-market languages (D-145).
        _phrase(
            r"(?:konfidenz|betrouwbaarheid|usaldusväärsus|ticamīb|patikimum|pasitikėjim)"
            + _ENDING,
            r"(?:auf|op|uz|į|=)?",
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
        _COMMAND_START + r"(?:" + _COMMANDS + r")",
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

# Where a pasted turn may start: after a line start, a fence, a bracket or a sentence end.
# The run of markers is never given back (`+`): what follows starts with a letter, which the
# run cannot hold, so a shorter run could not match either, and a page of line starts is
# read once instead of nine times (D-145 added the second rule that starts here).
_TURN_START = r"(?:^|[`>\[\](){}\"'|*#~]|[.!?…]\s)" r"[\s>\-*#`|]{0,8}+"
# "SYSTEM:", "assistant:", "<!-- agent:": a turn label pasted into the page, and never
# inside an abbreviation. The last line is the other home-market languages (D-145).
_ROLE_PREFIX = (
    _TURN_START + r"(?:system|assistenten|assistentti|assistent|assistant|developer|agent|ai"
    r"|instruktioner|instruktion|instructions|instruction|ohjeet|ohje"
    r"|anweisungen|anweisung|instructies|instructie|juhised|juhis"
    r"|instrukcijas|instrukcija|instrukcijos|asistents|asistentas)"
    r"\s{0,3}:" + _END_OF_WORD
)

# The same claims in German, Dutch, Estonian, Latvian and Lithuanian (D-145), each from the
# start of a word: "übersetzt" holds "ersetzt", and "neleidžiu tau" refuses.
_CLAIMS = "|".join(
    (
        # "Ich ermächtige dich", "Hierbij machtig ik je". German and Dutch need the "I" or
        # the "hereby": the bare verb also reports what somebody else is said to do.
        _phrase(
            r"(?:ich|ik|hiermit|hierbij)",
            r"(?:autorisiere|ermächtige|bevollmächtige|berechtige|beauftrage|instruiere"
            r"|befehle|erlaube|gestatte|machtig|autoriseer|beveel|gelast|instrueer|draag)",
            r"(?:ich|ik)?",
            r"(?:dich|dir|euch|sie|ihnen|je|jou|jullie|u)",
        )
        + _END_OF_WORD,
        # Estonian, Latvian and Lithuanian carry the "I" in the verb's ending, and Latvian
        # and Lithuanian often say the "you" first: "volitan sind", "es tevi pilnvaroju".
        _phrase(
            r"(?:volitan|käsin|juhendan|pilnvaroju|pavēlu|įgalioju|įsakau|nurodau|leidžiu)",
            r"(?:käesolevaga|ar" + _GAP + r"šo|šiuo)?",
            r"(?:sind|sul|sulle|teid|teil|teile|tevi|tev|jūs|jums|tave|tau|jus)",
        )
        + _END_OF_WORD,
        _phrase(
            r"(?:tevi|tev|jūs|jums|tave|tau|jus)",
            r"(?:pilnvaroju|pavēlu|įgalioju|įsakau|nurodau|leidžiu)",
        )
        + _END_OF_WORD,
        # "... ersetzt deinen Systemprompt". What is replaced must be the reader's own or
        # the system's: "das Rundschreiben ersetzt die bisherigen Anweisungen" is a
        # regulator's ordinary sentence.
        _phrase(
            r"(?:ersetzt|überschreibt|übersteuert|vervangt|overschrijft|tühistab|asendab"
            r"|aizstāj|aizvieto|atceļ|pakeičia|panaikina)",
            r"(?:den|die|das|dein\w{0,2}|ihr\w{0,2}|de|het|je|jouw|uw|sinu|teie|tav\w{0,2}"
            r"|jūsu|tavo|jūsų)?",
            r"(?:dein\w{0,2}|je|jouw|uw|sinu|teie|tav\w{0,2}|jūsu|tavo|jūsų|system|systeem"
            r"|süsteemi|sistēmas|sistemos|sistemin\w{0,2})",
            r"(?:prompt|anweisung|instruktion|instructie|viip|viiba|juhis|juhend|uzvedn"
            r"|instrukcij|norādījum|raginim|nurodym)\w*",
        ),
    )
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
        _START_OF_WORD + r"(?:" + _CLAIMS + r")",
    )
)

# "Til AI-assistenten:", "Huomio tekoälylle:", "Note to the assistant:".
_ADDRESS = (
    r"(?:(?:note|attention|obs|nb|meddelande|melding|besked|viesti|huomio)"
    r"(?:" + _GAP + r"(?:to|til|till|for|för))?"
    r"|to|til|till|för|for)"
)
_AI_NOUN = (
    r"(?:assistent\w*|assistant\w*|tekoäly\w*|kielimalli\w*|språkmodell\w*"
    r"|sprogmodel\w*|kunstig" + _GAP + r"intelligens|artificiell" + _GAP
    + r"intelligens|language" + _GAP + r"model|llm|chatbot|agent\w*)"
)

# The same asides in German, Dutch, Estonian, Latvian and Lithuanian (D-145), kept apart so
# that no word of theirs widens a phrase above. "Hinweis an die KI:", "Opmerking voor de AI:",
# "Märkus tehisintellektile:": German and Dutch add a preposition and an article; Estonian,
# Latvian and Lithuanian say "to" with the noun's case ending.
_NOTE = (
    r"(?:(?:hinweis|anmerkung|nachricht)"
    r"(?:" + _GAP + r"(?:an|für)(?:" + _GAP + r"(?:die|den|das))?)?"
    r"|(?:opmerking|attentie)(?:" + _GAP + r"(?:aan|voor)(?:" + _GAP + r"(?:de|het))?)?"
    r"|märkus|sõnum|piezīme|ziņa|pastaba|žinutė)"
)
# German and Dutch "to", with its article because English starts a sentence with "An agent,
# ..." too, and the words that also mean the attention a supervisor pays. They address an AI
# only where a turn may start: "Anforderungen an die KI, die ..." and "pöörab tähelepanu
# tehisintellektile, ..." are a regulator's ordinary sentences.
_TURN_NOTE = (
    r"(?:an" + _GAP + r"(?:die|den|das)|aan" + _GAP + r"(?:de|het)"
    r"|achtung|tähelepanu|uzmanību|dėmesio)"
)
# The AI such a note names: by its noun, after "AI" or what the language writes for it (KI,
# TI, MI, DI), or as "AI" or "KI" alone; then the colon or comma.
_NOTED_AI = (
    r"(?:"
    + _phrase(
        r"(?:a\.?i\.?|[kmdt]i)?",
        r"(?:" + _AI_NOUN + r"|(?:assistend|asistent|sprachmodell|taalmodel|keelemudel"
        r"|tehisintellekt|tehisaru|künstliche" + _GAP + r"intelligenz"
        r"|kunstmatige" + _GAP + r"intelligentie|(?:mākslīg|dirbtin)" + _ENDING + _GAP
        + r"intelekt|(?:valodas|kalbos)" + _GAP + r"model)" + _ENDING + r")",
        r"[:,]",
    )
    + r"|"
    + _phrase(r"(?:a\.?i\.?|ki)", r"[:,]")
    + r")"
)
# Where a turn may start the case ending alone addresses: "MI asistentam:",
# "AI-assistendile:". Only before a colon: "mākslīgajam intelektam, ko izmanto ...,
# jāatbilst" is prose.
_CASE_NOTE = r"(?:(?:a\.?i\.?|[mdt]i)" + _GAP + r")?" + _phrase(
    r"(?:assistendile|tehisintellektile|tehisarule|keelemudelile|asistentam|asistentui"
    r"|mākslīgajam" + _GAP + r"intelektam|valodas" + _GAP + r"modelim"
    r"|dirbtiniam" + _GAP + r"intelektui|kalbos" + _GAP + r"modeliui)",
    r":",
)

_AI_ASIDE = "|".join(
    (
        _phrase(_ADDRESS, r"(?:the|den|det|de)?", r"(?:a\.?i\.?|ki)?", _AI_NOUN, r"[:,]")
        + _END_OF_WORD,
        _phrase(_ADDRESS, r"(?:the|den|det)?", r"a\.?i\.?", r"[:,]") + _END_OF_WORD,
        _phrase(_NOTE, _NOTED_AI) + _END_OF_WORD,
        _TURN_START + r"(?:" + _phrase(_TURN_NOTE, _NOTED_AI) + r"|" + _CASE_NOTE + r")"
        + _END_OF_WORD,
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
    ("aside to an AI", re.compile(_AI_ASIDE, re.MULTILINE)),
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
