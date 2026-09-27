# ADR 0060 — One person closes a case that needs no work, audited

**Date:** 2026-09-25 · **Status:** accepted (Alex, 2026-09-20: "One person, audited", `OWNER_RECOMMENDATIONS.md` item 15; D-92; PRD CAS-02, CAS-06; built by `c9-triage`)

## Context

A bank's case for a regulatory change leaves the workflow by one of three exits: a
dismissal before triage ("this does not concern us"), a sign-off by a second person with a
passkey after the work is done (CAS-06), or a close without action when the change applies
but nothing has to change, or the assessment found it does not apply. The design has the
third as `POST /changes/{changeId}/close` with `closeReason` `no_action`, and `PUT
/changes/{changeId}/assessment` with `applies = no` closing as `not_applicable`, both behind
the permission that works a case.

`CLAUDE.md` section 5 puts four eyes and a step-up on "sign-off" and does not say whether
such a close is one. It is the one place a single person can take a regulatory change out
of the workflow and into `closed`, so the question (q-case-close) went to Alex with three
options: A, a second person for every close; B, one person, audited; C, one person, but the
close waits in a queue for a second look.

## Decision

Option B. A case in `assigned` or `assessing` is closed on one person's word by anyone whose
roles hold `cases.work`:

- **A reason key is required**, from the bank's own `close_reason` list, and only a row of
  the fixed kind `no_action` or `not_applicable` closes this way (`state.ONE_PERSON_CLOSE`).
  A `signed_off` reason is refused with 409 `four_eyes_violation`: it says a second person
  confirmed the work, which only the sign-off route may say.
- **The audit row names the person and the reason's key**, through `record()` in the same
  transaction as the move, and a `case_transition` row names the person and carries the
  optional note. The note is tenant content: it stays on the case (`closed_note`) and its
  ledger row, and never reaches an audit value, a log or a model.
- **It can be undone.** `POST /changes/{changeId}/restore` brings a one-person close back
  to `new`, clearing the close from the case while the ledger and the audit trail keep it.
  A signed-off close stays final: the state machine's `restorable_close` guard reads the
  close reason's kind.
- **No third door.** The route leaves only `assigned` and `assessing`. The machine also
  draws `signoff` to `closed`, and that edge's guard reads who asked for sign-off, not the
  reason, so the route refuses a case in `signoff` with 409 `invalid_transition` rather than
  let someone other than the requester close it without the approval's step-up. A test
  over the machine's tables pins the only edges into `closed` to these two and sign-off.
- **No step-up.** Playbook 4.2 does not list the close, and the passkey stays where work is
  claimed to be done.

## Consequences

- Four eyes and the step-up stay on sign-off, which is where a bank claims it did the work;
  a close that claims no work was needed is one accountable person's judgement, visible in
  the audit trail and in the case's history, and reversible.
- A bank that wants a second look at every such close has no switch for it in R2. Option C
  would be the shape if one is asked for.
- The `applies = no` path in `saveAssessment` closes under the same rule when
  `c9-assessment` builds it; it reuses the same reason kinds and the same restore.
- "Applies" and "we comply" stay separate: closing a case says nothing about the register.
