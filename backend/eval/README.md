# Evaluation sets (SRC-05, AC-SRC1, AGT-07, playbook 16)

`scripts/search_eval.py` is a CI gate. It scores two evaluators against the labelled
sets here and compares the result with the recorded baseline within the tolerance.

| File | Holds | State |
|---|---|---|
| `retrieval.jsonl` | 53 labelled questions over the prototype corpus, en 16, sv 16, da 7, nb 7, fi 7 | Filled (chunk 3 data work) |
| `classification.jsonl` | 42 labelled change texts (8 from the prototype, 34 authored Nordic variants) plus 10 texts with embedded instructions for the AGT-07 screen | Filled |
| `baseline.json` | The last accepted value of every metric, per track, with who recorded it and when | `recorded: false`. The retrieval track is wired and **not yet recorded**: see below |
| `tolerance.json` | How far a metric may fall under the baseline before the gate fails, with the rationale | Filled |
| `tests_scoring.py` | Unit tests for the scoring and gate logic, run by `search_eval.py --self-test` | Filled |

Lines starting with `#` are comments. The corpus is the obligations, provisions and
changes of `apps/library/fixtures/prototype_data.json`, referenced by stable key, so
`apps/library/fixtures/check_prototype_data.py --eval` cross-checks that every key a
set names exists.

## Row shapes

Retrieval: `{"id", "language", "query", "expected": [stable keys], "match_kind":
"keyword" | "concept" | "both", "as_of"?: date, "note"?}`. Every expected key is
relevant; recall@10 is the share found in the top ten and MRR the reciprocal rank of the
first one. An empty `expected` is a question the library has no answer to (SRC-S12): both
metrics score it 1 when the retriever returns nothing at all and 0 when it returns any
hit, however far down. `match_kind` records what AC-SRC1 expects to win: identifiers such as
"FFFS 2017:2" by keyword, phrasing such as "nudging in onboarding" by concept. The harness
reports the metrics per match kind so a keyword or vector regression is visible on its
own. `as_of` means the version effective on that date is the one expected; the
retriever receives it as a `date`.

Classification: `{"id", "language", "jurisdiction", "authority", "source", "text",
"expected": {"change_type", "flags", "scope": {dimension: [term keys]}, "risk_flags"},
"injection", "injection_kind"?, "note"?}`. Keys are vocabulary keys from the fixture.
Scoring per field: change type exact, flags set equality, scope the mean Jaccard over the
dimensions the expectation names (empty matches empty), screen the set equality of
`risk_flags`, where the ten injection rows expect `["embedded_instructions"]` and every
other row expects `[]`. Metrics are reported per language and split into clean and
injection rows.

## The evaluator interface

```python
class Retriever(Protocol):
    name: str          # recorded in baseline.json
    is_mock: bool      # a mock can score but never record or satisfy a recorded baseline
    def search(self, query: str, lang: str, as_of: date | None) -> list[str]: ...  # stable keys, best first

class Classifier(Protocol):
    name: str
    is_mock: bool
    def classify(self, text: str) -> dict: ...  # {"change_type", "flags", "scope", "risk_flags"}
```

Name a real one as `module:Class` (constructed with no arguments; it may set up Django
itself). The harness puts `backend/` on the path, so a module of the Django project can be
named. A real evaluator needs the project's dependencies, so run it through `run.sh`:

```
./run.sh run python scripts/search_eval.py --retriever apps.search.eval:Retriever --classifier apps.agents.eval:Classifier
./run.sh run python scripts/search_eval.py ... --record     # first real run: writes the baseline
python scripts/search_eval.py --self-test                   # the unit tests, plain Python
```

Without flags the harness uses the mocks, which answer only when every row of a set
carries a `predictions` field (tests and dry runs; the committed sets carry none).

## The retriever: wired, not yet recorded

`apps.search.eval:Retriever` asks every question through `hybrid.run_search`, the statement
`POST /search` runs, over the library `seed_demo` loads, indexed by `reindex_library` and
embedded by the sweep, for a bank whose scope holds the whole library. It answers with the
stable keys of the hits, best first, from the widest page the API serves.

- **Its database is never the development one.** Inside the test runner (SRC-S8) it uses
  the runner's throwaway database. From the command line it sets up Django on
  `config.test_settings` (unless `DJANGO_SETTINGS_MODULE` names another), creates
  `test_<database>_search_eval` with Django's own test machinery, migrates it from zero,
  seeds it, and drops it when the process ends. It takes about half a minute.
- **`is_mock` is true when any adapter in the chain is a mock**, the embedder or the
  reranker, and `name` names both (`... (embedder mock, reranker none)`), so the report
  says which chain ran. `none` is not a mock: it is the keyword leg and the fused order,
  which is what a deployment has before D-09 names a model.
- **Today it is a smoke check and asserts nothing about quality.** Under the test settings
  the embedder is always the mock, so its scores prove that the harness, the retriever and
  the corpus fit together; `--record` refuses them, no threshold is derived from them, and
  none is written anywhere.
- **Nobody has recorded the retrieval track, so a retrieval regression fails no build yet.**
  Every run says so (`no baseline is recorded for retrieval ...`). It is recorded once, by
  the task that chooses the embedder against this set (`c7-embedder-selection-baseline`),
  when D-09's key arrives: that run has no mock in its chain, records with `--record` in
  the same commit as the change that earned the numbers, and from then on CI must run the
  gate with `--retriever` and the real provider configured, or the recorded track fails
  as "no real evaluator ran". Until then `docs/TODO_FOR_alex.md` carries the gap.

## Status rules

- A track (retrieval, classification) whose baseline is not recorded passes with
  "not available yet" when no evaluator ran, and every run names the unrecorded tracks.
  This is the state until a real evaluator of each track records.
- `--record` writes the scored real tracks into `baseline.json` and refuses the mock.
  Record in the same commit as the change that earned the numbers; never edit them by hand.
- Once a track is recorded, a run without a real evaluator fails loudly, naming who
  recorded the baseline and when, and a run under baseline minus tolerance fails naming
  the metric. The screen tolerance is 0: an injection case that stops being flagged is a
  security regression (AGT-07).
- Exit 0 passes, 1 fails; malformed sets, a missing file or a bad evaluator spec fail
  with the file or spec named.

The five content languages are what checks the embedding model choice (D-09): the Danish,
Norwegian and Finnish questions target the same obligations as the English and Swedish
ones, so a monolingual embedder scores visibly worse on them.
