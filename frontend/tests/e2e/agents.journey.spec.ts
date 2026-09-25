import type { APIResponse } from '@playwright/test';

import {
  answered,
  currentPill,
  openDefinition,
  publishVersion,
  sessionApi,
  SWEEPER_RUN_ON_V1,
  SWEEPER_RUN_ON_V2,
  versionRow,
} from './support/agent-definitions';
import { mintAgentKey, revokeAgentKey } from './support/agent-key';
import { expect, test } from './support/api-guard';
import { allowFreshContext, BACKEND_URL, LOGINS, restrictedScreen, signInAs, signOut } from './support/passkeys';
import { approveQueueProposal } from './support/watch';

// agents: the @e2e scenarios from backend/apps/agents/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.
//
// AGT-S10 (J-4) versions its own duty, backend/apps/shared/e2e_seed.py J4_OBLIGATION, which
// no other spec or seed names; everything it files carries the attempt's own stable key,
// title and date, so a retry never merges into or asserts an earlier attempt's rows.

const J4_OBLIGATION = 'obl-product-governance';
const J4_OBLIGATION_TITLE = 'Define a target market and distribution strategy for each product';
// Version 1 as the fixture holds it; the new version keeps it and adds one sentence.
const J4_SUMMARY = {
  sv: 'För varje finansiellt instrument som produceras eller distribueras ska institutet fastställa en målgrupp, säkerställa att distributionsstrategin passar den och regelbundet se över båda.',
  en: 'For every financial instrument manufactured or distributed, the institution defines a target market, checks that the distribution strategy fits it, and reviews both regularly.',
};
const J4_SOURCE = 'https://www.fi.se/';
const J4_MODEL = 'agent pipeline 0.4';
// What one sweep spends (ID-10): open and close its run, read the terms, find the duty,
// register the change, file the proposal. Nothing reaches the library but through the queue.
const J4_SCOPES = ['agent-runs:write', 'library:read', 'search:read', 'changes:write', 'proposals:write'];

const escapeRegExp = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** The tenant-local day (Europe/Stockholm) plus `days`, as YYYY-MM-DD. */
function stockholmDayPlus(days: number): string {
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Stockholm', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  const date = new Date(`${today}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

/** One agent write: JSON under a fresh Idempotency-Key, as the sweeper sends it. */
function write(data: unknown) {
  return { data, headers: { 'Idempotency-Key': crypto.randomUUID() } };
}

/** The answer's body once its status is the one expected; the problem's own words otherwise. */
async function send<T = unknown>(call: Promise<APIResponse>, status: number): Promise<T> {
  const response = await call;
  expect(response.status(), `${response.url()} answered ${await response.text()}`).toBe(status);
  return (await response.json()) as T;
}

test.describe('agents journeys', () => {
  test("AGT-S4: Agent definitions are versioned and owned by the platform", async ({ page, apiGuard }, testInfo) => {
    // AGT-03, ADM-02: a platform admin publishes the sweeper's next version from the folder
    // the E2E stack ships (support/start-backend.sh: v3 to v5, one per attempt), behind a
    // passkey; the seeded runs keep the versions they started under; a bank's admin reaches
    // no definition. Publishing only adds a version and the seeded ones are left as they
    // were, so there is nothing to restore: a retry publishes the next folder, and the
    // screen offers no retiring of the current version, which new runs need.
    test.setTimeout(120_000);
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/agent-definitions\/watch-sweeper\/versions$/, 403, 'publishing asks for a fresh passkey first, which opens the step-up prompt');
    const note = `Reads the new FFFS index page first (attempt ${testInfo.retry}).`;

    await signInAs(page, LOGINS.platform);
    await page.goto('/console/agents');
    await page.locator('[data-agent-definition="watch-sweeper"]').getByRole('link').click();
    await expect(page).toHaveURL(/\/console\/agents\/watch-sweeper$/);
    const before = await openDefinition(page, 'watch-sweeper');
    expect(before).toEqual(expect.arrayContaining([1, 2]));
    const current = Math.max(...before);
    const next = current + 1;

    await publishVersion(page, next, note);
    // The list grows by the one version, which is now the current one, with its note.
    await expect(page.locator('[data-agent-versions] [data-agent-version]')).toHaveCount(before.length + 1);
    const row = versionRow(page, next);
    await expect(currentPill(row)).toBeVisible();
    await expect(row).toContainText(note);
    await expect(row).toContainText(`agents/watch-sweeper/v${next}`);
    await expect(currentPill(versionRow(page, current))).toHaveCount(0);

    // Earlier runs still name the version they started under, by exact text: the second
    // fact of each run's line, after its start.
    const facts = (runId: string) => page.locator(`[data-platform-runs] [data-run-id="${runId}"] > span`).first();
    await expect(facts(SWEEPER_RUN_ON_V1)).toHaveText(/^[^·]+ · Version 1 · \d+ min · /);
    await expect(facts(SWEEPER_RUN_ON_V2)).toHaveText(/^[^·]+ · Version 2 · \d+ min · /);

    // A bank's admin: no console entry, the client gate by address, and the server's own
    // structured 403 naming the permission on every definition route.
    await signOut(page);
    await signInAs(page, LOGINS.admin);
    await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible();
    await expect(page.locator('a[href^="/console"]')).toHaveCount(0);
    await page.goto('/console/agents/watch-sweeper');
    await expect(restrictedScreen(page)).toContainText('Needs agent definitions manage');
    apiGuard.allow(/\/agent-definitions/, 403, "a bank's admin reaches no agent definition (agent_definitions.manage)");
    const api = await sessionApi(page);
    for (const call of [
      api.get('/agent-definitions'),
      api.get('/agent-definitions/watch-sweeper'),
      api.post('/agent-definitions/watch-sweeper/versions', { versionNo: 9, changeNote: 'Not ours to publish.' }),
      api.post('/agent-definitions/watch-sweeper/versions/1/retire', {}),
    ]) {
      const refused = await answered<{ code: string; requiredPermission: string }>(call, 403);
      expect(refused).toMatchObject({ code: 'permission_denied', requiredPermission: 'agent_definitions.manage' });
    }
  });

  test.fixme("AGT-S5: A tenant controls its agents without touching their instructions", async () => {
    // pending: AGT-S5 (AGT-04, chunk 11)
  });

  test("AGT-S13: A bank cannot switch off, pause or re-scope one of bleqq's agents", async ({ page, apiGuard }) => {
    // AGT-03, AGT-04: a bank's admin holding agents.manage reads bleqq's agents on the
    // agents screen, read-only, with when each runs next and how its last run ended; none is
    // among the bank's own agents; and the requests the screen never sends answer 403 naming
    // agent_definitions.manage and change nothing. The AI switch line is the integration
    // test's (a beat run, which no journey drives).
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/api\/v1\/research-requests$/, 501, 'research requests answer not_built until c11-research-requests fills the route; the page draws them against the published contract');
    await signInAs(page, LOGINS.admin);
    await page.goto('/admin/agents');
    await expect(page.getByRole('heading', { level: 1, name: 'Agents' })).toBeVisible();

    const watch = page.locator('[data-platform-watch]');
    const sweeper = watch.locator('[data-platform-agent="watch-sweeper"]');
    await expect(sweeper).toBeVisible();
    await expect(sweeper).toContainText('Weekly');
    // Next run: a date, never "Not scheduled", for a weekly agent.
    await expect(sweeper).toContainText('Next run');
    await expect(sweeper).not.toContainText('Not scheduled');
    // Last run: its state as a pill (a journey running beside this one may be mid-run).
    await expect(sweeper.locator('[data-pill]', { hasText: /^(Done|Running|Failed|Stopped)$/ })).toHaveCount(1);
    // Read-only: nothing on bleqq's watch can be pressed, and none of it is the bank's own.
    await expect(watch.getByRole('button')).toHaveCount(0);
    const own = page.locator('[data-our-agents]');
    await expect(own.locator('[data-agent-key="tenant-source-watch"]')).toBeVisible();
    await expect(own.locator('[data-agent-key="watch-sweeper"]')).toHaveCount(0);

    // Adding it as the bank's own, changing how it runs, and stopping one of its runs.
    apiGuard.allow(/\/api\/v1\/(agents|agent-definitions\/watch-sweeper\/settings|agent-runs\/[^/]+\/interrupt)$/, 403, "bleqq's agents are the platform's: a bank's admin is refused (agent_definitions.manage)");
    const api = await sessionApi(page);
    const before = await answered<{ items: { key: string; cadence: string; jurisdictions: string[] }[] }>(api.get('/agents/platform?limit=100'), 200);
    for (const call of [
      api.post('/agents', { agent: 'watch-sweeper' }),
      api.put('/agent-definitions/watch-sweeper/settings', { cadence: 'monthly', jurisdictions: ['se'], monthlyBudget: '1.00' }),
      api.post(`/agent-runs/${SWEEPER_RUN_ON_V2}/interrupt`, {}),
    ]) {
      const refused = await answered<{ code: string; requiredPermission: string }>(call, 403);
      expect(refused).toMatchObject({ code: 'permission_denied', requiredPermission: 'agent_definitions.manage' });
    }
    // Nothing about it changed.
    const after = await answered<typeof before>(api.get('/agents/platform?limit=100'), 200);
    const pick = (page: typeof before) => page.items.filter((item) => item.key === 'watch-sweeper').map(({ key, cadence, jurisdictions }) => ({ key, cadence, jurisdictions }));
    expect(pick(after)).toEqual(pick(before));
  });

  test.fixme("AGT-S6: The budget cap pauses runs and the AI off switch stops every model call", async () => {
    // pending: AGT-S6 (AGT-04, chunk 11)
  });

  test.fixme("AGT-S7: Research requests ask an agent to check, research or re-tag", async () => {
    // pending: AGT-S7 (AGT-05, chunk 11)
  });

  test("AGT-S10 J-4 @smoke: an agent registers a change and a proposal, an editor approves, the tenant sees what changed", async ({ page, browser, playwright, apiGuard }, testInfo) => {
    // AGT-01, ID-10, WAT-02, PRO-02, INV-04, INV-05: one night of the watch sweeper, from the
    // key a platform administrator mints to what a bank's officer reads the next morning.
    test.setTimeout(180_000);
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/proposals\/.+\/approve$/, 403, 'approving asks for a fresh passkey assertion first, which opens the step-up prompt');

    // The administrator works in a context of their own, so the key can be revoked whatever
    // state the journey's page is left in.
    const admin = await browser.newContext({ baseURL: testInfo.project.use.baseURL });
    const adminPage = await admin.newPage();
    apiGuard.watch(adminPage);
    const stepUp = adminPage.waitForResponse((r) => r.url().endsWith('/api/v1/agent-keys') && r.request().method() === 'POST' && r.status() === 403);
    const key = await mintAgentKey(adminPage, apiGuard, { name: `J-4 sweeper ${Date.now()}`, agent: 'watch-sweeper', scopes: J4_SCOPES });
    // The agent is the API and its key, nothing else: no session and no cookie.
    const agent = await playwright.request.newContext({ baseURL: BACKEND_URL, extraHTTPHeaders: { 'X-API-Key': key.plainKey } });

    try {
      // Minting asked for the administrator's passkey before the key existed.
      expect(((await (await stepUp).json()) as { code: string }).code).toBe('step_up_required');

      // The run opens, then reads the terms it may name (AGT-02).
      const run = await send<{ id: string }>(agent.post('/api/v1/agent-runs', write({ agent: 'watch-sweeper', model: J4_MODEL, pipelineVersion: '0.4' })), 201);
      const regimes = await send<{ items: { id: string; key: string }[] }>(agent.get('/api/v1/taxonomy/terms', { params: { dimension: 'regime' } }), 200);
      const regime = regimes.items.find((term) => term.key === 'securities');
      expect(regime, 'the securities regime is a term the agent can name').toBeDefined();
      // The duty, found the way the sweeper finds one: the nearest library record to the text.
      const similar = await send<{ items: { id: string; type: string; title: string }[] }>(agent.post('/api/v1/search/similar', { data: { text: J4_OBLIGATION_TITLE, types: ['obligation'] } }), 200);
      const duty = similar.items.find((hit) => hit.title === J4_OBLIGATION_TITLE);
      expect(duty, `${J4_OBLIGATION} is in the library`).toBeDefined();
      const obligationId = duty?.id ?? '';

      // Registered with its regime (D-39), linked to the duty as a suggestion. The stable key
      // and the date are the attempt's own, so a retry is a second reform, not a merge.
      const attempt = `${Date.now()}`;
      const inForce = stockholmDayPlus(30 + testInfo.retry + testInfo.repeatEachIndex);
      const stableKey = `chg-e2e-j4-product-governance-${attempt}`;
      const change = await send<{ id: string }>(
        agent.post(
          '/api/v1/changes',
          write({
            stableKey,
            title: `FI tightens product governance reviews (${attempt})`,
            changeType: 'adopted',
            authorityLabel: 'Finansinspektionen',
            authorityCode: 'fi',
            summary: 'FI amends FFFS 2017:2 so that each product\'s target market is reviewed at least once a year.',
            sourceLabel: 'Finansinspektionen',
            sourceUrl: J4_SOURCE,
            documents: [{ url: J4_SOURCE, isPrimary: true }],
            termIds: [regime?.id],
            obligationLinks: [{ obligationId, confidence: 0.86 }],
            agentRunId: run.id,
            model: J4_MODEL,
          }),
        ),
        201,
      );

      // The new version of the duty, filed under the change and the run, a source per field.
      const added = { sv: `Från ${inForce} ser institutet över varje produkts målgrupp minst en gång om året och dokumenterar resultatet.`, en: `From ${inForce}, the institution reviews each product's target market at least once a year and records the outcome.` };
      const title = `Add a new version of the product governance obligation, with a yearly target market review (${attempt})`;
      const proposal = await send<{ status: string; changeId: string; agentRunId: string; fieldSources: Record<string, string> }>(
        agent.post(
          '/api/v1/proposals',
          write({
            kind: 'new_obligation_version',
            title,
            targetType: 'obligation',
            targetId: obligationId,
            changeId: change.id,
            agentRunId: run.id,
            payload: {
              summaries: { sv: `${J4_SUMMARY.sv} ${added.sv}`, en: `${J4_SUMMARY.en} ${added.en}` },
              originalLanguage: 'sv',
              isMachine: true,
              effectiveFrom: inForce,
              effectiveFromPrecision: 'day',
            },
            fieldSources: { 'summaries.sv': J4_SOURCE, 'summaries.en': J4_SOURCE, effectiveFrom: J4_SOURCE },
            sourceLabel: 'Finansinspektionen, board decision',
            sourceUrl: J4_SOURCE,
            model: J4_MODEL,
          }),
        ),
        201,
      );
      expect(proposal).toMatchObject({ status: 'open', changeId: change.id, agentRunId: run.id, fieldSources: { 'summaries.sv': J4_SOURCE, 'summaries.en': J4_SOURCE, effectiveFrom: J4_SOURCE } });
      const closed = await send<{ status: string }>(
        agent.patch(`/api/v1/agent-runs/${run.id}`, write({ status: 'succeeded', stats: { modelCalls: 2, fetches: 1, sourcesChecked: 0, changesRegistered: 1, proposalsSubmitted: 1 } })),
        200,
      );
      expect(closed.status).toBe('succeeded');

      // A library editor, a different principal from the agent, approves it with a passkey.
      await signInAs(page, LOGINS.editor2);
      await approveQueueProposal(page, new RegExp(escapeRegExp(title)));
      await signOut(page);

      // The bank's officer reads the new version on the duty's own card, with what changed.
      await signInAs(page, LOGINS.complianceOfficer);
      // The version this approval produced is the one in force from this attempt's date; the
      // card's own read names its number, and it is the newest the duty has.
      const card = page.waitForResponse((r) => new URL(r.url()).pathname === `/api/v1/obligations/${obligationId}` && r.ok());
      await page.goto(`/inventory/obligations/${obligationId}`);
      const { versions } = (await (await card).json()) as { versions: { versionNumber: number; effectiveFrom: { date: string } | null }[] };
      const produced = versions.find((v) => v.effectiveFrom?.date === inForce)?.versionNumber;
      expect(produced, 'the approval produced a version in force from the proposed date').toBe(Math.max(...versions.map((v) => v.versionNumber)));
      expect(produced).toBeGreaterThan(1);
      await expect(page.locator(`[data-versions-panel] [data-version-row="${produced}"]`)).toBeVisible();
      await page.getByRole('button', { name: 'Show what changed' }).click();
      await expect(page.locator('[data-diff-banner]')).toBeVisible();
      await expect(page.locator('[data-legal-text] ins').filter({ hasText: inForce }).first()).toBeVisible();

      // "Library updates" lists that version under the duty's own title, one tap from the
      // diff; the screen's own read says which row it is.
      const listed = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/v1/library-updates' && r.ok());
      await page.goto('/inventory/updates');
      const { days } = (await (await listed).json()) as { days: { items: { id: string; versionNumber: number | null; target: { id: string } | null }[] }[] };
      const row = days.flatMap((day) => day.items).find((item) => item.target?.id === obligationId && item.versionNumber === produced);
      expect(row, `Library updates lists version ${produced}`).toBeDefined();
      const update = page.locator(`[data-update-id="${row?.id}"]`);
      await expect(update).toBeVisible();
      await expect(update.getByRole('heading', { level: 3 })).toHaveText(J4_OBLIGATION_TITLE);
      await expect(update.getByRole('link', { name: 'Show what changed' })).toHaveAttribute('href', `/inventory/obligations/${obligationId}`);

      // The feed shows the change waiting for triage: the bank's case opens on the outbox
      // cursor after the registration (CAS-01), so the feed is read again until it is there.
      await expect(async () => {
        await page.goto('/watch');
        await expect(page.getByRole('tab', { name: /^Needs triage/ })).toHaveAttribute('aria-selected', 'true');
        await page.getByRole('searchbox', { name: 'Search these changes' }).fill(attempt);
        await page.getByRole('button', { name: 'Search' }).click();
        await expect(page.locator(`[data-change="${stableKey}"]`)).toBeVisible({ timeout: 3_000 });
      }).toPass({ timeout: 60_000 });
      await expect(page.locator(`[data-change="${stableKey}"]`).getByText('Needs triage', { exact: true })).toBeVisible();
    } finally {
      // Teardown that runs on failure too: a live key never outlives the attempt.
      await agent.dispose();
      await revokeAgentKey(adminPage, key.id);
      await admin.close();
    }
  });

  test.fixme("ACC-S1: An entry is registered, narrowed to a department, and revoking it stops its credentials", async () => {
    // pending: ACC-S1 (ACC-01, J-11, chunk 11)
  });

  test.fixme("ACC-S6: A narrowed entry never narrows silently", async () => {
    // pending: ACC-S6 (ACC-07, AC-ACC1, chunk 11)
  });

  test.fixme("ACC-S13 J-11 @smoke: a bank's coding agent reads what applies to it", async () => {
    // pending: ACC-S13 (ACC-01 to ACC-08, AC-ACC1, AC-ACC2, AC-ACC4, J-11, chunk 11)
  });
});
