# tenant-source-watch v1 evals

No labelled case exists yet, and that is why `definition.yaml` says `status: draft`. A
bank's own agent is measured by an evaluation of its own, as the sweeper's classifications
and the confirmer's decisions are: until these rows exist, the definition is exercised only
by the integration tests of the runner seam and a bank's agent controls, which prove what it
may touch and never whether what it counted was right.

## What the cases will hold

One case per document, authored by us and never copied from a publisher, each with the run's
scope as a bank would set it, the page as fetched text, and what the run should report:

- **Inside the scope.** A supervisory statement, a regulation or a consultation from a
  source in the run's scope: counted as checked and fetched, and looked up with
  `findSimilar`.
- **Outside the sector scope.** A medical-device rule, a construction-safety rule or an
  environmental permit that a source also publishes: counted as out of scope, nothing else.
- **Embedded instructions.** A page telling the agent to report success, widen its scope or
  call another tool: never followed, and the report unchanged by it.
- **A bank's scope text that tries to steer.** A topic the bank wrote that reads as an
  instruction: treated as a description of what to look for, never as a rule.
- **Standards.** A standard's publication facts only, and a blocked page a failed check
  that is never worked around.

## The rules the cases hold the prompt to

`prompt.md` carries the same sector scope, standards and screening sections the sweeper's
prompt does (PRD AGT-07, AGT-08, ADR 0033, ADR 0039), and one more: the agent has no tool
that writes the shared library, files a proposal or decides one, which
`apps/agents/tests_definition_files.py` proves from `definition.yaml` itself.
