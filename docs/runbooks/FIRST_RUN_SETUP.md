# First-run setup

For the owner in front of an empty database. Phase 0 version: it describes
what the deploy seeds and the steps a person takes, in dependency order, with
the grant each needs. The agent extends this file as each console lands, so
the step numbers may grow; the order does not change.

## What the deploy seeds (no person needed)

`docker-entrypoint.sh` runs these idempotent reference seeds on every deploy,
after migrating as `cw_migrator` and before starting gunicorn as `cw_app`.
Each matches on its immutable key, so a rename survives a deploy. Each line
in the entrypoint says what silently breaks without it.

| Seed | What it creates | What breaks without it |
|---|---|---|
| Permissions | Every permission constant as a row the role editor can list | Roles cannot be composed; every screen is denied |
| System roles | The seven tenant system roles of `PRD.md` §6 and the two platform roles | Nobody can be invited with a role |
| System vocabularies | Tier-two library vocabularies with their `kind` rows and defaults (instrument levels, provision kinds, change types, duty types, relation types, source kinds, term dimensions, urgency) | Pickers are empty and the vocabulary integrity guard fails |
| Languages | `en`, `sv`, `da`, `nb`, `fi` with their text search configurations | No translation row can be written; search chunks cannot be indexed |
| Jurisdictions and authorities | EU, SE, DK, NO, FI and their authorities | Instruments cannot be created |
| Agent definitions | The versioned definitions under `backend/agents/` | Runs cannot be opened |

Tenant vocabularies (tier three) are created per tenant from the system
defaults when the tenant is created, not by the deploy.

## Steps for a person, in dependency order

| # | Step | Where | Grant needed | Depends on |
|---|---|---|---|---|
| 1 | Create the database roles and extensions (`RAILWAY_DEPLOY.md` role script) and set every variable (`RAILWAY_VARIABLES.md`) | Railway console | Project owner | Nothing |
| 2 | Deploy `api`; confirm `/health/` answers 200 with every component named | Railway | Project owner | 1 |
| 3 | Deploy `worker`, `beat`, `web`; attach the test host to `web` and set `WEBAUTHN_RP_ID` to it (`DNS_DOMAINS.md`) | Railway | Project owner | 2 |
| 4 | `python manage.py bootstrap_platform --admin-email you@…` on the `api` service (the command lands with chunk 1). It creates the first platform admin invitation and prints nothing secret; the link arrives by email | `api` shell | None (a management command; it refuses a person who already holds a passkey, and any address a bank knows: platform staff are separate accounts) | 3, a working mail sender |
| 5 | Open the emailed link, enter the code, enrol a passkey, add a second passkey when prompted | Browser | The enrolment session only | 4 |
| 6 | Create the first tenant with its plan, timezone and language order | Platform console, Tenants | `tenants.manage` | 5 |
| 7 | Invite the tenant's first admin (the Admin system role) | Platform console, Tenants | `tenants.manage` | 6 |
| 8 | The tenant admin opens the link, enters the code, enrols a passkey | Browser | The enrolment session only | 7 |
| 9 | Set the tenant profile: name, timezone, default languages; work through the onboarding checklist | Tenant admin, Organisation | Admin system role (`members.manage` for people, `vocab.manage` for lists, `security.manage` for policy) | 8 |
| 10 | Invite members with roles: at least one compliance officer and one approver, because four eyes needs two people | Tenant admin, Members | `members.manage` | 9 |
| 11 | Set the footprint: one person requests, a second approves with step-up | Tenant app, Footprint | `footprint.request`, then `footprint.approve` by a different person | 10 |
| 12 | Review the tenant vocabularies and add what the bank uses (tags, sub-statuses, reasons) | Tenant admin, Vocabularies | `vocab.manage` | 9 |
| 13 | Invite each library editor: `python manage.py bootstrap_platform --admin-email them@… --role library_editor` on the `api` service. It grants the `library_editor` role, audits the grant and emails them the one-time enrolment link; they enrol a passkey as in step 5 | `api` shell | None (a management command; it refuses a role that is not a platform role, a person who already holds a passkey, and any address a bank knows, since platform staff are separate accounts. A person who already holds another platform role needs `--add-role`; the output lists every platform role they then hold) | 5, D-14 |
| 14 | Create an API key for the research agents with the `watch.write` and `proposals.write` scopes; store it in the runner's configuration | Tenant admin, Integrations | `integrations.manage` plus step-up | 10 |
| 15 | Switch the agents on and set a cadence within the plan | Tenant admin, Agents | `agents.manage` | 14 (R2: chunk 11) |
| 16 | Optional: `python manage.py seed_demo` (lands with chunk 3) loads the prototype's sample data into a demo tenant. It refuses to run when `ENVIRONMENT` is a production name | `api` shell | None | 6 |

## What to check before inviting anyone real

- `WEBAUTHN_RP_ID` is the stable test host, not a `*.up.railway.app` host
  (D-02): passkeys made on a throwaway host stop working when the host
  changes.
- `ENVIRONMENT=test` is the only deployed name where mock adapters are
  allowed; the UI shows a banner while any mock is active.
- The mail sender has SPF and DKIM on its domain, or codes land in spam.
- Every step above left an audit event (Tenant admin, Audit log).

## Extended as consoles land

| Chunk | Steps to add |
|---|---|
| 1 | Members, invitations, re-enrolment, sessions (steps 7 to 10 become real) |
| 2 | Vocabularies and footprint (steps 11 and 12) |
| 4 | Library editors, proposal queue, sources (step 13) |
| 5 | API keys (step 14) |
| 11 | Agents (step 15), credential and session policy |
| 12 | Data: import, export, retention |
