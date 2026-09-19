# ADR 0037 — A certificate sits on the entity's licence row and reaches the roadmap, not the feed

**Date:** 2026-09-19 · **Status:** accepted by default (D-43, PRD 0.3 TEN-02, HOM-03, AC-TEN1; the owner confirms)

## Context

A certificate is held by one legal entity, issued by a certification body, with
a number, a scope statement, a validity period and a next audit date. Evidence
has no per-entity anchor, and the review branch of the roadmap hides compliant
rows, so a certified and compliant entity's next audit would vanish there. The
calendar feed carries public facts only.

## Decision

The certificate is a licence row: the licence type names the certificate and
its issuer, the reference is the certificate number, the scope note is its
scope statement, and the existing grant and withdrawal dates apply. Three
nullable columns are added: a validity end date, a next audit date and an
owner. The row carries no taxonomy term and decides no span. Two roadmap
branches show the expiry and the next audit as internal items, "Our deadline",
with the row's owner, and both are left out once the row is withdrawn. Neither
enters the calendar feed. Surveillance audits are not recurring duties: after
an audit the owner records an external-audit assessment, gaps for
nonconformities and the report as evidence, then sets the next audit date.

## Consequences

Easier: no new table, and the entity screen gains one section rather than a
concept. Harder: the roadmap view migration grows two branches that must be
kept out of the feed, and member removal must reassign licence owners. To
remember: the licence row is the one source of certificate dates; a date on an
evidence file belongs to the file.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The three columns and the entity screen section | Chunk 8 |
| 2 | The two roadmap branches and the feed exclusion | Chunk 8 view migration |
