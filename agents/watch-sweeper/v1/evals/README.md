# watch-sweeper v1 evals

`cases.jsonl` lists one case per row of `backend/eval/classification.jsonl`: 42
classification cases (change type, flags, scope) and 10 AGT-07 screen cases (texts with
embedded instructions that must be flagged `embedded_instructions` and never followed).
The texts and expected labels live in that set, so the agent and the search harness
score the same thing. `backend/scripts/search_eval.py --classifier <module:Class>` runs
the classification track against `backend/eval/tolerance.json`; chunk 5 supplies the
classifier that drives this prompt and records the first baseline with `--record`.
