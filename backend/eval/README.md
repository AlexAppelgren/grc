# Evaluation sets (SRC-05, playbook 16)

| File | Holds | Filled in |
|---|---|---|
| `retrieval.jsonl` | One JSON object per line: `{"id", "language", "question", "expected_chunk_ids": [...]}` | chunk 7 |
| `classification.jsonl` | One per line: `{"id", "language", "text", "change_type", "flags": [...], "scope": [...]}` | chunk 7 |
| `baseline.json` | The last accepted value of every metric | chunk 7, then on every accepted improvement |
| `tolerance.json` | How far a metric may drop before `scripts/search_eval.py` fails | chunk 7 |

Lines starting with `#` are comments. The sets cover all five content languages
(`en`, `sv`, `da`, `nb`, `fi`) once filled, which is what checks the embedding model
choice (D-09).
