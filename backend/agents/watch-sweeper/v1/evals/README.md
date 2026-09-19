# watch-sweeper v1 evals

`cases.jsonl` lists one case per row of `backend/eval/classification.jsonl`: 42
classification cases (change type, flags, scope) and 10 AGT-07 screen cases (texts with
embedded instructions that must be flagged `embedded_instructions` and never followed).
The texts and expected labels live in that set, so the agent and the search harness
score the same thing. `backend/scripts/search_eval.py --classifier <module:Class>` runs
the classification track against `backend/eval/tolerance.json`; chunk 5 supplies the
classifier that drives this prompt and records the first baseline with `--record`.

## The scope and standards rules the cases hold the prompt to

`prompt.md` carries two sections these cases score (PRD AGT-08, ADR 0033, ADR 0039):

- **The sector scope.** A document outside regulated financial services is counted on its
  source's check and in the run's out-of-scope stat, and nothing is registered or proposed
  from it. The off-sector rows expecting `in_scope` false, and the law that cites a
  standard and expects no standard term, arrive with `f03-T46`; `f03-T47` scores them as
  in-scope accuracy and standard-term accuracy, each with its own tolerance.
- **Standards.** Publication facts only: a standard's requirements, clause and control
  numbers and titles are never fetched, quoted, summarised, translated or restated, a
  blocked page is a failed source check that is never worked around, an inactive
  standards-body source is not read, and an `opt_in` term sits only on a standard's own
  records. The standards rows (a new edition with a transition key date, an accreditation
  transition rule and a draft for comment) arrive with `f03-T46`, authored by us and never
  copied from a publisher.

The prompt lists no dimension keys any more: it reads every dimension whose
`restricts_footprint` is true or whose kind is `opt_in` at run start, so a case's expected
`scope` may name any dimension the fixture carries.
