# Compliance Watch frontend

Next.js 16 (App Router), React 19, TypeScript strict, Tailwind 4 on Green
tokens with our brand layer, Radix primitives, TanStack Query, Vitest,
Playwright. Conventions live in `docs/PLAYBOOK.md` Section 6; this file is
the quick start only.

```
npm ci
npm run build:tokens     # scripts/build-tokens.mjs -> src/styles/tokens.generated.css
npm run lint
npm run typecheck
npm run test:coverage
npm run check:messages   # scripts/messages-check.mjs
npm run check:copy-drift # scripts/copy-drift-check.mjs
npm run build
npm run test:e2e         # playwright: boots the backend + next start
npm run test:e2e -- --grep @smoke
```

`npm run dev` is for a person at a keyboard. E2E always runs a production
build (`playwright.config.ts`); `E2E_SKIP_BACKEND=1` exists only for the
specs that make no API call (gallery, spike, the Phase 0 shell smoke) and
api-guard prints a notice whenever it is set.

Where things are:

| Path | What |
|---|---|
| `src/styles/tokens.generated.css` | Green 2023 tokens, generated, never edited |
| `src/styles/brand.css` | Our brand values (D-05). The only file with our own colours |
| `src/styles/theme.css` | Tailwind theme: semantic colours, the named type scale |
| `src/components/ui/Pill.tsx` | The one pill component; tones in `pill-tones.ts` |
| `src/features/**/*-presentation.ts` | Label, tone and order from keys and kinds |
| `src/shared/navigation/registry.ts` | Every destination, permission-gated |
| `src/shared/utils/api-client.ts` | The single axios instance |
| `src/messages/<namespace>/{en,sv}.json` | Every user-facing string, one file pair per feature namespace |
| `tests/e2e/support/api-guard.ts` | `test` for every spec |
| `docs/D-04-spike.md` | Green Core under `next start`: the spike result |

Public settings: `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_PRODUCT_NAME`
(default "Compliance Watch"), `NEXT_PUBLIC_DEFAULT_LOCALE` (`en` or `sv`),
`NEXT_PUBLIC_SUPPORT_CONTACT`.
