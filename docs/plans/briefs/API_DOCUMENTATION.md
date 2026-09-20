# The published API explains itself (OpenAPI 3.1)

Alex, 2026-09-20: "ensure that the API is properly following latest OAS with good
examples and descriptions in the schema for each attribute and enumeration so
someone reading the API spec understands the full business context and usage",
and "every attribute should have a description as well as each enum/value that
the attribute can have (if it's string/text) or limitations that are important
to know".

The reader we write for is an integrator at a bank who has never seen this
codebase and cannot ask us a question. `openapi.json` is the whole manual: what
a field means in the bank's world, what may be in it, what the server refuses,
and what the call does to the record. A description that only restates the
field name ("The status", "The key") fails this standard.

## 1. What every attribute carries

Every property of every request and response schema has a `description`, in
full sentences, that says:

1. **What the fact is** in the bank's language, not the table's — "the date the
   rule starts binding the bank", not "effective_from column".
2. **Where it comes from**, when that changes how it is read: the library (a
   sourced public fact, changed only through a proposal), the bank's own zone
   (its judgement, never shared), an agent (labelled until a person confirms
   it), or the server (computed, read-only).
3. **What a reader must not conclude from it** where two facts are close
   enough to confuse — "applies to us" is not "we comply"; a machine-confirmed
   fact is not a human-verified one.

## 2. What every value carries

For any field whose value is drawn from a fixed set — and that is the whole
point of this section — the description lists **every value and what it means
to the business**, one line each. Three cases:

- **A kind enum in code** (`Literal[...]`, a `TextChoices`, an enum in the
  contract): list every member with its meaning and what the system does
  differently for it. The contract also carries `enum` and, where the generator
  supports it, a per-value line; the human-readable list in the description is
  the part a reader relies on.
- **A vocabulary key** (a row an admin manages — types, statuses, tags,
  reasons): the value set is data, so the description names the vocabulary, its
  `kind`s, says the values are rows that a tenant's admin may extend, gives the
  keys seeded on day one, and tells the reader to read the vocabulary endpoint
  for the live set. Never present a vocabulary as a closed enum, and never
  suggest matching on the label.
- **A format-constrained string** (a stable key, a language tag, an ETag, a
  date with a precision, an idempotency key): give the format, an example, and
  what the server does with a value it does not accept.

## 3. What every limit carries

Where a limit exists, the description states it in words and the schema states
it in keywords (`maxLength`, `minimum`, `maximum`, `format`, `pattern`,
`readOnly`, `default`). The limits that matter here:

- pagination: the default page size, the maximum, and what a larger one does;
- the longest accepted text and array (a query, a comment, a list of keys);
- concurrency: which records need `If-Match`, and that a stale ETag is a 412;
- write protection: which calls need a passkey step-up, which need an
  idempotency key, which are append-only or soft-delete-only;
- separation: which fields never leave the bank, and which are library facts a
  tenant cannot edit;
- immutability: a stable key never changes; a version is never overwritten.

## 4. What every operation carries

`summary` (what the caller achieves, in the user's voice), `description` (when
to call it, what it changes, which permission or scope it needs, what it
records in the audit), at least one realistic `example` per request body and
per response, taken from the prototype's data and never from a real bank, and
every error the caller must branch on, listed by its RFC 9457 `code` with the
condition that produces it. An empty answer is a 200 with an empty list, and
the description says so.

## 4b. Three things the first sweep had to decide

Settled once here so the remaining sweeps do not each answer them differently
(tenants and agents, 2026-09-20).

**A shape several apps reach has one owner: the app whose `schemas.py` defines
it.** `RoleRef` lives in identity and carries roles, languages and agent
definitions at once; `PageQuery` lives in shared and reaches every list. Its
owner writes its description, and a sweep that meets a shape it does not own
leaves it alone. Where one shape carries value sets with different rules — a
role a bank's admin may extend beside a language it may not — the description
says which is which rather than choosing the convenient half.

**A route published ahead of its logic says so.** Several routes answer 501
today: the contract is declared first on purpose, so the screens and the agents
can be built against it. Their descriptions are written in the present tense
for what the route will do, and end with one sentence: published ahead of the
logic that will fill it, and answering 501 until that ships. Never document a
501 as if it were the behaviour, and never leave a reader to discover it.

**An error code is documented only if a route raises it.** The gate reads every
`code=` literal under `backend/apps` outside its tests, so any code the API
really answers may be written down — and one that is invented is still refused.
Name the codes a caller must branch on, one line each, with the condition that
produces them.

## 5. How it is enforced

`backend/scripts/api_docs_gate.py` reads the generated `openapi.json` and
fails on: a property with no description; a description shorter than a
sentence or one that only repeats the property name; an `enum` whose
description does not mention every member; a string property known to be
vocabulary-backed that does not name its vocabulary; a `maxLength`,
`maximum` or `minimum` that the description never states; an operation with no
summary, no description, or no example; a documented error code that no route
can raise. Everything not yet documented is listed in
`backend/scripts/api_docs_pending.txt`, one `Schema.property` or
`operationId` per line with the task that will close it; the gate fails when a
line in that ledger is already documented (stale) and when anything outside the
ledger is undocumented. The ledger only ever shrinks, and it is empty before R1
is called done.

The gate runs in `prepush.sh` next to the contract-drift check and in CI on any
change to a route, schema or model.
