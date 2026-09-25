import type { APIRequestContext, APIResponse, Page } from '@playwright/test';

import { destinations } from '@/shared/navigation/registry';

import { mintAgentKey, revokeAgentKey, type MintedAgentKey } from './support/agent-key';
import { expect, test } from './support/api-guard';
import { allowFreshContext, BACKEND_URL, LOGINS, restrictedScreen, signInAs, signOut } from './support/passkeys';

// proposals: the @e2e scenarios from backend/apps/proposals/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.
//
// PRO-S3, PRO-S4 and PRO-S7 decide the new_obligation_version proposals
// backend/apps/shared/e2e_seed.py leaves waiting for them (EXPECTED_PROPOSALS). Each
// targets an obligation no other spec names, so the journeys never race each other or
// J-6. PRO-S5 and PRO-S9 decide a vocabulary proposal the journey proposes itself,
// through the console's own "Suggest a change" door (VOC-07), with a label unique to
// the attempt so a retry or a parallel run never collides on the near-duplicate check.
//
// No assertion here reads today's date against a seeded one: the versions these
// approvals write take effect on fixed legal dates, so a journey proves the version
// by the obligation card's version list, which holds every version whatever the day,
// never by the inventory row's "Version 2", which names only a version still ahead.

const APPROPRIATENESS_TITLE = 'Add version 2 of the appropriateness assessment obligation, in force 15 October 2026';
const COSTS_CHARGES_TITLE = 'Add version 2 of the costs and charges obligation, extending it to professional clients';
// PRO-S7 (e2e_seed.py PRO_S7_OBLIGATION): the proposal the console decides, and the
// duty's own title the bank then reads it under, never the proposal's.
const AUTOMATED_DECISIONS_TITLE = 'Add version 2 of the automated decisions obligation, with a review by a person within one month';
const AUTOMATED_DECISIONS_SOURCE = 'EUR-Lex, Regulation (EU) 2016/679, Article 22, consolidated text';
const AUTOMATED_DECISIONS_OBLIGATION = 'Apply safeguards to solely automated decisions with significant effects';
// PRO-S13 (e2e_seed.py PRO_S13_OBLIGATION): the sweeper's proposal the confirming agent
// decides through the API, and what that agent sends with its decision: the model call
// behind it (D-80, AUD-02), citing the page the proposal cites.
const PRO_S13_TITLE = 'Add version 2 of the demands and needs obligation, with the suitability assessment kept on file';
const PRO_S13_SOURCE = 'Finansinspektionen, amended insurance distribution rules';
const PRO_S13_URL = 'https://www.fi.se/';
const CONFIRMER_MODEL = 'confirmer pipeline 1.0';
const CONFIRMER_NOTE = 'The wording and the date match the amended rules the proposal cites.';
const CONFIRMER_DECISION = {
  model: CONFIRMER_MODEL,
  modelVersion: '2026-05-01',
  promptTemplate: 'library-confirmer/decide/v1',
  promptHash: 'e2e-pro-s13',
  output: 'Approve. The proposed wording and date match the amended rules at the cited page.',
  citations: [{ label: PRO_S13_SOURCE, url: PRO_S13_URL }],
};
const CONFIRMER_STATS = { modelCalls: 1, fetches: 1, sourcesChecked: 0, changesRegistered: 0, proposalsSubmitted: 0 };
// The console's destinations, read from the registry (src/shared/navigation/registry.ts)
// and never from a list written here, as ADM-S4 reads them.
const CONSOLE_HREFS: readonly string[] = destinations.filter((d) => d.surface === 'console').map((d) => d.href);

/** The queue has settled when its rows or its empty state is on screen (states.html). */
async function queueSettled(page: Page): Promise<void> {
  await expect(page.locator('[data-proposal-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
}

/** Opens a proposal's detail by title, whichever tab it is decided under (a retry finds it Approved or Rejected rather than Waiting). */
async function openProposal(page: Page, titleFragment: RegExp): Promise<void> {
  await page.goto('/console/queue');
  await queueSettled(page);
  for (const tab of ['Waiting', 'Approved', 'Rejected']) {
    await page.getByRole('tab', { name: tab }).click();
    await queueSettled(page);
    const row = page.getByRole('link', { name: titleFragment });
    if ((await row.count()) > 0) {
      await row.first().click();
      await expect(page.getByRole('heading', { level: 1, name: titleFragment })).toBeVisible();
      return;
    }
  }
  throw new Error(`No proposal titled ${titleFragment} in any tab of the queue.`);
}

/** Approve and apply, through the global step-up dialog; settles on "waiting or already applied" so a retry passes. */
async function approveAndApply(page: Page): Promise<void> {
  const applied = page.locator('[data-proposal-applied]');
  const approve = page.getByRole('button', { name: 'Approve and apply' });
  await expect(applied.or(approve).first()).toBeVisible();
  if (await approve.isVisible()) {
    await approve.click();
    const prompt = page.getByRole('dialog', { name: 'Confirm with your passkey' });
    await expect(prompt.or(applied).first()).toBeVisible();
    if (await prompt.isVisible()) await prompt.getByRole('button', { name: 'Use passkey' }).click();
  }
  await expect(applied).toBeVisible();
}

/**
 * The tenant reader opens the obligation's own card from the inventory and finds the version
 * the approval wrote in its version list, which holds every version whatever today's date.
 */
async function expectVersionOnCard(page: Page, stableKey: string, versionNumber: number): Promise<void> {
  await page.goto('/inventory');
  await expect(page.locator('[data-obligation-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
  await page.locator(`[data-obligation="${stableKey}"]`).click();
  await expect(page.locator(`[data-versions-panel] [data-version-row="${versionNumber}"]`)).toBeVisible();
}

/** A vocabulary proposal made live, through the console's own door (VOC-07), with a label unique to the attempt. */
async function proposeFlag(page: Page, label: string): Promise<void> {
  await page.goto('/console/vocabularies');
  await expect(page.getByRole('heading', { level: 1, name: 'Vocabularies' })).toBeVisible();
  await page.locator('[data-vocabulary-list="flag"]').click();
  await page.getByRole('button', { name: 'Suggest a change' }).click();
  const dialog = page.getByRole('dialog', { name: 'Add a value' });
  await dialog.getByLabel('Label', { exact: true }).fill(label);
  await dialog.getByRole('button', { name: 'Send for review' }).click();
  await expect(dialog.getByText(/is waiting for review\.$/)).toBeVisible();
  await dialog.getByRole('button', { name: 'Done' }).click();
}

/** What the journey reads of a queue row or a proposal's detail (GET /proposals, GET /proposals/{id}). */
interface QueueDetail {
  id: string;
  title: string;
  status: string;
  isMine: boolean;
  sourceLabel: string;
  proposedByAgent: { key: string } | null;
  reviewedByAgent: { key: string } | null;
  sources: { field: string; label: string; url: string }[];
  diff: unknown[];
}

/** The calls an agent makes with its own key, as its pipeline makes them: straight to the API, never through a page. */
function agentCalls(request: APIRequestContext, plainKey: string) {
  const url = (path: string) => `${BACKEND_URL}/api/v1${path}`;
  return {
    get: (path: string): Promise<APIResponse> => request.get(url(path), { headers: { 'X-API-Key': plainKey } }),
    send: (method: 'post' | 'patch', path: string, data: object): Promise<APIResponse> =>
      request[method](url(path), { headers: { 'X-API-Key': plainKey, 'Idempotency-Key': crypto.randomUUID() }, data }),
  };
}

/** PRO-S13's seeded proposal, as the confirming agent reads it: waiting, or already approved by an earlier attempt of this journey. */
async function findSeededProposal(agent: ReturnType<typeof agentCalls>): Promise<QueueDetail> {
  for (const status of ['open', 'approved']) {
    const page = await agent.get(`/proposals?status=${status}&kind=new_obligation_version&limit=100`);
    expect(page.status(), await page.text()).toBe(200);
    const row = ((await page.json()) as { items: QueueDetail[] }).items.find((item) => item.title === PRO_S13_TITLE);
    if (row !== undefined) return row;
  }
  throw new Error(`No proposal titled ${PRO_S13_TITLE} waiting or approved.`);
}

test.describe('proposals journeys', () => {
  // PRO-S3 and PRO-S4 take the two `new_obligation_version` proposals the seed leaves in
  // the queue, and both then read the same seeded reader's inventory to prove the version
  // arrived. Run side by side they race over that one reader's session and over which
  // proposal each finds, and either can fail looking for a proposal the other has just
  // decided. They are serial here until `chunk4-T8` lands, which lets a journey seed a
  // proposal of its own the way PRO-S5 and PRO-S9 already mint their own vocabulary rows.
  test.describe.configure({ mode: 'serial' });

  test('PRO-S3: Approval applies payload, version, audit row and re-index in one transaction', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    // The first approve attempt always answers 403 step_up_required, which is what opens
    // the passkey prompt (playbook 4.2); approveAndApply() confirms it.
    apiGuard.allow(/\/proposals\/.+\/approve$/, 403, 'approving asks for a fresh passkey assertion first, which opens the step-up prompt');
    await signInAs(page, LOGINS.editor);
    await openProposal(page, new RegExp(APPROPRIATENESS_TITLE));
    await approveAndApply(page);
    await expect(page.getByText(/^Applied/)).toBeVisible();
    await signOut(page);

    // A tenant reader finds the version this approval just wrote on the obligation's own
    // card. Its effective date is a fixed legal date, so the version list is read rather
    // than the inventory row, whose "Version 2" goes once that date has passed.
    await signInAs(page, LOGINS.reader);
    await expectVersionOnCard(page, 'obl-appropriateness', 2);
  });

  test('PRO-S4: The reviewer corrects scope and wording before approving', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/proposals\/.+\/approve$/, 403, 'approving asks for a fresh passkey assertion first, which opens the step-up prompt');
    await signInAs(page, LOGINS.editor2);
    await openProposal(page, new RegExp(COSTS_CHARGES_TITLE));

    const applied = page.locator('[data-proposal-applied]');
    const form = page.locator('[data-proposal-correction]');
    if (await form.isVisible()) {
      // The scope term the reviewer disagrees with (backend/apps/shared/e2e_seed.py):
      // removed before approving. "Professional" is the seeded taxonomy term's own
      // label (apps/taxonomy/seeds/fixture.py), never catalog copy, so it is found by
      // pattern rather than a literal the copy-drift check would look for in the catalogs.
      await form.getByRole('button', { name: /^Professional/ }).click();
      const english = form.getByLabel(/^Text \(English\)/);
      const original = await english.inputValue();
      await english.fill(`${original} A library editor confirmed this wording for PRO-S4.`);
      // Every corrected value names the source the reviewer read it in.
      await form.getByLabel('Source of your correction', { exact: true }).fill('https://www.fi.se/');
      await form.getByRole('button', { name: 'Approve and apply' }).click();
      const prompt = page.getByRole('dialog', { name: 'Confirm with your passkey' });
      await expect(prompt.or(applied).first()).toBeVisible();
      if (await prompt.isVisible()) await prompt.getByRole('button', { name: 'Use passkey' }).click();
    }
    await expect(applied).toBeVisible();
    await signOut(page);

    // As PRO-S3: the corrected version reaches the tenant's own card for the obligation.
    await signInAs(page, LOGINS.reader);
    await expectVersionOnCard(page, 'obl-costs-charges', 2);
  });

  test('PRO-S5: Approving your own proposal answers four_eyes_violation', async ({ page, apiGuard }, testInfo) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.editor);
    const label = `PRO-S5 four eyes ${testInfo.workerIndex}-${Date.now()}`;
    await proposeFlag(page, label);

    // Confirmed where it was sent: the console queue, under Waiting, marked Yours.
    await page.goto('/console/queue');
    await queueSettled(page);
    const row = page.getByRole('link', { name: new RegExp(label) });
    await expect(row).toBeVisible();
    await expect(row.getByText('Yours')).toBeVisible();
    await row.click();

    // The server enforces four eyes; the screen only explains it. No Approve control is
    // offered on a reader's own proposal, so the refusal can never be attempted from here
    // (backend/apps/proposals/logic.py `_decidable` answers 409 four_eyes_violation to
    // anyone who calls the route directly, proven at the integration level).
    await expect(page.getByText('You proposed this.')).toBeVisible();
    await expect(page.getByText('Someone else has to approve it.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Approve and apply' })).toHaveCount(0);
  });

  test('PRO-S7: The queue is in the console and tenants see updates and report problems', async ({ page, apiGuard }) => {
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/proposals\/.+\/approve$/, 403, 'approving asks for a fresh passkey assertion first, which opens the step-up prompt');
    apiGuard.allow(/^\/api\/v1\/console\/problem-reports$/, 404, "the console has no problem-report route: a bank's report stays inside the bank");

    // The editor opens the queue in the console and reads the source beside what changes
    // before approving with a passkey. A retry finds the proposal already applied.
    await signInAs(page, LOGINS.editor);
    await openProposal(page, new RegExp(AUTOMATED_DECISIONS_TITLE));
    const proposal = page.locator('[data-proposal]');
    await expect(proposal.locator('[data-proposal-changes]')).toBeVisible();
    await expect(proposal).toContainText(AUTOMATED_DECISIONS_SOURCE);
    await expect(proposal.locator('a[href="https://eur-lex.europa.eu/"]').first()).toBeVisible();
    await approveAndApply(page);
    // The console offers no surface for a bank's problem report: its rail draws only the
    // registry's console destinations, the queue among them, and the registry holds none
    // for a report.
    const railHrefs = await page.getByRole('navigation', { name: 'Main' }).locator('a').evaluateAll((links) => links.map((link) => link.getAttribute('href') ?? ''));
    expect(railHrefs).toContain('/console/queue');
    expect(railHrefs.filter((href) => !CONSOLE_HREFS.includes(href))).toEqual([]);
    expect(CONSOLE_HREFS.filter((href) => /report/.test(href))).toEqual([]);
    await signOut(page);

    // A bank's compliance officer has no queue: the tenant rail offers no console
    // destination, and the console's review screen is restricted. That screen refuses in
    // the client before any request is made; the server's own 403 on the queue routes is
    // test_pro_s7's.
    await signInAs(page, LOGINS.complianceOfficer);
    const tenantRail = page.getByRole('navigation', { name: 'Main' });
    await expect(tenantRail.locator('a[href="/inventory"]')).toBeVisible();
    await expect(tenantRail.locator('a[href^="/console"]')).toHaveCount(0);
    await page.goto('/console/queue');
    await expect(restrictedScreen(page)).toContainText('Needs proposals review');

    // The bank reads the change as a library update, under the duty's own title and never
    // the proposal's, and says it looks wrong through the same form the obligation card uses.
    await page.goto('/inventory/updates');
    await expect(page.locator('[data-update-days]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
    const row = page.locator('[data-update-id]').filter({ has: page.getByRole('heading', { level: 3, name: AUTOMATED_DECISIONS_OBLIGATION, exact: true }) }).first();
    await expect(row).toBeVisible();
    await expect(row).not.toContainText(AUTOMATED_DECISIONS_TITLE);
    await expect(row.getByRole('link', { name: 'Show what changed' })).toHaveAttribute('href', /^\/inventory\/obligations\/[0-9a-f-]{36}$/);
    await row.getByRole('button', { name: 'This looks wrong' }).click();
    const dialog = page.getByRole('dialog', { name: 'What looks wrong?' });
    await expect(dialog.getByText('Colleagues in your organisation read this and take it up. It reaches nobody outside your organisation.')).toBeVisible();
    await dialog.getByLabel('What you see').fill('The one-month review period is not in the consolidated text we read.');
    await dialog.getByRole('button', { name: 'Send report' }).click();
    await expect(dialog.getByText('Report sent. Thank you.')).toBeVisible();
    await dialog.getByRole('button', { name: 'Done' }).click();
    await expect(dialog).toBeHidden();

    // The console has no problem-report route: the address answers 404. This request
    // carries no session, so it proves only the route's absence; that no platform session
    // reads the report back is proven route by route in test_pro_s7.
    const consoleReports = await page.goto(`${BACKEND_URL}/api/v1/console/problem-reports`);
    expect(consoleReports?.status()).toBe(404);
  });

  test.fixme('PRO-S8: A batch proposal previews and is approved whole or row by row', async () => {
    // pending: PRO-S8 (PRO-04)
  });

  test('PRO-S9: A rejection needs a reason and is audited', async ({ page, apiGuard }, testInfo) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.editor);
    const label = `PRO-S9 reject ${testInfo.workerIndex}-${Date.now()}`;
    await proposeFlag(page, label);
    await signOut(page);
    await signInAs(page, LOGINS.editor2);

    // The label is unique to this attempt, so this proposal is always freshly waiting:
    // no "already decided" branch is needed, unlike PRO-S3 and PRO-S4's seeded fixtures.
    const rejected = page.locator('[data-proposal-rejected]');
    await openProposal(page, new RegExp(label));
    await page.getByRole('button', { name: 'Reject' }).click();
    const dialog = page.getByRole('dialog', { name: 'Reject this proposal' });
    const submit = dialog.getByRole('button', { name: 'Reject' });
    // Neither a reason nor a note yet: the button stays disabled, so the 422
    // reason_required the server would otherwise answer is never sent (PRO-01,
    // proven directly against the route in backend/apps/proposals/tests_scenarios.py).
    await expect(submit).toBeDisabled();
    await dialog.getByLabel('Reason').selectOption({ label: 'Poor wording' });
    await expect(submit).toBeDisabled();
    await dialog.getByLabel('Note').fill('The label needs tightening before this can be used.');
    await expect(submit).toBeEnabled();
    await submit.click();
    await expect(rejected).toBeVisible();
    await expect(rejected).toContainText('The label needs tightening before this can be used.');
  });

  test('PRO-S13: An independent agent confirms a proposal from the same queue', async ({ page, browser, request, apiGuard }) => {
    // The console mints the confirming agent's keys (support/agent-key.ts) in a context of
    // its own, which stays signed in so the teardown can revoke them whatever happens.
    const keysContext = await browser.newContext();
    const keysPage = await keysContext.newPage();
    apiGuard.watch(keysPage);
    const stamp = Date.now();
    const keys: MintedAgentKey[] = [];
    try {
      const confirmer = await mintAgentKey(keysPage, apiGuard, {
        name: `PRO-S13 confirmer ${stamp}`,
        agent: 'library-confirmer',
        scopes: ['agent-runs:write', 'proposals:review'],
      });
      keys.push(confirmer);
      const unscoped = await mintAgentKey(keysPage, apiGuard, { name: `PRO-S13 without review ${stamp}`, agent: 'library-confirmer', scopes: ['agent-runs:write'] });
      keys.push(unscoped);
      const agent = agentCalls(request, confirmer.plainKey);

      // The confirming agent opens a run of its own key and reads the queue a person reads.
      const run = await agent.send('post', '/agent-runs', { agent: 'library-confirmer', model: CONFIRMER_MODEL, pipelineVersion: '1' });
      expect(run.status(), await run.text()).toBe(201);
      const runId = ((await run.json()) as { id: string }).id;
      const found = await findSeededProposal(agent);
      if (found.status === 'open') {
        // It sees the sweeper's proposal, not its own, with the source beside the diff.
        const detail = await agent.get(`/proposals/${found.id}`);
        expect(detail.status()).toBe(200);
        const body = (await detail.json()) as QueueDetail;
        expect([body.proposedByAgent?.key, body.isMine]).toEqual(['watch-sweeper', false]);
        expect(body.sourceLabel).toBe(PRO_S13_SOURCE);
        expect(body.sources.map((source) => source.url)).toContain(PRO_S13_URL);
        expect(body.diff.length).toBeGreaterThan(0);

        // It approves through the same route, with the model call behind the decision and the run it made it in.
        const approved = await agent.send('post', `/proposals/${found.id}/approve`, { note: CONFIRMER_NOTE, decision: CONFIRMER_DECISION, agentRunId: runId });
        expect(approved.status(), await approved.text()).toBe(200);
        expect(((await approved.json()) as QueueDetail).reviewedByAgent?.key).toBe('library-confirmer');
      } else {
        // A retry: the earlier attempt's approval stands, and it was the confirming agent's.
        expect(found.reviewedByAgent?.key).toBe('library-confirmer');
      }
      const closed = await agent.send('patch', `/agent-runs/${runId}`, { status: 'succeeded', stats: CONFIRMER_STATS, error: null });
      expect(closed.status(), await closed.text()).toBe(200);

      // A key of the same agent without the review scope is refused at the queue itself.
      apiGuard.allow(/^\/api\/v1\/proposals$/, 403, 'a key without proposals:review may not read the queue (permission_denied)');
      const refused = await agentCalls(request, unscoped.plainKey).get('/proposals?status=open');
      expect(refused.status()).toBe(403);
      expect(((await refused.json()) as { code: string }).code).toBe('permission_denied');
    } finally {
      // Teardown that runs on failure too: no key minted here outlives the attempt.
      for (const key of keys) await revokeAgentKey(keysPage, key.id);
      await keysContext.close();
    }

    // The library editor finds it under Approved, decided by the agent, machine-confirmed.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.editor);
    await page.goto('/console/queue');
    await queueSettled(page);
    await page.getByRole('tab', { name: 'Approved' }).click();
    await queueSettled(page);
    await page.getByRole('link', { name: new RegExp(PRO_S13_TITLE) }).first().click();
    await expect(page.getByRole('heading', { level: 1, name: new RegExp(PRO_S13_TITLE) })).toBeVisible();
    const applied = page.locator('[data-proposal-applied]');
    await expect(applied).toContainText(/by the agent library-confirmer, machine-confirmed\./);
    await expect(applied).toContainText(CONFIRMER_NOTE);
    await expect(page.locator('[data-proposal]')).toContainText(PRO_S13_SOURCE);
    await signOut(page);

    // The bank's reader finds version 2 on the obligation's card, labelled as the agents'
    // and never as a person's.
    await signInAs(page, LOGINS.reader);
    await expectVersionOnCard(page, 'obl-idd-demands-needs', 2);
    await expect(page.locator('[data-versions-panel] [data-version-row="2"] [data-machine-confirmed]')).toContainText(/proposed by watch-sweeper, confirmed by library-confirmer/);
  });
});

// The bank's own queue (PRD 0.7, OWN-03): stays test.fixme until chunk 11 builds it.
test.describe("the bank's own queue", () => {
  test.fixme("PRO-S15: The bank's own queue decides what its own agent filed", async () => {
    // pending: PRO-S15 (OWN-03, INV-07, PRO-03, AC-OWN1, chunk 11)
  });
});
