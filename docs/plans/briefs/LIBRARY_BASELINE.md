# The library baseline: the shared library's starting inventory

Source: Alex, 2026-09-30: "build up the inventory for everything relevant as of today", and
market abuse laws "also needs to be included"; then "the bleqq agent will run and look for
changes and new things". Decided in D-118 and ADR 0065. Built on the branch
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
   `POST /proposals` takes it, with the official page it was read from. The rules it was
   researched under are the definition's `prompt.md` and the folder's `README.md`.
2. **Checked twice before any deploy.** `check_baseline.py` checks shape and keys without a
   database. `apps/proposals/tests_baseline.py` files every entry through the real proposal
   code, approves it as a person and proves each one applies.
3. **Filed through the proposal door.** `manage.py file_library_baseline` files what the
   library neither holds nor has open as proposals of the platform agent
   `library-baseline`, instruments first, each duty on the call after its instrument is
   approved. It is safe to repeat, and a rejected entry stays rejected until its file
   changes.
4. **Approved by a second principal.** A person in the console with a passkey today; the
   confirming agent once it is published and its runner is live.
5. **Kept current by the watch.** Each watch run re-checks the records of the sources it
   checks and proposes a correction where one has drifted, and registers what is new.

## What it covers

The sector scope on 2026-09-30, for the EU, Sweden, Denmark, Norway and Finland: what is in
force, and what is adopted and applies later (with the later date on the duty). An EU
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
| Sweden, acts | `se-acts` | 39 | 218 |
| Sweden, Finansinspektionen's regulations | `se-fffs` | 29 | 126 |
| Denmark | `dk` | 23 | 117 |
| Norway | `no` | 21 | 109 |
| Finland | `fi` | 35 | 166 |
| **All** | | **328** | **1248** |

**Market abuse** carries the regime `securities`, so every bank that follows securities law
sees it: MAR with the Listing Act's application dates, CSMAD, the delegated and
implementing acts on thresholds and closed periods, suspicious transaction reporting,
investment recommendations, buy-back and stabilisation, market soundings, disclosure and
delay, and insider lists (the 2026 act replacing Implementing Regulation (EU) 2022/1210),
the short selling and benchmarks regulations, ESMA's guidelines on delaying disclosure and
on market soundings, and each country's supplementary and criminal provisions.

## What it leaves out, and why

- **Sanctions.** Not named in the sector scope and without a regime (owner question).
- **Government ordinances.** A förordning, a Norwegian ministry forskrift or a Danish
  ministry bekendtgørelse fits no instrument level (owner question).
- **Standards.** They wait for the legal answer on standard titles (ADR 0041).
- **Proposals not adopted on 2026-09-30.** The Payment Services Regulation and PSD3, the
  Retail Investment Strategy, FiDA, the SFDR review and the digital omnibus beyond the AI
  Act. The watch follows them.
- **Acts aimed only at authorities, venues, CCPs or scheme operators**, and amending acts
  whose changes are cited in the duties they changed.
- **Guidelines not yet researched**: ESMA's guidelines on EMIR reporting, CSDR, SFTR and
  MiCA; the EBA's on STS criteria, SREP, IRRBB and suitability; EBA/GL/2026/09 on non-ICT
  third-party risk, whose application date was still blank.
- **National acts not yet researched**: in Norway the sanctions act, individual pension
  savings, the beneficial-owner register and the accounting act; in Finland the banks'
  corporate-form acts and FIN-FSA's reporting, accounting and covered-bond regulations.
- **Worth a legal read before they are left out for good**: the Cyber Resilience Act for a
  bank that publishes apps, and Denmark's BEK 105/2023 on payment incident reporting beside
  DORA.
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
- Where the baseline and the sample library meet: the baseline reuses the sample's key for
  every real instrument the sample holds, so a demo database skips it; the sample's date for
  Delegated Directive (EU) 2017/593 was wrong and is corrected to 2017-04-20.

## Sources the sweeper should check

The registry is empty on a new deployment. Register one source per authority the baseline
names, in the console (Sources), so the watch re-checks these records and finds what is new:
EUR-Lex, ESMA, EBA and EIOPA; riksdagen.se and fi.se; retsinformation.dk and
finanstilsynet.dk; lovdata.no and finanstilsynet.no; finlex.fi and finanssivalvonta.fi.
EUR-Lex and lovdata.no refused this build's direct requests, so the runner's network must be
able to reach them, or the Publications Office's own service in EUR-Lex's place.
