# ADR 0047 — Production refuses any processor outside the EU at boot

**Date:** 2026-09-20 · **Status:** accepted (D-54, Alex 2026-09-19; amends ADR 0016, stages ADR 0007)

## Context

The product is sold to Nordic banks, so where their data is processed is part
of the contract, and a transfer must never follow from a changed environment
variable. Anthropic's own API offers `us` and `global` inference only, and
Managed Agents follows the workspace geography. `eu-west-2` is the United
Kingdom and `eu-central-2` is Switzerland, so matching an `eu-` prefix is not
enough, and some Bedrock inference profiles route by source region. Sentry
ingests EU data through `ingest.de.sentry.io`.

## Decision

Every deployed environment except `ENVIRONMENT=test` refuses at boot any
processor located outside an EU member state, using allowlists that are
constants in the production-safety block, never environment variables. On test,
the existing mock banner also shows whenever a non-EU processor is configured,
so the exemption is never silent, and the test environment never holds a bank's
data.

Models: `anthropic` is refused; `bedrock` is allowed only in `eu-central-1`,
`eu-west-1`, `eu-west-3`, `eu-south-1`, `eu-south-2` or `eu-north-1`, with an
in-region model id or a (source region, `eu.` profile) pair from a list that
starts empty; `global.`, `us.`, `apac.` and application-profile ARNs are
refused. The embedder and reranker must be `none` or `bedrock` under the same
rule. The agent runner refuses `managed_agents` and gains a new value, `none`,
so production agents run inside our own worker on Bedrock in an EU region.
Other services: Sentry with no DSN or a `o<number>.ingest.de.sentry.io` host;
mail only from a reviewed host list that starts empty; storage at
`s3.<EU region>.amazonaws.com`, or a Railway (Tigris) endpoint only once its EU
restriction is verified, so until then production uses AWS S3 in an EU region;
and when `RAILWAY_ENVIRONMENT_NAME` is set, `RAILWAY_REPLICA_REGION` must be
present and equal `europe-west4-drams3a`.

Not refused at boot: destinations a bank configures itself (webhooks, SIEM,
ticket tools, its identity provider), the database, Redis and web regions, and
Sentry's account metadata, which Sentry keeps in the US. These go into the
subprocessor register and the operator checklist.

Deliberately not done: a denylist, allowlists read from environment variables,
an Anthropic exception for library-only work, matching on the `eu-` prefix,
guarding the test environment too, and checking each call's location at
runtime.

## Consequences

Easier: the assurance pack can say where every processor is, and adding one is
a reviewed code change with a Verification log row and advance notice to banks.
Harder: until an EU model is logged, production cannot boot with a real model,
and until the embedder has an EU endpoint production search is keyword-only.
To remember: this amends ADR 0016 with one more host variable, and the in-worker
EU runner it requires must be built before the first bank tenant (ADR 0007,
third tranche), leaving `c11-runner-managed-agents` test-only.

## Implementation plan (when staged)

| Tranche | What | When |
|---|---|---|
| 1 | The boot rules, one subprocess test per rule and the NFR-04 scenario | `c14-eu-data-location` |
| 2 | The in-worker agent runner on Bedrock EU | Before the first bank tenant |
| 3 | The subprocessor register, Tigris, Sentry's US metadata and the mail sender | `c14-assurance-locations` |
