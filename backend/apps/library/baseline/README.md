# The library baseline

The shared library's starting inventory: the instruments in force within the sector scope
on the day they were researched, for the EU, Sweden, Denmark, Norway and Finland, and the
core duties of each in our own words. It is not loaded by a seed. Each entry is a proposal
that the beat (every `LIBRARY_BASELINE_FILING_MINUTES`) or `manage.py file_library_baseline`
files through the proposal door as the platform agent `library-baseline`, and a second, independent principal approves it in the console
queue like any other (ADR 0065, D-118, `docs/plans/briefs/LIBRARY_BASELINE.md`). From then
on the watch agents keep it current: every run re-checks the records of the sources it
checks and proposes a correction where one has drifted (WAT-01, D-50).

One file per tranche, named by its `tranche`, and `sources.json`, the pages the watch checks
for these records, which the same filing registers. Beside them, by the tranche's name:
`summaries/`, what each instrument is in plain words (INV-09), `provisions/`, the law's
own words (INV-02, below), and `corrections/`, corrections of duties the library already
holds (D-144, below). `check_baseline.py` checks every file's shape
and keys without a database; `apps/proposals/tests_baseline.py` files and approves the whole
baseline through the real proposal code, so an entry the door would refuse fails the
backend suite, and `apps/library/tests_baseline_check.py` runs the checker over the whole
baseline there too.

```
python backend/apps/library/baseline/check_baseline.py [file.json ...]
```

Run it without arguments to check everything: the sources, the summaries and the provisions
are checked with the whole baseline, never with a single tranche file.

## Shape

```json
{
  "tranche": "eu-market-abuse",
  "researchedOn": "2026-09-30",
  "instruments": [
    {
      "title": "Add the Market Abuse Regulation, Regulation (EU) No 596/2014",
      "source": "https://eur-lex.europa.eu/eli/reg/2014/596/oj",
      "sourceLabel": "EUR-Lex, Regulation (EU) No 596/2014 as published in the Official Journal",
      "fieldSources": {"inForceFrom": "https://eur-lex.europa.eu/eli/reg/2014/596/oj"},
      "payload": { "...": "a new_instrument payload (apps/proposals/schemas.py ProposalInstrumentPayload)" },
      "obligations": [
        {
          "title": "...",
          "source": "https://...",
          "sourceLabel": "...",
          "payload": { "...": "a new_obligation payload without `instrument`, which the filing sets" }
        }
      ]
    }
  ]
}
```

- `title` is the proposal's one line in the queue. `source` is the https page the record is
  read from: it becomes the record's own source link (INV-06) and the source of every fact
  in the payload that `fieldSources` does not name with a page of its own.
- Payload fields are camelCase, exactly as `POST /proposals` takes them.

## Rules

- **Only what is in force or adopted on the research day.** A proposal for law that is not
  adopted is not here; the watch feed follows it. An instrument that stops binding later
  carries `inForceTo`, the first day it no longer binds.
- **Dates.** `inForceFrom` is the day the instrument entered into force. A duty that applies
  later than that carries the day it applies as the obligation's `effectiveFrom`, so "as of"
  reads show it as coming, not in force.
- **Where a duty sits.** A regulation binds a firm directly, so its duties sit under the EU
  instrument. A directive binds the state, so the directive is an instrument without duties
  and its duties sit under each country's act that implements it, whose `implementsNote`
  names the directive.
- **Levels.** `eu_regulation` (delegated and implementing regulations too), `eu_directive`,
  `eu_guidance` (the supervisory authorities' guidelines), `act` (a statute of the national
  legislature), `government_regulation` (binding rules a government or a ministry issues
  under an act: a förordning, a ministerial bekendtgørelse, a ministry forskrift, an asetus)
  and `authority_regulation` (binding rules a supervisor or another authority issues under
  delegation).
- **Sanctions** sit under `regime:aml`: EU restrictive measures and national sanctions law.
- **Keys** are for ever. Instruments: `celex-<celex lowercased>` for EU acts,
  `sfs-<year>-<number>`, `fffs-<year>-<number>`, `dk-lov-<year>-<number>`,
  `dk-bek-<year>-<number>`, `no-lov-<yyyy-mm-dd>-<number>`, `no-for-<yyyy-mm-dd>-<number>`,
  `fi-sd-<year>-<number>`, `fi-fiva-<topic>` for a FIN-FSA regulation, and
  `<authority>-gl-<year>-<number>` for a guideline. Obligations: `obl-<jurisdiction>-<instrument short>-<topic>`.
- **Our own words.** A summary says in one to three plain sentences what the firm must do,
  for whom and when, and never copies the law beyond a defined term. `refLabel` cites the
  article or section the duty comes from, as the source numbers it.
- **Scope terms narrow.** An obligation carries a restricting term only when the duty is
  limited to it (a legal entity, a service, a client category); a dimension left empty means
  the duty reaches every firm under the instrument's regime (FP-01). Never a jurisdiction,
  regime or standard term.
- **No standards.** A standard's records wait for the legal answer on standard titles
  (D-47, `docs/TODO_FOR_alex.md`).
- Every fact in the files is logged in `docs/plans/Verification_Log.md` under "Library
  baseline", with the page it was read from.

## The law's own words

An obligation's title and summary are our own words, written in English, and their original
is the language we wrote them in. The words of the law are another record. They live in the
library's provision tree (INV-02) and arrive here as `provisions/<tranche>.json`, one file
per tranche, each entry filed as a `new_provision` proposal once the library holds its
instrument and every duty it names. A person approves each one; an agent never does (D-79).
Approval adds the provision with its first text and ties it to the duties that cite it.

```json
{
  "tranche": "se-forordningar",
  "researchedOn": "2026-11-13",
  "provisions": [
    {
      "key": "sfs-2015-921/005",
      "instrument": "sfs-2015-921",
      "provisionKind": "section",
      "refLabel": "5 §",
      "path": "005",
      "heading": null,
      "texts": {
        "sv": "the section as the source publishes it, whole and unchanged",
        "en": "its translation into English"
      },
      "originalLanguage": "sv",
      "isMachine": true,
      "obligations": ["obl-se-crs-forordning-self-certification-form"],
      "source": "https://www.riksdagen.se/sv/dokument-och-lagar/dokument/svensk-forfattningssamling/forordning-2015921-om-identifiering-av_sfs-2015-921/",
      "sourceLabel": "Riksdagen, Svensk författningssamling, SFS 2015:921, 5 §, text as amended up to SFS 2025:1394. Källa: Sveriges riksdag",
      "readOn": "2026-11-13"
    }
  ],
  "withoutProvision": [
    { "obligation": "obl-se-...", "reason": "why no provision here cites this duty" }
  ]
}
```

- `key`, `instrument`, `provisionKind`, `refLabel`, `heading`, `texts`, `originalLanguage`,
  `isMachine`, `officialLanguages` and `obligations` are the door's own fields
  (`ProposalProvisionPayload`), copied into the proposal as they stand; a `heading` of null
  is left out. `path`, `source`, `sourceLabel` and `readOn` are the file's.
- `key` is for ever: the instrument's key, a slash and `path`, lower case, unique across the
  baseline, at most 158 characters (what the filing's retry key leaves of the door's 200).
  `instrument` is an instrument of the same tranche.
- `path` is the provision's place in its instrument: lowercase words and numbers joined by
  hyphens, **every number written with three digits**: `005` for 5 §, `009-006` for 9 kap.
  6 §, `002-001` for § 2-1, `016` for Art. 16, `005a` for 5 a §. The filing gives a
  provision no sort order of its own, and the library then lists an instrument's provisions
  by key, so the padding is what makes them read in the law's order.
- `provisionKind` is a seeded provision kind, none of them one jurisdiction's own: `section`
  for a paragraph (§) of national law, `article` for an article of an EU act, `guideline`
  for a numbered guideline, and `part`, `chapter`, `paragraph` and `annex`. `refLabel` cites
  the provision as the source numbers it (`9 kap. 6 §`, `§ 2-1`, `Art. 16`).
- `obligations` are the baseline keys of the obligations under the same instrument that cite
  the provision, at least one and at most 50. A duty that cites several sections is named by
  each of them.
- `source` is the https page the text was read from, addressed as closely as the source
  allows (its anchor for the section where it has one), and is the source of every fact in
  the entry. `sourceLabel` names the publisher, the reference, the section and what the text
  is amended up to, and carries the credit the source asks for (below). `readOn` is the day
  the text was read, which the proposal's title repeats.
- `withoutProvision` names every obligation of the tranche that no provision here cites,
  with the reason. A tranche that has a provisions file leaves no duty without its text
  silently; a tranche with no file yet is not checked.

Rules. `check_baseline.py` holds a file to everything below that a file can show: the
language of the original, the translations beside it, their marks and the limits.
How each text was read, and every check it went through, is recorded in
`docs/reviews/LAW_TEXT_REVIEW_2026-11-13.md`.

- **Produced by script, never retyped.** The text is what the official source publishes,
  fetched and cut to its section by script. Nobody types it, tidies it or shortens it; a
  correction is a new fetch. A text is at most 50,000 characters per language, the door's own
  limit.
- **The original is the authority's language.** Swedish for Sweden, Danish for Denmark,
  Norwegian (`nb`) for Norway, Finnish for Finland, English for the EU. The door refuses
  anything else, here and from every other proposer: recording English as the original of
  Swedish law is the mistake this format exists to end.
- **The texts beside the original.** English always. Swedish as well when the original is
  Danish, Norwegian or Finnish. An EU text is English alone.
- **A translation is a machine translation and is marked so.** `isMachine` is true whenever
  an entry holds a translation, and the library labels each one a machine translation,
  whoever approves it. Finland is the one exception: its acts are enacted and published in
  Finnish and in Swedish, so a Finnish provision carries the authority's own Swedish text
  and names it in `officialLanguages: ["sv"]`, which is stored neither as the original nor
  as a machine translation. Its English is a machine translation like any other. No other
  jurisdiction has an official second language here, and `officialLanguages` is left out.
- **A source's own unofficial translation does not stand in for one.** The English texts
  that Finlex, Lovdata, both Finanstilsynet and Finansinspektionen publish are not official
  and may trail the law, and Lovdata's are outside the texts it frees for reuse.

What each source asks of someone who republishes its text, read on 2026-11-13 at the pages
named:

| Source | What it allows | What the entry does |
|---|---|---|
| Sweden, `riksdagen.se` (SFS) | Statutes carry no copyright (upphovsrättslagen 9 §). The Riksdag's open data is free to use and pass on "så länge du anger källa"; a service must not look like the Riksdag's own (`riksdagen.se/sv/dokument-och-lagar/riksdagens-oppna-data/anvandarstod/anvandningsvillkor/`) | `sourceLabel` ends "Källa: Sveriges riksdag". The consolidated text is for information; the gazette as published binds |
| Sweden, `fi.se` (FFFS) | "Textmaterialet på webbplatsen får användas fritt, bara källan anges" (`fi.se/sv/om-fi/om-webbplatsen/`). Published as PDF only | `sourceLabel` names Finansinspektionen. Only the printed edition applies in law |
| Denmark, `retsinformation.dk` | Laws and orders carry no copyright (ophavsretsloven § 9). Civilstyrelsen grants free, non-exclusive, unlimited use, commercial too, with no credit asked and no endorsement implied; a fetch must not burden the interface (`retsinformation.dk/api`) | `sourceLabel` names Retsinformation all the same. Only Danish applies |
| Norway, `lovdata.no` | Laws and regulations carry no copyright (åndsverkloven § 14). Lovdata frees its current acts and central regulations under NLOD 2.0 when Lovdata is named as the source: credit, a link, and changes marked. No mass download from the site: its open nightly packages instead (`lovdata.no/info/brukeravtale`, `api.lovdata.no`) | `sourceLabel` names Lovdata and `source` links the section; the text is unchanged. Lovdata calls its consolidated text its own work, and whether that holds against § 14 is a lawyer's question still open |
| Finland, `finlex.fi` | No copyright in laws, decrees or official translations (tekijänoikeuslaki 9 §). Finlex open data is CC BY 4.0 (`finlex.fi/en/faq`); every request carries a User-Agent | `sourceLabel` names Finlex. FIN-FSA's regulations bind in Finnish and Swedish and are published as PDF |
| EU, `eur-lex.europa.eu` | Legal documents may be reused, commercially or not; a consolidated text is CC BY 4.0, the source acknowledged and changes indicated. Only the Official Journal is authentic (`eur-lex.europa.eu/content/legal-notice/legal-notice.html`) | `sourceLabel` names EUR-Lex and the Official Journal reference, and says so when the text is a consolidated one |
| EBA, ESMA, EIOPA | Reproduction with the source acknowledged (EBA); "Source: EIOPA - European Insurance and Occupational Pensions Authority."; a republished translation of an ESMA document says "This document constitutes a translation of a document downloaded from ESMA's website" | `sourceLabel` carries the authority's own wording |

## Corrections

A duty already in the library is never edited here: its corrections arrive as
`corrections/<tranche>.json`, one file per tranche, each entry filed as a
`new_obligation_version` proposal of the duty it names (D-144). They come from reading every
duty beside the law it cites (`docs/reviews/law-text-2026-11-13/duty-reading.json`). The filer
files an entry once the library holds the duty and every provision the entry names (so a
provision it cites for the first time is approved first), never while a version of that duty
waits in the queue, and never again in the same words once decided: the retry key is
`baseline:correction:<key>:<content hash>`. A version is agent-confirmable, so the demo's
confirmer applies the corrections too.

```json
{
  "tranche": "dk-bekendtgorelser",
  "readOn": "2026-11-13",
  "reading": "docs/reviews/law-text-2026-11-13/duty-reading.json",
  "obligations": [
    {
      "key": "obl-dk-afvplan-financial-contracts-register",
      "title": "Correct obl-dk-afvplan-financial-contracts-register: every firm keeps the register",
      "source": "https://www.retsinformation.dk/eli/lta/2021/2018",
      "sourceLabel": "Retsinformation, BEK nr 2018 af 26/10/2021 (...), § 12",
      "why": "What the cited law says that the old text did not, for the reviewer.",
      "payload": {
        "summaries": {"en": "..."},
        "originalLanguage": "en",
        "titles": {"en": "..."},
        "refLabel": "§ 12",
        "provisions": ["dk-bek-2021-2018/012"]
      }
    }
  ]
}
```

- `key` is a duty of the same tranche, corrected by at most one entry in the whole baseline.
- `title` and `why` become the proposal's one line, joined by a full stop, at most 500
  characters together: a proposal has no field of its own for the proposer's reasoning, and
  the reviewer has to read why. `source`, `sourceLabel` and `fieldSources` read as on a duty.
- `payload` is a `new_obligation_version` payload (`ProposalObligationVersionPayload`):
  `summaries` and `originalLanguage` always, the summary one to three sentences; `titles`,
  `refLabel` and `provisions` only when they change, and the checker refuses one equal to
  what the duty already has. Each one given replaces that part of the duty whole. Never
  `isMachine`, `effectiveFrom` or `terms` (the scope is not corrected here): a correction is
  in force from the duty's start, so the filer gives it the duty's own `effectiveFrom`, when
  the duty has one, and the correction is the later version of that day.
- `provisions` are keys of the provisions files under the duty's own instrument, at most 50:
  the door refuses a provision of another instrument. Where a summary element comes from
  another instrument, the summary says so in words rather than citing it.
