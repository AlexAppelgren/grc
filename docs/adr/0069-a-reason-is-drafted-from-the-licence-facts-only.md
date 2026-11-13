# ADR 0069 — A reason may be drafted by AI from the licence facts only, the third exception beside Ask

**Date:** 2026-11-13 · **Status:** accepted (Alex, 2026-11-13, in chat, offered "Yes, from the licence facts only", "Yes, from the typed text too" and "Not now": "Yes, go ahead and fix it, u dont need my approval to get things right"; D-143; amends D-07; follows ADRs 0057 and 0061)

## Context

D-07 sends a model no tenant-zone text except two named exceptions: the question typed into
Ask, and a bank's capped research text for its own agent (ADR 0061, D-98). ADR 0061 said a
third exception would be a decision of its own.

The "Does it apply" dialog (D-141) pre-fills the reason from the licence facts by a pure
function with no model call. Alex asked for AI help where text is typed. A model drafting
the reason reads tenant-zone facts: which register lines a company's licences carry and which
licences the bank recorded. D-143 left the choice open between no AI, AI from the licence
facts and the rule's own text, and AI reading what the person typed too.

## Decision

A model may draft the reason from the **licence facts and the library's shared facts only**:
the third named exception to D-07.

**What reaches the model, read by the server, never taken from the request.**

- The answer the person chose (applies, does not apply, not assessed) and the language to
  write in (Swedish for a Swedish locale, else English).
- The company's licence facts: each supervisor's register line, the business or licence
  wording as the register publishes it, with the scope terms it brings; each licence the bank
  recorded, as its type, authority, grant date and covered services; the company's type.
  Every term as its key and its label.
- The library's shared facts: each regulation's short name, official reference and regime,
  with the register lines that bring that regime in; up to `REGISTER_REASON_DRAFT_FACTS`
  obligations' reference, title, summary in force and source.

**What never does.** What the person typed, in that field or anywhere; the company's or the
bank's name, and a register line that names them (a branch's name); people; register
answers; cases; comments; a licence's own reference, number, notes or scope statement; any
other tenant text. A bank's own record (D-57) and an obligation under a standard (D-81) are
refused with 422 `draft_refused` before any model is asked.

**The guards, each required.**

1. Only on a person's request, `POST /applicability/reason-draft`, behind
   `applicability.approve`, the permission that sets the answer.
2. Every text is cut to `REGISTER_REASON_DRAFT_TEXT_MAX_CHARS` and read as untrusted: one
   numbered line each with its white space folded, a line the injection screen (AGT-07) flags
   left out, and a system prompt that says the lines are data, never instructions.
3. Only through the logged wrapper (`apps/shared/ai.py`), which writes the `ai_generation`
   row (purpose `reason_draft`, naming the person who asked) and keeps no prompt, only its
   hash. Stopped by the bank's AI switch (403 `feature_off`). Capped at
   `REGISTER_REASON_DRAFT_MAX_TOKENS` and `REGISTER_REASON_DRAFT_DEADLINE_MS`.
4. Never logged, never in an audit summary: drafting changes no record and writes no audit
   event.
5. Labelled until a person stands behind it: the dialog shows "AI draft — check it before you
   set it" until the person edits the text or sets the answer. Setting the answer with the
   draft's id marks its log row `confirmed` (kept as it stood) or `edited`, naming the person,
   and the decision's audit event carries the draft's id and that review, never its words.
6. The rule-based suggestion (D-141) stays the default prefill, so the dialog works the same
   with AI switched off.

So D-07 reads: **we** send no tenant-zone text to a model except Ask's question, a bank's
capped research text for its own agent, and the licence facts behind a reason a person asked
a model to draft, each of which the bank can switch off.

Deliberately not done: reading or rewriting what the person typed (the second option), a
draft without a person's request, a draft for the obligation as a whole where no company is
named (no licence facts to rest on), and a monthly cost cap of its own beyond the AI switch.

## Consequences

Easier: a person deciding many obligations gets a reason in plain words that names the
licence behind the answer, and the AI log says who stood behind it. Harder: one more prompt
builder carries the guards and their tests, and the register's licence lines become model
input, which the screen and the named-line prompt contain. To remember: a fourth exception,
or letting this one read typed text, is a decision of its own.
