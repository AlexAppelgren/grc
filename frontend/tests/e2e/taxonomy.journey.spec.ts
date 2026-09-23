import type { Browser, Page, TestInfo } from '@playwright/test';

import { expect, test, type ApiGuard } from './support/api-guard';
import { allowFreshContext, LOGINS, signInAs } from './support/passkeys';
import { approveQueueProposal } from './support/watch';

// taxonomy: the @e2e scenarios from backend/apps/taxonomy/app.md (playbook Appendix B).
// Each stays test.fixme until its chunk builds the journey; the scenario ID in
// the title is what scripts/requirements_coverage.py looks for. Never delete a
// stub: un-fixme it when the journey is real.
//
// Chunk 2 builds the vocabulary screens (VOC-01, VOC-02, VOC-07) and the
// footprint screen (FP-01, FP-02). The halves of a scenario that need a
// surface a later chunk builds (a record picker, the feed filter, the
// inventory, the platform console) are named where they would go.
//
// Values are created by the journeys themselves, with labels that are not
// near each other, so journeys running in parallel never trip each other's
// near-duplicate check. Vocabulary labels come from rows, not the catalog, so
// they are found by data attribute or by pattern, never by a quoted literal.

const TAGS = 'tenant_tag';
const FLAGS = 'flag';
const SERVICES = 'service_type';

// The seeded obligation whose only service is Advice (backend/apps/shared/e2e_seed.py,
// EXPECTED_LIBRARY.advice_only_obligation): switching Advice off is what hides it.
const ADVICE_ONLY_OBLIGATION = 'obl-suitability-statement';
// The seed's anchor date. Every inventory read here pins it, so nothing depends
// on today and no version that takes effect later changes what is listed.
const INVENTORY_AS_OF = '2026-09-16';

async function openInventory(page: Page): Promise<void> {
  await page.goto(`/inventory?asOf=${INVENTORY_AS_OF}`);
  await expect(page.locator('[data-obligation-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
}

/** Found by data attribute: library titles are rows, not catalog copy. */
function adviceOnlyRow(page: Page) {
  return page.locator(`[data-obligation="${ADVICE_ONLY_OBLIGATION}"]`);
}

// The server refuses a new value two ways (apps/taxonomy/tenant_lists_logic.py,
// its VOC-S7 test): 409 duplicate_key for the same label, 422 near_duplicate
// for a close one. Each is declared where it is provoked.
function allowDuplicateRefusals(apiGuard: ApiGuard, list: string): void {
  const route = new RegExp(`/api/v1/vocab/${list}$`);
  apiGuard.allow(route, 409, 'duplicate_key: the same label, case and space aside (AC-VOC3)');
  apiGuard.allow(route, 422, 'near_duplicate: a close label, the near match offered (AC-VOC3)');
}

async function openList(page: Page, list: string): Promise<void> {
  await page.goto(`/admin/vocabularies/${list}`);
  await expect(page.locator(`[data-vocabulary-values="${list}"]`).or(page.locator('[data-empty-state]')).first()).toBeVisible();
}

function valueRow(page: Page, label: string) {
  return page.locator('[data-value-key]').filter({ has: page.locator('[data-swatch="light"]', { hasText: new RegExp(`^${label}$`) }) });
}

async function addTenantValue(page: Page, label: string, usageNote = ''): Promise<void> {
  await page.getByRole('button', { name: 'Add a value' }).click();
  const dialog = page.getByRole('dialog', { name: 'Add a value' });
  await dialog.getByLabel('Label', { exact: true }).fill(label);
  if (usageNote !== '') await dialog.getByLabel('Usage note').fill(usageNote);
  await dialog.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(valueRow(page, label)).toHaveCount(1);
}

/** The second person of a four-eyes journey, in their own browser, held to the same API guard. */
async function secondPerson(browser: Browser, apiGuard: ApiGuard, testInfo: TestInfo, login: string): Promise<Page> {
  const context = await browser.newContext({ baseURL: testInfo.project.use.baseURL });
  const page = await context.newPage();
  apiGuard.watch(page);
  await signInAs(page, login);
  return page;
}

test.describe('taxonomy journeys', () => {
  test("VOC-S2: An admin adds a change type, a tag and a sub-status without a deploy", async ({ page, apiGuard }) => {
    // pending: VOC-S2 (VOC-01, AC-VOC1) -> built in chunk 2, the tenant tag half.
    // The change type is a library list, so it arrives as a proposal the
    // console approves (VOC-S11 covers the tenant side of that door). The
    // sub-status screen is R2 (chunk 8). The picker, the filter and the
    // record pills that show the tag land with the screens that host them.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.admin);
    await page.goto('/admin/vocabularies');
    await expect(page.getByRole('heading', { level: 1, name: 'Vocabularies' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Our lists' })).toHaveAttribute('aria-selected', 'true');
    await page.locator(`[data-vocabulary-list="${TAGS}"]`).click();
    await expect(page.getByRole('heading', { level: 1, name: 'Tenant tags' })).toBeVisible();

    await addTenantValue(page, 'Custody', 'Anything about safekeeping client assets');
    // A tenant tag is always an outlined information pill: the slot decides, never a person.
    const pills = valueRow(page, 'Custody').locator('[data-pill]');
    await expect(pills).toHaveCount(2);
    for (const pill of await pills.all()) {
      await expect(pill).toHaveAttribute('data-pill', 'information');
      await expect(pill).toHaveAttribute('data-outlined', '');
    }
    // Without a deploy: the list of lists counts it straight away.
    await page.goto('/admin/vocabularies');
    await expect(page.locator(`[data-vocabulary-list="${TAGS}"]`)).toContainText(/\d+ active/);
  });

  test("VOC-S3: The vocabulary screen renders the real pill with usage count, rename and reorder", async ({ page, apiGuard }) => {
    // pending: VOC-S3 (VOC-02) -> built in chunk 2. "Every record shows the new
    // label" needs a record screen (chunk 3); the order pickers follow is
    // proved here by the stored order surviving a reload.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.admin);
    await openList(page, TAGS);
    await addTenantValue(page, 'Pension transfers');
    await addTenantValue(page, 'Onboarding journeys');

    // The real pill, light and dark, with its usage count.
    const row = valueRow(page, 'Pension transfers');
    await expect(row.locator('[data-swatch="light"] [data-pill]')).toHaveCount(1);
    await expect(row.locator('[data-swatch="dark"] [data-pill]')).toHaveCount(1);
    await expect(row.getByText('Not used yet')).toBeVisible();

    // Inline rename with a translation; the key stays.
    const key = await row.getAttribute('data-value-key');
    await row.getByRole('button', { name: 'Rename' }).click();
    const form = page.locator(`[data-rename-form="${key}"]`);
    await expect(form.getByText(/^Records keep the key .+; only the label changes$/)).toBeVisible();
    await form.getByLabel('New label').fill('Pension transfer rights');
    await form.getByLabel('Label in Swedish').fill('Flytträtt för pension');
    await form.getByRole('button', { name: 'Save' }).click();
    const renamed = valueRow(page, 'Pension transfer rights');
    await expect(renamed).toHaveCount(1);
    await expect(renamed).toHaveAttribute('data-value-key', key ?? '');

    // Reorder with the keyboard on the grip: "Onboarding journeys" moves above it.
    const keys = async () => page.locator('[data-value-active]').evaluateAll((rows) => rows.map((r) => r.getAttribute('data-value-key')));
    const onboarding = await valueRow(page, 'Onboarding journeys').getAttribute('data-value-key');
    const before = await keys();
    const steps = before.indexOf(onboarding) - before.indexOf(key);
    expect(steps).toBeGreaterThan(0);
    const grip = page.locator(`[data-grip="${onboarding}"]`);
    await grip.focus();
    for (let i = 0; i < steps; i += 1) await grip.press('ArrowUp');
    await expect.poll(async () => (await keys()).indexOf(onboarding) < (await keys()).indexOf(key)).toBe(true);

    await page.reload();
    await expect(valueRow(page, 'Onboarding journeys')).toHaveCount(1);
    await expect.poll(async () => (await keys()).indexOf(onboarding) < (await keys()).indexOf(key)).toBe(true);
  });

  test("VOC-S4: Retiring a used value keeps history readable and leaves pickers", async ({ page, apiGuard }) => {
    // pending: VOC-S4 (VOC-02, AC-VOC2) -> built in chunk 2. Obligations that
    // carry the tag arrive with chunk 3; here the count shown first is the
    // row's own, and the row survives with active false under Retired.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.admin);
    await openList(page, TAGS);
    await addTenantValue(page, 'Legacy archive');
    const row = valueRow(page, 'Legacy archive');
    const key = await row.getAttribute('data-value-key');

    try {
      await row.getByRole('button', { name: 'Retire' }).click();
      const dialog = page.getByRole('dialog', { name: 'Retire "Legacy archive"?' });
      // The usage count comes before the confirmation.
      await expect(dialog.getByText(/^(Nothing uses it yet|It is used by \d+ records?)\./)).toBeVisible();
      await dialog.getByRole('button', { name: 'Retire' }).click();
      await expect(dialog).toBeHidden();
      await expect(page.locator(`[data-value-key="${key}"][data-value-active]`)).toHaveCount(0);

      await page.getByRole('button', { name: 'Retired' }).click();
      const retired = page.locator(`[data-value-key="${key}"]`);
      await expect(retired).toHaveCount(1);
      await expect(retired.locator('[data-value-active]')).toHaveCount(0);
    } finally {
      // Restore it, so the list reads as it did.
      await openList(page, TAGS);
      await page.getByRole('button', { name: 'Retired' }).click();
      const retired = page.locator(`[data-value-key="${key}"]`);
      if ((await retired.count()) > 0) {
        await retired.getByRole('button', { name: 'Restore' }).click();
        await expect(page.locator(`[data-value-key="${key}"]`)).toHaveCount(0);
      }
    }
  });

  test("VOC-S5: Merging re-points duplicates in one audited transaction", async ({ page, apiGuard }) => {
    // pending: VOC-S5 (VOC-02) -> built in chunk 2. The dry run previews the
    // count, the commit retires the merged value. Records that carry it and
    // the audit entry's keys are proved by the backend's VOC-S5 test.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.admin);
    await openList(page, TAGS);
    await addTenantValue(page, 'Settlement');
    await addTenantValue(page, 'Safe deposit boxes');
    const from = await valueRow(page, 'Safe deposit boxes').getAttribute('data-value-key');
    const into = await valueRow(page, 'Settlement').getAttribute('data-value-key');

    await valueRow(page, 'Safe deposit boxes').getByRole('button', { name: 'Merge into…' }).click();
    const dialog = page.getByRole('dialog', { name: 'Merge "Safe deposit boxes" into…' });
    await dialog.getByLabel('Keep').selectOption(into ?? '');
    const preview = dialog.locator('[data-merge-preview]');
    await expect(preview.getByText('What happens')).toBeVisible();
    await expect(preview.getByText('One audit entry with both keys and the count moved.')).toBeVisible();
    await expect(preview.getByText(/^"Safe deposit boxes" is retired and its history stays readable\.$/)).toBeVisible();
    await dialog.getByRole('button', { name: /^Merge \d+ records?$/ }).click();
    await expect(dialog).toBeHidden();

    await expect(page.locator(`[data-value-key="${from}"][data-value-active]`)).toHaveCount(0);
    await expect(page.locator(`[data-value-key="${into}"][data-value-active]`)).toHaveCount(1);
    await page.getByRole('button', { name: 'Retired' }).click();
    await expect(page.locator(`[data-value-key="${from}"]`)).toHaveCount(1);
  });

  test.fixme("VOC-S6: Create where you use it offers Create or Suggest by permission", async () => {
    // pending: VOC-S6 (VOC-03). VOC-03 is priority S, release R2 (decided with
    // the coordinator in chunk 2). The picker component exists
    // (components/vocabularies/VocabularyPicker.tsx, with Create and Propose
    // and unit tests); this journey needs a record screen that hosts it and
    // the Suggest path for members without vocab.manage, both R2.
  });

  test("VOC-S7: A near-duplicate is refused with the near match offered", async ({ page, apiGuard }) => {
    // pending: VOC-S7 (VOC-03, AC-VOC3) -> the near-duplicate check is live
    // from chunk 2 (picker card); proved here on the add form.
    allowFreshContext(apiGuard);
    allowDuplicateRefusals(apiGuard, TAGS);
    await signInAs(page, LOGINS.admin);
    await openList(page, TAGS);
    await addTenantValue(page, 'Derivatives');

    // The same label with a trailing space and another case is the value that is there (409).
    // A typo is a near match, asked as a question, with the match offered (422).
    for (const [attempt, refusal] of [
      [' derivatives ', '"Derivatives" already exists.'],
      ['Derivatves', 'Did you mean Derivatives?'],
    ] as const) {
      await page.getByRole('button', { name: 'Add a value' }).click();
      const dialog = page.getByRole('dialog', { name: 'Add a value' });
      await dialog.getByLabel('Label', { exact: true }).fill(attempt);
      await dialog.getByRole('button', { name: 'Add', exact: true }).click();
      await expect(dialog.getByText(refusal, { exact: true })).toBeVisible();
      await dialog.getByRole('button', { name: 'Use Derivatives' }).click();
      await expect(dialog).toBeHidden();
    }
    // Nothing was added: one row carries the label.
    await expect(page.locator('[data-value-key]').filter({ hasText: /derivat/i })).toHaveCount(1);
  });

  test("VOC-S11: A library vocabulary change goes through the proposal queue", async ({ page, apiGuard }) => {
    // pending: VOC-S11 (VOC-07) -> built in chunk 2, the tenant side of the
    // door: a write to a library list answers with a proposal, shows as
    // waiting and does not change the list. The second editor's approval is
    // the platform console's (console chunk). Proposing needs proposals.create,
    // which the seeded compliance officer holds and the admin does not.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await page.goto('/admin/vocabularies');
    await page.getByRole('tab', { name: 'Shared library lists' }).click();
    await page.locator(`[data-vocabulary-list="${FLAGS}"]`).click();
    await expect(page.getByText('These lists are shared by every organisation. Suggest a change and a library editor reviews it.')).toBeVisible();

    await page.getByRole('button', { name: 'Suggest a change' }).click();
    const dialog = page.getByRole('dialog', { name: 'Add a value' });
    await dialog.getByLabel('Label', { exact: true }).fill('Outsourcing');
    await dialog.getByRole('button', { name: 'Send for review' }).click();
    await expect(dialog.getByText(/is waiting for a library editor\.$/)).toBeVisible();
    await dialog.getByRole('button', { name: 'Done' }).click();

    // Not in the list until a library editor approves it. The proposal is
    // confirmed where it was sent; a list of what this tenant proposed comes
    // with chunk 4's tenant-scoped read.
    await expect(valueRow(page, 'Outsourcing')).toHaveCount(0);
    await expect(page.locator('[data-pending-proposals]')).toHaveCount(0);
  });

  test.fixme("VOC-S12: Bulk tagging from a list previews and writes one audit entry", async () => {
    // pending: VOC-S12 (VOC-08)
  });

  test("VOC-S15 J-5 @smoke: a flag is added, used, rendered as brand, renamed and merged", async ({ page, browser, apiGuard }, testInfo) => {
    // pending: VOC-S15 (VOC-01, VOC-02, VOC-07, AC-VOC1, AC-VOC2, J-5) -> built
    // in chunk 2 up to the library door. Flags are a library list, so adding
    // and renaming are proposals (VOC-07); every flag renders brand in both
    // themes. Using the new flag on a change, the feed filter and merging it
    // wait for the console's approval and the watch screens (chunk 4). The
    // proposer is the seeded compliance officer: a library change is a
    // proposal, and proposing needs proposals.create. c5-e2e-vocab-footprint-feed's own
    // watch steps add a second person and roughly a dozen more page loads to the same
    // journey rather than a second smoke test, so the default 30 s budget is tripled.
    test.slow();
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await openList(page, FLAGS);

    // Every flag is a brand pill, in the light and the dark swatch.
    const flagPills = page.locator('[data-value-active] [data-swatch] [data-pill]');
    await expect(flagPills.first()).toBeVisible();
    for (const pill of await flagPills.all()) await expect(pill).toHaveAttribute('data-pill', 'brand');

    // Added with a usage note: previewed as brand before it is sent.
    await page.getByRole('button', { name: 'Suggest a change' }).click();
    const dialog = page.getByRole('dialog', { name: 'Add a value' });
    await dialog.getByLabel('Label', { exact: true }).fill('Client money');
    await dialog.getByLabel('Usage note').fill('The change concerns how client money is held and segregated.');
    await expect(dialog.locator('[data-swatch-pair] [data-pill="brand"]')).toHaveCount(2);
    await dialog.getByRole('button', { name: 'Send for review' }).click();
    await expect(dialog.getByText(/is waiting for a library editor\.$/)).toBeVisible();
    await dialog.getByRole('button', { name: 'Done' }).click();

    // Renamed: a system flag can be relabelled, and on a library list that is a proposal too.
    const first = page.locator('[data-value-active]').first();
    const key = await first.getAttribute('data-value-key');
    await first.getByRole('button', { name: 'Rename' }).click();
    const form = page.locator(`[data-rename-form="${key}"]`);
    await form.getByLabel('Label in Swedish').fill('Nytt namn för granskning');
    await form.getByRole('button', { name: 'Send for review' }).click();
    await expect(page.locator('[data-rename-proposed]').getByText(/is waiting for a library editor\.$/)).toBeVisible();

    // The watch steps (c5-e2e-vocab-footprint-feed): "Client money" approved,
    // put on a change through the console, and it renders as a brand pill on
    // that bank's feed and change page. A second, independent person decides
    // (four eyes, PRO-02): the editor never proposed either of these. The first
    // approve attempt on each always answers 403 step_up_required, which is what opens
    // the passkey prompt (playbook 4.2); `approveQueueProposal()` confirms it.
    apiGuard.allow(/\/proposals\/.+\/approve$/, 403, 'approving asks for a fresh passkey assertion first, which opens the step-up prompt');
    const editor = await secondPerson(browser, apiGuard, testInfo, LOGINS.editor);
    await approveQueueProposal(editor, /Add Client money to flag/);

    // The rename and the merge below are proposed as editor2 and approved as editor:
    // one editor proposing and then approving its own change would be the four-eyes
    // violation PRO-02 refuses (409), and the console shows no Approve control on a
    // reviewer's own proposal at all (ProposalDetailScreen.tsx's "You proposed this.").
    const editor2 = await secondPerson(browser, apiGuard, testInfo, LOGINS.editor2);

    // The third seeded reform (`chg-e2e-c5-payments`, backend/apps/shared/e2e_seed.py):
    // untouched by any other journey's exact pill or timeline count, so a
    // correction here can never make WAT-S2 or WAT-S9 read a change that has
    // moved under them. Every agent-registered change is unconfirmed on at
    // least its own type, so the default "Only unconfirmed" filter already
    // lists it.
    await editor.goto('/console/change-facts');
    await expect(editor.locator('[data-change-facts-list]').or(editor.locator('[data-empty-state]')).first()).toBeVisible();
    await editor.getByRole('link', { name: /instant payment infrastructure resilience/ }).click();
    const flagsFact = editor.locator('[data-fact="Flags"]');
    await flagsFact.getByRole('button', { name: 'Correct' }).click();
    await editor.getByLabel('Client money', { exact: true }).check();
    await editor.locator('[data-correct-flags]').getByRole('button', { name: 'Save the flags' }).click();
    await expect(flagsFact.getByText('Client money')).toBeVisible();

    // The same fact, read on the bank's own feed row and change page: a
    // brand pill, still marked as the agent's own suggestion (a library
    // editor's correction is not a confirmation).
    await page.goto('/watch?tab=all');
    await expect(page.locator('[data-change-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
    const row = page.locator('[data-change="chg-e2e-c5-payments"]');
    await expect(row).toBeVisible();
    await expect(row.locator('[data-pill="brand"]').filter({ hasText: 'Client money' })).toBeVisible();
    await row.click();
    await expect(page).toHaveURL(/\/watch\/[0-9a-f-]+$/);
    const classification = page.locator('[data-change-classification]');
    await expect(classification.locator('[data-pill="brand"]').filter({ hasText: 'Client money' })).toBeVisible();
    const changeUrl = page.url();

    // Renamed, and the change still shows the new label with no change row
    // written: the link is a foreign key to the flag's own row, so the label
    // a reader sees follows the row it points at rather than a copy this
    // change carries, and the change keeps the same address throughout.
    await editor2.goto('/console/vocabularies');
    await editor2.locator('[data-vocabulary-list="flag"]').click();
    const clientMoney = editor2.locator('[data-value-key="client_money"]');
    await clientMoney.getByRole('button', { name: 'Rename' }).click();
    const renameForm = editor2.locator('[data-rename-form="client_money"]');
    await renameForm.getByLabel('New label', { exact: true }).fill('Segregated client money');
    await renameForm.getByRole('button', { name: 'Send for review' }).click();
    await expect(editor2.locator('[data-rename-proposed]').getByText(/is waiting for a library editor\.$/)).toBeVisible();
    await approveQueueProposal(editor, /Change client_money on flag/);

    await page.goto(changeUrl);
    await expect(page).toHaveURL(changeUrl);
    await expect(classification.locator('[data-pill="brand"]').filter({ hasText: 'Segregated client money' })).toBeVisible();
    await expect(classification.locator('[data-pill="brand"]').filter({ hasText: /^Client money$/ })).toHaveCount(0);

    // Merged into an existing flag, and the change still reads: nothing
    // breaks and the address is unchanged, whether or not the merge
    // re-points this change's own link (a later task's work;
    // `entry.repoint()` on `flag` is still `repoint.nothing_to_repoint`,
    // apps/taxonomy/registry.py).
    await editor2.goto('/console/vocabularies');
    await editor2.locator('[data-vocabulary-list="flag"]').click();
    await editor2.locator('[data-value-key="client_money"]').getByRole('button', { name: /^Merge into/ }).click();
    const mergeDialog = editor2.getByRole('dialog', { name: /^Merge "Segregated client money" into/ });
    await mergeDialog.locator('#merge-into').selectOption({ label: 'Advice perimeter' });
    await expect(mergeDialog.getByText('What happens')).toBeVisible();
    await mergeDialog.getByRole('button', { name: /^Merge/ }).click();
    await expect(mergeDialog.getByText(/is waiting for a library editor\.$/)).toBeVisible();
    await mergeDialog.getByRole('button', { name: 'Done' }).click();
    await approveQueueProposal(editor, /Merge client_money into advice_perimeter on flag/);

    await page.goto(changeUrl);
    await expect(page).toHaveURL(changeUrl);
    await expect(classification).toBeVisible();
  });

  test.describe('footprint', () => {
    // Both journeys change the one footprint of tenant A, so they run in
    // order in one worker. Each settles on whether a request is already
    // waiting (the seed leaves one for J-6) before it branches.
    test.describe.configure({ mode: 'default' });

    /** Opens the scope as the officer, withdrawing a request of theirs that is still waiting. */
    async function officerStartsClean(page: Page): Promise<void> {
      await page.goto('/admin/footprint');
      // The banner's text spans lines (pill, title, sentence), so the match is unanchored.
      const mine = page.locator('[data-pending-request]').filter({ hasText: /You requested this on/ });
      const groups = page.locator('[data-footprint-dimensions]');
      await expect(mine.or(groups).first()).toBeVisible();
      if ((await mine.count()) > 0) {
        await mine.getByRole('button', { name: 'Withdraw' }).click();
        await expect(page.getByText('Withdrawn.', { exact: true })).toBeFocused();
        await expect(page.locator('[data-pending-request]')).toHaveCount(0);
      }
    }

    /** Advice in the read state: a glyph and the label, with "In our scope" or "Not in our scope" for a screen reader. Found by key: terms are rows. */
    function adviceItem(page: Page) {
      return page.locator(`[data-dimension="${SERVICES}"] [data-term="advice"]`);
    }

    function adviceCheckbox(page: Page) {
      return page.locator(`[data-dimension="${SERVICES}"]`).getByRole('checkbox', { name: /^Advice$/ });
    }

    async function officerRemovesAdvice(page: Page): Promise<void> {
      // Read-only until asked: Advice is held, and nothing on the page is a checkbox.
      await expect(adviceItem(page)).toHaveText(/^Advice In our scope$/);
      await expect(page.locator('[data-footprint-dimensions]').getByRole('checkbox')).toHaveCount(0);
      await page.getByRole('button', { name: 'Propose a change' }).click();
      await expect(adviceCheckbox(page)).toBeChecked();
      await adviceCheckbox(page).uncheck();
      const draft = page.locator('[data-draft-preview]');
      await expect(draft.getByRole('heading', { name: 'Your change: Remove Advice' })).toBeVisible();
      const hides = draft.locator('[data-preview-side="hides"]');
      const reveals = draft.locator('[data-preview-side="reveals"]');
      await expect(hides.getByText('Hides')).toBeVisible();
      await expect(reveals.getByText('Reveals')).toBeVisible();
      await expect(draft.getByText('Loading…')).toHaveCount(0);
      // J-6: the preview counts what the change would take away, and the count
      // is not zero — one seeded obligation reaches this bank through Advice
      // alone. Counts only: the preview never names the records.
      await expect(hides.getByText(/^[1-9]\d* obligations?$/)).toBeVisible();
      await expect(hides.getByText('Nothing.')).toHaveCount(0);
      // FP-S2: any that would appear are counted too, and cases are not counted yet, on either side.
      await expect(reveals.getByText(/^(\d+ obligations?|Nothing\.)$/)).toBeVisible();
      await expect(hides.getByText('Open cases: not counted yet')).toBeVisible();
      await expect(reveals.getByText('Open cases: not counted yet')).toBeVisible();
      // It hides something, so the panel says once what that means for every member.
      await expect(draft.getByText('What this hides leaves the feed, the inventory, the roadmap and the briefing for every member.')).toBeVisible();
      await expect(page.getByRole('button', { name: 'Cancel' })).toHaveCount(1);
      await draft.getByRole('button', { name: 'Request approval' }).click();
      await expect(page.getByText('Sent for approval.', { exact: true })).toBeFocused();
      const banner = page.locator('[data-pending-request]');
      await expect(banner.getByText('Waiting for approval')).toBeVisible();
      await expect(banner.getByText('Remove Advice')).toBeVisible();
      // Four eyes on screen: the requester is offered Withdraw, never Approve.
      await expect(banner.getByRole('button', { name: 'Approve' })).toHaveCount(0);
      await expect(banner.getByRole('button', { name: 'Withdraw' })).toBeVisible();
      // While it waits, nothing is a control and Advice carries the change it waits for.
      await expect(page.getByRole('button', { name: 'Propose a change' })).toHaveCount(0);
      await expect(page.locator('[data-footprint-dimensions]').getByRole('checkbox')).toHaveCount(0);
      await expect(adviceItem(page).getByText('Removed when approved')).toBeVisible();
    }

    async function approveWithPasskey(approver: Page): Promise<void> {
      await approver.goto('/admin/footprint');
      const banner = approver.locator('[data-pending-request]');
      await banner.getByRole('button', { name: 'Approve' }).click();
      const dialog = approver.getByRole('dialog', { name: /^Approve ".+"\?$/ });
      await dialog.getByRole('button', { name: 'Approve with passkey' }).click();
      // Step-up: settle on the prompt or the outcome, since a sign-in moments ago may still count.
      const prompt = approver.getByRole('dialog', { name: 'Confirm with your passkey' });
      const done = approver.getByText('Approved. The regulatory scope has changed.');
      await expect(prompt.or(done).first()).toBeVisible();
      if (await prompt.isVisible()) await prompt.getByRole('button', { name: 'Use passkey' }).click();
      await expect(done).toBeVisible();
      await expect(approver.locator('[data-pending-request]')).toHaveCount(0);
    }

    test("FP-S2: A footprint change previews, waits for a second person and audits per term", async ({ page, browser, apiGuard }, testInfo) => {
      // pending: FP-S2 (FP-02, AC-FP1) -> built in chunk 2. What the change
      // hides "everywhere" and the per-term audit events are proved by the
      // backend's FP-S2 test; the surfaces arrive with chunk 3.
      allowFreshContext(apiGuard);
      await signInAs(page, LOGINS.complianceOfficer);
      await officerStartsClean(page);
      await expect(page.getByRole('heading', { level: 1, name: 'Regulatory scope' })).toBeVisible();

      await officerRemovesAdvice(page);
      // The stored request shows its counted preview on demand.
      const seePreview = page.locator('[data-pending-request]').getByRole('button', { name: 'See the preview' });
      await expect(seePreview).toHaveAttribute('aria-expanded', 'false');
      await seePreview.click();
      await expect(seePreview).toHaveAttribute('aria-expanded', 'true');
      await expect(page.locator('[data-pending-preview]').getByText('Hides')).toBeVisible();

      // The second person decides: here, a rejection, which needs a reason.
      const approver = await secondPerson(browser, apiGuard, testInfo, LOGINS.approver);
      await approver.goto('/admin/footprint');
      const banner = approver.locator('[data-pending-request]');
      await expect(banner.getByText(/^Requested by .+, .+\./)).toBeVisible();
      await banner.getByRole('button', { name: 'Reject' }).click();
      const dialog = approver.getByRole('dialog', { name: 'Reject this change' });
      await dialog.getByRole('button', { name: 'Reject' }).click();
      await expect(dialog.getByText('Give a reason.')).toBeVisible();
      await expect(dialog.getByLabel('Reason')).toBeFocused();
      await expect(dialog.getByLabel('Reason')).toHaveAttribute('aria-invalid', 'true');
      await dialog.getByLabel('Reason').fill('We still advise in private banking');
      await dialog.getByRole('button', { name: 'Reject' }).click();
      await expect(approver.getByText('Rejected.', { exact: true })).toBeFocused();
      await expect(approver.locator('[data-history-entry="rejected"]').first()).toBeVisible();
      await approver.context().close();

      // Rejected, so Advice is still held and the officer may propose a change again.
      await page.reload();
      await expect(page.locator('[data-pending-request]')).toHaveCount(0);
      await expect(adviceItem(page)).toHaveText(/^Advice In our scope$/);
      await expect(page.getByRole('button', { name: 'Propose a change' })).toBeVisible();
    });

    test.fixme("FP-S4: Every surface respects the footprint and offers a way to look outside it", async () => {
      // pending: FP-S4 (FP-03). The blocker this note used to describe is
      // gone: `apps/cases/matching.py` now recomputes `change_case.
      // footprint_match` on the outbox cursor when a footprint change is
      // approved and when a change's scope terms move, so dropping Advice
      // through FP-S5's own mechanism really does move the roadmap and the
      // briefing. The integration half of FP-S4 drives exactly that path in
      // `apps/taxonomy/tests_scenarios.py::test_fp_s4` and no longer seeds
      // the column false.
      //
      // What is left is the journey itself: four surfaces walked in one
      // session (feed, inventory, roadmap, briefing) with the "Show outside
      // our scope" switch on the inventory, plus the seeded advice-only
      // change the walk needs. That is a screen job, not a backend one, and
      // the plan gives it to the chunk that closes the four surfaces
      // (`docs/plans/briefs/CHUNK5_TASKS.md`, "Cut, with reasons").
    });

    test("FP-S5 J-6 @smoke: footprint change with preview and second-person approval", async ({ page, browser, apiGuard }, testInfo) => {
      // pending: FP-S5 (FP-01, FP-02, FP-03, AC-FP1, J-6) -> built in chunk 2,
      // the inventory half in chunk 3. The per-term audit events wait for the
      // audit log screen. Here: the officer's request with its preview, the
      // approver's passkey step-up, the footprint changed on screen, and the
      // advice-only obligation gone from the inventory.
      allowFreshContext(apiGuard);
      apiGuard.allow(/\/api\/v1\/tenant\/footprint\/requests\/[^/]+\/approve$/, 403, 'the first attempt answers step_up_required and opens the prompt');
      await signInAs(page, LOGINS.complianceOfficer);
      await officerStartsClean(page);
      await officerRemovesAdvice(page);

      const approver = await secondPerson(browser, apiGuard, testInfo, LOGINS.approver);
      try {
        await approveWithPasskey(approver);
        await expect(approver.locator('[data-history-entry="approved"]').first()).toBeVisible();
        await page.reload();
        await expect(adviceItem(page)).toHaveText(/^Advice Not in our scope$/);

        // J-6 on the inventory: the obligation the change hides is gone, the
        // rest of the library still reads, and "Show outside our scope" brings
        // it back dashed with the term that put it there.
        await openInventory(page);
        await expect(adviceOnlyRow(page)).toHaveCount(0);
        await expect(page.locator('[data-obligation]').first()).toBeVisible();

        await page.getByRole('button', { name: 'Show outside our scope' }).click();
        await expect(adviceOnlyRow(page)).toHaveAttribute('data-outside-footprint', '');
        await expect(adviceOnlyRow(page).getByText('Outside our scope: Advice')).toBeVisible();
      } finally {
        // Put Advice back through the same door, so the scope reads as seeded.
        await page.goto('/admin/footprint');
        await expect(adviceItem(page)).toBeVisible();
        if ((await page.locator('[data-pending-request]').count()) === 0 && /Not in our scope/.test((await adviceItem(page).textContent()) ?? '')) {
          await page.getByRole('button', { name: 'Propose a change' }).click();
          await adviceCheckbox(page).check();
          await page.locator('[data-draft-preview]').getByRole('button', { name: 'Request approval' }).click();
          await expect(page.getByText('Sent for approval.', { exact: true })).toBeFocused();
          await approveWithPasskey(approver);
        }
        await approver.context().close();
      }
    });
  });
});

// PRD 0.3: the regulatory scope's restricted page (FP-02), markets (FP-04) and
// the opt-in standards dimension (INV-08). Each stays test.fixme until the task
// in docs/plans/briefs/FEATURES_0_3_TASKS.md that builds it lands.
test.describe('regulatory scope, markets and standards', () => {
  test.fixme("FP-S7: Members without scope permissions cannot open the regulatory scope page", async () => {
    // pending: FP-S7 (FP-02, ADM-01)
  });

  test.fixme("FP-S8: Turning on a country brings the EU rules that reach it", async () => {
    // pending: FP-S8 (FP-04, AC-FP2)
  });

  test.fixme("FP-S10: Watching a market is one audited write that hides nothing", async () => {
    // pending: FP-S10 (FP-04, AC-FP2)
  });

  test.fixme("FP-S13: The watched-market view of the inventory shows only what watching adds", async () => {
    // pending: FP-S13 (FP-04); needs the chunk 3 inventory
  });

  test.fixme("FP-S15: A change's jurisdiction comes from its authority, and the feed has the watched-market view", async () => {
    // pending: FP-S15 (FP-04); needs the chunk 5 watch feed
  });

  test.fixme("FP-S16: A standard shows only to tenants whose regulatory scope names it", async () => {
    // pending: FP-S16 (FP-01, FP-02, INV-08, AC-FP3)
  });
});
