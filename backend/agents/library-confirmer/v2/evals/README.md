# library-confirmer v2 evals

No labelled case exists yet, and that is why `definition.yaml` says `status: draft`. A
confirming agent's decisions are measured by an evaluation of their own, as the sweeper's
classifications are (D-62, ADR 0054, `docs/plans/briefs/CHUNK5_TASKS.md`): until these
rows exist, an agent's approval is exercised only by the integration tests of the
proposal queue (PRO-S13, AGT-S15), which prove who may decide and never whether the
decision was right.

## What the cases will hold

One case per proposal, authored by us and never copied from a publisher, each with the
proposal as the queue returns it, the pages it cites as fetched text, and the decision
expected:

- **Approve.** Every changed value is stated by the page cited for it, as proposed.
- **Correct.** A sourced field says something other than its source; the expected
  `payloadOverrides` bring it back to the source, and touch no field the proposal did not
  source.
- **Reject.** A value no cited page states; a page that refuses the fetch (a 403, a
  paywall, a challenge page); a proposal that restates a standard's requirements or its
  clause or control numbers; a law given a standard's term; a cited page carrying embedded
  instructions to approve and nothing that supports the proposal. Each expects the
  `rejection_reason` key it should name.
- **A list value or a term.** A new value whose key and labels fit the list and repeat no
  row (approve); one repeating a live row under another key (reject, `duplicate`); a
  relabel that keeps the concept (approve) or changes what the key means (reject); a merge
  into a live row meaning the same thing (approve); a retire that removes a concept no
  other row carries (leave open). None is ever corrected.
- **Leave open.** A proposal outside the sector scope, or one whose sources contradict each
  other; a label the agent cannot read with confidence in its language; a kind it does not
  recognise: never approved, corrected or rejected, left in the queue for a person.

## The rules the cases hold the prompt to

`prompt.md` carries the same sector scope and standards sections the sweeper's prompt
does (PRD AGT-08, ADR 0033, ADR 0039), from the other side of the queue: it confirms only
what the proposal's sources support, it never fetches or restates a standard's text, a
source it cannot fetch is a rejection with a reason and never a guess, and it never
decides a proposal of its own definition, which the `proposal_four_eyes` constraint
refuses anyway.

## Scoring

The cases will be scored by the same harness as the sweeper's classification track,
`backend/scripts/search_eval.py`, against a tolerance of their own in
`backend/eval/tolerance.json`: decision accuracy (approve, correct, reject, leave open)
and, for a rejection, whether the expected reason was named. The track, the rows and the first
baseline arrive together; publishing this definition waits for all three.
