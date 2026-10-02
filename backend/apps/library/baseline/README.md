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
for these records, which the same filing registers. `check_baseline.py` checks every file's shape
and keys without a database; `apps/proposals/tests_baseline.py` files and approves the whole
baseline through the real proposal code, so an entry the door would refuse fails the
backend suite.

```
python backend/apps/library/baseline/check_baseline.py [file.json ...]
```

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
