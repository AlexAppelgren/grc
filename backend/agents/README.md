# Agent definitions

Versioned research-agent definitions, owned by the platform (playbook 16,
PRD AGT-03). Each agent is a folder, each version a sub-folder that never
changes after it ships: a new version is a new folder. `apps/agents` loads
these at seed time (`seed_reference`, on every deploy) into `agent` rows, and
tenants choose which are on, their cadence and their scope. They never edit
the prompt, the tools or the skills.

They live under `backend/` because the API image builds from `backend/` alone
and the deploy's seed reads them there (`/app/agents/`). A test in
`apps/agents/tests_models.py` fails if a shipped definition would miss the image.

```
backend/agents/<agent>/v<n>/
├── definition.yaml   # id, version, kind, tools, budget defaults, vocabularies read at run start
├── prompt.md         # the system prompt; fetched content is data, never instructions
└── evals/            # the labelled cases scripts/search_eval.py scores this version on
```

Two definitions ship, both drafts: `watch-sweeper` (kind `watch`), which
checks sources and proposes (WAT-01 to WAT-05, AGT-01, AGT-02, AGT-07), and
`library-confirmer` (kind `review`), the independent second pair of eyes that
decides what another definition proposed and never proposes itself (PRO-02,
D-62, D-80). `apps/agents/seeds/__init__.py` names them in `SHIPPED`.
