import type { APIRequestContext, APIResponse } from '@playwright/test';

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
import { agentWith, allowAccessStepUps, enableEntryReach, entriesReachOff, issueEntryKey, registerEntry, revokeEntry, switchTenantReachOff, switchTenantReachOn } from './support/agent-access';
import { mintAgentKey, revokeAgentKey } from './support/agent-key';
import { askForRetag, askOurAgent } from './support/agent-requests';
import { expect, test } from './support/api-guard';
import { allowFreshContext, BACKEND_URL, LOGINS, restrictedScreen, signInAs, signOut } from './support/passkeys';
import { approveQueueProposal } from './support/watch';
import { agentCard, changeSchedule, openAgents, restoreSeededAgent, SEEDED_CAP, setBankAi, setCap } from './support/agent-controls';

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

// acc-summary-j11: J-11's trading world as backend/apps/shared/e2e_seed.py EXPECTED_J11 seeds it.
const J11 = {
  department: 'Trading',
  team: 'trading',
  tradingObligations: ['obl-trading-order-routing-best-result', 'obl-trading-algo-pre-trade-controls'],
  cardObligation: 'obl-cards-interchange-caps',
} as const;
const J11_PURPOSE = 'Builds the order-routing service.';
// An order router that also touches card issuing, which a Trading entry cannot see.
const J11_DESCRIPTION = 'A new order-routing service that also issues virtual cards to trading clients';
type WhatApplies = {
  scope: { entry: { name: string }; departments: { name: string }[]; narrowed: boolean; asOf: string };
  summary: { status: string; aiGenerated: boolean; notice: string; text: string | null; citations: string[] };
  items: { stableKey: string; refLabel: string; instrument: { shortName: string }; decision: { applicability: string; applicabilityReason: string | null; interpretation: string | null } | null }[];
  total: number;
  registerRead: string;
  outsideScope: { terms: { dimension: { label: string }; term: { label: string } }[]; advice: string | null };
};

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
    // Settle the link's own read first: openDefinition reloads the page, and a read still in
    // flight from the click would be the response it waits for, with no body to read.
    await expect(page.locator('[data-agent-versions] [data-agent-version]').first()).toBeVisible();
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

  // AGT-S5, AGT-S6 and AGT-S7 steer tenant A's one seeded agent and its cap, so they run
  // one after the other rather than beside each other.
  test.describe('a bank steers its own agent', () => {
    test.describe.configure({ mode: 'serial' });

    test("AGT-S5: A tenant controls its agents without touching their instructions", async ({ page, apiGuard }) => {
      // AGT-04: tenant A's admin steers the bank's own agent; bleqq's watch has no control.
      // The screen offers the bank's own markets (Sweden operating, Denmark watched), so the
      // scope is narrowed to Sweden; the integration test narrows it to SE and FI by the API.
      allowFreshContext(apiGuard);
      apiGuard.allow(/\/api\/v1\/agents\/[^/]+$/, 422, 'a cadence above the plan limit answers above_plan_limit');
      apiGuard.allow(/\/api\/v1\/research-requests$/, 501, 'the list of research requests is not built yet; the screen shows its error state beside the controls');
      await signInAs(page, LOGINS.admin);
      try {
        const card = await openAgents(page);

        // What bleqq watches carries no control and no spend.
        const watch = page.locator('[data-platform-watch]');
        await expect(watch.getByRole('heading', { name: 'What bleqq watches' })).toBeVisible();
        await expect(watch.getByRole('button')).toHaveCount(0);
        await expect(watch).not.toContainText('€');

        // Switch it on, weekly within the plan, over Sweden alone, with room under the cap.
        await card.getByRole('button', { name: 'Switch off' }).click();
        await expect(card.getByText('Switched off. Nothing runs until it is switched on again.')).toBeVisible();
        await card.getByRole('button', { name: 'Switch on' }).click();
        await expect(card.getByText('Switched on.')).toBeVisible();
        await changeSchedule(card, 'Weekly', ['Sweden']);
        await expect(card.getByText('Saved.')).toBeVisible();
        await expect(card.locator('dd').filter({ hasText: /^Sweden$/ })).toBeVisible();
        await setCap(page, '40.00');

        // "Run now" queues a run, and Recent runs lists it beside the runs before it with what
        // each found and cost.
        const runs = card.locator('[data-run-id]');
        const before = await runs.evaluateAll((rows) => rows.map((row) => row.getAttribute('data-run-id')));
        const queued = page.waitForResponse((r) => /\/api\/v1\/agents\/[^/]+\/runs$/.test(r.url()) && r.request().method() === 'POST');
        await card.getByRole('button', { name: 'Run now' }).click();
        const run = (await (await queued).json()) as { id: string; status: string };
        expect(run.status).toBe('running');
        expect(before).not.toContain(run.id);
        await expect(card.getByText('Run started. It is at the top of Recent runs.')).toBeVisible();
        const row = card.locator(`[data-run-id="${run.id}"]`);
        await expect(row).toHaveAttribute('data-run-state', 'running');
        await expect(card.locator('[data-next-run]')).toHaveText('Running now');
        await expect(runs.filter({ hasText: /\d+ findings?|no findings/ }).first()).toBeVisible();
        await expect(runs.filter({ hasText: /€\s?\d/ }).first()).toBeVisible();

        // "Stop run" interrupts it, and its status says so.
        await card.getByRole('button', { name: 'Stop run' }).click();
        await card.getByRole('button', { name: 'Stop the run' }).click();
        await expect(card.getByText('Stopped. The run shows as stopped under Recent runs.')).toBeVisible();
        await expect(row).not.toHaveAttribute('data-run-state', 'running');
        await expect(card.getByRole('button', { name: 'Stop run' })).toHaveCount(0);

        // A cadence above the plan limit is refused and nothing changes.
        await changeSchedule(card, 'Daily', ['Sweden']);
        await expect(card.getByText('Our plan does not allow this, so nothing changed.')).toBeVisible();
        await page.reload();
        await expect(agentCard(page).locator('dd').first()).toContainText('Weekly');
      } finally {
        await restoreSeededAgent(page);
      }
    });

    test("AGT-S6: The budget cap pauses runs and the AI off switch stops every model call", async ({ page, apiGuard }) => {
      // AGT-04. The cap half is tenant A's, whose seeded runs put the month's spend just under
      // its cap; the AI half switches tenant B's AI off, because tenant A's Ask journeys run in
      // parallel and a bank's switch is the whole bank's. That the admins are notified when the
      // beat pauses an agent is the integration test's: no journey waits for the beat.
      allowFreshContext(apiGuard);
      apiGuard.allow(/\/api\/v1\/agents\/[^/]+\/runs$/, 422, 'a run that could pass the monthly cap answers budget_cap_reached');
      apiGuard.allow(/\/api\/v1\/research-requests$/, 501, 'the list of research requests is not built yet; the screen shows its error state beside the controls');
      apiGuard.allow(/\/api\/v1\/tenant\/ai$/, 403, 'switching AI answers step_up_required first and opens the passkey prompt');
      apiGuard.allow(/\/api\/v1\/ask$/, 403, 'Ask answers feature_off while the bank has AI off');
      await signInAs(page, LOGINS.admin);
      try {
        const card = await openAgents(page);

        // "Spend this month" is the bank's own runs, 6.25 of the 7.00 cap: bleqq's runs, which
        // cost 7.47 this month, are not in it.
        const spend = page.locator('[data-spend]');
        await expect(spend).toContainText('6.25');
        await expect(spend).toContainText('7.00');
        await expect(page.locator('[data-agent-budget]')).toContainText("bleqq's watch runs at bleqq's cost and is not counted here.");
        await setCap(page, SEEDED_CAP);

        // A run that could take the month past the cap is not started.
        const runs = card.locator('[data-run-id]');
        await expect(runs.first()).toBeVisible();
        const before = await runs.count();
        const refused = page.waitForResponse((r) => /\/api\/v1\/agents\/[^/]+\/runs$/.test(r.url()) && r.request().method() === 'POST');
        await card.getByRole('button', { name: 'Run now' }).click();
        expect(((await (await refused).json()) as { code: string }).code).toBe('budget_cap_reached');
        await expect(card.getByText("This month's cap is reached, so nothing more runs until next month or until the cap is raised.")).toBeVisible();
        await expect(card.locator('[data-run-state="running"]')).toHaveCount(0);
        await expect(runs).toHaveCount(before);
        await expect(spend).toContainText('6.25');
      } finally {
        await restoreSeededAgent(page);
      }
      await signOut(page);

      // Tenant B switches all AI features off.
      await signInAs(page, LOGINS.secondBankAdmin);
      try {
        await setBankAi(page, false);

        // None of the bank's own agents runs, and bleqq's watch keeps running.
        await page.goto('/admin/agents');
        await expect(page.locator('[data-ai-enabled="false"]')).toContainText('so our own agents do not run. What bleqq watches keeps running.');

        // Ask answers feature_off before a model is asked.
        await page.goto('/ask');
        const asked = page.waitForResponse((r) => r.url().endsWith('/api/v1/ask') && r.request().method() === 'POST');
        await page.getByRole('searchbox', { name: 'Question' }).fill('What must we disclose about costs and charges?');
        await page.getByRole('button', { name: 'Ask', exact: true }).click();
        const answer = await asked;
        expect(answer.status()).toBe(403);
        expect(((await answer.json()) as { code: string }).code).toBe('feature_off');
        await expect(page.locator('[data-ask-feature-off]')).toContainText('Ask is switched off for your organisation. Search in the inventory still works.');
      } finally {
        await setBankAi(page, true);
      }
    });

    test("AGT-S7: Research requests ask an agent to check, research or re-tag", async ({ page, apiGuard }) => {
      // AGT-05, reworded to the split: tenant A's admin (agents.manage) asks the bank's own
      // agent to check a source and to research a topic; a library editor asks bleqq's agent
      // for a re-tag in the console. Each is a job whose run opens at once. The mock runner
      // files no batch, so the re-tag stays "being prepared" here; the batch it files is
      // proven by AGT-S7's integration test. The topic is the attempt's own, so a retry never
      // reads an earlier attempt's request. A request's run must fit under the cap as run
      // now's does, and the seeded month leaves no room, so the cap is raised first and put
      // back after, beside AGT-S5 and AGT-S6 rather than during them.
      test.setTimeout(120_000);
      allowFreshContext(apiGuard);
      const attempt = `${Date.now()}`;
      const topic = `DORA subcontracting ${attempt}`;

      await signInAs(page, LOGINS.admin);
      try {
        await openAgents(page);
        await setCap(page, '40.00');
        const checked = await askOurAgent(page, { source: 'fi.se sweep (E2E)' });
        const researched = await askOurAgent(page, { topic });
        expect([checked.kind, researched.kind]).toEqual(['check_source', 'research_topic']);
        expect(researched.tenantAgentId).toBe(checked.tenantAgentId);
        const ours = page.locator('[data-research-list]');
        await expect(ours.locator(`[data-research-request="${checked.id}"]`)).toContainText('Check this source now');
        await expect(ours.locator(`[data-research-request="${researched.id}"]`)).toContainText(topic);
      } finally {
        await restoreSeededAgent(page);
      }
      await signOut(page);

      await signInAs(page, LOGINS.editor);
      await page.goto('/console/queue');
      const retag = await askForRetag(page, { term: 'Custody', records: `Custody records that hold client money, attempt ${attempt}` });
      expect([retag.kind, retag.tenantAgentId]).toEqual(['retag', null]);
      await expect(page.locator('[data-retag-form]').getByText('Sent. The batch is being prepared.')).toBeVisible();
      await signOut(page);
    });
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

  // --- acc-summary-j11 (ACC-01, ACC-06, ACC-07, J-11) ---------------------------------------
  // The admin registers the entry and issues its key on the admin screens with a passkey;
  // the agent is the REST API and that key. Every entry is named for its attempt, so a retry
  // never reads an earlier one's, and every teardown revokes it, on failure too.

  test("ACC-S1: An entry is registered, narrowed to a department, and revoking it stops its credentials", async ({ page, playwright, apiGuard }) => {
    test.setTimeout(120_000);
    allowFreshContext(apiGuard);
    allowAccessStepUps(apiGuard);
    await signInAs(page, LOGINS.admin);
    const entryId = await registerEntry(page, { name: `Trading platform coding agent ${Date.now()}`, purpose: J11_PURPOSE, team: J11.team, departments: [J11.department] });
    let agent: APIRequestContext | undefined;
    try {
      // The key is shown once, and the entry lists it with no last use.
      const key = await issueEntryKey(page, entryId, 'Build server', ['library:read']);
      await expect(page.locator(`[data-key-id="${key.id}"]`)).toContainText('never used');
      await expect(page.locator('[data-plain-key]')).toHaveCount(0);
      agent = await agentWith(playwright, key.plainKey);
      // A duty of the department's products reads; one carrying only the card product
      // type answers 404, the answer another tenant would get.
      expect((await agent.get(`/api/v1/obligations/${J11.tradingObligations[0]}`)).status()).toBe(200);
      const card = await agent.get(`/api/v1/obligations/${J11.cardObligation}`);
      expect(card.status()).toBe(404);
      expect(await card.text()).not.toContain(J11.cardObligation);
      // Revoking the entry stops the key on its next call, and the security log shows it.
      await revokeEntry(page, entryId);
      expect((await agent.get(`/api/v1/obligations/${J11.tradingObligations[0]}`)).status()).toBe(401);
      await page.goto('/admin/security-log');
      await expect(page.locator('[data-event="key_revoked"]').first()).toBeVisible();
    } finally {
      await agent?.dispose();
      await revokeEntry(page, entryId);
    }
  });

  test("ACC-S6: A narrowed entry never narrows silently", async ({ page, playwright, apiGuard }) => {
    test.setTimeout(120_000);
    allowFreshContext(apiGuard);
    allowAccessStepUps(apiGuard);
    await signInAs(page, LOGINS.admin);
    const name = `Trading platform coding agent ${Date.now()}`;
    const entryId = await registerEntry(page, { name, purpose: J11_PURPOSE, team: J11.team, departments: [J11.department] });
    let agent: APIRequestContext | undefined;
    try {
      const key = await issueEntryKey(page, entryId, 'Build server', ['library:read']);
      agent = await agentWith(playwright, key.plainKey);
      const response = await agent.post('/api/v1/agent-access/what-applies', { data: { description: 'a feature that issues virtual cards against a trading account' } });
      expect(response.status(), await response.text()).toBe(200);
      const body = (await response.json()) as WhatApplies;
      // The answer states the entry, its departments and products and its "as of" date.
      expect(body.scope.narrowed).toBe(true);
      expect(body.scope.entry.name).toBe(name);
      expect(body.scope.departments.map((unit) => unit.name)).toEqual([J11.department]);
      expect(body.scope.asOf).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      // It names card issuing and cards among what it could not see, and says to ask compliance.
      const outside = body.outsideScope.terms.map((row) => `${row.dimension.label}: ${row.term.label}`);
      expect(outside).toContain('Licensed activity: Card issuing');
      expect(outside).toContain('Product type: Cards');
      expect(body.outsideScope.advice).toBe('ask_compliance');
      // No record carrying those terms appears anywhere in the response.
      expect(await response.text()).not.toContain(J11.cardObligation);
    } finally {
      await agent?.dispose();
      await revokeEntry(page, entryId);
    }
  });

  test("ACC-S13 J-11 @smoke: a bank's coding agent reads what applies to it", async ({ page, browser, playwright, apiGuard }, testInfo) => {
    test.setTimeout(240_000);
    allowFreshContext(apiGuard);
    allowAccessStepUps(apiGuard);
    // The second holder of security.manage works in a context of their own (four eyes).
    const security = await browser.newContext({ baseURL: testInfo.project.use.baseURL });
    const securityPage = await security.newPage();
    apiGuard.watch(securityPage);
    await signInAs(page, LOGINS.admin);
    // The admin registers the Trading team's coding agent, narrowed to Trading's products,
    // and issues it a key with a step-up.
    const entryId = await registerEntry(page, { name: `Trading platform coding agent ${Date.now()}`, purpose: J11_PURPOSE, team: J11.team, departments: [J11.department] });
    let agent: APIRequestContext | undefined;
    try {
      const key = await issueEntryKey(page, entryId, 'Build server', ['library:read', 'tenant:read']);
      // Two different people holding security.manage switch tenant reach on, and the
      // admin enables it on the entry.
      await signInAs(securityPage, LOGINS.securityAdmin);
      await switchTenantReachOn(page, securityPage);
      await enableEntryReach(page, entryId);

      // The agent asks what applies to a new order-routing service.
      agent = await agentWith(playwright, key.plainKey);
      const response = await agent.post('/api/v1/agent-access/what-applies', { data: { description: J11_DESCRIPTION } });
      expect(response.status(), await response.text()).toBe(200);
      const body = (await response.json()) as WhatApplies;
      // It receives the bank's confirmed applicability and reading, with citations.
      expect(body.registerRead).toBe('included');
      for (const stableKey of J11.tradingObligations) {
        const row = body.items.find((item) => item.stableKey === stableKey);
        expect(row, `${stableKey} is on the list`).toBeDefined();
        expect(row?.decision?.applicability).toBe('applies');
        expect(row?.decision?.applicabilityReason).toBeTruthy();
        expect(row?.decision?.interpretation).toBeTruthy();
        expect(row?.instrument.shortName).toBeTruthy();
        expect(row?.refLabel).toBeTruthy();
      }
      // The full list sits beneath a summary labelled as AI-drafted, citing it by stable key.
      expect(body.summary.status).toBe('drafted');
      expect(body.summary.aiGenerated).toBe(true);
      expect(body.summary.notice).toBe("AI-drafted guidance only: your bank's own confirmed applicability is the decision.");
      expect(body.summary.citations.length).toBeGreaterThan(0);
      for (const cited of body.summary.citations) expect(body.items.map((item) => item.stableKey)).toContain(cited);
      expect(body.total).toBeGreaterThanOrEqual(J11.tradingObligations.length);
      // A line names card issuing as outside its scope.
      expect(body.outsideScope.terms.map((row) => row.term.label)).toContain('Card issuing');
      expect(body.outsideScope.advice).toBe('ask_compliance');
      expect(await response.text()).not.toContain(J11.cardObligation);

      // A card obligation's stable key answers 404, and a write answers 403.
      expect((await agent.get(`/api/v1/obligations/${J11.cardObligation}`)).status()).toBe(404);
      const write = await agent.post('/api/v1/proposals', { data: {} });
      expect(write.status()).toBe(403);
      expect(((await write.json()) as { code: string }).code).toBe('read_only_credential');

      // Revoking the entry stops the agent's next call.
      await revokeEntry(page, entryId);
      expect((await agent.post('/api/v1/agent-access/what-applies', { data: { description: J11_DESCRIPTION } })).status()).toBe(401);
    } finally {
      // Teardown, on failure too: the entry revoked, no entry reaching the register, and the
      // organisation's reach off again, as every other journey expects it.
      await agent?.dispose();
      await revokeEntry(page, entryId);
      entriesReachOff();
      await switchTenantReachOff(page);
      await security.close();
    }
  });
  // --- end acc-summary-j11 -------------------------------------------------------------------
});
