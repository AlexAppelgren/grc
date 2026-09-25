# First-run setup

For the owner in front of an empty database. Phase 0 version: it describes
what the deploy seeds and the steps a person takes, in dependency order, with
the grant each needs. The agent extends this file as each console lands, so
the step numbers may grow; the order does not change.

## What the deploy seeds (no person needed)

`docker-entrypoint.sh` runs `manage.py seed_reference` on every deploy, after
migrating as `cw_migrator` and as `cw_app`. It runs the seeds below in
dependency order; each matches on its immutable key, so a rename survives a
deploy. The list is `REFERENCE_SEEDS` in
`backend/apps/shared/management/commands/seed_reference.py`, and this table
says the same thing in the same order.

| Seed | What it creates | What breaks without it |
|---|---|---|
| Languages | `en`, `sv`, `da`, `nb`, `fi` with their text search configurations | No label can be stored and every picker is empty |
| Jurisdictions | EU, SE, DK, NO, FI | No instrument can be filed and provision kinds have no jurisdiction |
| Library vocabularies | Tier-two lists with their `kind` rows and defaults (instrument levels, provision kinds, change types, duty types, relation types, source kinds, term dimensions, urgency) | Agents get an empty vocabulary read and every classification is `unknown_key` |
| Taxonomy terms | The scope terms of the eleven dimensions the footprint is built from | No footprint can be set and no obligation can be scoped |
| Authorities | The authority of each jurisdiction | No instrument or source can name who issued it |
| Agent definitions | The versioned definitions under `backend/agents/` | No key can be bound to an agent and every agent write is audited as a bare key id |
| Platform roles | `platform_admin` and `library_editor` | Nobody can be a platform editor or admin |
| Tenant system roles | The seven tenant system roles of `PRD.md` §6, for every tenant that exists | Invitations cannot assign a role |
| Tenant vocabularies | The tier-three lists of every tenant that exists | A tenant's pickers are empty and a case has no status to start in |

Permissions are not a seed: they are constants in code, and the role editor
lists them from `GET /reference/permissions` (ID-09). Roles are rows.

The last two run for tenants that already exist. A new tenant gets its system
roles and its own vocabularies when it is created, not from the deploy.

## Steps for a person, in dependency order

| # | Step | Where | Grant needed | Depends on |
|---|---|---|---|---|
| 1 | Create the database roles and extensions (`RAILWAY_DEPLOY.md` role script) and set every variable (`RAILWAY_VARIABLES.md`) | Railway console | Project owner | Nothing |
| 2 | Deploy `api`; confirm `/health/` answers 200 with every component named | Railway | Project owner | 1 |
| 3 | Deploy `worker`, `beat`, `web`; attach the test host to `web` and set `WEBAUTHN_RP_ID` to it (`DNS_DOMAINS.md`) | Railway | Project owner | 2 |
| 4 | `python manage.py bootstrap_platform --admin-email you@…` on the `api` service. It creates the first platform admin invitation, emails the link and also prints it. **The printed link is a one-time enrolment secret**: do not paste it anywhere, and close the shell session afterwards. It is there so the first admin can enrol before the mail sender is proven | `api` shell | None (a management command; it refuses a person who already holds a passkey, and any address a bank knows: platform staff are separate accounts) | 3, a working mail sender |
| 5 | Open the emailed link, enter the code, enrol a passkey, add a second passkey when prompted | Browser | The enrolment session only | 4 |
| 6 | Create the first tenant: its name, short name, timezone, default language and language order, and the first administrator's address. One action writes the tenant with its system roles, its own vocabularies and its content languages, invites that person with the Admin system role and emails them the enrolment link. The address must be their own: platform staff are separate accounts, so an address that already holds a platform role is refused. Plans are R3 (NFR-05), so nothing is assigned here | Platform console, Tenants | `tenants.manage` | 5 |
| 7 | Confirm the tenant is in the console's tenant list with its status and default language. A second creation with the same short name answers 409, so retry with a different one rather than creating a duplicate | Platform console, Tenants | `tenants.manage` | 6 |
| 8 | The tenant admin opens the link, enters the code, enrols a passkey | Browser | The enrolment session only | 7 |
| 9 | Set the tenant profile: name, timezone, default languages; work through the onboarding checklist | Tenant admin, Organisation | Admin system role (`members.manage` for people, `vocab.manage` for lists, `security.manage` for policy) | 8 |
| 10 | Invite members with roles: at least one compliance officer and one approver, because four eyes needs two people | Tenant admin, Members | `members.manage` | 9 |
| 11 | Set the footprint: one person requests, a second approves with step-up | Tenant app, Footprint | `footprint.request`, then `footprint.approve` by a different person | 10 |
| 12 | Review the tenant vocabularies and add what the bank uses (tags, sub-statuses, reasons) | Tenant admin, Vocabularies | `vocab.manage` | 9 |
| 13 | Invite each library editor: `python manage.py bootstrap_platform --admin-email them@… --role library_editor` on the `api` service. It grants the `library_editor` role, audits the grant and emails them the one-time enrolment link; they enrol a passkey as in step 5 | `api` shell | None (a management command; it refuses a role that is not a platform role, a person who already holds a passkey, and any address a bank knows, since platform staff are separate accounts. A person who already holds another platform role needs `--add-role`; the output lists every platform role they then hold) | 5, D-14 |
| 14 | Create an API key for the research agents with the `watch.write` and `proposals.write` scopes; store it in the runner's configuration | Tenant admin, Integrations | `integrations.manage` plus step-up | 10 |
| 15 | Switch the agents on and set a cadence within the plan | Tenant admin, Agents | `agents.manage` | 14 (R2: chunk 11) |
| 16 | Optional: `python manage.py seed_demo` (lands with chunk 3) loads the prototype's sample data into a demo tenant. It refuses to run when `ENVIRONMENT` is a production name | `api` shell | None | 6 |

## The steps above are tested on an empty database

`npm run test:e2e -- --grep @coldstart` walks steps 4 to 11 through the real UI on a
database a deploy has only migrated and seeded reference data into. Its stack is booted
the way `docker-entrypoint.sh` boots one — migrate as the migrator, `seed_reference`, and
nothing else — with its own database name and its own ports, so it never touches the
seeded E2E run (`E2E_COLD_START=1` in `frontend/tests/e2e/support/start-backend.sh`,
chosen by `frontend/playwright.config.ts`). It runs in CI on every backend or frontend
change, beside the ordinary E2E job.

The journey is `frontend/tests/e2e/coldstart.journey.spec.ts` (scenario ADM-S8 in
`backend/apps/governance/app.md`). When a step below changes, change it there too: the
runbook and the test are meant to say the same thing. Steps 12 to 16 are not walked yet;
step 15 (agents) and the watch feed's empty state wait for their chunks.

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
| 4 | Tenants with their first administrator (steps 6 and 7), library editors, proposal queue, sources (step 13) |
| 5 | API keys (step 14) |
| 11 | Agents (step 15), credential and session policy |
| 12 | Data: import, export, retention |
