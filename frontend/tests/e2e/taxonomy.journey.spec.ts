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
// FP-S15 (e2e_seed.py, tax-watched-feed): a Danish authority's custody change, and
// the Swedish lead change of chunk 6 (EXPECTED_HOME.lead_change) inside tenant A's scope.
const WATCHED_MARKET_CHANGE = 'chg-e2e-dk-custody';
const IN_SCOPE_CHANGE = 'chg-e2e-research-payments';
// The seed's anchor date. Every inventory read here pins it, so nothing depends
// on today and no version that takes effect later changes what is listed.
const INVENTORY_AS_OF = '2026-09-16';

// FP-S13: the Danish custody duty and its act, which tenant A's watch on Denmark adds
// (backend/apps/shared/e2e_seed.py, WATCHED_MARKET_OBLIGATION).
const WATCHED_MARKET_OBLIGATION = 'obl-dk-csd-registration';
const WATCHED_MARKET_INSTRUMENT = 'dk-lov-2017-650';

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

// VOC-S6: the obligation whose "Our tags" the journey writes; no other journey tags it.
const TAGGED_OBLIGATION = 'obl-dora-ict-register';

/** From the inventory to the card, by stable key, until its tags panel has read the record. */
async function openTaggedObligation(page: Page): Promise<void> {
  await openInventory(page);
  await page.locator(`[data-obligation="${TAGGED_OBLIGATION}"]`).click();
  await expect(page.locator('[data-obligation-tags] [role="combobox"]')).toBeEnabled();
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

  test("VOC-S6: Create where you use it offers Create or Suggest by permission", async ({ page, browser, apiGuard }, testInfo) => {
    // VOC-S6 (VOC-03), on the obligation card's "Our tags" (VOC-08, one record):
    // the admin creates a tag where it is used and it goes on the record; a
    // member without vocab.manage reads the tags, cannot remove one, and the
    // same picker offers Suggest; the suggestion waits on the admin's Suggested tab.
    const created = 'Market sounding';
    const suggested = 'Conflicts register';
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.admin);
    await openTaggedObligation(page);
    const panel = page.locator('[data-obligation-tags]');
    const createdTag = panel.locator('[data-obligation-tag]').filter({ hasText: new RegExp(`^${created}`) });
    try {
      await panel.getByLabel('Add a tag').fill(created);
      await expect(panel.locator('[data-picker-last="create"]')).toBeVisible();
      await panel.locator('[data-picker-last="create"]').click();
      await panel.getByRole('button', { name: 'Create and select' }).click();
      await expect(createdTag).toHaveCount(1);

      const member = await secondPerson(browser, apiGuard, testInfo, LOGINS.reader);
      try {
        await openTaggedObligation(member);
        const memberPanel = member.locator('[data-obligation-tags]');
        await expect(memberPanel.locator('[data-obligation-tag]').filter({ hasText: new RegExp(`^${created}`) })).toHaveCount(1);
        await expect(memberPanel.getByRole('button', { name: new RegExp(`^Remove ${created}$`) })).toHaveCount(0);
        await memberPanel.getByLabel('Suggest a tag').fill(suggested);
        await expect(memberPanel.locator('[data-picker-last="create"]')).toHaveCount(0);
        await memberPanel.locator('[data-picker-last="suggest"]').click();
        await memberPanel.getByRole('button', { name: 'Send suggestion' }).click();
        await expect(memberPanel.locator('[data-picker-suggested]')).toBeVisible();
        // A suggestion is not a tag: the record still carries only what the admin put on it.
        await expect(memberPanel.locator('[data-obligation-tag]').filter({ hasText: new RegExp(`^${suggested}`) })).toHaveCount(0);
      } finally {
        await member.context().close();
      }

      await openList(page, TAGS);
      await page.getByRole('button', { name: /^Suggested \(\d+\)$/ }).click();
      const suggestion = page.locator('[data-suggestion]').filter({ hasText: new RegExp(suggested) });
      await expect(suggestion).toHaveCount(1);
      await suggestion.getByRole('button', { name: 'Decline' }).click();
      await expect(suggestion).toHaveCount(0);
    } finally {
      // Teardown, on failure too: the record carries no tag of this journey's.
      await openTaggedObligation(page);
      if ((await createdTag.count()) > 0) {
        await panel.getByRole('button', { name: new RegExp(`^Remove ${created}$`) }).click();
        await expect(createdTag).toHaveCount(0);
      }
    }
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
    // VOC-S11 (VOC-07, PRO-01): a write to a library list answers with a
    // proposal, shows as waiting in this bank's own pending list and does not
    // change the list. The second reviewer's approval is the platform
    // console's. Proposing needs proposals.create, which the seeded
    // compliance officer holds and the admin does not.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.complianceOfficer);
    await page.goto('/admin/vocabularies');
    await page.getByRole('tab', { name: 'Shared library lists' }).click();
    await page.locator(`[data-vocabulary-list="${FLAGS}"]`).click();
    await expect(page.getByText('These lists are shared by every organisation. Suggest a change and it is reviewed before anyone can use it.')).toBeVisible();

    await page.getByRole('button', { name: 'Suggest a change' }).click();
    const dialog = page.getByRole('dialog', { name: 'Add a value' });
    await dialog.getByLabel('Label', { exact: true }).fill('Outsourcing');
    await dialog.getByRole('button', { name: 'Send for review' }).click();
    await expect(dialog.getByText(/is waiting for review\.$/)).toBeVisible();
    await dialog.getByRole('button', { name: 'Done' }).click();

    // Waiting in this bank's own pending list, matched by its own label since
    // other runs may leave proposals there, and not a row of the list until
    // it is approved.
    const pending = page.locator(`[data-pending-proposals="${FLAGS}"]`);
    const waiting = pending.locator('[data-pending-proposal]').filter({ hasText: /\bOutsourcing\b/ }).first();
    await expect(waiting).toBeVisible();
    await expect(waiting.getByText('Waiting for review', { exact: true })).toBeVisible();
    await expect(valueRow(page, 'Outsourcing')).toHaveCount(0);
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
    await expect(dialog.getByText(/is waiting for review\.$/)).toBeVisible();
    await dialog.getByRole('button', { name: 'Done' }).click();

    // Renamed: a system flag can be relabelled, and on a library list that is a proposal too.
    const first = page.locator('[data-value-active]').first();
    const key = await first.getAttribute('data-value-key');
    await first.getByRole('button', { name: 'Rename' }).click();
    const form = page.locator(`[data-rename-form="${key}"]`);
    await form.getByLabel('Label in Swedish').fill('Nytt namn för granskning');
    await form.getByRole('button', { name: 'Send for review' }).click();
    await expect(page.locator('[data-rename-proposed]').getByText(/is waiting for review\.$/)).toBeVisible();

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
    // editor's correction is not a confirmation). The change's case is new in
    // every bank, as the registration's fan-out left it, and no other journey
    // moves it, so it sits on the triage tab; the tab is named and checked
    // rather than reached as the fallback of a tab the feed does not have.
    await page.goto('/watch?tab=triage');
    await expect(page.locator('[data-change-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
    await expect(page.getByRole('tab', { name: /^Needs triage/ })).toHaveAttribute('aria-selected', 'true');
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
    await expect(editor2.locator('[data-rename-proposed]').getByText(/is waiting for review\.$/)).toBeVisible();
    await approveQueueProposal(editor, /Change client_money on flag/);

    await page.goto(changeUrl);
    await expect(page).toHaveURL(changeUrl);
    await expect(classification.locator('[data-pill="brand"]').filter({ hasText: 'Segregated client money' })).toBeVisible();
    await expect(classification.locator('[data-pill="brand"]').filter({ hasText: /^Client money$/ })).toHaveCount(0);

    // Merged into an existing flag: the preview counts the one change this
    // journey put the flag on, the approval moves that change's link to the
    // flag it was merged into, and the merged-away flag leaves the list.
    await editor2.goto('/console/vocabularies');
    await editor2.locator('[data-vocabulary-list="flag"]').click();
    await editor2.locator('[data-value-key="client_money"]').getByRole('button', { name: /^Merge into/ }).click();
    const mergeDialog = editor2.getByRole('dialog', { name: /^Merge "Segregated client money" into/ });
    await mergeDialog.locator('#merge-into').selectOption({ label: 'Advice perimeter' });
    await expect(mergeDialog.getByText('What happens')).toBeVisible();
    await mergeDialog.getByRole('button', { name: 'Merge 1 record', exact: true }).click();
    await expect(mergeDialog.getByText(/is waiting for review\.$/)).toBeVisible();
    await mergeDialog.getByRole('button', { name: 'Done' }).click();
    await approveQueueProposal(editor, /Merge client_money into advice_perimeter on flag/);

    await page.goto(changeUrl);
    await expect(page).toHaveURL(changeUrl);
    await expect(classification.locator('[data-pill="brand"]').filter({ hasText: /^Advice perimeter$/ })).toHaveCount(1);
    await expect(classification.locator('[data-pill="brand"]').filter({ hasText: 'Segregated client money' })).toHaveCount(0);
    await editor2.goto('/console/vocabularies');
    await editor2.locator('[data-vocabulary-list="flag"]').click();
    await expect(editor2.locator('[data-value-key="advice_perimeter"]')).toBeVisible();
    await expect(editor2.locator('[data-value-active][data-value-key="client_money"]')).toHaveCount(0);
  });

  test.describe('footprint', () => {
    // FP-S2 files and rejects a request against tenant A's one scope, FP-S4
    // reads that scope and FP-S5 changes it, so they run in order in one
    // worker. FP-S2 and FP-S5 settle on whether a request is already waiting
    // (the seed leaves one for J-6) before they branch.
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
      // FP-S2: any that would appear are counted too, and so are this bank's open cases, on
      // either side. Other journeys triage this bank's cases in parallel, so the shape is
      // asserted here and test_fp_s2 proves the numbers.
      await expect(reveals.getByText(/^(\d+ obligations?|Nothing\.)$/)).toBeVisible();
      await expect(hides.getByText(/^\d+ open cases?$/)).toBeVisible();
      await expect(reveals.getByText(/^(\d+ open cases?|Nothing\.)$/)).toBeVisible();
      await expect(draft.getByText(/not counted yet/)).toHaveCount(0);
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

    // FP-S4's records outside tenant A's scope as seeded (backend/apps/shared/e2e_seed.py,
    // EXPECTED_OUTSIDE_SCOPE): the seed leaves pension accounts out of the scope, and this
    // obligation and this change fall outside it through that term alone.
    const OUTSIDE_SCOPE_OBLIGATION = 'obl-pension-transfer-right';
    const OUTSIDE_SCOPE_CHANGE = 'chg-e2e-outside-scope';
    // Carries no scope term, so it is inside any scope (EXPECTED_HOME.lead_change). It
    // stays in the week's briefing while its case is open, whoever triages it.
    const IN_SCOPE_CHANGE = 'chg-e2e-research-payments';

    test("FP-S4: Every surface respects the regulatory scope and offers a way to look outside it", async ({ page, apiGuard }) => {
      // FP-03 on the four surfaces R1 has, walked on tenant A's scope as seeded and never
      // changed here: FP-S5 changes it later in this worker, and the home and watch
      // journeys read it in parallel. Changing the scope and seeing records hide is FP-S5's
      // (J-6) and the integration half of FP-S4's. The fifth surface, the reports, stays
      // with chunk 12: every report reads the obligation register, which R1 does not have
      // (backend/apps/taxonomy/app.md, the notes under FP-S4).
      allowFreshContext(apiGuard);
      await signInAs(page, LOGINS.reader);

      // The feed opens on the cases that need triage, in our scope by default. It has no
      // tab for every case and other journeys triage cases in parallel (J-2 the lead), so
      // no in-scope change is named here: no row shown is marked outside, and the outside
      // change, whose case nobody works, is absent. "Show outside our scope" adds it,
      // marked, and leaves a row that was shown before unmarked.
      await page.goto('/watch');
      const rows = page.locator('[data-change-rows] [data-change]');
      const outsideChange = page.locator(`[data-change="${OUTSIDE_SCOPE_CHANGE}"]`);
      await expect(page.locator('[data-change-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
      await expect(outsideChange).toHaveCount(0);
      await expect(page.locator('[data-change][data-outside-footprint]')).toHaveCount(0);
      const shownInScope = (await rows.count()) > 0 ? await rows.first().getAttribute('data-change') : null;
      await page.getByRole('group', { name: 'Scope' }).getByRole('button', { name: 'Show outside our scope' }).click();
      await expect(page).toHaveURL(/scope=all/);
      await expect(outsideChange).toHaveAttribute('data-outside-footprint', '');
      if (shownInScope !== null) await expect(page.locator(`[data-change="${shownInScope}"]`)).not.toHaveAttribute('data-outside-footprint');
      // Library titles are rows, not catalog copy: the roadmap and the briefing are
      // checked for the title this row shows.
      const title = (await outsideChange.locator('h3').textContent())?.trim() ?? '';
      expect(title).not.toBe('');

      // The inventory, narrowed to the obligation's regime so a growing library never pages
      // it out of sight: absent by default while the rest reads, then marked once the Scope
      // filter is set to "Show outside our scope".
      await page.goto(`/inventory?regime=insurance&asOf=${INVENTORY_AS_OF}`);
      const outsideObligation = page.locator(`[data-obligation="${OUTSIDE_SCOPE_OBLIGATION}"]`);
      await expect(page.locator('[data-obligation]').first()).toBeVisible();
      await expect(outsideObligation).toHaveCount(0);
      await page.getByRole('group', { name: 'Scope' }).getByRole('button', { name: 'Show outside our scope' }).click();
      await expect(page).toHaveURL(/scope=all/);
      await expect(outsideObligation).toHaveAttribute('data-outside-footprint', '');

      // The roadmap: the change's date is within the quarters shown, and it is not there.
      await page.goto('/roadmap');
      const cards = page.locator('[data-roadmap-roster] [data-roadmap-card]');
      await expect(cards.first()).toBeVisible();
      await expect(cards.filter({ hasText: title })).toHaveCount(0);

      // The briefing: both changes were first seen this week. The in-scope one leads or
      // follows; the outside one is neither the lead, an item nor coming up.
      await page.goto('/briefing');
      await expect(page.locator(`[data-lead-card="${IN_SCOPE_CHANGE}"], [data-brief-item="${IN_SCOPE_CHANGE}"]`).first()).toBeVisible();
      await expect(page.locator(`[data-lead-card="${OUTSIDE_SCOPE_CHANGE}"]`)).toHaveCount(0);
      await expect(page.locator(`[data-brief-item="${OUTSIDE_SCOPE_CHANGE}"]`)).toHaveCount(0);
      await expect(page.locator('[data-coming-up] [data-roadmap-item]').filter({ hasText: title })).toHaveCount(0);
    });

    /** The id of the request the next "Request approval" files: the audit log names it. */
    function nextRequestId(page: Page): Promise<string> {
      return page
        .waitForResponse((r) => r.url().endsWith('/api/v1/tenant/footprint/requests') && r.request().method() === 'POST' && r.ok())
        .then(async (r) => ((await r.json()) as { id: string }).id);
    }

    /** Puts Advice back through the same door when it is out, so the scope reads as seeded; the restoring request's id, or null when nothing needed it. */
    async function restoreAdvice(page: Page, approver: Page): Promise<string | null> {
      await page.goto('/admin/footprint');
      await expect(adviceItem(page)).toBeVisible();
      if ((await page.locator('[data-pending-request]').count()) > 0 || !/Not in our scope/.test((await adviceItem(page).textContent()) ?? '')) return null;
      await page.getByRole('button', { name: 'Propose a change' }).click();
      await adviceCheckbox(page).check();
      const filed = nextRequestId(page);
      await page.locator('[data-draft-preview]').getByRole('button', { name: 'Request approval' }).click();
      await expect(page.getByText('Sent for approval.', { exact: true })).toBeFocused();
      const id = await filed;
      await approveWithPasskey(approver);
      return id;
    }

    /** TAX-14: the audit log holds exactly one event of this action for Advice, naming the request that caused it, confirmed with a passkey. */
    async function expectAdviceEvent(page: Page, action: 'footprint.term_removed' | 'footprint.term_added', requestId: string): Promise<void> {
      await page.goto('/admin/audit-log');
      await expect(page.getByRole('heading', { level: 1, name: 'Audit log' })).toBeVisible();
      await page.getByLabel('Record kind').selectOption('footprint');
      // A removal carries the term and its request as the state before, an addition as the state after.
      const side = action === 'footprint.term_removed' ? 'before' : 'after';
      const events = page
        .locator(`[data-audit-row][data-subject-type="footprint"][data-action="${action}"]`)
        .filter({ has: page.locator(`[data-audit-diff] [data-field="request"] [data-${side}]`, { hasText: requestId }) });
      await expect(events).toHaveCount(1);
      await expect(events.locator(`[data-audit-diff] [data-field="term"] [data-${side}]`)).toHaveText('advice');
      await expect(events.locator(`[data-audit-diff] [data-field="dimension"] [data-${side}]`)).toHaveText(SERVICES);
      await expect(events.getByText('Confirmed with a passkey')).toBeVisible();
    }

    test("FP-S5 J-6 @smoke: footprint change with preview and second-person approval", async ({ page, browser, apiGuard }, testInfo) => {
      // FP-S5 (FP-01, FP-02, FP-03, AC-FP1, J-6): the officer's request with its
      // preview, the approver's passkey step-up, the footprint changed on screen,
      // the advice-only obligation gone from the inventory, and the audit log's
      // one event per term, each naming its request (TAX-14), for the removal
      // and for the restore that puts the scope back as seeded.
      allowFreshContext(apiGuard);
      apiGuard.allow(/\/api\/v1\/tenant\/footprint\/requests\/[^/]+\/approve$/, 403, 'the first attempt answers step_up_required and opens the prompt');
      await signInAs(page, LOGINS.complianceOfficer);
      await officerStartsClean(page);
      const removal = nextRequestId(page);
      await officerRemovesAdvice(page);
      const removalId = await removal;

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

        await page.getByRole('group', { name: 'Scope' }).getByRole('button', { name: 'Show outside our scope' }).click();
        await expect(adviceOnlyRow(page)).toHaveAttribute('data-outside-footprint', '');
        await expect(adviceOnlyRow(page).getByText('Outside our scope: Advice')).toBeVisible();

        // The audit log: one removal for Advice naming the request, then one addition naming the restore.
        await expectAdviceEvent(page, 'footprint.term_removed', removalId);
        const restoreId = await restoreAdvice(page, approver);
        expect(restoreId).not.toBeNull();
        await expectAdviceEvent(page, 'footprint.term_added', restoreId ?? '');
      } finally {
        // On a failure too: the scope reads as seeded for every journey after this one.
        await restoreAdvice(page, approver);
        await approver.context().close();
      }
    });

    // FP-S16's standard (backend/apps/shared/e2e_seed.py, E2E_STANDARD_OBLIGATION and
    // E2E_STANDARD_TERM): the one conformance duty carries the standard's term, which no
    // seeded bank follows, under an instrument whose regime tenant A holds.
    const STANDARD_DIMENSION = 'standard';
    const STANDARD_TERM = 'iso_iec_27001';
    const STANDARD_OBLIGATION = 'iso-iec-27001-2022-conformance';

    function standardGroup(page: Page) {
      return page.locator(`[data-dimension="${STANDARD_DIMENSION}"]`);
    }

    function standardCheckbox(page: Page) {
      return standardGroup(page).getByRole('checkbox', { name: /^ISO\/IEC 27001$/ });
    }

    /** The duty in tenant A's inventory, narrowed to its regime so a growing library never pages it out. */
    async function openStandardDuty(page: Page) {
      await page.goto(`/inventory?regime=ai_ict&asOf=${INVENTORY_AS_OF}`);
      await expect(page.locator('[data-obligation-rows]').or(page.locator('[data-empty-state]')).first()).toBeVisible();
      return page.locator(`[data-obligation="${STANDARD_OBLIGATION}"]`);
    }

    /** Ticks or unticks the standard and waits for the counted preview. */
    async function draftStandard(page: Page, follow: boolean) {
      await page.goto('/admin/footprint');
      await page.getByRole('button', { name: 'Propose a change' }).click();
      if (follow) await standardCheckbox(page).check();
      else await standardCheckbox(page).uncheck();
      const draft = page.locator('[data-draft-preview]');
      await expect(draft.getByRole('heading', { name: follow ? 'Your change: Add ISO/IEC 27001' : 'Your change: Remove ISO/IEC 27001' })).toBeVisible();
      await expect(draft.getByText('Loading…')).toHaveCount(0);
      return draft;
    }

    async function sendDraft(page: Page): Promise<void> {
      await page.locator('[data-draft-preview]').getByRole('button', { name: 'Request approval' }).click();
      await expect(page.getByText('Sent for approval.', { exact: true })).toBeFocused();
    }

    test("FP-S16: A standard shows only to tenants whose regulatory scope names it", async ({ page, browser, apiGuard }, testInfo) => {
      // FP-S16 (FP-01, FP-02, INV-08, AC-FP3). The one audit event per added term is proved
      // by the backend's FP-S16 test; here, the screens: absent, proposed, approved with a
      // passkey, visible, and taken out again through the same door.
      allowFreshContext(apiGuard);
      apiGuard.allow(/\/api\/v1\/tenant\/footprint\/requests\/[^/]+\/approve$/, 403, 'the first attempt answers step_up_required and opens the prompt');
      await signInAs(page, LOGINS.complianceOfficer);
      await officerStartsClean(page);

      // Absent from the inventory, and there, marked, under "Show outside our scope".
      const duty = await openStandardDuty(page);
      await expect(duty).toHaveCount(0);
      await page.getByRole('button', { name: 'Show outside our scope' }).click();
      await expect(duty).toHaveAttribute('data-outside-footprint', '');

      // The scope page reads the empty opt-in group as following nothing, never as unrestricted.
      await page.goto('/admin/footprint');
      await expect(standardGroup(page).getByText('None followed.', { exact: true })).toBeVisible();
      await expect(standardGroup(page).getByText('Not restricted: every option applies.')).toHaveCount(0);

      const approver = await secondPerson(browser, apiGuard, testInfo, LOGINS.approver);
      try {
        // Following it reveals the duty, hides nothing and warns of no narrowing.
        const follow = await draftStandard(page, true);
        await expect(follow.locator('[data-preview-side="reveals"]').getByText(/^[1-9]\d* obligations?$/)).toBeVisible();
        // Now that open cases are counted too (tax-preview-cases), a side that moves nothing
        // of any kind says so in one word.
        await expect(follow.locator('[data-preview-side="hides"]').getByText('Nothing.', { exact: true })).toBeVisible();
        await expect(follow.locator('[data-notice="warn"]')).toHaveCount(0);
        await expect(follow.getByText(/will start to filter/)).toHaveCount(0);
        await sendDraft(page);
        await expect(standardGroup(page).locator(`[data-term="${STANDARD_TERM}"]`).getByText('Added when approved')).toBeVisible();

        await approveWithPasskey(approver);
        await page.goto('/admin/footprint');
        await expect(standardGroup(page).locator(`[data-term="${STANDARD_TERM}"]`)).toHaveText(/^ISO\/IEC 27001 In our scope$/);

        // Now in the inventory, inside the scope.
        const followed = await openStandardDuty(page);
        await expect(followed).toBeVisible();
        await expect(followed).not.toHaveAttribute('data-outside-footprint');

        // Removing it counts the duty as hidden, and the warning says what that means.
        const unfollow = await draftStandard(page, false);
        await expect(unfollow.locator('[data-preview-side="hides"]').getByText(/^[1-9]\d* obligations?$/)).toBeVisible();
        await expect(unfollow.getByText('What this hides leaves the feed, the inventory, the roadmap and the briefing for every member.')).toBeVisible();
        await sendDraft(page);
        await approveWithPasskey(approver);
        await page.goto('/admin/footprint');
        await expect(standardGroup(page).getByText('None followed.', { exact: true })).toBeVisible();
      } finally {
        // Restore the scope as seeded, on failure too: withdraw a request of ours still
        // waiting, then take the standard out again through the same door if it is held.
        await officerStartsClean(page);
        await expect(standardGroup(page)).toBeVisible();
        if ((await page.locator('[data-pending-request]').count()) === 0 && (await standardGroup(page).locator(`[data-term="${STANDARD_TERM}"]`).count()) > 0) {
          await draftStandard(page, false);
          await sendDraft(page);
          await approveWithPasskey(approver);
        }
        await approver.context().close();
      }
    });
  });
});

// PRD 0.3: the regulatory scope's restricted page (FP-02) and markets (FP-04).
// Each stays test.fixme until the task in docs/plans/briefs/FEATURES_0_3_TASKS.md
// that builds it lands. The opt-in standards dimension (INV-08), FP-S16, changes
// tenant A's scope, so it runs with the footprint journeys above.
test.describe('regulatory scope, markets and standards', () => {
  test("FP-S7: Members without scope permissions cannot open the regulatory scope page", async ({ page, browser, apiGuard }, testInfo) => {
    // FP-02, ADM-01. Only reads: the footprint journeys above file and decide
    // requests against tenant A's one scope in another worker, so each login
    // settles on the page's loaded state before it branches on a waiting request.
    allowFreshContext(apiGuard);

    // A reader holds neither footprint.request nor footprint.approve: no entry
    // in Admin, and the page opened directly is the restricted page naming the permission.
    await signInAs(page, LOGINS.reader);
    await page.goto('/admin');
    await expect(page.locator('[data-admin-section="admin-organisation"]')).toBeVisible();
    await expect(page.locator('[data-admin-section="admin-footprint"]')).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'Regulatory scope', exact: true })).toHaveCount(0);
    await page.goto('/admin/footprint');
    const restricted = page.getByRole('alert').filter({ hasText: 'This page is not available to you' });
    await expect(restricted).toContainText('Needs footprint request');
    await expect(page.locator('[data-footprint-dimensions]')).toHaveCount(0);

    // The approver holds footprint.approve only: the scope reads, nothing on it
    // is a checkbox, nothing offers to propose, and a phone never scrolls sideways.
    const approver = await secondPerson(browser, apiGuard, testInfo, LOGINS.approver);
    await approver.setViewportSize({ width: 375, height: 812 });
    await approver.goto('/admin/footprint');
    await expect(approver.locator('[data-footprint-dimensions]')).toBeVisible();
    await expect(approver.getByRole('checkbox')).toHaveCount(0);
    await expect(approver.getByRole('button', { name: 'Propose a change' })).toHaveCount(0);
    expect(await approver.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await approver.context().close();

    // The compliance officer holds footprint.request: offered "Propose a change"
    // while nothing waits, or their own waiting request to withdraw (only the
    // officer files requests on tenant A, and one waits at a time).
    const officer = await secondPerson(browser, apiGuard, testInfo, LOGINS.complianceOfficer);
    await officer.goto('/admin/footprint');
    await expect(officer.locator('[data-footprint-dimensions]')).toBeVisible();
    const waiting = officer.locator('[data-pending-request]');
    if ((await waiting.count()) === 0) {
      await expect(officer.getByRole('button', { name: 'Propose a change' })).toBeVisible();
    } else {
      await expect(waiting.getByRole('button', { name: 'Withdraw' })).toBeVisible();
    }
    await officer.context().close();
  });

  // --- tax-market-journeys (FP-S8, FP-S10) ---------------------------------------------
  // FP-S8 narrows tenant B's scope to Denmark while it waits, hiding every Swedish
  // obligation of that bank, so it runs alone and restores the scope on failure too. No
  // other journey reads tenant B's inventory; J-8 (TEN-S7) reads B's scope screen and
  // asserts only what holds either way. The obligations are the seed's
  // (backend/apps/shared/e2e_seed.py, EXPECTED_MARKET_JOURNEY), each inside B's scope.
  test.describe('operating markets', () => {
    test.describe.configure({ mode: 'serial' });

    const UNION_OBLIGATION = 'obl-esma-warnings';
    const HOME_OBLIGATION = 'obl-appropriateness';
    const COUNTRY_OBLIGATION = 'obl-dk-csd-registration';
    const JURISDICTIONS = '[data-dimension="jurisdiction"]';

    async function approveScopeChange(approver: Page): Promise<void> {
      await approver.goto('/admin/footprint');
      await approver.locator('[data-pending-request]').getByRole('button', { name: 'Approve' }).click();
      await approver.getByRole('dialog', { name: /^Approve ".+"\?$/ }).getByRole('button', { name: 'Approve with passkey' }).click();
      // Step-up: settle on the prompt or the outcome, since a sign-in moments ago may still count.
      const prompt = approver.getByRole('dialog', { name: 'Confirm with your passkey' });
      const done = approver.getByText('Approved. The regulatory scope has changed.');
      await expect(prompt.or(done).first()).toBeVisible();
      if (await prompt.isVisible()) await prompt.getByRole('button', { name: 'Use passkey' }).click();
      await expect(done).toBeVisible();
    }

    /** Tenant B's scope as seeded: no request of the admin's waiting and no jurisdiction held. */
    async function restoreSecondBank(page: Page, approver: Page): Promise<void> {
      await page.goto('/admin/footprint');
      const mine = page.locator('[data-pending-request]').filter({ hasText: /You requested this on/ });
      await expect(mine.or(page.locator('[data-footprint-dimensions]')).first()).toBeVisible();
      if ((await mine.count()) > 0) {
        await mine.getByRole('button', { name: 'Withdraw' }).click();
        await expect(page.getByText('Withdrawn.', { exact: true })).toBeFocused();
      }
      const denmark = page.locator(`${JURISDICTIONS} [data-term="dk"]`);
      if ((await denmark.count()) > 0 && /In our scope/.test((await denmark.textContent()) ?? '')) {
        await page.getByRole('button', { name: 'Propose a change' }).click();
        await page.locator(JURISDICTIONS).getByRole('checkbox', { name: /^Denmark$/ }).uncheck();
        await page.locator('[data-draft-preview]').getByRole('button', { name: 'Request approval' }).click();
        await expect(page.getByText('Sent for approval.', { exact: true })).toBeFocused();
        await approveScopeChange(approver);
        await page.reload();
      }
      await expect(page.locator(JURISDICTIONS).getByText('Not restricted')).toBeVisible();
    }

    test("FP-S8: Turning on a country brings the EU rules that reach it", async ({ page, browser, apiGuard }, testInfo) => {
      allowFreshContext(apiGuard);
      apiGuard.allow(/\/api\/v1\/tenant\/footprint\/requests\/[^/]+\/approve$/, 403, 'the first attempt answers step_up_required and opens the prompt');
      await signInAs(page, LOGINS.secondBankAdmin);
      const approver = await secondPerson(browser, apiGuard, testInfo, LOGINS.secondBankApprover);
      try {
        await restoreSecondBank(page, approver);

        // No jurisdiction held, so every market's rules show: the Swedish, the Danish and the EU one.
        await openInventory(page);
        for (const key of [UNION_OBLIGATION, HOME_OBLIGATION, COUNTRY_OBLIGATION]) {
          await expect(page.locator(`[data-obligation="${key}"]`)).toBeVisible();
        }

        // Turn on Denmark and preview: the change hides obligations (the Swedish ones).
        await page.goto('/admin/footprint');
        await page.getByRole('button', { name: 'Propose a change' }).click();
        await page.locator(JURISDICTIONS).getByRole('checkbox', { name: /^Denmark$/ }).check();
        const draft = page.locator('[data-draft-preview]');
        await expect(draft.getByRole('heading', { name: 'Your change: Add Denmark' })).toBeVisible();
        await expect(draft.getByText('Loading…')).toHaveCount(0);
        await expect(draft.locator('[data-preview-side="hides"]').getByText(/^[1-9]\d* obligations?$/)).toBeVisible();
        await draft.getByRole('button', { name: 'Request approval' }).click();
        await expect(page.getByText('Sent for approval.', { exact: true })).toBeFocused();
        const banner = page.locator('[data-pending-request]');
        await expect(banner.getByText('Add Denmark', { exact: true })).toBeVisible();
        // Four eyes: the requester may withdraw, never approve.
        await expect(banner.getByRole('button', { name: 'Approve' })).toHaveCount(0);
        await expect(page.locator(`${JURISDICTIONS} [data-term="dk"]`).getByText('Added when approved')).toBeVisible();

        // The second person approves with a passkey; the request held Denmark only.
        await approveScopeChange(approver);
        await expect(approver.locator('[data-history-entry="approved"]').first()).toContainText('approved "Add Denmark"');
        await page.reload();
        await expect(page.locator(`${JURISDICTIONS} [data-term="dk"]`)).toHaveText(/^Denmark In our scope$/);
        await expect(page.locator(`${JURISDICTIONS} [data-term="se"]`)).toHaveText(/^Sweden Not in our scope$/);
        await expect(page.locator('[data-markets] [data-market="dk"]')).toContainText('Operating');

        // The inventory lists the EU and the Danish obligation, and no Swedish one.
        await openInventory(page);
        await expect(page.locator(`[data-obligation="${UNION_OBLIGATION}"]`)).toBeVisible();
        await expect(page.locator(`[data-obligation="${COUNTRY_OBLIGATION}"]`)).toBeVisible();
        await expect(page.locator(`[data-obligation="${HOME_OBLIGATION}"]`)).toHaveCount(0);
        await page.getByRole('button', { name: 'Show outside our scope' }).click();
        await expect(page.locator(`[data-obligation="${HOME_OBLIGATION}"]`)).toHaveAttribute('data-outside-footprint', '');
      } finally {
        await restoreSecondBank(page, approver);
        await approver.context().close();
      }
    });
  });

  // FP-S10 on tenant A, which watches Denmark as seeded. Norway is watched and unwatched
  // here alone. The read-only view is the approver's: a reader holds no scope permission,
  // so the screen is closed to them (FP-S7); the approver reads it without footprint.request.
  test("FP-S10: Watching a market is one audited write that hides nothing", async ({ page, browser, apiGuard }, testInfo) => {
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.admin);
    await page.goto('/admin/footprint');
    const norway = page.locator('[data-markets] [data-market="no"]');
    const watching = norway.getByRole('button', { name: 'Watching Norway' });
    await expect(watching).toHaveAttribute('aria-pressed', 'false');
    // Only the jurisdictions are compared: FP-S5 changes tenant A's services in parallel.
    const jurisdictions = page.locator('[data-footprint-dimensions] [data-dimension="jurisdiction"]');
    const jurisdictionsBefore = (await jurisdictions.textContent()) ?? '';

    try {
      // One write, no second person and no step-up: the toggle saves at once.
      await watching.click();
      await expect(watching).toHaveAttribute('aria-pressed', 'true');
      await expect(page.getByRole('dialog')).toHaveCount(0);
      await page.reload();
      await expect(watching).toHaveAttribute('aria-pressed', 'true');
      // Watching hides nothing: the jurisdictions read as before and nothing waits for approval.
      await expect(jurisdictions).toHaveText(jurisdictionsBefore);
      await expect(page.locator('[data-pending-request]').filter({ hasText: /Norway/ })).toHaveCount(0);

      // One audit event holding the key only.
      await page.goto('/admin/audit-log');
      await page.getByLabel('Record kind').selectOption('watched_market');
      const added = page.locator('[data-audit-row][data-action="markets.watch_added"]').filter({ has: page.locator('[data-field="jurisdiction"] [data-after]', { hasText: /^no$/ }) });
      await expect(added.first()).toBeVisible();
      await expect(added.first().locator('[data-audit-diff] [data-field]')).toHaveCount(1);
      await expect(added.first().getByText('Confirmed with a passkey')).toHaveCount(0);

      // Someone without footprint.request sees which markets are operating and watched, and no toggle.
      const readOnly = await secondPerson(browser, apiGuard, testInfo, LOGINS.approver);
      await readOnly.goto('/admin/footprint');
      const markets = readOnly.locator('[data-markets]');
      await expect(markets.locator('[data-market="no"]')).toHaveText(/^Norway\s*Watching$/);
      await expect(markets.locator('[data-market="dk"]')).toHaveText(/^Denmark\s*Watching$/);
      await expect(markets.getByRole('button')).toHaveCount(0);
      await expect(markets.getByText(/^You can see the regulatory scope\. Changing it needs /)).toBeVisible();
      await readOnly.context().close();
    } finally {
      // Switch it off whatever happened above, so Norway reads as seeded.
      await page.goto('/admin/footprint');
      await expect(watching).toBeVisible();
      if ((await watching.getAttribute('aria-pressed')) === 'true') await watching.click();
      await expect(watching).toHaveAttribute('aria-pressed', 'false');
    }

    // The removal is audited too, on the same watch row.
    await page.goto('/admin/audit-log');
    await page.getByLabel('Record kind').selectOption('watched_market');
    const removed = page.locator('[data-audit-row][data-action="markets.watch_removed"]').filter({ has: page.locator('[data-field="jurisdiction"] [data-before]', { hasText: /^no$/ }) });
    await expect(removed.first()).toBeVisible();
    const watchRow = await removed.first().getAttribute('data-subject-id');
    await expect(page.locator(`[data-audit-row][data-action="markets.watch_added"][data-subject-id="${watchRow}"]`)).toHaveCount(1);
  });
  // --- end tax-market-journeys ----------------------------------------------------------


  test("FP-S13: The watched-market view of the inventory shows only what watching adds", async ({ page, apiGuard }) => {
    // Tenant A as seeded (backend/apps/shared/e2e_seed.py): operating in Sweden, providing
    // Custody and watching Denmark (EXPECTED_FOOTPRINTS, EXPECTED_WATCHED_MARKETS), so the
    // Danish custody duty is what watching adds. Read only: no journey changes the watch.
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    const danish = page.locator(`[data-obligation="${WATCHED_MARKET_OBLIGATION}"]`);

    // In our scope, the default, the Danish duty is hidden while the rest reads.
    await page.goto(`/inventory?regime=securities&asOf=${INVENTORY_AS_OF}`);
    await expect(page.locator('[data-obligation]').first()).toBeVisible();
    await expect(danish).toHaveCount(0);

    // "Markets we watch" is one value of the one Scope filter: choosing it presses it alone.
    const scope = page.getByRole('group', { name: 'Scope' });
    await scope.getByRole('button', { name: 'Markets we watch' }).click();
    await expect(page).toHaveURL(/scope=watched/);
    await expect(scope.getByRole('button', { name: 'Markets we watch' })).toHaveAttribute('aria-pressed', 'true');
    await expect(scope.getByRole('button', { name: 'In our scope' })).toHaveAttribute('aria-pressed', 'false');
    await expect(scope.getByRole('button', { name: 'Show outside our scope' })).toHaveAttribute('aria-pressed', 'false');

    // The Danish "Custody" duty is listed with its market as meta text, neither dashed nor
    // marked outside; no EU or Swedish duty is listed, because they are already in the
    // scope, and every row names Denmark.
    await expect(danish).toHaveAttribute('data-watched-market', 'dk');
    await expect(danish.getByText('Market we watch: Denmark', { exact: true })).toBeVisible();
    await expect(danish).not.toHaveAttribute('data-outside-footprint');
    await expect(page.locator('[data-obligation-rows] [data-obligation]:not([data-watched-market="dk"])')).toHaveCount(0);

    // The Instruments tab keeps the value and lists the Danish act alone.
    await page.getByRole('tab', { name: 'Instruments' }).click();
    await expect(page).toHaveURL(/tab=instruments.*scope=watched/);
    await expect(page.locator(`[data-instrument-rows] [data-instrument="${WATCHED_MARKET_INSTRUMENT}"]`)).toBeVisible();
    await expect(page.locator('[data-instrument="fffs-2017-2"]')).toHaveCount(0);
  });

  test("FP-S15: A change's jurisdiction comes from its authority, and the feed has the watched-market view", async ({ page, apiGuard }) => {
    // Tenant A operates in Sweden and watches Denmark, as seeded (backend/apps/shared/e2e_seed.py,
    // tax-watched-feed): the Danish authority's custody change is outside its scope by
    // jurisdiction alone, while the Swedish lead change is inside it. The journey reads
    // the scope and never changes it.
    const danish = page.locator(`[data-change="${WATCHED_MARKET_CHANGE}"]`);
    const swedish = page.locator(`[data-change="${IN_SCOPE_CHANGE}"]`);
    const scope = page.getByRole('group', { name: 'Scope' });
    allowFreshContext(apiGuard);
    await signInAs(page, LOGINS.reader);
    await page.goto('/watch');
    await expect(swedish).toBeVisible();
    await expect(danish).toHaveCount(0);

    // Markets we watch lists only what watching adds, the market named as text.
    await scope.getByRole('button', { name: 'Markets we watch' }).click();
    await expect(page).toHaveURL(/scope=watched/);
    await expect(danish).toBeVisible();
    await expect(danish).toContainText('Market we watch: Denmark');
    await expect(swedish).toHaveCount(0);
    // Watching opened nothing: the case still waits for triage, as creation left it.
    await expect(danish).toContainText('Needs triage');

    // Looking outside the scope shows it too, still naming the market it comes from.
    await scope.getByRole('button', { name: 'Show outside our scope' }).click();
    await expect(swedish).toBeVisible();
    await expect(danish).toContainText('Market we watch: Denmark');
  });

});
