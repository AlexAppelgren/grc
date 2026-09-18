# Kick-off prompt for the Claude Code session

Paste everything below the line as the first message.

---

You are building Compliance Watch (brand: bleqq) in this repository, from an
empty app to a product I can deploy to Railway for testing. Everything you
need is in the repo.

**Read first, in this order:** `CLAUDE.md`, `docs/PLAYBOOK.md`, `PRD.md`,
`docs/DECISIONS.md`, `docs/plans/Solution_Design.md`,
`docs/plans/Build_Plan.md`, `docs/inputs/README.md` and
`docs/inputs/INPUT_DELTAS.md`, then `docs/inputs/openapi.yaml`, `schema.sql`
and `data-model.md`, then `design/README.md`,
`design/system/pills-and-labels.md` and the prototype in
`design/prototype/index.html`. Open the prototype in a browser and click
through it, on a phone-sized viewport too: it is the contract for flow,
wording, labels and pills. If `docs/inputs/schema.sql` or `data-model.md` is
missing, stop and tell me.

**Precedence when sources disagree:** `PRD.md`, then `docs/DECISIONS.md` and
ADRs, then `INPUT_DELTAS.md`, then the other inputs, then playbook
conventions. The prototype decides look and flow, never rules.

**Then do this:**

1. Run Phase 0 from the playbook in full, including the structural guards,
   the CI workflow, the token pipeline from Green with `brand.css`, the `Pill`
   component with its gallery, the phonetic logo from `design/brand/`, the D-04
   spike, and one ADR per entry in `docs/DECISIONS.md`. Pin exact dependency
   versions and record them. Do not stop after Phase 0.
2. Work through `docs/plans/Build_Plan.md` chunk by chunk, in order. For every
   requirement follow the twelve-step loop in playbook Section 3. A chunk is
   done only when its definition of done holds, including its E2E journeys
   against the real stack.
3. After each chunk: update `docs/plans/IMPLEMENTATION_STATUS.md`, run the
   pre-push checklist (playbook Appendix D), commit and push directly to
   `main` with a message per playbook 13.4, and give me five lines: what a
   user can now do, what you cut and why, what landed in
   `docs/TODO_FOR_alex.md`, which defaults from `DECISIONS.md` you relied on,
   and the next chunk. Then continue without waiting for me.

**How to work:**

- Test locally on PostgreSQL 16 with pgvector and Redis. Use
  `docker compose up -d db redis`. If Docker is not available in this
  environment, install PostgreSQL 16 with the pgvector package and Redis
  locally and point the settings at them. There is no SQLite fallback.
- Build the domain model from `docs/inputs/` as corrected by
  `INPUT_DELTAS.md`. Do not invent a new model and do not execute
  `schema.sql`: Django migrations own the schema.
- Use the `green-design-system` MCP server in `.mcp.json` for token names and
  component documentation. Never recall them.
- Before implementing any external provider or API (WebAuthn library,
  Anthropic, embeddings, Managed Agents, Railway specifics), fetch its
  current documentation and record what you relied on in
  `docs/plans/Verification_Log.md`.
- When a decision is open, take the default in `docs/DECISIONS.md`, note it in
  the commit body and keep building. Stop and ask me only when a product
  invariant in playbook 13.2 would be weakened.
- Screens the prototype lacks are listed in `design/README.md`. Design each as
  a card in the prototype's language first, commit the card, then build it.
- Never lower a gate, skip or quarantine a test, mock an API in E2E, or
  inject a session in a journey. If a gate is wrong, fix the gate and say why.
- Do not deploy. Keep the Dockerfiles, the entrypoint, `.env.example` and
  `docs/runbooks/RAILWAY_DEPLOY.md` accurate, so I can deploy `main` whenever
  a chunk lands. Tell me when R1 (chunks 0 to 7) is ready for its first
  deploy.
- You may use sub-agents for parallel work inside a chunk. Give each the
  mandatory E2E rules and the invariants from `CLAUDE.md`.

Start now with Phase 0.
