# Compliance Watch (brand: bleqq)

A compliance inventory and regulatory watch platform for enterprise banks in
the Nordics. Research agents find and propose, people decide, every decision
is logged. The full scope lives in `PRD.md`; requirement IDs refer to it. Read
the relevant module before building any feature.

This is the bootstrap version of this file. Phase 0 expands it from
`docs/PLAYBOOK.md` Appendix A.

## Read in this order
1. `docs/PLAYBOOK.md` (how we build, what never bends)
2. `PRD.md` (what we build)
3. `docs/DECISIONS.md` (the default for every open decision)
4. `docs/plans/Solution_Design.md`, `docs/plans/Build_Plan.md`
5. `docs/inputs/README.md`, then `INPUT_DELTAS.md`, then the inputs
6. `design/README.md`, `design/system/pills-and-labels.md`, the prototype

## Precedence
`PRD.md` > `docs/DECISIONS.md` and ADRs > `docs/inputs/INPUT_DELTAS.md` >
other inputs > playbook conventions. The prototype decides look, wording and
flow, never rules.

## Non-negotiable
- Two zones. Tenant tables under forced row-level security. The app role
  cannot bypass it.
- Proposals are the only door into the library. Agents never edit it.
- Nothing overwritten: versions with effective dates. Audit and outbox rows
  in the same transaction as every write, through `record()`.
- Four eyes with a passkey step-up on approvals.
- No passwords. The emailed code works once, for enrolment, never as a
  fallback.
- Enums in code are for kinds only. Types, statuses, tags and reasons are
  rows an admin manages. The API returns `key` and `kind`.
- Six pill tones, chosen by slot or kind, never by a person. Pills only
  through `Pill`. No string literals in JSX.
- Tenant content never reaches logs, Sentry or an unapproved model endpoint.
- PostgreSQL with pgvector everywhere. There is no SQLite.

## Working agreement
- Whole slices, chunk by chunk through `Build_Plan.md`. Commit directly to
  `main`. Run the pre-push checklist (playbook Appendix D) before every push.
- Never lower a gate, skip a test or mock an API in E2E.
- Open decision: take the default in `docs/DECISIONS.md`, say so in the
  commit body, keep going. Product invariant at stake: stop and ask.
- Anything needing a person goes to `docs/TODO_FOR_alex.md`.
- Anything relied on from the outside world goes to
  `docs/plans/Verification_Log.md` with its source. Fetch provider docs, do
  not recall them. Use the Green MCP server for tokens and components.
- The owner deploys. Keep Dockerfiles, the entrypoint and
  `docs/runbooks/RAILWAY_DEPLOY.md` true, and never deploy yourself.
