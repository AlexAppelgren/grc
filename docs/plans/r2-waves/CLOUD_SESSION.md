# Standing rules for an R2 build cloud session

You build ONE package of the plan for release R2 of Compliance Watch (bleqq), unattended, in a Claude Code cloud session. Your prompt names your wave W, your package KEY, and possibly dependency branches. Your package entry (title, goal, requirement and scenario IDs, owned and shared files, acceptance, brief) is the object whose "package" is KEY in `docs/plans/r2-waves/waveW.json` on branch `origin/claude/r2-plan`. The brief is authoritative for scope; CLAUDE.md is authoritative for rules. Read the app.md of every app you touch, the relevant task brief in docs/plans/briefs/ (CHUNK8_TASKS.md to CHUNK11_TASKS.md, AGENT_ACCESS.md), and the design card in design/screens/ for any UI.

## Setup
1. Follow "The session's rules" in docs/runbooks/WORKTREES.md (section "Cloud tasks"). Run `bash scripts/cloud-setup.sh --e2e` first (in the background while you read).
2. `git fetch origin && git checkout -b claude/r2wW-KEY origin/main` (origin/main holds R1 and every integrated earlier wave). If your prompt names dependency branches, merge each with `git merge --no-ff origin/<branch>` before you start and resolve conflicts keeping both sides' intent.

## Parallel work
Many other sessions build the other packages of your wave from the same base at the same time. Stay inside your owned files plus clearly separated appended blocks in your shared files, so every merge stays mechanical. If you must touch anything else, keep it minimal and name it in your report.

## Decisions
Take the docs/DECISIONS.md default. D-74, D-75 and D-89 are Alex's decisions; D-89 means agents never manage a bank's regulatory scope and scope changes keep four eyes. The plan pre-assigns D-91 to D-97 to the packages its briefs name. Alex answered the plan's owner questions on 2026-09-25 (the "answer" of each entry in docs/plans/r2-waves/owner_questions.json): D-98, a bank's capped research text may reach a model as a guarded second exception beside Ask; D-99, a control is a REG-05 internal item of the control kind; D-100, the device-bound passkey policy (ID-07) is out of R2; D-101, evidence is uploaded multipart and Alex provisions clamd. They bind every package. If you need another decision row, number it D-1xx with your package key in the row; the integrator renumbers. Anything that genuinely needs Alex goes in docs/TODO_FOR_alex.md in a block headed with your package key, with the default you took.

## Gates (all green before you finish)
- Everything your brief lists.
- ruff and mypy; the backend test modules of every app you touched: `cd backend && ./run.sh run python manage.py test apps.<app> --settings=config.test_settings --noinput --parallel 4`; migration drift and `migrate_from_zero` if you touched a model.
- `python backend/scripts/compliance_check.py --all`, `python backend/scripts/requirements_coverage.py`, `python backend/scripts/api_docs_gate.py` (0 outside the ledger, 0 stale; the ledger only shrinks), `python backend/scripts/contract_drift.py`.
- Frontend: lint, typecheck, `npx vitest run` for your test files, `npm run check:messages`, `npm run check:copy-drift`.
- E2E for every journey your package owns or touches: `cd frontend && npm run test:e2e -- --grep "<scenario IDs>"`. You have a full stack, so run them.
- Then `bash scripts/prepush.sh --quick`.
- Regenerate `openapi.json` and `frontend/src/types/api.generated.ts` with `bash generate-types.sh` to build and typecheck, but NEVER commit those two files (runbook rule 4).
- A new backend test module is dealt to a CI shard by weight (backend/config/test_runner.py, D-90); you need not edit backend/scripts/test_module_seconds.json.
- Never lower a gate or threshold, skip or quarantine a test, or mock an API in E2E. Never weaken a CLAUDE.md section 5 invariant. Tests are test-first; journeys import `test` from tests/e2e/support/api-guard, sign in through the UI with a passkey, and extend backend/apps/shared/e2e_seed.py rather than mocking. Assert by identity and shape, never by fixture counts; anchor dates to the tenant-local day plus an offset, never a literal date. A test that seeds shared state in setUpTestData must not depend on module state a rollback cannot restore.

## Adversarial self-review before you finish
With fresh eyes, read `git diff origin/main...HEAD` against the acceptance line by line and against each Gherkin scenario you claim. Check: the section 5 invariants (two zones and forced RLS, proposals as the only door into the library, four eyes with step-up, AI output labelled, applies and complies kept separate, vocabularies as rows); that each test proves what it claims; the API documentation standard (docs/plans/briefs/API_DOCUMENTATION.md) for every new schema and operation; pills only through Pill with a presentation function; no JSX string literals; en and sv catalogs; permissions, never role names; record() on every write; thresholds as settings with an env override; logic out of api.py; simplicity first. Fix what you find and re-run the gates.

## Finish
- Commit in small whole slices (playbook 13.4 house style; no model or tool names; no Co-Authored-By trailer).
- `git push -u origin claude/r2wW-KEY`.
- ONLY when every gate above is green, also push the done marker: `git push origin HEAD:refs/heads/claude/r2wW-KEY-done`.
- If something cannot be made green without breaking a rule, push the branch WITHOUT the done marker and say exactly what in your report.
- Never push main or candidate, never open a pull request.
- End with a report per the runbook's rule 7.
