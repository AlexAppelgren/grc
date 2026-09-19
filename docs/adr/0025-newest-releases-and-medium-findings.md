# ADR 0025 — Newest releases of every package, and MEDIUM findings block

**Date:** 2026-09-19 · **Status:** accepted (owner decision)

## Context

Phase 0 pinned every dependency at the newest release found that morning,
with two exceptions kept on purpose: Django on the 5.2 LTS line (D-17, ADR
0017) and TypeScript on 5.x because 7.x tooling support was unverified (ADR
0019). Once Phase 0 was green on `main`, Alex asked for three things in
writing: update all packages and libraries to their latest versions, move to
the latest Django, and upgrade to the latest TypeScript. Separately: MEDIUM
security findings must fail CI too, not only HIGH and CRITICAL.

Checked before deciding (2026-09-19): django-ninja 1.7.0, django-cors-headers
4.9.0 and dj-database-url 3.1.2 declare Django 6 support in their PyPI
classifiers; django-stubs and django-stubs-ext 6.1.1 exist as a matched pair.
TypeScript 7.0 ships the native compiler and no JavaScript API (the TypeScript
7.0 announcement, fetched 2026-09-19, "Running side-by-side with TypeScript
6.0"). typescript-eslint 8.70.0 refuses to load under 7.0 and says so at
start-up; openapi-typescript 7.13.0 crashes on the missing `ts.factory`. The
announcement's own arrangement is the fix: the `typescript` package name
resolves to `@typescript/typescript6` (the last JavaScript API, 6.0.3) for
every tool that needs the API, and `@typescript/native` carries `typescript`
7.0.2 for the `tsc` command. typescript-eslint's peer range (`<6.1.0`) admits
6.0.3; openapi-typescript's (`^5.x`) does not, so an npm override widens it.

## Decision

- Every package in `backend/pyproject.toml` and `frontend/package.json` is
  pinned at its newest release on the pin date. Django 6.1.1 replaces 5.2.17.
  TypeScript 7.0.2 replaces 5.9.3 as the compiler (`npm run typecheck` runs
  the native `tsc`; Next builds with it), installed as `@typescript/native`,
  while the `typescript` name resolves to `@typescript/typescript6` 6.0.3 for
  typescript-eslint, openapi-typescript and Vitest. An npm override widens
  openapi-typescript's peer range to that package; the split collapses back
  to one package when TypeScript 7.1 ships its API and the tools adopt it.
- Two exceptions with a reason: `@types/node` follows the Node major the
  images and CI actually run (22), because typings for a newer runtime would
  admit APIs that do not exist at run time; `jsdom` stays on 30.x, which is
  newer than the `latest` dist-tag npm reports (29.1.1).
- Container images move to Alpine bases. The Debian slim base carried 91
  MEDIUM and HIGH findings with no upstream fix, which no change in this repo
  could clear; Alpine scans clean. Poetry, pip and npm are absent from the
  runtime layers.
- The gates block on MEDIUM: Trivy at `MEDIUM,HIGH,CRITICAL` with unfixed
  findings still counted, `npm audit --audit-level=moderate`, and the CodeQL
  gate at security-severity 4.0 (medium), which it already was.
- Dependabot no longer ignores Django or TypeScript majors.

Deliberately not done: Python stays on 3.12 (playbook 2.1 names it and the
request was about packages, not the runtime); Node stays on 22 for the same
reason.

## Consequences

Easier: no LTS-versus-latest debate, one policy, Dependabot keeps it true
weekly. Harder: a major release can land mid-chunk; the pre-push checklist
and CI are the safety net, and a breaking upgrade is pinned back with its
reason recorded here. To remember: Django 6 drops nothing this codebase used
on the day of the switch; the full backend checklist and the E2E run passed
on 6.1.1 before the commit.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | Pins, images, gate thresholds, this ADR | 2026-09-19, same commit |
| 2 | Collapse the TypeScript 6 API package and the override once TypeScript 7.1 ships its API and typescript-eslint and openapi-typescript support it | When Dependabot proposes it |
