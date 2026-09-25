import type { Page } from '@playwright/test';

import { destinations, type Destination } from '@/shared/navigation/registry';

import { expect, test } from './support/api-guard';
import { allowFreshContext, BACKEND_URL, inviteLinkFrom, LOGINS, mailOutbox, mailsTo, restrictedScreen, signInAs, signOut } from './support/passkeys';

// governance: the @e2e scenarios from backend/apps/governance/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.
//
// ADM-S4 reads the console from the registry (src/shared/navigation/registry.ts),
// never from a list written here, so a console destination a later chunk adds
// joins the role matrix with no edit to this file.

const CONSOLE_DESTINATIONS: readonly Destination[] = destinations.filter((d) => d.surface === 'console');

/** The grant the Restricted screen names, in plain words (humanisePermission, require-permission.tsx). */
function missingGrant(destination: Destination): string {
  return (destination.anyOfPermissions[0] ?? '').replace(/[._]/g, ' ');
}

/**
 * Signs the login in, then walks every console destination the registry holds:
 * the ones in their rail must open, the rest must refuse by address. Returns
 * the ids of the ones they hold, so the journey can prove the two platform
 * roles divide the console between them.
 */
async function consoleDestinationsOf(page: Page, login: string): Promise<string[]> {
  await signInAs(page, login);
  await page.goto('/console');
  const nav = page.getByRole('navigation', { name: 'Main' });
  // The landing sends each person on to their first destination: settle there
  // before reading the rail.
  await expect(page).not.toHaveURL(/\/console$/);
  // By address, not by label: the registry is the only list, and a spec that
  // read the catalog could not run under Playwright's JSON-free loader.
  const link = (destination: Destination) => nav.locator(`a[href="${destination.href}"]`);

  const mine: Destination[] = [];
  const theirs: Destination[] = [];
  for (const destination of CONSOLE_DESTINATIONS) {
    ((await link(destination).count()) > 0 ? mine : theirs).push(destination);
  }
  expect(mine.length, `${login} holds no console destination`).toBeGreaterThan(0);

  for (const destination of mine) {
    await link(destination).click();
    await expect(page).toHaveURL(new RegExp(`${destination.href}$`));
    await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible();
    await expect(restrictedScreen(page)).toHaveCount(0);
  }

  for (const destination of theirs) {
    await page.goto(destination.href);
    // The client gate refuses before any request is made, so the API guard
    // sees no 403 here; the server's own refusal is ADM-S4's integration half.
    await expect(restrictedScreen(page)).toBeVisible();
    await expect(restrictedScreen(page)).toContainText(missingGrant(destination));
    await expect(link(destination)).toHaveCount(0);
  }
  return mine.map((destination) => destination.id);
}

/** The research payment obligation's card, reached from the inventory filtered to its instrument. */
async function openResearchObligation(page: Page): Promise<void> {
  await page.goto('/inventory?instrument=fffs-2017-2');
  await expect(page.locator('[data-obligation-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
  await page.locator('[data-obligation="obl-research-payments"]').click();
  await expect(page.locator('[data-obligation="obl-research-payments"] [data-header-pills]')).toBeVisible();
}

test.describe('governance journeys', () => {
  test("AUD-S3: The audit log screen shows who did what, with before and after", async ({ page, apiGuard }) => {
    // pending: AUD-S3 (AUD-01) -> built in chunk 4. The record changed with step-up is an
    // API key: creating one is the shortest action in R1 that asks for a passkey. The
    // reader then reads the log, because audit.read is in every system role and the log is
    // the tenant's, not the actor's.
    allowFreshContext(apiGuard);
    apiGuard.allow(/\/tenant\/api-keys$/, 403, 'creating a key answers step_up_required first and opens the prompt');
    await signInAs(page, LOGINS.admin);
    await page.goto('/admin/api-keys');
    await page.getByRole('button', { name: 'Create a key' }).click();
    const form = page.locator('[data-key-form]');
    await form.getByLabel('Name', { exact: true }).fill('Audit log evidence');
    await form.locator('label', { hasText: /^tenant read/ }).getByRole('checkbox').check();
    // The key this run created, pinned by id: the log is filtered to it, never counted.
    const created = page.waitForResponse((r) => r.url().endsWith('/api/v1/tenant/api-keys') && r.request().method() === 'POST' && r.ok());
    await form.getByRole('button', { name: 'Create key' }).click();
    const prompt = page.getByRole('dialog', { name: 'Confirm with your passkey' });
    await expect(prompt).toBeVisible();
    await prompt.getByRole('button', { name: 'Use passkey' }).click();
    const { id: keyId } = (await (await created).json()) as { id: string };
    const keyRow = page.locator(`[data-key-id="${keyId}"]`);
    await expect(keyRow).toBeVisible();

    try {
      // A reader holds audit.read and nothing else of Admin's sections.
      await signOut(page);
      await signInAs(page, LOGINS.reader);
      await page.goto('/admin');
      await expect(page.locator('[data-admin-section="admin-organisation"]')).toBeVisible();
      await expect(page.locator('[data-admin-section="admin-audit-log"]')).toBeVisible();
      for (const section of ['admin-members', 'admin-roles', 'admin-vocabularies', 'admin-footprint', 'admin-api-keys', 'admin-security-log']) {
        await expect(page.locator(`[data-admin-section="${section}"]`)).toHaveCount(0);
      }
      await page.locator('[data-admin-section="admin-audit-log"]').click();
      await expect(page).toHaveURL(/\/admin\/audit-log$/);
      await expect(page.getByRole('heading', { level: 1, name: 'Audit log' })).toBeVisible();

      // Filter to the kind, then find the event this run wrote.
      await page.getByLabel('Record kind').selectOption('api_key');
      const event = page.locator(`[data-audit-row][data-subject-id="${keyId}"][data-action="api_key.created"]`);
      await expect(event).toBeVisible();
      await expect(event).toContainText('Audit log evidence');
      await expect(event).toContainText('By Erik Holm');
      await expect(event).toContainText('api key created');
      await expect(event.locator('time')).toHaveAttribute('datetime', /^\d{4}-\d{2}-\d{2}T/);
      // Before and after are the snapshot's own fields, as data.
      await expect(event.locator('[data-audit-diff] [data-field="scopes"] [data-after]')).toContainText('tenant:read');
      await expect(event.locator('[data-audit-diff] [data-field="scopes"] [data-before]')).toHaveText('Not set');
      // The passkey marker: this action was completed with a step-up.
      await expect(event.getByText('Confirmed with a passkey')).toBeVisible();

      // Filtering to that record leaves the log showing it and nothing else.
      await event.locator('[data-only-record]').click();
      await expect(page.getByRole('button', { name: 'Record: Audit log evidence ✕' })).toBeVisible();
      await expect(event).toBeVisible();
      await expect(page.locator(`[data-audit-row]:not([data-subject-id="${keyId}"])`)).toHaveCount(0);
    } finally {
      // Teardown that runs on failure too: a live key never outlives the attempt.
      await signOut(page);
      await signInAs(page, LOGINS.admin);
      await page.goto('/admin/api-keys');
      await expect(keyRow).toBeVisible();
      if ((await keyRow.getByRole('button', { name: 'Revoke' }).count()) > 0) {
        await keyRow.getByRole('button', { name: 'Revoke' }).click();
        await keyRow.getByRole('button', { name: 'Revoke' }).click();
        await expect(keyRow).toContainText('Revoked');
      }
    }
  });

  test("AUD-S4: Every model output is logged with its review state", async ({ page, apiGuard }, testInfo) => {
    // AUD-02: a reader asks, marks the answer wrong with a reason, and an approver, who
    // holds ai_log.read, finds that answer in the AI log with the verdict and the reason,
    // still labelled AI because nobody confirmed it. The answer this run wrote is pinned
    // by the id its feedback was posted to, never by a count. The integration half
    // (the So what? review state per bank) is governance's tests_scenarios.py.
    allowFreshContext(apiGuard);
    const reason = `AUD-S4 misses the exemption ${Date.now().toString(36)}-${testInfo.retry}`;

    await signInAs(page, LOGINS.reader);
    await page.goto('/search?mode=ask');
    await page.getByRole('searchbox', { name: 'Question' }).fill('What does the appropriateness assessment require?');
    await page.getByRole('button', { name: 'Ask', exact: true }).click();
    const answer = page.locator('[data-ask-answer="done"]');
    await expect(answer).toBeVisible();
    await answer.getByRole('button', { name: 'Wrong', exact: true }).click();
    await answer.getByLabel('What is wrong?').fill(reason);
    const rated = page.waitForResponse((r) => /\/api\/v1\/answers\/[^/]+\/feedback$/.test(r.url()) && r.request().method() === 'POST' && r.ok());
    await answer.getByRole('button', { name: 'Send', exact: true }).click();
    const answerId = /\/answers\/([^/]+)\/feedback$/.exec((await rated).url())?.[1] ?? '';
    expect(answerId).not.toBe('');
    await expect(answer.getByText('Thank you. Your feedback is logged with the answer.')).toBeVisible();

    // A reader holds no ai_log.read: Admin does not offer the AI log.
    await page.goto('/admin');
    await expect(page.locator('[data-admin-section="admin-audit-log"]')).toBeVisible();
    await expect(page.locator('[data-admin-section="admin-ai-log"]')).toHaveCount(0);

    await signOut(page);
    await signInAs(page, LOGINS.approver);
    await page.goto('/admin');
    await page.locator('[data-admin-section="admin-ai-log"]').click();
    await expect(page).toHaveURL(/\/admin\/ai-log$/);
    await expect(page.getByRole('heading', { level: 1, name: 'AI log' })).toBeVisible();

    await page.getByLabel('Purpose').selectOption('answer');
    await page.getByLabel('Review').selectOption('draft');
    const row = page.locator(`[data-ai-row][data-generation-id="${answerId}"]`);
    await expect(row).toBeVisible();
    await expect(row).toHaveAttribute('data-purpose', 'answer');
    await expect(row).toHaveAttribute('data-status', 'draft');
    await expect(row).toHaveAttribute('data-feedback', 'wrong');
    await expect(row.getByText('Ask answer', { exact: true })).toBeVisible();
    await expect(row.getByText('Not yet reviewed', { exact: true })).toBeVisible();
    await expect(row.getByText('Marked wrong', { exact: true })).toBeVisible();
    await expect(row.locator('time')).toHaveAttribute('datetime', /^\d{4}-\d{2}-\d{2}T/);

    await row.getByRole('button', { name: 'Show what it wrote' }).click();
    const output = row.locator('[data-ai-output]');
    await expect(output.getByText('Written by AI. No person has confirmed it.')).toBeVisible();
    await expect(output.locator('[data-feedback-note]')).toHaveText(`Reason given: ${reason}`);
    await expect(output.getByRole('list', { name: 'Sources' }).getByRole('link').first()).toBeVisible();
  });

  test("AUD-S5: A problem report stays inside the bank that filed it", async ({ page, apiGuard }, testInfo) => {
    // A reader of tenant A files a report through the obligation card; the bank's
    // compliance officer reads it on the same card and closes it with a note; the reader
    // sees it closed; tenant B's administrator, who reads every report of their own bank,
    // sees nothing of it. The report is this run's own, pinned by id, so the seeded open
    // report and earlier runs' closed ones never decide an assertion. The 403 and 404 of a
    // library editor, another bank, an API key and an agent, and the report's words kept
    // out of every log, outbox payload and model, are test_aud_s5's.
    allowFreshContext(apiGuard);
    const words = `The summary names only the institution's own resources (AUD-S5 ${testInfo.workerIndex}-${Date.now()}).`;
    const note = 'Version 2 names a research payment account as well; the watch has it.';

    await signInAs(page, LOGINS.reader);
    await openResearchObligation(page);
    const obligationUrl = new URL(page.url()).pathname;
    const provenance = page.locator('[data-provenance-panel]');
    await provenance.getByRole('button', { name: 'This looks wrong' }).click();
    const dialog = page.getByRole('dialog', { name: 'What looks wrong?' });
    // The dialog says who reads it: the bank, and nobody outside it, bleqq included.
    await expect(dialog.getByText('Colleagues in your organisation read this and take it up. It reaches nobody outside your organisation.')).toBeVisible();
    await dialog.getByLabel('What you see').fill(words);
    const filed = page.waitForResponse((r) => /\/api\/v1\/obligations\/[0-9a-f-]{36}\/problem-reports$/.test(r.url()) && r.request().method() === 'POST' && r.ok());
    await dialog.getByRole('button', { name: 'Send report' }).click();
    const { id: reportId } = (await (await filed).json()) as { id: string };
    await dialog.getByRole('button', { name: 'Done' }).click();

    // The reader's own report joins the record's section at once, open, and the section
    // says a close never changes the library: the watch corrects it.
    const section = page.locator('[data-problem-reports]');
    const mine = section.locator(`[data-report-id="${reportId}"]`);
    await expect(mine).toHaveAttribute('data-report-status', 'open');
    await expect(mine).toContainText(words);
    await expect(section.getByText('Reports stay inside your organisation. Closing one does not change the library: when a record is wrong, the watch re-checks it against its source and proposes the correction.')).toBeVisible();
    await signOut(page);

    // The compliance officer holds proposals.create: every report of the bank on this
    // record, with who filed it and what they had on screen, and the close.
    await signInAs(page, LOGINS.complianceOfficer);
    await page.goto(obligationUrl);
    const theirs = page.locator(`[data-problem-reports] [data-report-id="${reportId}"]`);
    await expect(theirs).toContainText(words);
    await expect(theirs).toContainText('Reported by Oskar Lund');
    await expect(theirs.getByText('Open', { exact: true })).toBeVisible();
    await theirs.getByRole('button', { name: 'Close report' }).click();
    const close = page.getByRole('dialog', { name: 'Close this report' });
    await expect(close.getByRole('button', { name: 'Close report' })).toBeDisabled();
    await close.getByLabel('Outcome').selectOption('answered');
    await close.getByLabel('Note for the reporter').fill(note);
    await close.getByRole('button', { name: 'Close report' }).click();
    await expect(close).toBeHidden();
    await expect(theirs).toHaveAttribute('data-report-status', 'answered');
    await expect(theirs.locator('[data-report-note]')).toHaveText(note);
    await expect(theirs).toContainText('Closed by Sara Lindqvist');
    await expect(theirs.getByRole('button', { name: 'Close report' })).toHaveCount(0);
    await signOut(page);

    // The reader sees their report closed, with the note and who closed it.
    await signInAs(page, LOGINS.reader);
    await page.goto(obligationUrl);
    const closed = page.locator(`[data-problem-reports] [data-report-id="${reportId}"]`);
    await expect(closed).toHaveAttribute('data-report-status', 'answered');
    await expect(closed.getByText('Answered', { exact: true })).toBeVisible();
    await expect(closed.locator('[data-report-note]')).toHaveText(note);
    await expect(closed).toContainText('Closed by Sara Lindqvist');
    await signOut(page);

    // Tenant B's administrator also holds proposals.create, so reads every report their
    // own bank filed on the same library record: tenant A's is not among them.
    await signInAs(page, LOGINS.secondBankAdmin);
    await page.goto(obligationUrl);
    const other = page.locator('[data-problem-reports]');
    await expect(other.locator('[data-reports-empty]').or(other.locator('[data-report-id]')).first()).toBeVisible();
    await expect(other.locator(`[data-report-id="${reportId}"]`)).toHaveCount(0);
    await expect(other).not.toContainText(words);
    await expect(other).not.toContainText('Oskar Lund');
  });

  test("ADM-S4: The platform console offers each surface to the platform role that owns it", async ({ page, request, apiGuard }, testInfo) => {
    // The two platform roles, each walking the whole console. No destination is
    // named here: the registry is the list, and the closing assertion is that it
    // divides cleanly between the two roles with nothing left over.
    allowFreshContext(apiGuard);
    const editor = await consoleDestinationsOf(page, LOGINS.editor);
    await signOut(page);
    const platform = await consoleDestinationsOf(page, LOGINS.platform);

    expect(editor.filter((id) => platform.includes(id))).toEqual([]);
    expect([...editor, ...platform].sort()).toEqual(CONSOLE_DESTINATIONS.map((d) => d.id).sort());

    // A bank's report that a library record looks wrong stays inside that bank
    // (Alex, 2026-09-20, item 3): the console offers no surface for one, and no
    // console route serves one. Asserted directly against the API, so it cannot
    // come back unnoticed. The request fixture is used on purpose — the guard
    // watches the page, and these 404s are the point of the assertion.
    expect(CONSOLE_DESTINATIONS.map((d) => d.id)).not.toContain('console-problem-reports');
    for (const path of ['/api/v1/console/problem-reports', '/api/v1/console/reports']) {
      expect((await request.get(`${BACKEND_URL}${path}`)).status(), `${path} must not exist`).toBe(404);
    }

    // The evaluation set, the library editor's (SRC-05): the set filtered by language, the
    // baseline as the server holds it, and a question added and marked as not yet in the
    // release gate. The key carries the attempt, so a retry never collides; a question is
    // never deleted, only added, and the database is this run's own.
    await signOut(page);
    await signInAs(page, LOGINS.editor);
    const baselineAnswer = page.waitForResponse((r) => r.url().endsWith('/api/v1/eval/baseline') && r.ok());
    await page.goto('/console/evaluation');
    await expect(page.getByRole('heading', { level: 1, name: 'Evaluation' })).toBeVisible();
    await expect(page.locator('[data-eval-questions] [data-question-key]').first()).toBeVisible();

    // A score nobody recorded reads Unrecorded, and a recorded one reads as its number.
    const baseline = (await (await baselineAnswer).json()) as { recallAt10: number | null; mrr: number | null };
    for (const metric of ['recallAt10', 'mrr'] as const) {
      const cell = page.locator(`[data-baseline-metric="${metric}"] [data-baseline-value]`);
      if (baseline[metric] === null) await expect(cell).toHaveText('Unrecorded');
      else await expect(cell).not.toHaveText('Unrecorded');
    }
    await expect(page.locator('[data-eval-runs] [data-run-id]').or(page.getByText('No runs recorded yet')).first()).toBeVisible();

    const key = `r-sv-e2e-${Date.now().toString(36)}-${testInfo.retry}`;
    await page.getByRole('button', { name: 'Add a question', exact: true }).click();
    const form = page.getByRole('dialog', { name: 'Add a question' });
    await expect(form.getByText(/^Not yet in the release gate\./)).toBeVisible();
    await form.getByLabel('Key', { exact: true }).fill(key);
    await form.getByLabel('Language', { exact: true }).selectOption('sv');
    await form.getByLabel('Question', { exact: true }).fill('kostnader och avgifter före tjänsten');
    await form.getByLabel('Expected records').fill('obl-costs-charges');
    const added = page.waitForResponse((r) => r.url().endsWith('/api/v1/eval/questions') && r.request().method() === 'POST' && r.ok());
    await form.getByRole('button', { name: 'Add question', exact: true }).click();
    expect(((await (await added).json()) as { inGate: boolean }).inGate).toBe(false);
    await expect(form).toBeHidden();
    await expect(page.getByText(`Added ${key}. It is not yet in the release gate.`)).toBeVisible();

    await page.getByLabel('Language', { exact: true }).selectOption('sv');
    const row = page.locator(`[data-question-key="${key}"]`);
    await expect(row).toContainText('Not yet in the release gate');
    await expect(page.locator('[data-eval-questions] [data-question-key]:not([data-lang="sv"])')).toHaveCount(0);
  });

  test.fixme("ADM-S5: System health names what is wrong", async () => {
    // pending: ADM-S5 (ADM-02, chunk 14)
  });

  test("ADM-S6: A tenant is created from the console with its first administrator invited", async ({ page, request, apiGuard }, testInfo) => {
    allowFreshContext(apiGuard);
    // A name carries the attempt, so a retry and a parallel run never collide and nothing
    // seeded is touched. The short name is derived from it, never typed here.
    const name = `ADM-S6 Bank AB ${Date.now().toString(36)}-${testInfo.retry}`;
    const email = `administrator@${Date.now().toString(36)}-${testInfo.retry}.test`;

    await signInAs(page, LOGINS.platform);
    await page.goto('/console/tenants');
    await expect(page.getByRole('heading', { level: 1, name: 'Tenants' })).toBeVisible();
    await expect(page.locator('[data-tenants-list]').or(page.locator('[data-empty-state]')).first()).toBeVisible();

    const openForm = async () => {
      await page.getByRole('button', { name: 'Create a tenant', exact: true }).click();
      const form = page.getByRole('dialog', { name: 'Create a tenant' });
      await expect(form).toBeVisible();
      return form;
    };

    const form = await openForm();
    await form.getByLabel('Name', { exact: true }).fill(name);
    await form.getByLabel("First administrator's email").fill(email);
    await form.getByLabel('Their title').fill('Head of compliance');
    const created = page.waitForResponse((r) => r.url().endsWith('/api/v1/console/tenants') && r.request().method() === 'POST' && r.ok());
    await form.getByRole('button', { name: 'Create tenant', exact: true }).click();
    const { id: tenantId } = (await (await created).json()) as { id: string };
    await expect(form).toBeHidden();

    // The bank this attempt created, pinned by id, never by a count. It has a short name
    // even though nobody typed one, and no timezone or language field was ever shown.
    const row = page.locator(`[data-tenant-id="${tenantId}"]`);
    await expect(row).toBeVisible();
    await expect(row).toHaveAttribute('data-tenant-slug', /.+/);
    await expect(row.getByText('Active', { exact: true })).toBeVisible();

    // One pending invitation went to that address, with the link that opens it.
    await expect.poll(async () => mailsTo(await mailOutbox(request), email).length).toBe(1);
    const [invitation] = mailsTo(await mailOutbox(request), email);
    expect(invitation === undefined ? null : inviteLinkFrom(invitation)).not.toBeNull();

    // A second bank with the same name is created too, not refused: two console
    // create-tenant calls never collide on a name a person never chose a short form for.
    const again = await openForm();
    await again.getByLabel('Name', { exact: true }).fill(name);
    await again.getByLabel("First administrator's email").fill(`second-${email}`);
    const createdAgain = page.waitForResponse((r) => r.url().endsWith('/api/v1/console/tenants') && r.request().method() === 'POST' && r.ok());
    await again.getByRole('button', { name: 'Create tenant', exact: true }).click();
    const { id: secondTenantId, slug: secondSlug } = (await (await createdAgain).json()) as { id: string; slug: string };
    await expect(again).toBeHidden();
    await expect(page.locator(`[data-tenant-id="${secondTenantId}"]`)).toHaveAttribute('data-tenant-slug', secondSlug);
    expect(secondTenantId).not.toBe(tenantId);
  });

  test.fixme("ACC-S11: Tenant reach needs two people, and off means off", async () => {
    // pending: ACC-S11 (ACC-08, AC-ACC2, chunk 11)
  });

  test.fixme("ADM-S18: A jurisdiction is relabelled, retired and restored by proposal, and the market that mirrors it follows", async () => {
    // pending: ADM-S18 (ADM-02, VOC-07, FP-04, I18N-01); x-console-jurisdictions-fe builds the screen
  });
});
