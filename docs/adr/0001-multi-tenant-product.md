# ADR 0001 — Multi-tenant product with one shared library

**Date:** 2026-09-19 · **Status:** accepted by default (DECISIONS D-01; the owner confirms before the first external tenant)

## Context

Compliance Watch could be built as an internal tool for one bank or as a
product sold to many. The PRD (section 1) describes a product for enterprise
banks in the Nordics, and the two-zone model in playbook Section 14 (a shared
library of public facts, a tenant zone of private judgement) works unchanged
whether there is one tenant or fifty. Nothing was verified against an outside
source; the constraint is the PRD.

## Decision

Build a multi-tenant product from the first commit: one shared library, many
tenants, tenant tables under forced row-level security, platform roles
(`library_editor`, `platform_admin`) distinct from tenant roles. Deliberately
not done: a single-tenant mode or a per-tenant database, because both would
fork the isolation model the guards prove.

## Consequences

Easier: onboarding a second bank is a row in `tenant`, and the library is
curated once for everyone. Harder: every tenant table needs its policy, every
tenant route its isolation proof (NFR-01), and platform staff need a support
access grant to see anything (TEN-06). To remember: the owner confirms this
before the first external tenant, and a single-tenant deployment is still
this product with one tenant row.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | `TenantModel`, `LibraryModel`, RLS policies, the isolation guards | Phase 0 and chunk 1 |
| 2 | Platform console with tenants and plans | Chunk 4 and chunk 12 |
