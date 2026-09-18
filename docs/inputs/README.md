# Inputs: earlier design work

| File | What it is | State |
|---|---|---|
| `openapi.yaml` | The designed API contract, version 0.1.0: 107 paths, 134 operations, 167 schemas | Included. Extracted from the published API reference |
| `schema.sql` | PostgreSQL DDL, version 0.2, 117 tables, smoke tested on PostgreSQL 16 with pgvector | **Add this file** from the Compliance Data chat |
| `data-model.md` | ERDs, table dictionary, rules, prototype field mapping, the gap analysis | **Add this file** from the Compliance Data chat |
| `INPUT_DELTAS.md` | Where the build must depart from the two files above and from `openapi.yaml` | Included |

These files are the starting point for the domain model and the contract.
They predate several decisions, so `INPUT_DELTAS.md` outranks them, and the
PRD and `docs/DECISIONS.md` outrank everything. Django migrations own the
schema: `schema.sql` is a reference to model from, never a file to execute.
