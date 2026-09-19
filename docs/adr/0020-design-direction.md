# ADR 0020 — Design direction

**Date:** 2026-09-19 · **Status:** accepted by default (playbook 7 step 1; source `design/README.md`; the owner confirms)

## Context

Playbook Section 7 asks for the chosen direction to be recorded with
`design/README.md` as the source. The interactive prototype
(`design/prototype/index.html`) is the contract for flow, wording, labels and
pills; the pill card (`design/system/pills-and-labels.md`) is the contract for
tones; `design/brand/README.md` holds the wordmark and the brand placeholders.
`design/README.md` also lists where the prototype is wrong or silent.

## Decision

The timeline home showing the next dates as the same short list on phone and
desktop, with part of the weekly briefing on it and the full briefing one
tap away. The full calendar on its own roadmap page where a card expands in
place. Restraint in the style of wealth and asset management: a very dark
green, sand surfaces, brass for identity, Hanken Grotesk for text, Noto Sans
Mono for legal references and the wordmark. Phone first: actions on the
right, two buttons share one row, primary on the right. The prototype's
labels and pill system reproduced, not reinterpreted. Where the prototype is
wrong (the tenant officer approving proposals, direct footprint toggles,
"Switch user", labels stored instead of keys, copied hex values, tags that
never render) the fixes in `design/README.md` apply. Screens the prototype
lacks (sign-in and enrolment, tenant admin, platform console, vocabulary
management, the empty, loading, error and denied states) are designed as
cards in the prototype's language before they are built. Deliberately not
done: a dashboard-first home, Green's own layout components, a light-only
theme.

## Consequences

Easier: every screen decision has a source to point at, and the `@e2e`
journeys follow the prototype's path. Harder: each new screen costs a card
first. To remember: the prototype decides look, wording and flow, never
rules; the PRD wins on any rule.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Tokens, type scale, `Pill`, gallery, phonetic logo, shell | Phase 0 |
| 2 | System cards and screen cards per chunk | Chunks 1 to 14 |
