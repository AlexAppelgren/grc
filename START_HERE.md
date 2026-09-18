# Compliance Watch kick-off package

Everything the Claude Code session needs to build the product from an empty
repository. Unzip it at the root of a new repo.

## Steps

1. Create an empty private GitHub repository (suggested name
   `bleqq-compliance`) and unzip this package at its root.
2. **Add two files** from the Compliance Data chat to `docs/inputs/`:
   `schema.sql` and `data-model.md` (version 0.2, 117 tables). I could not
   reach that chat's files from here. `openapi.yaml` is already included.
3. Commit and push to `main`.
4. Open the repo in Claude Code with permission to push to `main`. Approve the
   `green-design-system` MCP server from `.mcp.json` when asked.
5. Paste the prompt from `KICKOFF_PROMPT.md`.
6. Work through the first block of `docs/TODO_FOR_alex.md` while it builds:
   the Railway project, a test host for the passkey RP ID, a mail sender, an
   embeddings key.

## What is in here

| Path | Purpose |
|---|---|
| `KICKOFF_PROMPT.md` | The first message for the session |
| `CLAUDE.md` | Bootstrap agent context: read order, precedence, invariants, working agreement |
| `PRD.md` | Requirements with IDs, acceptance criteria, golden-path journeys, the permission matrix, the release plan |
| `docs/PLAYBOOK.md` | Your playbook, adapted: Postgres everywhere, two zones, passkey-only sign-in, vocabularies as rows, pills and labels, agents, five languages, bank assurance, one branch for now |
| `docs/DECISIONS.md` | Seventeen open decisions, each with the default the build uses, so it never waits |
| `docs/TODO_FOR_alex.md` | What needs you, ordered by what blocks testing |
| `docs/plans/Solution_Design.md` | Architecture, zones, modules, key mechanics, control mapping |
| `docs/plans/Build_Plan.md` | Fifteen chunks, each a usable slice. Chunks 0 to 7 are R1 and the first deploy |
| `docs/plans/Verification_Log.md` | What was checked against sources, and what was not |
| `docs/inputs/` | `openapi.yaml` (134 operations), `INPUT_DELTAS.md`, and the slot for your two files |
| `docs/runbooks/RAILWAY_DEPLOY.md` | Services, database roles, variables, first run |
| `design/prototype/index.html` | The published prototype, as the design contract |
| `design/system/pills-and-labels.*` | The pill and label contract, and a rendered card in light and dark |
| `design/brand/` | The phonetic wordmark `[blɛkː]`, the favicon, brand layer placeholders |
| `.mcp.json` | Green Design System MCP server for token and component lookups |

## Three things that differ from what we discussed

- **UI foundation.** Green's own agent instructions require its text and
  layout components everywhere, which would fight the prototype's custom
  components and Tailwind. The default is now our own components on Green
  tokens, with Green components only where a Phase 0 spike proves them
  (D-04).
- **Auth library.** `webauthn` with thin endpoints of our own, because the
  sign-in rules are few, specific and product invariants (D-03).
- **Branching.** One branch during the build, as you asked. The playbook
  switches to `staging` and `main` before the first real tenant (D-15).
