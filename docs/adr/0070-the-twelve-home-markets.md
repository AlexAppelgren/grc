# ADR 0070 — The platform covers the European Union and twelve home markets

**Date:** 2026-11-14 · **Status:** accepted (Alex, 2026-11-14: "We actullay need to cover all of SEBs home markets in bleqq, not just the Nordic's and EU.. this needs to be throughout everything in bleqq"; D-145, PRD 0.12 section 1, I18N-01, FP-04, INV-05; answers D-33; amends ADR 0026's last sentence, ADR 0023's language list and D-142's translation rule)

## Context

PRD section 1 and I18N-01 limited the platform to the Nordics and the EU: five jurisdictions
(EU, SE, DK, NO, FI) and five content languages. ADR 0026 listed "markets beyond EU, SE, DK,
NO and FI" as deliberately not done, and D-33 kept the question open: which other markets,
and when. A market is platform scope, never a tenant setting: it needs a jurisdiction row,
its authorities, its sources and a language before a sweep can find anything (D-33, D-94).

SEB names twelve home markets (`sebgroup.com/about-us/our-locations` and its newest Fact
Book, for the third quarter of 2026 and dated 22 October 2026, both read 2026-11-14,
`docs/plans/Verification_Log.md`): "the Nordic and Baltic countries, Germany, the United
Kingdom, Switzerland, Austria and the Netherlands (the last three countries with a
selective approach)". A bank with that footprint could operate in or watch four of its twelve
markets.

## Decision

1. **Thirteen jurisdictions a bank can name.** The reference seed files eight more countries
   beside the five: Estonia `ee`, Latvia `lv`, Lithuania `lt`, Germany `de`, the United
   Kingdom `gb`, the Netherlands `nl`, Austria `at` and Switzerland `ch`. Keys are the
   lowercased ISO 3166-1 alpha-2 codes, as the first four were, so a company's country code
   from GLEIF still finds its jurisdiction. They are seeded, not proposed (D-94): a
   jurisdiction's kind, parent and legal language are the seed's. In a new database they
   follow Finland and International comes last. A database seeded before this keeps
   International in its old place, between Estonia and Latvia, because a row's place is
   written once (D-94): one jurisdiction proposal in the console moves it.
2. **Whose rules reach them (D-28).** `ee`, `lv`, `lt`, `de`, `nl` and `at` are member
   states and have the EU as parent. `gb` and `ch` have none: EU law binds neither. A bank
   operating only in the United Kingdom or Switzerland is not shown EU law by the scope rule,
   and a Union rule no longer reaches every market, so its scope block lists the ten
   countries it does reach.
3. **Ten content languages.** Estonian `et`, Latvian `lv`, Lithuanian `lt`, German `de` and
   Dutch `nl` join, each the legal language of its market; German is Austria's and
   Switzerland's too, and English the United Kingdom's. Switzerland enacts federal law in
   German, French and Italian alike; the library holds the German text and no French or
   Italian one. Search reads German, Dutch and Lithuanian with PostgreSQL's own
   configurations. PostgreSQL 16 has none for Estonian or Latvian, so those are matched word
   for word (`simple`): the keyword leg finds an exact word and never an inflected form, and
   the vector leg carries the rest. The generated `tsv` column names every configuration, so
   a language is a seed row and a migration (search 0005), not a row alone as ADR 0023 said.
4. **The law's own words (amends D-142).** A provision's original is still the language its
   jurisdiction writes law in, refused otherwise at the door. Beside every national original
   stand English and Swedish, whichever of the two the original is not: a German section
   carries English and Swedish, a United Kingdom section Swedish. A European Union text stays
   English alone. Every translation is a machine translation, labelled so, and says what the
   law says as a lawyer of the target language would write it, never word for word.
5. **Authorities and watched sources** for the eight markets are filed with the same change:
   64 authorities (each market's legislature, government and finance ministry, its financial
   supervisors and central bank, its data protection, tax and financial intelligence
   authorities) and 39 sources (its official legal database and each supervisor's news page
   and register of binding rules). Each was read on the body's own site, or in an official
   directory where the site refused the read, which is the case for six of Lithuania's seven
   bodies (`docs/reviews/HOME_MARKETS_SOURCES_2026-11-14.md`).
6. **Everything that lists a market or a language follows the rows**: the markets screen,
   the country filter, the agents' scope, the content language pickers, the proposal door,
   the baseline checker, the agents' injection screen and the evaluation sets. The national
   standards bodies of the eight markets join `STANDARDS_PUBLISHER_HOSTS`, so no run reads
   them before a lawyer has cleared their terms (D-45).
7. **The starting inventory arrives market by market** through the proposal door, as ADR
   0065 files every baseline record. The plan is below.

## Consequences

- A bank can name any of the twelve markets as one it operates in or watches from the day
  this ships, and the watch sweeps their sources. Until a market's tranches below are filed
  and approved, its inventory holds only what the watch has proposed since.
- Every change is indexed once per content language (D-86), so ten rows and ten embeddings
  where there were five. The translator (D-129) writes nine languages per record where it
  wrote four: still one model call per record, with a longer answer.
- An EU obligation's scope block lists eleven jurisdiction pills, the Union and the ten
  countries its rules reach, where it listed five. Folding them is an open question
  (`docs/TODO_FOR_alex.md`).
- I18N-02 promises the interface in every content language by R3: eight catalogs beside
  English and Swedish, where it was three. Chunk 13 plans three.
- The embedding model D-09 is still to choose must cover ten languages, and the evaluation
  set asks in all ten.
- ADR 0047 is untouched: it decides where a bank's data is processed, and reading the public
  law of the United Kingdom and Switzerland processes no bank's data there.
- The supervisor's licence register is read for Sweden alone, as before (ADR 0066). GLEIF
  covers every market; the EBA register gives branches inside the EEA only, so a branch in
  the United Kingdom or Switzerland comes from GLEIF or is entered by hand.
- Six of the registered sources cannot be read as a plain page: Riigi Teataja, Fedlex and
  the FCA Handbook serve no text without a browser, and the Austrian RIS and FMA and the
  Lithuanian register refuse an automated read. Riigi Teataja, Fedlex and the RIS have an
  interface that serves the same law, which the runner does not use yet.
- Not done: French and Italian for Switzerland; Swedish beside EU texts, which EUR-Lex
  publishes officially; a sentence splitter that knows German capitalisation, so the "what
  changed" view may cut a German sentence at "1. Januar".

## Implementation plan

| Tranche | What | When |
|---|---|---|
| 1 | The platform: jurisdictions, languages, authorities, watched sources, the door's rule, search, the agents' screen and definitions, settings, filters, copy and the documents | This change, 2026-11-14 |
| 2 | Each market's statutes within the sector scope, their duties in plain words and what each instrument is, as `<market>-acts` tranches | Market by market, after tranche 1 is on `main` |
| 3 | Each market's government and ministerial regulations and its supervisors' binding rules, and its sanctions law | After tranche 2, per market |
| 4 | The law's own words for every duty of tranches 2 and 3, fetched by script, with English and Swedish beside the original | With each tranche, as D-142 did |
| 5 | The interface in `et`, `lv`, `lt`, `de` and `nl` | R3, with chunk 13's catalogs |
