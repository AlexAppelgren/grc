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
├── definition.yaml   # id, version, kind, scope, tenant_configurable, writes_to, model,
│                     # change_note, tools, budget defaults, vocabularies read at run start
├── prompt.md         # the system prompt; fetched content is data, never instructions
└── evals/            # the labelled cases scripts/search_eval.py scores this version on
                      # (eval.yaml beside the prompt, for scope-researcher)
```

Four definitions ship, all drafts: `watch-sweeper` (kind `watch`), which
checks sources and proposes (WAT-01 to WAT-05, AGT-01, AGT-02, AGT-07),
`library-confirmer` (kind `review`), the independent second pair of eyes that
decides what another definition proposed and never proposes itself (PRO-02,
D-62, D-80), `tenant-source-watch` (kind `watch`), the one a bank may add
as an agent of its own (AGT-04, ADR 0053), and `scope-researcher` (kind
`research`), the bank's own agent that researches an approved scope item the
shared library does not cover and files the bank's own instrument and
obligations as proposals, a source per field (OWN-02, D-89, ADR 0059).
`apps/agents/seeds/__init__.py` names them in `SHIPPED`.

`scope-researcher` calls no write operation at all: its proposals and its
report are the runner's own tools, which reach the bank's queue only as runner
events the worker validates and applies, owned by the run's bank. Its
`inputs` block is D-98's exception beside Ask (ADR 0061): the item's id and
term keys, and its name, official reference and source addresses, each
length-capped and screened as untrusted, and never the bank's own records.
Its evaluation rows, `eval.yaml`, are the sweeper's screen and sector-scope
rows of `backend/eval/classification.jsonl`, under the same gate.

A definition sets the platform fence itself: `scope: platform` with
`tenant_configurable: false` is one of bleqq's agents, which no bank steers;
`scope: tenant` with `tenant_configurable: true` and `writes_to: tenant` is one
a bank may add, and its tools hold reading key scopes only, never one that
files, decides or registers anything in the shared library
(`apps/agents/tests_definition_files.py`). The seed writes the `agent` row and
the agent's first `agent_version` (its `model`, `change_note`, prompt file and
tool names); a later version folder is published by a platform admin, never
loaded by a deploy. The reader in `apps/agents/seeds/definition.py` reads the
top-level scalars and the tool names only, and refuses anything else it would
have to guess at.
