# Scope items: the bank's own regulations (PRD 0.7, OWN)

Source: D-89 (Alex, 2026-09-24), the details answered by default in D-91, ADR 0059. The
requirements are PRD 0.7's OWN-01 to OWN-05 with INV-07, AC-OWN1, AC-OWN2 and J-12; the
scenarios are FP-S18, FP-S19, AGT-S14, AGT-S16, PRO-S12, PRO-S15, INV-S9, INV-S13, INV-S15
and REG-S17. Everything here is built in chunk 11 (R2), the register half after chunk 8.

## What Alex decided

"an agent can always add things to the library, and then another agent can verify it, its
then up to the tenant to decide if they want to use it or not", and "The previously called
'footprint' can not be agent managed, only a tenant admin can add things that the agents
should look out for or regulations that apply to them". A bank's people may add to its
regulatory scope a regulation or area the shared library does not yet cover; the bank's own
agents research it and fill the bank's own library zone with its regulation and control
inventories as proposals, which the bank's people approve or reject the way the shared queue
works.

## The flow

1. **Scope item (OWN-01, FP-S18).** On the regulatory scope page a person holding
   `footprint.request` adds "a regulation we need that the library does not cover": a name,
   jurisdiction terms, regime terms, an official reference where one exists, and one or more
   public https source addresses. It is a regulatory scope change request like any other:
   "Waiting for approval", one waiting request per organisation, a second person holding
   `footprint.approve` approves with a passkey, 409 `four_eyes_violation` for the requester,
   one audit event. Every route takes a person's session and a permission, so no API key
   reaches it. Approving an item changes no term: the preview hides and reveals nothing,
   and FP-01's matching never reads items.
2. **Research (OWN-02, AGT-S16).** The approval opens one research request for the bank's
   own agent, a tenant-scoped definition bleqq authored and the bank switched on (AGT-04).
   With no such agent switched on, the item waits. The worker
   opens the run with no key and starts it through the `agent_runner` adapter (the mock in
   tests and E2E).
3. **Findings (OWN-02, AGT-S14).** The run reports runner events. The worker validates each
   at the boundary and applies a `new_instrument` or `new_obligation` event as a proposal
   owned by the run's tenant, a source per field, through the same proposal-creation check
   the shared door uses. A duplicate of a record the bank already holds, by official
   reference, answers 409 `already_in_our_library` and stores nothing; the check is the
   server's, so the agent never reads the bank's own records. An event naming a shared
   record, the regulatory scope or a re-tag is refused and stored nowhere.
4. **Decision (OWN-03, PRO-S12, PRO-S15).** The bank's own queue lists them. A person
   holding `private_records.approve` approves with a passkey or rejects with a reason,
   never the proposer, through ADR 0050's routes, apply code and four-eyes constraint. The
   console never lists them and a platform session's fetch answers 404.
5. **Use (OWN-04, OWN-05, INV-S9, INV-S13, INV-S15, REG-S17).** The approved record reads
   "Private to us" in the inventory, beside the shared library, and only to that bank. The
   register sets applicability (D-75) and status on it as on a shared obligation. The agent
   may propose the obligation's controls as linked internal items of the control kind
   (REG-05), decided in the same queue.

## What never happens

- An agent or an API key writes, approves or edits a scope item or any term of the
  regulatory scope.
- A tenant run writes, re-tags or proposes against the shared library, or a bank's key files
  a proposal: `refuse_tenant_key` is unchanged and no key gains a proposal scope.
- A bank's own record, or any child of one, reaches the search index, an embedding, a
  reranker, a model, the console, an agent access answer (which says how many it left out),
  a support session or another bank (AC-OWN1).
- An agent confirms a bank's own record: the second pair of eyes here is always a person.
- The shared library later covering the same regulation changes the bank's record, its
  register rows or its label. Reconciling the two is the bank's own choice.

## What reaches a model

Until Alex answers the tenant-text question (D-07, D-32), only keys reach one: the item's
jurisdiction and regime term keys, and the pages fetched from its public source addresses,
which are untrusted content screened as every fetched page is (AGT-07). The item's name, any
note on it and every one of the bank's own records stay out. If Alex lets a bank's typed
text reach its own agent, the name joins the input and nothing else changes.

## Defaults taken (D-91, each reversible)

- A scope item is a row on the regulatory scope request, not a new approval path.
- The bank's own records are decided by a person only; an agent never confirms one.
- The run's input is keys and fetched public pages only (above).
- Nothing links or merges automatically when the library catches up.
- OWN-05's control is a linked internal item of the control kind (REG-05) with the fields
  REG-05 gives it, until Alex says what a control inventory holds.
- ADR 0050's private sources (tranche 3) stay chunk 13; a scope item's addresses are not
  private sources and are checked only as https public addresses at the request.
