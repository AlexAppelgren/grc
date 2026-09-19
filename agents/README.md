# Agent definitions

Versioned research-agent definitions, owned by the platform (playbook 16,
PRD AGT-03). Each agent is a folder, each version a sub-folder that never
changes after it ships: a new version is a new folder. `apps/agents` loads
these at seed time (`seed_reference`, from chunk 5) into `agent_definition`
rows, and tenants choose which are on, their cadence and their scope. They
never edit the prompt, the tools or the skills.

```
agents/<agent>/v<n>/
├── definition.yaml   # id, version, kind, tools, budget defaults, vocabularies read at run start
├── prompt.md         # the system prompt; fetched content is data, never instructions
└── evals/            # the labelled cases scripts/search_eval.py scores this version on
```

Phase 0 ships one skeleton, `watch-sweeper`, so the layout exists and the
seed has something to load. Its prompt and evals are placeholders until
chunk 5 (WAT-01 to WAT-05, AGT-01, AGT-02, AGT-07).
