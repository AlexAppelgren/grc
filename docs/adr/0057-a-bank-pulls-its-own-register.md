# ADR 0057 — A bank may pull its own register into its own agent; we still send nothing

**Date:** 2026-09-20 · **Status:** accepted (owner decision, 2026-09-20; D-68, D-72, amends D-07, PRD 0.5 ACC-04, ACC-08)

## Context

D-07 reads: "No tenant-zone text is sent to a model except the question typed
into Ask, which a tenant can switch off." It was written to keep a bank's
confidential judgement out of embeddings and out of a provider's US inference
region until the EU path is contracted, and D-10 holds the same line for the
search index.

Alex's answer on what a bank's own agent may read goes straight through it: "The
agent can access anything that the bank has put as it applies to them." A bank's
register decisions are tenant-zone text. A bank's coding agent is a model. Read
literally, D-07 forbids the feature.

Reinterpreting D-07 quietly would be the wrong way to resolve that, because the
invariant it protects is real and the next person to read it would not know it
had moved.

## Decision

D-07 is amended to say what it always meant: **we** send no tenant-zone text to a
model except Ask's question. A bank pulling its own register into its own agent
is a different act, and it is allowed, under two switches.

- **What is different.** The bank is the controller of its own data. It fetches
  it over an authenticated channel it opened, to an agent it runs, on
  infrastructure it chose. We are not the sender, we choose no provider and no
  region for it, and D-07's EU-inference reasoning does not reach it. What we owe
  is that the door is deliberate, narrow, approved by the bank and logged.
- **The tenant switch.** Tenant reach is off until two different people holding
  `security.manage` request and approve it, each with a passkey, never both by the
  same person. This is the four eyes that exports and tenant exit already carry,
  for the same reason: it is an egress decision about the bank's confidential
  judgement. Turning it off stops every entry at once.
- **The per-entry toggle.** Under it, a tenant admin enables reach on a named
  entry behind a step-up. With the tenant switch off, every entry is library-only
  whatever its own setting says, and every register route answers 403
  `tenant_reach_off`.
- **What still never leaves.** Gaps, cases and their assessments, comments and
  mentions, evidence of any kind, the audit log, and a tenant's private records.
  D-57 is untouched: a private record is never sent to a model, and a bank's own
  agent is a model.
- **D-10 is untouched.** Nothing here indexes or embeds tenant content. The
  what-applies call ranks in memory over rows the scope already selected.
- **The access log.** Every call records the credential, the entry, the person
  where the credential is personal, the tool, the filters, the record count, the
  scope applied and the timing. Never the content, never the question text. It is
  visible to the tenant on the entry and it is what a vendor review will ask for.

## Why

The distinction between sending and being read from is not a lawyer's trick, it
is the difference between us choosing a processor and the bank choosing one. Our
obligation is to make the door explicit, bounded and revocable, and to keep the
record of who opened it.

Putting four eyes on the tenant switch rather than on each entry puts the
ceremony where the decision actually is. Whether this bank lets its register
reach its own agents at all is a policy question for two senior people. Which of
its agents gets it is an operational question for an admin, and asking two people
every time would make the switch something a bank works around with one
over-broad entry.

## Consequences

- The tenant switch lives in `apps/governance` with the other four-eyes requests.
  `tenant_reach_off` is an RFC 9457 code the client branches on.
- The assurance pack (NFR-04) gains this door: what may leave, who approved it,
  and the access log that proves what did.
- Open, and in `docs/TODO_FOR_alex.md`: a bank running its agent on a model
  endpoint outside the EU is the bank's decision, and the first procurement review
  will ask what we do about it. Proposed: state it plainly in the assurance pack,
  record the approval, and do not police the endpoint.
- **Reversal.** Refusing `tenant:read` on every route leaves a library-only
  reader and restores D-07 word for word.
