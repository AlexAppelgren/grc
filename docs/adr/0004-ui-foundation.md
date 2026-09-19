# ADR 0004 — UI foundation: Tailwind, Radix primitives and our own components on Green tokens

**Date:** 2026-09-19 · **Status:** accepted by default (DECISIONS D-04; the owner confirms after the Phase 0 spike)

## Context

The prototype (`design/prototype/index.html`) uses the Green Design System's
token values but none of its components. Green's own agent instructions
require its text and layout components everywhere, which would fight the
prototype's custom rows, pills, chips and timeline, and Tailwind. Whether
Green Core web components render and hydrate under Next.js `next start` was
**not verified** before Phase 0 (`docs/plans/Verification_Log.md`). Playbook
Section 6.3 allows a Green component for a heavy widget only after a spike
proves it.

## Decision

Tailwind 4 plus Radix primitives (dialog, dropdown menu, tooltip, select,
popover, tabs, checkbox, switch) plus our own components that reproduce the
prototype (`Pill`, `Row`, `Chip`, the timeline, the legal text block), all on
Green 2023 tokens generated into `tokens.generated.css`. A Green Core component
may be used only where the D-04 spike proves it renders and hydrates under
`next start` and matches the design. Deliberately not done: adopting Green
Core's layout and text components, and any copied token values.

## Spike outcome

Run 2026-09-19 with `@sebgroup/green-core` 3.23.0, Next 16.3.5 and React
19.3.0 on the route `/dev/green-spike`, proven by
`frontend/tests/e2e/green-spike.spec.ts` against a production build. Full
notes in `frontend/docs/D-04-spike.md`.

- **Tried:** `GdsButton` from `@sebgroup/green-core/react`.
- **Renders on the server:** yes. The prerendered HTML carries the scoped
  custom element (`gds-button-<hash>`) with its slotted label.
- **Hydrates under `next start`:** yes. Two clicks advance React state and
  `customElements.get()` returns the real element class. No hydration
  warnings; the api-guard fixture would have failed the test on a page error.
- **Needed:** `'use client'` on the component that renders the element,
  nothing else. No `next/dynamic` with `ssr: false`, no manual registration
  (Green defines on first render and suffixes tag names by version), no CSS
  import for the 2023 look.
- **Design match:** the element styles itself inside shadow DOM, so only the
  `--gds-sys-*` tokens that `brand.css` overrides reach it. Colour parity
  with the prototype has to be checked per component, in both themes.
- **Allowlist after the spike:** empty. The condition for using a Green
  component is met, but no screen needs one yet. Candidates are heavy widgets
  only (date picker, dropdown, dialog), each added here with its check.
- **Regression check:** the spike route and its test stay until a real Green
  component ships with its own journey.

The owner confirms the default after reading this section.

## Consequences

Easier: the prototype's look is reproduced one to one and every component is
ours to test, theme and translate. Harder: heavy widgets (date pickers, data
grids) are built or chosen case by case. To remember: the `/dev/pills`
gallery and the contrast test are the design gate; a Green component that
passes the spike is listed here.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Token pipeline, `brand.css`, `Pill`, the gallery, the spike | Phase 0 |
| 2 | Further system cards as chunks need them | Chunks 1 onward |
