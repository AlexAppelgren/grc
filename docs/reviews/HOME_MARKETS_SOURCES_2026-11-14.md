# The eight new home markets: how their authorities and sources were read (2026-11-14)

**What this is.** The record behind the authority rows and the watched sources that D-145
and ADR 0070 add for Estonia, Latvia, Lithuania, Germany, the United Kingdom, the
Netherlands, Austria and Switzerland, and behind what the baseline README says about each
market's legal database. `home-markets-2026-11-14/authorities_sources.json` holds every body and
page with the address it was read at, what the page said, and a `verified` flag; this file
says what did not verify and what had to be chosen.

**What was seeded from it.** 64 authorities (`backend/apps/library/fixtures/prototype_data.json`)
and 39 watched sources (`backend/apps/library/baseline/sources.json`). Not everything in the
JSON was seeded. Left out: the German Bundesrat, since an act's issuer is the Bundestag; the
BfDI, which supervises federal public bodies and not private banks; the news listings that
serve no content without a browser (De Nederlandsche Bank) or were not found (the FMA); and
the extra pages of the financial intelligence units. A short name that two markets share
carries its country, as Finanstilsynet already did: `BMF (DE)`, `BMF (AT)`, `FM (LV)`,
`FM (LT)`, `FIU (DE)`. Estonia's supervisor goes by its full name, because its own
abbreviation is Sweden's "FI".

**Checked again after the first read** (all 2026-11-14):

- The United Kingdom's data protection authority. GOV.UK's organisation page reads
  "Information Commissioner's Office is now called Information Commission", and the body's
  own home page is titled "Information Commission's Office". The row is named Information
  Commission and keeps the short name ICO, which its site still uses.
- UK Parliament. Its own site refused the read; `legislation.gov.uk/understanding-legislation`
  says "Acts of the UK Parliament", which is the name the row carries.
- The Austrian FMA's address. Its site refused the read; the ECB's list of national
  supervisors links "Finanzmarktaufsicht" to `https://www.fma.gv.at/`.
- Lithuania. Every Lithuanian state site but the Seimas's refused the read, so each body
  was looked up in an official directory: Lietuvos bankas in the ECB's list of national
  supervisors, which links `lb.lt`; the State Data Protection Inspectorate with
  `https://vdai.lrv.lt/` in the EDPB's member list; the State Tax Inspectorate with
  `vmi.lt` and the Ministry of Finance with `finmin.lrv.lt` in the European Commission's
  list of national tax administrations; the Financial Crime Investigation Service under the
  Ministry of Interior in the Egmont Group's member list; the Government's resolutions in
  N-Lex's page on the Lithuanian register, which also links both legal databases. Each
  body's Lithuanian name is the title of its own site as a search engine shows it, and
  `fntt.lrv.lt` rests on that alone. A person who can open these sites should confirm the
  six names (`docs/TODO_FOR_alex.md`).
- An English edition of the supervisor's site, for the public page's language line: found
  for Finantsinspektsioon, Latvijas Banka, BaFin, the AFM, the Oesterreichische
  Nationalbank and FINMA; Lietuvos bankas could not be read.

The notes below are the first read's, market by market.

Read on 2026-11-14. Data file: `home-markets-2026-11-14/authorities_sources.json`, assembled by script and
validated: valid UTF-8 JSON, 66 authority keys, all unique, none of the 32 keys already taken, every
source's `authority` points at a key in the same market.

## How to read the `verified` flags

- `verified: true` on an authority: its name and role were read on the body's own site or in the statute text.
  Single fields that were not read are listed in `unverifiedFields` (mostly English names and abbreviations).
- `verified: false`: the body's own site could not be read, or a required fact has no fetched source.
  The values are candidates only, taken from an EU directory or a search-engine title, and say so.
- Sources: `verified` is true only when the exact URL returned 200 with the expected content.

## Things that affect all markets

- Three official databases are now JavaScript applications whose HTML has no content: Riigi Teataja (since
  1 June 2026), Fedlex and the FCA Handbook. A watch agent that reads HTML gets an empty shell with status 200.
  The JSON gives the API each one needs (Riigi Teataja REST API, Fedlex SPARQL endpoint); none was found for
  the FCA Handbook.
- Sites that refused automated fetches: lb.lt, lrv.lt, vmi.lt, e-tar.lt, e-seimas.lrs.lt, fma.gv.at,
  parliament.uk (Cloudflare challenge, 403); ris.bka.gv.at and bundesfinanzministerium.de (security check, 503).
  dnb.nl and admin.ch refused the command-line fetch but were readable with the web fetch tool.
  A watch agent will meet the same walls.
- Key collisions avoided by suffix: `bmf-de` / `bmf-at`, `bundesregierung-de` / `bundesregierung-at`,
  `bundesrat` (Swiss government) / `bundesrat-de` (German chamber), `fma-at`, `fiu-de`, `parlament-at`,
  `regering-nl`, `finansu-ministerija-lt` (Latvia's is `finansu-ministrija`).
- Code collision: Finantsinspektsioon abbreviates itself "FI", same as Sweden's. Code given as "FI (EE)".
- "Two examples each" for citations: where a second example was not fetched the entry says so instead of
  being filled in (LV government regulation, DE supervisor regulation, NL statute, CH government regulation,
  GB second statutory instrument title).

## Estonia (8 authorities, 5 sources, all verified)

- Riigi Teataja relaunched on 1 June 2026. Old patterns such as `/akt/{id}.xml` now return the HTML shell.
  Text, XML and PDF come from `https://www.riigiteataja.ee/public-api/api/v1/akt/{id}/xml|txt|pdf`. This API
  was found in the site's own JavaScript; no public documentation of it was found.
- ELI: only the English pattern was seen to answer (301 to the JavaScript page). Marked not verified.
- Finantsinspektsioon issues advisory guidelines only (FIS § 57). Binding sub-statutory rules for banks come
  from Eesti Pank ("Eesti Panga presidendi määrus") and the Minister of Finance, so the two "supervisor
  regulation" examples are Eesti Pank's.
- No Government regulation exists among the 22 implementing acts of the Credit Institutions Act; the
  Government example is an AML one.
- Finantsinspektsioon's site forbids reproduction without permission except for press and non-profit use;
  the Copyright Act exempts "juhendid" as administrative documents. Which rule governs its guidelines was not
  settled.
- The English name of the Government was read on emta.ee, not on valitsus.ee. "RAB" was seen only as a hashtag.

## Latvia (7 authorities, 5 sources, all verified)

- FKTK takeover confirmed from the Law on Latvijas Banka: in force 1 January 2023, references to the FKTK
  mean Latvijas Banka. Latvijas Banka is both supervisor and central bank (one row, `alsoRole`).
- FID has been the competent authority for sanctions since 1 April 2024 (its own page).
- VID: the CRS page was seen as a search result on vid.gov.lv but not opened; FATCA not confirmed.
- ELI: not found. No XML or API for consolidated text was found on likumi.lv, only RSS feeds.
- likumi.lv's terms of use allow free access and say nothing on republication or credit; Latvijas Banka's
  site carries only "© Latvijas Banka, 2026".
- A banking-sector Cabinet regulation with its number was not fetched (format confirmed from another one).
- "MK" and "FM" as codes come from likumi.lv usage and the domain, not from the bodies' own text.

## Lithuania (7 authorities, 1 verified; 4 sources, 0 verified)

- Only the Seimas site (lrs.lt) could be read. Every other Lithuanian state site answered 403 to both tools.
- Names for Lietuvos bankas, VDAI and VMI rest on ECB, EDPB and European Commission lists; the Government,
  Finance Ministry and FNTT names rest on search-engine titles. Treat all six rows as candidates.
- Not read at all: Lietuvos bankas's legal basis and what it supervises, VMI's CRS/FATCA role, FNTT's role
  in sanctions, the citation format, ELI, e-tar terms of use, and the URL of Lietuvos bankas's legal acts.
- Read on lrs.lt: Constitution Art. 14 (Lithuanian is the state language); the links to TAR and TAIS; a press
  release of 2 July 2025 saying TAR data and texts are open data (JSON, JSONL, CSV) at
  `https://data.gov.lt/datasets/2613/`. That portal is blocked from the build session, so the data set was not seen.
- This market needs a second pass from a network the Lithuanian sites accept, or by a person.

## Germany (9 authorities incl. 1 extra, 7 sources, all verified)

- BaFin's site was relaunched: it now spells itself "Bafin", and the old listing URLs for press releases and
  circulars return 404. The JSON has the new ones. Code left as "BaFin" with a note.
- The Finance Ministry's own site was not readable (503); its name and role come from bundesregierung.de and
  from the preamble of the Solvabilitätsverordnung.
- Bundesrat added as `extra` because statutes are passed with its participation.
- BfDI's page lists federal public bodies as its remit, not banks. Data-protection supervision of private
  banks sits with other authorities, which were not researched. Its name is given as the page writes it
  ("Der Bundesbeauftragte ..."); the article follows the office holder.
- Sanctions: the Bundesbank has a "Finanzsanktionen" page; the split with any customs-based enforcement
  office was not read. Bundesbank is entered once, as central bank, with `alsoRole`.
- ELI exists for gazette items since 2023 only. Consolidated texts have no ELI on Gesetze im Internet.
- English translations on Gesetze im Internet are copyright-restricted, unlike the German texts.

## United Kingdom (11 authorities, 9 verified; 8 sources, all returned 200)

- parliament.uk could not be read; its role is quoted from GOV.UK. Row marked not verified.
- ICO: the only long form on the pages fetched is the home page title "Information Commission's Office".
  The usual "Information Commissioner's Office" was not found there. Row marked not verified; confirm the name.
- PSR is being consolidated into the FCA (its own home page says so). It still has a site and news page.
- PRA Rulebook terms forbid commercial use without a licence from the PRA. The FCA Handbook is under the
  Open Government Licence v3.0 plus Handbook terms. These two differ and it matters for republishing.
- FCA Handbook and PRA legal-instrument lists load by script; instrument numbering was not read.
- No official sentence stating that UK legislation is in English was found.
- NCA is listed because the UK Financial Intelligence Unit sits there; it issues guidance, not rules.

## Netherlands (8 authorities, 7 verified; 5 sources, 4 verified)

- Belastingdienst's role in CRS/FATCA was not confirmed (guessed page 404, search page empty). Not verified.
- English names of Staten-Generaal, the ministry, AFM, AP and FIU-Nederland were not read on English pages.
- DNB news page delivers no items in its HTML; marked not verified as a watch target. Open Boek Toezicht read.
- No AFM rule register was found; AFM and DNB regulations are in wetten.nl (DNB's with type "zbo").
- A licence name for wetten.nl (for example CC0) was not found on the page read; the Copyright Act article on
  laws was read instead. `overheid.nl/copyright` is 404.
- ELI not found; the permanent identifier is the BWB id. Staatsblad numbers for the two regulations not read.
- No separate sanctions office was found.

## Austria (7 authorities, all verified by statute or own page; 4 sources, 1 verified)

- The FMA site was not readable. Its name, legal form and remit come from FMABG § 1 and BWG § 69 through the
  RIS open-data API. Its news listing URL was not found; the circulars URL comes from a search result.
- The RIS website was not readable, but the official API and document store were. A watch agent should use
  them. The ELI is returned by the API; the ELI URL itself answered 503.
- Sanctions: under the Sanktionengesetz 2024 (version in force 1 January 2026) the FMA grants permits for
  financial market participants. Any remaining OeNB sanctions function was not confirmed.
- Tax: no separate tax-authority row. The Finance Ministry carries `alsoRole: tax`; which office receives
  CRS reports, and FATCA, were not read.
- That the two "government" regulations are the Finance Minister's and the two "supervisor" ones the FMA's
  was not read in their preambles (only type and gazette number).
- RIS open-data licence text: not found.

## Switzerland (9 authorities, 6 sources incl. 1 extra, all verified)

- Publikationsgesetz Art. 14(1) confirmed: German, French and Italian versions are equally binding.
  Art. 15: the version in the Official Compilation on the platform is authoritative. English: "has no legal
  force" (notice on the English FINMASA text).
- Fedlex file names carry a varying numeric suffix, so they must be looked up by SPARQL, not built.
- Terms specific to Fedlex were not found; the general federal notice asks written consent for reproduction,
  while the Copyright Act exempts enactments and their official collections and translations.
  FINMA's own notice also asks written consent; whether circulars count as official enactments was not settled.
- SNB's binding rules for banks were not read. ESTV's FATCA role was not found. MROS's English name not read.
- A second Federal Council ordinance in banking was not looked up.
- The sentence that Switzerland is not an EU member came back from the fetch tool in two parts.
