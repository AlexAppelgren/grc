# ADR 0067 — The regulatory scope follows the organisation by itself

**Date:** 2026-10-08 · **Status:** accepted (Alex, 2026-10-08: "make it simple for the user so they ideally don't have to manage the overall surface at all, and eu banks should get eu rules of course"; "Is approval actually needed for the overall surface?"; "Yes, build it that way"; D-122, PRD 0.10 FP-02, FP-04, FP-05, TEN-08; amends ADR 0066 and the four-eyes invariant)

## Context

ADR 0066 had the public registers suggest the scope: a person filed the suggestion as a
request and a second person approved it with a passkey. Yet what it suggested was not a
choice. A company's country, its branches and what its licence allows are facts, so the
second person had nothing to check, and the bank still had to manage a scope its own
organisation already described. Whether a duty applies, the one judgement in the chain, is
already one person's decision (D-75).

The register's span offered a company every rule in the group's scope whatever its country:
in a group operating in Sweden and Denmark, the Swedish company was offered Danish rules.

## Decision

1. **What the organisation gives the scope applies by itself.** `follow()` in
   `apps/taxonomy/organisation_scope.py` writes it as the system, one history row and one
   audit event per term, with no request and no step-up, through the same writes an approval
   makes. It runs when a legal entity is added or its country or active state changes, once
   after a register lookup is applied, and after each nightly re-read.
2. **The rules are ADR 0066's, plus countries.** Each legal entity's country and each branch's
   country the library covers is an operating market, and the organisation never removes one.
   The licence-bound terms follow the register facts, and each company is outside the
   licence-bound terms its facts do not give it, as before.
3. **Each company keeps to its own countries.** A legal entity in a covered country is outside
   every other covered country but its branches', as company lines in the jurisdiction
   dimension, which the span already reads. An EU rule carries the EU and every country it
   reaches, so every company is offered it; a Danish rule only the Danish companies and those
   with a Danish branch. The EU is never outside a company's scope, and a company with no
   country, or one the library does not cover, is never narrowed.
4. **A person's change wins.** A term or company line whose last change was an approved request
   is a person's, and `follow()` leaves it alone. Changing the scope by hand is the request of
   FP-02, approved by a second person with a passkey: a market served without a branch, a term
   the registers cannot know, a country put back into one company's scope.
5. **The suggestion is gone.** `GET /tenant/footprint/suggestions` is removed. `GET
   /tenant/footprint` says how many companies the scope follows and when a register was last
   read, and the scope page says that it follows the organisation.

Rejected: keeping the approval on a suggestion nobody chooses; stopping the organisation from
moving anything after a person's first change to it, which would freeze the scope after one
edit; and a separate country rule in the span, when the exclusion rows already narrow it.

## Consequences

Easier: a bank adds its companies and its scope is set, with no boxes to pick and no request
to approve, and each company is offered its own countries' rules. Harder: a wrong register
fact or a wrong country on Organisation narrows unseen until someone looks, so every change is
audited and nothing is narrowed on a guess. To remember: a term a person changed by hand stays
theirs until a person changes it again, and licences typed on Organisation give the scope
nothing; only the register facts do.
