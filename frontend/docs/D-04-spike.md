# D-04 spike: a Green Core component under `next start`

Date: 2026-09-19. Packages: `@sebgroup/green-core` 3.23.0, `next` 16.3.5,
`react` 19.3.0. Route: `/dev/green-spike` (`src/app/dev/green-spike/`).
Proof: `tests/e2e/green-spike.spec.ts`, run against a production build
(`npm run build && npm run start`), Chromium.

## Result: works

`GdsButton` from `@sebgroup/green-core/react` renders on the server and
hydrates on the client. The Playwright test clicks the button twice and
reads React state change "Not clicked yet" → "Clicked 1 time" → "Clicked 2
times", and confirms `customElements.get('gds-button-…')` is defined, so the
element on the page is the real web component, not a fallback.

## What was needed

| Need | Answer |
|---|---|
| `'use client'` | Yes. The wrapper uses `useRef`/`useControlledValue`, so the component that renders `<GdsButton>` is a client component. The page itself stays a server component and renders the client component. |
| `next/dynamic` with `ssr: false` | **Not needed.** The wrapper calls `GdsButtonClass.define()` inside the render function; on the server this is a no-op because Green guards the custom-element registry. `next build` prerendered the route statically; the HTML contains `<gds-button-3deb38 rank="primary">` with the slotted label. |
| Custom-element registration | Automatic on first render on the client ("define on use"). Green scopes tag names with a version suffix (`gds-button-3deb38`), so two Green versions on one page cannot collide. Nothing to register by hand. |
| CSS | None to import for the 2023 design: styles are in the element's shadow root. The 2016 "transitional" style for the button is registered from `@sebgroup/green-core/components/button/button.trans.styles.js` (`register()`), called in a `useEffect` so it runs on the client only. The spike registers it as the brief asked; it is not needed for the 2023 look. |
| Hydration warnings | None in the console during the test (api-guard fails on page errors). |
| Bundle | The button pulls Lit and Green's shared chunks into the client bundle for that route only. |

## Caveats for the ADR

- Green's own agent instructions (MCP `get_instructions`) require Green's
  text and layout components everywhere. We do not follow them: the
  prototype's rows, pills, panels and timeline are our own primitives on
  Green tokens (DECISIONS D-04). A Green Core component is a candidate for
  a heavy widget only (datepicker, dropdown, dialog), after it is checked
  against the design in both themes.
- Green Core styles live in shadow DOM, so Tailwind utilities and our theme
  variables do not reach inside a Green element except through the tokens
  Green itself reads (`--gds-sys-*`), which brand.css overrides. Colour
  parity with the prototype must be checked per component.
- The React wrapper maps `className` to `class`; `onClick` works; camel-cased
  custom events (`onGdsUiState`) exist per the React guide.
- The spike route and its test stay in the repo as the regression check for
  the ADR's condition ("renders and hydrates under `next start`"). Remove
  both when a real Green component ships with its own journey, or keep them
  if none does.

## Verdict for DECISIONS D-04

The condition is met. Default stands: Tailwind + Radix + our own
components on Green tokens; a Green Core component may be used for a heavy
widget when it matches the design. Owner confirms after reading this.
