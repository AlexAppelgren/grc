# ADR 0019 — Framework choices and exact version pins

**Date:** 2026-09-19 · **Status:** accepted by default (playbook 2.1 and Appendix C; the owner confirms)

## Context

Playbook 2.1 names the stack and asks Phase 0 to pin exact versions and
record them. Versions were checked on PyPI and npm on 2026-09-19
(`docs/plans/Verification_Log.md`): Django 5.2.17 is the newest 5.2 patch and
Django 6.1.1 exists (D-17 pins 5.2, ADR 0017); TypeScript 7.0.2 exists but its
tooling support (typescript-eslint, Next, openapi-typescript) is unverified,
so the newest 5.x is used; Playwright 1.63.0 carries the
`browserContext.credentials` virtual authenticator (added in 1.61) that
passkey journeys need. The Phase 0 brief fixed every other pin.

## Decision

Django with Django Ninja (not DRF), PostgreSQL 16 with pgvector everywhere,
Celery with Redis, py_webauthn, Next.js with TypeScript, Tailwind, Radix
primitives, TanStack Query, Vitest, Playwright. Exact pins, recorded in
`backend/pyproject.toml` (`requires-python = ">=3.12,<3.13"`; ruff cannot parse the tilde form, same meaning) and `frontend/package.json`
(no `^`):

**Runtime.** Python 3.12.10 locally, Node 22.18 locally and 22.23.2 in CI (undici, a Next dependency, declares 22.19 as its floor; `frontend/package.json` engines say `>=22.19.0`), npm 10.9, Poetry 2.0.1.

**Backend.** django 5.2.17, django-ninja 1.7.0, psycopg[binary] 3.3.6,
pgvector 0.5.0, celery 5.6.3, redis 8.1.0, webauthn 3.0.0, gunicorn 26.2.0,
sentry-sdk 2.69.2, django-cors-headers 4.9.0, dj-database-url 3.1.2,
python-json-logger 4.2.0, boto3 1.43.97 (pydantic 2.13.5 transitively); whitenoise
was not needed and is not installed.
Dev: ruff 0.16.8, mypy 2.3.1, django-stubs 5.2.9 **and django-stubs-ext 5.2.9**
(Poetry otherwise resolved ext 6.1.1 beside stubs 5.2.9 and mypy crashed with
"Cannot find component 'db'"; mypy 2.3.1 works with the pair although
django-stubs declares `compatible-mypy <1.20`), coverage 7.16.1, pyyaml 6.0.3
and types-pyyaml 6.0.12.20250915 (the contract drift script reads
`docs/inputs/openapi.yaml`).

**Frontend.** next 16.3.5, react 19.3.0, react-dom 19.3.0, typescript 5.9.3
(newest 5.x), tailwindcss 4.3.3, @tailwindcss/postcss 4.3.3, postcss 8.5.28,
@tanstack/react-query 5.103.1, axios 1.20.0, next-themes 0.4.6, vitest 5.0.1,
@vitest/coverage-v8 5.0.1, @playwright/test 1.63.0, eslint 10.10.0,
typescript-eslint 8.70.0, @next/eslint-plugin-next 16.3.5,
eslint-plugin-react-hooks 7.1.1, eslint-plugin-react 7.37.5 (added for
`jsx-no-literals`; it declares ESLint <= 9.7, resolved with a scoped npm
`overrides` entry rather than `legacy-peer-deps`), openapi-typescript 7.13.0,
@sebgroup/green-tokens 3.1.8, @sebgroup/green-core 3.23.0,
@radix-ui/react-dialog 1.1.23, @radix-ui/react-dropdown-menu 2.1.24,
@radix-ui/react-tooltip 1.2.16, @radix-ui/react-select 2.3.7,
@radix-ui/react-popover 1.1.23, @radix-ui/react-tabs 1.1.21,
@radix-ui/react-checkbox 1.3.11, @radix-ui/react-switch 1.3.7,
class-variance-authority 0.7.1, clsx 2.1.1, tailwind-merge 3.7.0,
@testing-library/react 16.3.3, @testing-library/jest-dom 7.0.1, jsdom 30.1.0,
@fontsource-variable/hanken-grotesk 5.3.0,
@fontsource-variable/noto-sans-mono 5.3.0.

**Infrastructure.** `pgvector/pgvector:pg16`, `redis:7-alpine`.

Deliberately not done: Django 6.x (ADR 0017), TypeScript 7.x (tooling
unverified), DRF, SQLite anywhere, caret ranges.

## Consequences

Easier: every environment installs the same bytes; Dependabot proposes
upgrades one ecosystem at a time. Harder: a pin that fails to install is
replaced by the nearest working version and the change is recorded here
with its reason. To remember: the TypeScript 7 move is its own ADR once
typescript-eslint, Next and openapi-typescript support it.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Pins in `pyproject.toml`, `package.json`, `docker-compose.yml` | Phase 0 |
| 2 | Deviations recorded below as they happen | Ongoing |

## Deviations recorded

_None yet. Append a row: package, pinned, used, reason, date._
