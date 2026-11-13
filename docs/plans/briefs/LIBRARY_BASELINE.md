# The library baseline: the shared library's starting inventory

Source: Alex, 2026-09-30: "build up the inventory for everything relevant as of today", and
market abuse laws "also needs to be included"; then "the bleqq agent will run and look for
changes and new things". On 2026-10-01 Alex answered that bleqq files it and registers its
sources, that sanctions are in scope, that government ordinances get a level, and that
D-40's three areas are in. Decided in D-118 and ADR 0065, PRD 0.8. Built on the branch
`claude/library-baseline`.

## Why it was needed

A deployed library held reference data only. The sample library loads into demo and E2E
databases, never a deployment. The watch agents look for what is new on registered
sources, capped per run, with no source registered on a new deployment and no real runner
until D-07. So the first bank would have met an empty inventory, and search, Ask and the
footprint preview would have answered nothing.

## How it works

1. **Researched, reviewed data.** `backend/apps/library/baseline/` holds one file per
   tranche. Each entry is a `new_instrument` or `new_obligation` payload exactly as
   `POST /proposals` takes it, with the official page it was read from. Beside the tranches,
   by the tranche's name, `summaries/` holds what each instrument is in plain words
   (`new_instrument_summary`, D-124) and `provisions/` the law's own words
   (`new_provision`, below). The rules it was
   researched under are the definition's `prompt.md` and the folder's `README.md`.
2. **Checked twice before any deploy.** `check_baseline.py` checks shape and keys without a
   database. `apps/proposals/tests_baseline.py` files every entry through the real proposal
   code, approves it as a person and proves each one applies.
3. **Filed through the proposal door, by itself.** The beat (every
   `LIBRARY_BASELINE_FILING_MINUTES`, an hour by default, off under E2E) files what the
   library neither holds nor has open as proposals of the platform agent
   `library-baseline`, instruments first, each duty and summary once its instrument is
   approved, each provision once the duties it names are, and
   registers the pages in `sources.json` for the watch. An approved instrument or duty queues
   the same filing a few seconds later. `manage.py file_library_baseline`
   does the same by hand. It is safe to repeat, and a rejected entry stays rejected until
   its file changes.
4. **Approved by a second principal.** A person in the console with a passkey today, one
   proposal at a time or a page at once (the queue's "New instrument" and "New obligation"
   filters, then select and approve: one passkey, the same approve route per proposal);
   the confirming agent once it is published and its runner is live. A summary and a
   provision are always a person's to approve (D-79, D-124). Nothing approves
   itself, and the agent that filed an entry can never approve it.
5. **Kept current by the watch.** Each watch run re-checks the records of the sources it
   checks and proposes a correction where one has drifted, and registers what is new.

## What it covers

The sector scope on 2026-09-30 and 2026-10-01, for the EU, Sweden, Denmark, Norway and
Finland: what is in force, and what is adopted and applies later (with the later date on the
duty). Government ordinances carry the level `government_regulation`, and financial
sanctions the regime `aml`. An EU
regulation's duties sit under it. A directive is an instrument without duties, and its
duties sit under each country's implementing act.

| Tranche | File | Instruments | Duties |
|---|---|---|---|
| EU market abuse | `eu-market-abuse` | 21 | 72 |
| EU investment services | `eu-investment-services` | 21 | 89 |
| EU market infrastructure | `eu-markets-infrastructure` | 23 | 62 |
| EU securitisation | `eu-securitisation` | 10 | 23 |
| EU banking and credit | `eu-banking-credit` | 28 | 45 |
| EU payments | `eu-payments` | 15 | 45 |
| EU insurance, pensions and funds | `eu-insurance-funds` | 27 | 63 |
| EU AML and tax | `eu-aml-tax` | 19 | 50 |
| EU data protection, ICT risk and AI | `eu-data-ict-ai` | 17 | 63 |
| EU sanctions | `eu-sanctions` | 49 | 121 |
| Sweden, acts | `se-acts` | 39 | 218 |
| Sweden, förordningar | `se-forordningar` | 27 | 37 |
| Sweden, Finansinspektionen's regulations | `se-fffs` | 29 | 126 |
| Denmark, acts and Finanstilsynet's orders | `dk` | 23 | 117 |
| Denmark, more of Finanstilsynet's orders | `dk-finanstilsynet` | 8 | 36 |
| Denmark, ministerial orders | `dk-bekendtgorelser` | 34 | 138 |
| Norway, acts and Finanstilsynet's forskrifter | `no` | 21 | 109 |
| Norway, more supervisory regulations | `no-regulations` | 5 | 20 |
| Norway, Finansdepartementet's forskrifter | `no-forskrifter` | 19 | 73 |
| Norway, sanctions forskrifter | `no-sanctions` | 33 | 108 |
| Finland, acts and FIN-FSA's regulations | `fi` | 35 | 166 |
| Finland, decrees | `fi-asetukset` | 23 | 47 |
| Nordic sanctions acts | `nordic-sanctions` | 5 | 11 |
| Other ministries' and agencies' orders | `issuer-gaps` | 13 | 55 |
| **All** | | **544** | **1894** |

**Market abuse** carries the regime `securities`, so every bank that follows securities law
sees it: MAR with the Listing Act's application dates, CSMAD, the delegated and
implementing acts on thresholds and closed periods, suspicious transaction reporting,
investment recommendations, buy-back and stabilisation, market soundings, disclosure and
delay, and insider lists (the 2026 act replacing Implementing Regulation (EU) 2022/1210),
the short selling and benchmarks regulations, ESMA's guidelines on delaying disclosure and
on market soundings, and each country's supplementary and criminal provisions.

## The law's own words

Source: Alex, 2026-11-13, on an obligation under a Swedish ordinance whose page read
"English, original": "it says that the original text is in english while its actually
swedish.. we need to correctly have the original text. and then we also translate to english
by default, or to swedish and english if its in another scandinavian language. this applies
on all legal and similar text", and then "Isn't it better that we now prepare all the
original words and each translation, so it's in the seed and can be approved in the library".

The baseline's 1,894 summaries are bleqq's own words in English and stay that: their
original is the language they were written in. What the page lacked was the law itself,
which belongs in the provision tree (INV-02) and which the baseline never filled (D-120).
Built as BE-5a:

- **The door.** `new_provision` and `new_provision_version` refuse a text whose
  `originalLanguage` is not the language its instrument's jurisdiction writes law in, mark
  the other languages an authority itself publishes (`officialLanguages`, Finland's Swedish)
  as neither original nor machine-made, and take `obligations`, the duties that cite the
  provision, which approval ties to it (`backend/apps/proposals/app.md`, PRO-S20).
- **The format.** `backend/apps/library/baseline/provisions/<tranche>.json`, one entry per
  section, article or guideline a duty cites, with its source, the day it was read and the
  duties it is cited by; `withoutProvision` names each duty the file gives no text for, with
  the reason. The folder's `README.md`, "The law's own words", holds the format, which
  texts stand beside an original, and what each source asks of someone who republishes it.
- **The checker and the filer.** `check_baseline.py` holds every provisions file to those
  rules, and the backend suite runs it over the whole baseline. The filer files a provision
  once the library holds its instrument and every duty it names.

The texts themselves are fetched from the official sources by script and arrive in later
changes, one tranche's file at a time.

## What it leaves out, and why

- **Standards.** They wait for the legal answer on standard titles (ADR 0041).
- **Proposals not adopted on 2026-09-30.** The Payment Services Regulation and PSD3, the
  Retail Investment Strategy, FiDA, the SFDR review and the digital omnibus beyond the AI
  Act. The watch follows them.
- **Acts aimed only at authorities, venues, CCPs or scheme operators**, and amending acts
  whose changes are cited in the duties they changed.
- **Guidelines not yet researched**: ESMA's guidelines on EMIR reporting, CSDR, SFTR and
  MiCA; the EBA's on STS criteria, SREP, IRRBB and suitability; EBA/GL/2026/09 on non-ICT
  third-party risk, whose application date was still blank.
- **Not yet researched**: in Norway individual pension savings, the beneficial-owner
  register and the accounting act; in Finland the banks' corporate-form acts and FIN-FSA's
  reporting, accounting and covered-bond regulations.
- **Orders of other issuers that bind someone else**: Denmark's BEK 1442/2005 (the
  shareholder documents, the bank only receives the form), BEK 1311/2012 (the duties fall
  on the pension holder), BEK 788/2025 (binds people, public payers and the agency) and BEK
  1160/2010 (approves an optional form); BEK 970/1992, which cites sections of the 1990
  credit act that now say something else; and Finland's 355/2016, repealed from 2026-01-01.
- **Worth a legal read before they are left out for good**: the Cyber Resilience Act for a
  bank that publishes apps; Denmark's BEK 105/2023 on payment incident reporting, whose
  legal basis the DORA amendments repealed on 2025-01-17 while Retsinformation still shows
  it in force.
- Every tranche's report of what it left out and why is in the commit that added it, and
  every fact it could not verify is a Not verified row in the Verification log.

## For a lawyer to check first

- Effective dates that the researchers derived rather than read: the eIDAS wallet
  acceptance date, ESMA guidelines' application dates counted from their publication, and
  the application dates of EBA guidelines where the EBA's page and the final report differ.
- Duties whose reach the taxonomy cannot narrow: crypto-asset service providers,
  algorithmic trading and issuers have no term, so those duties reach every firm under the
  regime and say who they bind in their summary.
- The banking union duties (SSM, SRMR), which bind Finnish banks only; an obligation may
  not carry a jurisdiction term, so their summaries say so.
- Texts read at an older wording: Norway's finansavtaleloven at its adopted 2020 text, and
  verdipapirhandelloven § 3-1, which still names MAR without the Listing Act's changes.
- Dated changes after the research day: FFFS 2026:30 renumbers FFFS 2017:2's research
  payment rules on 2026-10-01; the Swedish mortgage credit act is renamed and renumbered on
  2026-11-20, when the new consumer credit acts in Sweden, Denmark and Finland apply. The
  acts they replace keep governing agreements made before that day.
- Orders of other issuers: Denmark's NemKonto order BEK 790/2025 binds only the banks that
  join its scheme; BEK 531/2000 rests on the repealed 2000 data protection act though
  Retsinformation lists it as valid; both NemKonto orders were issued by
  Digitaliseringsministeriet, abolished on 2026-06-03, whose work and orders moved to
  Forsknings-, Uddannelses- og Digitaliseringsministeriet, so the authority may want its
  successor's key. Finland's 1030/2025 applies first to 2026 data, and 699/2004's ESAP
  duties from 2030-01-10 are not recorded.
- Where the baseline and the sample library meet: the baseline reuses the sample's key for
  every real instrument the sample holds, so a demo database skips it; the sample's date for
  Delegated Directive (EU) 2017/593 was wrong and is corrected to 2017-04-20.

## Sources the sweeper checks

`sources.json` names fifteen pages, registered by the same filing through the console's own
writer, weekly to match the sweeper: the Official Journal, the Commission, ESMA, the EBA and
EIOPA; each country's legal gazette; and Finansinspektionen (news and FFFS), IMY, both
Finanstilsynet and Finanssivalvonta. EUR-Lex and lovdata.no refused this build's direct
requests, so the runner's network must be able to reach them, or the Publications Office's
own service in EUR-Lex's place.
