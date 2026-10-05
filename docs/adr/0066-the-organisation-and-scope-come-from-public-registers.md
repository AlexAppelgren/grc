# ADR 0066 — The organisation and the regulatory scope come from public registers, through the existing request

**Date:** 2026-10-05 · **Status:** accepted (Alex, 2026-10-05: "go ahead, write the brief and build all steps"; D-121, PRD 0.9 TEN-07, TEN-08, FP-05; follows D-89, D-96, ADR 0059)

## Context

A bank described itself twice: its companies, types and licences on Organisation, and around
40 terms across nine dimensions on Regulatory scope, with nothing joining the two. Most of
those terms are facts a supervisor publishes. GLEIF holds every company's identity and its
group, under CC0; Finansinspektionen's register holds each Swedish company's businesses,
licences with grant dates and branches, free to reuse with source and date. Neither offers a
documented API for licences: FI's is the CSV export behind its search and HTML pages.

`BANKING_GROUPS.md` (D-96) planned per-company scope as exclusions each company files by hand,
on a request that names one company.

## Decision

1. A person holding `vocab.manage` types an organisation number or LEI; a job reads GLEIF and
   FI through one adapter (`apps/shared/adapters/registers.py`, live and mock, the mock refused
   deployed outside the test environment) and returns the group. The person picks the
   companies; only then are legal entities created or linked and their register facts stored.
2. Licences are shown from the stored facts and never copied into licence rows.
3. A versioned mapping file turns FI's wording into term keys. From it the scope page suggests
   the group's terms and each company's exclusions (the licence-bound terms its facts do not
   give it). The person files the suggestion as an ordinary regulatory scope request; a second
   person approves it with a passkey.
4. Exclusions are stored in `entity_scope_exclusion` and carried on request lines, so one
   request holds the group's change and every company's, and one waiting request per bank
   stays the rule. They narrow the register's span only.
5. A nightly re-read refreshes the facts with an audit event and changes no scope.

## Consequences

- Every scope change, a company's included, still passes four eyes and a step-up; nothing a
  register says reaches the scope without two people.
- A layout change at FI fails a lookup or a re-read with `register_unavailable`; nothing is
  guessed. The mapping file is reviewed like code, and a licence it does not know is shown, not
  mapped.
- D-96's hand-filed exclusions are replaced by derived ones for the licence-bound dimensions;
  its entity switcher and membership scope remain to be built.
- Adding another supervisor's register is another adapter entry and another mapping section.
