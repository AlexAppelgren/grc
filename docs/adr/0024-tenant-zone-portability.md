# ADR 0024 — Tenant-zone portability

**Date:** 2026-09-19 · **Status:** accepted by default (playbook 12, 14, 18; Solution Design "Zones"; the owner confirms)

## Context

A large bank may require that its judgement and work (the tenant zone) run
inside its own environment while the shared library and the agents stay
with the platform. DORA (Article 30, secondary sources so far) makes service
and data locations, access, recovery and exit contract terms. The two-zone
model already separates the data; this ADR keeps the code from growing
dependencies that would prevent the split.

## Decision

Keep the tenant zone movable:

- Library and tenant tables never share a row; a tenant table references
  library records by immutable key or id, never by join for correctness.
- Deployment is container-only and twelve-factor with nothing host-specific
  in code (ADR 0016), so the same image runs in a bank's environment.
- Every tenant write goes through the API and `record()`, so an audit stream
  (INT-03) and a full export (REP-04) exist for any tenant on any host.
- Agents reach the API with scoped keys and never write tenant tables
  directly.
- Adapters (LLM, embedder, mailer, storage, runner) are chosen by settings,
  so a bank-hosted tenant zone can point at its own providers.

Deliberately not done in Phase 0: building the split itself, a
library-replication protocol, or per-tenant databases. Those are R3 or later
and get their own ADR when a bank asks.

## Consequences

Easier: the conversation with a bank's vendor review starts from an
architecture that already permits the ask. Harder: a cross-zone feature
(search over tenant text, joins from tenant to library in one SQL statement)
has to be designed as an API call or a copied fact, which is why chunks copy
validity dates and cases cache their footprint match. To remember: any new
foreign key from a tenant table to a library table is reviewed against this
ADR.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Zone base models, adapters by setting, container-only deploy | Phase 0 |
| 2 | Export, audit stream, exit | Chunks 12 and 13 |
| 3 | The split itself, if a bank requires it | New ADR |
