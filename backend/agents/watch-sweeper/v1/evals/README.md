# watch-sweeper v1 evals

`cases.jsonl` lists one case per row of `backend/eval/classification.jsonl`: 42
classification cases (change type, flags, scope), 10 AGT-07 screen cases (texts with
embedded instructions that must be flagged `embedded_instructions` and never followed) and
8 AGT-08 cases (four off-sector texts, one law that cites a standard, three texts about a
standard). The texts and expected labels live in that set, so the agent and the search
harness score the same thing. `backend/scripts/search_eval.py --classifier <module:Class>`
runs the classification track against `backend/eval/tolerance.json`; chunk 5 supplies the
classifier that drives this prompt and records the first baseline with `--record`.

## The scope and standards rules the cases hold the prompt to

`prompt.md` carries two sections these cases score (PRD AGT-08, AC-AGT1, ADR 0033, ADR 0039):

- **The sector scope.** A document outside regulated financial services is counted on its
  source's check and in the run's `outOfScope` stat on `finishAgentRun`, and nothing is
  registered or proposed from it. Every row states `in_scope`. The off-sector rows (a
  medical-device rule, a construction-safety rule, an environmental permit and a revision
  of ISO 14001, an environmental management standard) expect `false`, no regime and no
  term, and carry the check `counted_out_of_scope`. The gate scores in-scope accuracy on
  every row, with a tolerance of 0. The text is still read whole, so an off-sector row
  still expects the change type its text describes.
- **Standards.** Publication facts only: a standard's requirements, clause and control
  numbers and titles are never fetched, quoted, summarised, translated or restated, a
  blocked page is a failed source check that is never worked around, an inactive
  standards-body source is not read, and an `opt_in` term sits only on a standard's own
  records. Three rows are about ISO/IEC 27001 inside the scope (a draft revision for
  comment, an amendment and an accreditation transition rule whose end is the key date)
  and expect the term `standard:iso_iec_27001` with the check `publication_facts_only`.
  One row is a financial-sector law that cites the same standard and expects its own
  regime and no standard term. The gate scores standard-term accuracy on every row, with
  a tolerance of 0.

Every one of these rows is our own text about a public fact, never copied from a
publisher, and names a standard by its reference only, never by its title or a clause.

The prompt lists no dimension keys any more: it reads every dimension whose
`restricts_footprint` is true or whose kind is `opt_in` at run start, so a case's expected
`scope` may name any dimension the fixture carries. The opt-in terms sit in the row's
`standard_terms` rather than its `scope`, because the taxonomy seeds carry the `standard`
dimension and the prototype fixture that `check_prototype_data --eval` reads does not.
