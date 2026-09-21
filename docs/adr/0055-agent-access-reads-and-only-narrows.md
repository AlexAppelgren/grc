# ADR 0055 — An agent a bank runs reads through a registered entry that can only narrow

**Date:** 2026-09-20 · **Status:** accepted (owner decision, 2026-09-20; D-63, D-65, D-68, PRD 0.5 ACC-01, ACC-02, ACC-04, ACC-05, ACC-07)

## Context

A bank runs agents of its own: a coding agent building a payment or trading
service, a product agent shaping an account type, a procurement agent reading a
supplier contract, an assistant answering a staff question. Each needs to know
which regulation reaches what it is working on, and today the only way to find
out is to ask a compliance officer for an export.

Alex asked for an MCP server over the API, with each consuming agent registered
and its access managed by what the product calls the footprint: "an agent
developing solutions within a trading domain might not need access to card
related regulations." He then generalised it: development is only the first case,
and every agent a bank runs should reach the data the same way.

The product already has two kinds of agent and neither is this one. AGT-03's
platform agents and AGT-04's tenant agents run on our infrastructure, on our
schedules, against budgets we hold, and they **write**: changes, proposals,
findings. These run on the bank's infrastructure, we never see their prompts,
and they read.

## Decision

A tenant registers each agent it runs as an **agent access entry**: a name, a
purpose, the team that owns it, and the departments and products it serves. The
entry holds no prompt, no schedule and no definition, because we do not run it.

- **The scope is derived and only narrows.** The entry's effective scope is the
  taxonomy terms of the departments and products it names, intersected with the
  tenant footprint, computed per request from the footprint table and never from
  anything the caller sends. FP-01's rule applies unchanged inside it, so an empty
  dimension does not restrict and naming no department and no product narrows
  nothing. One code path serves a general assistant and a trading agent.
- **Outside scope is 404.** A record the entry may not see answers 404, the
  answer another tenant gets, so scope cannot be probed from the shape of an
  error. A filtered 200 would leak the existence of what it filtered.
- **It reads, and in R2 it only reads.** Every mutating route answers 403
  `read_only_credential`, and no agent access credential holds a writing scope.
  The proposal door, the applicability request and the four-eyes constraints stay
  the only ways anything changes, and none of them is reachable from here.
- **The MCP server adds no read path.** It is one router over the endpoints that
  already exist, using the same authentication classes, the same `@requires_scope`
  gates, the same logic modules and the same pagination. A bank that prefers the
  REST API directly gets identical guarantees, because there is only one
  implementation to guarantee.
- **It never narrows silently.** Every answer states the scope it was answered in
  and its "as of" date, and an answer to a description that appears to touch the
  bank's footprint outside the entry's scope names the dimensions and terms it
  could not see, read from their labels and never from their records.

## Why

The narrowing is nearly free because the rule already exists. `in_footprint` and
the SQL function `taxonomy_in_footprint` are applied a second time with the
entry's terms; there is no second access system to reason about, and the property
that matters ("an entry never sees what the bank's own regulatory scope does
not") holds because the intersection is taken on our side.

Deriving the scope from departments and products rather than from a list of terms
means it stays true as the bank re-describes itself, and the bank maintains one
description of its business instead of two.

The last bullet is the one that is not obvious and matters most. In a compliance
product a false negative is invisible: a developer who is told nothing assumes
nothing applies, and a narrowed agent is a machine for producing exactly that
failure. Naming what was out of scope costs a label lookup, leaks no record, and
turns the dangerous failure into a visible one.

## Consequences

- `agent_access` plus two join tables, and two columns on `api_key`. No new app.
- Chunk 11 (R2), because it needs chunk 3's library reads, chunk 7's search and
  chunk 8's departments, products, teams and register.
- ACC-10 (R3) opens one write: an entry records that a named application touches
  a register entry, as a linked internal item under REG-05. The read-only rule
  above is stated for R2 so that widening it later is a decision, not a drift.
- **Reversal.** Deleting the entry's department and product joins and refusing
  `tenant:read` leaves a library-only reader over the same API, which is the
  smaller feature this could have been.
